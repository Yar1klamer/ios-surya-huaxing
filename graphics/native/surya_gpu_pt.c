/* Default-off XNU allocation/table test. Does not enable GPU/SMMU hardware. */
#if defined(ARM64_BOARD_CONFIG_SURYA)
#include <sys/param.h>
#include <sys/systm.h>
#include <kern/clock.h>
#include <vm/pmap.h>
#include <vm/vm_kern.h>
#include <pexpert/pexpert.h>
#include "surya_gpu_pt.h"

extern ppnum_t pmap_find_phys(pmap_t, addr64_t);
extern int hz;
void surya_gpu_pt_diagnostic(void);

static int
surya_gpu_pt_check(void)
{
    vm_offset_t tables = 0, data = 0;
    struct sgpt pt = {0};
    const uint64_t va = 0x100000000ull;
    uint64_t pa;
    int error;
    if (PAGE_SIZE != SGPT_POOL) return 1;
    if (kmem_alloc_contig(kernel_map, &tables, SGPT_POOL, PAGE_MASK, 0, 0,
        KMA_DATA | KMA_ZERO | KMA_PERMANENT, VM_KERN_MEMORY_IOKIT) != KERN_SUCCESS)
        return 2;
    if (kmem_alloc_contig(kernel_map, &data, SGPT_POOL, PAGE_MASK, 0, 0,
        KMA_DATA | KMA_ZERO | KMA_PERMANENT, VM_KERN_MEMORY_IOKIT) != KERN_SUCCESS)
        return 3;
    ppnum_t tpn = pmap_find_phys(kernel_pmap, (addr64_t)tables);
    ppnum_t dpn = pmap_find_phys(kernel_pmap, (addr64_t)data);
    if (!tpn || !dpn) return 4;
    uint64_t table_pa = ptoa_64(tpn), data_pa = ptoa_64(dpn);
    error = sgpt_init(&pt, (uint64_t *)tables, table_pa, data_pa, SGPT_POOL, va);
    if (error) return 10 + error;
    for (unsigned off = 0; off < SGPT_POOL; off += SGPT_PAGE) {
        error = sgpt_map(&pt, va + off, data_pa + off,
            SGPT_READ | SGPT_NOEXEC | (off & SGPT_PAGE ? 0 : SGPT_WRITE));
        if (error) return 20 + error;
    }
    for (unsigned off = 0; off < SGPT_POOL; ++off) {
        if (sgpt_translate(&pt, va + off, &pa) || pa != data_pa + off) return 30;
    }
    if (sgpt_map(&pt, va, data_pa, SGPT_READ) != SGPT_EXISTS) return 31;
    if (sgpt_map(&pt, va + SGPT_POOL, table_pa, SGPT_READ) != SGPT_RANGE) return 32;
    if (sgpt_translate(&pt, va + SGPT_POOL, &pa) != SGPT_UNMAPPED) return 33;
    if (sgpt_unmap(&pt, va) || sgpt_translate(&pt, va, &pa) != SGPT_UNMAPPED) return 34;
    if (sgpt_map(&pt, va, data_pa, SGPT_READ | SGPT_WRITE | SGPT_NOEXEC)) return 35;
    sgpt_seal(&pt);
    if (sgpt_unmap(&pt, va) != SGPT_SEALED ||
        sgpt_map(&pt, va, data_pa, SGPT_READ) != SGPT_SEALED) return 36;
    printf("SURYA GPU PT: private bytes=%u table bytes=%u GPU VA=%#llx\n",
        SGPT_POOL, SGPT_POOL, va);
    printf("SURYA GPU PT: CPU table walks=16384, bounds/unmap/seal checks passed\n");
    return 0;
}

void
surya_gpu_pt_diagnostic(void)
{
    int enabled = 0;
    static int wait_channel;
    extern int disableConsoleOutput, sweet_console_muted;
    (void)PE_parse_boot_argn("suryagpummu", &enabled, sizeof(enabled));
    if (enabled != 1) return;
    int result = surya_gpu_pt_check();
    for (;;) {
        disableConsoleOutput = sweet_console_muted = 0;
        printf("\nSURYA GPU PAGE TABLE DIAGNOSTIC: %s code=%d\n",
            result ? "FAIL" : "CPU TABLE TEST PASS", result);
        printf("4-KiB LPAE tables in XNU 16-KiB allocations; private mapping only\n");
        printf("GPU and SMMU hardware NOT enabled; no GPU execution tested\n");
        printf("Launchd intentionally paused. Power + Volume Down: Fastboot\n");
        (void)tsleep(&wait_channel, PZERO, "gpummutest", hz * 5);
    }
}
#endif
