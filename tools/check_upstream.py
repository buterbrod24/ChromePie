#!/usr/bin/env python3
"""Lightweight upstream check, not a Chromium build."""
import base64
import re
import urllib.request
import urllib.error
import time
from pathlib import Path

TAG = "159.0.8154.33"
BASE = "https://chromium.googlesource.com/chromium/src/+/refs/tags/" + TAG + "/"

def fetch(path):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(BASE + path + "?format=TEXT", timeout=20) as response:
                return base64.b64decode(response.read(), validate=False).decode("utf-8")
        except (urllib.error.URLError, TimeoutError) as exc:
            if isinstance(exc, urllib.error.HTTPError) and exc.code not in (429, 500, 502, 503, 504):
                raise
            if attempt == 2:
                raise
            delay = 2 ** (attempt + 1)
            print(f"Transient upstream error for {path}: {exc}; retry in {delay}s", flush=True)
            time.sleep(delay)

def check_version(text):
    values = dict(re.findall(r"^(MAJOR|MINOR|BUILD|PATCH)=(\d+)\s*$", text, re.M))
    actual = ".".join(values[k] for k in ("MAJOR", "MINOR", "BUILD", "PATCH"))
    if actual != TAG:
        raise ValueError("Wrong upstream version: " + actual)
    return actual

def main():
    args = (Path(__file__).parent / "args.gn").read_text()
    for key in ("default_min_sdk_version", "android_ndk_api_level"):
        if not re.search(r"^" + key + r"\s*=\s*28\s*$", args, re.M):
            raise ValueError("Wrong API: " + key)
    print("Upstream version:", check_version(fetch("chrome/VERSION")))
    for path in ("build/config/android/config.gni", "chrome/android/BUILD.gn"):
        print("\n", path)
        for i, line in enumerate(fetch(path).splitlines(), 1):
            if re.search(r"min_sdk_version|min_supported_sdk_version|android_ndk_api_level|android_static_analysis|chrome_public_apk", line):
                print(f"{i}: {line.strip()}")
    print("Text inspection only; GN/linker/runtime verification still required.")

if __name__ == "__main__":
    main()
