#!/usr/bin/env bash
# Experimental build only; do not distribute before device testing.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
src=$(realpath "${1:?Usage: bash tools/build.sh /path/to/chromium/src [--gn-only]}")
mode=${2:-}
[[ -z "$mode" || "$mode" == --gn-only ]] || exit 64
cd "$src"
for t in gn git python3; do
  command -v "$t" >/dev/null || { echo "Missing $t"; exit 1; }
done
if [[ "$mode" != --gn-only ]]; then
  for t in autoninja ninja readelf; do
    command -v "$t" >/dev/null || { echo "Missing $t"; exit 1; }
  done
fi
[[ $(git rev-parse HEAD) == $(git rev-parse 'refs/tags/159.0.8154.33^{commit}') ]] || { echo 'Wrong upstream revision'; exit 1; }
for patch_name in 0001-api28-hardware-buffer.patch 0002-api28-isolated-renderers.patch 0003-api28-disable-javaless-renderer.patch; do
  patch_file="$here/../patches/$patch_name"
  if git apply --check "$patch_file"; then
    git apply "$patch_file"
  elif git apply --reverse --check "$patch_file"; then
    echo "Already applied: $patch_name"
  else
    echo "Patch conflict: $patch_name"
    exit 1
  fi
done
# Stage 28: keep the API29 encoder behind its original runtime requirement.
python3 "$here/api28_encoder_guard.py" --self-test
python3 "$here/api28_encoder_guard.py" "$src"
out=out/ChromePie159_API28
mkdir -p "$out"
exec > >(tee -a "$out/pie-session.log") 2>&1
git rev-parse HEAD > "$out/pie-commit.txt"
git diff --binary HEAD > "$out/pie-source.diff"
[[ ! -f "$out/args.gn" ]] || cmp -s "$here/args.gn" "$out/args.gn" || { echo 'Different args.gn; refusing overwrite'; exit 1; }
cp "$here/args.gn" "$out/args.gn"
gn gen "$out" --fail-on-unused-args 2>&1 | tee "$out/pie-gn.log"
for arg in default_min_sdk_version android_ndk_api_level; do
  gn args "$out" --list="$arg" --short | tee "$out/$arg.txt"
  grep -Eq "^$arg[[:space:]]*=[[:space:]]*28[[:space:]]*$" "$out/$arg.txt" || { echo "Effective $arg not 28"; exit 1; }
done
gn args "$out" --list=chrome_public_manifest_package --short | tee "$out/package.txt"
grep -Eq '^chrome_public_manifest_package[[:space:]]*=[[:space:]]*"org\.chromepie\.browser"[[:space:]]*$' "$out/package.txt" || { echo 'Unexpected package ID'; exit 1; }
[[ "$mode" != --gn-only ]] || exit 0
# Compile the two translation units that blocked Build 002 before the full APK.
# The Ninja graph is authoritative: never guess GN target labels or object paths.
mkdir -p "$out/pie-media-source"
for f in media/gpu/BUILD.gn media/gpu/gpu_video_encode_accelerator_factory.cc media/gpu/android/BUILD.gn media/gpu/android/ndk_video_encode_accelerator.cc media/gpu/android/ndk_video_encode_accelerator.h; do
  if [[ -f "$f" ]]; then
    mkdir -p "$out/pie-media-source/$(dirname "$f")"
    cp "$f" "$out/pie-media-source/$f"
  fi
done
ninja -C "$out" -t targets all > "$out/pie-ninja-targets.txt"
mapfile -t media_objects < <(awk -F ': ' '$1 ~ /(^|[\/\.])(gpu_video_encode_accelerator_factory|ndk_video_encode_accelerator)\.o$/ {print $1}' "$out/pie-ninja-targets.txt" | sort -u)
printf '%s\n' "${media_objects[@]}" > "$out/pie-media-targets.txt"
if ! grep -Eq '(^|[/.])gpu_video_encode_accelerator_factory\.o$' "$out/pie-media-targets.txt"; then
  echo 'Could not locate factory object in Ninja graph; inspect pie-ninja-targets.txt'
  exit 1
fi
autoninja -C "$out" "${media_objects[@]}" 2>&1 | tee "$out/pie-media-preflight.log"
autoninja -C "$out" chrome_public_apk 2>&1 | tee "$out/pie-build.log"
apk="$out/apks/ChromePublic.apk"
test -f "$apk"
sha256sum "$apk" > "$out/pie-apk.sha256"
ndk_sysroot="$src/third_party/android_toolchain/ndk/toolchains/llvm/prebuilt/linux-x86_64/sysroot"
python3 "$here/ndk_symbol_audit.py" "$apk" --sysroot "$ndk_sysroot" | tee "$out/pie-ndk-symbol-audit.json"
python3 "$here/native_gate.py" "$apk" | tee "$out/pie-native-gate.json"
sdk="$src/third_party/android_sdk/public/build-tools/37.0.0"
python3 "$here/apk_gate.py" "$apk" --aapt2 "$sdk/aapt2" --apksigner "$sdk/apksigner" | tee "$out/pie-apk-gate.json"
echo 'Selected native, manifest and signature checks passed. Physical-device runtime tests are still required.'
