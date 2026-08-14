#!/usr/bin/env bash
# Install missing Plasma bits (needs your sudo password) and open a nested
# Catppuccin Macchiato session so the look can be judged without rebuilding
# the ISO. Does not touch ~/.config on the host desktop.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PREVIEW="${SYNAPSEOS_PREVIEW_HOME:-$ROOT/.preview-home}"
AI="$ROOT/archiso/airootfs"

need=(
    papirus-icon-theme
    kdeplasma-addons
    dolphin
    konsole
    kate
    gwenview
    spectacle
    plasma-nm
    plasma-pa
    kscreen
    breeze-gtk
    kde-gtk-config
    inter-font
)

echo "=== SynapseOS Macchiato preview ==="
echo

missing=()
for pkg in "${need[@]}"; do
    if ! pacman -Q "$pkg" >/dev/null 2>&1; then
        missing+=("$pkg")
    fi
done

if ((${#missing[@]})); then
    echo "Installing ${#missing[@]} packages (sudo password):"
    printf '  %s\n' "${missing[@]}"
    echo
    sudo pacman -S --needed --noconfirm "${missing[@]}"
else
    echo "All preview packages already installed."
fi

echo
echo "Preparing isolated home at $PREVIEW"
rm -rf "$PREVIEW"
mkdir -p "$PREVIEW/.config" "$PREVIEW/.local/share" "$PREVIEW/.cache" \
    "$PREVIEW/.local/share/color-schemes" \
    "$PREVIEW/.local/share/aurorae/themes" \
    "$PREVIEW/.local/share/plasma/look-and-feel" \
    "$PREVIEW/.local/share/icons" \
    "$PREVIEW/.local/share/themes" \
    "$PREVIEW/.local/share/wallpapers/synapseos" \
    "$PREVIEW/.local/share/kwin/effects" \
    "$PREVIEW/.local/share/kwin-wayland/effects" \
    "$PREVIEW/.config/Kvantum"

cp -a "$AI/etc/skel/.config/." "$PREVIEW/.config/"
cp -a "$AI/etc/skel/.local/." "$PREVIEW/.local/"

# Desktop files so Icon Tasks can resolve icons in this isolated home.
mkdir -p "$PREVIEW/.local/share/applications"
for desk in org.kde.dolphin firefox org.kde.kate org.kde.gwenview org.kde.konsole systemsettings; do
    if [[ -f /usr/share/applications/${desk}.desktop ]]; then
        cp /usr/share/applications/${desk}.desktop "$PREVIEW/.local/share/applications/"
    fi
done

install -d "$PREVIEW/.config/autostart" "$PREVIEW/.config/synapseos" "$PREVIEW/.local/bin"
install -m 0755 "$AI/usr/bin/synapseos-apply-dock" "$PREVIEW/.local/bin/synapseos-apply-dock"
if [[ -x "$AI/usr/bin/synapseos-apply-chrome" ]]; then
    install -m 0755 "$AI/usr/bin/synapseos-apply-chrome" "$PREVIEW/.local/bin/synapseos-apply-chrome"
    cat > "$PREVIEW/.config/autostart/synapseos-apply-chrome.desktop" << EOF
[Desktop Entry]
Type=Application
Name=SynapseOS chrome
Exec=$PREVIEW/.local/bin/synapseos-apply-chrome
OnlyShowIn=KDE;
X-KDE-autostart-phase=1
NoDisplay=true
EOF
    rm -f "$PREVIEW/.config/synapseos/chrome-version"
fi
cat > "$PREVIEW/.config/autostart/synapseos-apply-dock.desktop" << EOF
[Desktop Entry]
Type=Application
Name=SynapseOS dock
Exec=env SYNAPSEOS_DOCK_JS=$AI/usr/share/synapseos/dock.js $PREVIEW/.local/bin/synapseos-apply-dock
OnlyShowIn=KDE;
X-KDE-autostart-phase=2
NoDisplay=true
EOF
# Force the dock script to run on this preview launch.
rm -f "$PREVIEW/.config/synapseos/dock-version"

# Themes from the ISO overlay
cp -a "$AI/usr/share/color-schemes/." "$PREVIEW/.local/share/color-schemes/"
cp -a "$AI/usr/share/aurorae/themes/." "$PREVIEW/.local/share/aurorae/themes/"
cp -a "$AI/usr/share/plasma/look-and-feel/." "$PREVIEW/.local/share/plasma/look-and-feel/"
cp -a "$AI/usr/share/icons/catppuccin-macchiato-mauve-cursors" "$PREVIEW/.local/share/icons/"
cp -a "$AI/usr/share/themes/catppuccin-macchiato-mauve-standard+default" "$PREVIEW/.local/share/themes/"
cp -a "$AI/usr/share/Kvantum/catppuccin-macchiato-mauve" "$PREVIEW/.config/Kvantum/"
if [[ -d "$AI/usr/share/kwin-wayland/effects/synapseosjump" ]]; then
    cp -a "$AI/usr/share/kwin-wayland/effects/synapseosjump" \
        "$PREVIEW/.local/share/kwin/effects/"
    cp -a "$AI/usr/share/kwin-wayland/effects/synapseosjump" \
        "$PREVIEW/.local/share/kwin-wayland/effects/"
fi
install -m 0644 "$AI/usr/share/backgrounds/synapseos/desktop.png" \
    "$PREVIEW/.local/share/wallpapers/synapseos/desktop.png"

# Point the panel/desktop wallpaper at this preview copy
sed -i "s|file:///usr/share/backgrounds/synapseos/desktop.png|file://$PREVIEW/.local/share/wallpapers/synapseos/desktop.png|g" \
    "$PREVIEW/.config/plasma-org.kde.plasma.desktop-appletsrc"

export HOME="$PREVIEW"
export XDG_CONFIG_HOME="$PREVIEW/.config"
export XDG_DATA_HOME="$PREVIEW/.local/share"
export XDG_CACHE_HOME="$PREVIEW/.cache"
export XDG_STATE_HOME="$PREVIEW/.local/state"
unset XDG_CURRENT_DESKTOP XDG_SESSION_DESKTOP DESKTOP_SESSION
export XDG_CURRENT_DESKTOP=KDE
export XDG_SESSION_TYPE=wayland
export QT_QPA_PLATFORM=wayland
export GTK_THEME=catppuccin-macchiato-mauve-standard+default
unset GTK_IM_MODULE QT_IM_MODULE GLFW_IM_MODULE
# Stay on the host compositor socket so KWin can nest as a window.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-1}"

echo
echo "Applying look-and-feel…"
plasma-apply-colorscheme CatppuccinMacchiatoMauve >/dev/null 2>&1 || true
plasma-apply-lookandfeel -a Catppuccin-Macchiato-Mauve >/dev/null 2>&1 || true
plasma-apply-wallpaperimage "$PREVIEW/.local/share/wallpapers/synapseos/desktop.png" >/dev/null 2>&1 || true

echo
echo "Launching nested Plasma (close the Plasma window when you are done)."
echo "Your Hyprland session stays running."
echo

# Nested session: with the host WAYLAND_DISPLAY set, KWin opens as a window
# on Hyprland instead of taking over the machine.
exec dbus-run-session -- startplasma-wayland
