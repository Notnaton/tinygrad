from tinygrad.renderer.cstyle import OpenCLRenderer
from tinygrad.runtime.support.compiler_intel import IntelOclocCompiler

class IntelOpenCLRenderer(OpenCLRenderer):
  """OpenCL C frontend with offline IGC/ocloc Zebin output for Xe2 BMG."""
  def __init__(self, target):
    super().__init__(target)
    self.compiler = IntelOclocCompiler("bmg")
