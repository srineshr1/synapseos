# Sourced by startplasma so SDDM sessions get the same compositor backend
# as the live tty1 path (which sources /etc/profile.d via synapseos-plasma).
# shellcheck disable=SC1091
[ -r /etc/profile.d/synapseos-graphics.sh ] && . /etc/profile.d/synapseos-graphics.sh
true
