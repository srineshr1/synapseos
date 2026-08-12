#!/usr/bin/env bash
# SynapseOS pre-initramfs fixups - runs inside the installed system chroot,
# before Calamares' initcpiocfg/initcpio steps.
#
# The target filesystem is a copy of the live medium, so it still carries the
# archiso mkinitcpio configuration. Left in place it would produce an initramfs
# that only boots from ISO media; deleted without a replacement, mkinitcpio
# would have no preset at all and produce no initramfs.
set -euo pipefail

rm -f /etc/mkinitcpio.conf.d/archiso.conf

cat > /etc/mkinitcpio.d/linux.preset << 'EOF'
# mkinitcpio preset file for the 'linux' package
#
# Mirrors the stock preset shipped by the linux package. The UKI entries stay
# commented out: enabling them makes `mkinitcpio -P` also try to build
# /boot/EFI/Linux/*.efi, which this profile does not use.

#ALL_config="/etc/mkinitcpio.conf"
ALL_kver="/boot/vmlinuz-linux"

PRESETS=('default' 'fallback')

#default_config="/etc/mkinitcpio.conf"
default_image="/boot/initramfs-linux.img"
#default_uki="/boot/EFI/Linux/arch-linux.efi"
#default_options="--splash /usr/share/systemd/bootctl/splash-arch.bmp"

#fallback_config="/etc/mkinitcpio.conf"
fallback_image="/boot/initramfs-linux-fallback.img"
fallback_options="-S autodetect"
EOF

# --- Restore the kernel and microcode into /boot ------------------------------
# mkarchiso deletes every file under /boot before it builds airootfs.sfs, so the
# freshly unpacked target has an empty /boot. Without the kernel, mkinitcpio
# (and later grub-mkconfig) fail:
#   ERROR: Invalid option -k -- '/boot/vmlinuz-linux' must be readable
# customize_airootfs.sh stashed the files in /usr/share/synapseos/boot/.
install -d -m 0755 /boot
for f in vmlinuz-linux intel-ucode.img amd-ucode.img; do
    if [[ ! -e "/boot/${f}" && -e "/usr/share/synapseos/boot/${f}" ]]; then
        cp -a "/usr/share/synapseos/boot/${f}" "/boot/${f}"
    fi
done

if [[ ! -r /boot/vmlinuz-linux ]]; then
    echo 'prepare.sh: /boot/vmlinuz-linux is missing; cannot build an initramfs.' >&2
    echo '            The ISO was built without the kernel stash in' >&2
    echo '            /usr/share/synapseos/boot/ - rebuild it.' >&2
    exit 1
fi

# Drop any stale initramfs; the initcpio module regenerates it next.
rm -f /boot/initramfs-linux.img /boot/initramfs-linux-fallback.img

exit 0
