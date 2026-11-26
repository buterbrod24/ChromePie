# ChromePie

Experimental Android 9 (API 28) compatibility port of Chromium 159.0.8154.33 for ARM64. Unofficial and not affiliated with Google.

## Current status
- Original Chrome APK requires Android 10.
- A separate diagnostic probe ran on a physical Android 9 device: 58 required and 10 optional system symbols unavailable in the app namespace.
- Binder NDK is unavailable on the test device.
- Full Chromium build and runtime testing have not yet been performed. No working browser APK is available.

## Goals
- Android 9 without root, without overwriting the installed Chrome.
- Preserve browser sandbox, TLS verification and OS security controls.
- Use upstream Chromium source, retaining applicable license notices.
- Zero-cost infrastructure if available.

## Build
The experimental GN configuration is in tools/args.gn. The initial CI is intended for lightweight checks only; a full Chromium checkout and build require a dedicated Linux x86-64 machine with ample memory and at least 100 GB free disk (200+ GB preferred). No paid resources are authorized.

Upstream: https://chromium.googlesource.com/chromium/src/
Instructions: https://chromium.googlesource.com/chromium/src/+/main/docs/android_build_instructions.md

No proprietary Google APKs or credentials are distributed here. Do not use experimental builds for sensitive accounts.
