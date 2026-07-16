from __future__ import annotations
import pathlib, shutil, subprocess, tempfile
from tinygrad.device import Compiler, CompileError
from tinygrad.helpers import getenv

PINNED_INTEL_OCLOC_VERSION = "26.18.38308.1"

def find_intel_ocloc(requested:str|None=None) -> str|None:
  requested = requested or getenv("INTEL_OCLOC", "ocloc")
  if requested != "ocloc": return shutil.which(requested)
  candidates = [*pathlib.Path("/usr/bin").glob("ocloc-*"), *pathlib.Path("/usr/local/bin").glob("ocloc-*"),
                pathlib.Path("/opt/intel/oneapi/compiler/latest/bin/ocloc")]
  if versioned:=next((path for path in sorted(candidates, reverse=True) if path.is_file()), None): return str(versioned)
  return shutil.which("ocloc")

class IntelOclocCompiler(Compiler):
  def __init__(self, device:str="bmg", ocloc:str|None=None):
    self.device = device
    self.ocloc = find_intel_ocloc(ocloc)
    if self.ocloc is None:
      raise RuntimeError(f"Intel ocloc was not found; install version {PINNED_INTEL_OCLOC_VERSION} or set INTEL_OCLOC")
    version = subprocess.run([self.ocloc, "--version"], capture_output=True, text=True)
    self.version = version.stdout.strip() if version.returncode == 0 else "unknown"
    super().__init__(f"intel_ocloc_{self.device}_{self.version}")

  def compile(self, src:str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="tinygrad-intel-") as directory:
      root = pathlib.Path(directory)
      source, output = root / "kernel.cl", root / "kernel.bin"
      source.write_text(src)
      command = [self.ocloc, "compile", "-file", str(source), "-device", self.device, "-output", "kernel",
                 "-out_dir", str(root), "-output_no_suffix", "-exclude_ir", "--format", "zebin",
                 "-options", "-cl-std=CL2.0"]
      result = subprocess.run(command, capture_output=True, text=True)
      if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise CompileError(f"Intel ocloc failed for {self.device} (exit {result.returncode}){': '+detail if detail else ''}")
      if not output.is_file(): raise CompileError(f"Intel ocloc did not produce {output.name}")
      return output.read_bytes()
