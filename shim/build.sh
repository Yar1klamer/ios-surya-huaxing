#!/bin/bash
# Build the shim and wrap it in a boot.img v2 that mirrors the stock PixelOS header.
set -euo pipefail
cd "$(dirname "$0")"
BOARD=${BOARD:-sweet}
case "$BOARD" in
    sweet) BOARD_FLAGS=""; DEFAULT_OS_VERSION=17.0.0; DEFAULT_OS_PATCH=2035-06 ;;
    surya) BOARD_FLAGS="-DSURYA_BRINGUP=1"; DEFAULT_OS_VERSION=16.0.0; DEFAULT_OS_PATCH=2026-10 ;;
    *) echo "unsupported BOARD: $BOARD" >&2; exit 1 ;;
esac
OUT=out
[ "$BOARD" != surya ] || OUT=out/surya
CC=aarch64-linux-gnu-gcc
OBJCOPY=aarch64-linux-gnu-objcopy
CFLAGS="-O2 -ffreestanding -nostdlib -fno-pic -mgeneral-regs-only -mstrict-align -fno-stack-protector -Wall -Wextra $BOARD_FLAGS"
mkdir -p "$OUT"
for f in start.S shim.c console.c mmu.c fdt.c loader.c ufs.c; do
	$CC $CFLAGS -c $f -o "$OUT"/${f%.*}.o
done
# The image runs wherever ABL puts it with no relocation pass: only the
# header's image_size (start.o, linked at 0) may be an absolute address.
abs=$(aarch64-linux-gnu-readelf -r "$OUT"/shim.o "$OUT"/console.o "$OUT"/mmu.o "$OUT"/fdt.o "$OUT"/loader.o "$OUT"/ufs.o | grep -c ABS64 || true)
[ "$abs" = 0 ] || { echo "error: $abs absolute relocations in C objects" >&2; exit 1; }
$CC $CFLAGS -static -T shim.ld -Wl,--build-id=none -Wl,--no-warn-rwx-segments -Wl,-N \
	"$OUT"/start.o "$OUT"/shim.o "$OUT"/console.o "$OUT"/mmu.o "$OUT"/fdt.o "$OUT"/loader.o "$OUT"/ufs.o -o "$OUT"/shim.elf
$OBJCOPY -O binary "$OUT"/shim.elf "$OUT"/Image
# ABL copies the file; pad to image_size so .bss/stacks exist as zeroed bytes.
size=$(aarch64-linux-gnu-nm "$OUT"/shim.elf | awk '$3=="_end"{print strtonum("0x"$1)}')
truncate -s "$size" "$OUT"/Image
# Build the raw Linux Image without needing a device DTB or a kernel payload.
if [ "${1:-}" = "--raw" ]; then
    sha256sum "$OUT"/Image
    exit 0
fi
# Ramdisk: an xnu payload (tools/mkpayload.py) if given as $1, else an empty
# newc cpio (ABL dislikes a zero-size ramdisk on some builds) -> diagnostics.
if [ -n "${1:-}" ]; then
	if [ "$BOARD" = surya ]; then
		python3 ../tools/check-surya-payload.py "$1"
	fi
	cp "$1" "$OUT"/ramdisk.bin
else
	[ "$BOARD" != surya ] || { echo "surya requires a validated RAM-disk payload" >&2; exit 1; }
	(cd "$OUT" && rm -rf rd && mkdir rd && cd rd && find . | cpio -o -H newc --quiet | gzip -9 > ../ramdisk.bin)
fi
# SURYA never silently packages sweet's DTB or copied PixelOS metadata.
DTB=${DTB:-../dtb/boot_unpacked/dtb}
if [ "$BOARD" = surya ]; then
    [ -n "${SURYA_DTB:-}" ] || { echo "set SURYA_DTB to this Poco's stock boot DTB" >&2; exit 1; }
    DTB=$SURYA_DTB
fi
MKBOOTIMG=${MKBOOTIMG:-mkbootimg}
"$MKBOOTIMG" --header_version 2 --kernel "$OUT"/Image --ramdisk "$OUT"/ramdisk.bin \
	--dtb "$DTB" --base 0 --kernel_offset 0x8000 --ramdisk_offset 0x1000000 \
	--tags_offset 0x100 --dtb_offset 0x1f00000 --pagesize 4096 \
	--os_version "${OS_VERSION:-$DEFAULT_OS_VERSION}" --os_patch_level "${OS_PATCH_LEVEL:-$DEFAULT_OS_PATCH}" \
	--cmdline "console=null" -o "$OUT"/shim-boot.img
# Host render of the console layout.
gcc -O1 -Wall -o "$OUT"/host_test console.c host_test.c && ./"$OUT"/host_test
ls -l "$OUT"/Image "$OUT"/shim-boot.img
