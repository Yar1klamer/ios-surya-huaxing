"""Compile and test the exact C policy header shipped in kernel patch 0086."""
import ctypes
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest


@unittest.skipUnless(shutil.which('cc'), 'host C compiler required')
class StoragePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        patch = (Path(__file__).resolve().parents[1] /
                 'xnu/patches/0086-surya-bounded-apple-root.patch').read_text()
        added = patch.split('+++ b/bsd/dev/surya_ufs_policy.h\n', 1)[1]
        header = '\n'.join(line[1:] for line in added.splitlines()
                           if line.startswith('+') and not line.startswith('+++'))
        cls.work = tempfile.TemporaryDirectory()
        root = Path(cls.work.name)
        (root / 'policy.h').write_text(header)
        (root / 'wrapper.c').write_text('#include "policy.h"\n'
            'int command(unsigned op,int out,int rw){return surya_ufs_command_allowed(op,out,rw);}\n'
            'int bounds(unsigned long long a,unsigned long long n,unsigned long long x,'
            'unsigned long long y,unsigned long long z){return surya_ufs_root_range(a,n,x,y,z);}'
            'int volume(const unsigned char *h,unsigned long long n){return surya_hfsx_volume_matches(h,n);}')
        subprocess.run(['cc', '-shared', '-fPIC', '-Wall', '-Werror',
                        str(root / 'wrapper.c'), '-o', str(root / 'policy.so')], check=True)
        cls.lib = ctypes.CDLL(str(root / 'policy.so'))
        cls.lib.bounds.argtypes = [ctypes.c_ulonglong] * 5

    @classmethod
    def tearDownClass(cls):
        cls.work.cleanup()

    def test_probe_all_opcodes_reject_disk_writes(self):
        for opcode in range(256):
            self.assertEqual(self.lib.command(opcode, 0, 0), opcode in (0x00, 0x28))
            self.assertFalse(self.lib.command(opcode, 1, 0))

    def test_root_all_opcodes_allow_only_read_write_and_flush(self):
        for opcode in range(256):
            self.assertEqual(self.lib.command(opcode, 0, 1), opcode in (0x00, 0x28, 0x35))
            self.assertEqual(self.lib.command(opcode, 1, 1), opcode == 0x2a)

    def test_root_bounds_must_match_and_fit_image(self):
        self.assertTrue(self.lib.bounds(3688984, 26430947, 3688984, 26430947, 4194304))
        for values in [(2, 10, 3, 10, 8), (2, 10, 2, 11, 8), (2, 10, 2, 10, 11),
                       (0, 10, 0, 10, 8), (2, 10, 2, 10, 0),
                       (0xffffffff, 10, 0xffffffff, 10, 2),
                       (0x100000000, 10, 0x100000000, 10, 2)]:
            self.assertFalse(self.lib.bounds(*values), values)

    def test_root_write_gate_requires_expected_hfsx_volume(self):
        header = bytearray(48)
        header[:4] = b'HX\x00\x05'
        struct.pack_into('>II', header, 40, 4096, 4194304)
        self.assertTrue(self.lib.volume(bytes(header), 4194304))
        self.assertFalse(self.lib.volume(bytes(header), 4194303))
        header[:4] = bytes.fromhex('1020f5f2')  # Android F2FS superblock
        self.assertFalse(self.lib.volume(bytes(header), 4194304))
