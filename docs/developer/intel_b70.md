# Intel Arc Pro B70 bring-up research

Status: research/design plus hardware-independent Xe UAPI, program-loading,
GPU-VA, and mock-HCQ scaffolding; no hardware validation yet.

This note records the sources and implementation plan for a native tinygrad
backend for Intel's Arc Pro B70.  The intended end state is the same layering
used by `AMD` and `NV`: tinygrad owns allocation, command construction,
submission, synchronization, and kernel dispatch.  A Linux `xe`-UAPI interface
is useful for early bring-up, while a PCI/BAR interface can be added behind the
same device abstraction later.

## Confirmed device facts

| Property | Arc Pro B70 |
| --- | --- |
| PCI vendor/device | `8086:e223` |
| GPU family | Battlemage (`BMG`), Xe2-HPG |
| Xe cores / XMX engines | 32 / 256 |
| Memory | 32 GB GDDR6, 256-bit, 608 GB/s |
| PCIe | Gen 5 x16 |
| Addressing in Linux `xe` | 48-bit GPU VA, four-level page tables |

The PCI ID is present in current Linux `INTEL_BMG_IDS`, but not in the
`INTEL_BMG_G21_IDS` subset.  Intel's compute runtime explicitly names `0xe223`
as Arc Pro B70 and assigns it 19,000 MT/s memory on a 256-bit bus.  Code must
therefore identify the product from queries/PCI ID and must not assume B70 is a
larger G21 SKU.

The current `xe` description for Battlemage also reports properties relevant to
a low-level driver: discrete graphics, a 46-bit DMA mask, flat CCS, late bind,
scratch mappings, up to two GTs per tile, four compute command streamers
(`CCS0..CCS3`), render and copy engines, and mandatory hardware workarounds.
The actual topology must still be queried from the card rather than inferred
from the marketing core count.

## What tinygrad's AMD/NVIDIA backends actually contain

`tinygrad/runtime/ops_amd.py` and `ops_nv.py` are not just PCI drivers.  Each
backend supplies five cooperating pieces:

1. a `HCQCompiled` device and renderer/compiler selection;
2. an allocator and a GPU virtual-address policy;
3. compute/copy command packet builders and timeline signals;
4. a program loader that turns compiler output into dispatch metadata; and
5. interchangeable interfaces (kernel UAPI and direct PCI/BAR access).

The direct interfaces delegate hardware boot, MMIO, firmware, page tables, and
engine setup to `AMDev`/`NVDev`.  Intel support should preserve this split:

```text
IntelDevice (HCQCompiled)
  IntelAllocator
  IntelProgram
  IntelCommandQueue / IntelCopyQueue
  XeKmdIface       - /dev/dri/renderD*, DRM Xe UAPI
  PCIIface         - VFIO/sysfs PCI resources, future IntelDev
```

This makes the command builder, allocator contract, program metadata, tests,
and renderer reusable between the kernel-assisted and sovereign paths.

## Recommended first interface: DRM Xe, not Level Zero

The first executable backend should talk directly to `/dev/dri/renderD*` using
`xe_drm.h`.  This uses the upstream kernel only for protected device boot,
memory management, and GuC scheduling; it does not depend on Intel Level Zero,
OpenCL, SYCL, or the Intel compute runtime.

The minimum UAPI sequence is:

1. `DRM_XE_DEVICE_QUERY` for engines, memory regions, config, GT list,
   topology, and firmware version;
2. `DRM_XE_VM_CREATE` for one GPU address space;
3. `DRM_XE_GEM_CREATE`, GEM mmap offset, and `mmap` for buffers;
4. `DRM_XE_VM_BIND` to map GEM objects or aligned user pointers;
5. `DRM_XE_EXEC_QUEUE_CREATE` on a compute engine;
6. `DRM_XE_EXEC` with the GPU address of an Intel batch buffer; and
7. user-fence syncs plus `DRM_XE_WAIT_USER_FENCE` for timeline semantics.

This maps cleanly onto tinygrad's HCQ abstractions.  It also permits meaningful
tests without a card: ctypes layout checks against the C header, serialized
ioctl fixtures, engine/memory query parsing, VA allocation, command packet
goldens, and mock submission.

The current `intel-b70` branch implements the first hardware-independent
checkpoint: the stable submission-related Xe UAPI structures, B70 product
identification, query parsing and request builders, Xe2 encoders for
`STATE_BASE_ADDRESS`, `CFE_STATE`, `COMPUTE_WALKER`, `PIPE_CONTROL`, and
`MI_BATCH_BUFFER_END`, plus a stateful mock that exercises query, VM creation,
GEM creation, VM binding, compute-queue creation, fenced execution, and batch
termination.  The packet goldens are pinned to the compute-runtime revision
listed under Primary sources.

The second checkpoint adds an absolute-address 48-bit low-canonical GPU VA
allocator, a strict parser for the IGC Zebin `.ze_info` subset, `.text.<kernel>`
extraction, and a versioned tinygrad Intel program container.  Its metadata
tracks SIMD width, GRF count/large-GRF mode, SLM, barriers, DPAS use,
cross-thread arguments, per-thread payload size, inline payload size, and the
actual and per-thread-skip kernel start offsets.  It also parses and validates
text relocations instead of passing Intel ELF relocation types to the generic
host linker.  Synthetic ELF fixtures exercise the loader without depending on
IGC at test time.

An opt-in `DEV=MOCK+INTEL` HCQ skeleton now joins these pieces.  It allocates
mock buffers at GPU virtual addresses, lays out pointer and scalar kernel
arguments, uploads kernel code, emits the Xe2 compute-state and walker packets,
captures serialized batches, and models timeline completion.  Genuine BMG
Zebins additionally exercise implicit dimension patching, the 32-byte inline
cross-thread prefix, aligned indirect cross-thread data, and hardware local-ID
generation with the compiler's per-thread-load prologue skipped.  Plain
`INTEL` deliberately fails because no real interface exists yet.  The mock
does not execute EU instructions and is not evidence that the packets run on
silicon.

## Kernel binary and command-stream options

There are three practical compiler stages:

1. **Bring-up:** generate OpenCL C or SPIR-V from tinygrad and use IGC offline
   to obtain Xe2 machine code and metadata.  IGC explicitly supports BMG.
2. **Reduced dependency:** emit documented vISA and invoke the open-source vISA
   backend.  vISA is an intermediate ISA, not the final hardware encoding.
3. **Native tinygrad:** add a Xe2 machine-code renderer/assembler.  This is the
   largest compiler task because send messages, register allocation, SIMD
   control flow, barriers, and XMX all need correct encodings.

Intel's MIT-licensed compute runtime contains generated Xe2 command definitions
for `CFE_STATE`, `STATE_BASE_ADDRESS`, `COMPUTE_WALKER`, `PIPE_CONTROL`, and
`MI_BATCH_BUFFER_START`.  These are sufficient source material for a small
Python packet encoder; the full compute runtime should not be copied into
tinygrad.  `COMPUTE_WALKER` is 160 bytes on Xe2 in the current generated
definition.

The first kernel should be a hand-inspected SIMD kernel doing one global load,
one add, and one global store.  XMX support should come only after scalar/vector
dispatch, barriers, local memory, and copy queues are stable.

### tinygrad operation coverage

At the pinned tinygrad revision `Ops` has 82 members, but this is not the number
of machine operations an Intel renderer needs: it includes tensor graph,
scheduler, container, and HCQ-only IR.  `GroupOp.ALU` currently contains 28
elementwise operations (the older count of 26 predates `FLOORDIV` and
`FLOORMOD`).

The offline OpenCL/IGC path can use tinygrad's standard decomposition rules:

| Lowering class | tinygrad operations |
|---|---|
| Direct OpenCL expression/builtin | `EXP2`, `LOG2`, `SIN`, `SQRT`, `RECIPROCAL`, `NEG`, `TRUNC`, `ADD`, `MUL`, `SHL`, `SHR`, `CDIV`, `CMOD`, `CMPLT`, `CMPNE`, `CMPEQ`, `XOR`, `OR`, `AND`, `SUB`, `FDIV`, `WHERE`, `MULACC` |
| Decomposed before rendering | `MAX`, `THREEFRY`, `POW`, `FLOORDIV`, `FLOORMOD` |

All 28 therefore need semantic tests even though only 23 need a direct OpenCL
spelling.  A future native Xe2 renderer additionally needs the lowered program
IR for parameters/constants, work-item IDs, casts/bitcasts, global and local
index/load/store, ranges and conditionals, barriers, and eventually `WMMA` for
XMX.  The first correctness milestone excludes `WMMA`, exotic image operations,
atomics, and custom inline instructions; each must fail closed until its ABI and
encoding are implemented.

The branch wires this OpenCL lowering to `IntelOclocCompiler`, which invokes
offline IGC for `-device bmg` and returns Zebin directly to `IntelProgram`.
`ocloc-VERSION` executables are preferred over an unversioned distro executable;
`INTEL_OCLOC=/absolute/path/to/ocloc-26.18.1` selects an exact installation.
This makes ordinary tinygrad programs compile and traverse mock submission, but
the mock intentionally does not fabricate output values.

Compile a one-element tinygrad kernel for every current ALU UOp and record the
rendered-source, complete-Zebin, extracted-code, metadata, and relocation hashes
with:

```sh
python extra/intel/validate_ops.py \
  --ocloc /usr/bin/ocloc-26.18.1 \
  --manifest /tmp/intel-bmg-ops.json
```

The pinned toolchain currently compiles all 28 cases.  This corpus is a compiler
and loader check, not a numerical result check; once hardware is available the
same cases should execute against CPU reference values and become the initial
native-Xe2 renderer conformance suite.

Structural kernels can be compiled, loaded, and passed through mock walker
construction with:

```sh
python extra/intel/validate_programs.py \
  --ocloc /usr/bin/ocloc-26.18.1 \
  --manifest /tmp/intel-bmg-programs.json
```

The cases cover casts/bitcasts, a reduction loop with conditional control flow,
gated global loads, and grouped local-memory reduction.  With the pinned
compiler the two reduction cases request respectively 64 and 512 bytes of SLM,
one barrier, and one or two local-ID channels.  The validator records both
Zebin details and the serialized mock batch for each case.

### Golden kernel comparison

The branch includes small OpenCL C add, copy, and naïve matrix-multiply kernels
under `test/intel/kernels/`.  They are inputs to Intel IGC, not claimed native
tinygrad Xe2 output.  With the compute runtime's `ocloc` installed, generate
BMG Zebins and a reproducibility manifest with:

```sh
python extra/intel/compare_kernels.py compile \
  --output /tmp/bmg-goldens --manifest /tmp/bmg-goldens.json
```

The command invokes `ocloc compile -device bmg --format zebin`, then records the
full Zebin hash, extracted `.text.<kernel>` size/hash, and decoded `.ze_info`
metadata for every kernel.  `inspect` produces the same description for an
existing Zebin, while `compare EXPECTED.json ACTUAL.json` reports field-level
differences.  This lets us compare compiler versions, compiler options, BMG
steppings, and eventually a tinygrad Xe2 assembler without pretending that
equal source code implies equal machine code.

The unit suite also parses a metadata fixture copied from Intel compute-runtime
at the pinned revision.  It covers real IGC conventions including paired
zero-sized stateful and eight-byte stateless argument records.

Reference BMG Zebins and IGA disassemblies are checked in under
`test/intel/goldens/ocloc-26.18.38308.1/`.  They were produced without a GPU by
`intel-ocloc` 26.18.38308.1 and IGC 2.34.4 from Intel's Ubuntu packages.  The
add, copy, and naïve matmul kernel texts are respectively 896, 832, and 1,792
bytes.  All three compile as SIMD32 with 128 GRFs and a 32-byte inline payload;
matmul requires 128 bytes of per-thread payload versus 64 bytes for add/copy.
The manifest pins complete-Zebin and extracted-code hashes so later compiler or
tinygrad output can be compared exactly.

These Zebins also contain Intel relocation records such as
`__INTEL_PATCH_CROSS_THREAD_OFFSET_OFF_R0`.  The loader now decodes and
validates those records.  Compute-runtime only patches these sites with the
aligned implicit-argument structure size when a kernel actually requires that
structure; the checked-in ordinary OpenCL kernels do not, so their two 32-bit
immediates correctly remain zero.  Unknown text relocation symbols and types
fail closed.

#### Installing the pinned compiler

`ocloc` is an Intel compute-runtime tool and is not installed with tinygrad.
For Ubuntu 24.04, the exact packages used for the checked-in goldens can be
installed from Intel's GitHub releases:

```sh
mkdir -p /tmp/intel-ocloc && cd /tmp/intel-ocloc
wget https://github.com/intel/intel-graphics-compiler/releases/download/v2.34.4/intel-igc-core-2_2.34.4+21428_amd64.deb
wget https://github.com/intel/intel-graphics-compiler/releases/download/v2.34.4/intel-igc-opencl-2_2.34.4+21428_amd64.deb
wget https://github.com/intel/compute-runtime/releases/download/26.18.38308.1/intel-ocloc_26.18.38308.1-0_amd64.deb
sudo apt install ./intel-igc-core-2_2.34.4+21428_amd64.deb \
  ./intel-igc-opencl-2_2.34.4+21428_amd64.deb \
  ./intel-ocloc_26.18.38308.1-0_amd64.deb
ocloc --version
```

Some packages expose only a versioned executable such as `ocloc-26.18.1`.
The comparison script discovers those under `/usr/bin` and `/usr/local/bin`, or
an explicit path can be supplied with `--ocloc`.  Other distributions should
use equivalent packages or a locally built compute-runtime/IGC pair; comparing
their manifest with the pinned one will show any output differences.

## Details from `llm-scaler` and `compute-runtime`

Intel's `llm-scaler` is useful as a workload and compiler-tuning reference, but
it is not a driver reference.  It confirms that Intel's validated B70 stack
still exposes `/dev/dri/card*` and `/dev/dri/renderD*` to containers and added
B70 support in its May 2026 platform image.  Its useful transferable details
are:

- Battlemage AOT kernels are compiled for `spir64_gen` with the IGC backend
  option `-device bmg` and per-kernel device-code splitting.
- Register-heavy ESIMD kernels are split into a separate translation unit and
  use the large-GRF mode: 256 registers per thread instead of the default 128.
  Less demanding kernels retain small-GRF mode for better occupancy.  The
  tinygrad program container therefore needs an explicit GRF-mode/count field.
- Optimized attention and GEMM paths use DPAS/XMX, not only vector ALUs.  One
  published B580 attention configuration uses a 16-thread workgroup, 32 KiB of
  SLM, 64-row KV tiles, and 128-wide heads.  These are workload tuning clues,
  not B70 hardware constants.
- The multi-GPU stack tests CCL P2P and USM, tensor/pipeline/data parallelism,
  memory bandwidth, collectives, and GEMM.  These form a useful acceptance-test
  list for tinygrad peer mappings and copy queues.

The repository also provides strong platform evidence for the direct-driver
plan.  Its installer fetches exactly `xe/bmg_guc_70.bin` and
`xe/bmg_huc.bin`; its known-issues document reports that an outdated B60 GuC
firmware can hang an OS installation.  It also treats Resizable BAR/BAR2 sizing
as a board-firmware concern and recommends disabling the Intel IOMMU for its
validated multi-GPU P2P setup.  Tinygrad should report these conditions but
must not silently modify bootloader, IOMMU, or firmware configuration.

`compute-runtime` is the lower-level executable reference.  The most useful
parts for tinygrad are:

- `shared/source/os_interface/linux/xe/ioctl_helper_xe.cpp` and its tests for
  translating allocations, VM binds, execution queues, exec requests, and
  syncs to the Xe UAPI;
- `shared/source/generated/xe2_hpg_core/` for exact Xe2 packet layouts;
- `shared/source/xe2_hpg_core/command_stream_receiver_hw_xe2_hpg_core.cpp` for
  the required command-stream prologue and state transitions;
- the BMG product helpers and device table for PCI/product behavior; and
- the mocked DRM Xe implementation and ioctl tests as a model for testing
  without hardware.

The compute runtime's feature named "direct submission" must not be confused
with tinygrad's proposed PCI driver.  It is part of Intel's userspace command
submission stack and still relies on an initialized kernel/firmware contract;
it does not replace PCI reset, GuC boot, page tables, or interrupt setup.

## Why the direct PCI path is a separate milestone

Unbinding `xe` and mapping BARs is only the beginning.  Current Battlemage boot
requires signed microcontroller firmware and substantial initialization:

- GuC submission cannot be disabled in the current driver design;
- Linux requests Battlemage GuC major version 70 and `xe/bmg_huc.bin`;
- GuC/HuC upload uses WOPCM and authenticated firmware layouts;
- reset, force-wake, power wells, pcode, memory training/VRAM discovery,
  GGTT/PPGTT, interrupts, doorbells, engine contexts, and GuC CT buffers must
  be initialized in the correct order;
- stepping-specific register workarounds must be applied; and
- faults and hangs need a safe reset/recovery path during development.

For scale, the current upstream `drivers/gpu/drm/xe` directory is roughly 139k
lines across about 550 C/header files, although a headless compute-only port
would use a smaller subset.  The kernel code is dual MIT/GPL in many relevant
files, but every reused file/definition must be checked individually.

The sovereign milestone should therefore start after the `xe` UAPI backend can
produce known-good batches.  Captured UAPI command buffers and queried hardware
state then become an oracle for the PCI implementation.  A B580 is also useful
as an earlier, cheaper Xe2 validation target; product-specific assumptions must
remain isolated because B70 is not listed as G21.

## Work plan

### Phase 0: hardware-independent scaffolding

- [x] Generate minimal Python bindings from `xe_drm.h` plus required generic DRM
  ioctls; check struct sizes/offsets in tests.
- [x] Add `IntelDevice` with a mock interface and BMG PCI/product descriptors.
- [x] Implement query parsing, GPU VA allocation, GEM/VM-bind request building, and
  user-fence timeline objects.
- [x] Implement Xe2 command packet encoders with golden tests derived from Intel's
  generated definitions.
- [x] Define a compact program container for machine code, SIMD width, GRF count,
  SLM size, cross-thread data, and implicit arguments.
- [x] Load genuine BMG Zebins through mock dispatch, including Intel relocation
  validation, inline/indirect cross-thread payload placement, and hardware local
  ID generation.

Phase 0 is a testable structural prototype.  Before calling it complete for
hardware bring-up, add missing real-queue commands such as semaphore waits,
validate the full command prologue against a compute-runtime capture, and decide
which additional implicit `.ze_info` argument kinds the first tinygrad renderer
needs.

### Phase 1: kernel-assisted hardware bring-up

- [x] Add read-only Xe render-node discovery and stable CONFIG, ENGINES, and
  MEMORY_REGIONS query wrappers; reject non-`xe` devices.
- Extend the query wrapper into `XeKmdIface` allocation, VM-bind, execution,
  synchronization, and cleanup.
- Validate query, allocation/mmap, VM bind/unbind, and a no-op batch.
- Compile and dispatch add/copy kernels, then implement HCQ compute/copy queues.
- Add fault reporting using `devcoredump`, debugfs, and user-fence timeouts.
- Validate on B580/B570 if available, then B70.

### Phase 2: direct PCI/BAR driver

- Add a read-only PCI probe first: BAR layout, PCI capabilities, revision,
  GMD_ID, tiles/GTs, and fuse topology.
- Port reset/force-wake/power and VRAM/GGTT discovery with register-level tests.
- Load GuC/HuC firmware and establish CT/doorbell communication.
- Build PPGTT mappings, engine contexts, interrupts, submission, and recovery.
- Reuse Phase 1 batches and programs unchanged; only the interface changes.

### Phase 3: native compiler and optimization

- Replace offline IGC with a tinygrad Xe2 renderer/assembler.
- Add SLM/barriers, atomics, subgroups, vectorized memory, and XMX lowering.
- Tune occupancy, GRF modes, SIMD width, memory/cache policy, and multi-engine
  scheduling for B70.

## Unknowns that require hardware or newer public data

- B70 BAR sizes, revision/stepping, GMD_ID, tile/GT topology, and fuse layout;
- the minimum working GuC/HuC/NVM firmware combination on shipping cards;
- whether all 32 Xe cores reside on one GT and how they map to CCS engines;
- Resizable BAR behavior and the CPU-visible VRAM aperture on target systems;
- B70-specific workarounds absent from public G21 documentation; and
- cache policy, arbitration, and remaining command-prologue fields needed for a
  raw `COMPUTE_WALKER` on the shipping stepping.

No code should hard-code answers to these.  Add probe dumps and fail closed
when a queried topology or revision is unsupported.

Once a B70 is installed with the Linux `xe` driver, the first safe data capture
is read-only:

```sh
python extra/intel/query_xe.py > /tmp/b70-xe-query.json
```

This records the render node, PCI device/revision, VA width and alignment,
engine placements, and VRAM/system-memory regions.  It does not create a VM,
allocate memory, or submit GPU commands.

## Primary sources reviewed

The research snapshot used tinygrad commit
`810d8732f9b0f589f08c1b9443600254897852fd`, Linux commit
`37e2f878a7a660a216cc7a60459995fefd150f25`, Intel compute-runtime commit
`48d4b5a48767eefaf12aa349190cc3e105afe66a`, and IGC commit
`1ab82848b079dcfdaacba3815e653376ecf8f2ab`.  The `llm-scaler` review used
commit `1380ca7d443e24d0eb53e95353bc7f1f08be3476`.

- [Intel Arc Pro B70 product datasheet](https://www.intel.com/content/dam/www/central-libraries/us/en/documents/2026-03/datasheet-b70-gpu.pdf)
- [Intel Arc Pro B-series overview](https://www.intel.com/content/www/us/en/products/docs/discrete-gpus/arc/workstations/b-series/overview.html)
- [Linux Xe UAPI: `xe_drm.h`](https://github.com/torvalds/linux/blob/master/include/uapi/drm/xe_drm.h)
- [Linux Xe PCI/product description](https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/xe/xe_pci.c)
- [Linux Intel PCI IDs](https://github.com/torvalds/linux/blob/master/include/drm/intel/pciids.h)
- [Linux Xe firmware selection](https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/xe/xe_uc_fw.c)
- [Linux Xe driver documentation](https://github.com/torvalds/linux/tree/master/Documentation/gpu/xe)
- [Intel compute runtime](https://github.com/intel/compute-runtime)
- [BMG product helper naming `0xe223` as B70](https://github.com/intel/compute-runtime/blob/master/shared/source/xe2_hpg_core/linux/product_helper_bmg.cpp)
- [Xe ioctl helper in compute-runtime](https://github.com/intel/compute-runtime/blob/master/shared/source/os_interface/linux/xe/ioctl_helper_xe.cpp)
- [Generated Xe2 command definitions](https://github.com/intel/compute-runtime/blob/master/shared/source/generated/xe2_hpg_core/hw_cmds_generated_xe2_hpg_core.inl)
- [Intel `llm-scaler`](https://github.com/intel/llm-scaler)
- [`llm-scaler` BMG firmware installer](https://github.com/intel/llm-scaler/blob/main/vllm/tools/platform/installation/install_gpu_fw.sh)
- [`llm-scaler` platform FAQ](https://github.com/intel/llm-scaler/blob/main/vllm/FAQ.md)
- [`llm-scaler` BMG ESIMD build targets](https://github.com/intel/llm-scaler/blob/main/vllm/custom-esimd-kernels-vllm/setup_sycl.py)
- [`llm-scaler` hardware-specific attention configuration](https://github.com/intel/llm-scaler/blob/main/omni/omni_xpu_kernel/omni_xpu_kernel/lgrf_uni/sdp_config.h)
- [Intel graphics compiler](https://github.com/intel/intel-graphics-compiler)
- [IGC vISA documentation](https://github.com/intel/intel-graphics-compiler/tree/master/documentation/visa)
- [tinygrad AMD runtime](https://github.com/tinygrad/tinygrad/blob/master/tinygrad/runtime/ops_amd.py)
- [tinygrad NVIDIA runtime](https://github.com/tinygrad/tinygrad/blob/master/tinygrad/runtime/ops_nv.py)
- [tinygrad PCI support](https://github.com/tinygrad/tinygrad/blob/master/tinygrad/runtime/support/system.py)
