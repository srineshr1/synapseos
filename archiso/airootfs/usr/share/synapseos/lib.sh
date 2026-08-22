# Shared helpers for the SynapseOS (Omarchy-style) CLI.
# shellcheck shell=bash

SYNAPSEOS_MAUVE="#c6a0f6"
SYNAPSEOS_TEXT="#cad3f5"
SYNAPSEOS_RED="#ed8796"
SYNAPSEOS_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export GUM_CHOOSE_CURSOR_FOREGROUND="${GUM_CHOOSE_CURSOR_FOREGROUND:-$SYNAPSEOS_MAUVE}"
export GUM_CHOOSE_HEADER_FOREGROUND="${GUM_CHOOSE_HEADER_FOREGROUND:-$SYNAPSEOS_MAUVE}"
export GUM_CHOOSE_SELECTED_FOREGROUND="${GUM_CHOOSE_SELECTED_FOREGROUND:-$SYNAPSEOS_TEXT}"
export GUM_CONFIRM_SELECTED_FOREGROUND="${GUM_CONFIRM_SELECTED_FOREGROUND:-#181926}"
export GUM_CONFIRM_SELECTED_BACKGROUND="${GUM_CONFIRM_SELECTED_BACKGROUND:-$SYNAPSEOS_MAUVE}"

synapseos_have() {
    command -v "$1" >/dev/null 2>&1
}

synapseos_pkg_present() {
    local pkg
    for pkg in "$@"; do
        pacman -Q "$pkg" >/dev/null 2>&1 || return 1
    done
    return 0
}

synapseos_pkg_missing() {
    ! synapseos_pkg_present "$@"
}

synapseos_sudo() {
    if (( EUID == 0 )); then
        "$@"
    else
        sudo "$@"
    fi
}

synapseos_pkg_add() {
    local pkgs=()
    local pkg
    for pkg in "$@"; do
        synapseos_pkg_present "$pkg" || pkgs+=("$pkg")
    done
    (( ${#pkgs[@]} == 0 )) && return 0
    synapseos_sudo pacman -S --needed --noconfirm "${pkgs[@]}"
}

synapseos_pkg_aur_add() {
    local helper=""
    if synapseos_have paru; then
        helper=paru
    elif synapseos_have yay; then
        helper=yay
    else
        echo "synapseos: need paru or yay to install AUR packages" >&2
        return 1
    fi
    "$helper" -S --needed --noconfirm "$@"
}

synapseos_pkg_drop() {
    local pkgs=()
    local pkg
    for pkg in "$@"; do
        synapseos_pkg_present "$pkg" && pkgs+=("$pkg")
    done
    (( ${#pkgs[@]} == 0 )) && return 0
    synapseos_sudo pacman -Rns --noconfirm "${pkgs[@]}"
}

synapseos_enable_multilib() {
    local conf=/etc/pacman.conf
    grep -q '^\[multilib\]' "$conf" && return 0
    synapseos_sudo sed -i \
        -e 's/^#\[multilib\]/[multilib]/' \
        -e '/^\[multilib\]/{n;s/^#Include/Include/}' \
        "$conf"
    synapseos_sudo pacman -Sy --noconfirm
}

synapseos_pick() {
    local header="$1"
    shift
    if (( $# == 0 )); then
        return 1
    fi
    if synapseos_have gum; then
        printf '%s\n' "$@" | gum choose --header "$header"
    elif synapseos_have fzf; then
        printf '%s\n' "$@" | fzf --prompt "$header > "
    else
        echo "$header" >&2
        select _choice in "$@"; do
            [[ -n ${_choice:-} ]] && { printf '%s\n' "$_choice"; return 0; }
            return 1
        done
    fi
}

synapseos_confirm() {
    local prompt="${1:-Continue?}"
    if synapseos_have gum; then
        gum confirm "$prompt"
    else
        local reply
        read -r -p "$prompt [y/N] " reply
        [[ $reply == [yY] || $reply == yes ]]
    fi
}

synapseos_done() {
    echo
    echo "Done."
    if [[ -t 0 ]]; then
        read -r -p "Press Enter to close. "
    fi
}

synapseos_terminal() {
    if synapseos_have kitty; then
        command -p kitty "$@"
    elif synapseos_have foot; then
        command -p foot "$@"
    else
        xdg-terminal-exec "$@"
    fi
}

# Floating kitty used for the Super+Space menu and one-click installers.
synapseos_float() {
    local title="${1:-SynapseOS}"
    shift
    local cmd=("$@")
    if (( ${#cmd[@]} == 0 )); then
        cmd=(bash)
    fi
    synapseos_terminal \
        --class org.synapseos.menu \
        --title "$title" \
        -o remember_window_size=no \
        -o initial_window_width=96c \
        -o initial_window_height=30c \
        -e bash -lc "$(printf '%q ' "${cmd[@]}")" >/dev/null 2>&1 &
    disown || true
}

synapseos_webapp() {
    local url="$1"
    if synapseos_have helium; then
        helium --app="$url" >/dev/null 2>&1 &
    elif synapseos_have firefox; then
        firefox --new-window "$url" >/dev/null 2>&1 &
    else
        xdg-open "$url" >/dev/null 2>&1 &
    fi
}

synapseos_default_browser() {
    local desktop
    desktop=$(xdg-settings get default-web-browser 2>/dev/null || true)
    if [[ -n $desktop ]] && synapseos_have gtk-launch; then
        gtk-launch "$desktop" >/dev/null 2>&1 && return 0
    fi
    if synapseos_have helium; then
        helium >/dev/null 2>&1 &
    elif synapseos_have firefox; then
        firefox >/dev/null 2>&1 &
    else
        xdg-open https:// >/dev/null 2>&1 &
    fi
}

synapseos_default_editor() {
    if synapseos_have code; then
        code >/dev/null 2>&1 &
    elif synapseos_have helix; then
        synapseos_float "Helix" helix
    elif synapseos_have nvim; then
        synapseos_float "Neovim" nvim
    elif synapseos_have micro; then
        synapseos_float "micro" micro
    else
        synapseos_float "Neovim" nvim
    fi
}
