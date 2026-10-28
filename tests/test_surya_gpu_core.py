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
CP_START = {0x2000, 0x2008, 0x2010, 0x201c, 0x2020, 0x20c0, 0x3d000}


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


def parity(v):
    """Linux adreno_gpu.h PM4_PARITY."""
    return (0x9669 >> (0xf & (v ^ (v >> 4) ^ (v >> 8) ^ (v >> 12) ^ (v >> 16) ^ (v >> 20) ^ (v >> 24) ^ (v >> 28)))) & 1


def pkt7(opcode, count):
    return (7 << 28) | count | (parity(count) << 15) | ((opcode & 0x7f) << 16) | (parity(opcode) << 23)


def added2():
    text = (ROOT / 'xnu/patches/0101-surya-gpu-core-stage2.patch').read_text()
    return chr(10).join(l[1:] for l in text.splitlines() if l.startswith('+') and not l.startswith('+++'))


class GpuCoreStage2Tests(unittest.TestCase):
    def setUp(self):
        self.src = added2()

    def test_pkt7_header_matches_linux(self):
        # CP_ME_INIT (0x48) with 8 payload dwords: the header the Linux driver puts in the ring
        self.assertEqual(pkt7(0x48, 8), 0x70c80008)
        self.assertIn('(7u << 28) | count | (pm4_parity(count) << 15) | ((opcode & 0x7fu) << 16) | (pm4_parity(opcode) << 23)', self.src)

    def test_ring_control_value_is_msm_gpu_rb_cntl_default_with_no_update(self):
        # BUFSZ = log2(32 KiB / 8) = 12, BLKSZ = log2(32 / 8) = 2 (bits 13:8), NO_UPDATE = bit 27
        self.assertEqual((12 | (2 << 8) | (1 << 27)), 0x0800020c)
        self.assertIn('#define RB_CNTL_VALUE   (12u | (2u << 8) | (1u << 27))', self.src)

    def test_cp_registers_are_linuxs_offsets(self):
        for name, off in (('CP_RB_BASE', 0x2000), ('CP_RB_CNTL', 0x2008), ('CP_RB_RPTR', 0x2018), ('CP_RB_WPTR', 0x201c),
                          ('CP_SQE_CNTL', 0x2020), ('CP_HW_FAULT', 0x2084),
                          ('CP_INTERRUPT_STATUS', 0x208c), ('RBBM_INT_0_STATUS', 0x804), ('RBBM_STATUS', 0x840)):
            self.assertRegex(self.src, r'#define %s\s+%#x' % (name, off), name)

    def test_stream_match_is_the_device_trees(self):
        # kgsl gfx3d_user: iommus = <&kgsl_smmu 0x0 0x401>; S2CR first (translate, bank 0), then the match register
        self.assertIn('(1u << 31) | (0x401u << 16) | (uint32_t)SURYA_DT_USER_SID', self.src)
        self.assertLess(self.src.index('smmu + 0xc00) = 0;'), self.src.index('smmu + 0x800) ='))

    def test_ordering_in_the_core_stage(self):
        order = [self.src.index(m) for m in ('ArmSmmu4KProgramDisabledContext', 'smmu + 0xc00) = 0;', 'core_wr64(gpu, CP_SQE_INSTR_BASE',
                                              'core_wr(gpu, CP_SQE_CNTL, 1);', 'core_wr(gpu, CP_RB_WPTR, n);')]
        self.assertEqual(order, sorted(order))
        # the zap shader is not part of this stage and the CP is stopped again afterwards
        self.assertNotIn('surya_zap_load', self.src)
        self.assertIn('core_wr(gpu, CP_SQE_CNTL, 0);', self.src)

    def test_sqe_microcode_contract_and_profile(self):
        import surya_sqe_firmware as sqe
        with self.assertRaises(ValueError):
            sqe.validate(bytes(sqe.SIZE))
        self.assertEqual(surya.gpu_core_cmdline(2), surya.APPLE_GPU_ZAP_CMDLINE + ' suryacore=2')
        self.assertIn(surya.gpu_core_cmdline(2), surya.APPLE_GPU_CORE_CMDLINES)
        self.assertIn('sqe_size - 4', self.src)     # the microcode goes to the GPU without its first dword
        fw = ROOT / 'research' / 'macos-bundle' / 'fw' / 'a630_sqe.fw'
        alt = ROOT / 'research' / 'live-surya-android' / 'fw' / 'a630_sqe.fw'
        path = fw if fw.exists() else alt
        if path.exists():
            sqe.validate(path.read_bytes())


class GpuCoreLeafBudgetTests(unittest.TestCase):
    def test_leaf_budget_is_the_whole_buffer_in_4k_pages(self):
        # patch 0102: ArmSmmu4KConfig's 4th member is the leaf-page budget, not a table-page count (0101 passed 4 for 128 KiB: Budget error)
        text = (ROOT / 'xnu/patches/0102-surya-gpu-core-leaf-budget.patch').read_text()
        added = chr(10).join(l[1:] for l in text.splitlines() if l.startswith('+') and not l.startswith('+++'))
        self.assertIn('ArmSmmu4KConfig config = {39, 36, tables_pa, G3_BYTES / 4096};', added)
        self.assertIn('s2_code', added)


class GpuCoreSmrProbeTests(unittest.TestCase):
    def setUp(self):
        text = (ROOT / 'xnu/patches/0103-surya-gpu-core-smr-probe.patch').read_text()
        self.src = chr(10).join(l[1:] for l in text.splitlines() if l.startswith('+') and not l.startswith('+++'))

    def test_widths_are_probed_with_the_valid_bit_clear_before_the_real_write(self):
        # 0102's run: SMR0 written 0x84010000 read back 0 (this SMMU has 3 stream-id bits, 5 groups); Linux probes the widths first
        probe_id = self.src.index('= 0x7fffu;')
        probe_mask = self.src.index('= 0x7fffu << 16;')
        real = self.src.index('= want_smr;')
        self.assertLess(probe_id, probe_mask)
        self.assertLess(probe_mask, real)
        self.assertNotIn('(1u << 31) | 0x7fff', self.src)       # the probes never set the valid bit
        self.assertIn('0x401u & r->smr_maskmask', self.src)     # the DT mask, cut to the implemented bits

    def test_report_carries_the_groups_and_widths(self):
        for name in ('smr_idmask', 'smr_maskmask', 'smr_want', 'smr_init', 's2cr_init', 'gfsr', 'scr1'):
            self.assertIn(name, self.src)


class GpuCoreSmrShapesTests(unittest.TestCase):
    def setUp(self):
        text = (ROOT / 'xnu/patches/0104-surya-gpu-core-smr-shapes.patch').read_text()
        self.src = chr(10).join(l[1:] for l in text.splitlines() if l.startswith('+') and not l.startswith('+++'))

    def test_match_is_cut_to_numsidb_bits(self):
        # 0103's run: SMR0 valid|mask 0x401 was dropped (ID0 = 0x48016605: NUMSIDB = 3, mask bit 10 is out of range)
        self.assertEqual((0x48016605 >> 9) & 0xf, 3)
        self.assertIn('(u->id0 >> 9) & 0xfu', self.src)
        self.assertIn('(0x401u & sid_mask) << 16', self.src)
        # the DT's own value stays last, as a control
        self.assertLess(self.src.index('(0x401u & sid_mask) << 16'), self.src.index('(0x401u << 16) | sid'))

    def test_failed_entries_are_left_invalid_and_every_try_is_reported(self):
        self.assertIn('leave the entry invalid', self.src)
        self.assertIn('r->tries[r->ntries].read = smr;', self.src)
        self.assertIn('try %u: group %u wrote SMR', self.src)
        self.assertIn('GFSR', self.src)

    def test_stage_stops_with_7_when_no_shape_holds(self):
        self.assertIn('if (r->attach_slot < 0) {', self.src)   # the stop-7 return after it is unchanged context


class GpuCoreSmrExperimentsTests(unittest.TestCase):
    def setUp(self):
        text = (ROOT / 'xnu/patches/0105-surya-gpu-core-smr-experiments.patch').read_text()
        self.src = chr(10).join(l[1:] for l in text.splitlines() if l.startswith('+') and not l.startswith('+++'))

    def test_each_hypothesis_has_its_experiment(self):
        for tag in ('dive_fault_valid', 'dive_smr_first', 'dive_late', 'dive_wide', 'dive_bypass'):
            self.assertIn(tag, self.src)

    def test_experiments_touch_group_zero_only_and_leave_it_as_found(self):
        body = self.src[self.src.index('smr_dive(vm_offset_t smmu'):self.src.index('r->gfsr_after = smmu_r(smmu, 0x48);')]
        self.assertIn('const uint32_t smr = 0x800, s2cr = 0xc00;', body)        # group 0's registers, no slot arithmetic
        self.assertNotIn('4 * ', body)
        tail = body[body.rindex('smmu_w(smmu, s2cr, 0x20000);'):]
        self.assertIn('smmu_w(smmu, smr, 0);', tail)                                # S2CR fault, SMR invalid: as found

    def test_run_only_when_no_shape_was_taken(self):
        full = (ROOT / 'xnu/patches/0105-surya-gpu-core-smr-experiments.patch').read_text()   # the guard line is diff context
        self.assertLess(full.index('if (r->attach_slot < 0) {'), full.index('smr_dive(smmu, r);'))


class GpuCoreCatchPageTests(unittest.TestCase):
    def setUp(self):
        text = (ROOT / 'xnu/patches/0106-surya-gpu-core-catch-page.patch').read_text()
        self.src = chr(10).join(l[1:] for l in text.splitlines() if l.startswith('+') and not l.startswith('+++'))

    def test_catch_page_at_iova_zero_sorted_before_the_buffer(self):
        # 0105's run: translation fault at FAR=0; the library wants sorted ranges, so the catch at 0 comes first
        self.assertIn('{0, buf_cpa, CATCH_BYTES, ArmSmmu4KRead | ArmSmmu4KWrite, 0, 2},', self.src)
        self.assertLess(self.src.index('{0, buf_cpa, CATCH_BYTES'), self.src.index('{G3_IOVA, buf_pa, G3_BYTES'))
        self.assertIn('ArmSmmu4KBuild(&config, ranges, 2,', self.src)
        # leaf budget covers both ranges (the 4th member is a leaf count, see 0102)
        self.assertIn('(CATCH_BYTES + G3_BYTES) / 4096', self.src)

    def test_catch_pattern_and_report(self):
        self.assertIn('#define CATCH_PATTERN   0xdeadbeefu', self.src)
        for name in ('catch_hits', 'fsr_start', 'cb_fsynr0', 'cb_fsynr1', 'gfsr_end', 'scratch0', 'CP_RB_RPTR_ADDR'):
            self.assertIn(name, self.src)

    def test_rptr_shadow_address_is_a_mapped_page_and_set_before_the_start(self):
        self.assertIn('core_wr64(gpu, CP_RB_RPTR_ADDR, G3_IOVA + G3_SCRATCH_OFF);', self.src)
        # the CP start line itself is unchanged diff context; the start-up probe right after it is added text
        self.assertLess(self.src.index('core_wr64(gpu, CP_RB_RPTR_ADDR'), self.src.index('r->fsr_start ='))

    def test_startup_state_is_read_before_any_command(self):
        self.assertLess(self.src.index('r->fsr_start ='), self.src.index('r->cb_fsynr0 ='))


if __name__ == '__main__':
    unittest.main()


class GpuCoreSqeBaseRegisterTests(unittest.TestCase):
    """0107: CP_SQE_INSTR_BASE is dword 0x830 (byte 0x20c0) on A6xx (mesa a6xx.xml); 0x2058 is the A8XX register."""

    def setUp(self):
        self.text = (ROOT / 'xnu/patches/0107-surya-gpu-core-sqe-base-register.patch').read_text(encoding='utf-8')

    def test_register_moved_from_a8xx_offset_to_a6xx_offset(self):
        self.assertEqual(0x830 * 4, 0x20c0)
        self.assertIn('-#define CP_SQE_INSTR_BASE 0x2058u', self.text)
        self.assertIn('+#define CP_SQE_INSTR_BASE 0x20c0u', self.text)


class GpuCoreAllUserStreamsTests(unittest.TestCase):
    """0108: ids 1, 0x400, 0x401 attached with exact SMR entries (a mask is dropped); progress printed around the CP start."""

    def setUp(self):
        text = (ROOT / 'xnu/patches/0108-surya-gpu-core-all-user-streams-and-progress.patch').read_text(encoding='utf-8')
        self.src = chr(10).join(l[1:] for l in text.splitlines() if l.startswith('+') and not l.startswith('+++'))

    def test_exact_entries_for_the_other_user_stream_ids(self):
        self.assertIn('{ 1u, 0x400u, 0x401u }', self.src)
        self.assertIn('(1u << 31) | more[m]', self.src)
        self.assertNotIn('<< 16', self.src)

    def test_progress_is_printed_between_the_cp_start_and_each_read(self):
        order = [self.src.index(m) for m in ('CP_SQE_CNTL written', 'reading the SMMU fault registers', 'reading RBBM_STATUS', 'RBBM_STATUS %#x')]
        self.assertEqual(order, sorted(order))


class GpuCorePreRingErrorStateTests(unittest.TestCase):
    """0109: CP_INT/HW_FAULT/INT0 read after the CP start and before the ring is fed (0108 saw CP_INT=0x80, ILLEGAL_INSTR)."""

    def setUp(self):
        text = (ROOT / 'xnu/patches/0109-surya-gpu-core-pre-ring-error-state.patch').read_text(encoding='utf-8')
        self.src = chr(10).join(l[1:] for l in text.splitlines() if l.startswith('+') and not l.startswith('+++'))

    def test_error_registers_are_read_before_the_write_pointer_is_written(self):
        self.assertIn('r->pre_cp_int = core_rd(gpu, CP_INTERRUPT_STATUS);', self.src)
        self.assertIn('r->pre_hw_fault = core_rd(gpu, CP_HW_FAULT);', self.src)

    def test_extra_streams_reach_the_final_report(self):
        self.assertIn('extra user streams attached', self.src)
        self.assertIn('SURYA CORE2: extra stream %#x: SMR %#x S2CR %#x', self.src)


class GpuCoreKeepZapTests(unittest.TestCase):
    """0110: KGSL/Linux start the CP with the zap shader authenticated, then CP_SET_SECURE_MODE 0; 0099's final SHUTDOWN is skipped."""

    def setUp(self):
        text = (ROOT / 'xnu/patches/0110-surya-gpu-core-keep-zap-secure-mode-off.patch').read_text(encoding='utf-8')
        self.src = chr(10).join(l[1:] for l in text.splitlines() if l.startswith('+') and not l.startswith('+++'))

    def test_zap_is_kept_when_the_cp_stage_runs(self):
        self.assertIn('surya_zap_keep = core_stage_early >= 2;', self.src)
        self.assertIn('if (surya_zap_keep) {', self.src)
        self.assertIn('extern int surya_zap_keep;', self.src)

    def test_secure_mode_is_left_with_set_secure_mode_zero(self):
        self.assertEqual(0x66, 0x66)
        self.assertIn('ring[n++] = pkt7(0x66, 1);', self.src)
