# SynapseOS

An Arch Linux based distribution built around the COSMIC desktop (System76).

## Project layout

```
SynapseOs/
├── archiso/                          # ISO build profile
│   ├── profiledef.sh                 # ISO identity: name, label, publisher, versions
│   ├── packages.x86_64              # ALL software that ends up in the live image
│   ├── pacman.conf                   # pacman/mirror settings used while building
│   ├── grub/                         # GRUB boot menu (splash, titles, entries)
│   ├── efiboot/                      # systemd-boot loader (UEFI)
│   ├── syslinux/                     # Syslinux menu (BIOS)
│   └── airootfs/                     # Files overlaid on the live root filesystem
│       ├── root/customize_airootfs.sh  # post-pacstrap setup (services, users, preinstalled pkg)
│       ├── etc/calamares/            # Installer config + branding + slideshow
│       ├── etc/hostname              # live + default installed hostname
│       ├── usr/bin/synapseos-installer  # launcher used by the desktop entry
│       └── usr/share/synapseos/      # prepare.sh + postinstall.sh (shellprocess targets)
├── packaging/calamares/PKGBUILD      # vendored recipe for the installer
├── tools/gen-branding.py             # regenerates the Calamares branding art
├── tools/build-aur.sh                # builds AUR packages into archiso/repo/
├── tools/check-packages.py           # pre-flight: resolves packages.x86_64
├── tools/live-hotfix-kernel.sh       # live-session workaround for pre-fix ISOs
├── build.sh                          # builds the ISO (needs root): ./build.sh
└── out/                              # built ISO + checksum
```

## Preinstalled software

Everything below ships in the live session and, because the installer copies the
live filesystem, in the installed system too.

| Area        | Packages                                                                 |
| ----------- | ------------------------------------------------------------------------ |
| Desktop     | COSMIC, firefox, helium-browser, pipewire                                |
| C / C++     | base-devel (gcc), clang, llvm, lld, gdb, lldb, valgrind, cmake, ninja, meson |
| Java        | jdk-openjdk, maven, gradle                                               |
| Go          | go, gopls                                                                |
| Rust        | rust (offline toolchain, not rustup), rust-analyzer                       |
| Python      | python, pip, pipx, virtualenv, uv, ipython                               |
| JS / TS     | nodejs, npm, yarn, pnpm, deno                                            |
| Other       | ruby, lua, luarocks, sqlite                                              |
| Git         | git, git-lfs, git-delta, lazygit, github-cli                             |
| Editors     | code (Code - OSS), neovim, helix                                         |
| Containers  | docker, docker-compose, docker-buildx                                    |
| AI agents   | claude-code (`claude`), openai-codex-bin (`codex`), opencode-bin (`opencode`) |
| AUR helper  | paru                                                                     |
| CLI         | ripgrep, fd, fzf, jq, yq, bat, eza, just, tokei, hyperfine, httpie, shellcheck, 7zip |

Notes:

- The three AI agents are installed but not authenticated: run `claude`,
  `codex` or `opencode` once and log in. They need network access at runtime.
- `docker.socket` is enabled on the installed system, so `sudo docker ...`
  works immediately. Adding your user to the `docker` group is intentionally
  left out: that group is equivalent to passwordless root.
- The AUR packages are pinned to whatever `tools/build-aur.sh` last built.
  `paru` can update them on the installed system; plain `pacman -Syu` cannot,
  because the local build repo is removed during installation.

### AUR packages

`claude-code`, `openai-codex-bin`, `opencode-bin`, `helium-browser-bin` and
`paru-bin` are not in the official repositories, so they are built on the build
host and staged into `archiso/repo/`, which `pacman.conf` exposes to mkarchiso
as `[synapseos-local]` (`SigLevel = Optional TrustAll`):

```bash
./tools/build-aur.sh                  # all of them, as a normal user
./tools/build-aur.sh opencode-bin     # just one, e.g. to pick up a new version
```

All five are binary repacks, so nothing is compiled and no build dependencies
are installed on the host; `makepkg -d` skips the dependency checks and the
runtime dependencies are resolved from the official repositories inside the
ISO. `*-debug` packages are filtered out. Note that Claude Code ships under a
proprietary license, so redistributing an ISO containing it publicly is
probably not permitted — check the terms before publishing images.

`calamares` is not in the official repositories *or* the AUR at the version this
profile uses, so its recipe is vendored in `packaging/calamares/`. Unlike the
others it is compiled, so its `makedepends` (boost, extra-cmake-modules, ninja,
qt6-tools, qt6-translations, libglvnd) must be installed on the build host:

```bash
./tools/build-aur.sh calamares
```

## From a fresh clone

`out/`, `work/` and the staged `archiso/repo/*.pkg.tar.zst` are not in git (some
packages exceed GitHub's 100 MB per-file limit), so stage them first:

```bash
git clone https://github.com/srineshr1/synapseos.git && cd synapseos
./tools/build-aur.sh              # stage AI agents, helium, paru (no root)
./tools/build-aur.sh calamares    # the installer itself (compiles)
python3 tools/check-packages.py   # pre-flight the package list
./build.sh                        # needs root
```

`build.sh` rewrites the `[synapseos-local]` server path in
`archiso/pacman.conf` to match the checkout location, so the clone can live
anywhere.

## Build

```bash
./build.sh            # sudo mkarchiso, ~30-60 min on first run
```

The previous ISO is renamed to `*.iso.prev` instead of being deleted, so a run
that fails during validation does not cost the last good image.

Check the package list before starting an hour-long build. This resolves every
package against the real `core`/`extra` databases plus the local repo, and
reports unknown packages, unsatisfied dependencies and genuine conflicts:

```bash
python3 tools/check-packages.py
```

Measured with that tool, the toolchains, editors, browsers and agents take the
root filesystem from **5.6 GB to 12.2 GB** (140 -> 209 requested packages, 755
-> 969 with dependencies), so expect an ISO around 5 GB and a much longer
squashfs step. `profiledef.sh` compresses with `xz`, which is by far the slowest
part of the build; for faster iteration at the cost of ~20% ISO size, switch it
to:

```bash
airootfs_image_tool_options=('-comp' 'zstd' '-Xcompression-level' '19' '-b' '1M')
```

### Build host requirements

`mkarchiso` validates the host before doing any work. This profile
(`bootmodes=('bios.syslinux' 'uefi.grub')`, squashfs) needs:

| Host tool                   | Package                |
| --------------------------- | ---------------------- |
| `pacstrap`                  | `arch-install-scripts` |
| `mkarchiso`                 | `archiso`              |
| `grub-mkstandalone`, `sbat.csv` | `grub`             |
| `mkfs.fat`                  | `dosfstools`           |
| `mmd`, `mcopy`              | `mtools`               |
| `mksquashfs`                | `squashfs-tools`       |
| `xorriso`                   | `libisoburn`           |

`grub` is required even if the build host itself boots with something else
(systemd-boot, limine): it is only used to generate the ISO's own UEFI boot
payload, and the package ships no pacman hooks or units, so installing it does
not touch the host's bootloader. Its absence looks like:

```
[mkarchiso] ERROR: Validating 'uefi.grub': grub-install is not available on this host. Install 'grub'!
```

Note that `bios.syslinux` and `uefi.grub` are the current boot mode names in
archiso 88; the `uefi-x64.grub.esp`-style names are deprecated stubs that fail.

## Installing

Boot the ISO → COSMIC desktop appears → launch **Install SynapseOS**.

Calamares copies the live rootfs to disk (offline), then, in order: partitions
and formats the disk, unpacks the squashfs, writes locale/keymap/fstab, fixes
the mkinitcpio setup and rebuilds the initramfs, creates your user, enables
NetworkManager and the COSMIC greeter, installs GRUB (UEFI + BIOS), runs
`postinstall.sh` to strip the live-media bits, and unmounts the target.

The install image is fully self-contained — no network is required.

## Troubleshooting the installer

The installer log is written to `~/.cache/calamares/session.log` in the live
session (under `/home/live` because the launcher keeps the caller's `HOME`).

The Calamares configuration can be checked on the build host, without booting
or rebuilding the ISO:

```bash
# unpack the calamares package that is staged in archiso/repo/
mkdir -p /tmp/calaroot && tar --zstd -xf archiso/repo/calamares-*.pkg.tar.zst -C /tmp/calaroot usr

# build a throwaway app-data dir out of the package + this profile's config
SB=~/.cache/synapseos-calamares-test
rm -rf "$SB" && cp -r /tmp/calaroot/usr/share/calamares "$SB"
cp archiso/airootfs/etc/calamares/settings.conf "$SB"/
cp archiso/airootfs/etc/calamares/modules/*.conf "$SB"/modules/
cp -r archiso/airootfs/etc/calamares/branding/synapseos "$SB"/branding/
sed -i 's|^  - /usr/lib/calamares/modules|  - /tmp/calaroot/usr/lib/calamares/modules|' "$SB"/settings.conf

# -d is debug/dry-run: no root, nothing is written to any disk
LD_LIBRARY_PATH=/tmp/calaroot/usr/lib QT_QPA_PLATFORM=offscreen \
    /tmp/calaroot/usr/bin/calamares -d -c "$SB"
```

Startup aborts on a bad `branding.desc`, and any module named in
`settings.conf` that does not exist is reported as
`failed modules are QList(...)`. Warnings about `ckbcomp`, `os-prober`, missing
EFI partitions and `locale1` authorization are expected on a build host and do
not appear on the live medium.

Two things are easy to get wrong and both look like "the installer does
nothing":

- module names must match the package (`locale` handles timezones, the final
  step is `finished`, the unmount step is `umount`);
- the launcher must forward the session environment, because `sudo calamares`
  alone loses `WAYLAND_DISPLAY`/`XDG_RUNTIME_DIR` and exits at once.

### `mkinitcpio` fails: `-k '/boot/vmlinuz-linux' must be readable`

`mkarchiso` runs `find "$pacstrap_dir/boot" -mindepth 1 -delete` right before it
builds `airootfs.sfs`, so **the squashfs ships an empty `/boot`**: the kernel and
microcode only exist on the ISO itself (`<label>/boot/x86_64/`), which the
installer's chroot cannot see. Left unhandled, the `initcpio` step dies with:

```
==> ERROR: Invalid option -k -- '/boot/vmlinuz-linux' must be readable
```

The profile works around this in two halves:

- `customize_airootfs.sh` copies `vmlinuz-linux`, `intel-ucode.img` and
  `amd-ucode.img` into `/usr/share/synapseos/boot/`, which survives the cleanup
  because it is outside `/boot`;
- `prepare.sh` copies them back into `/boot` before `initcpiocfg`/`initcpio`
  run, and `postinstall.sh` deletes `/usr/share/synapseos` afterwards.

Anything else added under `/boot` at build time (bootloader files, UKIs) is
deleted the same way and must be restored the same way.

On an ISO built *before* this fix, the config can be patched in the live session
instead of rebuilding — it bind-mounts the live medium into the target and copies
the kernel from there:

```bash
sudo ./tools/live-hotfix-kernel.sh   # then launch the installer again
```

The script only edits `/etc/calamares/modules/{mount,shellprocess-prepare}.conf`
on the live overlay (originals kept as `*.orig`) and is idempotent.

## Customizing

| What you want to change        | Where to edit                                                              |
| ------------------------------ | -------------------------------------------------------------------------- |
| Apps in the ISOLive etc       | `archiso/packages.x86_64` (e.g. add `code`, `steam`, ...)                  |
| ISO name / label / version     | `archiso/profiledef.sh`                                                    |
| System files in live + target  | files under `archiso/airootfs/etc/...` (they land in /etc of every image)  |
| Defaults for new desktop users | `archiso/airootfs/etc/skel/` (COSMIC settings, dotfiles)                   |
| Wallpapers                     | ship them under `airootfs/usr/share/backgrounds/` and set in skel config   |
| Build-time rootfs steps        | `archiso/airootfs/root/customize_airootfs.sh`                              |
| Pre-initramfs install step     | `archiso/airootfs/usr/share/synapseos/prepare.sh`                          |
| Installed-system cleanup       | `archiso/airootfs/usr/share/synapseos/postinstall.sh`                      |
| Installer wizard behavior      | `archiso/airootfs/etc/calamares/modules/*.conf` and `settings.conf`        |
| Installer art + slideshow      | `tools/gen-branding.py`, then `archiso/.../branding/synapseos/`             |
| GRUB defaults of installed sys | `archiso/airootfs/etc/default/grub` (+ `modules/grubcfg.conf`)             |
| GRUB menu look / entries       | `archiso/grub/` (splash.png, grub.cfg)                                     |
| systemd-boot (UEFI)            | `archiso/efiboot/`                                                         |
| BIOS boot menu                 | `archiso/syslinux/` (splash.png must be 640x480 8-bit PNG)                 |

Key COSMIC default state lives in the user config database:

```
~/.config/cosmic/com.system76.CosmicSettings/v1/*.ron
```

To change defaults (dock, panel, theme, accent color), start a configured
session, copy the resulting `~/.config/cosmic/` tree into
`airootfs/etc/skel/.config/cosmic/`, and rebuild.

Live-shell credentials: user `live` / password `live` (passwordless sudo).

## Recovery account on the installed system

`postinstall.sh` creates **`rescue` / `rescue`** with full sudo (password
required) in the installed system, because root is locked and Calamares' sudo
rule names only the account it created — a mistyped or forgotten password would
otherwise mean reinstalling. The `live` user is still deleted, and `rescue` is
in `forbidden_names` so the installer cannot create a clashing account.

This is a known-credentials sudo account, i.e. an intentional backdoor: anyone
with console or SSH access to the machine can become root. `sshd` is not enabled
on the installed system, but remove the account as soon as your own login
works. The installed system's `/etc/motd` says so at every console login:

```bash
sudo userdel -r rescue && sudo rm -f /etc/sudoers.d/20-rescue
sudo rm -f /etc/motd
```

To change the credentials, edit `RESCUE_USER` / `RESCUE_PASS` at the top of the
recovery-account block in
`archiso/airootfs/usr/share/synapseos/postinstall.sh`. To drop the feature,
delete that block and restore `rm -f /etc/motd` at the end of the script.

## Boot / desktop diagnostics

The live boot entries are verbose on purpose: kernel and systemd messages are
shown so a failure is visible on screen. `quiet loglevel=3
systemd.show_status=false rd.systemd.show_status=false
vt.global_cursor_default=0` now lives only on the extra "quiet boot" entry in
`archiso/grub/grub.cfg` and `archiso/syslinux/archiso_sys-linux.cfg`. The
installed system still boots quietly (`airootfs/etc/default/grub` and
`modules/grubcfg.conf`).

COSMIC is autostarted on tty1 by `/home/live/.zprofile`, which calls
`synapseos-cosmic` instead of `exec start-cosmic`. That wrapper runs the
cosmic-session package's own `/usr/bin/start-cosmic` (which is what sets up
dbus, `XDG_CURRENT_DESKTOP`, the dconf profile and the Qt theme), tees the
session output to `~/.cache/synapseos/cosmic-session.log` and returns to the
shell when the compositor exits non-zero — an exec'd session that dies takes the
login shell with it, agetty restarts, and all that is left on screen is the motd,
which is indistinguishable from "the ISO just boots to text".

The wrapper must **not** be called `start-cosmic`: since cosmic-session 1.3 that
path is shipped by the package itself, and `airootfs/usr/bin/start-cosmic` makes
pacstrap abort the build with
`cosmic-session: /...\/usr/bin/start-cosmic exists in filesystem`. Upstream's
script also re-execs itself through `$SHELL` as a login shell, so the autostart
in `.zprofile` is guarded by `SYNAPSEOS_COSMIC_AUTOSTART` to avoid recursing.

If the desktop does not appear:

```bash
synapseos-cosmic      # retry, with the failure printed and logged
synapseos-logs        # one file with journal, cosmic log, GPU info, mounts
journalctl -b -p err --no-pager
```

`synapseos-logs [DIR]` writes `synapseos-logs-<host>-<date>.txt` to `$HOME` or
to `DIR`, so pass a mounted USB stick to get it off the machine. The live
journal is `Storage=volatile`, i.e. RAM only — collect it before rebooting.

Booting with `nodesktop` on the kernel command line (the "console only" menu
entry) skips the COSMIC autostart and leaves a plain shell for debugging.

## Rebuilding notes

`mkarchiso` reuses the pacman cache and work dir, so rebuilds only redo the
changed steps (airootfs changes alone cost a few minutes). Delete `work/`
to force a full rebuild.