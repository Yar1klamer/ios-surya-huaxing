/*
 * Just enough flattened-device-tree parsing to find what ABL put in
 * /chosen (initrd location). Big-endian, 4-byte aligned tokens.
 */
#include "fdt.h"

#define FDT_MAGIC	0xd00dfeed
#define FDT_BEGIN_NODE	1
#define FDT_END_NODE	2
#define FDT_PROP	3
#define FDT_NOP		4
#define FDT_END		9

static uint32_t be32(uintptr_t a)
{
	return __builtin_bswap32(*(volatile uint32_t *)a);
}

static int streq(const char *a, const char *b)
{
	while (*a && *a == *b)
		a++, b++;
	return *a == *b;
}

static uintptr_t align4(uintptr_t a)
{
	return (a + 3) & ~3UL;
}

static uintptr_t skip_str(uintptr_t p)
{
	/* byte loads are fine on Device memory as long as they are aligned to 1 */
	while (*(volatile char *)p)
		p++;
	return p + 1;
}

int fdt_chosen_u64(uintptr_t fdt, const char *prop, uint64_t *out)
{
	if (!fdt || be32(fdt) != FDT_MAGIC)
		return 0;
	uintptr_t p = fdt + be32(fdt + 8);		/* off_dt_struct */
	uintptr_t strings = fdt + be32(fdt + 12);	/* off_dt_strings */
	int depth = 0, in_chosen = 0;

	for (;;) {
		uint32_t tok = be32(p);
		p += 4;
		switch (tok) {
		case FDT_BEGIN_NODE: {
			const char *name = (const char *)p;
			depth++;
			in_chosen = depth == 2 && streq(name, "chosen");
			p = align4(skip_str(p));
			break;
		}
		case FDT_END_NODE:
			if (in_chosen)
				return 0;
			depth--;
			break;
		case FDT_PROP: {
			uint32_t len = be32(p), nameoff = be32(p + 4);
			uintptr_t val = p + 8;
			if (in_chosen && streq((const char *)(strings + nameoff), prop)) {
				if (len == 4)
					*out = be32(val);
				else if (len == 8)
					*out = (uint64_t)be32(val) << 32 | be32(val + 4);
				else
					return 0;
				return 1;
			}
			p = align4(val + len);
			break;
		}
		case FDT_NOP:
			break;
		default:	/* FDT_END or garbage */
			return 0;
		}
	}
}

static uint64_t be64(uintptr_t a)
{
	return (uint64_t)be32(a) << 32 | be32(a + 4);
}

static int overlaps(uint64_t a, uint64_t n, uint64_t b, uint64_t m)
{
	return n && m && (a < b ? n > b - a : m > a - b);
}

static int bounded_string(uintptr_t p, uintptr_t end)
{
	while (p < end) {
		if (!*(volatile char *)p++)
			return 1;
	}
	return 0;
}

int fdt_check_ram(uintptr_t fdt, uint64_t start, uint64_t size)
{
	if (!fdt || !size || size > UINT64_MAX - start || be32(fdt) != FDT_MAGIC)
		return -1;
	uint32_t total = be32(fdt + 4), so = be32(fdt + 8),
	    strings_off = be32(fdt + 12), reserve_off = be32(fdt + 16),
	    strings_size = be32(fdt + 32), struct_size = be32(fdt + 36);
	if (total < 56 || total > (16u << 20) || so < 40 || (so & 3) ||
	    so > total || struct_size > total - so || strings_off > total ||
	    strings_size > total - strings_off || reserve_off < 40 ||
	    (reserve_off & 7) || reserve_off > total - 16)
		return -1;
	/* The header reservation map is separate from /reserved-memory. */
	uint32_t r = reserve_off;
	for (;;) {
		if (r > total - 16)
			return -1;
		uint64_t a = be64(fdt + r), n = be64(fdt + r + 8);
		if (!a && !n)
			break;
		if (overlaps(start, size, a, n))
			return -2;
		r += 16;
	}
	uintptr_t p = fdt + so, end = p + struct_size,
	    strings = fdt + strings_off, strings_end = strings + strings_size;
	unsigned depth = 0, address_cells = 2, size_cells = 1;
	int memory = 0, reserved = 0, covered = 0;
	while (p + 4 <= end) {
		uint32_t tok = be32(p);
		p += 4;
		if (tok == FDT_BEGIN_NODE) {
			if (!bounded_string(p, end) || ++depth > 64)
				return -1;
			const char *name = (const char *)p;
			if (depth == 2) {
				memory = streq(name, "memory") ||
				    (name[0] == 'm' && name[1] == 'e' && name[2] == 'm' &&
				     name[3] == 'o' && name[4] == 'r' && name[5] == 'y' && name[6] == '@');
				reserved = streq(name, "reserved-memory");
			}
			p = align4(skip_str(p));
		} else if (tok == FDT_END_NODE) {
			if (!depth)
				return -1;
			if (depth == 2)
				memory = reserved = 0;
			depth--;
		} else if (tok == FDT_PROP) {
			if (p + 8 > end)
				return -1;
			uint32_t len = be32(p), no = be32(p + 4);
			p += 8;
			if (len > (uint64_t)(end - p) || no >= strings_size ||
			    !bounded_string(strings + no, strings_end))
				return -1;
			const char *name = (const char *)(strings + no);
			if (streq(name, "#address-cells") || streq(name, "#size-cells")) {
				if (depth == 1 || (depth == 2 && reserved)) {
					if (len != 4 || be32(p) != 2)
						return -1; /* SM7150 ABI: 64-bit address and size */
					if (depth == 1) {
						if (name[1] == 'a') address_cells = 2;
						else size_cells = 2;
					}
				}
			} else if (streq(name, "reg") &&
			    ((depth == 2 && memory) || (depth == 3 && reserved))) {
				if (address_cells != 2 || size_cells != 2 || (len & 15))
					return -1;
				for (uint32_t i = 0; i < len; i += 16) {
					uint64_t a = be64(p + i), n = be64(p + i + 8);
					if (depth == 2 && start >= a && start - a <= n && size <= n - (start - a))
						covered = 1;
					if (depth == 3 && overlaps(start, size, a, n))
						return -2;
				}
			}
			p = align4(p + len);
		} else if (tok == FDT_END) {
			return depth == 0 ? covered : -1;
		} else if (tok != FDT_NOP) {
			return -1;
		}
	}
	return -1;
}
