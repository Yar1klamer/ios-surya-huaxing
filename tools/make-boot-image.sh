#!/bin/bash
# Build a temporary-boot image for the Poco X3 NFC (surya) from a kernel, on macOS or Linux, without the old Linux host.
# Needs python3 and the "bundle" folder (default research/macos-bundle): shim-Image, smp6.adt, stock.dtb, mkbootimg/, fw/.
# Never touches the phone: the result is only for "fastboot boot".
#
# Usage: tools/make-boot-image.sh KERNEL PROFILE OUT.img [CPUS]
#   PROFILE  gui | touch | gpu | gpu-zap | diag    (gui = muted console, touch = visible console, gpu = GPU page-table diagnostic,
#                                                   gpu-zap = gpu + the zap shader handed to TrustZone, diag = daemon-stderr diagnostic)
#   CPUS     boot CPU count, default 6 (8 is not stable)
set -euo pipefail
[ $# -ge 3 ] || { sed -n 2,11p "$0"; exit 1; }
REPO=$(cd "$(dirname "$0")/.." && pwd)
BUNDLE=${BUNDLE:-$REPO/research/macos-bundle}
KERNEL=$1 PROFILE=$2 OUT=$3 CPUS=${4:-6}
FW=$BUNDLE/fw
for f in "$KERNEL" "$BUNDLE/shim-Image" "$BUNDLE/smp6.adt" "$BUNDLE/stock.dtb" "$BUNDLE/mkbootimg/mkbootimg.py" \
         "$FW/novatek_ts_huaxing_fw.bin" "$FW/a618_gmu.bin" "$FW/a615_zap.mdt" "$FW/a615_zap.b02"; do
	[ -e "$f" ] || { echo "make-boot-image.sh: missing $f" >&2; exit 1; }
done
case "$PROFILE" in
	gui)      ARGS=(--gui) ;;
	touch)    ARGS=(--touch-diagnostic) ;;
	gpu)      ARGS=(--gpu-table-diagnostic) ;;
	gpu-zap)  ARGS=(--gpu-zap-diagnostic --zap-dir "$FW") ;;
	diag)     ARGS=(--diagnostic) ;;
	*) echo "unknown profile $PROFILE" >&2; exit 1 ;;
esac
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
python3 "$REPO/tools/mksurya-apple-root.py" "$KERNEL" "$BUNDLE/smp6.adt" "$WORK/payload.bin" "${ARGS[@]}" \
	--cpus "$CPUS" --touch-firmware "$FW/novatek_ts_huaxing_fw.bin" --gmu-firmware "$FW/a618_gmu.bin"
python3 "$BUNDLE/mkbootimg/mkbootimg.py" --header_version 2 --os_version 16.0.0 --os_patch_level 2026-10 \
	--kernel "$BUNDLE/shim-Image" --ramdisk "$WORK/payload.bin" --dtb "$BUNDLE/stock.dtb" \
	--pagesize 0x1000 --base 0 --kernel_offset 0x8000 --ramdisk_offset 0x1000000 --second_offset 0 \
	--tags_offset 0x100 --dtb_offset 0x1f00000 --cmdline console=null -o "$OUT"
shasum -a 256 "$OUT" 2>/dev/null || sha256sum "$OUT"
echo "ready: $OUT  (fastboot boot $OUT; temporary, nothing is flashed)"
