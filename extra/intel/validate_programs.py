#!/usr/bin/env python3
"""Compile representative structural tinygrad kernels to BMG Zebin."""
from __future__ import annotations
import argparse, collections, hashlib, json, pathlib, sys
from dataclasses import replace

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from extra.intel.validate_ops import describe_program  # noqa: E402
from tinygrad import Tensor, dtypes  # noqa: E402
from tinygrad.codegen import to_program  # noqa: E402
from tinygrad.codegen.opt import Opt, OptOps  # noqa: E402
from tinygrad.device import BufferSpec  # noqa: E402
from tinygrad.dtype import AddrSpace  # noqa: E402
from tinygrad.helpers import Context, Target  # noqa: E402
from tinygrad.renderer.intel import IntelOpenCLRenderer  # noqa: E402
from tinygrad.runtime.ops_intel import IntelComputeQueue, IntelDevice  # noqa: E402
from tinygrad.runtime.support.compiler_intel import IntelOclocCompiler  # noqa: E402
from tinygrad.uop import Ops  # noqa: E402

def _ast(tensor:Tensor): return tensor.schedule_linear().src[-1].src[0]

def make_structural_cases() -> dict:
  cases = {
    "cast_bitcast": _ast(Tensor.empty(128, dtype=dtypes.float).cast(dtypes.int).bitcast(dtypes.uint)+1),
    "reduction_loop": _ast(Tensor.empty(256, dtype=dtypes.float).sum()),
    "conditional_load": _ast(Tensor.empty(32, dtype=dtypes.float).pad(((3, 5),))*2),
  }
  x, y = Tensor.empty(1, 128), Tensor.empty(128, 128)
  local = _ast((x@y).relu())
  opts = (Opt(OptOps.GROUP, 0, 8), Opt(OptOps.LOCAL, 0, 4), Opt(OptOps.UPCAST, 0, 4))
  cases["local_barrier"] = local.replace(arg=replace(local.arg, opts_to_apply=opts))
  return cases

def compile_structural(compiler:IntelOclocCompiler) -> dict:
  renderer = IntelOpenCLRenderer(Target(device="INTEL", arch="xe2"), compiler)
  with Context(DEV="MOCK+INTEL"): device = IntelDevice("INTEL:255")
  kernels = []
  for case, sink in make_structural_cases().items():
    program = to_program(sink, renderer)
    uops = tuple(program.src[1].src)
    counts = collections.Counter(uop.op.name for uop in uops)
    local_buffers = sum(uop.op is Ops.BUFFER and uop.addrspace is AddrSpace.LOCAL for uop in uops)
    gated_loads = sum(uop.op is Ops.LOAD and len(uop.src) == 3 for uop in uops)
    if case == "cast_bitcast" and not (counts["CAST"] and counts["BITCAST"]): raise RuntimeError("cast case lost its casts")
    if case == "reduction_loop" and not all(counts[op] for op in ("RANGE", "IF", "ENDIF", "BARRIER")):
      raise RuntimeError("reduction case lost loop/barrier control flow")
    if case == "conditional_load" and not gated_loads: raise RuntimeError("conditional case lost its gated loads")
    if case == "local_barrier" and not (local_buffers and counts["BARRIER"]): raise RuntimeError("local case lost shared memory/barrier")
    runtime = device.runtime(program.arg.function_name, program.src[3].arg, *program.arg.aux)
    buffers = tuple(device.allocator.alloc(0x1000, BufferSpec()) for _ in program.arg.globals)
    args_state = runtime.fill_kernargs(buffers, ())
    IntelComputeQueue().exec(runtime, args_state, tuple(program.arg.global_size), tuple(program.arg.local_size)).submit(device)
    batch = device.iface.submissions[-1]
    kernels.append({"case":case, "global_size":program.arg.global_size, "local_size":program.arg.local_size,
                    "uop_counts":dict(sorted(counts.items())), "local_buffers":local_buffers, "gated_loads":gated_loads,
                    "mock_batch_size":len(batch), "mock_batch_sha256":hashlib.sha256(batch).hexdigest(),
                    **describe_program(program)})
  return {"schema":1, "device":compiler.device, "ocloc_version":compiler.version, "kernels":kernels}

def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--ocloc", help="exact ocloc executable; defaults to INTEL_OCLOC/versioned auto-detection")
  parser.add_argument("--manifest", type=pathlib.Path)
  args = parser.parse_args()
  rendered = json.dumps(compile_structural(IntelOclocCompiler(ocloc=args.ocloc)), indent=2, sort_keys=True) + "\n"
  if args.manifest: args.manifest.write_text(rendered)
  else: sys.stdout.write(rendered)
  return 0

if __name__ == "__main__": raise SystemExit(main())
