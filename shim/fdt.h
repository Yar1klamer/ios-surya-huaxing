#pragma once
#include <stdint.h>

/* Read a u32/u64 (cell-size agnostic) property of /chosen. Returns 0 if absent. */
int fdt_chosen_u64(uintptr_t fdt, const char *prop, uint64_t *out);
/* 1: range is RAM and outside fixed reservations; 0: not covered;
 * -1: invalid/unsupported FDT; -2: overlaps a fixed reservation. */
int fdt_check_ram(uintptr_t fdt, uint64_t start, uint64_t size);
