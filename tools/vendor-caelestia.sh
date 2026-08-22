#!/usr/bin/env bash
# Snapshot Caelestia dots into airootfs skel. Do not run `caelestia install`
# on the live ISO — that needs a network, a writable home, and git.
#
#   ./tools/vendor-caelestia.sh
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
skel="${repo_root}/archiso/airootfs/etc/skel"
cache="${CAELESTIA_CACHE:-${HOME}/.cache/synapseos-caelestia}"
src="${cache}/dots"
url="https://github.com/caelestia-dots/caelestia.git"

mkdir -p "$cache"
if [[ -d "${src}/.git" ]]; then
    git -C "$src" fetch --depth 1 origin main
    git -C "$src" reset --hard origin/main
else
    rm -rf "$src"
    git clone --depth 1 "$url" "$src"
fi

commit="$(git -C "$src" rev-parse HEAD)"
echo "==> vendoring caelestia-dots ${commit}"

install -d "$skel/.config"

copy_tree() {
    local from="$1" to="$2"
    rm -rf "$to"
    install -d "$(dirname "$to")"
    cp -a "$from" "$to"
}

copy_tree "$src/hypr" "$skel/.config/hypr"
copy_tree "$src/fish" "$skel/.config/fish"
copy_tree "$src/foot" "$skel/.config/foot"
copy_tree "$src/btop" "$skel/.config/btop"
copy_tree "$src/thunar" "$skel/.config/Thunar"
if [[ -d "$src/uwsm" ]]; then
    copy_tree "$src/uwsm" "$skel/.config/uwsm"
fi
install -m 0644 "$src/starship.toml" "$skel/.config/starship.toml"

install -d "$skel/.config/caelestia"
printf '%s\n' "$commit" > "$skel/.config/caelestia/dots-commit"

# Ensure user overlay files exist even if this script is re-run; the
# SynapseOS copies below are the ones we actually want.
if [[ ! -f "$skel/.config/caelestia/hypr-vars.lua" ]]; then
    printf 'return {}\n' > "$skel/.config/caelestia/hypr-vars.lua"
fi
if [[ ! -f "$skel/.config/caelestia/hypr-user.lua" ]]; then
    : > "$skel/.config/caelestia/hypr-user.lua"
fi

# Caelestia fish config expects this file.
install -d "$skel/.config/caelestia"
touch "$skel/.config/caelestia/user-config.fish"

echo "    wrote ${skel}/.config/{hypr,fish,foot,btop,Thunar,caelestia,starship.toml}"
echo "    pin ${commit}"
