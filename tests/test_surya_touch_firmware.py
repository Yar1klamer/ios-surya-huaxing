"""Reject unverified controller firmware before building a phone payload."""
import struct
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import surya_touch_firmware as fw

FW_DIR = ROOT / 'research' / 'live-surya-android' / 'fw'


def header_table(data):
    """The five SRAM parts as the loader's table has them: (file offset, SRAM address, size, crc)."""
    o0, a0, s0 = struct.unpack_from('<3I', data, 0)
    o1, a1, s1 = struct.unpack_from('<3I', data, 12)
    c0, c1 = struct.unpack_from('<2I', data, 0x18)
    a2, s2, o2, c2 = struct.unpack_from('<4I', data, 0x60)
    a3, s3, o3, c3 = struct.unpack_from('<4I', data, 0x70)
    a4, s4, _, c4 = struct.unpack_from('<4I', data, 0xf0)
    return [(o0, a0, s0 + 1, c0), (o1, a1, s1 + 1, c1), (o2, a2, s2 + 1, c2), (o3, a3, s3 + 1, c3), (0, a4, s4 + 1, c4)]


class TouchFirmwareTests(unittest.TestCase):
    def test_rejects_missing_and_truncated_images(self):
        for data in (b'', bytes(fw.SIZE - 1), bytes(fw.SIZE + 1)):
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                fw.validate(data)

    def test_rejects_wrong_image_of_correct_size(self):
        for panel in fw.PANELS:
            with self.subTest(panel=panel), self.assertRaises(ValueError):
                fw.validate(bytes(fw.SIZE), panel)
        self.assertIsNone(fw.panel_of(bytes(fw.SIZE)))

    def test_rejects_unknown_panel(self):
        with self.assertRaises(ValueError):
            fw.validate(bytes(fw.SIZE), 'nope')

    def test_kernel_tables_match_the_pinned_images(self):
        # patch 0091 (Tianma) / 0096 (Huaxing) carry each image's header table; compare with the real files when present
        text = (ROOT / 'xnu/patches/0091-surya-tianma-volatile-firmware-loader.patch').read_text() + \
               (ROOT / 'xnu/patches/0096-surya-huaxing-touch-firmware.patch').read_text()
        seen = 0
        for panel in fw.PANELS:
            path = FW_DIR / ('novatek_ts_%s_fw.bin' % panel)
            if not path.exists():
                continue
            data = path.read_bytes()
            self.assertEqual(fw.panel_of(data), panel)
            fw.validate(data, panel)
            for off, addr, size, crc in header_table(data):
                self.assertIn('{%su, %su, %du, 0x%08xu}' % (hex(off), hex(addr), size, crc), text)
            seen += 1
        if not seen:
            self.skipTest('device firmware not pulled (research/live-surya-android/fw)')
