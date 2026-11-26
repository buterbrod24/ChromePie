#!/usr/bin/env python3
"""Check a candidate APK using the pinned Android SDK tools.

This is a static release gate, not evidence of safe runtime operation.
"""
import argparse
import json
import re
import subprocess
import unittest
from pathlib import Path

PACKAGE = "org.chromepie.browser"
SERVICE = "org.chromium.content.app.SandboxedProcessService"
META = "org.chromium.content.browser.NUM_SANDBOXED_SERVICES"

def parse_tree(tree):
    nodes = []
    stack = []
    for line in tree.splitlines():
        m = re.match(r"^(\s*)E:\s+([^\s(]+)", line)
        if m:
            depth = len(m[1])
            while stack and stack[-1]["depth"] >= depth:
                stack.pop()
            node = {"tag": m[2], "depth": depth, "attrs": {},
                    "parent": stack[-1]["tag"] if stack else None}
            nodes.append(node)
            stack.append(node)
            continue
        m = re.match(r"^\s*A:\s+([^\s(=]+)(?:\([^)]*\))?\s*=\s*(.*)$", line)
        if m and stack:
            stack[-1]["attrs"][m[1]] = m[2]
    return nodes

def value(raw):
    m = re.match(r'^"([^"]*)"', raw)
    return m[1] if m else raw.strip()

def number(raw):
    raw = re.sub(r"^\(type 0x[0-9a-fA-F]+\)\s*", "", value(raw))
    if raw in ("true", "false"):
        return int(raw == "true")
    try:
        return int(raw, 0)
    except ValueError:
        return None

def check_manifest(badging, tree):
    errors = []
    def need(ok, msg):
        if not ok:
            errors.append(msg)
    package = re.search(r"^package: name='([^']+)'", badging, re.M)
    sdk = re.search(r"^sdkVersion:'(\d+)'", badging, re.M)
    need(bool(package and package[1] == PACKAGE), "Unexpected package identity")
    need(bool(sdk and sdk[1] == "28"), "minSdkVersion is not 28")
    nodes = parse_tree(tree)
    apps = [n for n in nodes if n["tag"] == "application"]
    need(len(apps) == 1, "Missing or duplicate application element")
    metadata = [n["attrs"] for n in nodes if n["tag"] == "meta-data"
                and n["parent"] == "application"
                and value(n["attrs"].get("android:name", "")) == META]
    need(len(metadata) == 1 and number(metadata[0].get("android:value", "")) == 16,
         "Renderer pool metadata must equal 16")
    services = {}
    for node in nodes:
        if node["tag"] != "service" or node["parent"] != "application":
            continue
        attrs = node["attrs"]
        name = value(attrs.get("android:name", ""))
        if name.startswith("org.chromium.content.app.NativeOnlySandboxedProcessService"):
            errors.append("Unexpected native-only renderer: " + name)
        if not name.startswith(SERVICE):
            continue
        if name in services:
            errors.append("Duplicate renderer service: " + name)
        services[name] = attrs
    expected = {SERVICE + str(i) for i in range(16)}
    need(set(services) == expected, "Renderer service names do not match fixed pool")
    for name, attrs in services.items():
        suffix = name[len(SERVICE):]
        need(number(attrs.get("android:isolatedProcess", "")) in (1, -1, 0xffffffff),
             name + ": must be isolated")
        need(number(attrs.get("android:exported", "")) == 0, name + ": must not be exported")
        need(value(attrs.get("android:permission", "")) == PACKAGE + ".permission.CHILD_SERVICE",
             name + ": incorrect service permission")
        need(value(attrs.get("android:process", "")) == ":sandboxed_process" + suffix,
             name + ": incorrect process")
    return {"package": package[1] if package else None, "min_sdk": int(sdk[1]) if sdk else None,
            "renderer_count": len(services), "errors": errors}

def fixture():
    tree = 'E: manifest\n  E: application\n    E: meta-data\n'
    tree += f'      A: android:name(0x1)="{META}"\n      A: android:value(0x2)=(type 0x10)0x10\n'
    for i in range(16):
        tree += f'    E: service\n      A: android:name(0x1)="{SERVICE}{i}"\n'
        tree += f'      A: android:process(0x2)=":sandboxed_process{i}"\n'
        tree += f'      A: android:permission(0x3)="{PACKAGE}.permission.CHILD_SERVICE"\n'
        tree += '      A: android:isolatedProcess(0x4)=(type 0x12)0xffffffff\n'
        tree += '      A: android:exported(0x5)=(type 0x12)0x0\n'
    return f"package: name='{PACKAGE}'\nsdkVersion:'28'\n", tree

class Tests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(check_manifest(*fixture())["errors"], [])
    def test_bad_sdk(self):
        b, t = fixture()
        self.assertTrue(check_manifest(b.replace("'28'", "'29'"), t)["errors"])
    def test_bad_package(self):
        b, t = fixture()
        self.assertTrue(check_manifest(b.replace(PACKAGE, "com.android.chrome"), t)["errors"])
    def test_exported(self):
        b, t = fixture()
        self.assertTrue(check_manifest(b, t.replace("android:exported(0x5)=(type 0x12)0x0",
            "android:exported(0x5)=(type 0x12)0xffffffff", 1))["errors"])
    def test_missing_renderer(self):
        b, t = fixture()
        self.assertTrue(check_manifest(b, t.rsplit("    E: service", 1)[0])["errors"])
    def test_native_renderer(self):
        b, t = fixture()
        t += '    E: service\n      A: android:name="org.chromium.content.app.NativeOnlySandboxedProcessService0"\n'
        self.assertTrue(check_manifest(b, t)["errors"])

def main():
    p = argparse.ArgumentParser()
    p.add_argument("apk", nargs="?", type=Path)
    p.add_argument("--aapt2", default="aapt2")
    p.add_argument("--apksigner", default="apksigner")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        return 0 if unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful() else 1
    if not args.apk:
        p.error("APK required")
    def run(*cmd):
        return subprocess.run(cmd, text=True, capture_output=True, check=True).stdout
    report = check_manifest(
        run(args.aapt2, "dump", "badging", str(args.apk)),
        run(args.aapt2, "dump", "xmltree", "--file", "AndroidManifest.xml", str(args.apk)))
    signature = subprocess.run([args.apksigner, "verify", "--min-sdk-version", "28",
                                "--verbose", "--print-certs", str(args.apk)],
                               text=True, capture_output=True)
    report["signature_verified"] = signature.returncode == 0
    report["signature_details"] = signature.stdout + signature.stderr
    if signature.returncode:
        report["errors"].append("APK signature verification failed for API 28")
    print(json.dumps(report, indent=2))
    return 2 if report["errors"] else 0

if __name__ == "__main__":
    raise SystemExit(main())
