# iOS/XNU for Poco X3 NFC (surya)

Adaptation of [ios-sweet](https://github.com/dipa-studio/ios-sweet), pinned at
`11da58bd050672960c0a83b5bef2176047eea479`. Target: **Poco X3 NFC (`surya`),
SM7150 / Snapdragon 732G**. Other Poco X3 variants are not targets.

**Native SURYA XNU boots the RAM disk and runs the static test PID 1.**
Apple launchd and the iOS interface have not booted on this device.
Upstream Redmi Note 10 Pro results belong to that device. Its original
[README](README.sweet.md) is preserved as reference; its userdata-erasing
installation steps are not the procedure for this Poco port.

The previous independent Poco project is suspended and preserved at
`C:/Users/Arbuxik/Documents/ChatGPT/fdsfsdfdsfsdfffff`. This checkout is separate.

## Implemented

- Separate `SURYA` XNU machine configuration, plain arm64, reusing upstream's
  SM7150 CPU, GICv3, VM, crypto, RAM-disk, HFS and iOS compatibility support.
- Platform matches `xiaomi,surya`. Apple userland identity remains iPhone X
  (`iPhone10,3` / D22AP), separate from physical board identity.
- Poco ADT: one boot CPU, explicit RAM range/provenance, no UFS node, optional
  QEMU timer map. No Redmi RAM size is selected automatically.
- SURYA kernel refuses unverified Redmi touch/PMIC/USB/UFS routines at their
  entry points, including the L11C rail vote, regardless of copied boot arguments.
  The RAM-disk profile disables disk writes and persistent logging.
  An explicit measured-controller ADT can enable a read-only UFS probe while
  retaining the working RAM-disk root; native GPT identification passed on the Poco.
- Separate Poco shim output under `shim/out/surya/`. Payload failure halts instead
  of starting the Redmi UFS probe. Segment bounds are checked before RAM copies.
- A live-FDT check requires RAM coverage and rejects fixed reservation overlap
  before copying kernel segments.
- SURYA reserves at least 64 MiB of early I/O page-table coverage so the
  two boot framebuffer mappings fit with the small RAM-disk target.
- Packaging checks board identity, kernel target, plain arm64, RAM bounds,
  command line, entry point and required test RAM disk.

Internal `sweet-*` driver/node/protocol names remain where they are an existing
ABI. They do not select the Redmi physical board.

## Build stage 1

Stage 1 attempts **XNU plus a static test PID 1**, not SpringBoard or full iOS.
The build scripts do not invoke adb/fastboot or write any phone partition.

1. Build `xnu.yml` on a macOS host or your own GitHub fork with
   `machine_config=SURYA`, release 13.5, DEVELOPMENT. Download
   `kernel.development.surya`. The first complete SURYA build
   [passed on GitHub Actions](https://github.com/arbuxiktech/ios-surya/actions/runs/39300223403);
   all 82 numbered patches applied, artifact SHA256 and plain arm64 verified.
2. Obtain this Poco's stock boot DTB and actual RAM/reserved-memory map, including
   DTBO fixups. Choose a contiguous 32 MiB aligned range outside every firmware/XPU
   reservation. A generic UEFI compatibility DTB is reference material, not proof
   of the current firmware's layout. Memory evidence requires manual review.
3. On Linux/WSL with `clang`, `aarch64-linux-gnu-gcc`, `gawk`, Python 3 and Android
   `mkbootimg`, run:

   ```sh
   bash tools/build-surya-stage1.sh \
       /absolute/path/kernel.development.surya /absolute/path/surya-stock.dtb \
       VERIFIED_DRAM_BASE VERIFIED_DRAM_SIZE /absolute/path/memory-evidence.txt
   ```

   Memory values above are deliberately placeholders. Output:
   `shim/out/surya/shim-boot.img`. Review its hashes before a later observed
   temporary boot test. Stock boot-header layout also needs confirmation.

Build the raw shim without a DTB/kernel:

```sh
BOARD=surya bash shim/build.sh --raw
```

Output `shim/out/surya/Image` is **not a complete bootable iOS image**.

## Apple-root boot profile

Patch 0086 adds a separate bounded writable-root profile, prepared with
`tools/surya.py --apple-root` and `tools/mksurya-apple-root.py`.
It checks the measured userdata partition bounds and exposes only the installed
image window. The RAM-disk storage probe stays read-only. Preparing this image
does not authorize installing it or booting a writable root over Android data.

## Prepared userspace

A local 16 GiB HFSX image contains real iPhone X iOS 16.7.16 / 20H392
userspace: launchd, dyld, backboardd, SpringBoard and arm64 dyld caches.
`tools/prepare-ios-userland.py` assembles the roots and checks the executables;
`tools/pack-ios-userland.sh` packages a new local image. Filesystem checks passed
and executable hashes matched after read-back. Apple artifacts remain untracked.

This image has not booted on the Poco. UFS remains disabled; activation, display
and input support still need physical validation. No iOS/XNU QEMU boot tests
will be run under the current owner's preference.

## Verification and remaining work

Run `python3 -m unittest discover -s tests -v` and
`python3 tools/validate-repo.py`. The Poco shim and test-init assembly compile
locally. Patch 0082 applies to the relevant sources after patches 0001–0081;
this is not a full kernel compile or runtime test.

Next: validate Poco storage/clock/reset details and bring up storage read-only;
Poco panel refresh, touch, keys and power details; separately approved
installation of the prepared iOS userspace.
Do not reuse Redmi GPIO/rail values, partition offsets or installation approvals.

Earlier Poco UEFI diagnostics observed framebuffer `0x9c000000`, 1080×2400,
4320-byte stride. This agrees with the inherited console layout but does not
establish stock ABL panel continuity or LCD refresh behavior.

A physical Poco test confirmed RAM-disk root `md0`, the static test program
running as PID 1, and repeated heartbeat messages after patch 0084. The original
framebuffer mapping panic is resolved for this test. No partitions have been
flashed or erased. See [NOTES.md](NOTES.md) for evidence and remaining work.
