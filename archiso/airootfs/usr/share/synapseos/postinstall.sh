#!/usr/bin/env bash
# SynapseOS post-install cleanup - runs inside the installed system chroot,
# after Calamares has created the user, initramfs and bootloader.
#
# Anything that must happen *before* the initramfs is built belongs in
# prepare.sh instead. Service enablement is handled by the services-systemd
# module (see /etc/calamares/modules/services-systemd.conf).
set -euo pipefail

# --- Strip live-media systemd units -----------------------------------------
rm -f \
    /etc/systemd/system/pacman-init.service \
    /etc/systemd/system/choose-mirror.service \
    /etc/systemd/system/livecd-alsa-unmuter.service \
    /etc/systemd/system/livecd-talk.service \
    /etc/systemd/system/etc-pacman.d-gnupg.mount \
    /etc/systemd/system/systemd-networkd-wait-online.service.d/wait-for-only-one-interface.conf \
    /etc/systemd/network/20-ethernet.network \
    /etc/systemd/network/20-wlan.network \
    /etc/systemd/network/20-wwan.network
rmdir /etc/systemd/system/systemd-networkd-wait-online.service.d 2>/dev/null || true

# NetworkManager owns networking here, but leave systemd-networkd usable.
systemctl unmask systemd-networkd.service 2>/dev/null || true
systemctl disable systemd-networkd.service 2>/dev/null || true

# --- Remove the live user and its autologin ---------------------------------
rm -f /etc/systemd/system/getty@tty1.service.d/autologin.conf
rmdir /etc/systemd/system/getty@tty1.service.d 2>/dev/null || true
userdel -r -f live 2>/dev/null || true
rm -rf /home/live

# --- Passwordless sudo must not leak into installed systems -----------------
# (The users module already wrote /etc/sudoers.d/10-installer for the wheel
# group, so no replacement rule is needed here.)
rm -f /etc/sudoers.d/10-live

# --- Root stays locked; administration goes through sudo --------------------
passwd -l root 2>/dev/null || true

# --- Recovery account -------------------------------------------------------
# Root is locked and Calamares' sudo rule names the account it created, so a
# failed/forgotten user step would leave the installed system with no way in
# short of booting the ISO again. This account is the fallback. It has full
# sudo (password required) and known credentials, so it is a backdoor by
# design: delete it once the real account works.
#     sudo userdel -r rescue && sudo rm -f /etc/sudoers.d/20-rescue
RESCUE_USER='rescue'
RESCUE_PASS='rescue'

# Only add supplementary groups that actually exist in the installed system.
rescue_groups=()
for g in wheel audio video storage input lp network; do
    if getent group "$g" > /dev/null 2>&1; then
        rescue_groups+=("$g")
    fi
done

if ! id -u "$RESCUE_USER" > /dev/null 2>&1; then
    useradd_args=(-m -c 'SynapseOS recovery account' -s /bin/bash)
    if (( ${#rescue_groups[@]} > 0 )); then
        useradd_args+=(-G "$(IFS=','; echo "${rescue_groups[*]}")")
    fi
    useradd "${useradd_args[@]}" "$RESCUE_USER"
fi
echo "${RESCUE_USER}:${RESCUE_PASS}" | chpasswd

# Recovery login should not run the Plasma welcome wizard. The real user
# created by Calamares already inherits /etc/skel (theme + layout).
install -d -m 0755 -o "$RESCUE_USER" -g "$RESCUE_USER" \
    "/home/${RESCUE_USER}/.config"
printf '[General]\nShouldShow=false\n' \
    > "/home/${RESCUE_USER}/.config/plasma-welcomerc"
chown "$RESCUE_USER:$RESCUE_USER" "/home/${RESCUE_USER}/.config/plasma-welcomerc"

# Installed system must stop at the SDDM greeter, not autologin as live.
rm -f /etc/sddm.conf.d/20-autologin.conf

# wheel alone is not enough: users.conf sets sudoersConfigureWithGroup: false,
# so Calamares' /etc/sudoers.d/10-installer names the created user, not %wheel.
printf '%s ALL=(ALL:ALL) ALL\n' "$RESCUE_USER" > /etc/sudoers.d/20-rescue
chmod 440 /etc/sudoers.d/20-rescue
visudo -cqf /etc/sudoers.d/20-rescue || {
    echo 'postinstall: generated sudoers rule for the recovery account is invalid' >&2
    rm -f /etc/sudoers.d/20-rescue
    exit 1
}

# --- The journal must be persistent on disk -----------------------------------
# The live medium sets Storage=volatile (RAM only) because writing to a squashfs
# overlay is pointless. Copied to an installed system that setting silently
# throws away every log at reboot, so a compositor crash or a failed boot cannot
# be investigated afterwards. Drop the override; systemd's default (Storage=auto
# with /var/log/journal present) keeps logs across reboots.
rm -f /etc/systemd/journald.conf.d/volatile-storage.conf
rmdir /etc/systemd/journald.conf.d 2> /dev/null || true
install -d -m 2755 -g systemd-journal /var/log/journal

# --- The live pacman repo must not linger -----------------------------------
sed -i '/^\[synapseos-local\]/,/^$/d' /etc/pacman.conf

# --- Pacman keyring ---------------------------------------------------------
# The live ISO keeps /etc/pacman.d/gnupg on a tmpfs (etc-pacman.d-gnupg.mount)
# and fills it at boot with pacman-init.service. Calamares unpackfs copies
# the squashfs, not that tmpfs, so the installed system only gets the empty
# mount point. The units above are then deleted. Result: `pacman -S` dies
# with "keyring is not writable" / "Public keyring not found" and a 300+
# package upgrade cannot even start.
rm -f /etc/systemd/system/multi-user.target.wants/pacman-init.service \
      /etc/systemd/system/multi-user.target.wants/choose-mirror.service
rm -rf /etc/pacman.d/gnupg
install -d -m 0755 /etc/pacman.d/gnupg
pacman-key --init
pacman-key --populate archlinux

# --- Remove the installer itself --------------------------------------------
rm -f /usr/share/applications/synapseos-installer.desktop \
      /etc/xdg/autostart/synapseos-installer.desktop \
      /usr/bin/synapseos-installer \
      /usr/share/pixmaps/synapseos-installer.png
rm -rf /etc/calamares
pacman -Rns --noconfirm calamares 2>/dev/null || true

# --- Remove live-media helpers ----------------------------------------------
rm -f \
    /root/.automated_script.sh \
    /root/.zlogin \
    /usr/local/bin/choose-mirror \
    /usr/local/bin/Installation_guide \
    /usr/local/bin/livecd-sound

# The live motd is replaced, not just deleted: every console login must show
# that a known-password recovery account exists until it is removed.
cat > /etc/motd << EOF

SynapseOS

A recovery account is present: ${RESCUE_USER} / ${RESCUE_PASS} (full sudo).
It exists so a forgotten password cannot lock you out. Delete it once your
own account works:

    sudo userdel -r ${RESCUE_USER} && sudo rm -f /etc/sudoers.d/20-rescue
    sudo rm -f /etc/motd

EOF
chmod 644 /etc/motd

# Installer scratch only. Keep dock.js, gtk-theme-name and anything else the
# installed desktop still reads from this tree. The assistant lives in
# /usr/lib/synapseos and is not touched here.
rm -rf /usr/share/synapseos/boot
rm -f /usr/share/synapseos/prepare.sh /usr/share/synapseos/postinstall.sh \
    /usr/share/synapseos/inject-plymouth.sh

exit 0
