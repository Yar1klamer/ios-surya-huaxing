#!/bin/bash
# Local build of the SURYA XNU kernel on macOS: the same steps as .github/workflows/xnu.yml, without GitHub.
# Needs Xcode 15.x (Xcode 16's iig emits IORPC.kernelContent, which this xnu lacks). Homebrew is NOT needed (it no longer
# supports Intel Macs): jq is part of macOS 15, cmake and ninja come from pip, xcodes/gum are stubbed (build.sh only checks
# that they exist). Installing the Kernel Debug Kit asks for the administrator password (sudo installer): run this in a Terminal.
# NOT yet run on the owner's machine: the first run is a trial, send the output if it stops.
# Usage: tools/build-kernel-macos.sh            full build (clean work tree each time)
#        XCODE=/Applications/Xcode_15.4.app tools/build-kernel-macos.sh
# Result: research/kernel-local/kernel.development.surya (+ SHA256SUMS), the same file CI's xnu-kernel artifact holds.
set -euo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd)
DXB_REPO=https://github.com/blacktop/darwin-xnu-build
DXB_SHA=663906528d1cd5ea8fde7de6f16de73db9511549      # keep in step with .github/workflows/xnu.yml
export MACOS_VERSION=${MACOS_VERSION:-13.5}              # xnu-8796, the iOS 16 era
export KERNEL_CONFIG=${KERNEL_CONFIG:-DEVELOPMENT}
export MACHINE_CONFIG=${MACHINE_CONFIG:-SURYA}
export MAKEFLAGS=${MAKEFLAGS:--k}                        # keep going: one run shows every compile error
WORK=${WORK:-$HOME/surya-xnu-build}

[ "$(uname)" = Darwin ] || { echo "build-kernel-macos.sh: this runs on macOS only" >&2; exit 1; }
for t in git curl patch python3 jq; do
	command -v "$t" >/dev/null || { echo "build-kernel-macos.sh: $t is missing" >&2; exit 1; }
done

# Xcode 15.x, not the newest one.
if [ -z "${XCODE:-}" ]; then
	XCODE=$(ls -d /Applications/Xcode_15*.app /Applications/Xcode15*.app /Applications/Xcode-15*.app /Applications/Xcode.app 2>/dev/null | sed -n 1p || true)
fi
[ -n "$XCODE" ] && [ -d "$XCODE" ] || { echo "Xcode 15.x not found in /Applications (set XCODE=...)" >&2; exit 1; }
export DEVELOPER_DIR="$XCODE/Contents/Developer"
XCVER=$(xcodebuild -version | sed -n 1p)
echo "using $XCVER at $XCODE"
case "$XCVER" in
	"Xcode 15."*) ;;
	*) echo "this kernel needs Xcode 15.x, found: $XCVER" >&2; exit 1 ;;
esac
xcrun --find iig >/dev/null

# build.sh only checks that "xcodes" and "gum" exist (Xcode is already installed, the version is given): stubs in a private directory.
mkdir -p "$WORK/bin"
for stub in xcodes gum; do
	printf '#!/bin/sh\nexit 0\n' > "$WORK/bin/$stub"
	chmod +x "$WORK/bin/$stub"
done
# cmake and ninja from pip (python wheels carry the binaries, also for Intel Macs), no Homebrew and no sudo.
if ! command -v cmake >/dev/null || ! command -v ninja >/dev/null; then
	[ -x "$WORK/venv/bin/python" ] || python3 -m venv "$WORK/venv"
	"$WORK/venv/bin/python" -m pip install -q cmake ninja
fi
export SURYA_EXTRA_PATH="$WORK/bin:$WORK/venv/bin"
export PATH="$SURYA_EXTRA_PATH:$PATH"
cmake --version | sed -n 1p
ninja --version

# The build project, pinned, with our patches next to blacktop's.
rm -rf "$WORK/dxb"
git init -q "$WORK/dxb"
git -C "$WORK/dxb" fetch -q --depth 1 "$DXB_REPO" "$DXB_SHA"
git -C "$WORK/dxb" checkout -q FETCH_HEAD
cp "$REPO"/xnu/patches/*.patch "$REPO"/xnu/patches/*.sh "$WORK/dxb/patches/"
# libfirehose_kernel is built arm64e-only; the SURYA kernel is plain arm64
sed -i '' 's/ARCHS="x86_64 arm64e" VALID_ARCHS="x86_64 arm64e"/ARCHS="x86_64 arm64e arm64" VALID_ARCHS="x86_64 arm64e arm64"/' "$WORK/dxb/build.sh"
grep -c 'VALID_ARCHS="x86_64 arm64e arm64"' "$WORK/dxb/build.sh"
# build.sh rebuilds PATH from Xcode, the system and /usr/local/bin only: keep our stubs and pip tools reachable too
sed -i '' 's|${SYSTEM_PATHS}${HOMEBREW_PATHS}"|${SYSTEM_PATHS}${HOMEBREW_PATHS}:${SURYA_EXTRA_PATH}"|' "$WORK/dxb/build.sh"
grep -c 'SURYA_EXTRA_PATH' "$WORK/dxb/build.sh"

(cd "$WORK/dxb" && bash build.sh) || echo "build.sh ended with errors: the kernel may still have been produced, see below" >&2

OUT="$REPO/research/kernel-local"
mkdir -p "$OUT"
cp -R "$WORK/dxb/fakeroot/System/Library/Kernels/." "$OUT/" 2>/dev/null || true
if ls "$OUT"/kernel.* >/dev/null 2>&1; then
	(cd "$OUT" && for f in kernel.*; do if [ -f "$f" ]; then shasum -a 256 "$f"; fi; done | tee SHA256SUMS)
	echo "done: $OUT"
else
	echo "no kernel was produced: send the log above" >&2
	exit 1
fi
