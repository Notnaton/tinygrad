from tinygrad.helpers import round_up

class IntelVAAllocator:
  """Reusable low-canonical Xe GPU virtual-address allocator."""
  def __init__(self, va_bits:int, min_alignment:int, *, base:int=0x1_0000_0000, limit:int|None=None):
    if not 32 <= va_bits <= 57: raise ValueError(f"unsupported Xe VA width: {va_bits}")
    if min_alignment <= 0 or min_alignment & (min_alignment-1): raise ValueError("Xe minimum alignment must be a power of two")
    self.va_bits, self.min_alignment, self.base = va_bits, min_alignment, round_up(base, min_alignment)
    self.limit = limit if limit is not None else 1 << (va_bits-1)
    if self.limit <= self.base or self.limit > 1 << (va_bits-1) or self.limit & (min_alignment-1):
      raise ValueError("invalid Xe low-canonical VA range")
    self._free:list[tuple[int, int]] = [(self.base, self.limit)]
    self.allocations:dict[int, int] = {}

  def alloc(self, size:int, alignment:int|None=None) -> int:
    if size <= 0: raise ValueError("Xe VA allocation size must be positive")
    alignment = max(self.min_alignment, alignment or self.min_alignment)
    if alignment & (alignment-1): raise ValueError("Xe VA alignment must be a power of two")
    size = round_up(size, self.min_alignment)
    for index, (start, end) in enumerate(self._free):
      if (address:=round_up(start, alignment)) + size > end: continue
      replacement = []
      if start < address: replacement.append((start, address))
      if address+size < end: replacement.append((address+size, end))
      self._free[index:index+1] = replacement
      break
    else: raise MemoryError(f"can't allocate {size} bytes of Xe VA space")
    self.allocations[address] = size
    return address

  def free(self, address:int):
    if address not in self.allocations: raise ValueError(f"unknown Xe VA allocation: {address:#x}")
    size = self.allocations[address]
    self._free.append((address, address+size))
    self._free.sort()
    merged:list[tuple[int, int]] = []
    for start, end in self._free:
      if merged and start == merged[-1][1]: merged[-1] = (merged[-1][0], end)
      else: merged.append((start, end))
    self._free = merged
    del self.allocations[address]

  def contains(self, address:int, size:int=1) -> bool:
    if size <= 0: return False
    return any(start <= address and address+size <= start+length for start, length in self.allocations.items())
