# Graphics support on Poco X3 NFC

The working iOS GUI uses QuartzCore's CPU renderer and CPU framebuffer copies.
Native GPU command submission, Vulkan execution and Metal execution under XNU
have not been demonstrated. A successful shader compilation does not change
that status.

## Hardware evidence

`tools/surya_gpu_inventory.py` reads a captured Android device-tree directory.
It resolves clock, supply and IOMMU references and records hashes of the
properties it consumed. It never opens a device, powers a domain, maps registers,
or authorizes DMA. Keep its output and the captured device tree under ignored
`research/`.

The captured SURYA board has chip ID `0x06010800` (Adreno 618), GPU registers at
`0x05000000`, GMU at `0x0506a000`, GPUCC at `0x05090000` and SMMU at
`0x05040000`. The user and secure IOMMU contexts are distinct. These addresses
are hardware facts, not permission to read powered-down registers.

Xiaomi's `surya-q-oss` `drivers/gpu/msm/adreno-gpulist.h` selects `a630_sqe.fw`,
`a618_gmu.bin` and `a615_zap` for this chip. Firmware handling, GPU power and
clock control, GMU/HFI setup, the secure-monitor/PAS path, SMMU mappings and
fault handling must be implemented before command submission. Existing XNU
framebuffer and touch code does not provide those services.

Source: <https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/surya-q-oss/drivers/gpu/msm/adreno-gpulist.h>

## Offline translation test

The evaluated translator is `steelbrain/metal2vulkan`, pinned to
`a2c440b8bcdcf20d34aa1694b61ae22c2a7ea68b`. Its source and binaries remain
outside this repository. Build its release CLI with Rust 1.98 or newer:

```sh
cargo build --release -p metal2vulkan --features cli
```

On Linux/WSL with LLVM's `llvm-as`, SPIR-V Tools, GNU time, `timeout` and
`prlimit` installed, run:

```sh
bash tools/check-metal-translation.sh /path/to/metal2vulkan research/gpu-bringup/offline
```

The two authored fixtures are synthetic AIR-shaped LLVM modules: a uint buffer
copy, and vertex/fragment stages defining a red triangle. They are not produced
by Apple's Metal compiler. Each translation has a 20-second deadline and a
240-MiB per-process virtual-memory limit. Both emitted modules and pipeline
metadata are retained only after success and independent Vulkan 1.2 SPIR-V
validation. Resource measurements are included alongside the outputs.

The target profile is the translator's generic Vulkan 1.2 floor, **not a query of
the Poco's capabilities**. This proves only the selected compiler paths. It
does not prove shader semantics by execution, Apple metallib compatibility,
Objective-C Metal ABI compatibility, a native Vulkan device, or a rendered
triangle.

Sources: <https://github.com/steelbrain/metal2vulkan>,
<https://docs.mesa3d.org/drivers/freedreno.html>

## Host CPU Vulkan semantic check

`graphics/metal-smoke` is a Rust consumer of the same pinned translator and
runtime revision. It accepts only CPU Vulkan devices, compiles the synthetic
copy kernel through the runtime, submits 64 threads, waits for completion and
compares the full 256-byte output with a varied integer reference. The output
buffer starts with a different sentinel value so a missing dispatch cannot pass.
Its shader cache is explicitly placed under the supplied scratch directory.

```sh
cargo build --locked --release --manifest-path graphics/metal-smoke/Cargo.toml
bash tools/check-metal-runtime.sh \
  graphics/metal-smoke/target/release/surya-metal-host-smoke \
  research/gpu-bringup/offline/surya_copy.air \
  /usr/share/vulkan/icd.d/lvp_icd.json research/gpu-bringup/runtime
```

The test passed with lavapipe/llvmpipe (LLVM 20.1.2). This is CPU Vulkan on the
development PC, with no QEMU or phone access. It verifies the chosen integer
kernel's output through the Rust Metal-shaped runtime; it does not implement
the Objective-C Metal framework ABI or test iOS 16's system shaders. Runtime
notices remain in its log, including its host Metal-level defaults. There is
no claim of iOS Metal compatibility from this test.

## Native integration boundary

Mesa 25.3.0's `src/freedreno/vulkan/tu_knl.h` is the kernel-backend boundary to
evaluate for Turnip. The existing KGSL implementation depends on Linux
ioctls, DMA heaps/ION, mmap, sync files and timestamps. It cannot be loaded as
an XNU GPU driver. Porting needs real equivalents for GPU buffers and virtual
addresses, queues, submission, cache maintenance and fence completion.

The next native milestone is a private GPU buffer and bounded command/fence
test after verified power, firmware and SMMU initialization. Unsupported
operations must return an error; no fake GPU service or success-returning
submission stub is part of this work. Metal framework, shader and IOSurface
integration follow a working native Vulkan backend. Keep the working CPU GUI
and touch image available throughout bring-up.

## Private page-table component

`graphics/native/surya_gpu_pt.h` builds offline ARM LPAE stage-1 tables for a
single 2-MiB GPU VA window. Three 4-KiB tables occupy one XNU 16-KiB allocation.
Only caller-owned physical pages can be mapped; table memory cannot overlap
that allocation. Read/write, no-execute and cache attributes are explicit.
Duplicate/unaligned/out-of-range maps fail. Corrupted table references fail
closed. Sealing prohibits further mapping, unmapping or reinitialization.
This component is not a live SMMU driver: no cache publication, TLB invalidation,
TTBR programming or GPU access occurs. MAIR/layout must be matched explicitly
by a future hardware attachment, after capabilities and power are verified.

Patch0092 compiles the exact same header and an XNU diagnostic. The optional
`--gpu-table-diagnostic` Apple payload profile adds `suryagpummu=1`, allocates
private wired table/data pages and checks all 16384 byte translations plus
bounds, unmap and sealing before pausing ahead of launchd. Normal GUI profiles
leave it off. A pass means CPU-side table construction/allocation works; it
is not GPU execution or a hardware SMMU walk.

Descriptor reference: <https://github.com/torvalds/linux/blob/v6.12/drivers/iommu/io-pgtable-arm.c>

## A618 OOB bring-up correction

The hardware diagnostic now also attempts GPUCC/GMU bring-up. It is no longer
limited to offline tables. The default GUI profile still leaves it disabled.
A615-family (including A618) boot/slumber is request **6**: HOST2GMU bit22,
GMU2HOST ACK bit30, HOST2GMU release bit30. CM3 fault is bit15; bit23 alone
must not be called a firmware fault or a boot acknowledgement. Tests exercise
every individual status bit and require a fault to override an ACK.

Reference: [Xiaomi's GMU driver](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/surya-q-oss/drivers/gpu/msm/adreno_a6xx_gmu.c),
[request enum](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/surya-q-oss/drivers/gpu/msm/kgsl_gmu_core.h),
[IRQ masks](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/surya-q-oss/drivers/gpu/msm/kgsl_hfi.h).

The firmware upload is checked word for word while CM3 is in reset. The
transaction captures status before clearing its ACK, and stops GX writes after
an unsuccessful handshake. Existing GX/MX indices1/1 are diagnostic inputs,
not verified operating points: the stock driver derives these from RPMh
command-database voltage dependency tables. A successful handshake still does
not prove a GPU command, SMMU walk, Vulkan rendering, or Metal support.
