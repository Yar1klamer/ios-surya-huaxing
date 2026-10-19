#!/usr/bin/env python3
"""Prepare an Apple launchd boot payload; never installs or boots it on a phone."""
import argparse
from pathlib import Path
import mkpayload
import surya

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('kernel', type=Path)
p.add_argument('adt', type=Path)
p.add_argument('out', type=Path)
p.add_argument('--diagnostic', action='store_true', help='tee selected daemon stderr from /dev/null to console')
a = p.parse_args()
kernel = a.kernel.read_bytes()
if b'SURYA: bounded Apple root writes armed' not in kernel:
    raise SystemExit('kernel lacks bounded SURYA Apple-root support')
m = mkpayload.parse_macho(kernel)
if m['cputype'] != 0x100000c or m['cpusub'] != 0:
    raise SystemExit('SURYA requires plain arm64')
blob, info = mkpayload.build(str(a.kernel), str(a.adt), surya.APPLE_DIAGNOSTIC_CMDLINE if a.diagnostic else surya.APPLE_CMDLINE)
result = surya.validate_payload(blob)
if result['stage'] != 'apple-root':
    raise SystemExit('expected an explicit Apple-root ADT')
a.out.parent.mkdir(parents=True, exist_ok=True)
a.out.write_bytes(blob)
print(a.out, info['size'], 'bytes; bounded Apple-root profile')
print('Do not boot before the root filesystem is installed with owner approval.')
