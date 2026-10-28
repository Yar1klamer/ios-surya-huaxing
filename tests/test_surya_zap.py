"""The GPU zap shader contract (tools) and the shape of its loader (patch 0099)."""
import re
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import surya
import surya_zap_firmware as zap

FW_DIR = ROOT / 'research' / 'live-surya-android' / 'fw'


def patch_added(name):
    text = (ROOT / 'xnu/patches' / name).read_text()
    return chr(10).join(l[1:] for l in text.splitlines() if l.startswith('+') and not l.startswith('+++'))


class ZapFirmwareTests(unittest.TestCase):
    def test_rejects_wrong_images(self):
        with self.assertRaises(ValueError):
            zap.validate(bytes(zap.MDT_SIZE), bytes(zap.CODE_SIZE))
        with self.assertRaises(ValueError):
            zap.validate(b'', b'')

    def test_pinned_images_from_the_phone_validate(self):
        mdt, code = FW_DIR / 'a615_zap.mdt', FW_DIR / 'a615_zap.b02'
        if not (mdt.exists() and code.exists()):
            self.skipTest('device firmware not pulled (research/live-surya-android/fw)')
        zap.validate(mdt.read_bytes(), code.read_bytes())

    def test_region_is_the_device_trees_gpu_region(self):
        self.assertEqual((zap.REGION_BASE, zap.REGION_SIZE), (0x97715000, 0x2000))
        added = patch_added('0099-surya-zap-shader-loader.patch')
        self.assertIn('#define ZAP_REGION_PA           0x97715000ull', added)
        self.assertIn('#define ZAP_REGION_SIZE         0x2000u', added)


class ZapProfileTests(unittest.TestCase):
    def test_zap_profile_extends_the_gpu_profile_only_by_suryazap(self):
        self.assertEqual(surya.APPLE_GPU_ZAP_CMDLINE, surya.APPLE_GPU_PT_CMDLINE + ' suryazap=1')
        for cmd in (surya.APPLE_CMDLINE, surya.APPLE_GUI_CMDLINE, surya.APPLE_TOUCH_CMDLINE, surya.APPLE_GPU_PT_CMDLINE):
            self.assertNotIn('suryazap', cmd)


class ZapLoaderShapeTests(unittest.TestCase):
    def setUp(self):
        self.added = patch_added('0099-surya-zap-shader-loader.patch')

    def test_calls_come_in_linux_order(self):
        calls = re.findall(r'zap_scm\("[^"]*",\s*ZAP_64 \| ZAP_SIP \| (ZAP_PAS_\w+)', self.added)
        self.assertEqual(calls, ['ZAP_PAS_SHUTDOWN', 'ZAP_PAS_INIT_IMAGE', 'ZAP_PAS_MEM_SETUP',
                                 'ZAP_PAS_AUTH_AND_RESET', 'ZAP_PAS_SHUTDOWN'])
        # the code goes into the reserved memory only after TrustZone took the place, and before the authentication
        self.assertLess(self.added.index('ZAP_PAS_MEM_SETUP,'), self.added.index('region[i] = word;'))
        self.assertLess(self.added.index('region[i] = word;'), self.added.index('ZAP_PAS_AUTH_AND_RESET,'))

    def test_only_the_explicit_bootarg_runs_it(self):
        self.assertIn('PE_parse_boot_argn("suryazap"', self.added)
        self.assertIn('zap_enabled == 1 && tz.answers', self.added)

    def test_every_call_is_announced_first(self):
        self.assertLess(self.added.index('SURYA ZAP: asking TrustZone'), self.added.index('smc #0'))


if __name__ == '__main__':
    unittest.main()
