"""Pinned Adreno 618 zap shader (a615_zap) contract. Binaries stay outside the repository.

The files are the ones in this phone's own /vendor/firmware. TrustZone is given the whole .mdt (the ELF header,
its program headers and the block of hashes and certificates) to check the signature, and the image's one
loadable segment (the .b02 file, relocatable) goes into the memory the device tree reserves for it.
"""
import hashlib
import struct

MDT_SHA256 = '6085cee5637f8d84376ea782a629186a70d660adb05720d3b3685b6895f3de07'
CODE_SHA256 = '61be42f041eb6051eb9f56beb1f98ed97ab21faf2ef2df6b9151ba1a46aae878'
MDT_SIZE = 6860
CODE_SIZE = 1984
# reserved-memory gpu_region@97715000 of the captured device tree (no-map, 0x2000)
REGION_BASE = 0x97715000
REGION_SIZE = 0x2000


def validate(mdt, code):
    if len(mdt) != MDT_SIZE or hashlib.sha256(mdt).hexdigest() != MDT_SHA256:
        raise ValueError('zap .mdt does not match the pinned SURYA a615_zap image')
    if len(code) != CODE_SIZE or hashlib.sha256(code).hexdigest() != CODE_SHA256:
        raise ValueError('zap .b02 does not match the pinned SURYA a615_zap image')
    if mdt[:5] != b'\x7fELF\x01':
        raise ValueError('zap .mdt is not a 32-bit ELF')
    phnum, = struct.unpack_from('<H', mdt, 44)
    hash_size, = struct.unpack_from('<I', mdt, 52 + 32 + 16)
    # The header followed by the hashes alone: the only thing TrustZone takes.
    if phnum < 2 or 52 + 32 * phnum + hash_size != len(mdt):
        raise ValueError('zap .mdt is not the ELF header followed by the hash block')
    # The one loadable segment: PT_LOAD, relocatable, its file size is the .b02 size.
    seg_type, _off, _va, _pa, filesz, _memsz, flags, _align = struct.unpack_from('<8I', mdt, 52 + 2 * 32)
    if seg_type != 1 or filesz != len(code) or not (flags & 0x08000000):
        raise ValueError('zap segment does not match the .b02 file')
    if len(code) > REGION_SIZE:
        raise ValueError('zap code does not fit the reserved region')
    return mdt, code
