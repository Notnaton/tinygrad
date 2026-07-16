from tinygrad.renderer.cstyle import OpenCLRenderer
from tinygrad.runtime.support.compiler_intel import IntelOclocCompiler
from tinygrad.uop import Ops

class IntelOpenCLRenderer(OpenCLRenderer):
  """OpenCL C frontend with offline IGC/ocloc Zebin output for Xe2 BMG."""
  code_for_op = {**OpenCLRenderer.code_for_op,
                 Ops.FDIV: lambda a,b,dtype: f"({a}/{b})", Ops.MULACC: lambda a,b,c,dtype: f"(({a}*{b})+{c})"}

  def __init__(self, target, compiler=None):
    super().__init__(target)
    self.compiler = compiler or IntelOclocCompiler("bmg")
