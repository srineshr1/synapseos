#!/usr/bin/env bash
# Locate airootfs.sfs for Calamares unpackfs and publish a stable path.
#
# On real USB installs with enough free RAM, archiso's default copytoram=auto
# copies the squashfs into /run/archiso/copytoram/ and unmounts
# /run/archiso/bootmnt. Calamares was hard-coded to the bootmnt path, so
# unpackfs failed with "source filesystem does not exist" (often reported as
# "ISO not found"). VMs usually keep bootmnt (optical device, or too little
# RAM for the auto threshold), which is why the same ISO could install in a
# VM and fail on bare metal.
set -euo pipefail

STABLE_DIR=/run/synapseos
STABLE_SFS="${STABLE_DIR}/airootfs.sfs"

is_rootfs_image() {
    local f=$1
    [[ -f $f && -r $f ]] || return 1
    case $f in
        *.sfs|*.erofs) return 0 ;;
        *) return 1 ;;
    esac
}

find_rootfs_image() {
    local p candidates=()

    # Prefer copytoram: present after bootmnt has been unmounted.
    candidates+=(
        /run/archiso/copytoram/airootfs.sfs
        /run/archiso/copytoram/airootfs.erofs
        /run/archiso/bootmnt/synapseos/x86_64/airootfs.sfs
        /run/archiso/bootmnt/synapseos/x86_64/airootfs.erofs
    )

    if [[ -d /run/archiso/bootmnt ]]; then
        while IFS= read -r -d '' p; do
            candidates+=("$p")
        done < <(find /run/archiso/bootmnt -maxdepth 3 -type f \
            \( -name 'airootfs.sfs' -o -name 'airootfs.erofs' \) -print0 2>/dev/null || true)
    fi

    if [[ -d /run/archiso ]]; then
        while IFS= read -r -d '' p; do
            candidates+=("$p")
        done < <(find /run/archiso -maxdepth 4 -type f \
            \( -name 'airootfs.sfs' -o -name 'airootfs.erofs' \) -print0 2>/dev/null || true)
    fi

    # Last resort: removable media mounts (Ventoy/file-copy layouts).
    local base
    for base in /run/media /media /mnt; do
        [[ -d $base ]] || continue
        while IFS= read -r -d '' p; do
            candidates+=("$p")
        done < <(find "$base" -maxdepth 6 -type f \
            \( -name 'airootfs.sfs' -o -name 'airootfs.erofs' \) -print0 2>/dev/null || true)
    done

    local c real
    for c in "${candidates[@]}"; do
        is_rootfs_image "$c" || continue
        real=$(readlink -f -- "$c" 2>/dev/null || printf '%s\n' "$c")
        if is_rootfs_image "$real"; then
            printf '%s\n' "$real"
            return 0
        fi
    done
    return 1
}

if [[ -L $STABLE_SFS || -e $STABLE_SFS ]]; then
    if [[ -e $STABLE_SFS ]]; then
        # Already published and still readable (e.g. installer re-run).
        exit 0
    fi
    rm -f -- "$STABLE_SFS"
fi

img=$(find_rootfs_image) || {
    echo 'synapseos-locate-rootfs: installation image (airootfs.sfs) not found.' >&2
    echo '  Checked /run/archiso/copytoram, /run/archiso/bootmnt, and mounted media.' >&2
    echo '  The live medium may have been removed, or this is not a SynapseOS live boot.' >&2
    exit 1
}

install -d -m 0755 "$STABLE_DIR"
ln -sfn -- "$img" "$STABLE_SFS"

# If the image is erofs, rewrite unpackfs so Calamares mounts it correctly.
# Squashfs is the build default; leave sourcefs alone when already squashfs.
unpack_conf=/etc/calamares/modules/unpackfs.conf
if [[ -f $unpack_conf ]]; then
    case $img in
        *.erofs)
            if grep -q 'sourcefs:[[:space:]]*squashfs' "$unpack_conf"; then
                sed -i 's/sourcefs:[[:space:]]*squashfs/sourcefs: erofs/' "$unpack_conf"
            fi
            ;;
        *.sfs)
            if grep -q 'sourcefs:[[:space:]]*erofs' "$unpack_conf"; then
                sed -i 's/sourcefs:[[:space:]]*erofs/sourcefs: squashfs/' "$unpack_conf"
            fi
            ;;
    esac
    # Point source at the stable path (idempotent).
    if grep -qE '^[[:space:]]*source:[[:space:]]*' "$unpack_conf"; then
        sed -i "s|^[[:space:]]*source:[[:space:]].*|      source: ${STABLE_SFS}|" "$unpack_conf"
    fi
fi

echo "synapseos-locate-rootfs: ${img} -> ${STABLE_SFS}"
exit 0
