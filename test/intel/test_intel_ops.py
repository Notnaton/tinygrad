import unittest
from extra.intel.validate_ops import make_op_sink
from tinygrad.codegen import to_program
from tinygrad.device import Compiler
from tinygrad.helpers import Target
from tinygrad.renderer.intel import IntelOpenCLRenderer
from tinygrad.uop import GroupOp, Ops

class TestIntelOpCoverage(unittest.TestCase):
  def test_opencl_and_decomposition_cover_current_alu_ops(self):
    direct = GroupOp.ALU & set(IntelOpenCLRenderer.code_for_op)
    decomposed = GroupOp.ALU - direct
    self.assertEqual(len(GroupOp.ALU), 28)
    self.assertEqual(len(direct), 23)
    self.assertEqual(decomposed, {Ops.MAX, Ops.THREEFRY, Ops.POW, Ops.FLOORDIV, Ops.FLOORMOD})

  def test_every_alu_op_reaches_opencl_source(self):
    renderer = IntelOpenCLRenderer(Target(device="INTEL", arch="xe2"), Compiler())
    for op in GroupOp.ALU:
      with self.subTest(op=op):
        program = to_program(make_op_sink(op), renderer)
        self.assertIn("__kernel void", program.src[2].arg)
        self.assertEqual(program.src[3].arg, program.src[2].arg.encode())

if __name__ == "__main__": unittest.main()
