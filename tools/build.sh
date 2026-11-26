#!/usr/bin/env bash
# Experimental build only. Does not publish an APK or bypass security.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
src=$(realpath "${1:?Usage: bash tools/build.sh /path/to/chromium/src [--gn-only]}")
mode=${2:-}
[[ -z "$mode" || "$mode" == --gn-only ]] || exit 64
cd "$src"
for t in gn autoninja git; do command -v "$t" >/dev/null || { echo "Missing $t"; exit 1; }; done
[[ $(git rev-parse HEAD) == $(git rev-parse 'refs/tags/159.0.8154.33^{commit}') ]] || { echo 'Wrong upstream revision'; exit 1; }
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
[[ "$mode" != --gn-only ]] || exit 0
autoninja -C "$out" chrome_public_apk 2>&1 | tee "$out/pie-build.log"
apk="$out/apks/ChromePublic.apk"
test -f "$apk"
sha256sum "$apk" > "$out/pie-apk.sha256"
echo 'Candidate only: native imports, manifest, signing and device tests required before distribution.'
