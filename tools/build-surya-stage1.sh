#!/usr/bin/env bash
# Offline build only: does not invoke adb/fastboot or write a phone partition.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "$#" -ne 5 ]; then
    echo "usage: $0 SURYA_KERNEL STOCK_DTB DRAM_BASE DRAM_SIZE MEMORY_EVIDENCE_FILE" >&2
    exit 2
fi
kernel=$(realpath "$1")
stock_dtb=$(realpath "$2")
evidence=$(realpath "$5")
[ -s "$kernel" ] && [ -s "$stock_dtb" ] && [ -s "$evidence" ]
mkdir -p shim/out/surya
clang -target arm64-apple-ios16.0 -c tools/sweet-init.S -o shim/out/surya/init.o
python3 tools/mkinit.py shim/out/surya/init.o shim/out/surya/test-init
python3 tools/surya.py shim/out/surya/surya.adt \
    --dram-base "$3" --dram-size "$4" --memory-evidence "$evidence"
python3 tools/mksurya-payload.py "$kernel" shim/out/surya/surya.adt \
    shim/out/surya/test-init shim/out/surya/payload.bin
BOARD=surya SURYA_DTB="$stock_dtb" bash shim/build.sh ../shim/out/surya/payload.bin
sha256sum shim/out/surya/{shim-boot.img,payload.bin,surya.adt,test-init}
echo "Built stage 1: test PID 1 only; no Apple iOS userland in this image."
