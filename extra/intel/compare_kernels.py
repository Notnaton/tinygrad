#!/usr/bin/env python3
"""Compile BMG golden kernels with Intel ocloc and inspect/compare their Zebin output."""
from __future__ import annotations
import argparse, base64, hashlib, json, pathlib, subprocess, sys
from dataclasses import asdict
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tinygrad.runtime.support.elf import elf_sections  # noqa: E402
from tinygrad.runtime.support.compiler_intel import PINNED_INTEL_OCLOC_VERSION, find_intel_ocloc  # noqa: E402
from tinygrad.runtime.support.intel_program import load_zebin, parse_ze_info  # noqa: E402

DEFAULT_SOURCES = ROOT / "test/intel/kernels"
PINNED_OCLOC_VERSION = PINNED_INTEL_OCLOC_VERSION

def find_ocloc(requested:str) -> str|None: return find_intel_ocloc(requested)

def describe_zebin(path:pathlib.Path) -> dict[str, Any]:
  raw = path.read_bytes()
  blob = base64.b64decode(raw) if path.name.endswith(".b64") else raw
  sections = elf_sections(blob)
  ze_info = next((section.content for section in sections if section.name == ".ze_info"), None)
  if ze_info is None: raise ValueError(f"{path} has no .ze_info section")
  kernels = []
  for metadata in parse_ze_info(ze_info.rstrip(b'\0').decode()):
    image = load_zebin(blob, metadata.name)
    kernels.append({"name":metadata.name, "code_size":len(image.code),
                    "code_sha256":hashlib.sha256(image.code).hexdigest(), "metadata":asdict(metadata)})
  return {"file":path.name, "zebin_size":len(blob), "zebin_sha256":hashlib.sha256(blob).hexdigest(), "kernels":kernels}

def compile_goldens(args:argparse.Namespace) -> dict[str, Any]:
  compiler = find_ocloc(args.ocloc)
  if compiler is None:
    raise RuntimeError(f"{args.ocloc!r} was not found. Install Intel compute-runtime's ocloc {PINNED_OCLOC_VERSION} to reproduce the checked-in "
                       "goldens, or pass --ocloc /path/to/ocloc[-VERSION]. See docs/developer/intel_b70.md#installing-the-pinned-compiler")
  output = pathlib.Path(args.output)
  output.mkdir(parents=True, exist_ok=True)
  sources = sorted(pathlib.Path(args.sources).glob("*.cl"))
  if not sources: raise RuntimeError(f"no OpenCL kernels found in {args.sources}")
  commands, binaries = [], []
  for source in sources:
    command = [compiler, "compile", "-file", str(source), "-device", args.device, "-output", source.stem,
               "-out_dir", str(output), "-output_no_suffix", "-exclude_ir", "--format", "zebin",
               "-options", "-cl-std=CL2.0"]
    try: subprocess.run(command, check=True)
    except subprocess.CalledProcessError as error:
      raise RuntimeError(f"ocloc failed while compiling {source.name} for {args.device!r} (exit {error.returncode}). If it reported "
                         f"'Cannot get HW Info', this ocloc is too old for {args.device}; install a newer intel-ocloc/IGC pair") from error
    binary = output / f"{source.stem}.bin"
    if not binary.is_file(): raise RuntimeError(f"ocloc did not create expected output {binary}")
    commands.append(["ocloc", "compile", "-file", str(source.relative_to(ROOT)), "-device", args.device, "-output", source.stem,
                     "-out_dir", "<OUTPUT>", "-output_no_suffix", "-exclude_ir", "--format", "zebin", "-options", "-cl-std=CL2.0"])
    binaries.append(describe_zebin(binary))
  version_result = subprocess.run([compiler, "--version"], capture_output=True, text=True)
  version = version_result.stdout.strip() if version_result.returncode == 0 else "unknown"
  return {"schema":1, "device":args.device, "ocloc_version":version, "commands":commands, "binaries":binaries}

def differences(expected:Any, actual:Any, path:str="") -> list[str]:
  if type(expected) is not type(actual): return [f"{path or '<root>'}: {type(expected).__name__} != {type(actual).__name__}"]
  if isinstance(expected, dict):
    lines = [f"{path}/{key}: missing from actual" for key in expected.keys()-actual.keys()]
    lines += [f"{path}/{key}: unexpected in actual" for key in actual.keys()-expected.keys()]
    for key in expected.keys() & actual.keys(): lines += differences(expected[key], actual[key], f"{path}/{key}")
    return lines
  if isinstance(expected, list):
    if len(expected) != len(actual): return [f"{path}: list length {len(expected)} != {len(actual)}"]
    return [line for index, (left, right) in enumerate(zip(expected, actual)) for line in differences(left, right, f"{path}/{index}")]
  return [] if expected == actual else [f"{path}: {expected!r} != {actual!r}"]

def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  subparsers = parser.add_subparsers(dest="command", required=True)
  compile_parser = subparsers.add_parser("compile", help="compile all .cl sources and write a JSON manifest")
  compile_parser.add_argument("--sources", default=str(DEFAULT_SOURCES))
  compile_parser.add_argument("--output", required=True)
  compile_parser.add_argument("--manifest")
  compile_parser.add_argument("--device", default="bmg")
  compile_parser.add_argument("--ocloc", default="ocloc")
  inspect_parser = subparsers.add_parser("inspect", help="describe one or more Zebin files")
  inspect_parser.add_argument("zebin", nargs="+", type=pathlib.Path)
  inspect_parser.add_argument("--manifest")
  compare_parser = subparsers.add_parser("compare", help="compare two generated JSON manifests")
  compare_parser.add_argument("expected", type=pathlib.Path)
  compare_parser.add_argument("actual", type=pathlib.Path)
  args = parser.parse_args()

  if args.command == "compile": result = compile_goldens(args)
  elif args.command == "inspect": result = {"schema":1, "binaries":[describe_zebin(path) for path in args.zebin]}
  else:
    if not args.expected.is_file(): raise RuntimeError(f"expected manifest does not exist: {args.expected}")
    if not args.actual.is_file(): raise RuntimeError(f"actual manifest does not exist: {args.actual}; the compile step must succeed first")
    diff = differences(json.loads(args.expected.read_text()), json.loads(args.actual.read_text()))
    if diff:
      print("\n".join(diff))
      return 1
    print("kernel manifests match")
    return 0
  rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
  if args.manifest: pathlib.Path(args.manifest).write_text(rendered)
  else: sys.stdout.write(rendered)
  return 0

if __name__ == "__main__":
  try: raise SystemExit(main())
  except RuntimeError as error:
    print(f"error: {error}", file=sys.stderr)
    raise SystemExit(2) from None
