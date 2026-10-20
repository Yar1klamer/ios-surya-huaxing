import struct
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from surya_gpu_inventory import Tree, cells, strings


def u32(*values):
    return struct.pack('>' + 'I' * len(values), *values)


class GpuInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.soc = self.root / 'soc'
        self.soc.mkdir()
        self.node = self.soc / 'gpu'
        self.node.mkdir()

    def test_cell_and_string_truncation_rejected(self):
        with self.assertRaises(ValueError):
            cells(b'\x00')
        with self.assertRaises(ValueError):
            strings(b'qcom,gpu')

    def test_reg_uses_parent_64_bit_cells(self):
        (self.soc / '#address-cells').write_bytes(u32(2))
        (self.soc / '#size-cells').write_bytes(u32(2))
        (self.node / 'reg').write_bytes(u32(1, 0x5000000, 0, 0x40000))
        result = Tree(self.root).ranges(self.node)
        self.assertEqual(result[0]['base'], '0x105000000')
        self.assertEqual(result[0]['size'], '0x40000')

    def test_reg_name_count_mismatch_rejected(self):
        (self.node / 'reg').write_bytes(u32(0, 0x5000000, 0x40000))
        (self.node / 'reg-names').write_bytes(b'gpu\0extra\0')
        with self.assertRaises(ValueError):
            Tree(self.root).ranges(self.node)

    def test_clock_provider_and_arguments_resolved(self):
        clock = self.soc / 'gpucc'
        clock.mkdir()
        (clock / 'phandle').write_bytes(u32(43))
        (clock / '#clock-cells').write_bytes(u32(1))
        (self.node / 'clocks').write_bytes(u32(43, 17))
        result = Tree(self.root).references(self.node, 'clocks', '#clock-cells')
        self.assertEqual(result, [dict(provider='/soc/gpucc', args=[17])])
        (self.node / 'clocks').write_bytes(u32(43))
        with self.assertRaises(ValueError):
            Tree(self.root).references(self.node, 'clocks', '#clock-cells')

    def test_duplicate_and_missing_phandles_rejected(self):
        (self.node / 'clocks').write_bytes(u32(999, 1))
        with self.assertRaises(ValueError):
            Tree(self.root).references(self.node, 'clocks', '#clock-cells')
        for name in ('one', 'two'):
            node = self.soc / name
            node.mkdir()
            (node / 'phandle').write_bytes(u32(9))
        with self.assertRaises(ValueError):
            Tree(self.root)
