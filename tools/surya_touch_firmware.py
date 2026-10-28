"""Pinned touch controller firmware contracts (Tianma and Huaxing). Binaries stay outside the repository."""
import hashlib
import struct

SIZE = 139264
# Source of the Tianma image: sm7150-mainline/firmware-xiaomi-surya, commit
# 971dfbf9dafb27a235eea04794cfcb501fa80655, novatek_ts_tianma_fw.bin.
# The Huaxing image is the one in this phone's own vendor partition
# (/vendor/firmware/novatek_ts_huaxing_fw.bin, Android bootargs say dsi_nt36672c_huaxing).
PANELS = {
    'tianma': {'sha256': '6084479e391048f029da01df9c8c0ff9fdf47c8bbfcac3b927572eca23592c90', 'version': (0xc2, 0x3d)},
    'huaxing': {'sha256': '4e519856514bad7e495466b28809ff4f074642c32a4f433a76028a309d966aab', 'version': (0xc3, 0x3c)},
}
SHA256 = PANELS['tianma']['sha256']  # kept for existing callers


def panel_of(data):
    """Name of the pinned panel image this is, or None."""
    digest = hashlib.sha256(data).hexdigest()
    for name, spec in PANELS.items():
        if len(data) == SIZE and digest == spec['sha256']:
            return name
    return None


def validate(data, panel='tianma'):
    if panel not in PANELS:
        raise ValueError('unknown touch panel %r' % (panel,))
    spec = PANELS[panel]
    if len(data) != SIZE or hashlib.sha256(data).hexdigest() != spec['sha256']:
        raise ValueError('touch firmware does not match pinned SURYA %s image' % panel.capitalize())
    if data[126976:126978] != bytes(spec['version']) or data[131069:131072] != b'NVT':
        raise ValueError('touch firmware version/end marker invalid')
    # Validate the two CRC-protected executable partitions.
    for i in range(2):
        off, addr, size_minus_one = struct.unpack_from('<3I', data, i * 12)
        if off > len(data) or size_minus_one + 1 > len(data) - off:
            raise ValueError('touch firmware file bounds invalid')
        if addr >= 0x30000 or size_minus_one + 1 > 0x30000 - addr:
            raise ValueError('touch firmware SRAM bounds invalid')
    return data
