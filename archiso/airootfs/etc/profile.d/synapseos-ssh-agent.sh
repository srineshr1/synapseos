# SynapseOS: give the session a real SSH_AUTH_SOCK.
#
# systemctl --user import-environment logs
#     Environment variable $SSH_AUTH_SOCK not set, ignoring.
# when the socket is missing. That notice is painted on tty1. When KWin
# dies the compositor surface goes away and the tty flashes through —
# which looks like this line killed the desktop. It did not; see
# synapseos-graphics.sh.
#
# gcr-ssh-agent.socket (gcr-4) listens on $XDG_RUNTIME_DIR/gcr/ssh. Export the
# path even if the socket is still coming up, so the import has something to
# import. An inherited value (agent forwarding) is left alone.

if [ -z "${SSH_AUTH_SOCK:-}" ]; then
    _synapseos_ssh_sock="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/gcr/ssh"
    if [ ! -S "${_synapseos_ssh_sock}" ] && command -v systemctl > /dev/null 2>&1; then
        systemctl --user start gcr-ssh-agent.socket > /dev/null 2>&1 || true
    fi
    SSH_AUTH_SOCK="${_synapseos_ssh_sock}"
    export SSH_AUTH_SOCK
    unset _synapseos_ssh_sock
fi

true
