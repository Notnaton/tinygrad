from __future__ import annotations
import ctypes, struct
from dataclasses import dataclass
from tinygrad.runtime.autogen import xe_drm

INTEL_VENDOR_ID = 0x8086
ARC_PRO_B70_DEVICE_ID = 0xE223
BMG_DEVICE_IDS = frozenset({0xE202, 0xE209, 0xE20B, 0xE20C, 0xE20D, 0xE210, 0xE211,
                            0xE212, 0xE216, 0xE220, 0xE221, 0xE222, ARC_PRO_B70_DEVICE_ID})

@dataclass(frozen=True)
class IntelProduct:
  name: str
  device_id: int
  architecture: str
  compiler_device: str

ARC_PRO_B70 = IntelProduct("Intel Arc Pro B70", ARC_PRO_B70_DEVICE_ID, "Xe2-HPG", "bmg")
INTEL_PRODUCTS = {ARC_PRO_B70.device_id: ARC_PRO_B70}

def identify_product(device_id:int) -> IntelProduct:
  if (product:=INTEL_PRODUCTS.get(device_id)) is None: raise ValueError(f"unsupported Intel PCI device 0x{device_id:04x}")
  return product

def is_battlemage(device_id:int) -> bool: return device_id in BMG_DEVICE_IDS

@dataclass(frozen=True)
class XeEngine:
  engine_class: int
  engine_instance: int
  gt_id: int

@dataclass(frozen=True)
class XeMemoryRegion:
  mem_class: int
  instance: int
  min_page_size: int
  total_size: int
  used: int
  cpu_visible_size: int
  cpu_visible_used: int

@dataclass(frozen=True)
class XeConfig:
  device_id: int
  revision: int
  flags: int
  min_alignment: int
  va_bits: int
  max_exec_queue_priority: int

def _array_count(blob:bytes|bytearray|memoryview, item_size:int, name:str) -> int:
  if len(blob) < 8: raise ValueError(f"truncated Xe {name} query header")
  count, pad = struct.unpack_from("<II", blob)
  if pad: raise ValueError(f"non-zero padding in Xe {name} query")
  if len(blob) < 8 + count * item_size: raise ValueError(f"truncated Xe {name} query: expected {count} entries")
  return count

def parse_query_engines(blob:bytes|bytearray|memoryview) -> tuple[XeEngine, ...]:
  count = _array_count(blob, xe_drm.struct_drm_xe_engine.SIZE, "engines")
  return tuple(XeEngine(*struct.unpack_from("<HHH", blob, 8+i*xe_drm.struct_drm_xe_engine.SIZE)) for i in range(count))

def parse_query_mem_regions(blob:bytes|bytearray|memoryview) -> tuple[XeMemoryRegion, ...]:
  count = _array_count(blob, xe_drm.struct_drm_xe_mem_region.SIZE, "memory regions")
  return tuple(XeMemoryRegion(*struct.unpack_from("<HHIQQQQ", blob, 8+i*xe_drm.struct_drm_xe_mem_region.SIZE)) for i in range(count))

def parse_query_config(blob:bytes|bytearray|memoryview) -> XeConfig:
  count = _array_count(blob, 8, "config")
  if count <= xe_drm.DRM_XE_QUERY_CONFIG_MAX_EXEC_QUEUE_PRIORITY:
    raise ValueError(f"Xe config query has only {count} parameters")
  info = struct.unpack_from(f"<{count}Q", blob, 8)
  rev_and_device = info[xe_drm.DRM_XE_QUERY_CONFIG_REV_AND_DEVICE_ID]
  return XeConfig(rev_and_device & 0xFFFF, (rev_and_device >> 16) & 0xFF, info[xe_drm.DRM_XE_QUERY_CONFIG_FLAGS],
                  info[xe_drm.DRM_XE_QUERY_CONFIG_MIN_ALIGNMENT], info[xe_drm.DRM_XE_QUERY_CONFIG_VA_BITS],
                  info[xe_drm.DRM_XE_QUERY_CONFIG_MAX_EXEC_QUEUE_PRIORITY])

def make_query(query:int, size:int=0) -> tuple[xe_drm.struct_drm_xe_device_query, ctypes.Array|None]:
  if size < 0: raise ValueError("Xe query size cannot be negative")
  if size == 0: return xe_drm.struct_drm_xe_device_query(query=query), None
  data = ctypes.create_string_buffer(size)
  return xe_drm.struct_drm_xe_device_query(query=query, size=size, data=ctypes.addressof(data)), data

def make_vm_bind(vm_id:int, obj:int, addr:int, size:int, *, obj_offset:int=0, pat_index:int=0, flags:int=0) -> xe_drm.struct_drm_xe_vm_bind:
  if size <= 0: raise ValueError("Xe VM bind size must be positive")
  op = xe_drm.struct_drm_xe_vm_bind_op(obj=obj, pat_index=pat_index, obj_offset=obj_offset, range=size, addr=addr,
                                       op=xe_drm.DRM_XE_VM_BIND_OP_MAP, flags=flags)
  return xe_drm.struct_drm_xe_vm_bind(vm_id=vm_id, num_binds=1, bind=op)

def make_vm_unbind(vm_id:int, addr:int, size:int, *, flags:int=0) -> xe_drm.struct_drm_xe_vm_bind:
  if size <= 0: raise ValueError("Xe VM unbind size must be positive")
  op = xe_drm.struct_drm_xe_vm_bind_op(range=size, addr=addr, op=xe_drm.DRM_XE_VM_BIND_OP_UNMAP, flags=flags)
  return xe_drm.struct_drm_xe_vm_bind(vm_id=vm_id, num_binds=1, bind=op)

def make_exec_queue(vm_id:int, engines:tuple[XeEngine, ...]) -> tuple[xe_drm.struct_drm_xe_exec_queue_create, ctypes.Array]:
  if not engines: raise ValueError("Xe exec queue needs at least one engine placement")
  instances = (xe_drm.struct_drm_xe_engine_class_instance * len(engines))(
    *(xe_drm.struct_drm_xe_engine_class_instance(x.engine_class, x.engine_instance, x.gt_id) for x in engines))
  request = xe_drm.struct_drm_xe_exec_queue_create(width=1, num_placements=len(engines), vm_id=vm_id, instances=ctypes.addressof(instances))
  return request, instances

def make_user_fence(addr:int, *, signal:bool=True, timeline_value:int=0) -> xe_drm.struct_drm_xe_sync:
  if addr & 7: raise ValueError("Xe user fence address must be qword aligned")
  return xe_drm.struct_drm_xe_sync(type=xe_drm.DRM_XE_SYNC_TYPE_USER_FENCE,
    flags=xe_drm.DRM_XE_SYNC_FLAG_SIGNAL if signal else 0, addr=addr, timeline_value=timeline_value)

def make_exec(exec_queue_id:int, address:int, syncs:tuple[xe_drm.struct_drm_xe_sync, ...]=()) -> tuple[xe_drm.struct_drm_xe_exec, ctypes.Array|None]:
  sync_array = (xe_drm.struct_drm_xe_sync * len(syncs))(*syncs) if syncs else None
  request = xe_drm.struct_drm_xe_exec(exec_queue_id=exec_queue_id, num_syncs=len(syncs),
    syncs=ctypes.addressof(sync_array) if sync_array is not None else 0, address=address, num_batch_buffer=1)
  return request, sync_array

def make_wait_user_fence(addr:int, value:int, timeout_ns:int, *, exec_queue_id:int=0,
                         op:int=xe_drm.DRM_XE_UFENCE_WAIT_OP_GTE, mask:int=(1 << 64)-1) -> xe_drm.struct_drm_xe_wait_user_fence:
  if addr & 7: raise ValueError("Xe user fence address must be qword aligned")
  return xe_drm.struct_drm_xe_wait_user_fence(addr=addr, op=op, value=value, mask=mask, timeout=timeout_ns, exec_queue_id=exec_queue_id)
