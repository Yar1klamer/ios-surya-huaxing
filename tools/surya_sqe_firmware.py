"""Pinned Adreno 618 SQE microcode (a630_sqe.fw). The binary stays outside the repository; it is the vendor's, from this phone's own
/vendor/firmware. Linux copies the file to the GPU without its first dword (adreno_fw_create_bo), and the kernel does the same."""
import hashlib

SIZE = 32136
SHA256 = '36298bd53ea3666413d288a3a3f5266f67fcb6db038a0a481af5869d1c17859c'


def validate(data):
    if len(data) != SIZE or hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('SQE microcode does not match the pinned SURYA a630_sqe.fw')
    return data
