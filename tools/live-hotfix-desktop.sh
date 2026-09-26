#!/usr/bin/env bash
# Apply Hyprland / Caelestia desktop bits on a running SynapseOS live session
# that was built before those files landed in the ISO.
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
    echo "run as root: sudo $0" >&2
    exit 1
fi

src="$(cd "$(dirname "$0")/.." && pwd)/archiso/airootfs"

install -m 0755 "$src/etc/profile.d/synapseos-graphics.sh" /etc/profile.d/synapseos-graphics.sh
install -m 0755 "$src/etc/profile.d/synapseos-ssh-agent.sh" /etc/profile.d/synapseos-ssh-agent.sh
install -m 0755 "$src/usr/bin/synapseos-safe-graphics" /usr/bin/synapseos-safe-graphics
if [[ -f "$src/usr/lib/systemd/user-environment-generators/30-synapseos-graphics" ]]; then
    install -d /usr/lib/systemd/user-environment-generators
    install -m 0755 \
        "$src/usr/lib/systemd/user-environment-generators/30-synapseos-graphics" \
        /usr/lib/systemd/user-environment-generators/30-synapseos-graphics
fi
if [[ -x "$src/usr/bin/synapseos-session" ]]; then
    install -m 0755 "$src/usr/bin/synapseos-session" /usr/bin/synapseos-session
fi
if [[ -x "$src/usr/bin/synapseos-check-desktop" ]]; then
    install -m 0755 "$src/usr/bin/synapseos-check-desktop" /usr/bin/synapseos-check-desktop
fi
if [[ -x "$src/usr/bin/synapseos-start-desktop" ]]; then
    install -m 0755 "$src/usr/bin/synapseos-start-desktop" /usr/bin/synapseos-start-desktop
fi
if [[ -x "$src/usr/bin/synapseos-installer" ]]; then
    install -m 0755 "$src/usr/bin/synapseos-installer" /usr/bin/synapseos-installer
fi
if [[ -f "$src/etc/fonts/conf.d/50-synapseos.conf" ]]; then
    install -d /etc/fonts/conf.d
    install -m 0644 "$src/etc/fonts/conf.d/50-synapseos.conf" \
        /etc/fonts/conf.d/50-synapseos.conf
    fc-cache -f /usr/share/fonts >/dev/null 2>&1 || true
fi
if [[ -f "$src/etc/environment.d/50-synapseos.conf" ]]; then
    install -d /etc/environment.d
    install -m 0644 "$src/etc/environment.d/50-synapseos.conf" \
        /etc/environment.d/50-synapseos.conf
fi

_install_caelestia_overrides() {
    local home="$1" owner="$2"
    [[ -d "$home" ]] || return 0
    install -d -m 0755 -o "$owner" -g "$owner" "$home/.config/caelestia"
    if [[ -f "$src/etc/skel/.config/caelestia/hypr-user.lua" ]]; then
        install -o "$owner" -g "$owner" -m 0644 \
            "$src/etc/skel/.config/caelestia/hypr-user.lua" \
            "$home/.config/caelestia/hypr-user.lua"
    fi
    if [[ -f "$src/etc/skel/.config/caelestia/shell.json" ]]; then
        install -o "$owner" -g "$owner" -m 0644 \
            "$src/etc/skel/.config/caelestia/shell.json" \
            "$home/.config/caelestia/shell.json"
    fi
}

_install_caelestia_overrides /etc/skel root

live_home=/home/live
if [[ -d "$live_home" ]]; then
    cat > "$live_home/.zprofile" << 'EOF'
if [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${DISPLAY:-}" ] && [ "$(tty)" = "/dev/tty1" ] &&
   [ -z "${SYNAPSEOS_SESSION_AUTOSTART:-}" ]; then
    if grep -qw nodesktop /proc/cmdline; then
        printf '\nnodesktop on the kernel command line: the desktop was not started.\n'
        printf 'Start it with:  synapseos-session     Collect diagnostics:  synapseos-logs\n\n'
    else
        export SYNAPSEOS_SESSION_AUTOSTART=1
        synapseos-session
    fi
fi
EOF
    chown live:live "$live_home/.zprofile"
    _install_caelestia_overrides "$live_home" live
fi

echo
echo "Hotfix applied. VMs use software Qt Quick (and llvmpipe when virtio has no 3D)"
echo "so the Caelestia bar can paint. Restart the session:"
echo "  loginctl terminate-user live     # or reboot"
echo "If the desktop fails to start:  synapseos-session"
echo "Log: ~/.cache/synapseos/session.log"
