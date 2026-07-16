import ctypes, pathlib, shutil, struct, subprocess, tempfile, unittest
from tinygrad.runtime.autogen import xe_drm
from tinygrad.runtime.support.intel import (ARC_PRO_B70, ARC_PRO_B70_DEVICE_ID, XeEngine, identify_product, is_battlemage,
                                            make_exec, make_exec_queue, make_query, make_user_fence, make_vm_bind,
                                            parse_query_config, parse_query_engines, parse_query_mem_regions)

class TestXeABI(unittest.TestCase):
  def test_struct_sizes(self):
    expected = {
      "struct_drm_xe_engine_class_instance": 8, "struct_drm_xe_engine": 32, "struct_drm_xe_query_engines": 8,
      "struct_drm_xe_mem_region": 88, "struct_drm_xe_query_mem_regions": 8, "struct_drm_xe_query_config": 8,
      "struct_drm_xe_device_query": 40, "struct_drm_xe_gem_create": 56, "struct_drm_xe_gem_mmap_offset": 40,
      "struct_drm_xe_vm_create": 32, "struct_drm_xe_vm_destroy": 24, "struct_drm_xe_vm_bind_op": 80,
      "struct_drm_xe_vm_bind": 136, "struct_drm_xe_exec_queue_create": 48, "struct_drm_xe_exec_queue_destroy": 24,
      "struct_drm_xe_sync": 48, "struct_drm_xe_exec": 56, "struct_drm_xe_wait_user_fence": 72,
    }
    for name, size in expected.items(): self.assertEqual(ctypes.sizeof(getattr(xe_drm, name)), size, name)

  @unittest.skipUnless(pathlib.Path("/usr/include/drm/xe_drm.h").is_file() and shutil.which("cc"), "Xe UAPI headers and C compiler required")
  def test_layouts_against_installed_c_header(self):
    names = [name for name in dir(xe_drm) if name.startswith("struct_drm_xe_")]
    assertions = "\n".join(f'_Static_assert(sizeof(struct {name.removeprefix("struct_")}) == {getattr(xe_drm, name).SIZE}, "{name}");'
                           for name in names)
    source = f"#include <drm/xe_drm.h>\n{assertions}\nint main(void) {{ return 0; }}\n"
    with tempfile.TemporaryDirectory() as tmp:
      src, out = pathlib.Path(tmp)/"layout.c", pathlib.Path(tmp)/"layout"
      src.write_text(source)
      subprocess.run(["cc", "-std=c11", "-Werror", str(src), "-o", str(out)], check=True, capture_output=True)

  def test_b70_product(self):
    self.assertEqual(identify_product(ARC_PRO_B70_DEVICE_ID), ARC_PRO_B70)
    self.assertTrue(is_battlemage(ARC_PRO_B70_DEVICE_ID))
    with self.assertRaises(ValueError): identify_product(0xFFFF)

  def test_query_parsers(self):
    engines = bytearray(8 + 2*xe_drm.struct_drm_xe_engine.SIZE)
    struct.pack_into("<II", engines, 0, 2, 0)
    struct.pack_into("<HHHH", engines, 8, xe_drm.DRM_XE_ENGINE_CLASS_COMPUTE, 3, 1, 0)
    struct.pack_into("<HHHH", engines, 40, xe_drm.DRM_XE_ENGINE_CLASS_COPY, 0, 1, 0)
    self.assertEqual(parse_query_engines(engines), (XeEngine(4, 3, 1), XeEngine(1, 0, 1)))

    regions = bytearray(8 + xe_drm.struct_drm_xe_mem_region.SIZE)
    struct.pack_into("<IIHHIQQQQ", regions, 0, 1, 0, xe_drm.DRM_XE_MEM_REGION_CLASS_VRAM, 2, 65536,
                     32 << 30, 1 << 30, 32 << 30, 1 << 30)
    parsed_region = parse_query_mem_regions(regions)[0]
    self.assertEqual((parsed_region.instance, parsed_region.min_page_size, parsed_region.total_size), (2, 65536, 32 << 30))

    config = struct.pack("<II5Q", 5, 0, ARC_PRO_B70_DEVICE_ID | (7 << 16), 1, 65536, 48, 2)
    parsed_config = parse_query_config(config)
    self.assertEqual((parsed_config.device_id, parsed_config.revision, parsed_config.va_bits), (ARC_PRO_B70_DEVICE_ID, 7, 48))

  def test_rejects_truncated_query(self):
    with self.assertRaisesRegex(ValueError, "truncated"): parse_query_engines(struct.pack("<II", 1, 0))

  def test_request_builders(self):
    query, buf = make_query(xe_drm.DRM_XE_DEVICE_QUERY_CONFIG, 128)
    self.assertEqual((query.query, query.size, query.data), (xe_drm.DRM_XE_DEVICE_QUERY_CONFIG, 128, ctypes.addressof(buf)))

    bind = make_vm_bind(5, 11, 0x100000, 0x10000, obj_offset=0x20000, pat_index=3)
    self.assertEqual((bind.vm_id, bind.num_binds, bind.bind.obj, bind.bind.obj_offset), (5, 1, 11, 0x20000))

    queue, instances = make_exec_queue(5, (XeEngine(xe_drm.DRM_XE_ENGINE_CLASS_COMPUTE, 2, 0),))
    self.assertEqual((queue.width, queue.num_placements, queue.instances), (1, 1, ctypes.addressof(instances)))

    fence = make_user_fence(0x200000)
    execute, syncs = make_exec(7, 0x100000, (fence,))
    self.assertEqual((execute.exec_queue_id, execute.address, execute.num_syncs), (7, 0x100000, 1))
    self.assertEqual(execute.syncs, ctypes.addressof(syncs))
    with self.assertRaisesRegex(ValueError, "qword aligned"): make_user_fence(3)

if __name__ == "__main__": unittest.main()
