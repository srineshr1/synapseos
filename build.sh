#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

WORK_DIR="${WORK_DIR:-./work}"
OUT_DIR="${OUT_DIR:-./out}"

# [synapseos-local] holds the packages that are not in the official repos
# (calamares, the AI agents, helium, paru). pacman needs an absolute path, so
# point it at wherever this checkout happens to live.
if [[ ! -e archiso/repo/synapseos-local.db ]]; then
    echo "error: archiso/repo/synapseos-local.db is missing." >&2
    echo "       Run ./tools/build-aur.sh first (see README)." >&2
    exit 1
fi
python3 - "$PWD" <<'EOF'
import pathlib, re, sys
conf = pathlib.Path("archiso/pacman.conf")
text = conf.read_text()
new = re.sub(r"^Server = file://.*$", f"Server = file://{sys.argv[1]}/archiso/repo",
             text, flags=re.MULTILINE)
if new != text:
    conf.write_text(new)
    print(f"Updated [synapseos-local] server path to {sys.argv[1]}/archiso/repo")
EOF

# mkarchiso skips steps whose run-once markers exist in work/, so stale markers
# from an older build silently produce a stale ISO. Always start fresh (pacman's
# /var/cache keeps downloads, so this is cheap).
#
# DANGER: mkarchiso bind-mounts /dev (devtmpfs), /run, /sys and efivarfs into
# the pacstrap dir. An interrupted build leaves those mounts behind, and a plain
# `rm -rf work` then recurses into the host's real devtmpfs and EFI variable
# store, which can break the running system or its UEFI variables. Unmount
# first (deepest mount first) and keep rm inside a single filesystem.
if [[ -d "$WORK_DIR" ]]; then
    work_abs="$(realpath "$WORK_DIR")"
    mapfile -t stale_mounts < <(findmnt -rno TARGET | grep "^${work_abs}/" | sort -r)
    if (( ${#stale_mounts[@]} )); then
        echo "Unmounting ${#stale_mounts[@]} stale mount(s) left by an interrupted build:"
        for mountpoint in "${stale_mounts[@]}"; do
            echo "  umount ${mountpoint}"
            sudo umount -R "$mountpoint" 2>/dev/null || sudo umount -l "$mountpoint"
        done
        if findmnt -rno TARGET | grep -q "^${work_abs}/"; then
            echo "error: mounts remain under ${work_abs}; refusing to delete it." >&2
            findmnt -rno TARGET | grep "^${work_abs}/" >&2
            exit 1
        fi
    fi
    sudo rm -rf --one-file-system "$work_abs"
fi
# Leftover build dirs on the /tmp tmpfs must not be reused or starve it
sudo rm -rf --one-file-system /tmp/synapse-iso-work

# Keep the previous ISO as *.iso.prev rather than deleting it: mkarchiso can
# still fail during validation, and a failed run must not cost the last good
# image. Only one *.iso remains, so the result is still unambiguous.
if compgen -G "${OUT_DIR}/*.iso" > /dev/null; then
    for iso in "${OUT_DIR}"/*.iso; do
        sudo mv -f -- "$iso" "${iso}.prev"
        echo "Previous ISO kept at ${iso}.prev"
    done
fi
sudo rm -f -- "${OUT_DIR}"/*.iso.sha512 "${OUT_DIR}"/*.iso.sig 2>/dev/null || true

sudo mkarchiso -v -r -w "$WORK_DIR" -o "$OUT_DIR" archiso

echo "ISO built: $(ls -lh "${OUT_DIR}"/*.iso 2>/dev/null | awk '{print $NF, $5}')"
