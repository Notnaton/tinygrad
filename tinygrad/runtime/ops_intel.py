from __future__ import annotations
import ctypes, functools, math, time, weakref
from dataclasses import dataclass
from tinygrad.device import BufferSpec
from tinygrad.helpers import DEV, from_mv, round_up
from tinygrad.runtime.autogen import xe_drm
from tinygrad.runtime.support.hcq import HCQAllocator, HCQArgsState, HCQBuffer, HCQCompiled, HCQProgram, HCQSignal, HWQueue, MMIOInterface
from tinygrad.runtime.support.intel import is_battlemage, make_user_fence
from tinygrad.runtime.support.intel_kmd import XeBufferObject, XeKmdDevice, discover_xe_render_nodes
from tinygrad.runtime.support.intel_program import IntelProgramImage, load_zebin
from tinygrad.runtime.support.intel_va import IntelVAAllocator
from tinygrad.runtime.support.intel_xe2 import Xe2CommandBuffer, cfe_state, compute_walker, pipe_control, state_base_address
from tinygrad.renderer.intel import IntelOpenCLRenderer
from tinygrad.uop.ops import sint

class MOCKIface:
  """Opt-in command capture interface. Selected only with DEV=MOCK+INTEL."""
  def __init__(self, dev:IntelDevice, device_id:int):
    self.dev, self.device_id, self.count, self.peer_group = dev, device_id, 1, f"INTEL_MOCK_{device_id}"
    self.submissions:list[bytes] = []

  def submit(self, batch:bytes): self.submissions.append(batch)

@dataclass(frozen=True)
class XeAllocation:
  bo: XeBufferObject
  cpu_address: int
  gpu_address: int

class XEKMDIface:
  """Explicitly selected DRM Xe interface. Initial bring-up is synchronous and uses CPU-mappable system memory."""
  def __init__(self, dev:IntelDevice, device_id:int, *, nodes=None, kmd:XeKmdDevice|None=None):
    nodes = discover_xe_render_nodes() if nodes is None else tuple(nodes)
    if not nodes: raise RuntimeError("no Intel render node bound to the Xe driver was found")
    if device_id < 0 or device_id >= len(nodes): raise IndexError(f"Intel Xe device index {device_id} is out of range for {len(nodes)} nodes")
    self.dev, self.count, self.node = dev, len(nodes), nodes[device_id]
    self.kmd = kmd or XeKmdDevice(self.node)
    self.config, engines, regions = self.kmd.config(), self.kmd.engines(), self.kmd.memory_regions()
    if self.config.device_id != self.node.device_id: raise RuntimeError("Xe query device ID does not match the render node")
    if not is_battlemage(self.config.device_id): raise RuntimeError(f"unsupported non-Battlemage Xe device 0x{self.config.device_id:04x}")
    self.compute_engine = next((engine for engine in engines if engine.engine_class == xe_drm.DRM_XE_ENGINE_CLASS_COMPUTE), None)
    if self.compute_engine is None: raise RuntimeError("Xe device reports no compute engine")
    self.memory_region = next((region for region in regions if region.mem_class == xe_drm.DRM_XE_MEM_REGION_CLASS_SYSMEM), None)
    if self.memory_region is None: raise RuntimeError("initial Xe bring-up requires a system-memory region")
    if self.memory_region.instance >= 32: raise RuntimeError(f"Xe memory-region instance {self.memory_region.instance} does not fit placement mask")
    self.alignment = max(0x1000, self.config.min_alignment, self.memory_region.min_page_size)
    self.placement = 1 << self.memory_region.instance
    self.peer_group = f"INTEL_XE_{self.node.path}"
    self.allocations:dict[int, XeAllocation] = {}
    self.closed = False
    self.vm_id = self.kmd.create_vm()
    try: self.exec_queue_id = self.kmd.create_exec_queue(self.vm_id, (self.compute_engine,))
    except Exception:
      self.kmd.destroy_vm(self.vm_id)
      raise

  def _bind_sync(self, submit):
    storage = ctypes.c_uint64(0)
    address = ctypes.addressof(storage)
    submit((make_user_fence(address, timeline_value=1),))
    self.kmd.wait_user_fence(address, 1, 30_000_000_000)

  def alloc(self, size:int) -> HCQBuffer:
    if self.closed: raise RuntimeError("Xe device is closed")
    size = round_up(size, self.alignment)
    bo, cpu_address, gpu_address = None, 0, 0
    try:
      bo = self.kmd.create_bo(size, self.placement, self.vm_id, cpu_caching=xe_drm.DRM_XE_GEM_CPU_CACHING_WB)
      cpu_address = self.kmd.mmap_bo(bo)
      gpu_address = self.dev.va_allocator.alloc(size, self.alignment)
      self._bind_sync(lambda syncs: self.kmd.bind(self.vm_id, bo, gpu_address, size, syncs=syncs))
    except Exception:
      if gpu_address: self.dev.va_allocator.free(gpu_address)
      if cpu_address: self.kmd.munmap_bo(cpu_address, size)
      if bo is not None: self.kmd.close_bo(bo)
      raise
    allocation = XeAllocation(bo, cpu_address, gpu_address)
    self.allocations[bo.handle] = allocation
    return HCQBuffer(gpu_address, size, meta=allocation, view=MMIOInterface(cpu_address, size), owner=self.dev)

  def free(self, buf:HCQBuffer):
    if not isinstance(buf.meta, XeAllocation): raise ValueError("Xe buffer is missing allocation metadata")
    allocation = buf.meta
    if allocation.bo.handle not in self.allocations:
      if self.closed: return
      raise ValueError(f"Xe GEM handle {allocation.bo.handle} is not live")
    self._bind_sync(lambda syncs: self.kmd.unbind(self.vm_id, allocation.gpu_address, allocation.bo.size, syncs=syncs))
    self.kmd.munmap_bo(allocation.cpu_address, allocation.bo.size)
    self.kmd.close_bo(allocation.bo)
    self.dev.va_allocator.free(allocation.gpu_address)
    del self.allocations[allocation.bo.handle]

  def submit(self, batch:bytes):
    if self.closed: raise RuntimeError("Xe device is closed")
    fence_offset = round_up(len(batch), 8)
    batch_buf = self.alloc(fence_offset + 8)
    try:
      batch_buf.cpu_view().view(size=len(batch), fmt='B')[:] = batch
      batch_buf.cpu_view().view(offset=fence_offset, size=8, fmt='Q')[0] = 0
      self.kmd.exec(self.exec_queue_id, int(batch_buf.va_addr),
                    (make_user_fence(int(batch_buf.va_addr)+fence_offset, timeline_value=1),))
      self.kmd.wait_user_fence(batch_buf.cpu_view().addr+fence_offset, 1, 30_000_000_000, exec_queue_id=self.exec_queue_id)
    finally: self.free(batch_buf)

  def device_fini(self):
    if self.closed: return
    self.kmd.destroy_exec_queue(self.exec_queue_id)
    for allocation in tuple(self.allocations.values()):
      self._bind_sync(lambda syncs, allocation=allocation: self.kmd.unbind(
        self.vm_id, allocation.gpu_address, allocation.bo.size, syncs=syncs))
      self.kmd.munmap_bo(allocation.cpu_address, allocation.bo.size)
      self.kmd.close_bo(allocation.bo)
      self.dev.va_allocator.free(allocation.gpu_address)
      del self.allocations[allocation.bo.handle]
    self.kmd.destroy_vm(self.vm_id)
    self.closed = True

class IntelAllocator(HCQAllocator['IntelDevice']):
  def __init__(self, dev:IntelDevice):
    super().__init__(dev, batch_size=0x1000, batch_cnt=1, supports_copy_from_disk=False, supports_transfer=False)

  def _alloc(self, size:int, options:BufferSpec) -> HCQBuffer:
    if isinstance(self.dev.iface, XEKMDIface): return self.dev.iface.alloc(size)
    size = round_up(size, 0x1000)
    storage = ctypes.create_string_buffer(size)
    va = self.dev.va_allocator.alloc(size, 0x1000)
    return HCQBuffer(va, size, meta=storage, view=MMIOInterface(ctypes.addressof(storage), size), owner=self.dev)

  def _do_free(self, buf:HCQBuffer, options:BufferSpec|None):
    if isinstance(self.dev.iface, XEKMDIface): self.dev.iface.free(buf)
    else: self.dev.va_allocator.free(int(buf.va_addr))
  def _copyin(self, dest:HCQBuffer, src:memoryview): ctypes.memmove(dest.cpu_view().addr, bytes(src), len(src))
  def _copyout(self, dest:memoryview, src:HCQBuffer): ctypes.memmove(from_mv(dest), src.cpu_view().addr, len(dest))

class IntelArgsState(HCQArgsState['IntelProgram']):
  def __init__(self, buf:HCQBuffer, prg:IntelProgram, bufs:tuple[HCQBuffer, ...], vals:tuple[sint|None, ...]=()):
    super().__init__(buf, prg, bufs, vals)
    if int(buf.va_addr) & 63: raise ValueError("Intel kernel arguments must be 64-byte aligned")
    payload_span = round_up(max(prg.metadata.cross_thread_data_size, 1), 64)
    if buf.size < payload_span * 2: raise ValueError("Intel kernel argument allocation has no indirect payload space")
    self.indirect_buf = buf.offset(payload_span, payload_span)
    buf.cpu_view().view(fmt='B')[:] = bytes(buf.size)
    buf_index, val_index = 0, 0
    for arg in prg.metadata.payload_arguments:
      if arg.size == 0: continue  # stateful descriptor record; the paired stateless/bindless record carries the payload
      if arg.arg_type == "arg_bypointer":
        if buf_index >= len(bufs) or arg.size != 8: raise ValueError(f"unsupported Intel pointer argument {arg.arg_index}")
        self.bind_sints_to_buf(bufs[buf_index].va_addr, buf=buf, fmt='Q', offset=arg.offset)
        buf_index += 1
      elif arg.arg_type == "arg_byvalue":
        if val_index >= len(vals) or vals[val_index] is None or arg.size not in (1, 2, 4, 8):
          raise ValueError(f"unsupported Intel by-value argument {arg.arg_index}")
        self.bind_sints_to_buf(vals[val_index], buf=buf, fmt={1:'B', 2:'H', 4:'I', 8:'Q'}[arg.size], offset=arg.offset)
        val_index += 1
    if buf_index != len(bufs) or val_index != len(vals): raise ValueError("Intel argument count does not match .ze_info metadata")

class IntelProgram(HCQProgram['IntelDevice']):
  def __init__(self, dev:IntelDevice, name:str, lib:bytes, *aux, **kwargs):
    self.image = load_zebin(lib, name) if lib.startswith(b'\x7fELF') else IntelProgramImage.decode(lib)
    if self.image.metadata.name != name: raise ValueError(f"Intel program container holds {self.image.metadata.name!r}, not {name!r}")
    self.metadata = self.image.metadata
    self.code = dev.allocator.alloc(round_up(len(self.image.code), 0x1000), BufferSpec(nolru=True))
    dev.allocator._copyin(self.code, memoryview(self.image.code))
    self.instruction_base, self.kernel_start = int(self.code.va_addr), self.metadata.actual_kernel_start_offset
    kernargs_size = round_up(max(self.metadata.cross_thread_data_size, self.metadata.inline_data_payload_size, 1), 64) * 2
    super().__init__(IntelArgsState, dev, name, kernargs_alloc_size=kernargs_size, lib=lib, base=self.instruction_base)
    weakref.finalize(self, self._fini, dev, self.code, BufferSpec(nolru=True))

  def fill_kernargs(self, bufs:tuple[HCQBuffer, ...], vals:tuple[int|None, ...]=(), kernargs:HCQBuffer|None=None) -> IntelArgsState:
    argsbuf = kernargs or self.dev.kernargs_buf.offset(
      offset=self.dev.kernargs_offset_allocator.alloc(self.kernargs_alloc_size, 64), size=self.kernargs_alloc_size)
    return IntelArgsState(argsbuf, self, bufs, vals)

class IntelComputeQueue(HWQueue[HCQSignal, 'IntelDevice', IntelProgram, IntelArgsState]):
  def __init__(self):
    super().__init__()
    self.commands, self.waits, self.signals = Xe2CommandBuffer(), [], []

  def memory_barrier(self):
    self.commands.emit(pipe_control(dc_flush=True))
    return self

  def wait(self, signal:HCQSignal, value:sint=0):
    if not isinstance(value, int): raise ValueError("symbolic Intel mock waits are not implemented")
    self.waits.append((signal, value))
    return self

  def signal(self, signal:HCQSignal, value:sint=0):
    if not isinstance(value, int): raise ValueError("symbolic Intel mock signals are not implemented")
    self.commands.emit(pipe_control(address=int(signal.value_addr), immediate_data=value, post_sync=1))
    self.signals.append((signal, value, False))
    return self

  def timestamp(self, signal:HCQSignal):
    self.commands.emit(pipe_control(address=int(signal.timestamp_addr), post_sync=3))
    self.signals.append((signal, 0, True))
    return self

  def exec(self, prg:IntelProgram, args_state:IntelArgsState, global_size:tuple[sint, ...], local_size:tuple[sint, ...]):
    if not all(isinstance(x, int) for x in (*global_size, *local_size)): raise ValueError("symbolic Intel mock dispatch sizes are not implemented")
    if len(global_size) != 3 or len(local_size) != 3: raise ValueError("Intel dispatch sizes must have three dimensions")
    required = prg.metadata.required_work_group_size
    if required != (0, 0, 0) and tuple(local_size) != required:
      raise ValueError(f"Intel kernel requires local size {required}, got {tuple(local_size)}")
    self.bind_args_state(args_state)
    for arg in prg.metadata.payload_arguments:
      if arg.arg_type == "global_id_offset": values = (0, 0, 0)
      elif arg.arg_type in ("local_size", "enqueued_local_size"): values = tuple(local_size)
      elif arg.arg_type == "global_size": values = tuple(g*l for g, l in zip(global_size, local_size))
      elif arg.arg_type == "group_count": values = tuple(global_size)
      elif arg.arg_type == "work_dimensions": values = (3,)
      elif arg.arg_type in ("arg_bypointer", "arg_byvalue") or arg.size == 0: continue
      else: raise ValueError(f"unsupported Intel implicit payload argument {arg.arg_type!r}")
      if arg.size != 4 * len(values): raise ValueError(f"invalid size for Intel {arg.arg_type} payload")
      dst = args_state.buf.cpu_view().view(offset=arg.offset, size=arg.size, fmt='I')
      for i, value in enumerate(values): dst[i] = value

    cross_thread_size = prg.metadata.cross_thread_data_size
    inline_size = min(prg.metadata.inline_data_payload_size, cross_thread_size, 32)
    cross_thread = bytes(args_state.buf.cpu_view().view(size=cross_thread_size, fmt='B'))
    inline_data, indirect_data = cross_thread[:inline_size], cross_thread[inline_size:]
    if indirect_data: args_state.indirect_buf.cpu_view().view(size=len(indirect_data), fmt='B')[:] = indirect_data
    dynamic_base = int(prg.dev.kernargs_buf.va_addr)
    indirect_length = len(indirect_data)
    indirect_start = int(args_state.indirect_buf.va_addr)-dynamic_base if indirect_length else 0
    generate_local_ids = prg.metadata.local_id_channels > 0
    kernel_start = prg.kernel_start + (prg.metadata.offset_to_skip_per_thread_data_load if generate_local_ids else 0)
    self.commands.emit(cfe_state(maximum_threads=512, large_grf_thread_adjust_disable=prg.metadata.large_grf))
    self.commands.emit(state_base_address(dynamic=dynamic_base, instruction=prg.instruction_base,
      dynamic_size_pages=math.ceil(prg.dev.kernargs_buf.size/0x1000), instruction_size_pages=math.ceil(prg.code.size/0x1000)))
    self.commands.emit(compute_walker(kernel_start=kernel_start, group_count=tuple(global_size), local_size=tuple(local_size),
      simd_size=prg.metadata.simd_size, indirect_data_start=indirect_start, indirect_data_length=indirect_length,
      slm_size=prg.metadata.slm_size, barrier_count=prg.metadata.barrier_count, inline_data=inline_data,
      generate_local_ids=generate_local_ids, emit_local=(1 << prg.metadata.local_id_channels)-1 if generate_local_ids else 0))
    return self

  def _submit(self, dev:IntelDevice):
    for signal, value in self.waits:
      if signal.value < value: raise RuntimeError(f"unsatisfied Intel mock wait: {signal.value} < {value}")
    dev.iface.submit(self.commands.end().to_bytes())
    if isinstance(dev.iface, MOCKIface):
      now = time.perf_counter_ns()
      for signal, value, timestamp in self.signals:
        if timestamp: signal.base_buf.cpu_view().view(8, 8, 'Q')[0] = now
        else: signal.value = value

class IntelDevice(HCQCompiled[HCQSignal]):
  ifaces = [XEKMDIface, MOCKIface]

  def _select_iface(self):
    interface = DEV.target("INTEL").interface
    if interface == "MOCK": return MOCKIface(self, self.device_id)
    if interface == "XEKMD": return XEKMDIface(self, self.device_id)
    raise RuntimeError("No interface for INTEL is enabled; use DEV=MOCK+INTEL or explicitly opt in with DEV=XEKMD+INTEL")

  def __init__(self, device:str="INTEL"):
    self.device_id = int(device.split(":")[1]) if ":" in device else 0
    self.va_allocator = IntelVAAllocator(48, 0x1000)
    self.iface = self._select_iface()
    if isinstance(self.iface, XEKMDIface): self.va_allocator = IntelVAAllocator(self.iface.config.va_bits, self.iface.alignment)
    super().__init__(device, IntelAllocator(self), [IntelOpenCLRenderer], functools.partial(IntelProgram, self), HCQSignal,
                     IntelComputeQueue, None, kernargs_size=1 << 16, sigalloc_size=0x1000, arch="xe2")

  def device_props(self):
    return {"device_id": self.iface.device_id if isinstance(self.iface, MOCKIface) else self.iface.config.device_id,
            "architecture": "xe2", "mock": isinstance(self.iface, MOCKIface)}
