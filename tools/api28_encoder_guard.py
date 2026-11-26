#!/usr/bin/env python3
"""Stage 28: restore the Android API runtime guard at the NDK VEA factory.

Do not lower the upstream encoder's availability annotation or hide compiler
warnings. This is a narrow factory fix, not an API28 hardware encoder port.
"""
import argparse
from pathlib import Path
import re
import unittest

FACTORY = Path("media/gpu/gpu_video_encode_accelerator_factory.cc")
WRAPPER = Path("media/gpu/android/ndk_media_codec_wrapper.h")
GUARD = "if (__builtin_available(android NDK_MEDIA_CODEC_MIN_API, *)) {"
RETURN = re.compile(
    r"(?m)^(?P<indent>[ \t]*)return\s+base::WrapUnique<VideoEncodeAccelerator>"
    r"\(\s*new\s+NdkVideoEncodeAccelerator\s*\([^;{}]*\)\s*\);"
)
FACTORY_HEADER = re.compile(
    r"std::unique_ptr<VideoEncodeAccelerator>\s+CreateAndroidVEA\s*\([^{};]*\)\s*\{"
)


def transform(source):
    headers = list(FACTORY_HEADER.finditer(source))
    if len(headers) != 1:
        raise ValueError("Unexpected Android VEA factory declaration")
    start = headers[0].end()
    # Restrict changes to the simple factory body, not other call sites.
    end = source.find("\n}", start)
    if end == -1:
        raise ValueError("Missing Android factory closing brace")
    body = source[start:end]
    matches = list(RETURN.finditer(body))
    if len(matches) != 1:
        raise ValueError("Unexpected NDK VEA constructor expression")
    if GUARD in body:
        if not re.fullmatch(
            r"\s*" + re.escape(GUARD) + r"\s*" + RETURN.pattern.removeprefix("(?m)^")
            + r"\s*}\s*return nullptr;\s*", body
        ):
            raise ValueError("Existing guard differs; inspect manually")
        return source
    match = matches[0]
    if body[:match.start()].strip() or body[match.end():].strip():
        raise ValueError("Factory contains unexpected additional logic")
    indent = match.group("indent")
    statement = "\n".join("  " + line for line in match.group().splitlines())
    guarded = (
        indent + GUARD + "\n" + statement + "\n" + indent + "}\n"
        + indent + "return nullptr;"
    )
    return source[:start] + body[:match.start()] + guarded + body[match.end():] + source[end:]


class Tests(unittest.TestCase):
    sample = (
        "std::unique_ptr<VideoEncodeAccelerator> CreateAndroidVEA(\n"
        "    const gpu::GpuDriverBugWorkarounds& gpu_workarounds) {\n"
        "  return base::WrapUnique<VideoEncodeAccelerator>(new NdkVideoEncodeAccelerator(\n"
        "      base::SequencedTaskRunner::GetCurrentDefault(), gpu_workarounds));\n"
        "}\n"
    )

    def test_guard_and_idempotence(self):
        patched = transform(self.sample)
        self.assertIn(GUARD, patched)
        self.assertIn("return nullptr;", patched)
        self.assertEqual(transform(patched), patched)
        self.assertEqual(patched.count("new NdkVideoEncodeAccelerator"), 1)

    def test_reject_unknown(self):
        with self.assertRaises(ValueError):
            transform(self.sample.replace("return base::", "Check();\n  return base::"))
        with self.assertRaises(ValueError):
            transform(self.sample.replace("CreateAndroidVEA", "Unknown"))
        with self.assertRaises(ValueError):
            transform(self.sample + self.sample)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("src", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    if args.src is None:
        parser.error("src is required")
    wrapper = (args.src / WRAPPER).read_text()
    if not re.search(r"(?m)^\s*#define\s+NDK_MEDIA_CODEC_MIN_API\s+29\b", wrapper):
        raise SystemExit("Unexpected upstream codec minimum; inspect before modifying")
    path = args.src / FACTORY
    old = path.read_text()
    new = transform(old)
    if old != new:
        path.write_text(new)
    print("API29 encoder factory guard:", "applied" if old != new else "already applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
