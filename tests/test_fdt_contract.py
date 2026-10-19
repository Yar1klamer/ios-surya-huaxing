import ctypes
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest


def tree(*, bank=(0x100000000, 0xfcc00000), fixed=None, header_reserve=None, cells=2):
    strings = bytearray()
    def prop(name, value):
        off = len(strings)
        strings.extend(name.encode() + b'\0')
        return struct.pack('>III', 3, len(value), off) + value + b'\0' * (-len(value) % 4)
    def node(name, body):
        n = name.encode() + b'\0'
        return struct.pack('>I', 1) + n + b'\0' * (-len(n) % 4) + body + struct.pack('>I', 2)
    u32 = lambda n: struct.pack('>I', n)
    reserved = b''
    if fixed:
        reserved = node('reserved-memory', prop('#address-cells', u32(2)) +
                        prop('#size-cells', u32(2)) + node('test', prop('reg', struct.pack('>QQ', *fixed))))
    body = (prop('#address-cells', u32(cells)) + prop('#size-cells', u32(2)) +
            node('memory@100000000', prop('reg', struct.pack('>QQ', *bank))) + reserved)
    data = node('', body) + u32(9)
    reserve = (struct.pack('>QQ', *header_reserve) if header_reserve else b'') + b'\0' * 16
    so = 40 + len(reserve)
    header = struct.pack('>10I', 0xd00dfeed, so + len(data) + len(strings), so,
                         so + len(data), 40, 17, 16, 0, len(strings), len(data))
    return header + reserve + data + strings


@unittest.skipIf(os.name == 'nt' or not shutil.which('cc'), 'run C helper checks on Linux/WSL with cc')
class FdtContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        lib = Path(cls.temp.name) / 'fdt.so'
        source = Path(__file__).resolve().parents[1] / 'shim/fdt.c'
        subprocess.run(['cc', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra',
                        str(source), '-o', str(lib)], check=True)
        cls.lib = ctypes.CDLL(str(lib))
        cls.lib.fdt_check_ram.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64]
        cls.lib.fdt_check_ram.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def check(self, blob, start=0x100000000, size=0x20000000):
        buf = ctypes.create_string_buffer(bytes(blob))
        return self.lib.fdt_check_ram(buf, start, size)

    def test_realistic_upper_bank(self):
        self.assertEqual(self.check(tree(fixed=(0x9c000000, 0x1700000))), 1)

    def test_zero_placeholder_memory_cannot_approve_ram(self):
        self.assertEqual(self.check(tree(bank=(0, 0))), 0)

    def test_range_outside_bank(self):
        self.assertEqual(self.check(tree(), start=0x1f0000000), 0)

    def test_fixed_reservation_overlap(self):
        self.assertEqual(self.check(tree(fixed=(0x110000000, 0x4000))), -2)

    def test_header_reservation_overlap(self):
        self.assertEqual(self.check(tree(header_reserve=(0x100000000, 0x4000))), -2)

    def test_adjacent_reservation_does_not_overlap(self):
        self.assertEqual(self.check(tree(fixed=(0x120000000, 0x4000))), 1)

    def test_unsupported_cells_and_overflow(self):
        self.assertEqual(self.check(tree(cells=1)), -1)
        self.assertEqual(self.check(tree(), start=0xfffffffffffffff0, size=0x100), -1)

    def test_invalid_token_and_string_bounds(self):
        blob = bytearray(tree())
        so = struct.unpack_from('>I', blob, 8)[0]
        struct.pack_into('>I', blob, so, 99)
        self.assertEqual(self.check(blob), -1)
        blob = bytearray(tree())
        struct.pack_into('>I', blob, 32, 0)
        self.assertEqual(self.check(blob), -1)


if __name__ == '__main__':
    unittest.main()
