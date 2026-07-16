from __future__ import annotations
import math, struct
from dataclasses import dataclass, field

# Encodings verified against compute-runtime 48d4b5a48767eefaf12aa349190cc3e105afe66a,
# shared/source/generated/xe2_hpg_core/hw_cmds_generated_xe2_hpg_core.inl.

def _check(value:int, bits:int, name:str) -> int:
  if value < 0 or value >= 1 << bits: raise ValueError(f"{name} does not fit in {bits} bits: {value:#x}")
  return value

def _aligned(value:int, alignment:int, name:str) -> int:
  if value & (alignment-1): raise ValueError(f"{name} must be {alignment:#x}-byte aligned: {value:#x}")
  return value

def _set64(dwords:list[int], index:int, value:int):
  _check(value, 64, "64-bit value")
  dwords[index:index+2] = [value & 0xFFFFFFFF, value >> 32]

def mi_batch_buffer_end(*, end_context:bool=False, predicate:bool=False) -> tuple[int, ...]:
  return ((0xA << 23) | int(end_context) | (int(predicate) << 15),)

def pipe_control(*, address:int=0, immediate_data:int=0, post_sync:int=0, command_streamer_stall:bool=True,
                 dc_flush:bool=False, tlb_invalidate:bool=False) -> tuple[int, ...]:
  """Encode Xe2 PIPE_CONTROL. post_sync is 0=no write, 1=immediate, 2=depth count, 3=timestamp."""
  _check(post_sync, 2, "PIPE_CONTROL post-sync operation")
  if post_sync: _aligned(address, 4, "PIPE_CONTROL destination")
  dwords = [0x7A000004, (int(dc_flush) << 5) | (post_sync << 14) | (int(tlb_invalidate) << 18) |
            (int(command_streamer_stall) << 20), 0, 0, 0, 0]
  _set64(dwords, 2, address)
  _set64(dwords, 4, immediate_data)
  return tuple(dwords)

def cfe_state(*, scratch_address:int=0, maximum_threads:int=0, large_grf_thread_adjust_disable:bool=False,
              compute_overdispatch_disable:bool=False, single_slice_dispatch:bool=False) -> tuple[int, ...]:
  _aligned(scratch_address, 64, "CFE scratch address")
  if scratch_address > 0xFFFFFC00: raise ValueError(f"CFE scratch address is out of range: {scratch_address:#x}")
  _check(maximum_threads, 16, "CFE maximum thread count")
  dwords = [0x72000004, (scratch_address >> 6) << 10, 0,
            (int(large_grf_thread_adjust_disable) << 10) | (int(compute_overdispatch_disable) << 11) |
            (int(single_slice_dispatch) << 13) | (2 << 14) | (maximum_threads << 16), 0, 0]
  return tuple(dwords)

def _base_address(dwords:list[int], index:int, address:int|None, mocs:int):
  if address is None: return
  _aligned(address, 0x1000, "STATE_BASE_ADDRESS address")
  _check(address, 64, "STATE_BASE_ADDRESS address")
  _check(mocs, 7, "STATE_BASE_ADDRESS MOCS")
  _set64(dwords, index, address | (mocs << 4) | 1)

def _buffer_size(dwords:list[int], index:int, size_pages:int|None):
  if size_pages is None: return
  _check(size_pages, 20, "STATE_BASE_ADDRESS buffer size")
  dwords[index] = 1 | (size_pages << 12)

def state_base_address(*, general:int|None=None, surface:int|None=None, dynamic:int|None=None, instruction:int|None=None,
                       bindless_surface:int|None=None, bindless_sampler:int|None=None, mocs:int=0,
                       general_size_pages:int|None=None, dynamic_size_pages:int|None=None,
                       instruction_size_pages:int|None=None, bindless_surface_size:int=0,
                       bindless_sampler_size_pages:int=0, stateless_mocs:int=0, l1_cache_policy:int=0) -> tuple[int, ...]:
  _check(stateless_mocs, 7, "stateless MOCS")
  _check(l1_cache_policy, 3, "L1 cache policy")
  dwords = [0] * 22
  dwords[0] = 0x61010014
  dwords[3] = (stateless_mocs << 16) | (l1_cache_policy << 23)
  for index, address in ((1, general), (4, surface), (6, dynamic), (10, instruction),
                         (16, bindless_surface), (19, bindless_sampler)):
    _base_address(dwords, index, address, mocs)
  _buffer_size(dwords, 12, general_size_pages)
  _buffer_size(dwords, 13, dynamic_size_pages)
  _buffer_size(dwords, 15, instruction_size_pages)
  _check(bindless_surface_size, 32, "bindless surface size")
  _check(bindless_sampler_size_pages, 20, "bindless sampler size")
  dwords[18], dwords[21] = bindless_surface_size, bindless_sampler_size_pages << 12
  return tuple(dwords)

SLM_SIZE_ENCODING = {0:0, 1<<10:1, 2<<10:2, 4<<10:3, 8<<10:4, 16<<10:5, 32<<10:6, 64<<10:7,
                     24<<10:8, 48<<10:9, 96<<10:10, 128<<10:11, 192<<10:12, 256<<10:13, 384<<10:14}

def encode_slm_size(size:int) -> int:
  if size not in SLM_SIZE_ENCODING: raise ValueError(f"unsupported Xe2 SLM allocation size: {size}")
  return SLM_SIZE_ENCODING[size]

BARRIER_COUNT_ENCODING = {0:0, 1:1, 2:2, 4:3, 8:4, 16:5, 24:6, 32:7}

def encode_barrier_count(count:int) -> int:
  if count not in BARRIER_COUNT_ENCODING: raise ValueError(f"unsupported Xe2 barrier count: {count}")
  return BARRIER_COUNT_ENCODING[count]

def _interface_descriptor(kernel_start:int, threads:int, slm_size:int, barrier_count:int) -> list[int]:
  _aligned(kernel_start, 64, "kernel start pointer")
  _check(kernel_start, 32, "kernel start pointer")
  _check(threads, 10, "threads per thread group")
  dwords = [0] * 8
  dwords[0] = kernel_start
  dwords[5] = threads | (encode_slm_size(slm_size) << 16) | (encode_barrier_count(barrier_count) << 28)
  return dwords

def _post_sync(address:int|None, value:int, mocs:int) -> list[int]:
  if address is None: return [0] * 5
  _aligned(address, 8, "COMPUTE_WALKER post-sync address")
  _check(mocs, 7, "post-sync MOCS")
  dwords = [1 | (mocs << 4), 0, 0, 0, 0]
  _set64(dwords, 1, address)
  _set64(dwords, 3, value)
  return dwords

def compute_walker(*, kernel_start:int, group_count:tuple[int, int, int], local_size:tuple[int, int, int], simd_size:int,
                   indirect_data_start:int=0, indirect_data_length:int=0, slm_size:int=0, barrier_count:int=0,
                   post_sync_address:int|None=None, post_sync_value:int=0, mocs:int=0, inline_data:bytes=b'',
                   generate_local_ids:bool=False, emit_local:int=0) -> tuple[int, ...]:
  if simd_size not in (16, 32): raise ValueError(f"Xe2 SIMD size must be 16 or 32, got {simd_size}")
  if any(x <= 0 for x in (*group_count, *local_size)): raise ValueError("Xe2 group counts and local sizes must be positive")
  for value, name in zip(group_count, ("group X", "group Y", "group Z")): _check(value, 32, name)
  if any(x > 1024 for x in local_size): raise ValueError("Xe2 local dimensions cannot exceed 1024")
  local_threads = math.prod(local_size)
  if local_threads > 1024: raise ValueError("Xe2 thread group cannot exceed 1024 work-items")
  _aligned(indirect_data_start, 64, "indirect data start")
  _check(indirect_data_start, 32, "indirect data start")
  _check(indirect_data_length, 17, "indirect data length")
  if len(inline_data) > 32: raise ValueError("Xe2 COMPUTE_WALKER inline data is limited to 32 bytes")
  if emit_local not in (0, 1, 3, 7): raise ValueError(f"invalid Xe2 local ID emission mask: {emit_local:#x}")
  if emit_local and not generate_local_ids: raise ValueError("local ID emission requires local ID generation")

  simd_encoding = {16:1, 32:2}[simd_size]
  active_lanes = local_threads % simd_size or simd_size
  dwords = [0] * 40
  dwords[0] = 0x72080026
  dwords[2] = indirect_data_length
  dwords[3] = indirect_data_start
  dwords[4] = ((simd_encoding << 17) | (int(bool(inline_data)) << 25) | (emit_local << 26) |
               (int(generate_local_ids) << 29) | (simd_encoding << 30))
  dwords[5] = (1 << active_lanes) - 1
  dwords[6] = (local_size[0]-1) | ((local_size[1]-1) << 10) | ((local_size[2]-1) << 20)
  dwords[7:10] = group_count
  dwords[19:27] = _interface_descriptor(kernel_start, math.ceil(local_threads/simd_size), slm_size, barrier_count)
  dwords[27:32] = _post_sync(post_sync_address, post_sync_value, mocs)
  padded_inline = inline_data.ljust(32, b'\0')
  dwords[32:40] = struct.unpack("<8I", padded_inline)
  return tuple(dwords)

@dataclass
class Xe2CommandBuffer:
  dwords: list[int] = field(default_factory=list)
  ended: bool = False

  def emit(self, packet:tuple[int, ...]) -> Xe2CommandBuffer:
    if self.ended: raise RuntimeError("cannot emit after MI_BATCH_BUFFER_END")
    self.dwords.extend(packet)
    return self

  def end(self, *, qword_align:bool=True) -> Xe2CommandBuffer:
    if self.ended: raise RuntimeError("command buffer already ended")
    self.dwords.extend(mi_batch_buffer_end())
    if qword_align and len(self.dwords) & 1: self.dwords.append(0)  # MI_NOOP
    self.ended = True
    return self

  def to_bytes(self) -> bytes:
    if not self.ended: raise RuntimeError("command buffer must end before serialization")
    return struct.pack(f"<{len(self.dwords)}I", *self.dwords)
