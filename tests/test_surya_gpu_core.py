"""The 3D core stage 1 (patch 0100): the register list is Linux's a6xx_hw_init for an A618, and it never starts the command processor."""
import re
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import surya

# Byte offsets (dwords * 4) from Linux registers/adreno/a6xx.xml, checked when the patch was written.
LINUX = {
    'GBIF_HALT': 0xf114, 'RBBM_GBIF_HALT': 0x58, 'RBBM_SECVID_TSB_CNTL': 0x3e00c,
    'RBBM_SECVID_TSB_TRUSTED_BASE': 0x3e000, 'RBBM_SECVID_TSB_TRUSTED_SIZE': 0x3e008,
    'CP_ADDR_MODE_CNTL': 0x2108, 'VSC_ADDR_MODE_CNTL': 0x3004, 'GRAS_ADDR_MODE_CNTL': 0x21804,
    'RB_ADDR_MODE_CNTL': 0x23814, 'PC_ADDR_MODE_CNTL': 0x27804, 'HLSQ_ADDR_MODE_CNTL': 0x2f814,
    'VFD_ADDR_MODE_CNTL': 0x29804, 'VPC_ADDR_MODE_CNTL': 0x25804, 'UCHE_ADDR_MODE_CNTL': 0x3800,
    'SP_ADDR_MODE_CNTL': 0x2b804, 'TPL1_ADDR_MODE_CNTL': 0x2d804, 'RBBM_SECVID_TSB_ADDR_MODE_CNTL': 0x3e040,
    'RBBM_VBIF_CLIENT_QOS_CNTL': 0x40, 'RBBM_PERFCTR_GPU_BUSY_MASKED': 0x142c,
    'UCHE_WRITE_RANGE_MAX': 0x3814, 'UCHE_TRAP_BASE': 0x3824, 'UCHE_WRITE_THRU_BASE': 0x381c,
    'UCHE_GMEM_RANGE_MIN': 0x382c, 'UCHE_GMEM_RANGE_MAX': 0x3834, 'UCHE_FILTER_CNTL': 0x3860,
    'UCHE_CACHE_WAYS': 0x385c, 'CP_ROQ_THRESHOLDS_2': 0x2308, 'CP_ROQ_THRESHOLDS_1': 0x2304,
    'CP_MEM_POOL_SIZE': 0x230c, 'PC_DBG_ECO_CNTL': 0x27800, 'CP_AHB_CNTL': 0x2634, 'RBBM_PERFCTR_CNTL': 0x1400,
    'RBBM_INTERFACE_HANG_INT_CNTL': 0x7c, 'UCHE_CLIENT_PF': 0x3864,
}
# The command processor's own start-up registers: stage 1 must not touch them.
CP_START = {0x2000, 0x2008, 0x2010, 0x201c, 0x2020, 0x2058, 0x3d000}


def added():
    text = (ROOT / 'xnu/patches/0100-surya-gpu-core-stage1.patch').read_text()
    return chr(10).join(l[1:] for l in text.splitlines() if l.startswith('+') and not l.startswith('+++'))


class GpuCoreStage1Tests(unittest.TestCase):
    def setUp(self):
        self.src = added()
        self.regs = re.findall(r'\{ "(\w+)", (0x[0-9a-f]+), ', self.src)

    def test_every_register_is_linuxs_offset(self):
        self.assertEqual(len(self.regs), len(LINUX))
        for name, off in self.regs:
            self.assertEqual(int(off, 16), LINUX[name], name)

    def test_the_command_processor_is_not_started(self):
        for name, off in self.regs:
            self.assertNotIn(int(off, 16), CP_START, name)
        self.assertNotIn('CP_SQE_CNTL', self.src)

    def test_each_write_is_announced_first(self):
        self.assertLess(self.src.index('SURYA CORE: writing'), self.src.index('core_wr_reg(gpu, g);'))

    def test_profile_and_stages(self):
        self.assertEqual(surya.gpu_core_cmdline(1), surya.APPLE_GPU_ZAP_CMDLINE + ' suryacore=1')
        with self.assertRaises(ValueError):
            surya.gpu_core_cmdline(0)
        for cmd in (surya.APPLE_GPU_PT_CMDLINE, surya.APPLE_GPU_ZAP_CMDLINE, surya.APPLE_GUI_CMDLINE):
            self.assertNotIn('suryacore', cmd)
        self.assertIn('suryacore', self.src)
        self.assertIn('PE_parse_boot_argn("suryacore"', self.src)


if __name__ == '__main__':
    unittest.main()
