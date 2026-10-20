#!/usr/bin/env python3
"""Embed pinned UniXNU table/context code and SURYA integration into XNU."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def new_file(name, data):
    if b'\r' in data or not data.endswith(b'\n'):
        raise ValueError('kernel source must use LF with final newline')
    digest = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
    return (f'diff --git a/bsd/dev/{name} b/bsd/dev/{name}\n'
            f'new file mode 100644\nindex 0000000..{digest[:7]}\n'
            f'--- /dev/null\n+++ b/bsd/dev/{name}\n'
            f'@@ -0,0 +1,{data.count(bytes([10]))} @@\n' +
            ''.join('+' + line for line in data.decode().splitlines(keepends=True)))


def generate():
    vendor = ROOT / 'graphics/vendor/unixnu/ArmSmmu4K'
    files = [(p.name, p.read_bytes()) for p in (
        vendor / 'ArmSmmu4K.h', vendor / 'ArmSmmu4K.c',
        vendor / 'ArmSmmu4KContext.h', vendor / 'ArmSmmu4KContext.c',
        ROOT / 'graphics/native/surya_unixnu_smmu.h',
        ROOT / 'graphics/native/surya_unixnu_smmu.c')]
    # Preserve the upstream MIT notice inside the source patch as well.
    files.append(('ArmSmmu4K.LICENSE', (vendor / 'LICENSE').read_bytes()))
    patch = ''.join(new_file(name, data) for name, data in files)
    patch += '''diff --git a/bsd/conf/files b/bsd/conf/files
--- a/bsd/conf/files
+++ b/bsd/conf/files
@@ -109,6 +109,9 @@
 bsd/dev/sweet_keys.c\t\t\tstandard
 bsd/dev/sweet_touch.c\t\t\tstandard
 bsd/dev/surya_gpu_pt.c\t\t\tstandard
+bsd/dev/ArmSmmu4K.c\t\t\tstandard
+bsd/dev/ArmSmmu4KContext.c\t\t\tstandard
+bsd/dev/surya_unixnu_smmu.c\t\tstandard
 bsd/dev/sweet_rpmh.c\t\t\tstandard
 bsd/dev/sweet_spmi.c\t\t\tstandard
 bsd/dev/sweet_usb.c\t\t\tstandard
'''
    # Stop only diagnostic SMMU faults before the missing panic-buffer path.
    for name, kind in (("sleh_synchronous", 1), ("sleh_serror", 2)):
        signature = f"{name}(arm_context_t *context, uint32_t esr, vm_offset_t far)"
        lines = ["#if defined(ARM64_BOARD_CONFIG_SURYA)",
                 "\textern void surya_smmu_exception_capture(unsigned, uint32_t, uint64_t, uint64_t, uint64_t);",
                 f"\tsurya_smmu_exception_capture({kind}, esr, far,",
                 "\t    get_saved_state_pc(&context->ss), get_saved_state_lr(&context->ss));",
                 "#endif"]
        patch += ("diff --git a/osfmk/arm64/sleh.c b/osfmk/arm64/sleh.c\n"
                  "--- a/osfmk/arm64/sleh.c\n+++ b/osfmk/arm64/sleh.c\n"
                  "@@ -1,3 +1,8 @@\n " + signature + "\n {\n" +
                  "".join("+" + line + "\n" for line in lines) +
                  (" \tesr_exception_class_t  class   = ESR_EC(esr);\n" if kind == 1 else
                   " \ttask_vtimer_check(current_thread());\n"))
    return patch


if __name__ == '__main__':
    target = ROOT / 'xnu/patches/0093-surya-unixnu-smmu-foundation.patch'
    target.write_bytes(generate().encode())
    print(target.name)
