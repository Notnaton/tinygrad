# BMG kernel goldens

These files were generated without GPU hardware using Intel's Ubuntu 24.04
release packages:

- `intel-ocloc` 26.18.38308.1-0
- `intel-igc-core-2` 2.34.4
- `intel-igc-opencl-2` 2.34.4

Each `*.zebin.b64` is the exact base64 encoding of the corresponding Zebin.
The decoded binary and kernel-text SHA-256 values are recorded in
`manifest.json`.  Each `*.asm` is the matching IGA disassembly produced by:

```sh
ocloc disasm -file NAME.bin -dump DUMP_DIRECTORY -device bmg
```

The inputs live in `test/intel/kernels`. Regenerate the binaries and manifest
with `extra/intel/compare_kernels.py compile`. The assembly is reference
material, not tinygrad-generated Xe2 code and not proof of execution on B70.
