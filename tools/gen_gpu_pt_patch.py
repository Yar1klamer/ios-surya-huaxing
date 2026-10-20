#!/usr/bin/env python3
"""Regenerate xnu/patches/0092-surya-private-gpu-page-tables.patch.

Produces a proper git-apply-compatible patch that includes new file mode
headers so darwin-xnu-build's 'git apply --check' passes for new-file hunks.
"""
import hashlib
import pathlib
import textwrap

ROOT = pathlib.Path(__file__).parent.parent

def git_blob_hash(data: bytes) -> str:
    header = f"blob {len(data)}\x00".encode()
    return hashlib.sha1(header + data).hexdigest()

def make_new_file_diff(git_path: str, content: bytes) -> str:
    blob = git_blob_hash(content)
    lines = content.decode("utf-8")
    body = ""
    for line in lines.splitlines(keepends=True):
        body += "+" + line
    if not body.endswith("\n"):
        body += "\n\\ No newline at end of file\n"
    n = lines.count("\n")
    hunk_header = f"@@ -0,0 +1,{n} @@"
    return (
        f"diff --git a/{git_path} b/{git_path}\n"
        f"new file mode 100644\n"
        f"index 0000000..{blob[:7]}\n"
        f"--- /dev/null\n"
        f"+++ b/{git_path}\n"
        f"{hunk_header}\n"
        f"{body}"
    )

# Read the canonical sources from graphics/native/
h_src = (ROOT / "graphics/native/surya_gpu_pt.h").read_bytes()
c_src = (ROOT / "graphics/native/surya_gpu_pt.c").read_bytes()

# The xnu-side paths (relative to xnu source tree)
h_diff = make_new_file_diff("bsd/dev/surya_gpu_pt.h", h_src)
dt_diff = make_new_file_diff("bsd/dev/surya_gpu_dt.h", (ROOT / "graphics/native/surya_gpu_dt.h").read_bytes())
protocol_diff = make_new_file_diff("bsd/dev/surya_gmu_protocol.h", (ROOT / "graphics/native/surya_gmu_protocol.h").read_bytes())
c_diff = make_new_file_diff("bsd/dev/surya_gpu_pt.c", c_src)

# bsd/conf/files modification: add surya_gpu_pt.c entry
files_mod = """\
diff --git a/bsd/conf/files b/bsd/conf/files
--- a/bsd/conf/files
+++ b/bsd/conf/files
@@ -108,6 +108,7 @@
 bsd/dev/sweet_sample.c\t\t\tstandard
 bsd/dev/sweet_keys.c\t\t\tstandard
 bsd/dev/sweet_touch.c\t\t\tstandard
+bsd/dev/surya_gpu_pt.c\t\t\tstandard
 bsd/dev/sweet_rpmh.c\t\t\tstandard
 bsd/dev/sweet_spmi.c\t\t\tstandard
 bsd/dev/sweet_usb.c\t\t\tstandard
"""

# bsd/kern/bsd_init.c modification: call surya_gpu_pt_diagnostic before touch report
bsd_init_mod = """\
diff --git a/bsd/kern/bsd_init.c b/bsd/kern/bsd_init.c
--- a/bsd/kern/bsd_init.c
+++ b/bsd/kern/bsd_init.c
@@ -1103,6 +1103,8 @@
 \tbsd_init_kprintf(\"bsd_do_post - done\");
 
 #if defined(ARM64_BOARD_CONFIG_SURYA)
+\textern void surya_gpu_pt_diagnostic(void);
+\tsurya_gpu_pt_diagnostic();
 \textern void surya_touch_boot_report(void);
 \tsurya_touch_boot_report();
 #endif
"""

patch = h_diff + dt_diff + protocol_diff + c_diff + files_mod + bsd_init_mod

out = ROOT / "xnu/patches/0092-surya-private-gpu-page-tables.patch"
out.write_bytes(patch.encode("utf-8"))
print(f"Wrote {len(patch)} bytes to {out}")
print(f"surya_gpu_pt.h blob: {git_blob_hash(h_src)[:7]}")
print(f"surya_gpu_pt.c blob: {git_blob_hash(c_src)[:7]}")
