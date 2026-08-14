#!/bin/bash
# Push Aether's rendered palette into Plasma + GTK.
#
# Aether writes the filled template under ~/.config/omarchy/themes/aether/
# (or ~/.config/aether/theme/) and then runs this hook. The previous hook
# preferred ~/.local/share/color-schemes/Aether.colors — after the first
# apply that file already exists, so every later apply copied the stale
# scheme onto itself and Plasma never saw the new colours.
set -u

LOG="${XDG_CACHE_HOME:-$HOME/.cache}/synapseos/aether-post-apply.log"
mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1
echo "=== $(date -Is) pid=$$ ==="

SCHEME_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/color-schemes"
DEST="$SCHEME_DIR/Aether.colors"
mkdir -p "$SCHEME_DIR"

src=""
for cand in \
    "$HOME/.config/omarchy/themes/aether/plasma-Aether.colors" \
    "$HOME/.config/omarchy/themes/aether/Aether.colors" \
    "$HOME/.config/aether/theme/Aether.colors" \
    "$HOME/.config/aether/theme/plasma-Aether.colors"
do
    if [[ -f "$cand" ]] && ! grep -q '{background' "$cand" 2>/dev/null; then
        src="$cand"
        break
    fi
done

if [[ -z "$src" ]]; then
    echo "no rendered Aether.colors template found"
    # Still try to reload whatever is already installed.
    src=""
    if [[ -f "$DEST" ]] && ! grep -q '{background' "$DEST" 2>/dev/null; then
        src="$DEST"
    fi
fi

if [[ -n "$src" ]]; then
    echo "using $src"
    rm -f "$DEST"
    cp -f "$src" "$DEST"
else
    echo "nothing to apply"
fi

reload_scheme() {
    command -v plasma-apply-colorscheme >/dev/null || return 0
    [[ -f "$DEST" ]] || return 0
    # Same scheme name is a no-op. Bounce through a throwaway name so a
    # second Apply actually repaints.
    local bounce="$SCHEME_DIR/.AetherBounce.colors"
    sed 's/^Name=.*/Name=AetherBounce/;s/^ColorScheme=.*/ColorScheme=AetherBounce/' \
        "$DEST" >"$bounce"
    plasma-apply-colorscheme AetherBounce >/dev/null 2>&1 || true
    plasma-apply-colorscheme Aether >/dev/null 2>&1 || true
    rm -f "$bounce"

    local accent=""
    if [[ -f "$HOME/.config/aether/theme/colors.toml" ]]; then
        accent="$(sed -n 's/^accent *= *"\(#\{0,1\}[0-9A-Fa-f]\{6\}\)"/\1/p' \
            "$HOME/.config/aether/theme/colors.toml" | head -1)"
        [[ "$accent" == \#* ]] || [[ -z "$accent" ]] || accent="#$accent"
    fi
    if [[ -n "$accent" ]]; then
        plasma-apply-colorscheme --accent-color "$accent" Aether >/dev/null 2>&1 || true
    fi
}

reload_scheme

if command -v kwriteconfig6 >/dev/null; then
    kwriteconfig6 --file kdeglobals --group General --key ColorScheme Aether || true
elif command -v kwriteconfig5 >/dev/null; then
    kwriteconfig5 --file kdeglobals --group General --key ColorScheme Aether || true
fi

dbus-send --session --type=signal /KGlobalSettings \
    org.kde.KGlobalSettings.notifyChange int32:3 int32:0 >/dev/null 2>&1 || true
if command -v qdbus6 >/dev/null; then
    qdbus6 org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true
elif command -v qdbus >/dev/null; then
    qdbus org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true
fi

wall=""
if [[ -d "$HOME/.config/aether/theme/backgrounds" ]]; then
    wall="$(find "$HOME/.config/aether/theme/backgrounds" -type f \
        \( -name '*.jpg' -o -name '*.png' -o -name '*.jpeg' -o -name '*.webp' \) \
        | head -1 || true)"
fi
if [[ -n "$wall" ]] && command -v plasma-apply-wallpaperimage >/dev/null; then
    echo "wallpaper $wall"
    plasma-apply-wallpaperimage "$wall" >/dev/null 2>&1 || true
fi

if command -v kwriteconfig6 >/dev/null; then
    kwriteconfig6 --file breezerc --group Style --key MenuOpacity 70 || true
elif command -v kwriteconfig5 >/dev/null; then
    kwriteconfig5 --file breezerc --group Style --key MenuOpacity 70 || true
fi
dbus-send --session --type=signal /BreezeStyle \
    org.kde.Breeze.Style.reparseConfiguration >/dev/null 2>&1 || true

if [[ -f "$HOME/.config/aether/theme/gtk.css" ]]; then
    mkdir -p "$HOME/.config/gtk-3.0" "$HOME/.config/gtk-4.0"
    cp -f "$HOME/.config/aether/theme/gtk.css" "$HOME/.config/gtk-3.0/gtk.css"
    cp -f "$HOME/.config/aether/theme/gtk.css" "$HOME/.config/gtk-4.0/gtk.css"
fi

menu_css='
/* SynapseOS: translucent menus so KWin can blur them */
menu,
.csd menu,
menuitem > window.popup > menu,
popover contents,
popover.background {
  background-color: alpha(@theme_bg_color, 0.70);
}
'
mkdir -p "$HOME/.config/gtk-3.0" "$HOME/.config/gtk-4.0"
for gtkcss in "$HOME/.config/gtk-3.0/gtk.css" "$HOME/.config/gtk-4.0/gtk.css"; do
    if [[ -f "$gtkcss" ]] && grep -q 'SynapseOS: translucent menus' "$gtkcss"; then
        continue
    fi
    printf '%s\n' "$menu_css" >> "$gtkcss"
done

echo "done"
exit 0
