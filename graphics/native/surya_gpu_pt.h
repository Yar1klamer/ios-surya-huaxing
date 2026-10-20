/* Offline ARM LPAE stage-1 tables for one private 2-MiB GPU VA window.
 * Three 4-KiB tables fit inside one XNU 16-KiB page. No register access,
 * allocation, cache publication or TLB invalidation is performed here.
 * Descriptor layout reference: Linux v6.12 drivers/iommu/io-pgtable-arm.c.
 * This is not a live IOMMU driver: seal before any future hardware attachment.
 */
#ifndef SURYA_GPU_PT_H
#define SURYA_GPU_PT_H
#include <stdint.h>

#define SGPT_PAGE 4096u
#define SGPT_POOL 16384u
#define SGPT_WINDOW 0x200000ull
#define SGPT_ADDR 0x0000fffffffff000ull
#define SGPT_READ 1u
#define SGPT_WRITE 2u
#define SGPT_NOEXEC 4u
#define SGPT_CACHE 8u
#define SGPT_MAIR 0xff44ull /* slot0 normal non-cacheable, slot1 WBWA */
enum { SGPT_OK, SGPT_INVALID, SGPT_RANGE, SGPT_EXISTS,
       SGPT_UNMAPPED, SGPT_SEALED, SGPT_CORRUPT };

struct sgpt {
    uint64_t *pool;
    uint64_t pool_pa, data_pa, data_size, va;
    unsigned sealed;
};

static inline int
sgpt_init(struct sgpt *s, uint64_t *pool, uint64_t pool_pa,
    uint64_t data_pa, uint64_t data_size, uint64_t va)
{
    if (s && s->sealed) return SGPT_SEALED;
    if (!s || !pool || ((uintptr_t)pool & (SGPT_PAGE - 1)) ||
        (pool_pa & (SGPT_PAGE - 1)) || (data_pa & (SGPT_PAGE - 1)) ||
        (data_size & (SGPT_PAGE - 1)) || (va & (SGPT_WINDOW - 1)))
        return SGPT_INVALID;
    if (!pool_pa || pool_pa > (1ull << 48) - SGPT_POOL ||
        !data_size || data_size > SGPT_WINDOW || !data_pa ||
        data_pa > (1ull << 48) - data_size || va > (1ull << 39) - SGPT_WINDOW ||
        (pool_pa < data_pa + data_size && data_pa < pool_pa + SGPT_POOL))
        return SGPT_RANGE;
    for (unsigned i = 0; i < SGPT_POOL / sizeof(uint64_t); ++i) pool[i] = 0;
    s->pool = pool;
    s->pool_pa = pool_pa;
    s->data_pa = data_pa;
    s->data_size = data_size;
    s->va = va;
    s->sealed = 0;
    pool[(va >> 30) & 511] = (pool_pa + SGPT_PAGE) | 3;
    pool[512 + ((va >> 21) & 511)] = (pool_pa + 2 * SGPT_PAGE) | 3;
    return SGPT_OK;
}

static inline int
sgpt_slot(const struct sgpt *s, uint64_t va, unsigned *slot)
{
    if (!s || !s->pool || !slot) return SGPT_INVALID;
    if (va < s->va || va - s->va >= SGPT_WINDOW) return SGPT_RANGE;
    if (s->pool[(va >> 30) & 511] != ((s->pool_pa + SGPT_PAGE) | 3) ||
        s->pool[512 + ((va >> 21) & 511)] != ((s->pool_pa + 2 * SGPT_PAGE) | 3))
        return SGPT_CORRUPT;
    *slot = 1024 + (unsigned)((va >> 12) & 511);
    return SGPT_OK;
}

static inline int
sgpt_map(struct sgpt *s, uint64_t va, uint64_t pa, unsigned flags)
{
    unsigned slot;
    int error;
    if (!s || !s->pool) return SGPT_INVALID;
    if (s->sealed) return SGPT_SEALED;
    if ((va & (SGPT_PAGE - 1)) || (pa & (SGPT_PAGE - 1)) ||
        !(flags & SGPT_READ) || (flags & ~15u)) return SGPT_INVALID;
    if (pa < s->data_pa || pa - s->data_pa >= s->data_size) return SGPT_RANGE;
    error = sgpt_slot(s, va, &slot);
    if (error) return error;
    if (s->pool[slot]) return SGPT_EXISTS;
    uint64_t bits = 3ull | (1ull << 6) | (1ull << 10) | (1ull << 11);
    if (!(flags & SGPT_WRITE)) bits |= 1ull << 7;
    if (flags & SGPT_NOEXEC) bits |= 3ull << 53;
    bits |= flags & SGPT_CACHE ? ((3ull << 8) | (1ull << 2)) : (2ull << 8);
    s->pool[slot] = pa | bits;
    return SGPT_OK;
}

static inline int
sgpt_translate(const struct sgpt *s, uint64_t va, uint64_t *pa)
{
    unsigned slot;
    if (!pa) return SGPT_INVALID;
    int error = sgpt_slot(s, va, &slot);
    if (error) return error;
    uint64_t pte = s->pool[slot];
    if (!pte) return SGPT_UNMAPPED;
    uint64_t base = pte & SGPT_ADDR;
    const uint64_t allowed = SGPT_ADDR | (3ull << 53) | (1ull << 11) |
        (1ull << 10) | (3ull << 8) | (3ull << 6) | (1ull << 2) | 3;
    if ((pte & ~allowed) || (pte & 3) != 3 || !(pte & (1ull << 10)) ||
        !(pte & (1ull << 6)) ||
        base < s->data_pa || base - s->data_pa >= s->data_size)
        return SGPT_CORRUPT;
    *pa = base | (va & (SGPT_PAGE - 1));
    return SGPT_OK;
}

static inline int
sgpt_unmap(struct sgpt *s, uint64_t va)
{
    unsigned slot;
    if (!s || !s->pool || (va & (SGPT_PAGE - 1))) return SGPT_INVALID;
    if (s->sealed) return SGPT_SEALED;
    int error = sgpt_slot(s, va, &slot);
    if (error) return error;
    if (!s->pool[slot]) return SGPT_UNMAPPED;
    s->pool[slot] = 0;
    return SGPT_OK;
}

static inline int sgpt_seal(struct sgpt *s) {
    if (!s || !s->pool) return SGPT_INVALID;
    s->sealed = 1;
    return SGPT_OK;
}
#endif
