#!/bin/bash
# Deliberately CPU Vulkan: semantic evidence for the host smoke, not Adreno.
set -euo pipefail
if [ "$#" -ne 4 ]; then
    echo "usage: $0 HOST_SMOKE_BINARY COPY_AIR CPU_ICD_JSON OUTPUT_DIRECTORY" >&2
    exit 2
fi
binary=$(realpath "$1")
air=$(realpath "$2")
icd=$(realpath "$3")
out=$(realpath -m "$4")
mkdir -p "$out"
env VK_DRIVER_FILES="$icd" /usr/bin/time -v -o "$out/runtime.resources.txt" \
    timeout -k 1 20 "$binary" "$air" "$out/cache" >"$out/runtime.log" 2>&1
cat "$out/runtime.log"
sha256sum "$binary" "$air" "$icd" > "$out/runtime-inputs.sha256"
