#!/usr/bin/env bash
# Build a local HFSX image using a Linux filesystem appliance. No iOS boot test.
set -euo pipefail
if [ "$#" -ne 2 ]; then
    echo "usage: $0 PREPARED_ROOT NEW_OUTPUT.img" >&2
    exit 2
fi
root=$(realpath "$1")
out=$(realpath -m "$2")
partial=$out.partial
script_dir=$(cd "$(dirname "$0")" && pwd)
[[ ! -e $out && ! -e $partial ]] || { echo "refusing to overwrite output" >&2; exit 1; }
for program in mkfs.hfsplus fsck.hfsplus guestfish tar sha256sum; do
    command -v "$program" >/dev/null
done
python3 "$script_dir/prepare-ios-userland.py" --check "$root" > "$out.files.json"
truncate -s "${IOS_ROOT_SIZE:-16G}" "$partial"
mkfs.hfsplus -s -J -v SuryaIOS16 "$partial"
# guestfish mounts the image file inside its own Linux appliance, never a host
# or phone disk. tar retains numeric owners, modes, symlinks and hard links.
tar --numeric-owner -C "$root" -cpf - . |
    LIBGUESTFS_BACKEND=direct guestfish --rw --format=raw -a "$partial" \
        run : mount-options rw,force /dev/sda / : tar-in /dev/stdin / : sync : umount-all
set +e
fsck.hfsplus -f -y "$partial" > "$out.fsck-repair.txt" 2>&1
repair=$?
fsck.hfsplus -f -n "$partial" > "$out.fsck-check.txt" 2>&1
verify=$?
set -e
if [[ $repair -gt 1 || $verify -ne 0 ]]; then
    echo "filesystem check needs review (repair=$repair verify=$verify); partial image preserved" >&2
    exit 1
fi
mv -- "$partial" "$out"
sha256sum "$out" > "$out.sha256"
echo "Prepared local userspace image: $out (not boot-tested on Poco)."
