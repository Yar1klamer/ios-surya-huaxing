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
p.add_argument('--gui', action='store_true', help='clean GUI boot: mute console on first frame present and set sweetfb_hz=30')
p.add_argument('--touch-diagnostic', action='store_true', help='enable touch with visible console diagnostics')

a = p.parse_args()
if sum((a.diagnostic, a.gui, a.touch_diagnostic)) > 1:
    raise SystemExit('select only one boot profile')
kernel = a.kernel.read_bytes()
if b'SURYA: bounded Apple root writes armed' not in kernel:
    raise SystemExit('kernel lacks bounded SURYA Apple-root support')
m = mkpayload.parse_macho(kernel)
if m['cputype'] != 0x100000c or m['cpusub'] != 0:
    raise SystemExit('SURYA requires plain arm64')
cmdline = surya.APPLE_TOUCH_CMDLINE if a.touch_diagnostic else surya.APPLE_GUI_CMDLINE if a.gui else (surya.APPLE_DIAGNOSTIC_CMDLINE if a.diagnostic else surya.APPLE_CMDLINE)
blob, info = mkpayload.build(str(a.kernel), str(a.adt), cmdline)
result = surya.validate_payload(blob)
if result['stage'] != 'apple-root':
    raise SystemExit('expected an explicit Apple-root ADT')
a.out.parent.mkdir(parents=True, exist_ok=True)
a.out.write_bytes(blob)
print(a.out, info['size'], 'bytes; bounded Apple-root profile')
print('Do not boot before the root filesystem is installed with owner approval.')
