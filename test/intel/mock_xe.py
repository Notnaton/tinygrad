from __future__ import annotations
import ctypes, struct
from tinygrad.runtime.autogen import xe_drm

class MockXeKmd:
  """Small stateful Xe-UAPI model for testing request lifetimes and submission ordering without a GPU."""
  def __init__(self, queries:dict[int, bytes]):
    self.queries, self.next_vm, self.next_handle, self.next_queue = queries, 1, 1, 1
    self.vms:set[int] = set()
    self.bos:dict[int, bytearray] = {}
    self.bindings:dict[tuple[int, int], tuple[int, int]] = {}
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

  def write_bo(self, handle:int, data:bytes, offset:int=0): self.bos[handle][offset:offset+len(data)] = data

  def vm_bind(self, request:xe_drm.struct_drm_xe_vm_bind):
    op = request.bind
    if request.vm_id not in self.vms or request.num_binds != 1 or op.obj not in self.bos: raise ValueError("invalid Xe VM bind")
    if op.range <= 0 or op.obj_offset + op.range > len(self.bos[op.obj]): raise ValueError("Xe VM bind exceeds object")
    self.bindings[(request.vm_id, op.addr)] = (op.obj, op.obj_offset)

  def exec_queue_create(self, request:xe_drm.struct_drm_xe_exec_queue_create,
                        instances:ctypes.Array[xe_drm.struct_drm_xe_engine_class_instance]):
    if request.vm_id not in self.vms or request.width != 1 or request.num_placements != len(instances):
      raise ValueError("invalid Xe exec queue")
    engine = instances[0]
    request.exec_queue_id, self.next_queue = self.next_queue, self.next_queue + 1
    self.queues[request.exec_queue_id] = (request.vm_id, (engine.engine_class, engine.engine_instance, engine.gt_id))

  def exec(self, request:xe_drm.struct_drm_xe_exec, syncs:ctypes.Array|None):
    if request.exec_queue_id not in self.queues or request.num_batch_buffer != 1: raise ValueError("invalid Xe exec request")
    vm_id = self.queues[request.exec_queue_id][0]
    if (binding:=self.bindings.get((vm_id, request.address))) is None: raise ValueError("Xe batch address is not bound")
    handle, offset = binding
    dwords = struct.unpack_from(f"<{(len(self.bos[handle])-offset)//4}I", self.bos[handle], offset)
    if xe_drm.DRM_XE_SYNC_TYPE_USER_FENCE not in (() if syncs is None else tuple(x.type for x in syncs)):
      raise ValueError("mock Xe submissions require a user fence")
    if 0x05000000 not in dwords: raise ValueError("Xe batch has no MI_BATCH_BUFFER_END")
    self.submissions.append((request.exec_queue_id, request.address))
