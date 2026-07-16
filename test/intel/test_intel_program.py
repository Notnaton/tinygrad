import pathlib, struct, unittest
from tinygrad.runtime.support.intel_program import IntelProgramImage, load_zebin, parse_ze_info

ZE_INFO = """---
version : '1.39'
kernels :
  - name : add
    execution_env :
      barrier_count : 2
      grf_count : 256
      has_dpas : true
      inline_data_payload_size : 32
      simd_size : 16
      slm_size : 4096
    user_attributes :
      reqd_work_group_size : [ 8, 4, 1 ]
    payload_arguments :
      - arg_type : arg_bypointer
        offset : 0
        size : 8
        arg_index : 0
        addrmode : stateless
        addrspace : global
        access_type : readwrite
      - arg_type : arg_byvalue
        offset : 16
        size : 4
        arg_index : 1
    per_thread_payload_arguments :
      - arg_type : local_id
        offset : 0
        size : 192
...
"""

def make_zebin(ze_info:bytes, kernel:bytes) -> bytes:
  names = b"\0.shstrtab\0.ze_info\0.text.add\0"
  pieces, offset = [], 64
  def put(data:bytes, alignment:int=1) -> tuple[int, int]:
    nonlocal offset
    padding = (-offset) % alignment
    pieces.append(b"\0" * padding + data)
    offset += padding + len(data)
    return offset-len(data), len(data)
  names_off, names_size = put(names)
  info_off, info_size = put(ze_info)
  text_off, text_size = put(kernel, 64)
  shoff = (offset + 7) & -8
  pieces.append(b"\0" * (shoff-offset))
  shdr = struct.Struct("<IIQQQQIIQQ")
  sections = [shdr.pack(0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
              shdr.pack(1, 3, 0, 0, names_off, names_size, 0, 0, 1, 0),
              shdr.pack(11, 0xFF000011, 0, 0, info_off, info_size, 0, 0, 1, 0),
              shdr.pack(20, 1, 6, 0, text_off, text_size, 0, 0, 64, 0)]
  ident = b"\x7fELF\x02\x01\x01" + b"\0" * 9
  header = struct.pack("<16sHHIQQQIHHHHHH", ident, 0xFF12, 0, 1, 0, 0, shoff, 0, 64, 0, 0, 64, 4, 1)
  return header + b"".join(pieces) + b"".join(sections)

class TestIntelProgram(unittest.TestCase):
  def test_compute_runtime_metadata_fixture(self):
    fixture = pathlib.Path(__file__).parent / "fixtures/compute_runtime_test.ze_info"
    meta, = parse_ze_info(fixture.read_text())
    self.assertEqual((meta.name, meta.simd_size, meta.grf_count), ("test", 32, 128))
    self.assertEqual((meta.inline_data_payload_size, meta.per_thread_payload_size), (32, 192))
    self.assertEqual(meta.local_id_channels, 3)
    self.assertEqual(meta.cross_thread_data_size, 92)
    stateful, stateless = meta.payload_arguments[2:4]
    self.assertEqual((stateful.size, stateful.addrmode), (0, "stateful"))
    self.assertEqual((stateless.size, stateless.addrmode), (8, "stateless"))

  def test_parse_ze_info(self):
    meta, = parse_ze_info(ZE_INFO)
    self.assertEqual((meta.name, meta.simd_size, meta.grf_count), ("add", 16, 256))
    self.assertEqual((meta.slm_size, meta.barrier_count), (4096, 2))
    self.assertEqual(meta.required_work_group_size, (8, 4, 1))
    self.assertEqual(meta.cross_thread_data_size, 20)
    self.assertEqual(meta.per_thread_payload_size, 192)
    self.assertEqual(meta.local_id_channels, 3)
    self.assertTrue(meta.large_grf)
    self.assertTrue(meta.has_dpas)
    self.assertEqual(meta.payload_arguments[0].addrspace, "global")

  def test_container_roundtrip(self):
    meta, = parse_ze_info(ZE_INFO)
    image = IntelProgramImage(meta, b"\x01\x02\x03\x04")
    self.assertEqual(IntelProgramImage.decode(image.encode()), image)
    for bad in (b"", b"bad container data", image.encode()[:-1], image.encode()+b"x"):
      with self.assertRaises(ValueError): IntelProgramImage.decode(bad)

  def test_load_zebin(self):
    code = bytes(range(128))
    image = load_zebin(make_zebin(ZE_INFO.encode(), code), "add")
    self.assertEqual(image.metadata.name, "add")
    self.assertEqual(image.code, code)
    with self.assertRaisesRegex(ValueError, "no metadata"): load_zebin(make_zebin(ZE_INFO.encode(), code), "missing")

  def test_rejects_missing_or_invalid_metadata(self):
    with self.assertRaisesRegex(ValueError, "no kernels"): parse_ze_info("version: 1.0")
    with self.assertRaisesRegex(ValueError, "grf_count"): parse_ze_info("kernels:\n  - name: bad\n    execution_env:\n      simd_size: 16")
    with self.assertRaisesRegex(ValueError, "SIMD"): parse_ze_info("kernels:\n  - name: bad\n    execution_env:\n      simd_size: 64\n      grf_count: 128")

if __name__ == "__main__": unittest.main()
