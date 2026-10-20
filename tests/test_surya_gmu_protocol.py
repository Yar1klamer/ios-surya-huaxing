"""A618 acknowledgement decoding: unrelated IRQs must never pass a boot."""
import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('cc'), 'host C compiler required')
class GmuProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        p = Path(cls.temp.name)
        shutil.copyfile(ROOT / 'graphics/native/surya_gmu_protocol.h', p / 'protocol.h')
        (p / 'wrap.c').write_text('''#include "protocol.h"
unsigned request(void) { return SGMU_BOOT_SET; }
unsigned ack(void) { return SGMU_BOOT_ACK; }
unsigned release(void) { return SGMU_BOOT_RELEASE; }
int classify(unsigned status) { return sgmu_boot_reply(status); }
''')
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared',
                        '-fPIC', str(p / 'wrap.c'), '-o', str(p / 'protocol.so')], check=True)
        cls.lib = ctypes.CDLL(str(p / 'protocol.so'))
        cls.lib.classify.argtypes = [ctypes.c_uint32]

    def test_stock_request_six_encoding(self):
        self.assertEqual(self.lib.request(), 0x00400000)
        self.assertEqual(self.lib.ack(), 0x40000000)
        self.assertEqual(self.lib.release(), 0x40000000)

    def test_every_individual_interrupt(self):
        for bit in range(32):
            expected = 2 if bit == 15 else 1 if bit == 30 else 0
            self.assertEqual(self.lib.classify(1 << bit), expected, f'IRQ bit {bit}')

    def test_photo_status_is_neither_fault_nor_ack(self):
        self.assertEqual(self.lib.classify(0x800000), 0)
        self.assertEqual(self.lib.classify((1 << 26) | (1 << 18)), 0)

    def test_fault_overrides_ack(self):
        self.assertEqual(self.lib.classify(0x40008000), 2)
        self.assertEqual(self.lib.classify(0xffffffff), 2)
        self.assertEqual(self.lib.classify(0x40800000), 1)
