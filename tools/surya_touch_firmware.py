"""Pinned Tianma touch firmware contract. Binary stays outside the repository."""
import hashlib
import struct

SIZE = 139264
SHA256 = '6084479e391048f029da01df9c8c0ff9fdf47c8bbfcac3b927572eca23592c90'
# Source: sm7150-mainline/firmware-xiaomi-surya, commit
# 971dfbf9dafb27a235eea04794cfcb501fa80655, novatek_ts_tianma_fw.bin.

def validate(data):
    if len(data) != SIZE or hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('touch firmware does not match pinned SURYA Tianma image')
    if data[126976:126978] != bytes((0xc2, 0x3d)) or data[131069:131072] != b'NVT':
        raise ValueError('touch firmware version/end marker invalid')
    # Validate the two CRC-protected executable partitions.
    for i in range(2):
        off, addr, size_minus_one = struct.unpack_from('<3I', data, i * 12)
        if off > len(data) or size_minus_one + 1 > len(data) - off:
            raise ValueError('touch firmware file bounds invalid')
        if addr >= 0x30000 or size_minus_one + 1 > 0x30000 - addr:
            raise ValueError('touch firmware SRAM bounds invalid')
    return data
