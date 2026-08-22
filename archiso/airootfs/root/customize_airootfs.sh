#!/usr/bin/env bash
# SynapseOS airootfs customization - runs in the built chroot
set -euo pipefail

# Live user
useradd -m -G wheel,audio,video,storage,input -s /usr/bin/zsh live
echo "live:live" | chpasswd
# Passwordless sudo in the live session
printf '%%wheel ALL=(ALL:ALL) NOPASSWD: ALL\n' > /etc/sudoers.d/10-live
chmod 440 /etc/sudoers.d/10-live

# Auto-start Hyprland on the live user's first login from tty1.
# synapseos-session wraps Hyprland, logs to ~/.cache/synapseos/session.log
# and returns to the shell on failure instead of exec'ing, so a compositor
# that dies leaves a diagnosable console rather than a getty restart loop.
cat > /home/live/.zprofile << 'EOF'
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
chown live:live /home/live/.zprofile

# Also drop the installer into the live user's autostart. Hyprland starts
# graphical-session.target (hypr-user.lua), which picks up this and
# /etc/xdg/autostart/; synapseos-installer --autostart takes a lock so
# only one Calamares window appears.
install -d -m 0755 -o live -g live /home/live/.config/autostart
install -o live -g live -m 0644 \
    /etc/xdg/autostart/synapseos-installer.desktop \
    /home/live/.config/autostart/synapseos-installer.desktop

# Network: NetworkManager instead of systemd-networkd on the live media
systemctl mask systemd-networkd.service
systemctl enable NetworkManager.service
systemctl enable bluetooth.service

# Generic live helpers kept from upstream
systemctl enable pacman-init.service choose-mirror.service

# Stable path for airootfs.sfs before Calamares (copytoram may drop bootmnt)
systemctl enable synapseos-locate-rootfs.service

# --- SSH agent ---------------------------------------------------------------
# systemctl --user import-environment logs
#   Environment variable $SSH_AUTH_SOCK not set, ignoring.
# when the socket is missing. Enable gcr's agent for every user; the
# profile.d snippet exports the socket so the import has a value.
systemctl --global enable gcr-ssh-agent.socket
# OS MCP broker: starts with the graphical session for every user.
systemctl --global enable synapse-core.service
find /usr/lib/synapseos -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true

# Optional: a missing module must not block login.
_add_gnome_keyring_pam() {
    local pam_file="$1"
    [[ -f "$pam_file" ]] || return 0
    grep -q 'pam_gnome_keyring\.so' "$pam_file" && return 0
    printf '\nauth       optional     pam_gnome_keyring.so\nsession    optional     pam_gnome_keyring.so auto_start\n' >> "$pam_file"
}
_add_gnome_keyring_pam /etc/pam.d/login
_add_gnome_keyring_pam /etc/pam.d/sddm
_add_gnome_keyring_pam /etc/pam.d/greetd
unset -f _add_gnome_keyring_pam

# The calamares package ships its own launcher that runs `sh -c "pkexec
# calamares"`. On a Wayland session pkexec drops WAYLAND_DISPLAY and the window
# never appears, so hide it and leave only "Install SynapseOS", which forwards
# the session environment (see /usr/bin/synapseos-installer).
rm -f /usr/share/applications/calamares.desktop

# Kickoff + wired-network icons: a 3x3 grid and a globe, not the KDE K
# or Papirus computer/ethernet glyph.
_icon_src=/usr/share/synapseos/icons
if [[ -d "$_icon_src" ]]; then
    install -d /usr/share/icons/hicolor/scalable/apps
    install -m 0644 "$_icon_src/synapseos-launcher.svg" \
        /usr/share/icons/hicolor/scalable/apps/synapseos-launcher.svg
    install -m 0644 "$_icon_src/synapseos-launcher.svg" \
        /usr/share/pixmaps/synapseos-launcher.svg
    for _theme in Papirus-Dark Papirus; do
        for _dir in /usr/share/icons/"$_theme"/*/apps /usr/share/icons/"$_theme"/scalable/apps; do
            [[ -d "$_dir" ]] || continue
            ln -sfn "$_icon_src/synapseos-launcher.svg" "$_dir/start-here-kde.svg"
            ln -sfn "$_icon_src/synapseos-launcher.svg" "$_dir/synapseos-launcher.svg"
        done
        for _dir in /usr/share/icons/"$_theme"/*/status /usr/share/icons/"$_theme"/scalable/status; do
            [[ -d "$_dir" ]] || continue
            for _name in network-wired network-wired-activated network-wired-acquiring \
                network-wired-available network-wired-disconnected network-wired-error \
                network-wired-no-route network-wired-offline network-wired-unavailable \
                nm-device-wired network-wired-activated-private; do
                ln -sfn "$_icon_src/network-wired.svg" "$_dir/${_name}.svg"
            done
        done
    done
    gtk-update-icon-cache -q /usr/share/icons/hicolor 2>/dev/null || true
    gtk-update-icon-cache -q /usr/share/icons/Papirus-Dark 2>/dev/null || true
fi
unset _icon_src _theme _dir _name

# Qt will not see JetBrains if the live image has no fontconfig cache.
if command -v fc-cache >/dev/null; then
    fc-cache -f /usr/share/fonts >/dev/null 2>&1 || true
fi

# The local build repo must not linger in the live pacman.conf
sed -i '/^\[synapseos-local\]/,/^$/d' /etc/pacman.conf

# Live + installed splash. Do not pass -R: mkarchiso rebuilds the
# archiso initramfs after this script, and the installed image is
# rebuilt by Calamares' initcpio module.
if command -v plymouth-set-default-theme >/dev/null; then
    plymouth-set-default-theme synapseos || true
fi

# --- Stash the kernel and microcode outside /boot ----------------------------
# mkarchiso empties /boot in the pacstrap dir (_cleanup_pacstrap_dir) *before*
# building airootfs.sfs, so the installed system - which is a copy of that
# squashfs - would have no kernel at all and `mkinitcpio -P` fails with
#   ERROR: Invalid option -k -- '/boot/vmlinuz-linux' must be readable
# This copy lives outside /boot, survives the cleanup, and is put back by
# /usr/share/synapseos/prepare.sh during installation (removed afterwards by
# postinstall.sh). /run/archiso is not an option there: Calamares runs the
# script inside the target chroot, where the live medium is not mounted.
install -d -m 0755 /usr/share/synapseos/boot
for _f in vmlinuz-linux intel-ucode.img amd-ucode.img; do
    if [[ -e "/boot/${_f}" ]]; then
        cp -a "/boot/${_f}" /usr/share/synapseos/boot/
    fi
done
[[ -e /usr/share/synapseos/boot/vmlinuz-linux ]] || {
    echo 'customize_airootfs: /boot/vmlinuz-linux missing, cannot stash kernel' >&2
    exit 1
}

exit 0