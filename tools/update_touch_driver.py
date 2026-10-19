import sys
from pathlib import Path

# Paths
root = Path(__file__).resolve().parents[1]
target_src = root / 'research' / 'xnu-port' / 'bsd' / 'dev' / 'sweet_touch.c'
base_xnu_src = root / 'research' / 'ci-surya-first-tree' / 'extracted' / 'xnu' / 'bsd' / 'dev' / 'sweet_touch.c'
patch_out = root / 'xnu' / 'patches' / '0087-surya-touch-novatek-spi.patch'

orig = target_src.read_text(encoding='utf-8')
split_marker = '#if defined(ARM64_BOARD_CONFIG_SURYA)\n'
prefix = orig[:orig.find(split_marker)]
suffix_marker = 'void\nsweet_touch_init(void)\n'
suffix = orig[orig.find(suffix_marker):]

surya_code = """#if defined(ARM64_BOARD_CONFIG_SURYA)
/* ---- Physical addresses (from stock surya DTB and Linux SM7150) ---- */
#define SURYA_SE0_PA        0x00880000u   /* GENI SE0 SPI master        */
#define SURYA_GCC_PA        0x00100000u   /* GCC clock controller       */
#define SURYA_TLMM_W_PA     0x03500000u   /* TLMM West (pins 49-52 SPI) */
#define SURYA_TLMM_W_SIZE   0x00040000u
#define SURYA_TLMM_N_PA     0x03900000u   /* TLMM North (pins 8, 9 RST/IRQ) */
#define SURYA_TLMM_N_SIZE   0x00010000u

/* GCC offsets for QUPV3 wrapper0 / SE0 */
#define SURYA_GCC_VOTE      0x5200cu      /* QUPV3 wrapper0 vote        */
#define SURYA_RCG           0x17034u      /* wrapper0 LOCAL S0 RCG CMD  */

/* GPIO helpers (one page per pin) */
#define SGPIO_CFG(n)  ((uint32_t)(n) * 0x1000u)
#define SGPIO_IO(n)   (SGPIO_CFG(n) + 4u)

/* GENI SE register aliases */
#define SSE_STATUS      0x040u
#define SSE_MCLK        0x048u
#define SSE_FW          0x068u
#define SSE_CLK_SEL     0x07cu
#define SSE_DMA         0x258u
#define SSE_TX_LEN      0x26cu
#define SSE_RX_LEN      0x270u
#define SSE_CMD         0x600u
#define SSE_CTRL        0x604u
#define SSE_IRQ         0x610u
#define SSE_IRQ_EN      0x614u
#define SSE_IRQ_CLR     0x618u
#define SSE_TX          0x700u
#define SSE_RX          0x780u
#define SSE_TX_COUNT    0x800u
#define SSE_RX_COUNT    0x804u
#define SSE_HW_TX       0xe24u
#define SSE_HW_RX       0xe28u
#define SSE_DONE        (1u << 0)
#define SSE_ERRORS      (0x0eu | (1u << 9) | (1u << 10) | (1u << 12) | \\
                         (1u << 13) | (3u << 24) | (3u << 28))
#define SSE_EVENTS      (SSE_DONE | SSE_ERRORS | (1u << 26) | (1u << 27) | (1u << 30))

/* Novatek NT36672C protocol constants (from stock surya kernel nt36xxx disassembly) */
#define NVT_MAX_FINGERS     10u
#define NVT_WIDTH           1080
#define NVT_HEIGHT          2400

static struct {
	vm_offset_t se, gcc, tlmm_w, tlmm_n;
	bool started, dead;
	uint32_t active;
	int x[NVT_MAX_FINGERS], y[NVT_MAX_FINGERS];
} sst;
static int surya_touch_sleep_chan;

static inline uint32_t
surya_touch_rd(vm_offset_t base, uint32_t off)
{
	uint32_t v = *(volatile uint32_t *)(base + off);
	__asm__ volatile("dmb oshld" ::: "memory");
	return v;
}

static inline void
surya_touch_wr(vm_offset_t base, uint32_t off, uint32_t val)
{
	__asm__ volatile("dmb oshst" ::: "memory");
	*(volatile uint32_t *)(base + off) = val;
	__asm__ volatile("dsb osh" ::: "memory");
}

static void
surya_touch_wait(unsigned ms)
{
	uint64_t deadline;
	clock_interval_to_deadline(ms, NSEC_PER_MSEC, &deadline);
	(void)assert_wait_deadline(&surya_touch_sleep_chan, THREAD_UNINT, deadline);
	thread_block(THREAD_CONTINUE_NULL);
}

static bool
surya_touch_wait_clear(vm_offset_t base, uint32_t off, uint32_t mask)
{
	unsigned i;
	for (i = 0; i < 5000; ++i) {
		if (!(surya_touch_rd(base, off) & mask)) {
			return true;
		}
		delay(1);
	}
	return false;
}

static void
surya_touch_gpio(vm_offset_t gbase, unsigned pin, unsigned mux, unsigned pull,
    unsigned drive, bool out)
{
	uint32_t off = SGPIO_CFG(pin);
	uint32_t cfg = surya_touch_rd(gbase, off);
	if (out) {
		surya_touch_wr(gbase, SGPIO_IO(pin), surya_touch_rd(gbase, SGPIO_IO(pin)) | 2u);
	}
	cfg &= ~0x3ffu;
	cfg |= (mux << 2) | pull | (drive << 6) | (out ? 0x200u : 0u);
	surya_touch_wr(gbase, off, cfg);
}

static void
surya_touch_gpio_out(vm_offset_t gbase, unsigned pin, bool high)
{
	uint32_t io = surya_touch_rd(gbase, SGPIO_IO(pin));
	if (high) {
		io |= 2u;
	} else {
		io &= ~2u;
	}
	surya_touch_wr(gbase, SGPIO_IO(pin), io);
}

static bool
surya_touch_gpio_in(vm_offset_t gbase, unsigned pin)
{
	return !!(surya_touch_rd(gbase, SGPIO_IO(pin)) & 1u);
}

static bool
surya_touch_clocks(void)
{
	uint32_t mask;
	uint32_t dfs;
	uint32_t cfg;
	unsigned i;
	const uint32_t branches[] = {0x17004, 0x17008, 0x1700c, 0x17014, 0x17030};

	mask = (1u << 6) | (1u << 7) | (1u << 8) | (1u << 9) | (1u << 10);
	surya_touch_wr(sst.gcc, SURYA_GCC_VOTE, surya_touch_rd(sst.gcc, SURYA_GCC_VOTE) | mask);

	dfs = surya_touch_rd(sst.gcc, SURYA_RCG + 0x14u);
	cfg = surya_touch_rd(sst.gcc, SURYA_RCG + 4u);
	printf("SURYA TOUCH: gcc vote=%#x rcg=%#x cfg=%#x dfs=%#x\\n",
	    surya_touch_rd(sst.gcc, SURYA_GCC_VOTE), surya_touch_rd(sst.gcc, SURYA_RCG), cfg, dfs);

	if (dfs & 1u) {
		cfg = surya_touch_rd(sst.gcc, SURYA_RCG + 0x1cu);
		if ((cfg & 0x371fu) != 1u) {
			printf("SURYA TOUCH: DFS level0=%#x not XO/1; need clock integration\\n", cfg);
			return false;
		}
	} else {
		cfg = (cfg & ~(0x371fu | (1u << 20))) | 1u;
		surya_touch_wr(sst.gcc, SURYA_RCG + 4u, cfg);
		surya_touch_wr(sst.gcc, SURYA_RCG, surya_touch_rd(sst.gcc, SURYA_RCG) | 1u);
		if (!surya_touch_wait_clear(sst.gcc, SURYA_RCG, 1u)) {
			printf("SURYA TOUCH: RCG update timeout\\n");
			return false;
		}
	}
	for (i = 0; i < sizeof(branches) / sizeof(branches[0]); ++i) {
		if (!surya_touch_wait_clear(sst.gcc, branches[i], 1u << 31)) {
			printf("SURYA TOUCH: GCC branch %#x halted (%#x)\\n",
			    branches[i], surya_touch_rd(sst.gcc, branches[i]));
			return false;
		}
	}
	return true;
}

static bool
surya_touch_se_init(void)
{
	uint32_t fw  = surya_touch_rd(sst.se, SSE_FW);
	uint32_t htx = surya_touch_rd(sst.se, SSE_HW_TX);
	uint32_t hrx = surya_touch_rd(sst.se, SSE_HW_RX);
	printf("SURYA TOUCH: SE0 fw=%#x proto=%u status=%#x htx=%#x hrx=%#x\\n",
	    fw, (fw >> 8) & 0xffu, surya_touch_rd(sst.se, SSE_STATUS), htx, hrx);

	if (((fw >> 8) & 0xffu) != 1u) {
		printf("SURYA TOUCH: SE0 firmware is not SPI (proto=%u); expected 1\\n",
		    (fw >> 8) & 0xffu);
		return false;
	}
	if (surya_touch_rd(sst.se, SSE_STATUS) & 0x1001u) {
		printf("SURYA TOUCH: SE0 busy; skipping init\\n");
		return false;
	}

	surya_touch_wr(sst.se, 0xe18, 0);
	surya_touch_wr(sst.se, 0xe1c, 0);
	surya_touch_wr(sst.se, 0x644, 0);
	surya_touch_wr(sst.se, SSE_IRQ_CLR, 0xffffffffu);
	surya_touch_wr(sst.se, 0x648, 0xffffffffu);
	surya_touch_wr(sst.se, SSE_DMA, 0);

	/* CGC and IO defaults */
	surya_touch_wr(sst.se, 0x28, surya_touch_rd(sst.se, 0x28) | 0x7fu);
	surya_touch_wr(sst.se, 0xe30, surya_touch_rd(sst.se, 0xe30) | 0x0fu);
	surya_touch_wr(sst.se, 0x24, 0x7f);
	surya_touch_wr(sst.se, 0x20, 1);

	/* SPI parameters */
	surya_touch_wr(sst.se, 0x22c, 0);
	surya_touch_wr(sst.se, 0x250, 0);
	surya_touch_wr(sst.se, 0x224, 0);
	surya_touch_wr(sst.se, 0x230, 0);
	surya_touch_wr(sst.se, 0x24c, 0);
	surya_touch_wr(sst.se, 0x25c, 0);
	surya_touch_wr(sst.se, 0x268, 4);

	/* Packing: 8-bit MSB first, 4 bytes per 32-bit FIFO word */
	surya_touch_wr(sst.se, 0x254, 0);
	surya_touch_wr(sst.se, 0x260, 0x0007f8feu);
	surya_touch_wr(sst.se, 0x264, 0x000ffefeu);
	surya_touch_wr(sst.se, 0x284, 0x0007f8feu);
	surya_touch_wr(sst.se, 0x288, 0x000ffefeu);

	surya_touch_wr(sst.se, SSE_CLK_SEL, 0);
	surya_touch_wr(sst.se, SSE_MCLK, (2u << 4) | 1u);

	surya_touch_wr(sst.se, 0x80c, 1);
	surya_touch_wr(sst.se, 0x810, 0);
	surya_touch_wr(sst.se, 0x814, ((hrx >> 16) & 0x3fu) - 1u);

	surya_touch_wr(sst.se, SSE_IRQ_EN, SSE_EVENTS);

	if ((surya_touch_rd(sst.se, SSE_TX_COUNT) & 0xfffffffu) ||
	    (surya_touch_rd(sst.se, SSE_RX_COUNT) & 0x1ffffffu)) {
		printf("SURYA TOUCH: inherited FIFO data; skipping\\n");
		return false;
	}
	return true;
}

static int
surya_touch_spi_xfer(const uint8_t *tx, unsigned tx_len,
    uint8_t *rx, unsigned rx_len)
{
	unsigned sent = 0, got = 0;
	int err = ETIMEDOUT;
	unsigned i;
	uint32_t irq;
	unsigned chunk;
	uint32_t word;
	unsigned k;
	uint32_t count;
	unsigned m;

	if (sst.dead || tx_len > 90 || rx_len > 90 || rx_len != tx_len || tx_len == 0) {
		return EIO;
	}
	if (!surya_touch_wait_clear(sst.se, SSE_STATUS, 1u)) {
		sst.dead = true;
		return EBUSY;
	}
	surya_touch_wr(sst.se, SSE_IRQ_CLR, 0xffffffffu);
	surya_touch_wr(sst.se, SSE_TX_LEN, rx_len);
	surya_touch_wr(sst.se, SSE_RX_LEN, rx_len);
	surya_touch_wr(sst.se, 0x80c, 1);
	surya_touch_wr(sst.se, SSE_CMD, (3u << 27));

	for (i = 0; i < 20000 && !sst.dead; ++i) {
		irq = surya_touch_rd(sst.se, SSE_IRQ);
		if (irq & SSE_ERRORS) {
			unsigned j;
			err = EIO;
			for (j = 0; j < 5000 && !(irq & SSE_DONE); ++j) {
				delay(1);
				irq = surya_touch_rd(sst.se, SSE_IRQ);
			}
			surya_touch_wr(sst.se, SSE_IRQ_CLR, irq);
			break;
		}

		while (sent < tx_len && (surya_touch_rd(sst.se, SSE_TX_COUNT) & 0xfffffffu) < 16u) {
			chunk = tx_len - sent;
			word = 0;
			if (chunk > 4) {
				chunk = 4;
			}
			for (k = 0; k < chunk; ++k) {
				word |= (uint32_t)tx[sent + k] << (8u * k);
			}
			surya_touch_wr(sst.se, SSE_TX, word);
			sent += chunk;
		}

		count = surya_touch_rd(sst.se, SSE_RX_COUNT) & 0x1ffffffu;
		while (count--) {
			word = surya_touch_rd(sst.se, SSE_RX);
			for (m = 0; m < 4 && got < rx_len; ++m) {
				if (rx) {
					rx[got] = (uint8_t)(word >> (8u * m));
				}
				got++;
			}
		}

		if (irq & SSE_DONE) {
			surya_touch_wr(sst.se, SSE_IRQ_CLR, irq);
			err = (got == rx_len && sent == tx_len) ? 0 : EIO;
			break;
		}
		surya_touch_wr(sst.se, SSE_IRQ_CLR, irq & ((1u << 26) | (1u << 27) | (1u << 30)));
		delay(1);
	}
	return err;
}

static int
surya_touch_spi_write(const uint8_t *tx, unsigned len)
{
	uint8_t buf[96];
	uint8_t dummy_rx[96];
	unsigned i;

	if (len == 0 || len > 90) {
		return EINVAL;
	}
	for (i = 0; i < len; ++i) {
		buf[i] = tx[i];
	}
	buf[0] |= 0x80u;
	return surya_touch_spi_xfer(buf, len, dummy_rx, len);
}

static int
surya_touch_spi_read(uint8_t reg, uint8_t *out, unsigned len)
{
	uint8_t tx[96];
	uint8_t rx[96];
	unsigned total = len + 2u;
	unsigned i;
	int err;

	if (len == 0 || total > 90) {
		return EINVAL;
	}
	memset(tx, 0, total);
	tx[0] = reg & 0x7fu;
	tx[1] = 0x00;

	err = surya_touch_spi_xfer(tx, total, rx, total);
	if (!err && out) {
		for (i = 0; i < len; ++i) {
			out[i] = rx[2u + i];
		}
	}
	return err;
}

static int
surya_nvt_check_trim(uint8_t *trim_out)
{
	const uint8_t page_cmd[3] = {0xff, 0x03, 0xec};
	int err;

	err = surya_touch_spi_write(page_cmd, 3);
	if (err) {
		return err;
	}
	delay(1000);
	return surya_touch_spi_read(0x4e, trim_out, 6);
}

static void
surya_nvt_report(uint32_t mask, const int *x, const int *y)
{
	unsigned id;
	uint32_t bit;
	for (id = 0; id < NVT_MAX_FINGERS; ++id) {
		bit = 1u << id;
		if (mask & bit) {
			if (!(sst.active & bit) || x[id] != sst.x[id] || y[id] != sst.y[id]) {
				sweet_hid_touch((int)id, 1, x[id], y[id]);
			}
			sst.x[id] = x[id];
			sst.y[id] = y[id];
		} else if (sst.active & bit) {
			sweet_hid_touch((int)id, 0, sst.x[id], sst.y[id]);
		}
	}
	sst.active = mask;
}

static int
surya_nvt_poll(void)
{
	uint8_t pts[65];
	int err;
	int x[NVT_MAX_FINGERS];
	int y[NVT_MAX_FINGERS];
	uint32_t mask = 0;
	unsigned i;
	unsigned off;
	uint8_t status;
	uint8_t state;
	unsigned fid;
	unsigned px, py;

	memset(pts, 0, sizeof(pts));
	memset(x, 0, sizeof(x));
	memset(y, 0, sizeof(y));

	err = surya_touch_spi_read(0x00, pts, 65);
	if (err) {
		return err;
	}

	for (i = 0; i < NVT_MAX_FINGERS; ++i) {
		off = 6u * i;
		status = pts[off];
		if (!status) {
			continue;
		}
		fid = (status >> 3) - 1u;
		if (fid >= NVT_MAX_FINGERS) {
			continue;
		}
		state = status & 7u;
		if (state == 1u || state == 2u) {
			px = ((unsigned)pts[off + 1] << 4) | ((unsigned)pts[off + 3] >> 4);
			py = ((unsigned)pts[off + 2] << 4) | ((unsigned)pts[off + 3] & 0x0fu);
			if (px >= (unsigned)NVT_WIDTH || py >= (unsigned)NVT_HEIGHT) {
				continue;
			}
			mask |= 1u << fid;
			x[fid] = (int)px;
			y[fid] = (int)py;
		}
	}
	surya_nvt_report(mask, x, y);
	return 0;
}

static void
surya_touch_thread(void *arg, wait_result_t result)
{
	unsigned delay_s = 3;
	uint8_t trim[6];
	int perr = -1;
	unsigned errors = 0, ticks = 0;
	bool irq_low;
	int poll_err;
	unsigned attempt;
	(void)arg;
	(void)result;

	(void)PE_parse_boot_argn("sweettouchdelay", &delay_s, sizeof(delay_s));
	printf("SURYA TOUCH: thread starting in %u s\\n", delay_s);
	surya_touch_wait(delay_s * 1000u);

	printf("SURYA TOUCH: mapping SE0/GCC/TLMM\\n");
	sst.se     = ml_io_map(SURYA_SE0_PA,      0x4000);
	sst.gcc    = ml_io_map(SURYA_GCC_PA,      0x60000);
	sst.tlmm_w = ml_io_map(SURYA_TLMM_W_PA,   SURYA_TLMM_W_SIZE);
	sst.tlmm_n = ml_io_map(SURYA_TLMM_N_PA,   SURYA_TLMM_N_SIZE);
	if (!sst.se || !sst.gcc || !sst.tlmm_w || !sst.tlmm_n) {
		printf("SURYA TOUCH: MMIO mapping failed\\n");
		goto out;
	}

	if (!surya_touch_clocks()) {
		goto out;
	}

	/* Pins 49 (MOSI), 50 (MISO), 51 (SCLK), 52 (CS): WEST tile, qup00 (mux=2), no pull, 6mA */
	surya_touch_gpio(sst.tlmm_w, 49, 2, 0, 2, false);
	surya_touch_gpio(sst.tlmm_w, 50, 2, 0, 2, false);
	surya_touch_gpio(sst.tlmm_w, 51, 2, 0, 2, false);
	surya_touch_gpio(sst.tlmm_w, 52, 2, 0, 2, false);

	/* Pin 9 (IRQ): NORTH tile, gpio (mux=0), pull-up, 8mA, input */
	surya_touch_gpio(sst.tlmm_n, 9, 0, 3, 3, false);

	/* Pin 8 (Reset): NORTH tile, gpio (mux=0), no pull, 8mA, output */
	surya_touch_gpio(sst.tlmm_n, 8, 0, 0, 3, true);
	surya_touch_gpio_out(sst.tlmm_n, 8, false);
	surya_touch_wait(10);
	surya_touch_gpio_out(sst.tlmm_n, 8, true);
	surya_touch_wait(30);

	if (!surya_touch_se_init()) {
		goto out;
	}

	for (attempt = 0; attempt < 10; ++attempt) {
		memset(trim, 0, sizeof(trim));
		perr = surya_nvt_check_trim(trim);
		if (!perr && trim[5] == 0x03u) {
			break;
		}
		surya_touch_wait(10);
	}

	printf("SURYA TOUCH: NT36672C probe err=%d trim=%02x %02x %02x %02x %02x %02x irq=%d\\n",
	    perr, trim[0], trim[1], trim[2], trim[3], trim[4], trim[5],
	    (int)surya_touch_gpio_in(sst.tlmm_n, 9));

	printf("SURYA TOUCH: NT36672C ready, 1080x2400, polling every 10 ms\\n");
	while (!sst.dead) {
		irq_low = !surya_touch_gpio_in(sst.tlmm_n, 9);
		if (sst.active || irq_low || (++ticks % 10u) == 0) {
			poll_err = surya_nvt_poll();
			if (poll_err) {
				if ((errors++ % 100u) == 0) {
					printf("SURYA TOUCH: poll err=%d\\n", poll_err);
				}
				if (errors == 10) {
					surya_nvt_report(0, sst.x, sst.y);
				}
			} else {
				errors = 0;
			}
		}
		surya_touch_wait(10);
	}
	surya_nvt_report(0, sst.x, sst.y);
out:
	(void)thread_terminate(current_thread());
	thread_block(THREAD_CONTINUE_NULL);
}

static void
surya_touch_init(void)
{
	int enabled = 1;
	thread_t thread;
	if (sst.started) {
		return;
	}
	sst.started = true;
	(void)PE_parse_boot_argn("sweettouch", &enabled, sizeof(enabled));
	if (!enabled) {
		printf("SURYA TOUCH: disabled (sweettouch=0)\\n");
		return;
	}
	kern_return_t kr = kernel_thread_start(surya_touch_thread, NULL, &thread);
	if (kr == KERN_SUCCESS) {
		thread_deallocate(thread);
	} else {
		printf("SURYA TOUCH: kernel_thread_start failed %d\\n", kr);
	}
}
#endif /* ARM64_BOARD_CONFIG_SURYA */
"""

new_content = prefix + surya_code + '\n' + suffix
target_src.write_text(new_content, encoding='utf-8')
print('Updated', target_src)

# Now generate patch 0087
import difflib

base_text = base_xnu_src.read_text(encoding='utf-8').splitlines(keepends=True)
new_text = new_content.splitlines(keepends=True)

diff = difflib.unified_diff(
    base_text, new_text,
    fromfile='a/bsd/dev/sweet_touch.c',
    tofile='b/bsd/dev/sweet_touch.c',
    n=3
)

diff_lines = list(diff)
# Ensure standard git diff header
patch_header = [
    'diff --git a/bsd/dev/sweet_touch.c b/bsd/dev/sweet_touch.c\n',
    'index 6ac690f..31727ee 100644\n',
]

final_patch = ''.join(patch_header + diff_lines[2:]) # Skip the --- / +++ from unified_diff if we format them
# unified_diff lines 0 and 1 are --- a/... and +++ b/...
final_patch = ''.join(patch_header) + ''.join(diff_lines)
# Wait, diff_lines already has --- and +++ at index 0 and 1
final_patch = 'diff --git a/bsd/dev/sweet_touch.c b/bsd/dev/sweet_touch.c\nindex 6ac690f..31727ee 100644\n' + ''.join(diff_lines)

patch_out.write_bytes(final_patch.encode('utf-8'))
print('Wrote patch to', patch_out)
