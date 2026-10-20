"""Pinned UniXNU components: provenance, upstream software tests, ARM compile."""
from pathlib import Path
import hashlib, json, shutil, subprocess, tempfile, unittest
ROOT=Path(__file__).resolve().parents[1]
VENDOR=ROOT/'graphics/vendor/unixnu'

class UnixnuVendorTests(unittest.TestCase):
    def test_pinned_file_hashes_and_licenses(self):
        m=json.loads((VENDOR/'sources.json').read_text())
        for name, component in m['components'].items():
            self.assertEqual(len(component['commit']),40)
            self.assertIn('MIT License',(VENDOR/name/'LICENSE').read_text())
            for filename, expected in component['files'].items():
                self.assertEqual(hashlib.sha256((VENDOR/name/filename).read_bytes()).hexdigest(),expected,filename)

    @unittest.skipUnless(shutil.which('cc'),'C compiler required')
    def test_upstream_software_fixtures(self):
        src=VENDOR/'ArmSmmu4K'
        # Direct MMIO binding requires ARM64. Do not replace its real barriers
        # with host stubs: compile it separately, and run the pure C fixtures.
        sources=sorted(str(p) for p in src.glob('ArmSmmu4K*.c') if p.name!='ArmSmmu4KMmio.c')
        with tempfile.TemporaryDirectory() as d:
            for name in ('tables','alias','audit','streams'):
                exe=str(Path(d)/name)
                linked=[p for p in sources if name!='alias' or not p.endswith('/ArmSmmu4KLive.c')]
                result=subprocess.run(['cc','-std=c11','-O2','-I',str(src),*linked,str(src/f'test_{name}.c'),'-o',exe],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                result=subprocess.run([exe],check=True,capture_output=True,text=True,timeout=20)
                self.assertIn('PASS',result.stdout,name)

    @unittest.skipUnless(shutil.which('aarch64-linux-gnu-gcc'),'ARM64 cross compiler required')
    def test_real_mmio_adapter_cross_compiles(self):
        src=VENDOR/'ArmSmmu4K'
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(['aarch64-linux-gnu-gcc','-std=c11','-ffreestanding','-Wall','-Wextra','-Werror','-c',str(src/'ArmSmmu4KMmio.c'),'-o',str(Path(d)/'mmio.o')],check=True,capture_output=True)

    @unittest.skipUnless(shutil.which('c++'),'C++ compiler required')
    def test_exact_native_adreno_wire_layout(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'abi.cpp';exe=Path(d)/'abi'
            source.write_text('#include "NativeAdrenoABI.h"\nstatic_assert(NativeAdrenoAbiVersion==1);\nstatic_assert(NativeAdrenoMethodBoImport==16);\nint main() {return 0;}\n')
            subprocess.run(['c++','-std=c++17','-I',str(VENDOR/'NativeAdreno'),str(source),'-o',str(exe)],check=True,capture_output=True)
            subprocess.run([str(exe)],check=True)

    def test_kernel_patch_is_generated_from_pinned_sources(self):
        import runpy
        tool=runpy.run_path(str(ROOT/'tools/gen_unixnu_smmu_patch.py'))
        self.assertEqual(tool['generate'](),(ROOT/'xnu/patches/0093-surya-unixnu-smmu-foundation.patch').read_text())

    @unittest.skipUnless(shutil.which('cc'),'C compiler required')
    def test_surya_geometry_and_inactive_context(self):
        code=r'''#include <assert.h>
#include "surya_unixnu_smmu.h"
static _Alignas(4096) uint64_t tables[2048];
int main(void) {
 uint32_t off=0;
 assert(!surya_unixnu_cb0(0x20000008,65536,&off) && off==0x8000);
 assert(surya_unixnu_cb0(0x20000008,65535,&off) && off==0);
 assert(surya_unixnu_cb0(0,65536,&off));
 assert(surya_unixnu_cb0(0xffffffff,65536,&off));
 assert(surya_unixnu_cb0(0x20010008,65536,&off));
 assert(surya_unixnu_cb0(0xa0000008,65536,&off));
 assert(surya_unixnu_cb0(0x20000009,65536,&off));
 ArmSmmu4KConfig c={39,36,0x110000000ull,4};
 ArmSmmu4KRange range={0x100000000ull,0x120000000ull,16384,3,0,2};
 ArmSmmu4KResult built={0};
 assert(!ArmSmmu4KBuild(&c,&range,1,tables,4,&built));
 assert(built.table_pages==3 && built.leaf_pages==4 && built.start_level==1);
 ArmSmmu4KContextConfig ctx={0};ctx.lower=&c;ctx.lower_tables=&built;
 ctx.id0=1u<<30;ctx.id2=0x1510;ctx.asid=1;ctx.stall_on_fault=1;
 ArmSmmu4KContextImage image={0};
 assert(!ArmSmmu4KEncodeContext(&ctx,&image));
 assert(image.ttbr0==0x0001000110000000ull && image.mair0==0xff44);
 ctx.id0=0;
 assert(ArmSmmu4KEncodeContext(&ctx,&image)==ArmSmmu4KUnsupported);
 assert(image.ttbr0==0 && image.sctlr==0);
 return 0;
}
'''
        kit=VENDOR/'ArmSmmu4K'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bridge.c';p.write_text(code);exe=Path(d)/'bridge'
            r=subprocess.run(['cc','-std=c11','-I',str(kit),'-I',str(ROOT/'graphics/native'),str(p),str(kit/'ArmSmmu4K.c'),str(kit/'ArmSmmu4KContext.c'),'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            subprocess.run([str(exe)],check=True)
