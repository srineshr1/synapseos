# SynapseOS: KWin compositor backend.
#
# Frosted menus, Kickoff and inactive windows need OpenGL. Stock KWin
# blur only loads when isOpenGLCompositing() is true — a Vulkan or
# QPainter scene makes loadEffect(blur) return false.
#   auto  (default)  KWIN_COMPOSE=O
#   safe             KWIN_COMPOSE=Q (`safegfx` on the kernel cmdline, or
#                    /etc/synapseos/safe-graphics)
#   off              /etc/synapseos/no-safe-graphics exists: never apply Q
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
            export KWIN_COMPOSE="${KWIN_COMPOSE:-O}"
            ;;
    esac

    unset _synapseos_gfx
fi

true
