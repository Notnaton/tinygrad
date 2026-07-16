import struct, unittest
from tinygrad.runtime.support.intel_xe2 import (Xe2CommandBuffer, cfe_state, compute_walker, encode_barrier_count, encode_slm_size,
                                                mi_batch_buffer_end, pipe_control, state_base_address)

class TestXe2Packets(unittest.TestCase):
  def test_command_headers_from_fields(self):
    self.assertEqual(cfe_state()[0], 4 | (2 << 24) | (2 << 27) | (3 << 29))
    self.assertEqual(pipe_control()[0], 4 | (2 << 24) | (3 << 27) | (3 << 29))
    self.assertEqual(compute_walker(kernel_start=0, group_count=(1, 1, 1), local_size=(1, 1, 1), simd_size=16)[0],
                     0x26 | (2 << 18) | (2 << 24) | (2 << 27) | (3 << 29))

  def test_batch_buffer_end_golden(self):
    self.assertEqual(mi_batch_buffer_end(), (0x05000000,))
    self.assertEqual(mi_batch_buffer_end(end_context=True, predicate=True), (0x05008001,))

  def test_pipe_control_golden(self):
    self.assertEqual(pipe_control(), (0x7A000004, 0x00100000, 0, 0, 0, 0))
    self.assertEqual(pipe_control(address=0x123456788, immediate_data=0x1122334455667788, post_sync=1, dc_flush=True),
                     (0x7A000004, 0x00104020, 0x23456788, 0x1, 0x55667788, 0x11223344))

  def test_cfe_state_golden(self):
    self.assertEqual(cfe_state(), (0x72000004, 0, 0, 0x00008000, 0, 0))
    self.assertEqual(cfe_state(scratch_address=0x4000, maximum_threads=0x123, large_grf_thread_adjust_disable=True,
                               compute_overdispatch_disable=True, single_slice_dispatch=True),
                     (0x72000004, 0x00040000, 0, 0x0123AC00, 0, 0))

  def test_state_base_address_golden(self):
    packet = state_base_address(general=0x100000, surface=0x200000, dynamic=0x300000, instruction=0x123456000,
                                mocs=3, stateless_mocs=5, l1_cache_policy=2, general_size_pages=1,
                                dynamic_size_pages=2, instruction_size_pages=3)
    expected = [0] * 22
    expected[0] = 0x61010014
    expected[1:3] = [0x00100031, 0]
    expected[3] = 0x01050000
    expected[4:6] = [0x00200031, 0]
    expected[6:8] = [0x00300031, 0]
    expected[10:12] = [0x23456031, 1]
    expected[12:14] = [0x1001, 0x2001]
    expected[15] = 0x3001
    self.assertEqual(packet, tuple(expected))

  def test_compute_walker_golden(self):
    packet = compute_walker(kernel_start=0x1000, group_count=(4, 2, 1), local_size=(16, 1, 1), simd_size=16,
                            indirect_data_start=0x2000, indirect_data_length=96, slm_size=32 << 10, barrier_count=2,
                            post_sync_address=0x123456780, post_sync_value=0x1122334455667788, mocs=3,
                            inline_data=b'\x01\x02\x03\x04', generate_local_ids=True, emit_local=7)
    expected = [0] * 40
    expected[0:10] = [0x72080026, 0, 96, 0x2000, 0x7E020000, 0xFFFF, 0xF, 4, 2, 1]
    expected[19] = 0x1000
    expected[24] = 0x20060001
    expected[27:32] = [0x31, 0x23456780, 1, 0x55667788, 0x11223344]
    expected[32] = 0x04030201
    self.assertEqual(packet, tuple(expected))

  def test_command_buffer_serialization(self):
    cmd = Xe2CommandBuffer().emit(cfe_state()).emit(pipe_control()).end()
    self.assertEqual(len(cmd.dwords) % 2, 0)
    self.assertEqual(cmd.dwords[-2:], [0x05000000, 0])
    self.assertEqual(struct.unpack(f"<{len(cmd.dwords)}I", cmd.to_bytes()), tuple(cmd.dwords))
    with self.assertRaises(RuntimeError): cmd.emit(mi_batch_buffer_end())

  def test_validation(self):
    self.assertEqual(encode_slm_size(32 << 10), 6)
    self.assertEqual(encode_barrier_count(4), 3)
    self.assertEqual(encode_slm_size(3 << 10), 3)
    self.assertEqual(encode_barrier_count(3), 3)
    with self.assertRaises(ValueError): encode_slm_size(385 << 10)
    with self.assertRaises(ValueError): encode_barrier_count(33)
    with self.assertRaisesRegex(ValueError, "aligned"): pipe_control(address=3, post_sync=1)
    with self.assertRaisesRegex(ValueError, "local ID emission"): compute_walker(
      kernel_start=0, group_count=(1, 1, 1), local_size=(1, 1, 1), simd_size=16, emit_local=1)
    with self.assertRaisesRegex(RuntimeError, "must end"): Xe2CommandBuffer().to_bytes()

  def test_simd8_walker(self):
    walker = compute_walker(kernel_start=0, group_count=(1, 1, 1), local_size=(8, 1, 1), simd_size=8)
    self.assertEqual((walker[4] >> 17) & 0x3, 0)
    self.assertEqual(walker[5], 0xff)

if __name__ == "__main__": unittest.main()
