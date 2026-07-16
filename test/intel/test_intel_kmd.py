import base64, ctypes, pathlib, struct, tempfile, types, unittest
from unittest import mock as unittest_mock
from tinygrad.device import BufferSpec
from tinygrad.runtime.autogen import xe_drm
from tinygrad.helpers import Context
from tinygrad.runtime.ops_intel import IntelComputeQueue, IntelDevice, XEKMDIface
from tinygrad.runtime.support.intel import ARC_PRO_B70_DEVICE_ID, XeEngine, make_user_fence
from tinygrad.runtime.support.intel_va import IntelVAAllocator
from tinygrad.runtime.support.intel_xe2 import Xe2CommandBuffer
from tinygrad.runtime.support.intel_kmd import XeKmdDevice, XeRenderNode, discover_xe_render_nodes
from test.intel.mock_xe import MockXeKmd

class MockXeFile:
  def __init__(self, mock:MockXeKmd): self.mock, self.mappings = mock, {}
  def ioctl(self, request, arg):
    if request == xe_drm.DRM_IOCTL_XE_DEVICE_QUERY: self.mock.device_query(arg)
    elif request == xe_drm.DRM_IOCTL_XE_VM_CREATE: self.mock.vm_create(arg)
    elif request == xe_drm.DRM_IOCTL_XE_VM_DESTROY: self.mock.vm_destroy(arg)
    elif request == xe_drm.DRM_IOCTL_XE_GEM_CREATE: self.mock.gem_create(arg)
    elif request == xe_drm.DRM_IOCTL_XE_GEM_MMAP_OFFSET: self.mock.gem_mmap_offset(arg)
    elif request == xe_drm.DRM_IOCTL_GEM_CLOSE: self.mock.gem_close(arg)
    elif request == xe_drm.DRM_IOCTL_XE_VM_BIND: self.mock.vm_bind(arg)
    elif request == xe_drm.DRM_IOCTL_XE_EXEC_QUEUE_CREATE:
      instances = (xe_drm.struct_drm_xe_engine_class_instance * arg.num_placements).from_address(arg.instances)
      self.mock.exec_queue_create(arg, instances)
    elif request == xe_drm.DRM_IOCTL_XE_EXEC_QUEUE_DESTROY: self.mock.exec_queue_destroy(arg)
    elif request == xe_drm.DRM_IOCTL_XE_EXEC:
      syncs = (xe_drm.struct_drm_xe_sync * arg.num_syncs).from_address(arg.syncs) if arg.num_syncs else None
      self.mock.exec(arg, syncs)
    elif request == xe_drm.DRM_IOCTL_XE_WAIT_USER_FENCE: self.mock.wait_user_fence(arg)
    else: raise ValueError(f"unexpected ioctl {request:#x}")
  def mmap(self, start, size, prot, flags, offset):
    handle = offset >> 20
    if handle not in self.mock.bos or size > len(self.mock.bos[handle]): raise ValueError("invalid mock Xe mmap")
    mapping = (ctypes.c_ubyte * size).from_buffer(self.mock.bos[handle])
    address = ctypes.addressof(mapping)
    self.mappings[address] = mapping
    return address
  def munmap(self, address, size):
    if address not in self.mappings: return -1
    del self.mappings[address]
    return 0

class TestIntelKmd(unittest.TestCase):
  def test_render_node_discovery(self):
    with tempfile.TemporaryDirectory() as root:
      root = pathlib.Path(root)
      driver = root / "drivers/xe"
      driver.mkdir(parents=True)
      device = root / "drm/renderD128/device"
      device.mkdir(parents=True)
      (device / "vendor").write_text("0x8086\n")
      (device / "device").write_text("0xe223\n")
      (device / "driver").symlink_to(driver)
      nodes = discover_xe_render_nodes(str(root / "drm"), str(root / "dev"))
    self.assertEqual(nodes, (XeRenderNode(str(root / "dev/renderD128"), str(root / "drm/renderD128"), ARC_PRO_B70_DEVICE_ID, "xe"),))

  def test_two_step_queries(self):
    config = struct.pack("<II5Q", 5, 0, ARC_PRO_B70_DEVICE_ID, xe_drm.DRM_XE_QUERY_CONFIG_FLAG_HAS_VRAM, 0x10000, 48, 2)
    engines = struct.pack("<IIHHHH", 1, 0, xe_drm.DRM_XE_ENGINE_CLASS_COMPUTE, 0, 0, 0) + bytes(24)
    memory = struct.pack("<IIHHIQQQQ", 1, 0, xe_drm.DRM_XE_MEM_REGION_CLASS_VRAM, 0, 0x10000, 1<<30, 0, 1<<29, 0) + bytes(48)
    mock = MockXeKmd({xe_drm.DRM_XE_DEVICE_QUERY_CONFIG:config, xe_drm.DRM_XE_DEVICE_QUERY_ENGINES:engines,
                      xe_drm.DRM_XE_DEVICE_QUERY_MEM_REGIONS:memory})
    node = XeRenderNode("/dev/dri/renderD128", "/sys/class/drm/renderD128", ARC_PRO_B70_DEVICE_ID, "xe")
    device = XeKmdDevice(node, MockXeFile(mock))
    self.assertEqual(device.config().device_id, ARC_PRO_B70_DEVICE_ID)
    self.assertEqual(device.engines()[0].engine_class, xe_drm.DRM_XE_ENGINE_CLASS_COMPUTE)
    self.assertEqual(device.memory_regions()[0].mem_class, xe_drm.DRM_XE_MEM_REGION_CLASS_VRAM)

  def test_rejects_non_xe_driver(self):
    node = XeRenderNode("/dev/dri/renderD128", "/sys/class/drm/renderD128", ARC_PRO_B70_DEVICE_ID, "i915")
    with self.assertRaisesRegex(ValueError, "not 'xe'"): XeKmdDevice(node, MockXeFile(MockXeKmd({})))

  def test_allocate_bind_submit_wait_and_cleanup(self):
    mock = MockXeKmd({})
    node = XeRenderNode("/dev/dri/renderD128", "/sys/class/drm/renderD128", ARC_PRO_B70_DEVICE_ID, "xe")
    device = XeKmdDevice(node, MockXeFile(mock))
    vm_id = device.create_vm()
    bo = device.create_bo(0x10000, 1, vm_id)
    self.assertEqual(device.mmap_offset(bo), bo.handle << 20)
    batch = Xe2CommandBuffer().end().to_bytes()
    cpu_address = device.mmap_bo(bo)
    ctypes.memmove(cpu_address, batch, len(batch))
    gpu_address = 0x100000
    bind_fence_storage = ctypes.c_uint64(0)
    bind_fence_address = ctypes.addressof(bind_fence_storage)
    device.bind(vm_id, bo, gpu_address, bo.size, syncs=(make_user_fence(bind_fence_address, timeline_value=1),))
    device.wait_user_fence(bind_fence_address, 1, 1_000_000_000)
    queue_id = device.create_exec_queue(vm_id, (XeEngine(xe_drm.DRM_XE_ENGINE_CLASS_COMPUTE, 0, 0),))
    fence_offset = 0x100
    device.exec(queue_id, gpu_address, (make_user_fence(gpu_address+fence_offset, timeline_value=1),))
    device.wait_user_fence(cpu_address+fence_offset, 1, 1_000_000_000, exec_queue_id=queue_id)
    self.assertEqual(ctypes.c_uint64.from_address(cpu_address+fence_offset).value, 1)
    with self.assertRaises(TimeoutError): device.wait_user_fence(cpu_address+fence_offset, 2, 0, exec_queue_id=queue_id)
    device.destroy_exec_queue(queue_id)
    unbind_fence_storage = ctypes.c_uint64(0)
    unbind_fence_address = ctypes.addressof(unbind_fence_storage)
    device.unbind(vm_id, gpu_address, bo.size, syncs=(make_user_fence(unbind_fence_address, timeline_value=1),))
    device.wait_user_fence(unbind_fence_address, 1, 1_000_000_000)
    device.munmap_bo(cpu_address, bo.size)
    device.close_bo(bo)
    device.destroy_vm(vm_id)
    self.assertEqual((mock.vms, mock.bos, mock.bindings, mock.queues), (set(), {}, {}, {}))

  def test_opt_in_iface_allocates_submits_and_cleans_up(self):
    config = struct.pack("<II5Q", 5, 0, ARC_PRO_B70_DEVICE_ID, xe_drm.DRM_XE_QUERY_CONFIG_FLAG_HAS_VRAM, 0x10000, 48, 2)
    engines = struct.pack("<IIHHHH", 1, 0, xe_drm.DRM_XE_ENGINE_CLASS_COMPUTE, 0, 0, 0) + bytes(24)
    memory = struct.pack("<IIHHIQQQQ", 1, 0, xe_drm.DRM_XE_MEM_REGION_CLASS_SYSMEM, 0, 0x10000, 1<<30, 0, 1<<30, 0) + bytes(48)
    mock = MockXeKmd({xe_drm.DRM_XE_DEVICE_QUERY_CONFIG:config, xe_drm.DRM_XE_DEVICE_QUERY_ENGINES:engines,
                      xe_drm.DRM_XE_DEVICE_QUERY_MEM_REGIONS:memory})
    node = XeRenderNode("/dev/dri/renderD128", "/sys/class/drm/renderD128", ARC_PRO_B70_DEVICE_ID, "xe")
    kmd = XeKmdDevice(node, MockXeFile(mock))
    dev = types.SimpleNamespace(va_allocator=IntelVAAllocator(48, 0x10000))
    iface = XEKMDIface(dev, 0, nodes=(node,), kmd=kmd)
    dev.iface = iface
    buf = iface.alloc(1)
    self.assertEqual((buf.size, int(buf.va_addr) % 0x10000), (0x10000, 0))
    buf.cpu_view().view(size=4, fmt='I')[0] = 0x05000000
    iface.submit(struct.pack("<I", 0x05000000))
    self.assertEqual(len(mock.submissions), 1)
    iface.free(buf)
    iface.device_fini()
    self.assertEqual((mock.vms, mock.bos, mock.bindings, mock.queues), (set(), {}, {}, {}))

  def test_opt_in_device_uses_xe_allocator_and_queue(self):
    config = struct.pack("<II5Q", 5, 0, ARC_PRO_B70_DEVICE_ID, xe_drm.DRM_XE_QUERY_CONFIG_FLAG_HAS_VRAM, 0x10000, 48, 2)
    engines = struct.pack("<IIHHHH", 1, 0, xe_drm.DRM_XE_ENGINE_CLASS_COMPUTE, 0, 0, 0) + bytes(24)
    memory = struct.pack("<IIHHIQQQQ", 1, 0, xe_drm.DRM_XE_MEM_REGION_CLASS_SYSMEM, 0, 0x10000, 1<<30, 0, 1<<30, 0) + bytes(48)
    mock = MockXeKmd({xe_drm.DRM_XE_DEVICE_QUERY_CONFIG:config, xe_drm.DRM_XE_DEVICE_QUERY_ENGINES:engines,
                      xe_drm.DRM_XE_DEVICE_QUERY_MEM_REGIONS:memory})
    node = XeRenderNode("/dev/dri/renderD128", "/sys/class/drm/renderD128", ARC_PRO_B70_DEVICE_ID, "xe")
    kmd = XeKmdDevice(node, MockXeFile(mock))
    with unittest_mock.patch("tinygrad.runtime.ops_intel.discover_xe_render_nodes", return_value=(node,)), \
         unittest_mock.patch("tinygrad.runtime.ops_intel.XeKmdDevice", return_value=kmd), Context(DEV="XEKMD+INTEL"):
      dev = IntelDevice("INTEL")
      golden = pathlib.Path(__file__).parent / "goldens/ocloc-26.18.38308.1/add_f32.zebin.b64"
      program = dev.runtime("add_f32", base64.b64decode(golden.read_bytes()))
      bufs = tuple(dev.allocator.alloc(0x1000, BufferSpec()) for _ in range(3))
      args = program.fill_kernargs(bufs, (32,))
      IntelComputeQueue().exec(program, args, (1, 1, 1), (32, 1, 1)).signal(dev.timeline_signal, 1).submit(dev)
      self.assertEqual(dev.timeline_signal.value, 1)
      self.assertEqual(len(mock.submissions), 1)
      self.assertEqual(dev.device_props(), {"device_id":ARC_PRO_B70_DEVICE_ID, "architecture":"xe2", "mock":False})
      dev.finalize()
    self.assertEqual((mock.vms, mock.bos, mock.bindings, mock.queues), (set(), {}, {}, {}))

if __name__ == "__main__": unittest.main()
