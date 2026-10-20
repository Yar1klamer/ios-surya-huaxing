/* Offline ARM LPAE table test & Adreno GPU power/clock bringup diagnostic. */
#if defined(ARM64_BOARD_CONFIG_SURYA)
#include <sys/param.h>
#include <sys/systm.h>
#include <kern/clock.h>
#include <vm/pmap.h>
#include <vm/vm_kern.h>
#include <pexpert/pexpert.h>
#include "surya_gpu_pt.h"

extern ppnum_t pmap_find_phys(pmap_t, addr64_t);
extern vm_offset_t ml_io_map(vm_offset_t, vm_size_t);
extern int hz;
void surya_gpu_pt_diagnostic(void);

#define SURYA_GPUCC_PA   0x05090000u
#define SURYA_GPUCC_SIZE 0x3000u

#define SURYA_GMU_PA     0x0506a000u
#define SURYA_GMU_SIZE   0x20000u

static inline uint32_t
sgpu_rd(vm_offset_t base, uint32_t off)
{
    uint32_t v = *(volatile uint32_t *)(base + off);
    __asm__ volatile("dmb oshld" ::: "memory");
    return v;
}

static inline void
sgpu_wr(vm_offset_t base, uint32_t off, uint32_t val)
{
    __asm__ volatile("dmb oshst" ::: "memory");
    *(volatile uint32_t *)(base + off) = val;
    __asm__ volatile("dsb osh" ::: "memory");
}

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

static int
surya_gpu_power_check(uint32_t *p_cx_init, uint32_t *p_cx_on,
    uint32_t *p_ahb, uint32_t *p_gmu_clk,
    uint32_t *p_c1, uint32_t *p_c2, uint32_t *p_gx_init)
{
    vm_offset_t gpucc = ml_io_map(SURYA_GPUCC_PA, SURYA_GPUCC_SIZE);
    if (!gpucc) return 1;

    uint32_t cx_init = sgpu_rd(gpucc, 0x106c);
    *p_cx_init = cx_init;

    /* Power on CX GDSC if collapsed (clear bit 0) */
    if (cx_init & 1u) {
        sgpu_wr(gpucc, 0x106c, cx_init & ~1u);
        for (unsigned i = 0; i < 5000; ++i) {
            if (sgpu_rd(gpucc, 0x106c) & (1u << 31)) break;
            delay(1);
        }
    }
    uint32_t cx_on = sgpu_rd(gpucc, 0x106c);
    *p_cx_on = cx_on;
    if (!(cx_on & (1u << 31))) return 2; /* CX power on timeout */

    /* Enable GPU_CC_AHB_CLK (0x1078) */
    sgpu_wr(gpucc, 0x1078, sgpu_rd(gpucc, 0x1078) | 1u);
    for (unsigned i = 0; i < 5000; ++i) {
        if (!(sgpu_rd(gpucc, 0x1078) & (1u << 31))) break;
        delay(1);
    }
    *p_ahb = sgpu_rd(gpucc, 0x1078);

    /* Enable CXO AON clock (0x1004) and CXO clock (0x109c) */
    sgpu_wr(gpucc, 0x1004, sgpu_rd(gpucc, 0x1004) | 1u);
    sgpu_wr(gpucc, 0x109c, sgpu_rd(gpucc, 0x109c) | 1u);

    /* Configure CX GMU clock (0x1098) wakeup/sleep and enable */
    uint32_t gmu_cfg = (sgpu_rd(gpucc, 0x1098) & ~0xff0u) | 0xff0u | 1u;
    sgpu_wr(gpucc, 0x1098, gmu_cfg);
    for (unsigned i = 0; i < 5000; ++i) {
        if (!(sgpu_rd(gpucc, 0x1098) & (1u << 31))) break;
        delay(1);
    }
    *p_gmu_clk = sgpu_rd(gpucc, 0x1098);

    /* Read GX GDSC initial state (0x100c) */
    *p_gx_init = sgpu_rd(gpucc, 0x100c);

    /* Map GMU to read live hardware always-on counter */
    vm_offset_t gmu = ml_io_map(SURYA_GMU_PA, SURYA_GMU_SIZE);
    if (!gmu) return 3;

    /* A6XX_GMU_CX_GMU_ALWAYS_ON_COUNTER_L at GMU offset 0x14220 */
    uint32_t c1 = sgpu_rd(gmu, 0x14220);
    delay(10000); /* 10 ms wait */
    uint32_t c2 = sgpu_rd(gmu, 0x14220);
    *p_c1 = c1;
    *p_c2 = c2;

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
    int pt_res = surya_gpu_pt_check();

    uint32_t cx_init = 0, cx_on = 0, ahb = 0, gmu_clk = 0, c1 = 0, c2 = 0, gx_init = 0;
    int pwr_res = surya_gpu_power_check(&cx_init, &cx_on, &ahb, &gmu_clk, &c1, &c2, &gx_init);

    for (;;) {
        disableConsoleOutput = sweet_console_muted = 0;
        printf("\nSURYA GPU PAGE TABLE DIAGNOSTIC: %s code=%d\n",
            pt_res ? "FAIL" : "CPU TABLE TEST PASS", pt_res);
        printf("SURYA GPU POWER: %s code=%d (CX_GDSC=%#x->%#x AHB=%#x GMUCLK=%#x)\n",
            pwr_res ? "FAIL" : "PASS", pwr_res, cx_init, cx_on, ahb, gmu_clk);
        printf("SURYA GPU GMU: counter c1=%u c2=%u (delta=%u ticks) GX_GDSC=%#x\n",
            c1, c2, c2 - c1, gx_init);
        printf("Launchd intentionally paused. Power + Volume Down: Fastboot\n");
        (void)tsleep(&wait_channel, PZERO, "gpudiag", hz * 5);
    }
}
#endif
