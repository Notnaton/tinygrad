import pathlib, subprocess, unittest
from unittest import mock
from tinygrad.runtime.support import compiler_intel

class TestIntelCompiler(unittest.TestCase):
  def test_ocloc_command_produces_zebin(self):
    calls = []
    def fake_run(command, **kwargs):
      calls.append(command)
      if "--version" in command: return subprocess.CompletedProcess(command, 0, "26.18.38308.1\n", "")
      output = pathlib.Path(command[command.index("-out_dir")+1]) / "kernel.bin"
      output.write_bytes(b"zebin")
      return subprocess.CompletedProcess(command, 0, "", "")

    with mock.patch.object(compiler_intel, "find_intel_ocloc", return_value="/usr/bin/ocloc-26.18.1"), \
         mock.patch.object(compiler_intel.subprocess, "run", side_effect=fake_run):
      compiler = compiler_intel.IntelOclocCompiler()
      self.assertEqual(compiler.compile("__kernel void test() {}"), b"zebin")

    compile_command = calls[1]
    self.assertEqual(compile_command[0], "/usr/bin/ocloc-26.18.1")
    self.assertIn("bmg", compile_command)
    self.assertIn("--format", compile_command)
    self.assertIn("zebin", compile_command)

if __name__ == "__main__": unittest.main()
