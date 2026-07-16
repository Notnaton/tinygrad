import json, pathlib, tempfile, unittest
from extra.intel.compare_kernels import describe_zebin, differences
from test.intel.test_intel_program import ZE_INFO, make_zebin

class TestKernelCompare(unittest.TestCase):
  def test_actual_bmg_golden(self):
    directory = pathlib.Path(__file__).parent / "goldens/ocloc-26.18.38308.1"
    manifest = json.loads((directory / "manifest.json").read_text())
    self.assertEqual((manifest["device"], manifest["ocloc_version"]), ("bmg", "26.18.38308.1"))
    for expected in manifest["binaries"]:
      result = json.loads(json.dumps(describe_zebin(directory / expected["file"].replace(".bin", ".zebin.b64"))))
      result["file"] = expected["file"]
      self.assertEqual(result, expected)

  def test_describe_zebin(self):
    with tempfile.TemporaryDirectory() as directory:
      path = pathlib.Path(directory) / "add.bin"
      path.write_bytes(make_zebin(ZE_INFO.encode(), bytes(range(128))))
      result = describe_zebin(path)
    self.assertEqual(result["file"], "add.bin")
    self.assertEqual(result["kernels"][0]["name"], "add")
    self.assertEqual(result["kernels"][0]["code_size"], 128)
    self.assertEqual(result["kernels"][0]["metadata"]["grf_count"], 256)

  def test_manifest_differences(self):
    self.assertEqual(differences({"code_size":64}, {"code_size":64}), [])
    self.assertEqual(differences({"code_size":64}, {"code_size":128}), ["/code_size: 64 != 128"])
    self.assertEqual(differences({"a":1}, {"b":1}), ["/a: missing from actual", "/b: unexpected in actual"])

if __name__ == "__main__": unittest.main()
