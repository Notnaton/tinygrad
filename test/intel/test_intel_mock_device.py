import base64, pathlib, struct, unittest
from tinygrad.device import BufferSpec
from tinygrad.helpers import Context
from tinygrad.runtime.ops_intel import IntelComputeQueue, IntelDevice
from tinygrad.runtime.support.intel_program import IntelKernelArg, IntelKernelMetadata, IntelProgramImage

class TestIntelMockDevice(unittest.TestCase):
  def test_program_arguments_and_submission(self):
    with Context(DEV="MOCK+INTEL"):
      dev = IntelDevice("INTEL:1")
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

  def test_actual_bmg_zebin_payload_and_walker(self):
    golden = pathlib.Path(__file__).parent / "goldens/ocloc-26.18.38308.1/add_f32.zebin.b64"
    with Context(DEV="MOCK+INTEL"):
      dev = IntelDevice("INTEL")
      program = dev.runtime("add_f32", base64.b64decode(golden.read_bytes()))
      bufs = tuple(dev.allocator.alloc(0x1000, BufferSpec()) for _ in range(3))
      args = program.fill_kernargs(bufs, (123,))
      queue = IntelComputeQueue().exec(program, args, (2, 1, 1), (32, 1, 1))

      cross_thread = bytes(args.buf.cpu_view().view(size=program.metadata.cross_thread_data_size, fmt='B'))
      self.assertEqual(struct.unpack_from("<3I", cross_thread, 0), (0, 0, 0))
      self.assertEqual(struct.unpack_from("<3I", cross_thread, 12), (32, 1, 1))
      self.assertEqual(struct.unpack_from("<3Q", cross_thread, 24), tuple(int(buf.va_addr) for buf in bufs))
      self.assertEqual(struct.unpack_from("<I", cross_thread, 48)[0], 123)
      self.assertEqual(bytes(args.indirect_buf.cpu_view().view(size=20, fmt='B')), cross_thread[32:])

      walker = queue.commands.dwords[28:68]
      self.assertEqual((walker[2], walker[3]), (20, int(args.indirect_buf.va_addr)-int(dev.kernargs_buf.va_addr)))
      self.assertEqual(walker[19], 128)  # skip IGC's per-thread local-ID load prologue
      self.assertEqual((walker[4] >> 29) & 1, 1)
      self.assertEqual((walker[4] >> 26) & 0x7, 1)
      self.assertEqual(struct.pack("<8I", *walker[32:40]), cross_thread[:32])
      self.assertEqual(tuple((reloc.offset, reloc.rel_type) for reloc in program.image.relocations), ((76, 2), (156, 2)))
      self.assertEqual(tuple(struct.unpack_from("<I", program.image.code, reloc.offset)[0] for reloc in program.image.relocations), (0, 0))

if __name__ == "__main__": unittest.main()
