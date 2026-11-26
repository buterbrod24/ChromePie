# ChromePie

Experimental Android 9 (API 28) compatibility port of Chromium 159.0.8154.33 for ARM64. Unofficial and not affiliated with Google.

## Current status (Stage 18)
- The original Chrome APK requires API 29. The intended minimum for ChromePie is API 28.
- The physical Android 9 diagnostic probe reported 58 unavailable strong symbols and 10 unavailable weak symbols in the application namespace.
- [NDK/Clang C-only ARM64 API 28 smoke test passed](https://github.com/buterbrod24/ChromePie/actions/runs/45739853396). This is not a Chromium build or a device test.
- [Both compatibility patches apply cleanly to the pinned Chromium source](https://github.com/buterbrod24/ChromePie/actions/runs/45740258678). The fixed renderer pool and manifest isolation attributes passed static checks.
- [First full source sync and experimental build](https://github.com/buterbrod24/ChromePie/actions/runs/45739509666) has been started. No successful browser build or runtime test has been confirmed.

## Toolchain
The upstream DEPS file pins NDK 30.0.16248370, Android SDK 37.2, build tools 37.0.0 and Chromium Clang llvmorg-24-init-17044-gc3223914-1.
Chromium distributes Clang separately from its stripped NDK sysroot.
The isolated C smoke test uses -unwindlib=none. This does not validate C++ unwinding. The upstream compiler configuration supports building its own libunwind from buildtools/third_party/libunwind when use_custom_libunwind is enabled. Do not disable unwinding in the browser as a workaround.

## Compatibility patches
1. Restore API 28 hardware buffer modules and guard API 29-only multi-plane CPU mapping.
2. Restore a fixed pool of 16 isolated Java renderer services and guard newer service-binding APIs.

The patches are experimental and have not been compiled as part of the browser yet.

## Build
On a dedicated unprivileged Linux x86-64 build host with the upstream host dependencies installed, at least 100 GiB of free disk (200+ recommended), and at least 8 GiB RAM:
```sh
bash tools/bootstrap.sh /path/to/new/workspace
export PATH="/path/to/new/workspace/depot_tools:$PATH"
bash tools/build.sh /path/to/new/workspace/src
```
Use --gn-only for build graph generation. A standard public GitHub Actions workflow also attempts the full build with a disk preflight. No paid resources are authorized.

## Goals and release gates
- Android 9 without root, without overwriting the installed Chrome.
- Separate package org.chromepie.browser.
- Preserve browser sandbox, TLS verification and OS security controls.
- Verify manifest, native imports, signing and physical-device runtime before any release.
- Preserve applicable upstream license notices. No proprietary Google APKs or credentials are distributed here.

Do not use experimental builds for sensitive accounts.

[Upstream source](https://chromium.googlesource.com/chromium/src/) | [Pinned Android build instructions](https://github.com/chromium/chromium/blob/159.0.8154.33/docs/android_build_instructions.md)
