"""DT-to-kernel resources: context-offset semantics and bus/provider refusals."""
import copy, struct, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from gen_surya_gpu_dt import generate

def words(*v):return struct.pack('>'+str(len(v))+'I',*v)

class GpuDtTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);soc=self.root/'soc';soc.mkdir()
        (self.root/'#address-cells').write_bytes(words(2))
        (soc/'#address-cells').write_bytes(words(1));(soc/'#size-cells').write_bytes(words(1))
        (soc/'ranges').write_bytes(words(0,0,0,0xffffffff))
        self.report={'chip_id':'0x6010800','nodes':{},'property_hashes':{},'iommu_contexts':{}}
        specs={'gpu':('gpu',0x5000000,0x40000),'gmu':('gmu',0x506a000,0x31000),'gpucc':('gpucc',0x5090000,0x9000),'smmu':('smmu',0x5040000,0x10000)}
        for key,(name,base,size) in specs.items():
            n=soc/name;n.mkdir();(n/'reg').write_bytes(words(base,size))
            self.report['nodes'][key]={'path':'/soc/'+name}
        (soc/'gmu/reg').write_bytes(words(0x506a000,0x31000,0xb290000,0x10000,0xb490000,0x10000))
        (soc/'gmu/reg-names').write_bytes(b'csr\0kgsl_gmu_pdc_cfg\0kgsl_gmu_pdc_seq\0')
        gcc=soc/'gcc';gcc.mkdir();(gcc/'reg').write_bytes(words(0x100000,0x1f0000));(gcc/'compatible').write_bytes(b'qcom,gcc-sdmmagpie\0syscon\0')
        self.report['nodes']['smmu']['clocks']=[{'name':'gcc_gpu_memnoc_gfx_clk','provider':'/soc/gcc','args':[43]}]
        for name,sid in [('gfx3d_user',0),('gfx3d_secure',2)]:
            self.report['iommu_contexts'][name]=[{'provider':'/soc/smmu','args':[sid]}]
        user=soc/'qcom,kgsl-iommu@5040000/gfx3d_user';user.mkdir(parents=True)
        (user/'qcom,gpu-offset').write_bytes(words(0x48000))
    def run_generator(self):
        with patch('gen_surya_gpu_dt.inventory',return_value=copy.deepcopy(self.report)):
            return generate(self.root)
    def test_context_offset_is_gpu_relative(self):
        out=self.run_generator()
        self.assertIn('SURYA_DT_USER_CB_OFFSET UINT64_C(0x8000)',out)
        self.assertIn('SURYA_DT_MEMNOC_CLOCK_ID UINT64_C(0x2b)',out)
        self.assertIn('SURYA_DT_SECURE_SID UINT64_C(0x2)',out)
    def test_reject_wrong_clock_provider(self):
        (self.root/'soc/gcc/compatible').write_bytes(b'qcom,other\0')
        with self.assertRaises(ValueError):self.run_generator()
    def test_reject_context_outside_smmu(self):
        (self.root/'soc/qcom,kgsl-iommu@5040000/gfx3d_user/qcom,gpu-offset').write_bytes(words(0x90000))
        with self.assertRaises(ValueError):self.run_generator()
    def test_reject_unhandled_bus_translation(self):
        (self.root/'soc/ranges').write_bytes(words(0,0,0x100000,0xff000000))
        with self.assertRaises(ValueError):self.run_generator()
