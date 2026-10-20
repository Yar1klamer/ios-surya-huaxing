"""Exercise the exact offline table builder embedded in the XNU patch."""
import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
VA, TABLE, DATA = 0x100000000, 0x110000000, 0x120000000


@unittest.skipUnless(shutil.which('cc'), 'host C compiler required')
class GpuPageTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        p = Path(cls.temp.name)
        shutil.copyfile(ROOT / 'graphics/native/surya_gpu_pt.h', p / 'pt.h')
        (p / 'wrap.c').write_text('''#include "pt.h"
static _Alignas(4096) uint64_t pool[2048];
static struct sgpt state;
int reset(uint64_t t,uint64_t d,uint64_t n,uint64_t v) {
 state=(struct sgpt){0}; return sgpt_init(&state,pool,t,d,n,v);
}
int reinit(uint64_t t,uint64_t d,uint64_t n,uint64_t v) {
 return sgpt_init(&state,pool,t,d,n,v);
}
int map(uint64_t v,uint64_t p,unsigned f) {return sgpt_map(&state,v,p,f);}
int unmap(uint64_t v) {return sgpt_unmap(&state,v);}
int translate(uint64_t v,uint64_t *p) {return sgpt_translate(&state,v,p);}
int seal(void) {return sgpt_seal(&state);}
uint64_t entry(unsigned i) {return pool[i];}
void corrupt(unsigned i,uint64_t value) {pool[i]=value;}
''', encoding='utf-8')
        subprocess.run(['cc', '-std=c11', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                        str(p / 'wrap.c'), '-o', str(p / 'pt.so')], check=True)
        cls.lib = ctypes.CDLL(str(p / 'pt.so'))
        for name in ('reset', 'reinit'):
            getattr(cls.lib, name).argtypes = [ctypes.c_uint64] * 4
        cls.lib.map.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint]
        cls.lib.unmap.argtypes = [ctypes.c_uint64]
        cls.lib.translate.argtypes = [ctypes.c_uint64, ctypes.POINTER(ctypes.c_uint64)]
        cls.lib.entry.argtypes = [ctypes.c_uint]
        cls.lib.entry.restype = ctypes.c_uint64
        cls.lib.corrupt.argtypes = [ctypes.c_uint, ctypes.c_uint64]

    def setUp(self):
        self.assertEqual(self.lib.reset(TABLE, DATA, 16384, VA), 0)

    def query(self, va):
        pa = ctypes.c_uint64(0xdeadbeef)
        result = self.lib.translate(va, ctypes.byref(pa))
        return result, pa.value

    def test_kernel_patch_is_exact_canonical_source(self):
        patch = (ROOT / 'xnu/patches/0092-surya-private-gpu-page-tables.patch').read_text()
        for name in ('surya_gpu_pt.h', 'surya_gpu_pt.c', 'surya_gmu_protocol.h'):
            body = patch.split('+++ b/bsd/dev/' + name + '\n', 1)[1].split('diff --git ', 1)[0]
            embedded = '\n'.join(line[1:] for line in body.splitlines() if line.startswith('+')) + '\n'
            self.assertEqual(embedded, (ROOT / 'graphics/native' / name).read_text())

    def test_full_xnu_page_and_descriptor_permissions(self):
        for i in range(4):
            self.assertEqual(self.lib.map(VA + 4096 * i, DATA + 4096 * i, 5 | (2 if i % 2 == 0 else 0)), 0)
        for off in range(16384):
            self.assertEqual(self.query(VA + off), (0, DATA + off))
        self.assertEqual(self.lib.entry(4), (TABLE + 4096) | 3)
        self.assertEqual(self.lib.entry(512), (TABLE + 8192) | 3)
        self.assertFalse(self.lib.entry(1024) & (1 << 7))
        self.assertTrue(self.lib.entry(1025) & (1 << 7))
        self.assertEqual(self.lib.entry(1024) >> 53 & 3, 3)

    def test_window_and_owned_physical_bounds(self):
        for va, pa in ((VA - 4096, DATA), (VA + 0x200000, DATA),
                       (VA, DATA - 4096), (VA, DATA + 16384), (VA, TABLE)):
            self.assertEqual(self.lib.map(va, pa, 3), 2)
        self.assertEqual(self.lib.map(VA + 0x1ff000, DATA + 12288, 3), 0)
        self.assertEqual(self.query(VA + 0x1fffff), (0, DATA + 16383))

    def test_invalid_geometry_and_overlap(self):
        for t, d, n, v in ((TABLE + 1, DATA, 16384, VA), (TABLE, DATA, 1, VA),
                           (TABLE, DATA, 16384, VA + 4096)):
            self.assertEqual(self.lib.reset(t, d, n, v), 1)
        for t, d, n, v in ((TABLE, TABLE + 4096, 16384, VA), (TABLE, DATA, 0, VA),
                           (TABLE, DATA, 0x400000, VA), (TABLE, DATA, 4096, 1 << 39),
                           ((1 << 48) - 4096, DATA, 4096, VA)):
            self.assertEqual(self.lib.reset(t, d, n, v), 2)

    def test_rejected_maps_do_not_replace_leaf(self):
        self.assertEqual(self.lib.map(VA, DATA, 3), 0)
        original = self.lib.entry(1024)
        self.assertEqual(self.lib.map(VA, DATA + 4096, 3), 3)
        for va, pa, flags in ((VA + 1, DATA, 3), (VA, DATA + 1, 3), (VA, DATA, 2), (VA, DATA, 17)):
            self.assertEqual(self.lib.map(va, pa, flags), 1)
        self.assertEqual(self.lib.entry(1024), original)

    def test_unmap_and_seal(self):
        self.assertEqual(self.query(VA)[0], 4)
        self.assertEqual(self.lib.map(VA, DATA, 3), 0)
        self.assertEqual(self.lib.unmap(VA), 0)
        self.assertEqual(self.query(VA)[0], 4)
        self.assertEqual(self.lib.map(VA, DATA, 3), 0)
        self.assertEqual(self.lib.seal(), 0)
        self.assertEqual(self.lib.map(VA + 4096, DATA + 4096, 3), 5)
        self.assertEqual(self.lib.unmap(VA), 5)
        self.assertEqual(self.lib.reinit(TABLE, DATA, 16384, VA), 5)
        self.assertEqual(self.query(VA), (0, DATA))

    def test_corrupt_table_and_leaf_rejected(self):
        self.assertEqual(self.lib.map(VA, DATA, 3), 0)
        leaf = self.lib.entry(1024)
        self.lib.corrupt(1024, leaf | (1 << 60))
        self.assertEqual(self.query(VA)[0], 6)
        self.lib.corrupt(1024, leaf)
        self.lib.corrupt(4, (TABLE + 12288) | 3)
        self.assertEqual(self.query(VA)[0], 6)
