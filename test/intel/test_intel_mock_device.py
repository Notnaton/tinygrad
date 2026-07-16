import struct, unittest
from tinygrad.device import BufferSpec
from tinygrad.helpers import Context
from tinygrad.runtime.ops_intel import IntelComputeQueue, IntelDevice
from tinygrad.runtime.support.intel_program import IntelKernelArg, IntelKernelMetadata, IntelProgramImage

class TestIntelMockDevice(unittest.TestCase):
  def test_program_arguments_and_submission(self):
    with Context(DEV="MOCK+INTEL"):
      dev = IntelDevice("INTEL")
      metadata = IntelKernelMetadata(name="add", simd_size=16, grf_count=128,
        payload_arguments=(IntelKernelArg("arg_bypointer", 0, 8, 0), IntelKernelArg("arg_byvalue", 8, 4, 1)))
      program = dev.runtime("add", IntelProgramImage(metadata, bytes(64)).encode())
      data = dev.allocator.alloc(0x1000, BufferSpec())
      args = program.fill_kernargs((data,), (0x12345678,))
      queue = IntelComputeQueue().wait(dev.timeline_signal, 0).memory_barrier().exec(program, args, (2, 3, 1), (8, 1, 1))
      queue.signal(dev.timeline_signal, 1).submit(dev)

      self.assertEqual(struct.unpack_from("<Q", bytes(args.buf.cpu_view()[:]), 0)[0], data.va_addr)
      self.assertEqual(struct.unpack_from("<I", bytes(args.buf.cpu_view()[:]), 8)[0], 0x12345678)
      self.assertEqual(dev.timeline_signal.value, 1)
      self.assertEqual(len(dev.iface.submissions), 1)
      dwords = struct.unpack(f"<{len(dev.iface.submissions[0])//4}I", dev.iface.submissions[0])
      self.assertIn(0x72000004, dwords)
      self.assertIn(0x61010014, dwords)
      self.assertIn(0x72080026, dwords)
      self.assertEqual(dwords[-2:], (0x05000000, 0))

  def test_mock_interface_is_opt_in(self):
    with Context(DEV="INTEL"):
      with self.assertRaisesRegex(RuntimeError, "No interface"): IntelDevice("INTEL")

if __name__ == "__main__": unittest.main()
