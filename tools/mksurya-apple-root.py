#!/usr/bin/env python3
"""Prepare an Apple launchd boot payload; never installs or boots it on a phone."""
import argparse
from pathlib import Path
import mkpayload
import surya
import adt
import surya_touch_firmware

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('kernel', type=Path)
p.add_argument('adt', type=Path)
p.add_argument('out', type=Path)
p.add_argument('--diagnostic', action='store_true', help='tee selected daemon stderr from /dev/null to console')
p.add_argument('--gui', action='store_true', help='clean GUI boot: mute console on first frame present and set sweetfb_hz=30')
p.add_argument('--touch-diagnostic', action='store_true', help='enable touch with visible console diagnostics')

p.add_argument('--touch-firmware', type=Path, help='pinned Poco touch controller RAM firmware (Tianma or Huaxing image; the panel is taken from its hash)')
p.add_argument('--gmu-firmware', type=Path, help='pinned Adreno 618 GMU firmware')

p.add_argument('--gpu-table-diagnostic', action='store_true', help='pause before launchd for offline XNU GPU table allocation checks')

p.add_argument('--cpus', type=int, default=1, help='boot CPU count (1..8); must equal the ADT CPU node count (surya.py --cpus)')

a = p.parse_args()
if sum((a.diagnostic, a.gui, a.touch_diagnostic, a.gpu_table_diagnostic)) > 1:
    raise SystemExit('select only one boot profile')
kernel = a.kernel.read_bytes()
if b'SURYA: bounded Apple root writes armed' not in kernel:
    raise SystemExit('kernel lacks bounded SURYA Apple-root support')
m = mkpayload.parse_macho(kernel)
if m['cputype'] != 0x100000c or m['cpusub'] != 0:
    raise SystemExit('SURYA requires plain arm64')
cmdline = surya.APPLE_GPU_PT_CMDLINE if a.gpu_table_diagnostic else surya.APPLE_TOUCH_CMDLINE if a.touch_diagnostic else surya.APPLE_GUI_CMDLINE if a.gui else (surya.APPLE_DIAGNOSTIC_CMDLINE if a.diagnostic else surya.APPLE_CMDLINE)
cmdline = surya.with_cpus(cmdline, a.cpus)
if a.gpu_table_diagnostic and b'SURYA GPU PAGE TABLE DIAGNOSTIC' not in kernel:
    raise SystemExit('kernel lacks SURYA GPU table diagnostic')
adt_path = a.adt
if a.touch_firmware or a.gmu_firmware:
    tree, end = adt.parse(a.adt.read_bytes())
    if end != a.adt.stat().st_size:
        raise SystemExit('unexpected trailing ADT bytes')
    chosen = surya.child(tree, 'chosen')
    if a.touch_firmware:
        if not (a.gui or a.touch_diagnostic or a.gpu_table_diagnostic):
            raise SystemExit('touch firmware requires a touch-enabled boot profile')
        fw_bytes = a.touch_firmware.read_bytes()
        panel = surya_touch_firmware.panel_of(fw_bytes)
        if panel is None:
            raise SystemExit('touch firmware is not one of the pinned Tianma/Huaxing images')
        if ('SURYA TOUCH: loading verified %s image' % panel.capitalize()).encode() not in kernel:
            raise SystemExit('kernel lacks the bounded %s SRAM loader' % panel.capitalize())
        fw = surya_touch_firmware.validate(fw_bytes, panel)
        surya.setprop(chosen, 'surya-touch-panel', panel.encode() + b'\0')
        surya.setprop(chosen, 'surya-touch-firmware', fw)
    if a.gmu_firmware:
        gmu_fw = a.gmu_firmware.read_bytes()
        if len(gmu_fw) != 32768:
            raise SystemExit(f'invalid GMU firmware size: {len(gmu_fw)}')
        surya.setprop(chosen, 'surya-gmu-firmware', gmu_fw)
    adt_path = a.out.with_suffix('.adt')
    adt_path.parent.mkdir(parents=True, exist_ok=True)
    adt_path.write_bytes(adt.serialize(tree))
blob, info = mkpayload.build(str(a.kernel), str(adt_path), cmdline)
result = surya.validate_payload(blob)
if result['stage'] != 'apple-root':
    raise SystemExit('expected an explicit Apple-root ADT')
a.out.parent.mkdir(parents=True, exist_ok=True)
a.out.write_bytes(blob)
print(a.out, info['size'], 'bytes; bounded Apple-root profile')
print('Do not boot before the root filesystem is installed with owner approval.')
