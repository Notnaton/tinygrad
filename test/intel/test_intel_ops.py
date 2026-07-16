import unittest
from tinygrad.renderer.cstyle import OpenCLRenderer
from tinygrad.uop import GroupOp, Ops

class TestIntelOpCoverage(unittest.TestCase):
  def test_opencl_and_decomposition_cover_current_alu_ops(self):
    direct = GroupOp.ALU & set(OpenCLRenderer.code_for_op)
    decomposed = GroupOp.ALU - direct
    self.assertEqual(len(GroupOp.ALU), 28)
    self.assertEqual(len(direct), 21)
    self.assertEqual(decomposed, {Ops.MAX, Ops.THREEFRY, Ops.FDIV, Ops.POW, Ops.FLOORDIV, Ops.FLOORMOD, Ops.MULACC})

if __name__ == "__main__": unittest.main()
