#!/bin/bash
# Push Aether's palette into Plasma + GTK. Must reload even when the
# scheme name is already "Aether" — plasma-apply-colorscheme otherwise
# no-ops and only the wallpaper changes.
set -euo pipefail

SCHEME_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/color-schemes"
mkdir -p "$SCHEME_DIR"

src=""
for cand in \
    "$HOME/.local/share/color-schemes/Aether.colors" \
    "$HOME/.config/omarchy/themes/aether/plasma-Aether.colors" \
    "$HOME/.config/omarchy/themes/aether/Aether.colors" \
    "$HOME/.config/aether/theme/Aether.colors"
do
    if [[ -f "$cand" ]] && ! grep -q '{background' "$cand" 2>/dev/null; then
        src="$cand"
        break
    fi
done

if [[ -n "$src" ]]; then
    cp -f "$src" "$SCHEME_DIR/Aether.colors"
fi

if command -v plasma-apply-colorscheme >/dev/null && [[ -f "$SCHEME_DIR/Aether.colors" ]]; then
    # Force a real reload: applying the same name is skipped.
    plasma-apply-colorscheme BreezeDark >/dev/null 2>&1 || true
    plasma-apply-colorscheme Aether >/dev/null 2>&1 || true
    accent=""
    if [[ -f "$HOME/.config/aether/theme/colors.toml" ]]; then
        accent="$(sed -n 's/^accent *= *"\(#\{0,1\}[0-9A-Fa-f]\{6\}\)"/\1/p' "$HOME/.config/aether/theme/colors.toml" | head -1)"
        [[ "$accent" == \#* ]] || [[ -z "$accent" ]] || accent="#$accent"
    fi
    if [[ -n "$accent" ]]; then
        plasma-apply-colorscheme --accent-color "$accent" Aether >/dev/null 2>&1 || true
    fi
fi

# Tell running Qt/KWin apps the palette changed.
dbus-send --session --type=signal /KGlobalSettings \
    org.kde.KGlobalSettings.notifyChange int32:3 int32:0 >/dev/null 2>&1 || true
if command -v qdbus6 >/dev/null; then
    qdbus6 org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true
elif command -v qdbus >/dev/null; then
    qdbus org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true
fi

wall=""
if [[ -d "$HOME/.config/aether/theme/backgrounds" ]]; then
    wall="$(find "$HOME/.config/aether/theme/backgrounds" -type f \( -name '*.jpg' -o -name '*.png' -o -name '*.jpeg' -o -name '*.webp' \) | head -1 || true)"
fi
if [[ -n "$wall" ]] && command -v plasma-apply-wallpaperimage >/dev/null; then
    plasma-apply-wallpaperimage "$wall" >/dev/null 2>&1 || true
fi

if [[ -f "$HOME/.config/aether/theme/gtk.css" ]]; then
    mkdir -p "$HOME/.config/gtk-3.0" "$HOME/.config/gtk-4.0"
    cp -f "$HOME/.config/aether/theme/gtk.css" "$HOME/.config/gtk-3.0/gtk.css"
    cp -f "$HOME/.config/aether/theme/gtk.css" "$HOME/.config/gtk-4.0/gtk.css"
fi
