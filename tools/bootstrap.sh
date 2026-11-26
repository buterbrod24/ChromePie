#!/usr/bin/env bash
# Dedicated, unprivileged Linux x86-64 workspace. No cloud resources provisioned.
set -euo pipefail
version=159.0.8154.33
root=$(realpath -m "${1:?Usage: bash tools/bootstrap.sh /path/to/new/workspace}")
[[ $(uname -s) == Linux && $(uname -m) == x86_64 && $EUID != 0 ]] || { echo 'Use an unprivileged x86-64 Linux account'; exit 1; }
mkdir -p "$root"
[[ ! -e "$root/.gclient" ]] || { echo 'Existing checkout: resume manually, do not overwrite'; exit 1; }
[[ $(df -Pk "$root" | awk 'END{print $4}') -ge $((100*1024*1024)) ]] || { echo 'Need at least 100 GiB free; 200+ recommended'; exit 1; }
exec > >(tee -a "$root/chromepie-bootstrap.log") 2>&1
git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git "$root/depot_tools"
export PATH="$PATH:$root/depot_tools"
cd "$root"
gclient config --name src https://chromium.googlesource.com/chromium/src.git
printf '\ntarget_os = ["android"]\n' >> .gclient
mkdir src
git -C src init
git -C src remote add origin https://chromium.googlesource.com/chromium/src.git
git -C src fetch --depth=1 origin "refs/tags/$version:refs/tags/$version"
commit=$(git -C src rev-parse "refs/tags/$version^{commit}")
git -C src checkout --detach "$commit"
gclient sync --nohooks --no-history --revision "src@$commit"
[[ $(git -C src rev-parse HEAD) == "$commit" ]]
cd src
echo 'Host dependencies must already be installed using upstream install-build-deps.sh.'
gclient runhooks
printf '%s\n' "$commit" > "$root/chromepie-source-commit.txt"
