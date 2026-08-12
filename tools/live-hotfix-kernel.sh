#!/usr/bin/env bash
# Run this INSIDE the live session (sudo), BEFORE launching "Install SynapseOS",
# on an ISO built before the kernel-stash fix. It is not needed on ISOs built
# from the current profile.
#
# Why: mkarchiso deletes every file under /boot before building airootfs.sfs, so
# the installed system starts with an empty /boot and Calamares' initcpio step
# dies with
#     ERROR: Invalid option -k -- '/boot/vmlinuz-linux' must be readable
#
# This patches the live Calamares config (it lives on the writable overlay) to
# bind-mount the live medium into the target and copy the kernel there before
# mkinitcpio runs. Nothing is written to any disk; re-run the installer after.
set -euo pipefail

if (( EUID != 0 )); then
    echo "run as root: sudo $0" >&2
    exit 1
fi

CAL=/etc/calamares/modules
MOUNT="$CAL/mount.conf"
PREP="$CAL/shellprocess-prepare.conf"
BOOTMNT=/run/archiso/bootmnt

[[ -f "$MOUNT" && -f "$PREP" ]] || { echo "not a SynapseOS live session: $CAL missing" >&2; exit 1; }
[[ -d "$BOOTMNT" ]] || { echo "$BOOTMNT is not mounted; is this an ISO boot?" >&2; exit 1; }

kernel=$(compgen -G "$BOOTMNT/*/boot/x86_64/vmlinuz-linux" | head -n1 || true)
[[ -n "$kernel" ]] || { echo "no vmlinuz-linux found under $BOOTMNT" >&2; exit 1; }
boot_dir=${kernel%/vmlinuz-linux}
echo "live kernel: $kernel"

# 1. make the live medium visible inside the target chroot
if grep -q "$BOOTMNT" "$MOUNT"; then
    echo "$MOUNT already patched"
else
    cp -n "$MOUNT" "$MOUNT.orig"
    python3 - "$MOUNT" "$BOOTMNT" << 'PY'
import sys
path, bootmnt = sys.argv[1], sys.argv[2]
text = open(path).read()
entry = f"    - device: {bootmnt}\n      mountPoint: {bootmnt}\n      options: [ bind ]\n"
marker = "\nbtrfsSubvolumes:"
if marker in text:
    text = text.replace(marker, "\n" + entry + marker, 1)
else:
    text = text.rstrip("\n") + "\n" + entry
open(path, "w").write(text)
PY
    echo "patched $MOUNT"
fi

# 2. copy the kernel into the target before prepare.sh / initcpiocfg / initcpio.
#    Commands run inside the chroot; a leading '-' means "ignore failure"
#    (the microcode images are only on some media).
if grep -q 'vmlinuz-linux' "$PREP"; then
    echo "$PREP already patched"
else
    cp -n "$PREP" "$PREP.orig"
    cat > "$PREP" << EOF
---
dontChroot: false
timeout: 600
script:
  - "/usr/bin/install -d -m 0755 /boot"
  - "/usr/bin/cp -a $boot_dir/vmlinuz-linux /boot/vmlinuz-linux"
  - "-/usr/bin/cp -a $boot_dir/intel-ucode.img /boot/intel-ucode.img"
  - "-/usr/bin/cp -a $boot_dir/amd-ucode.img /boot/amd-ucode.img"
  - "/usr/share/synapseos/prepare.sh"
EOF
    echo "patched $PREP"
fi

echo
echo "Done. Launch 'Install SynapseOS' now."
