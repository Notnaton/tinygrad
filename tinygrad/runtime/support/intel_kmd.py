from __future__ import annotations
import ctypes, mmap, os, pathlib
from dataclasses import dataclass
from tinygrad.runtime.autogen import xe_drm
from tinygrad.runtime.support.hcq import FileIOInterface
from tinygrad.runtime.support.intel import (INTEL_VENDOR_ID, XeConfig, XeEngine, XeMemoryRegion, make_exec, make_exec_queue, make_query,
                                            make_vm_bind, make_vm_unbind, make_wait_user_fence, parse_query_config, parse_query_engines,
                                            parse_query_mem_regions)

@dataclass(frozen=True)
class XeRenderNode:
  path: str
  sysfs_path: str
  device_id: int
  driver: str

@dataclass(frozen=True)
class XeBufferObject:
  handle: int
  size: int
  placement: int

def discover_xe_render_nodes(sysfs_root:str="/sys/class/drm", dev_root:str="/dev/dri") -> tuple[XeRenderNode, ...]:
  nodes = []
  for entry in sorted(pathlib.Path(sysfs_root).glob("renderD*")):
    device = entry / "device"
    try:
      vendor, device_id = int((device / "vendor").read_text().strip(), 0), int((device / "device").read_text().strip(), 0)
      driver = (device / "driver").resolve(strict=True).name
    except (FileNotFoundError, OSError, ValueError): continue
    node = pathlib.Path(dev_root) / entry.name
    if vendor == INTEL_VENDOR_ID and driver == "xe" and (node.exists() or dev_root != "/dev/dri"):
      nodes.append(XeRenderNode(str(node), str(entry), device_id, driver))
  return tuple(nodes)

class XeKmdDevice:
  """Minimal wrapper around the stable DRM Xe query and submission UAPI."""
  def __init__(self, node:XeRenderNode, io:FileIOInterface|None=None):
    if node.driver != "xe": raise ValueError(f"Intel render node uses {node.driver!r}, not 'xe'")
    self.node, self.io = node, io or FileIOInterface(node.path, os.O_RDWR)

  def query(self, query_id:int) -> bytes:
    request, _ = make_query(query_id)
    self.io.ioctl(xe_drm.DRM_IOCTL_XE_DEVICE_QUERY, request)
    if request.size <= 0: raise RuntimeError(f"Xe query {query_id} returned invalid size {request.size}")
    request, storage = make_query(query_id, request.size)
    allocated = request.size
    self.io.ioctl(xe_drm.DRM_IOCTL_XE_DEVICE_QUERY, request)
    if request.size > allocated: raise RuntimeError(f"Xe query {query_id} grew from {allocated} to {request.size} bytes")
    if storage is None: raise RuntimeError("Xe query allocation failed")
    return storage.raw[:request.size]

  def config(self) -> XeConfig: return parse_query_config(self.query(xe_drm.DRM_XE_DEVICE_QUERY_CONFIG))
  def engines(self) -> tuple[XeEngine, ...]: return parse_query_engines(self.query(xe_drm.DRM_XE_DEVICE_QUERY_ENGINES))
  def memory_regions(self) -> tuple[XeMemoryRegion, ...]: return parse_query_mem_regions(self.query(xe_drm.DRM_XE_DEVICE_QUERY_MEM_REGIONS))

  def create_vm(self, flags:int=0) -> int:
    request = xe_drm.struct_drm_xe_vm_create(flags=flags)
    self.io.ioctl(xe_drm.DRM_IOCTL_XE_VM_CREATE, request)
    if request.vm_id == 0: raise RuntimeError("Xe VM create returned ID zero")
    return request.vm_id

  def destroy_vm(self, vm_id:int):
    self.io.ioctl(xe_drm.DRM_IOCTL_XE_VM_DESTROY, xe_drm.struct_drm_xe_vm_destroy(vm_id=vm_id))

  def create_bo(self, size:int, placement:int, vm_id:int, *, cpu_caching:int=xe_drm.DRM_XE_GEM_CPU_CACHING_WC,
                flags:int=0) -> XeBufferObject:
    if size <= 0: raise ValueError("Xe buffer size must be positive")
    request = xe_drm.struct_drm_xe_gem_create(size=size, placement=placement, flags=flags, vm_id=vm_id, cpu_caching=cpu_caching)
    self.io.ioctl(xe_drm.DRM_IOCTL_XE_GEM_CREATE, request)
    if request.handle == 0: raise RuntimeError("Xe GEM create returned handle zero")
    return XeBufferObject(request.handle, request.size, request.placement)

  def close_bo(self, bo:XeBufferObject|int):
    self.io.ioctl(xe_drm.DRM_IOCTL_GEM_CLOSE, xe_drm.struct_drm_gem_close(handle=bo.handle if isinstance(bo, XeBufferObject) else bo))

  def mmap_offset(self, bo:XeBufferObject|int, flags:int=0) -> int:
    request = xe_drm.struct_drm_xe_gem_mmap_offset(handle=bo.handle if isinstance(bo, XeBufferObject) else bo, flags=flags)
    self.io.ioctl(xe_drm.DRM_IOCTL_XE_GEM_MMAP_OFFSET, request)
    return request.offset

  def mmap_bo(self, bo:XeBufferObject, *, prot:int=mmap.PROT_READ|mmap.PROT_WRITE, flags:int=mmap.MAP_SHARED) -> int:
    return self.io.mmap(0, bo.size, prot, flags, self.mmap_offset(bo))

  def munmap_bo(self, address:int, size:int):
    if (ret:=self.io.munmap(address, size)) != 0: raise OSError(f"failed to unmap Xe buffer at {address:#x}")

  @staticmethod
  def _attach_syncs(request:xe_drm.struct_drm_xe_vm_bind, syncs:tuple[xe_drm.struct_drm_xe_sync, ...]) -> ctypes.Array|None:
    sync_array = (xe_drm.struct_drm_xe_sync * len(syncs))(*syncs) if syncs else None
    request.num_syncs = len(syncs)
    request.syncs = ctypes.addressof(sync_array) if sync_array is not None else 0
    return sync_array

  def bind(self, vm_id:int, bo:XeBufferObject|int, addr:int, size:int, *, obj_offset:int=0, pat_index:int=0, flags:int=0,
           syncs:tuple[xe_drm.struct_drm_xe_sync, ...]=()):
    handle = bo.handle if isinstance(bo, XeBufferObject) else bo
    request = make_vm_bind(vm_id, handle, addr, size, obj_offset=obj_offset, pat_index=pat_index, flags=flags)
    _sync_array = self._attach_syncs(request, syncs)
    self.io.ioctl(xe_drm.DRM_IOCTL_XE_VM_BIND, request)

  def unbind(self, vm_id:int, addr:int, size:int, *, flags:int=0, syncs:tuple[xe_drm.struct_drm_xe_sync, ...]=()):
    request = make_vm_unbind(vm_id, addr, size, flags=flags)
    _sync_array = self._attach_syncs(request, syncs)
    self.io.ioctl(xe_drm.DRM_IOCTL_XE_VM_BIND, request)

  def create_exec_queue(self, vm_id:int, engines:tuple[XeEngine, ...], flags:int=0) -> int:
    request, _instances = make_exec_queue(vm_id, engines)
    request.flags = flags
    self.io.ioctl(xe_drm.DRM_IOCTL_XE_EXEC_QUEUE_CREATE, request)
    if request.exec_queue_id == 0: raise RuntimeError("Xe exec queue create returned ID zero")
    return request.exec_queue_id

  def destroy_exec_queue(self, exec_queue_id:int):
    self.io.ioctl(xe_drm.DRM_IOCTL_XE_EXEC_QUEUE_DESTROY,
                  xe_drm.struct_drm_xe_exec_queue_destroy(exec_queue_id=exec_queue_id))

  def exec(self, exec_queue_id:int, address:int, syncs:tuple[xe_drm.struct_drm_xe_sync, ...]=()):
    request, _sync_array = make_exec(exec_queue_id, address, syncs)
    self.io.ioctl(xe_drm.DRM_IOCTL_XE_EXEC, request)

  def wait_user_fence(self, addr:int, value:int, timeout_ns:int, *, exec_queue_id:int=0,
                      op:int=xe_drm.DRM_XE_UFENCE_WAIT_OP_GTE, mask:int=(1 << 64)-1):
    request = make_wait_user_fence(addr, value, timeout_ns, exec_queue_id=exec_queue_id, op=op, mask=mask)
    self.io.ioctl(xe_drm.DRM_IOCTL_XE_WAIT_USER_FENCE, request)
