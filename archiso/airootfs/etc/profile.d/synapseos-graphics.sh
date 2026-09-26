# SynapseOS: Hyprland + Quickshell renderer workarounds.
#
#   auto  (default)  GPU compositor when the guest actually has 3D; VMs still
#                    get software Qt Quick (virgl dmabuf kills Caelestia)
#   safe             llvmpipe (`safegfx` on the kernel cmdline, or
#                    /etc/synapseos/safe-graphics)
#   off              /etc/synapseos/no-safe-graphics exists: never apply
#
# Two VM failure modes look the same from the seat: no bar, no windows.
#
#   1. virtio-vga without 3D (virt-manager default). Hyprland/Aquamarine
#      needs GLES; WLR_RENDERER=pixman does nothing on Hyprland 0.55+.
#      Force Mesa llvmpipe so the compositor can paint.
#   2. virtio-vga-gl (virgl). Hyprland can run, but Quickshell dies on
#      "importing the supplied dmabufs failed". Software Qt Quick + the
#      basic render loop is required: Caelestia's shell.qml sets
#      QSG_RENDER_LOOP=threaded via DefaultEnv, which does not mix with
#      QT_QUICK_BACKEND=software.
#
# `cosmicsafe` is still accepted as an alias for safegfx so older boot
# entries keep working.

# Return 0 if a virtio-gpu device advertises VIRGL (feature bit 0).
_synapseos_virtio_gpu_has_virgl() {
    _synapseos_d=
    _synapseos_driver=
    _synapseos_feat=
    for _synapseos_d in /sys/bus/virtio/devices/virtio*; do
        [ -e "${_synapseos_d}/driver" ] || continue
        _synapseos_driver=$(basename "$(readlink -f "${_synapseos_d}/driver" 2>/dev/null || true)" 2>/dev/null || true)
        [ "${_synapseos_driver}" = virtio_gpu ] || continue
        _synapseos_feat=$(tr -d '[:space:]' < "${_synapseos_d}/features" 2>/dev/null || true)
        [ -n "${_synapseos_feat}" ] || continue
        case "${_synapseos_feat}" in
            1*)
                unset _synapseos_d _synapseos_driver _synapseos_feat
                return 0
                ;;
        esac
        if [ "${_synapseos_feat}" -eq "${_synapseos_feat}" ] 2>/dev/null; then
            if [ $((_synapseos_feat & 1)) -eq 1 ]; then
                unset _synapseos_d _synapseos_driver _synapseos_feat
                return 0
            fi
        fi
    done
    unset _synapseos_d _synapseos_driver _synapseos_feat
    return 1
}

_synapseos_force_llvmpipe() {
    export LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}"
    export GALLIUM_DRIVER="${GALLIUM_DRIVER:-llvmpipe}"
    export AQ_NO_MODIFIERS="${AQ_NO_MODIFIERS:-1}"
    export QT_QUICK_BACKEND="${QT_QUICK_BACKEND:-software}"
    export QSG_RHI_BACKEND="${QSG_RHI_BACKEND:-software}"
    export QSG_RENDER_LOOP="${QSG_RENDER_LOOP:-basic}"
    # Leftover wlroots clients; Hyprland itself ignores this.
    export WLR_RENDERER="${WLR_RENDERER:-pixman}"
    if [ -z "${VK_ICD_FILENAMES:-}" ]; then
        for _synapseos_icd in /usr/share/vulkan/icd.d/lvp_icd*.json; do
            if [ -f "${_synapseos_icd}" ]; then
                export VK_ICD_FILENAMES="${_synapseos_icd}"
                break
            fi
        done
        unset _synapseos_icd
    fi
}

if [ ! -e /etc/synapseos/no-safe-graphics ]; then
    _synapseos_gfx=auto

    if [ -e /etc/synapseos/safe-graphics ]; then
        _synapseos_gfx=safe
    elif grep -Eqw 'safegfx|cosmicsafe' /proc/cmdline 2>/dev/null; then
        _synapseos_gfx=safe
    fi

    _synapseos_vm=0
    if command -v systemd-detect-virt >/dev/null 2>&1 && systemd-detect-virt -q; then
        _synapseos_vm=1
        export SYNAPSEOS_VM="${SYNAPSEOS_VM:-1}"
        export AQ_NO_MODIFIERS="${AQ_NO_MODIFIERS:-1}"
        # Caelestia shell.qml: //@ pragma DefaultEnv QSG_RENDER_LOOP=threaded
        export QT_QUICK_BACKEND="${QT_QUICK_BACKEND:-software}"
        export QSG_RHI_BACKEND="${QSG_RHI_BACKEND:-software}"
        export QSG_RENDER_LOOP="${QSG_RENDER_LOOP:-basic}"
    fi

    case "${_synapseos_gfx}" in
        safe)
            _synapseos_force_llvmpipe
            ;;
        auto)
            if [ "${_synapseos_vm}" -eq 1 ]; then
                if [ -d /sys/module/virtio_gpu ] && ! _synapseos_virtio_gpu_has_virgl; then
                    # virt-manager "Virtio" video with 3D off.
                    _synapseos_force_llvmpipe
                elif [ ! -e /dev/dri/card0 ] && [ ! -e /dev/dri/card1 ]; then
                    _synapseos_force_llvmpipe
                fi
            fi
            ;;
    esac

    unset _synapseos_gfx _synapseos_vm
fi

unset -f _synapseos_virtio_gpu_has_virgl _synapseos_force_llvmpipe

true
