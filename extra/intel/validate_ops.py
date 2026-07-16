#!/usr/bin/env python3
"""Compile one tinygrad kernel for every ALU UOp and summarize the resulting BMG Zebins."""
from __future__ import annotations
import argparse, hashlib, json, pathlib, sys
from dataclasses import asdict

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tinygrad.codegen import to_program  # noqa: E402
from tinygrad.dtype import dtypes  # noqa: E402
from tinygrad.helpers import Target  # noqa: E402
from tinygrad.renderer.intel import IntelOpenCLRenderer  # noqa: E402
from tinygrad.runtime.support.compiler_intel import IntelOclocCompiler  # noqa: E402
from tinygrad.runtime.support.intel_program import load_zebin  # noqa: E402
from tinygrad.uop import GroupOp, Ops  # noqa: E402
from tinygrad.uop.ops import KernelInfo, UOp  # noqa: E402

FLOAT_UNARY = {Ops.EXP2, Ops.LOG2, Ops.SIN, Ops.SQRT, Ops.RECIPROCAL, Ops.NEG, Ops.TRUNC}
INTEGER_BINARY = {Ops.SHL, Ops.SHR, Ops.CDIV, Ops.CMOD, Ops.XOR, Ops.OR, Ops.AND, Ops.FLOORDIV, Ops.FLOORMOD}
COMPARISONS = {Ops.CMPLT, Ops.CMPNE, Ops.CMPEQ}

def make_op_sink(op:Ops) -> UOp:
  if op in FLOAT_UNARY: dtype, arity = dtypes.float, 1
  elif op in INTEGER_BINARY: dtype, arity = dtypes.int, 2
  elif op is Ops.THREEFRY: dtype, arity = dtypes.uint64, 2
  elif op in (Ops.WHERE, Ops.MULACC): dtype, arity = dtypes.float, 3
  else: dtype, arity = dtypes.float, 2

  index = UOp.special(1, "gidx0")
  output = UOp.param(0, dtypes.bool if op in COMPARISONS else dtype, (1,))
  inputs = [UOp.param(i+1, dtype, (1,)).index(index).load() for i in range(max(arity, 2))]
  if op is Ops.WHERE: value = (inputs[0] < inputs[1]).where(inputs[0], inputs[1])
  elif op is Ops.MULACC: value = inputs[0].alu(op, inputs[1], inputs[0])
  else: value = inputs[0].alu(op, *inputs[1:arity])
  return UOp(Ops.SINK, src=(output.index(index).store(value),), arg=KernelInfo(name=f"intel_{op.name.lower()}"))

def compile_ops(compiler:IntelOclocCompiler) -> dict:
  renderer = IntelOpenCLRenderer(Target(device="INTEL", arch="xe2"), compiler)
  kernels = []
  for op in sorted(GroupOp.ALU, key=lambda item:item.value):
    program = to_program(make_op_sink(op), renderer)
    source, zebin = program.src[2].arg, program.src[3].arg
    image = load_zebin(zebin, program.arg.function_name)
    lowered = sorted({uop.op.name for uop in program.src[1].src if uop.op in GroupOp.ALU})
    kernels.append({"requested_op":op.name, "lowered_ops":lowered, "kernel_name":program.arg.function_name,
                    "source_sha256":hashlib.sha256(source.encode()).hexdigest(), "zebin_size":len(zebin),
                    "zebin_sha256":hashlib.sha256(zebin).hexdigest(), "code_size":len(image.code),
                    "code_sha256":hashlib.sha256(image.code).hexdigest(), "metadata":asdict(image.metadata),
                    "relocations":[asdict(reloc) for reloc in image.relocations]})
  return {"schema":1, "device":compiler.device, "ocloc_version":compiler.version, "alu_op_count":len(GroupOp.ALU), "kernels":kernels}

def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--ocloc", help="exact ocloc executable; defaults to INTEL_OCLOC/versioned auto-detection")
  parser.add_argument("--manifest", type=pathlib.Path)
  args = parser.parse_args()
  result = compile_ops(IntelOclocCompiler(ocloc=args.ocloc))
  rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
  if args.manifest: args.manifest.write_text(rendered)
  else: sys.stdout.write(rendered)
  return 0

if __name__ == "__main__": raise SystemExit(main())
