#!/usr/bin/env bash
# Boot the newest SynapseOS ISO with OpenGL and a writable disk.
#
# Never run this with sudo. qemu as root cannot talk to the session GPU
# ("Authorization required" / "OpenGL is not supported by display gtk").
# sudo ./build.sh leaves out/ owned by root — the disk then goes under
# ~/.cache/synapseos/ instead.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if (( EUID == 0 )); then
    echo "do not use sudo. qemu needs your user session for the GPU." >&2
    echo "  ./tools/run-iso.sh" >&2
    if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != root ]]; then
        exec sudo -u "$SUDO_USER" -H -- "$0" "$@"
    fi
    exit 1
fi

ISO=""
if [[ "${1:-}" == *.iso && -f "${1:-}" ]]; then
    ISO="$1"
    shift
fi
if [[ -z "$ISO" ]]; then
    ISO="$(ls -1t "$ROOT"/out/synapseos-*.iso 2>/dev/null | head -1 || true)"
fi
if [[ -z "$ISO" || ! -f "$ISO" ]]; then
    echo "no ISO found. build one with ./build.sh or pass a path." >&2
    exit 1
fi

cache_disk="${XDG_CACHE_HOME:-$HOME/.cache}/synapseos/synapseos-vm.qcow2"
out_disk="$ROOT/out/synapseos-vm.qcow2"
if [[ -n "${SYNAPSEOS_QEMU_DISK:-}" ]]; then
    DISK="$SYNAPSEOS_QEMU_DISK"
elif [[ -e "$out_disk" && -w "$out_disk" ]]; then
    DISK="$out_disk"
elif [[ -d "$ROOT/out" && -w "$ROOT/out" && ! -e "$out_disk" ]]; then
    DISK="$out_disk"
else
    DISK="$cache_disk"
    if [[ -e "$out_disk" && ! -w "$out_disk" ]]; then
        echo "out/synapseos-vm.qcow2 is not writable (sudo ./build.sh)." >&2
        echo "using $DISK  — or: sudo chown -R \"\$USER:\$USER\" \"$ROOT/out\"" >&2
    fi
fi

DISK_SIZE="${SYNAPSEOS_QEMU_DISK_SIZE:-40G}"
if [[ ! -f "$DISK" ]]; then
    mkdir -p "$(dirname "$DISK")"
    echo "creating $DISK ($DISK_SIZE, sparse)"
    qemu-img create -f qcow2 "$DISK" "$DISK_SIZE" >/dev/null
fi

# gtk,gl=on fails on Hyprland. SDL + XWayland is the reliable virgl path.
if [[ -n "${SYNAPSEOS_QEMU_DISPLAY:-}" ]]; then
    display="$SYNAPSEOS_QEMU_DISPLAY"
else
    display="sdl,gl=on"
    export SDL_VIDEODRIVER="${SDL_VIDEODRIVER:-x11}"
fi

MEM="${SYNAPSEOS_QEMU_MEM:-8192}"
echo "booting $ISO ($display, virgl hostmem=1G) disk=$DISK"
exec qemu-system-x86_64 \
    -enable-kvm -machine q35,accel=kvm \
    -m "$MEM" -cpu host -smp "${SYNAPSEOS_QEMU_SMP:-4}" \
    -cdrom "$ISO" -boot order=d \
    -drive "file=${DISK},if=virtio,format=qcow2,cache=writeback,discard=unmap" \
    -device virtio-vga-gl,hostmem=1G \
    -display "$display" \
    "$@"
