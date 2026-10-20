#!/bin/bash
# Host-only compiler smoke test. Does not open Vulkan or access the Poco GPU.
set -euo pipefail
if [ "$#" -ne 2 ]; then
    echo "usage: $0 PINNED_METAL2VULKAN_CHECKOUT OUTPUT_DIRECTORY" >&2
    exit 2
fi
repo=$(realpath "$1")
out=$(realpath -m "$2")
project=$(cd "$(dirname "$0")/.." && pwd)
expected=a2c440b8bcdcf20d34aa1694b61ae22c2a7ea68b
[ "$(git -C "$repo" rev-parse HEAD)" = "$expected" ] || {
    echo "unexpected metal2vulkan revision" >&2; exit 2;
}
translator="$repo/target/release/metal2vulkan"
profile="$repo/crates/metal2vulkan-validation/profiles/vk12-floor.json"
[ -x "$translator" ] || { echo "build metal2vulkan release CLI first" >&2; exit 2; }
for tool in llvm-as spirv-val timeout prlimit; do command -v "$tool" >/dev/null; done
mkdir -p "$out"
scratch=$(mktemp -d /tmp/surya-metal.XXXXXXXX)
cleanup() { rm -f "$scratch"/*; rmdir "$scratch"; }
trap cleanup EXIT
for name in surya_copy surya_triangle; do
    llvm-as "$project/tests/fixtures/metal/$name.ll" -o "$scratch/$name.air"
    options=(--function surya_copy)
    if [ "$name" = surya_triangle ]; then
        options=(--function surya_vertex --fragment surya_fragment --color-format 0:BGRA8Unorm)
    fi
    /usr/bin/time -v -o "$scratch/$name.resources.txt" \
        timeout -k 1 20 prlimit --as=251658240 -- \
        "$translator" "$scratch/$name.air" "$scratch/$name.spv" \
        --profile "$profile" "${options[@]}" --emit-meta "$scratch/$name.json" \
        >"$scratch/$name.log" 2>&1
    cat "$scratch/$name.log"
done
for spv in "$scratch"/*.spv; do spirv-val --target-env vulkan1.2 "$spv"; done
# Publish only after both translations and independent validation succeed.
cp "$scratch"/* "$out/"
git -C "$repo" rev-parse HEAD > "$out/translator-commit.txt"
sha256sum "$profile" > "$out/profile.sha256"
sha256sum "$translator" > "$out/translator.sha256"
echo "PASS: authored synthetic AIR -> validated SPIR-V; no GPU execution tested"
