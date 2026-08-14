# SynapseOS: KWin compositor backend.
#
# Frosted menus, Kickoff and inactive windows need OpenGL. QPainter
# composition (KWIN_COMPOSE=Q) is stable on broken GPUs but cannot blur,
# so it is opt-in only:
#   auto  (default)  OpenGL, including in a VM
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
    esac

    unset _synapseos_gfx
fi

true
