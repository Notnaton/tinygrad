import pathlib, struct, tempfile, unittest
from tinygrad.runtime.autogen import xe_drm
from tinygrad.runtime.support.intel import ARC_PRO_B70_DEVICE_ID
from tinygrad.runtime.support.intel_kmd import XeKmdDevice, XeRenderNode, discover_xe_render_nodes
from test.intel.mock_xe import MockXeKmd

class MockXeFile:
  def __init__(self, mock:MockXeKmd): self.mock = mock
  def ioctl(self, request, arg):
    if request != xe_drm.DRM_IOCTL_XE_DEVICE_QUERY: raise ValueError(f"unexpected ioctl {request:#x}")
    self.mock.device_query(arg)

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

if __name__ == "__main__": unittest.main()
