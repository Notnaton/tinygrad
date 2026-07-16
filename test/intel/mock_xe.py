from __future__ import annotations
import ctypes, struct, time
from tinygrad.runtime.autogen import xe_drm

class MockXeKmd:
  """Small stateful Xe-UAPI model for testing request lifetimes and submission ordering without a GPU."""
  def __init__(self, queries:dict[int, bytes]):
    self.queries, self.next_vm, self.next_handle, self.next_queue = queries, 1, 1, 1
    self.vms:set[int] = set()
    self.bos:dict[int, bytearray] = {}
    self.bindings:dict[tuple[int, int], tuple[int, int, int]] = {}
    self.queues:dict[int, tuple[int, tuple[int, int, int]]] = {}
    self.submissions:list[tuple[int, int]] = []

  def device_query(self, request:xe_drm.struct_drm_xe_device_query):
    data = self.queries[request.query]
    if request.size == 0: request.size = len(data)
    elif request.size < len(data): raise ValueError("Xe query destination is too small")
    elif request.data == 0: raise ValueError("Xe query destination pointer is null")
    else: ctypes.memmove(request.data, data, len(data))

  def vm_create(self, request:xe_drm.struct_drm_xe_vm_create):
    request.vm_id, self.next_vm = self.next_vm, self.next_vm + 1
    self.vms.add(request.vm_id)

  def gem_create(self, request:xe_drm.struct_drm_xe_gem_create):
    if request.vm_id not in self.vms or request.size <= 0: raise ValueError("invalid Xe GEM create")
    request.handle, self.next_handle = self.next_handle, self.next_handle + 1
    self.bos[request.handle] = bytearray(request.size)

  def gem_mmap_offset(self, request:xe_drm.struct_drm_xe_gem_mmap_offset):
    if request.handle not in self.bos: raise ValueError("invalid Xe GEM mmap handle")
    request.offset = request.handle << 20

  def gem_close(self, request:xe_drm.struct_drm_gem_close):
    if request.handle not in self.bos: raise ValueError("invalid Xe GEM close handle")
    if any(handle == request.handle for handle, _, _ in self.bindings.values()): raise ValueError("cannot close a bound Xe GEM")
    del self.bos[request.handle]

  def vm_destroy(self, request:xe_drm.struct_drm_xe_vm_destroy):
    if request.vm_id not in self.vms: raise ValueError("invalid Xe VM destroy")
    if any(vm_id == request.vm_id for vm_id, _ in self.bindings): raise ValueError("cannot destroy a bound Xe VM")
    if any(vm_id == request.vm_id for vm_id, _ in self.queues.values()): raise ValueError("cannot destroy a queued Xe VM")
    self.vms.remove(request.vm_id)

  def write_bo(self, handle:int, data:bytes, offset:int=0): self.bos[handle][offset:offset+len(data)] = data

  def vm_bind(self, request:xe_drm.struct_drm_xe_vm_bind):
    op = request.bind
    if request.vm_id not in self.vms or request.num_binds != 1 or op.range <= 0: raise ValueError("invalid Xe VM bind")
    if op.op == xe_drm.DRM_XE_VM_BIND_OP_MAP:
      if op.obj not in self.bos or op.obj_offset + op.range > len(self.bos[op.obj]): raise ValueError("Xe VM bind exceeds object")
      self.bindings[(request.vm_id, op.addr)] = (op.obj, op.obj_offset, op.range)
    elif op.op == xe_drm.DRM_XE_VM_BIND_OP_UNMAP:
      if (request.vm_id, op.addr) not in self.bindings: raise ValueError("Xe VM unbind address is not bound")
      del self.bindings[(request.vm_id, op.addr)]
    else: raise ValueError(f"unsupported mock Xe VM bind operation {op.op}")
    syncs = (xe_drm.struct_drm_xe_sync * request.num_syncs).from_address(request.syncs) if request.num_syncs else ()
    self._signal_user_fences(syncs)

  def exec_queue_create(self, request:xe_drm.struct_drm_xe_exec_queue_create,
                        instances:ctypes.Array[xe_drm.struct_drm_xe_engine_class_instance]):
    if request.vm_id not in self.vms or request.width != 1 or request.num_placements != len(instances):
      raise ValueError("invalid Xe exec queue")
    engine = instances[0]
    request.exec_queue_id, self.next_queue = self.next_queue, self.next_queue + 1
    self.queues[request.exec_queue_id] = (request.vm_id, (engine.engine_class, engine.engine_instance, engine.gt_id))

  def exec_queue_destroy(self, request:xe_drm.struct_drm_xe_exec_queue_destroy):
    if request.exec_queue_id not in self.queues: raise ValueError("invalid Xe exec queue destroy")
    del self.queues[request.exec_queue_id]

  def exec(self, request:xe_drm.struct_drm_xe_exec, syncs:ctypes.Array|None):
    if request.exec_queue_id not in self.queues or request.num_batch_buffer != 1: raise ValueError("invalid Xe exec request")
    vm_id = self.queues[request.exec_queue_id][0]
    if (binding:=self.bindings.get((vm_id, request.address))) is None: raise ValueError("Xe batch address is not bound")
    handle, offset, _ = binding
    dwords = struct.unpack_from(f"<{(len(self.bos[handle])-offset)//4}I", self.bos[handle], offset)
    if xe_drm.DRM_XE_SYNC_TYPE_USER_FENCE not in (() if syncs is None else tuple(x.type for x in syncs)):
      raise ValueError("mock Xe submissions require a user fence")
    if 0x05000000 not in dwords: raise ValueError("Xe batch has no MI_BATCH_BUFFER_END")
    for i, dword in enumerate(dwords[:-5]):
      if dword != 0x7A000004 or not (post_sync:=(dwords[i+1] >> 14) & 0x3): continue
      address = dwords[i+2] | (dwords[i+3] << 32)
      value = dwords[i+4] | (dwords[i+5] << 32) if post_sync == 1 else time.perf_counter_ns()
      self._write_gpu_qword(vm_id, address, value)
    self._signal_user_fences(syncs or (), vm_id)
    self.submissions.append((request.exec_queue_id, request.address))

  def _signal_user_fences(self, syncs, vm_id:int|None=None):
    for sync in syncs:
      if sync.type == xe_drm.DRM_XE_SYNC_TYPE_USER_FENCE and sync.flags & xe_drm.DRM_XE_SYNC_FLAG_SIGNAL:
        if vm_id is None: ctypes.c_uint64.from_address(sync.addr).value = sync.timeline_value
        else: self._write_gpu_qword(vm_id, sync.addr, sync.timeline_value)

  def _write_gpu_qword(self, vm_id:int, address:int, value:int):
    for (bound_vm, base), (handle, obj_offset, size) in self.bindings.items():
      if bound_vm == vm_id and base <= address and address + 8 <= base + size:
        struct.pack_into("<Q", self.bos[handle], obj_offset + address-base, value)
        return
    raise ValueError(f"Xe GPU address {address:#x} is not bound")

  def wait_user_fence(self, request:xe_drm.struct_drm_xe_wait_user_fence):
    if request.addr == 0 or request.addr & 7: raise ValueError("invalid Xe user fence address")
    current, expected = ctypes.c_uint64.from_address(request.addr).value & request.mask, request.value & request.mask
    comparisons = {xe_drm.DRM_XE_UFENCE_WAIT_OP_EQ: current == expected, xe_drm.DRM_XE_UFENCE_WAIT_OP_NEQ: current != expected,
                   xe_drm.DRM_XE_UFENCE_WAIT_OP_GT: current > expected, xe_drm.DRM_XE_UFENCE_WAIT_OP_GTE: current >= expected,
                   xe_drm.DRM_XE_UFENCE_WAIT_OP_LT: current < expected, xe_drm.DRM_XE_UFENCE_WAIT_OP_LTE: current <= expected}
    if request.op not in comparisons: raise ValueError(f"invalid Xe user fence operation {request.op}")
    if not comparisons[request.op]: raise TimeoutError(f"mock Xe user fence timed out after {request.timeout} ns")
