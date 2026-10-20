/* SURYA bridge to pinned UniXNU ArmSmmu4K, before live context attachment.
 * Only the documented GPU MEMNOC clock may be enabled. SMMU registers are
 * read only; TTBR/SCTLR/streams/TLBs are never written by this diagnostic.
 */
#if defined(ARM64_BOARD_CONFIG_SURYA)
#include <sys/param.h>
#include <sys/systm.h>
#include <kern/clock.h>
#include <vm/pmap.h>
#include <vm/vm_kern.h>
#include "surya_unixnu_smmu.h"

extern vm_offset_t ml_io_map(vm_offset_t, vm_size_t);
extern ppnum_t pmap_find_phys(pmap_t, addr64_t);

static uint32_t read32(vm_offset_t base, unsigned off)
{
    uint32_t value = *(volatile uint32_t *)(base + off);
    __asm__ volatile("dmb oshld" ::: "memory");
    return value;
}

static int private_tables(struct surya_unixnu_smmu_report *r)
{
    vm_offset_t tables = 0, data = 0;
    if (PAGE_SIZE != 16384) return 100;
    if (kmem_alloc_contig(kernel_map, &tables, 16384, PAGE_MASK, 0, 0,
        KMA_DATA | KMA_ZERO | KMA_PERMANENT, VM_KERN_MEMORY_IOKIT) != KERN_SUCCESS)
        return 101;
    if (kmem_alloc_contig(kernel_map, &data, 16384, PAGE_MASK, 0, 0,
        KMA_DATA | KMA_ZERO | KMA_PERMANENT, VM_KERN_MEMORY_IOKIT) != KERN_SUCCESS)
        return 102;
    ppnum_t tp = pmap_find_phys(kernel_pmap, (addr64_t)tables);
    ppnum_t dp = pmap_find_phys(kernel_pmap, (addr64_t)data);
    if (!tp || !dp) return 103;
    const uint64_t physical = ptoa_64(tp), data_physical = ptoa_64(dp);
    const uint64_t iova = UINT64_C(0x100000000);
    ArmSmmu4KConfig config = {39, 36, physical, 4};
    ArmSmmu4KRange range = {iova, data_physical, 16384,
        ArmSmmu4KRead | ArmSmmu4KWrite, 0, 2};
    ArmSmmu4KResult built = {0};
    ArmSmmu4KStatus status = ArmSmmu4KBuild(&config, &range, 1,
        (uint64_t *)tables, 4, &built);
    if (status) return status;
    r->table_pages = (unsigned)built.table_pages;
    r->leaves = (unsigned)built.leaf_pages;
    /* Independent CPU walk over the actual newly allocated descriptors. */
    for (unsigned off = 0; off < 16384; ++off) {
        uint64_t table = physical, descriptor = 0;
        for (unsigned shift = 30; ; shift -= 9) {
            if (table < physical || table - physical >= 16384 || (table & 4095))
                return 104;
            descriptor = ((uint64_t *)tables)[(table - physical) / 8 +
                (((iova + off) >> shift) & 511)];
            if ((descriptor & 3) != 3) return 105;
            if (shift == 12) break;
            table = descriptor & UINT64_C(0x0000fffffffff000);
        }
        if ((descriptor & UINT64_C(0x0000fffffffff000)) + (off & 4095) !=
            data_physical + off) return 106;
    }
    ArmSmmu4KContextConfig context = {0};
    context.lower = &config;
    context.lower_tables = &built;
    context.id0 = r->id0; context.id2 = r->id2;
    context.asid = 1; /* hypothetical image only; no ASID is claimed */
    context.stall_on_fault = 1;
    ArmSmmu4KContextImage image = {0};
    return ArmSmmu4KEncodeContext(&context, &image);
}

void
surya_unixnu_smmu_capture(struct surya_unixnu_smmu_report *r)
{
    *r = (struct surya_unixnu_smmu_report){0};
    r->stage = 1;
    /* MiCode gcc-sm6150.c: gcc_gpu_memnoc_gfx_clk, enable/halt 0x7100c.
     * DT provider is GCC at 0x100000; caller already verified CX/GX powered. */
    vm_offset_t gcc = ml_io_map(0x171000, 0x1000);
    if (!gcc) {r->code = 1; return;}
    r->memnoc_before = read32(gcc, 0xc);
    if (r->memnoc_before == UINT32_MAX || r->memnoc_before == 0xdeafbead) {
        r->code = 2; return;
    }
    __asm__ volatile("dmb oshst" ::: "memory");
    *(volatile uint32_t *)(gcc + 0xc) = r->memnoc_before | 1u;
    __asm__ volatile("dsb osh" ::: "memory");
    for (unsigned i = 0; i < 5000; ++i) {
        r->memnoc_after = read32(gcc, 0xc);
        if (!(r->memnoc_after & (1u << 31))) break;
        delay(1);
    }
    if (r->memnoc_after & (1u << 31)) {r->code = 3; return;}
    r->stage = 2;
    vm_offset_t smmu = ml_io_map(0x05040000, 0x10000);
    if (!smmu) {r->code = 4; return;}
    r->id0 = read32(smmu, 0x20); r->id1 = read32(smmu, 0x24);
    r->id2 = read32(smmu, 0x28); r->scr0 = read32(smmu, 0);
    if (surya_unixnu_cb0(r->id1, 0x10000, &r->cb_offset)) {
        r->code = 5; return;
    }
    r->stage = 3;
    r->cb_sctlr = read32(smmu, r->cb_offset);
    r->cb_fsr = read32(smmu, r->cb_offset + 0x58);
    r->cb_tcr = read32(smmu, r->cb_offset + 0x30);
    r->cb_ttbr0 = *(volatile uint64_t *)(smmu + r->cb_offset + 0x20);
    __asm__ volatile("dmb oshld" ::: "memory");
    r->stage = 4;
    r->code = private_tables(r);
    if (!r->code) r->stage = 5;
}
#endif
