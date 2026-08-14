#!/usr/bin/env bash
# Vendor Catppuccin Macchiato (Mauve) into the ISO overlay.
# Safe to re-run. Needs network the first time (cached under /tmp).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AIROOTFS="$ROOT/archiso/airootfs"
CACHE="${SYNAPSEOS_THEME_CACHE:-/tmp/synapseos-themes}"
SRC_WALL="${1:-}"

mkdir -p "$CACHE"
cd "$CACHE"

clone() {
    local url="$1" dir="$2"
    if [[ -d "$dir/.git" ]]; then
        git -C "$dir" pull --ff-only >/dev/null || true
    else
        git clone --depth=1 "$url" "$dir"
    fi
}

clone https://github.com/catppuccin/kde.git kde
clone https://github.com/catppuccin/kvantum.git kvantum

fetch_zip() {
    local url="$1" dest="$2"
    if [[ ! -d "$dest" ]]; then
        local tmp
        tmp="$(mktemp -d)"
        curl -fsSL "$url" -o "$tmp/a.zip"
        unzip -q "$tmp/a.zip" -d "$tmp/out"
        mkdir -p "$dest"
        # flatten a single top-level dir
        if [[ "$(find "$tmp/out" -mindepth 1 -maxdepth 1 | wc -l)" -eq 1 ]]; then
            mv "$tmp/out"/*/* "$dest"/ 2>/dev/null || mv "$tmp/out"/* "$dest"/
        else
            mv "$tmp/out"/* "$dest"/
        fi
        rm -rf "$tmp"
    fi
}

fetch_zip \
    "https://github.com/catppuccin/cursors/releases/download/v2.0.0/catppuccin-macchiato-mauve-cursors.zip" \
    "$CACHE/cursors-macchiato-mauve"
fetch_zip \
    "https://github.com/catppuccin/gtk/releases/download/v1.0.3/catppuccin-macchiato-mauve-standard+default.zip" \
    "$CACHE/gtk-macchiato-mauve"
fetch_zip \
    "https://github.com/catppuccin/sddm/releases/download/v1.1.2/catppuccin-macchiato-mauve-sddm.zip" \
    "$CACHE/sddm-macchiato-mauve"

# --- Color scheme -----------------------------------------------------------
install -d "$AIROOTFS/usr/share/color-schemes"
install -m 0644 \
    "$CACHE/kde/generated/color-schemes/CatppuccinMacchiatoMauve.colors" \
    "$AIROOTFS/usr/share/color-schemes/"

# --- Aurorae window decoration ---------------------------------------------
AUR_DST="$AIROOTFS/usr/share/aurorae/themes/CatppuccinMacchiato-Modern"
rm -rf "$AUR_DST"
mkdir -p "$AUR_DST"
cp -a "$CACHE/kde/Resources/Aurorae/CatppuccinMacchiato-Modern/." "$AUR_DST/"
install -m 0644 \
    "$CACHE/kde/Resources/Aurorae/Common/Catppuccin-Modernrc" \
    "$AUR_DST/CatppuccinMacchiato-Modernrc"

# --- Look-and-feel ----------------------------------------------------------
LNF_DST="$AIROOTFS/usr/share/plasma/look-and-feel/Catppuccin-Macchiato-Mauve"
rm -rf "$LNF_DST"
mkdir -p "$LNF_DST"
cp -a "$CACHE/kde/Resources/LookAndFeel/Catppuccin-Macchiato-Global/." "$LNF_DST/"
cp -a "$CACHE/kde/generated/look-and-feel/Modern/Catppuccin-Macchiato-Mauve/." "$LNF_DST/"

# Keep Breeze chrome. Upstream LnF defaults select Aurorae; pin Breeze so
# a look-and-feel apply does not swap the window decorations.
_lnf_defaults="$LNF_DST/contents/defaults"
if [[ -f "$_lnf_defaults" ]]; then
    sed -i \
        -e 's|^library=.*|library=org.kde.breeze|' \
        -e 's|^theme=.*|theme=Breeze|' \
        -e 's|^BorderSize=.*|BorderSize=Normal|' \
        -e 's|^BorderSizeAuto=.*|BorderSizeAuto=false|' \
        "$_lnf_defaults"
fi
unset _lnf_defaults

# --- Cursors ----------------------------------------------------------------
CUR_DST="$AIROOTFS/usr/share/icons/catppuccin-macchiato-mauve-cursors"
rm -rf "$CUR_DST"
mkdir -p "$CUR_DST"
cp -a "$CACHE/cursors-macchiato-mauve/." "$CUR_DST/"

# --- GTK --------------------------------------------------------------------
# zip contains the standard theme plus -hdpi / -xhdpi siblings. Use the
# unsuffixed directory (it has gtk-3.0 / gtk-4.0).
GTK_SRC="$CACHE/gtk-macchiato-mauve"
GTK_FROM="$(find "$GTK_SRC" -mindepth 1 -maxdepth 1 -type d ! -name '*-hdpi' ! -name '*-xhdpi' | head -1)"
if [[ -z "${GTK_FROM:-}" ]]; then
    GTK_FROM="$GTK_SRC"
fi
GTK_NAME="$(basename "$GTK_FROM")"
GTK_DST="$AIROOTFS/usr/share/themes/$GTK_NAME"
rm -rf "$AIROOTFS/usr/share/themes"/catppuccin-macchiato-mauve*
mkdir -p "$GTK_DST"
cp -a "$GTK_FROM/." "$GTK_DST/"

# --- Kvantum ----------------------------------------------------------------
KV_DST="$AIROOTFS/usr/share/Kvantum/catppuccin-macchiato-mauve"
rm -rf "$KV_DST"
mkdir -p "$KV_DST"
cp -a "$CACHE/kvantum/themes/catppuccin-macchiato-mauve/." "$KV_DST/"

# --- SDDM -------------------------------------------------------------------
SDDM_DST="$AIROOTFS/usr/share/sddm/themes/catppuccin-macchiato-mauve"
rm -rf "$SDDM_DST"
mkdir -p "$SDDM_DST"
cp -a "$CACHE/sddm-macchiato-mauve/." "$SDDM_DST/"

# Point SDDM at the SynapseOS wallpaper when we have one.
if [[ -f "$AIROOTFS/usr/share/backgrounds/synapseos/desktop.png" ]]; then
    install -d "$SDDM_DST/backgrounds"
    ln -sfn /usr/share/backgrounds/synapseos/desktop.png \
        "$SDDM_DST/backgrounds/synapseos.png"
    if [[ -f "$SDDM_DST/theme.conf" ]]; then
        sed -i 's|^Background=.*|Background="backgrounds/synapseos.png"|' "$SDDM_DST/theme.conf" || true
    fi
fi

# Remember the GTK directory name for skel writers.
printf '%s\n' "$GTK_NAME" > "$AIROOTFS/usr/share/synapseos/gtk-theme-name"
echo "Catppuccin Macchiato Mauve installed into airootfs"
echo "GTK theme: $GTK_NAME"
