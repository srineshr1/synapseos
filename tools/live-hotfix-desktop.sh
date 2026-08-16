#!/usr/bin/env bash
# Apply the Plasma / SSH_AUTH_SOCK desktop bits on a running SynapseOS
# live session that was built before those files landed in the ISO.
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
    echo "run as root: sudo $0" >&2
    exit 1
fi

src="$(cd "$(dirname "$0")/.." && pwd)/archiso/airootfs"

if [[ -f "$src/usr/share/backgrounds/synapseos/desktop-frost.jpg" ]]; then
    install -d /usr/share/backgrounds/synapseos
    install -m 0644 "$src/usr/share/backgrounds/synapseos/desktop-frost.jpg" \
        /usr/share/backgrounds/synapseos/desktop-frost.jpg
fi
if [[ -f "$src/usr/share/synapseos/frost-noise.png" ]]; then
    install -m 0644 "$src/usr/share/synapseos/frost-noise.png" \
        /usr/share/synapseos/frost-noise.png
fi
install -m 0755 "$src/etc/profile.d/synapseos-graphics.sh" /etc/profile.d/synapseos-graphics.sh
install -m 0755 "$src/etc/profile.d/synapseos-ssh-agent.sh" /etc/profile.d/synapseos-ssh-agent.sh
install -m 0755 "$src/usr/bin/synapseos-safe-graphics" /usr/bin/synapseos-safe-graphics
if [[ -f "$src/usr/lib/systemd/user-environment-generators/30-synapseos-graphics" ]]; then
    install -d /usr/lib/systemd/user-environment-generators
    install -m 0755 \
        "$src/usr/lib/systemd/user-environment-generators/30-synapseos-graphics" \
        /usr/lib/systemd/user-environment-generators/30-synapseos-graphics
fi
if [[ -x "$src/usr/bin/synapseos-plasma" ]]; then
    install -m 0755 "$src/usr/bin/synapseos-plasma" /usr/bin/synapseos-plasma
fi
if [[ -x "$src/usr/bin/synapseos-check-desktop" ]]; then
    install -m 0755 "$src/usr/bin/synapseos-check-desktop" /usr/bin/synapseos-check-desktop
fi
if [[ -x "$src/usr/bin/synapseos-apply-chrome" ]]; then
    install -m 0755 "$src/usr/bin/synapseos-apply-chrome" /usr/bin/synapseos-apply-chrome
fi
if [[ -x "$src/usr/bin/synapseos-apply-chrome" ]]; then
    install -m 0755 "$src/usr/bin/synapseos-apply-chrome" /usr/bin/synapseos-apply-chrome
    install -d /etc/xdg/autostart
    install -m 0644 "$src/etc/xdg/autostart/synapseos-apply-chrome.desktop" \
        /etc/xdg/autostart/synapseos-apply-chrome.desktop
fi
if [[ -f "$src/etc/fonts/conf.d/50-synapseos.conf" ]]; then
    install -d /etc/fonts/conf.d
    install -m 0644 "$src/etc/fonts/conf.d/50-synapseos.conf" \
        /etc/fonts/conf.d/50-synapseos.conf
    fc-cache -f /usr/share/fonts >/dev/null 2>&1 || true
fi

# Bounce is an overlay of the stock scale effect (KWin already loads scale).
if [[ -f "$src/usr/share/synapseos/kwin/scale-main.js" ]]; then
    install -d /usr/share/kwin-wayland/effects/scale/contents/code
    install -m 0644 \
        "$src/usr/share/synapseos/kwin/scale-main.js" \
        /usr/share/kwin-wayland/effects/scale/contents/code/main.js
fi

# Force-blur helper so stock KWin blur frosts kitty/windows when
# Better Blur DX does not load.
if [[ -f "$src/usr/share/synapseos/kwin/frost-main.js" ]]; then
    install -d /usr/share/kwin/effects/synapseosfrost/contents/code
    install -d /usr/share/kwin-wayland/effects/synapseosfrost/contents/code
    install -m 0644 "$src/usr/share/synapseos/kwin/frost-main.js" \
        /usr/share/kwin/effects/synapseosfrost/contents/code/main.js
    install -m 0644 "$src/usr/share/synapseos/kwin/frost-main.js" \
        /usr/share/kwin-wayland/effects/synapseosfrost/contents/code/main.js
    if [[ -f "$src/usr/share/kwin/effects/synapseosfrost/metadata.json" ]]; then
        install -m 0644 "$src/usr/share/kwin/effects/synapseosfrost/metadata.json" \
            /usr/share/kwin/effects/synapseosfrost/metadata.json
        install -m 0644 "$src/usr/share/kwin/effects/synapseosfrost/metadata.json" \
            /usr/share/kwin-wayland/effects/synapseosfrost/metadata.json
    fi
fi

install -d /etc/xdg /etc/environment.d /etc/firefox/policies \
    /usr/lib/firefox/defaults/pref
install -m 0644 "$src/etc/xdg/kwinrc" /etc/xdg/kwinrc
if [[ -f "$src/etc/xdg/kwinrulesrc" ]]; then
    install -m 0644 "$src/etc/xdg/kwinrulesrc" /etc/xdg/kwinrulesrc
fi
if [[ -f "$src/etc/xdg/breezerc" ]]; then
    install -m 0644 "$src/etc/xdg/breezerc" /etc/xdg/breezerc
fi
if [[ -f "$src/etc/xdg/klaunchrc" ]]; then
    install -m 0644 "$src/etc/xdg/klaunchrc" /etc/xdg/klaunchrc
fi
install -m 0644 "$src/etc/environment.d/50-synapseos.conf" \
    /etc/environment.d/50-synapseos.conf
install -m 0644 "$src/etc/firefox/policies/policies.json" \
    /etc/firefox/policies/policies.json
install -m 0644 "$src/usr/lib/firefox/defaults/pref/synapseos.js" \
    /usr/lib/firefox/defaults/pref/synapseos.js

for home in /home/*; do
    if [[ -d "$home" ]]; then
        owner="$(stat -c %U "$home")"
        group="$(stat -c %G "$home")"
        install -d -o "$owner" -g "$group" "$home/.config"
        install -m 0644 -o "$owner" -g "$group" \
            "$src/etc/skel/.config/kwinrc" "$home/.config/kwinrc"
        if [[ -f "$src/etc/skel/.config/kwinrulesrc" ]]; then
            install -m 0644 -o "$owner" -g "$group" \
                "$src/etc/skel/.config/kwinrulesrc" "$home/.config/kwinrulesrc"
        fi
        if [[ -f "$src/etc/skel/.config/breezerc" ]]; then
            install -m 0644 -o "$owner" -g "$group" \
                "$src/etc/skel/.config/breezerc" "$home/.config/breezerc"
        fi
        if [[ -f "$src/etc/skel/.config/klaunchrc" ]]; then
            install -m 0644 -o "$owner" -g "$group" \
                "$src/etc/skel/.config/klaunchrc" "$home/.config/klaunchrc"
        fi
        if [[ -f "$src/etc/skel/.config/gtk-3.0/gtk.css" ]]; then
            install -d -o "$owner" -g "$group" "$home/.config/gtk-3.0"
            install -m 0644 -o "$owner" -g "$group" \
                "$src/etc/skel/.config/gtk-3.0/gtk.css" "$home/.config/gtk-3.0/gtk.css"
        fi
        if [[ -f "$src/etc/skel/.config/gtk-4.0/gtk.css" ]]; then
            install -d -o "$owner" -g "$group" "$home/.config/gtk-4.0"
            install -m 0644 -o "$owner" -g "$group" \
                "$src/etc/skel/.config/gtk-4.0/gtk.css" "$home/.config/gtk-4.0/gtk.css"
        fi
        kitty_conf="$home/.config/kitty/kitty.conf"
        if [[ -f "$kitty_conf" ]]; then
            grep -q '^background_opacity ' "$kitty_conf" ||
                printf '\nbackground_opacity 0.78\n' >> "$kitty_conf"
            grep -q '^background_blur ' "$kitty_conf" ||
                printf 'background_blur 32\n' >> "$kitty_conf"
            chown "$owner:$group" "$kitty_conf"
        elif [[ -f "$src/etc/skel/.config/kitty/kitty.conf" ]]; then
            install -d -o "$owner" -g "$group" "$home/.config/kitty"
            install -m 0644 -o "$owner" -g "$group" \
                "$src/etc/skel/.config/kitty/kitty.conf" "$kitty_conf"
        fi
    fi
done

if command -v qdbus6 >/dev/null; then
    sudo -u live qdbus6 org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true
elif command -v qdbus >/dev/null; then
    sudo -u live qdbus org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true
fi

if [[ -x /usr/bin/synapseos-apply-chrome ]]; then
    sudo -u live /usr/bin/synapseos-apply-chrome >/dev/null 2>&1 || true
fi

echo "Installed Plasma graphics + ssh-agent helpers."
echo "Breeze decorations, bounce scale effect, JetBrains fonts."
echo "Blur: stock KWin blur + frost fallback if Better Blur DX fails."
echo "VMs use software Qt Quick so plasmashell survives virgl dmabuf."
echo "Frost: live stock blur if OpenGL works, else desktop-frost.jpg."
echo "If the desktop fails to start:  export QT_QUICK_BACKEND=software && synapseos-plasma"
echo "Log out and back in, or run:  synapseos-plasma"
echo "Then:  synapseos-check-desktop"
