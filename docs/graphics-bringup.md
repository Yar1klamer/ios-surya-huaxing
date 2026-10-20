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
