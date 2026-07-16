import unittest
from tinygrad.runtime.support.intel_va import IntelVAAllocator

class TestIntelVAAllocator(unittest.TestCase):
  def test_alloc_alignment_tracking_and_free(self):
    va = IntelVAAllocator(48, 0x1000, base=0x1_0000_0123, limit=0x1_0010_0000)
    first = va.alloc(1)
    second = va.alloc(0x1800, 0x10000)
    self.assertEqual(first, 0x1_0000_1000)
    self.assertEqual(second & 0xFFFF, 0)
    self.assertEqual(va.allocations[first], 0x1000)
    self.assertEqual(va.allocations[second], 0x2000)
    self.assertTrue(va.contains(second + 0x100, 0x1000))
    self.assertFalse(va.contains(second + 0x1000, 0x1001))
    self.assertFalse(va.contains(second, 0))
    va.free(first)
    self.assertFalse(va.contains(first))
    with self.assertRaises(ValueError): va.free(first)

  def test_reuses_freed_ranges(self):
    va = IntelVAAllocator(48, 0x1000, base=0x1_0000_0000, limit=0x1_0001_0000)
    first = va.alloc(0x2000)
    va.alloc(0x2000)
    va.free(first)
    self.assertEqual(va.alloc(0x2000), first)

  def test_out_of_memory(self):
    va = IntelVAAllocator(48, 0x1000, base=0x1_0000_0000, limit=0x1_0000_2000)
    va.alloc(0x2000)
    with self.assertRaises(MemoryError): va.alloc(1)

  def test_invalid_parameters(self):
    for bits in (31, 58):
      with self.assertRaises(ValueError): IntelVAAllocator(bits, 0x1000)
    for alignment in (0, 3, 0x1800):
      with self.assertRaises(ValueError): IntelVAAllocator(48, alignment)
    with self.assertRaises(ValueError): IntelVAAllocator(48, 0x1000, limit=1 << 48)
    with self.assertRaises(ValueError): IntelVAAllocator(48, 0x1000, limit=0x1_0000_0001)
    va = IntelVAAllocator(48, 0x1000)
    with self.assertRaises(ValueError): va.alloc(0)
    with self.assertRaises(ValueError): va.alloc(1, 0x1800)

if __name__ == "__main__": unittest.main()
