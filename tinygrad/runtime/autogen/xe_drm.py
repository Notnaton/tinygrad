# Minimal bindings for the stable Intel Xe DRM UAPI submission path, initially
# verified against Linux 37e2f878a7a660a216cc7a60459995fefd150f25.
# Keep layouts in sync with include/uapi/drm/xe_drm.h in the Linux kernel.
from __future__ import annotations
import ctypes
from typing import Literal
from tinygrad.runtime.support.c import _IOW, _IOWR
from tinygrad.runtime.support import c

@c.record
class struct_drm_xe_engine_class_instance(c.Struct):
  SIZE = 8
  engine_class: int
  engine_instance: int
  gt_id: int
  pad: int
struct_drm_xe_engine_class_instance.register_fields([('engine_class', ctypes.c_uint16, 0), ('engine_instance', ctypes.c_uint16, 2),
  ('gt_id', ctypes.c_uint16, 4), ('pad', ctypes.c_uint16, 6)])

@c.record
class struct_drm_xe_engine(c.Struct):
  SIZE = 32
  instance: struct_drm_xe_engine_class_instance
  reserved: c.Array[ctypes.c_uint64, Literal[3]]
struct_drm_xe_engine.register_fields([('instance', struct_drm_xe_engine_class_instance, 0), ('reserved', ctypes.c_uint64 * 3, 8)])

@c.record
class struct_drm_xe_query_engines(c.Struct):
  SIZE = 8
  num_engines: int
  pad: int
struct_drm_xe_query_engines.register_fields([('num_engines', ctypes.c_uint32, 0), ('pad', ctypes.c_uint32, 4)])

@c.record
class struct_drm_xe_mem_region(c.Struct):
  SIZE = 88
  mem_class: int
  instance: int
  min_page_size: int
  total_size: int
  used: int
  cpu_visible_size: int
  cpu_visible_used: int
  reserved: c.Array[ctypes.c_uint64, Literal[6]]
struct_drm_xe_mem_region.register_fields([('mem_class', ctypes.c_uint16, 0), ('instance', ctypes.c_uint16, 2),
  ('min_page_size', ctypes.c_uint32, 4), ('total_size', ctypes.c_uint64, 8), ('used', ctypes.c_uint64, 16),
  ('cpu_visible_size', ctypes.c_uint64, 24), ('cpu_visible_used', ctypes.c_uint64, 32), ('reserved', ctypes.c_uint64 * 6, 40)])

@c.record
class struct_drm_xe_query_mem_regions(c.Struct):
  SIZE = 8
  num_mem_regions: int
  pad: int
struct_drm_xe_query_mem_regions.register_fields([('num_mem_regions', ctypes.c_uint32, 0), ('pad', ctypes.c_uint32, 4)])

@c.record
class struct_drm_xe_query_config(c.Struct):
  SIZE = 8
  num_params: int
  pad: int
struct_drm_xe_query_config.register_fields([('num_params', ctypes.c_uint32, 0), ('pad', ctypes.c_uint32, 4)])

@c.record
class struct_drm_xe_device_query(c.Struct):
  SIZE = 40
  extensions: int
  query: int
  size: int
  data: int
  reserved: c.Array[ctypes.c_uint64, Literal[2]]
struct_drm_xe_device_query.register_fields([('extensions', ctypes.c_uint64, 0), ('query', ctypes.c_uint32, 8),
  ('size', ctypes.c_uint32, 12), ('data', ctypes.c_uint64, 16), ('reserved', ctypes.c_uint64 * 2, 24)])

@c.record
class struct_drm_xe_gem_create(c.Struct):
  SIZE = 56
  extensions: int
  size: int
  placement: int
  flags: int
  vm_id: int
  handle: int
  cpu_caching: int
  pad: c.Array[ctypes.c_uint16, Literal[3]]
  reserved: c.Array[ctypes.c_uint64, Literal[2]]
struct_drm_xe_gem_create.register_fields([('extensions', ctypes.c_uint64, 0), ('size', ctypes.c_uint64, 8),
  ('placement', ctypes.c_uint32, 16), ('flags', ctypes.c_uint32, 20), ('vm_id', ctypes.c_uint32, 24),
  ('handle', ctypes.c_uint32, 28), ('cpu_caching', ctypes.c_uint16, 32), ('pad', ctypes.c_uint16 * 3, 34),
  ('reserved', ctypes.c_uint64 * 2, 40)])

@c.record
class struct_drm_xe_gem_mmap_offset(c.Struct):
  SIZE = 40
  extensions: int
  handle: int
  flags: int
  offset: int
  reserved: c.Array[ctypes.c_uint64, Literal[2]]
struct_drm_xe_gem_mmap_offset.register_fields([('extensions', ctypes.c_uint64, 0), ('handle', ctypes.c_uint32, 8),
  ('flags', ctypes.c_uint32, 12), ('offset', ctypes.c_uint64, 16), ('reserved', ctypes.c_uint64 * 2, 24)])

@c.record
class struct_drm_xe_vm_create(c.Struct):
  SIZE = 32
  extensions: int
  flags: int
  vm_id: int
  reserved: c.Array[ctypes.c_uint64, Literal[2]]
struct_drm_xe_vm_create.register_fields([('extensions', ctypes.c_uint64, 0), ('flags', ctypes.c_uint32, 8),
  ('vm_id', ctypes.c_uint32, 12), ('reserved', ctypes.c_uint64 * 2, 16)])

@c.record
class struct_drm_xe_vm_destroy(c.Struct):
  SIZE = 24
  vm_id: int
  pad: int
  reserved: c.Array[ctypes.c_uint64, Literal[2]]
struct_drm_xe_vm_destroy.register_fields([('vm_id', ctypes.c_uint32, 0), ('pad', ctypes.c_uint32, 4), ('reserved', ctypes.c_uint64 * 2, 8)])

@c.record
class struct_drm_xe_vm_bind_op(c.Struct):
  SIZE = 80
  extensions: int
  obj: int
  pat_index: int
  pad: int
  obj_offset: int
  userptr: int
  range: int
  addr: int
  op: int
  flags: int
  prefetch_mem_region_instance: int
  pad2: int
  reserved: c.Array[ctypes.c_uint64, Literal[3]]
struct_drm_xe_vm_bind_op.register_fields([('extensions', ctypes.c_uint64, 0), ('obj', ctypes.c_uint32, 8),
  ('pat_index', ctypes.c_uint16, 12), ('pad', ctypes.c_uint16, 14), ('obj_offset', ctypes.c_uint64, 16),
  ('userptr', ctypes.c_uint64, 16), ('range', ctypes.c_uint64, 24), ('addr', ctypes.c_uint64, 32),
  ('op', ctypes.c_uint32, 40), ('flags', ctypes.c_uint32, 44), ('prefetch_mem_region_instance', ctypes.c_uint32, 48),
  ('pad2', ctypes.c_uint32, 52), ('reserved', ctypes.c_uint64 * 3, 56)])

@c.record
class struct_drm_xe_vm_bind(c.Struct):
  SIZE = 136
  extensions: int
  vm_id: int
  exec_queue_id: int
  pad: int
  num_binds: int
  bind: struct_drm_xe_vm_bind_op
  vector_of_binds: int
  pad2: int
  num_syncs: int
  syncs: int
  reserved: c.Array[ctypes.c_uint64, Literal[2]]
struct_drm_xe_vm_bind.register_fields([('extensions', ctypes.c_uint64, 0), ('vm_id', ctypes.c_uint32, 8),
  ('exec_queue_id', ctypes.c_uint32, 12), ('pad', ctypes.c_uint32, 16), ('num_binds', ctypes.c_uint32, 20),
  ('bind', struct_drm_xe_vm_bind_op, 24), ('vector_of_binds', ctypes.c_uint64, 24), ('pad2', ctypes.c_uint32, 104),
  ('num_syncs', ctypes.c_uint32, 108), ('syncs', ctypes.c_uint64, 112), ('reserved', ctypes.c_uint64 * 2, 120)])

@c.record
class struct_drm_xe_exec_queue_create(c.Struct):
  SIZE = 48
  extensions: int
  width: int
  num_placements: int
  vm_id: int
  flags: int
  exec_queue_id: int
  instances: int
  reserved: c.Array[ctypes.c_uint64, Literal[2]]
struct_drm_xe_exec_queue_create.register_fields([('extensions', ctypes.c_uint64, 0), ('width', ctypes.c_uint16, 8),
  ('num_placements', ctypes.c_uint16, 10), ('vm_id', ctypes.c_uint32, 12), ('flags', ctypes.c_uint32, 16),
  ('exec_queue_id', ctypes.c_uint32, 20), ('instances', ctypes.c_uint64, 24), ('reserved', ctypes.c_uint64 * 2, 32)])

@c.record
class struct_drm_xe_exec_queue_destroy(c.Struct):
  SIZE = 24
  exec_queue_id: int
  pad: int
  reserved: c.Array[ctypes.c_uint64, Literal[2]]
struct_drm_xe_exec_queue_destroy.register_fields([('exec_queue_id', ctypes.c_uint32, 0), ('pad', ctypes.c_uint32, 4),
  ('reserved', ctypes.c_uint64 * 2, 8)])

@c.record
class struct_drm_xe_sync(c.Struct):
  SIZE = 48
  extensions: int
  type: int
  flags: int
  handle: int
  addr: int
  timeline_value: int
  reserved: c.Array[ctypes.c_uint64, Literal[2]]
struct_drm_xe_sync.register_fields([('extensions', ctypes.c_uint64, 0), ('type', ctypes.c_uint32, 8),
  ('flags', ctypes.c_uint32, 12), ('handle', ctypes.c_uint32, 16), ('addr', ctypes.c_uint64, 16),
  ('timeline_value', ctypes.c_uint64, 24), ('reserved', ctypes.c_uint64 * 2, 32)])

@c.record
class struct_drm_xe_exec(c.Struct):
  SIZE = 56
  extensions: int
  exec_queue_id: int
  num_syncs: int
  syncs: int
  address: int
  num_batch_buffer: int
  pad: c.Array[ctypes.c_uint16, Literal[3]]
  reserved: c.Array[ctypes.c_uint64, Literal[2]]
struct_drm_xe_exec.register_fields([('extensions', ctypes.c_uint64, 0), ('exec_queue_id', ctypes.c_uint32, 8),
  ('num_syncs', ctypes.c_uint32, 12), ('syncs', ctypes.c_uint64, 16), ('address', ctypes.c_uint64, 24),
  ('num_batch_buffer', ctypes.c_uint16, 32), ('pad', ctypes.c_uint16 * 3, 34), ('reserved', ctypes.c_uint64 * 2, 40)])

@c.record
class struct_drm_xe_wait_user_fence(c.Struct):
  SIZE = 72
  extensions: int
  addr: int
  op: int
  flags: int
  pad: int
  value: int
  mask: int
  timeout: int
  exec_queue_id: int
  pad2: int
  reserved: c.Array[ctypes.c_uint64, Literal[2]]
struct_drm_xe_wait_user_fence.register_fields([('extensions', ctypes.c_uint64, 0), ('addr', ctypes.c_uint64, 8),
  ('op', ctypes.c_uint16, 16), ('flags', ctypes.c_uint16, 18), ('pad', ctypes.c_uint32, 20),
  ('value', ctypes.c_uint64, 24), ('mask', ctypes.c_uint64, 32), ('timeout', ctypes.c_int64, 40),
  ('exec_queue_id', ctypes.c_uint32, 48), ('pad2', ctypes.c_uint32, 52), ('reserved', ctypes.c_uint64 * 2, 56)])

DRM_XE_DEVICE_QUERY, DRM_XE_GEM_CREATE, DRM_XE_GEM_MMAP_OFFSET = 0x00, 0x01, 0x02
DRM_XE_VM_CREATE, DRM_XE_VM_DESTROY, DRM_XE_VM_BIND = 0x03, 0x04, 0x05
DRM_XE_EXEC_QUEUE_CREATE, DRM_XE_EXEC_QUEUE_DESTROY, DRM_XE_EXEC = 0x06, 0x07, 0x09
DRM_XE_WAIT_USER_FENCE = 0x0A

DRM_XE_ENGINE_CLASS_RENDER, DRM_XE_ENGINE_CLASS_COPY = 0, 1
DRM_XE_ENGINE_CLASS_VIDEO_DECODE, DRM_XE_ENGINE_CLASS_VIDEO_ENHANCE = 2, 3
DRM_XE_ENGINE_CLASS_COMPUTE, DRM_XE_ENGINE_CLASS_VM_BIND = 4, 5
DRM_XE_MEM_REGION_CLASS_SYSMEM, DRM_XE_MEM_REGION_CLASS_VRAM = 0, 1
DRM_XE_DEVICE_QUERY_ENGINES, DRM_XE_DEVICE_QUERY_MEM_REGIONS, DRM_XE_DEVICE_QUERY_CONFIG = 0, 1, 2
DRM_XE_QUERY_CONFIG_REV_AND_DEVICE_ID, DRM_XE_QUERY_CONFIG_FLAGS = 0, 1
DRM_XE_QUERY_CONFIG_MIN_ALIGNMENT, DRM_XE_QUERY_CONFIG_VA_BITS, DRM_XE_QUERY_CONFIG_MAX_EXEC_QUEUE_PRIORITY = 2, 3, 4
DRM_XE_QUERY_CONFIG_FLAG_HAS_VRAM = 1 << 0
DRM_XE_GEM_CREATE_FLAG_DEFER_BACKING, DRM_XE_GEM_CREATE_FLAG_SCANOUT = 1 << 0, 1 << 1
DRM_XE_GEM_CREATE_FLAG_NEEDS_VISIBLE_VRAM = 1 << 2
DRM_XE_GEM_CPU_CACHING_WB, DRM_XE_GEM_CPU_CACHING_WC = 1, 2
DRM_XE_VM_CREATE_FLAG_SCRATCH_PAGE, DRM_XE_VM_CREATE_FLAG_LR_MODE, DRM_XE_VM_CREATE_FLAG_FAULT_MODE = 1 << 0, 1 << 1, 1 << 2
DRM_XE_VM_BIND_OP_MAP, DRM_XE_VM_BIND_OP_UNMAP, DRM_XE_VM_BIND_OP_MAP_USERPTR = 0, 1, 2
DRM_XE_VM_BIND_OP_UNMAP_ALL, DRM_XE_VM_BIND_OP_PREFETCH = 3, 4
DRM_XE_VM_BIND_FLAG_NULL, DRM_XE_VM_BIND_FLAG_DUMPABLE = 1 << 2, 1 << 3
DRM_XE_SYNC_TYPE_SYNCOBJ, DRM_XE_SYNC_TYPE_TIMELINE_SYNCOBJ, DRM_XE_SYNC_TYPE_USER_FENCE = 0, 1, 2
DRM_XE_SYNC_FLAG_SIGNAL = 1 << 0
DRM_XE_UFENCE_WAIT_OP_EQ, DRM_XE_UFENCE_WAIT_OP_NEQ, DRM_XE_UFENCE_WAIT_OP_GT = 0, 1, 2
DRM_XE_UFENCE_WAIT_OP_GTE, DRM_XE_UFENCE_WAIT_OP_LT, DRM_XE_UFENCE_WAIT_OP_LTE = 3, 4, 5
DRM_XE_UFENCE_WAIT_FLAG_ABSTIME = 1 << 0

DRM_IOCTL_BASE, DRM_COMMAND_BASE = 'd', 0x40
DRM_IOCTL_XE_DEVICE_QUERY = _IOWR(DRM_IOCTL_BASE, DRM_COMMAND_BASE + DRM_XE_DEVICE_QUERY, struct_drm_xe_device_query)
DRM_IOCTL_XE_GEM_CREATE = _IOWR(DRM_IOCTL_BASE, DRM_COMMAND_BASE + DRM_XE_GEM_CREATE, struct_drm_xe_gem_create)
DRM_IOCTL_XE_GEM_MMAP_OFFSET = _IOWR(DRM_IOCTL_BASE, DRM_COMMAND_BASE + DRM_XE_GEM_MMAP_OFFSET, struct_drm_xe_gem_mmap_offset)
DRM_IOCTL_XE_VM_CREATE = _IOWR(DRM_IOCTL_BASE, DRM_COMMAND_BASE + DRM_XE_VM_CREATE, struct_drm_xe_vm_create)
DRM_IOCTL_XE_VM_DESTROY = _IOW(DRM_IOCTL_BASE, DRM_COMMAND_BASE + DRM_XE_VM_DESTROY, struct_drm_xe_vm_destroy)
DRM_IOCTL_XE_VM_BIND = _IOW(DRM_IOCTL_BASE, DRM_COMMAND_BASE + DRM_XE_VM_BIND, struct_drm_xe_vm_bind)
DRM_IOCTL_XE_EXEC_QUEUE_CREATE = _IOWR(DRM_IOCTL_BASE, DRM_COMMAND_BASE + DRM_XE_EXEC_QUEUE_CREATE, struct_drm_xe_exec_queue_create)
DRM_IOCTL_XE_EXEC_QUEUE_DESTROY = _IOW(DRM_IOCTL_BASE, DRM_COMMAND_BASE + DRM_XE_EXEC_QUEUE_DESTROY, struct_drm_xe_exec_queue_destroy)
DRM_IOCTL_XE_EXEC = _IOW(DRM_IOCTL_BASE, DRM_COMMAND_BASE + DRM_XE_EXEC, struct_drm_xe_exec)
DRM_IOCTL_XE_WAIT_USER_FENCE = _IOWR(DRM_IOCTL_BASE, DRM_COMMAND_BASE + DRM_XE_WAIT_USER_FENCE, struct_drm_xe_wait_user_fence)
