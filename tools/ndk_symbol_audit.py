#!/usr/bin/env python3
"""Diagnostic comparison of APK dynamic imports with ARM64 API 28 NDK stubs.

The public NDK stub inventory is not an Android linker namespace simulation.
Report unknown imports and missing DT_NEEDED dependencies for review; do not
claim device compatibility or silently replace missing functions.
"""
import argparse
import json
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

def elf(path, flag):
    return subprocess.check_output(["readelf", "-W", flag, str(path)], text=True)

def symbols(text):
    exports, imports = set(), []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 8 or not re.fullmatch(r"\d+:", fields[0]):
            continue
        if fields[4] not in ("GLOBAL", "WEAK", "UNIQUE"):
            continue
        name, sep, version = fields[7].partition("@")
        if not name:
            continue
        ver = version.lstrip("@")
        if fields[6] == "UND":
            imports.append((fields[4], name, ver))
        elif fields[5] in ("DEFAULT", "PROTECTED"):
            if not sep or version.startswith("@"):
                exports.add((name, ""))
            if ver:
                exports.add((name, ver))
    return exports, imports

def needed(text):
    return set(re.findall(r"\(NEEDED\).*?\[([^\]]+)\]", text))

def scan(apk, sysroot):
    api = sysroot / "usr/lib/aarch64-linux-android/28"
    if not (api / "libc.so").is_file() or not (api / "libandroid.so").is_file():
        raise ValueError("Missing ARM64 API28 NDK stubs")
    stub_exports = set()
    stub_names = set()
    non_elf_stubs = []
    for lib in sorted(api.glob("*.so")):
        with lib.open("rb") as f:
            magic = f.read(4)
        if magic != b"\x7fELF":
            if lib.name in ("libc.so", "libandroid.so"):
                raise ValueError("Essential stub is not ELF: " + lib.name)
            # Some NDK .so entries are linker scripts, not loadable libraries.
            # Do not count them as runtime exports or available DT_NEEDED names.
            non_elf_stubs.append(lib.name)
            continue
        stub_exports.update(symbols(elf(lib, "--dyn-syms"))[0])
        stub_names.add(lib.name)
    packaged = {}
    with zipfile.ZipFile(apk) as z, tempfile.TemporaryDirectory() as tmp:
        for entry in z.namelist():
            if not re.fullmatch(r"lib/arm64-v8a/[^/]+\.so", entry):
                continue
            name = Path(entry).name
            if name in packaged:
                raise ValueError("Duplicate library: " + name)
            p = Path(tmp) / name
            with z.open(entry) as src, p.open("wb") as out:
                shutil.copyfileobj(src, out)
            ex, im = symbols(elf(p, "--dyn-syms"))
            packaged[name] = (ex, im, needed(elf(p, "-d")))
            p.unlink()
    if not packaged:
        raise ValueError("No ARM64 libraries found")
    all_exports = stub_exports.union(*(v[0] for v in packaged.values()))
    available_libs = stub_names | set(packaged)
    unknown, absent = [], []
    for lib, (_, imports, dependencies) in packaged.items():
        for dep in sorted(dependencies - available_libs):
            absent.append({"library":lib, "needed":dep})
        for binding, name, version in imports:
            if (name, version) not in all_exports:
                unknown.append({"library":lib, "binding":binding, "symbol":name,
                                "version":version})
    return {"api":28, "ndk_stub_count":len(stub_names),
            "apk_libraries":sorted(packaged), "non_elf_stubs":non_elf_stubs, "unmatched_needed":absent,
            "unmatched_imports":unknown,
            "strong_unmatched":sum(x["binding"] != "WEAK" for x in unknown),
            "weak_unmatched":sum(x["binding"] == "WEAK" for x in unknown),
            "limitations":"Union of public stubs and packaged exports; not dependency closure, namespace, or runtime validation."}

class Tests(unittest.TestCase):
    def test_versions(self):
        ex, im = symbols("  1: 0 0 FUNC GLOBAL DEFAULT 1 foo@@LIBC\n"
                         "  2: 0 0 FUNC GLOBAL DEFAULT 1 bar@LIBC_Q\n"
                         "  3: 0 0 FUNC WEAK DEFAULT UND baz@LIBC_R")
        self.assertEqual(ex, {("foo",""), ("foo","LIBC"), ("bar","LIBC_Q")})
        self.assertEqual(im, [("WEAK","baz","LIBC_R")])
    def test_hidden(self):
        self.assertEqual(symbols("  1: 0 0 FUNC GLOBAL HIDDEN 1 foo")[0], set())
    def test_needed(self):
        self.assertEqual(needed("  0x1 (NEEDED) Shared library: [libandroid.so]"),
                         {"libandroid.so"})

def main():
    p = argparse.ArgumentParser()
    p.add_argument("apk", nargs="?", type=Path)
    p.add_argument("--sysroot", type=Path)
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        return 0 if unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful() else 1
    if not a.apk or not a.sysroot:
        p.error("APK and --sysroot required")
    print(json.dumps(scan(a.apk, a.sysroot), indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
