# SynapseOS: KWin compositor backend + Qt Quick renderer.
#
# Do not set KWIN_COMPOSE=O. If OpenGL cannot start, KWin logs
#   Could not fulfill the requested compositing mode in KWIN_COMPOSE: 1
# and exits — the session never comes up. Prefer OpenGL by disabling
# Vulkan instead; KWin can still fall back to QPainter.
#   auto  (default)  KWIN_DISABLE_VULKAN=1
#   safe             KWIN_COMPOSE=Q (`safegfx` on the kernel cmdline, or
#                    /etc/synapseos/safe-graphics)
#   off              /etc/synapseos/no-safe-graphics exists: never apply
#
# virgl advertises linux-dmabuf then fails to import. plasmashell dies
# with "error 7: importing the supplied dmabufs failed" and systemd hits
# start-limit. In a VM, force software Qt Quick so the shell survives.
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
            export KWIN_COMPOSE="${KWIN_COMPOSE:-Q}"
            ;;
        auto)
            export KWIN_DISABLE_VULKAN="${KWIN_DISABLE_VULKAN:-1}"
            ;;
    esac

    if command -v systemd-detect-virt >/dev/null 2>&1 && systemd-detect-virt -q; then
        export QT_QUICK_BACKEND="${QT_QUICK_BACKEND:-software}"
        export QSG_RHI_BACKEND="${QSG_RHI_BACKEND:-software}"
        export KWIN_DRM_USE_MODIFIERS="${KWIN_DRM_USE_MODIFIERS:-0}"
    fi

    unset _synapseos_gfx
fi

true
