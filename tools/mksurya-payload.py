#!/usr/bin/env python3
"""Package a SURYA-target XNU and a mandatory test RAM-disk root."""
import argparse
from pathlib import Path
import mkpayload
import surya

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('kernel', type=Path)
    p.add_argument('adt', type=Path)
    p.add_argument('ramdisk', type=Path)
    p.add_argument('out', type=Path)
    a = p.parse_args()
    kernel = a.kernel.read_bytes()
    if b'SURYA: RAM-disk bring-up; board peripherals withheld' not in kernel:
        raise SystemExit('kernel lacks the SURYA target marker; build machine_config=SURYA')
    m = mkpayload.parse_macho(kernel)
    if m['cputype'] != 0x100000c or m['cpusub'] != 0:
        raise SystemExit('SURYA requires plain arm64, not arm64e')
    blob, info = mkpayload.build(str(a.kernel), str(a.adt), surya.CMDLINE, str(a.ramdisk))
    surya.validate_payload(blob)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(blob)
    print(a.out, info['size'], 'bytes; validated SURYA RAM-disk payload')
