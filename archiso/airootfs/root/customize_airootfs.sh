#!/usr/bin/env bash
# SynapseOS airootfs customization - runs in the built chroot
set -euo pipefail

# Live user
useradd -m -G wheel,audio,video,storage,input -s /usr/bin/zsh live
echo "live:live" | chpasswd
# Passwordless sudo in the live session
printf '%%wheel ALL=(ALL:ALL) NOPASSWD: ALL\n' > /etc/sudoers.d/10-live
chmod 440 /etc/sudoers.d/10-live

# Auto-start the COSMIC session on the live user's first login.
# synapseos-cosmic wraps the cosmic-session package's own /usr/bin/start-cosmic,
# logs to ~/.cache/synapseos/cosmic-session.log and returns to the shell on
# failure instead of exec'ing, so a compositor that dies leaves a diagnosable
# console rather than a getty restart loop. SYNAPSEOS_COSMIC_AUTOSTART guards
# against recursion: start-cosmic re-execs itself through a login shell, which
# sources this file again.
cat > /home/live/.zprofile << 'EOF'
if [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${DISPLAY:-}" ] && [ "$(tty)" = "/dev/tty1" ] &&
   [ -z "${SYNAPSEOS_COSMIC_AUTOSTART:-}" ]; then
    if grep -qw nodesktop /proc/cmdline; then
        printf '\nnodesktop on the kernel command line: COSMIC was not started.\n'
        printf 'Start it with:  synapseos-cosmic     Collect diagnostics:  synapseos-logs\n\n'
    else
        export SYNAPSEOS_COSMIC_AUTOSTART=1
        synapseos-cosmic
    fi
fi
EOF
chown live:live /home/live/.zprofile

# Network: NetworkManager instead of systemd-networkd on the live media
systemctl mask systemd-networkd.service
systemctl enable NetworkManager.service

# Generic live helpers kept from upstream
systemctl enable pacman-init.service choose-mirror.service

# The calamares package ships its own launcher that runs `sh -c "pkexec
# calamares"`. On a Wayland session pkexec drops WAYLAND_DISPLAY and the window
# never appears, so hide it and leave only "Install SynapseOS", which forwards
# the session environment (see /usr/bin/synapseos-installer).
rm -f /usr/share/applications/calamares.desktop

# The local build repo must not linger in the live pacman.conf
sed -i '/^\[synapseos-local\]/,/^$/d' /etc/pacman.conf

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