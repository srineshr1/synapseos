#!/usr/bin/env bash
# Build the AUR packages this profile needs and stage them in archiso/repo/,
# which pacman.conf exposes to mkarchiso as the [synapseos-local] repository.
#
# Run as a normal user (makepkg refuses to run as root). Most packages are
# binary repacks. quickshell-git and caelestia-shell are compiled. Dependency
# checks are skipped (-d), which also breaks the caelestia-cli / caelestia-shell
# circular optional depends.
#
#   ./tools/build-aur.sh              # build all packages
#   ./tools/build-aur.sh opencode-bin # build just one
set -euo pipefail

PACKAGES=(
    claude-code         # Anthropic Claude Code CLI (proprietary binary)
    openai-codex-bin    # OpenAI Codex CLI       -> provides `codex`
    opencode-bin        # opencode agent         -> provides `opencode`
    helium-browser-bin  # Helium browser (Chromium fork)
    paru-bin            # AUR helper, so the installed system can use the AUR
    libcava
    ttf-rubik-vf
    papirus-folders
    darkly-bin
    pwvucontrol
    qtengine
    python-materialyoucolor  # caelestia-cli dependency (AUR)
    qt6-m3shapes-git    # caelestia-shell 2.5 dependency (AUR, compile)
    quickshell-git      # compile; pin via the AUR PKGBUILD
    caelestia-cli
    caelestia-shell
)

if (( $# )); then
    PACKAGES=("$@")
fi

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
repo_dir="${repo_root}/archiso/repo"
work_dir="${AUR_WORK_DIR:-${HOME}/.cache/synapseos-aur}"
db_name="synapseos-local"

if (( EUID == 0 )); then
    echo "error: run this as a normal user, not root (makepkg refuses)" >&2
    exit 1
fi

mkdir -p "$repo_dir" "$work_dir"

built=()
for pkg in "${PACKAGES[@]}"; do
    echo "==> ${pkg}"
    build_dir="${work_dir}/${pkg}"
    if [[ -d "${repo_root}/packaging/${pkg}" ]]; then
        # Vendored recipe (e.g. calamares, which is not in the AUR either).
        # This one is compiled, so its makedepends must be installed already.
        build_dir="${repo_root}/packaging/${pkg}"
        echo "    using vendored PKGBUILD ${build_dir#"${repo_root}"/}"
    elif [[ -d "${build_dir}/.git" ]]; then
        git -C "${build_dir}" pull --ff-only
    else
        rm -rf "${build_dir:?}"
        git clone --depth 1 "https://aur.archlinux.org/${pkg}.git" "${build_dir}"
    fi

    # -d: skip dependency checks (runtime deps are resolved inside the ISO)
    # -f: overwrite an existing package, -c: clean up src/ afterwards
    # --skippgpcheck: AUR git tags are often signed by keys not on this host;
    # we already trust the PKGBUILD by cloning it.
    ( cd "${build_dir}" && makepkg -dcf --noconfirm --noprogressbar --skippgpcheck )

    while IFS= read -r -d '' file; do
        # makepkg also emits *-debug packages; they have no place in the ISO.
        case "$(basename "$file")" in
            *-debug-*) continue ;;
        esac
        install -m 0644 -- "$file" "${repo_dir}/"
        built+=("${repo_dir}/$(basename "$file")")
        echo "    staged $(basename "$file")"
    done < <(find "${build_dir}" -maxdepth 1 -name '*.pkg.tar.zst' -print0)
done

if (( ${#built[@]} == 0 )); then
    echo "error: no packages were produced" >&2
    exit 1
fi

# Re-index every staged package. Do not use --new: staging can overwrite a
# same-version .pkg.tar.zst (install -m 0644), and --new would leave a stale
# %CSIZE%/%SHA256SUM% that pacman then rejects as "maximum allowed file size".
repo-add --quiet --remove "${repo_dir}/${db_name}.db.tar.gz" "${repo_dir}"/*.pkg.tar.zst

echo
echo "Repository ${repo_dir}/${db_name}.db now contains:"
tar -tzf "${repo_dir}/${db_name}.db.tar.gz" | sed -n 's|/$||p' | sort | sed 's/^/  /'
