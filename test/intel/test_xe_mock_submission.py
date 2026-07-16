import ctypes, struct, unittest
from tinygrad.runtime.autogen import xe_drm
from tinygrad.runtime.support.intel import (ARC_PRO_B70_DEVICE_ID, XeEngine, make_exec, make_exec_queue, make_query,
                                            make_user_fence, make_vm_bind, parse_query_config)
from tinygrad.runtime.support.intel_xe2 import Xe2CommandBuffer, cfe_state, pipe_control
from test.intel.mock_xe import MockXeKmd

class TestXeMockSubmission(unittest.TestCase):
  def test_query_allocate_bind_and_submit(self):
    config = struct.pack("<II5Q", 5, 0, ARC_PRO_B70_DEVICE_ID, xe_drm.DRM_XE_QUERY_CONFIG_FLAG_HAS_VRAM, 0x10000, 48, 2)
    mock = MockXeKmd({xe_drm.DRM_XE_DEVICE_QUERY_CONFIG: config})

    query, _ = make_query(xe_drm.DRM_XE_DEVICE_QUERY_CONFIG)
    mock.device_query(query)
    query, data = make_query(query.query, query.size)
    mock.device_query(query)
    self.assertEqual(parse_query_config(data.raw).device_id, ARC_PRO_B70_DEVICE_ID)

    vm = xe_drm.struct_drm_xe_vm_create()
    mock.vm_create(vm)
    bo = xe_drm.struct_drm_xe_gem_create(size=0x10000, placement=1, vm_id=vm.vm_id, cpu_caching=xe_drm.DRM_XE_GEM_CPU_CACHING_WC)
    mock.gem_create(bo)

    batch = Xe2CommandBuffer().emit(cfe_state(maximum_threads=512)).emit(pipe_control()).end().to_bytes()
    mock.write_bo(bo.handle, batch)
    gpu_address = 0x100000
    mock.vm_bind(make_vm_bind(vm.vm_id, bo.handle, gpu_address, bo.size))

    queue, instances = make_exec_queue(vm.vm_id, (XeEngine(xe_drm.DRM_XE_ENGINE_CLASS_COMPUTE, 0, 0),))
    mock.exec_queue_create(queue, instances)
    fence_storage = ctypes.c_uint64()
    fence = make_user_fence(ctypes.addressof(fence_storage))
    execute, syncs = make_exec(queue.exec_queue_id, gpu_address, (fence,))
    mock.exec(execute, syncs)
    self.assertEqual(mock.submissions, [(queue.exec_queue_id, gpu_address)])

if __name__ == "__main__": unittest.main()
