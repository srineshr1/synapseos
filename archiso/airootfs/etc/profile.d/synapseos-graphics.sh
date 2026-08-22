# SynapseOS: Hyprland + Quickshell renderer workarounds.
#
#   auto  (default)  no compositor override; VMs still get software Qt Quick
#   safe             WLR_RENDERER=pixman (`safegfx` on the kernel cmdline, or
#                    /etc/synapseos/safe-graphics)
#   off              /etc/synapseos/no-safe-graphics exists: never apply
#
# virgl advertises linux-dmabuf then fails to import. Quickshell dies with
# the same "importing the supplied dmabufs failed" path plasmashell used
# to. In a VM, force software Qt Quick so the Caelestia shell survives.
#
# `cosmicsafe` is still accepted as an alias for safegfx so older boot
# entries keep working.

if [ ! -e /etc/synapseos/no-safe-graphics ]; then
    _synapseos_gfx=auto

    if [ -e /etc/synapseos/safe-graphics ]; then
        _synapseos_gfx=safe
    elif grep -Eqw 'safegfx|cosmicsafe' /proc/cmdline 2> /dev/null; then
        _synapseos_gfx=safe
    fi

    case "${_synapseos_gfx}" in
        safe)
            export WLR_RENDERER="${WLR_RENDERER:-pixman}"
            export AQ_NO_MODIFIERS="${AQ_NO_MODIFIERS:-1}"
            ;;
    esac

    if command -v systemd-detect-virt >/dev/null 2>&1 && systemd-detect-virt -q; then
        export QT_QUICK_BACKEND="${QT_QUICK_BACKEND:-software}"
        export QSG_RHI_BACKEND="${QSG_RHI_BACKEND:-software}"
        export AQ_NO_MODIFIERS="${AQ_NO_MODIFIERS:-1}"
    fi

    unset _synapseos_gfx
fi

true
