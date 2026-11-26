#!/usr/bin/env python3
"""Native compatibility gate for a candidate ARM64 Chromium APK.
Not proof of runtime compatibility; weak imports require guarded call sites.
"""
import argparse
import json
import re
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

def inspect_text(dynamic, symbols):
    findings = []
    if re.search(r"\(NEEDED\).*\[libbinder_ndk\.so\]", dynamic):
        findings.append(("BLOCK", "DT_NEEDED libbinder_ndk.so"))
    for line in symbols.splitlines():
        f = line.split()
        if len(f) < 8 or f[6] != "UND" or f[4] not in ("GLOBAL", "WEAK"):
            continue
        name, _, version = f[7].partition("@")
        version = version.lstrip("@")
        if (name.startswith(("AIBinder_", "AParcel_", "AStatus_", "ASurfaceControl_", "ASurfaceTransaction", "android_fdsan_"))
                or name in ("android_get_device_api_level", "AHardwareBuffer_lockPlanes", "AHardwareBuffer_lockAndGetInfo", "AHardwareBuffer_isSupported", "AHardwareBuffer_getId", "AHardwareBuffer_readFromParcel", "AHardwareBuffer_writeToParcel")
                or re.fullmatch(r"LIBC_(?:Q|R|S|T|U|V|W|X|Y|Z)(?:_.*)?", version)
                or version == "LIBBINDER_NDK"):
            findings.append(("BLOCK" if f[4] == "GLOBAL" else "REVIEW", f[7]))
    return findings

def inspect_apk(path):
    findings = []
    libraries = []
    with zipfile.ZipFile(path) as z, tempfile.TemporaryDirectory() as tmp:
        entries = [n for n in z.namelist() if re.fullmatch(r"lib/arm64-v8a/[^/]+\.so", n)]
        if len(entries) != len(set(entries)):
            raise ValueError("Duplicate ARM64 library")
        if not any(Path(n).name in ("libchrome.so", "libmonochrome.so") for n in entries):
            findings.append(("BLOCK", "APK", "No ARM64 Chromium engine"))
        for entry in entries:
            name = Path(entry).name
            p = Path(tmp) / name
            with z.open(entry) as src, p.open("wb") as out:
                import shutil
                shutil.copyfileobj(src, out)
            libraries.append(name)
            if name == "libbinder_ndk.so":
                findings.append(("BLOCK", name, "Bundled Binder requires ABI/security review"))
            def readelf(flag):
                return subprocess.check_output(["readelf", "-W", flag, str(p)], text=True)
            if not re.search(r"Machine:\s+AArch64", readelf("-h")):
                findings.append(("BLOCK", name, "Not AArch64"))
            findings.extend((level, name, detail) for level, detail in inspect_text(readelf("-d"), readelf("--dyn-syms")))
    return {"libraries": libraries, "findings": findings, "blocks": sum(f[0] == "BLOCK" for f in findings), "reviews": sum(f[0] == "REVIEW" for f in findings)}

class Tests(unittest.TestCase):
    def test_binder(self):
        self.assertEqual(inspect_text(" 0x1 (NEEDED) Shared library: [libbinder_ndk.so]", ""), [("BLOCK", "DT_NEEDED libbinder_ndk.so")])
    def test_strong(self):
        self.assertEqual(inspect_text("", " 1: 0 0 FUNC GLOBAL DEFAULT UND ASurfaceControl_create"), [("BLOCK", "ASurfaceControl_create")])
    def test_weak(self):
        self.assertEqual(inspect_text("", " 2: 0 0 FUNC WEAK DEFAULT UND android_fdsan_close_with_tag@LIBC_Q"), [("REVIEW", "android_fdsan_close_with_tag@LIBC_Q")])
    def test_defined(self):
        self.assertEqual(inspect_text("", " 3: 0 0 FUNC GLOBAL DEFAULT 12 ASurfaceControl_create"), [])
    def test_old_api(self):
        self.assertEqual(inspect_text("", " 4: 0 0 FUNC GLOBAL DEFAULT UND malloc@LIBC"), [])

def main():
    p = argparse.ArgumentParser()
    p.add_argument("apk", type=Path, nargs="?")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        return 0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful() else 1
    if args.apk is None:
        p.error("APK required")
    report = inspect_apk(args.apk)
    print(json.dumps(report, indent=2))
    return 2 if report["blocks"] else 0

if __name__ == "__main__":
    raise SystemExit(main())
