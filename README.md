# SynapseOS

An Arch Linux desktop with a system assistant as a first-class OS service.
The assistant sees the session and acts on it through typed tools you
approve. The ISO is the vehicle. The assistant is the product.

See [docs/GOAL.md](docs/GOAL.md) for the one-sentence goal, what this is
not (not a Linux kernel, not [AIOS](https://github.com/agiresearch/AIOS)),
and the v1 definition of done.

The live and installed desktop is Plasma 6 with a compact Catppuccin
Macchiato look.

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
├── tools/install-catppuccin-plasma.sh # re-vendors Macchiato into airootfs
├── tools/live-hotfix-desktop.sh      # live-session Plasma / SSH_AUTH_SOCK fix
├── build.sh                          # builds the ISO (needs root): ./build.sh
└── out/                              # built ISO + checksum
```

## Preinstalled software

Everything below ships in the live session and, because the installer copies the
live filesystem, in the installed system too.

| Area        | Packages                                                                 |
| ----------- | ------------------------------------------------------------------------ |
| Desktop     | Plasma 6 (Catppuccin Macchiato), firefox, helium-browser, pipewire, obs-studio |
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
| Assistant   | Super+S overlay, `synapse-core` user service, `synapsectl`, OS MCP (`synapseos-mcp`) |
| AI agents   | claude-code (`claude`), openai-codex-bin (`codex`), opencode-bin (`opencode`) |
| AUR helper  | paru                                                                     |
| CLI         | ripgrep, fd, fzf, jq, yq, bat, eza, just, tokei, hyperfine, httpie, shellcheck, 7zip |

### Synapse assistant

Press **Super+S** (or run `synapseos-overlay`) for a Macchiato overlay that
does what you say: open apps, navigate the browser, list what is running and
for how long, throttle or kill a runaway process. The model never talks to
`/proc` itself. It calls typed tools on a local MCP server.

```
synapse-core.service   # user systemd, starts with the graphical session
synapseos-overlay      # Super+S
synapsectl ask "…"     # same brain, no GUI
synapsectl apps        # running apps + elapsed time
synapsectl proc
synapseos-mcp          # stdio MCP for claude / codex / opencode
```

The core is unprivileged. Launch / focus / open-URL run immediately in the
default **assist** mode. Kill, throttle, close and `shell_run` ask first.
PID 1, KWin, plasmashell and the core itself cannot be killed. Ctrl+Alt+S
is the kill switch.

The planner and the mic use SpaceXAI (`XAI_API_KEY` or `synapsectl key set`).
Without a key the overlay still lists local state; it will not pretend a
cloud call succeeded.

```bash
# Attach a preinstalled coding agent to the OS tool server
claude mcp add synapseos -- synapseos-mcp

# From a git checkout, against the session you are in now:
./tools/run-synapseos.sh core
./tools/run-synapseos.sh overlay
./tools/run-synapseos.sh ctl apps
./tools/run-synapseos.sh test
```

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
# Catppuccin Macchiato is already in airootfs. Re-fetch with:
#   ./tools/install-catppuccin-plasma.sh
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

Boot the ISO → Plasma appears (floating Macchiato panel) → **Install SynapseOS**
opens on its own (xdg-autostart). If it does not, launch it from the app
menu or run `synapseos-installer`.

Calamares copies the live rootfs to disk (offline), then, in order: partitions
and formats the disk, unpacks the squashfs, writes locale/keymap/fstab, fixes
the mkinitcpio setup and rebuilds the initramfs, creates your user, enables
NetworkManager and SDDM, installs GRUB (UEFI + BIOS), runs
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

### Desktop dies when you minimise a window or open an app

That is KWin failing to compose (usually missing 3D in a VM), not the
`SSH_AUTH_SOCK not set` line that can flash on tty1. On an ISO built
before the compositor workarounds, copy this checkout into the live
session (shared folder, scp, USB) and run:

```bash
sudo ./tools/live-hotfix-desktop.sh   # then log out of Plasma, or reboot
```

It installs `/etc/profile.d/synapseos-{graphics,ssh-agent}.sh`,
`synapseos-safe-graphics`, and the PAM/gcr bits. After a session restart the
minimise crash should stop. If it does not, `sudo synapseos-safe-graphics on`
and log out again.

## Customizing

| What you want to change        | Where to edit                                                              |
| ------------------------------ | -------------------------------------------------------------------------- |
| OS assistant (overlay, MCP)    | `archiso/airootfs/usr/lib/synapseos/` + `usr/bin/synapseos-*` / `synapsectl` |
| Apps in the ISO / live etc     | `archiso/packages.x86_64` (e.g. add `code`, `steam`, ...)                  |
| ISO name / label / version     | `archiso/profiledef.sh`                                                    |
| System files in live + target  | files under `archiso/airootfs/etc/...` (they land in /etc of every image)  |
| Defaults for new desktop users | `archiso/airootfs/etc/skel/` (Plasma + Catppuccin Macchiato)                |
| Wallpapers                     | `/usr/share/backgrounds/synapseos/desktop.png` + Plasma appletsrc           |
| Catppuccin theme files         | `tools/install-catppuccin-plasma.sh`                                        |
| Build-time rootfs steps        | `archiso/airootfs/root/customize_airootfs.sh`                              |
| Pre-initramfs install step     | `archiso/airootfs/usr/share/synapseos/prepare.sh`                          |
| Installed-system cleanup       | `archiso/airootfs/usr/share/synapseos/postinstall.sh`                      |
| Installer wizard behavior      | `archiso/airootfs/etc/calamares/modules/*.conf` and `settings.conf`        |
| Installer art + slideshow      | `tools/gen-branding.py`, then `archiso/.../branding/synapseos/`             |
| Desktop crash on minimise      | `airootfs/etc/profile.d/synapseos-graphics.sh` + `synapseos-safe-graphics` |
| `SSH_AUTH_SOCK not set` flash  | `airootfs/etc/profile.d/synapseos-ssh-agent.sh` (harmless; tty leftover)   |
| GRUB defaults of installed sys | `archiso/airootfs/etc/default/grub` (+ `modules/grubcfg.conf`)             |
| GRUB menu look / entries       | `archiso/grub/` (`theme/` + grub.cfg; art from `tools/gen-branding.py`)    |
| systemd-boot (UEFI)            | `archiso/efiboot/`                                                         |
| BIOS boot menu                 | `archiso/syslinux/` (640x480 8-bit splash.png from `tools/gen-branding.py`) |

Plasma defaults live in `/etc/xdg/` (system) and `/etc/skel/.config/`
(new users): `kwinrc`, `kwinrulesrc`, `kdeglobals`, the look-and-feel
package, and the Konsole / Kitty profiles. To change dock, panel, theme
or window rules, configure a session, copy the resulting files into
`airootfs/etc/skel/.config/`, and rebuild.

Live-shell credentials: user `live` / password `live` (passwordless sudo).

Plasma Welcome is skipped on the live user and on `rescue`. The account
Calamares creates still inherits `/etc/skel` and can run Welcome on first
login after install.

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

Plasma is autostarted on tty1 by `/home/live/.zprofile`, which calls
`synapseos-plasma`. That wrapper runs `startplasma-wayland`, tees the
session output to `~/.cache/synapseos/plasma-session.log` and returns to the
shell when the compositor exits non-zero — an exec'd session that dies takes the
login shell with it, agetty restarts, and all that is left on screen is the motd.

If the desktop does not appear:

```bash
synapseos-plasma      # retry, with the failure printed and logged
synapseos-logs        # one file with journal, plasma log, GPU info, mounts
journalctl -b -p err --no-pager
```

`synapseos-logs [DIR]` writes `synapseos-logs-<host>-<date>.txt` to `$HOME` or
to `DIR`, so pass a mounted USB stick to get it off the machine. The live
journal is `Storage=volatile`, i.e. RAM only — collect it before rebooting.

Booting with `nodesktop` on the kernel command line (the "console only" menu
entry) skips the Plasma autostart and leaves a plain shell for debugging.

### The desktop fails to start in a VM

On the 2026.08.15 ISO this is KWin + virgl, not a missing package. Forcing
`KWIN_COMPOSE=O` makes KWin exit if OpenGL cannot start, and even when the
compositor comes back, plasmashell dies on
`error 7: importing the supplied dmabufs failed` (three times →
start-limit → empty session). **Safe graphics is not enough** — QPainter
still advertises linux-dmabuf.

On that ISO, switch to tty2 (`Ctrl+Alt+F2`), log in as `live` / `live`, and
either copy this checkout in and run `sudo ./tools/live-hotfix-desktop.sh`,
or:

```bash
export QT_QUICK_BACKEND=software QSG_RHI_BACKEND=software
unset KWIN_COMPOSE
export KWIN_DISABLE_VULKAN=1
synapseos-plasma
```

Newer images set those automatically in a VM (`systemd-detect-virt`) and
disable Vulkan instead of requiring OpenGL. Rebuild to pick that up.

Frost in a VM is a pre-rendered cache of the wallpaper
(`desktop-frost.jpg`, regenerated with `python3 tools/gen-frost.py`)
plus cheap stock KWin blur when OpenGL actually starts. If live blur
does not load, translucent windows show the baked frost image instead
of a raw see-through. Panels and menus are force-blurred; browsers stay
opaque.

Blur (windows, menus, Kickoff) needs OpenGL. Better Blur DX
(`kwin-effects-better-blur-dx` in `archiso/repo/`) is preferred on bare
metal; a VM always uses stock KWin blur plus the SynapseOS frost effect.
Rebuild the DX package after a kwin upgrade
(`./tools/build-aur.sh kwin-effects-better-blur-dx`).
Software composition (`KWIN_COMPOSE=Q`) cannot blur — it is opt-in via the
**safe graphics** boot entry (`safegfx`) or:

```bash
sudo synapseos-safe-graphics on      # or: off, auto, status
```

Then log out and back in. `cosmicsafe` on the kernel command line is still
accepted as an alias for `safegfx` (leftover from the COSMIC-era ISOs).

VirtualBox: graphics controller **VMSVGA**, **3D acceleration on**, 128 MB
of VRAM. Without 3D, KWin falls back to software GL (slow blur) or fails
and you boot **safe graphics** instead.

QEMU (do not use plain `virtio-vga` — that is 2D and blur will not run):

```bash
./tools/run-iso.sh                  # as your user, not sudo
```

`sudo ./build.sh` leaves `out/` owned by root, so the VM disk is created in
`~/.cache/synapseos/`. Fix ownership with
`sudo chown -R "$USER:$USER" out` if you want the qcow2 next to the ISO.
Do not launch qemu with sudo — GTK then has no GPU and blur dies.
On Hyprland the viewer is `sdl,gl=on` (GTK GL is unsupported there).

Calamares needs a disk of at least 25 GiB. A CD-only VM shows
"There are no partitions to install on" and refuses Next. VirtualBox:
add a 40 GB VDI and keep **VMSVGA + 3D**.

`virtualbox-guest-utils` replaces archiso's `virtualbox-guest-utils-nox` in the
package list, which adds `VBoxDRMClient` (resolution follows the window on a
Wayland session), `vboxwl` (clipboard) and the `vboxclient` autostart entry.

To find the actual crash, `postinstall.sh` now also deletes the live
`Storage=volatile` journald drop-in and creates `/var/log/journal`, so the
installed system keeps its logs across reboots — without that, the evidence for
a crash that forces a reboot is gone. `systemd-coredump` is enabled by default,
so the backtrace is in `coredumpctl info kwin_wayland`; `synapseos-logs` collects
that, the previous boot and the workaround variables into its bundle.


### `Environment variable $SSH_AUTH_SOCK not set, ignoring.`

Harmless. Something in the session (historically `start-cosmic`, still
true of some PAM/systemd imports) runs

```bash
systemctl --user import-environment XDG_SESSION_TYPE XDG_CURRENT_DESKTOP DCONF_PROFILE SSH_AUTH_SOCK
```

and `systemctl import-environment` logs that notice for every variable that is
unset; it still exits 0.

The profile turns it into something useful instead of silencing it:
`customize_airootfs.sh` runs `systemctl --global enable gcr-ssh-agent.socket`
(from `gcr-4`) and adds `pam_gnome_keyring` to `/etc/pam.d/{login,sddm,greetd}`.
`airootfs/etc/profile.d/synapseos-ssh-agent.sh` exports
`SSH_AUTH_SOCK=$XDG_RUNTIME_DIR/gcr/ssh` for login shells (and starts the
socket if needed) so the import always has a value. An inherited
`SSH_AUTH_SOCK` (agent forwarding) is never overwritten.

When KWin dies the compositor surface goes away and that leftover tty1
line can flash through, which is why it looks like the SSH notice killed
the desktop. Fix the crash (safe graphics) and the flash goes with it.

On an already-installed system, without rebuilding:

```bash
systemctl --user enable --now gcr-ssh-agent.socket
sudo cp /path/to/profile/airootfs/etc/profile.d/synapseos-ssh-agent.sh /etc/profile.d/
```

## Rebuilding notes

`mkarchiso` reuses the pacman cache and work dir, so rebuilds only redo the
changed steps (airootfs changes alone cost a few minutes). Delete `work/`
to force a full rebuild.