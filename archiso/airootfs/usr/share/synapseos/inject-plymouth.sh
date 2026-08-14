#!/usr/bin/env bash
# Ensure the plymouth hook sits after kms (or udev) in the target
# mkinitcpio.conf. Calamares 3.4 already appends plymouth when
# /usr/bin/plymouth exists; this is a no-op in that case and a fallback
# if detect_plymouth() missed it.
set -euo pipefail

conf=/etc/mkinitcpio.conf
[[ -f $conf ]] || exit 0

if grep -Eq '^HOOKS=.*\bplymouth\b' "$conf"; then
    exit 0
fi

if grep -Eq '^HOOKS=.*\bkms\b' "$conf"; then
    sed -i -E 's/^(HOOKS=\([^)]*\b)kms\b/\1kms plymouth/' "$conf"
elif grep -Eq '^HOOKS=.*\budev\b' "$conf"; then
    sed -i -E 's/^(HOOKS=\([^)]*\b)udev\b/\1udev plymouth/' "$conf"
else
    sed -i -E 's/^(HOOKS=\()/\1plymouth /' "$conf"
fi
