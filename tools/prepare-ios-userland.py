#!/usr/bin/env python3
"""Assemble iPhone X 16.7.16 userspace in a NEW local directory, never a device.

Inputs are the read-only APFS roots of OS, Cryptex1,SystemOS and Cryptex1,AppOS.
The output preserves Unix owners/modes/hard links and can be packed into HFSX.
Apple files and the resulting tree/image must stay out of Git.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import struct
import subprocess
import sys

BUILD = '20H392'
VERSION = '16.7.16'
VERSION_PATH = 'System/Library/CoreServices/SystemVersion.plist'
EXECUTABLES = ('sbin/launchd', 'usr/lib/dyld', 'usr/libexec/backboardd',
               'System/Library/CoreServices/SpringBoard.app/SpringBoard')
CACHE = 'System/Library/Caches/com.apple.dyld'


def version(root):
    with (root / VERSION_PATH).open('rb') as f:
        v = plistlib.load(f)
    if (v['ProductBuildVersion'], v['ProductVersion']) != (BUILD, VERSION):
        raise ValueError(f'expected iOS {VERSION} ({BUILD}); got {v}')
    return v


def executable(path):
    with path.open('rb') as f:
        h = f.read(12)
    if len(h) != 12 or struct.unpack('<III', h) != (0xfeedfacf, 0x100000c, 0):
        raise ValueError(f'not the expected plain arm64 Mach-O: {path}')
    if path.stat().st_mode & 0o111 == 0:
        raise ValueError(f'executable permission missing: {path}')


def check(root):
    version(root)
    files = {}
    for name in EXECUTABLES:
        path = root / name
        executable(path)
        files[name] = dict(size=path.stat().st_size,
                          sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                          uid=path.stat().st_uid, gid=path.stat().st_gid,
                          mode=oct(path.stat().st_mode & 0o7777))
    cache = root / CACHE / 'dyld_shared_cache_arm64'
    with cache.open('rb') as f:
        magic = f.read(16)
    if magic.rstrip(b'\0 ') != b'dyld_v1   arm64':
        raise ValueError(f'wrong dyld cache architecture: {magic!r}')
    files[CACHE] = dict(count=sum(p.is_file() for p in cache.parent.iterdir()),
                        magic=magic.decode('ascii').rstrip('\0'))
    return files


def copy(source, dest):
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(['rsync', '-aH', '--numeric-ids', str(source) + '/', str(dest) + '/'], check=True)


def additions(root):
    # ignition_level=1 finds the shared cache and non-cache cryptex files here.
    cache = root / 'private/preboot/Cryptexes/OS' / CACHE
    dest = root / CACHE
    dest.mkdir(parents=True, exist_ok=True)
    for src in cache.iterdir():
        target = dest / src.name
        if not os.path.lexists(target):
            os.link(src, target)
    for cryptex in ('OS', 'App'):
        base = root / 'private/preboot/Cryptexes' / cryptex
        for directory, dirs, files in os.walk(base, followlinks=False):
            # Include directory symlinks without following them outside this tree.
            names = files + [n for n in dirs if (Path(directory) / n).is_symlink()]
            for name in names:
                src = Path(directory) / name
                relative = src.relative_to(base)
                if str(relative).startswith(CACHE + '/'):
                    continue
                target = root / relative
                if not os.path.lexists(target):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if src.is_symlink():
                        target.symlink_to(os.readlink(src))
                        os.lchown(target, src.lstat().st_uid, src.lstat().st_gid)
                    else:
                        os.link(src, target)
    for directory, mode in [('diagnostics', 0o751), ('uuidtext', 0o755),
                            ('diagnostics/timesync', 0o755)]:
        d = root / 'private/var/db' / directory
        d.mkdir(parents=True, exist_ok=True)
        os.chown(d, 272, 272)
        os.chmod(d, mode)
        marker = d / '.migrated'
        marker.touch()
        os.chown(marker, 272, 272)
        os.chmod(marker, 0o644)
    keybags = root / 'private/var/keybags'
    keybags.mkdir(parents=True, exist_ok=True)
    os.chown(keybags, 0, 0)
    os.chmod(keybags, 0o700)
    keybag = keybags / 'systembag.kb'
    keybag.write_bytes(plistlib.dumps({'KeyBagKeys': b'SURYA'}, fmt=plistlib.FMT_XML))
    os.chmod(keybag, 0o600)


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--check':
        print(json.dumps(check(Path(sys.argv[2])), indent=2))
        return
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('os_root', type=Path)
    p.add_argument('systemos_root', type=Path)
    p.add_argument('appos_root', type=Path)
    p.add_argument('out', type=Path)
    a = p.parse_args()
    if os.geteuid() != 0:
        p.error('run on Linux as root to preserve numeric owners')
    version(a.os_root)
    if a.out.exists():
        p.error('output already exists; refusing to overwrite it')
    a.out.mkdir(parents=True)
    print('Copying OS, SystemOS and AppOS with original numeric owners...', flush=True)
    copy(a.os_root, a.out)
    copy(a.systemos_root, a.out / 'private/preboot/Cryptexes/OS')
    copy(a.appos_root, a.out / 'private/preboot/Cryptexes/App')
    additions(a.out)
    subprocess.run([sys.executable, str(Path(__file__).with_name('sweet-root-tweaks.py')),
                    str(a.out)], check=True)
    report = dict(board='surya', version=VERSION, build=BUILD, files=check(a.out),
                  status='prepared offline; not boot-tested on Poco',
                  kernel='SURYA; storage integration still required')
    a.out.with_suffix('.manifest.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
