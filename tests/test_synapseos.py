"""Unit tests for Synapse Core — no desktop session required."""

from __future__ import annotations

import io
import json
import os
import stat
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "archiso/airootfs/usr/lib/synapseos"
import sys

sys.path.insert(0, str(LIB))

from synapseos.config import Config, _dump, load, save  # noqa: E402
from synapseos.mcp import read_message, write_message  # noqa: E402
from synapseos.perception.apps import DesktopApp, match_app, parse_desktop_file  # noqa: E402
from synapseos.perception.proc import (  # noqa: E402
    boot_time,
    desktop_id_from_cgroup,
    fmt_duration,
    parse_cmdline,
    parse_stat,
    read_process,
)
from synapseos.perception.store import Sampler  # noqa: E402
from synapseos.policy import Policy, is_protected  # noqa: E402
from synapseos.server import Core  # noqa: E402
from synapseos.tools import ToolBroker, ToolError  # noqa: E402


def _write_proc(root: Path, pid: int, *, comm: str, ppid: int = 1, utime: int = 10,
                stime: int = 5, start_ticks: int = 1000, rss_kb: int = 4096,
                uid: int = 1000, exe: str = "/usr/bin/sleep",
                cmdline: bytes = b"sleep\x003600\x00",
                cgroup: str = "0::/user.slice/user-1000.slice/user@1000.service/"
                               "app.slice/app-firefox-a1b2.scope",
                state: str = "S") -> None:
    d = root / str(pid)
    d.mkdir(parents=True, exist_ok=True)
    # pid (comm) state ppid ... starttime at rest[19]
    rest = [state, str(ppid)] + ["0"] * 9 + [str(utime), str(stime)] + ["0"] * 5 + ["0", str(start_ticks)]
    (d / "stat").write_text(f"{pid} ({comm}) {' '.join(rest)}\n", encoding="utf-8")
    (d / "status").write_text(f"Name:\t{comm}\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\nVmRSS:\t{rss_kb} kB\n")
    (d / "cmdline").write_bytes(cmdline)
    (d / "cgroup").write_text(cgroup + "\n")
    if exe:
        try:
            os.symlink(exe, d / "exe")
        except FileExistsError:
            pass


class ProcTests(unittest.TestCase):
    def test_parse_stat_spaces_in_comm(self) -> None:
        parsed = parse_stat("42 (Web Content) S 1 1 1 0 0 0 0 0 0 0 30 10 0 0 20 0 1 0 999 0 0")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["pid"], 42)
        self.assertEqual(parsed["comm"], "Web Content")
        self.assertEqual(parsed["utime"], 30)
        self.assertEqual(parsed["stime"], 10)
        self.assertEqual(parsed["start_ticks"], 999)

    def test_desktop_id_from_cgroup(self) -> None:
        self.assertEqual(
            desktop_id_from_cgroup(
                "/user.slice/user-1000.slice/user@1000.service/app.slice/app-firefox-a1b2.scope"
            ),
            "firefox",
        )
        self.assertEqual(
            desktop_id_from_cgroup(
                "/user.slice/user-1000.slice/user@1000.service/app.slice/"
                "app-gio-org.kde.konsole-f3.scope"
            ),
            "org.kde.konsole",
        )

    def test_elapsed_from_btime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            procfs = Path(tmp)
            (procfs / "stat").write_text("btime 1000000\n")
            _write_proc(procfs, 9, comm="firefox", start_ticks=200, uid=os.getuid())
            now = 1000000 + 20  # 20s after boot; start_ticks=200 / 100hz = 2s
            proc = read_process(9, procfs, now=now, btime=1_000_000, hz=100)
            self.assertIsNotNone(proc)
            assert proc is not None
            self.assertAlmostEqual(proc.elapsed_sec, 18.0, places=1)
            self.assertEqual(proc.desktop_id, "firefox")

    def test_boot_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            procfs = Path(tmp)
            (procfs / "stat").write_text("cpu 1\nbtime 42\n")
            self.assertEqual(boot_time(procfs), 42.0)

    def test_fmt_duration(self) -> None:
        self.assertEqual(fmt_duration(12), "12s")
        self.assertEqual(fmt_duration(75), "1m 15s")
        self.assertEqual(fmt_duration(3700), "1h 1m")

    def test_cmdline(self) -> None:
        self.assertEqual(parse_cmdline(b"sleep\x003600\x00"), ["sleep", "3600"])


class AppTests(unittest.TestCase):
    def test_parse_and_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "firefox.desktop"
            path.write_text(
                "[Desktop Entry]\nType=Application\nName=Firefox\n"
                "Exec=firefox %u\nStartupWMClass=firefox\nIcon=firefox\n",
                encoding="utf-8",
            )
            app = parse_desktop_file(path)
            self.assertIsNotNone(app)
            assert app is not None
            self.assertEqual(app.id, "firefox")
            self.assertEqual(app.exec, "firefox")
            apps = [app, DesktopApp(id="org.kde.kate", name="Kate", exec="kate")]
            self.assertEqual(match_app("Fire", apps).id, "firefox")
            self.assertEqual(match_app("kate", apps).id, "org.kde.kate")


class PolicyTests(unittest.TestCase):
    def test_protected_set(self) -> None:
        self.assertTrue(is_protected(pid=1))
        self.assertTrue(is_protected(comm="kwin_wayland"))
        self.assertTrue(is_protected(comm="plasmashell"))
        self.assertFalse(is_protected(comm="firefox", pid=4417))

    def test_observe_blocks_launch(self) -> None:
        cfg = Config()
        cfg.policy.mode = "observe"
        pol = Policy(cfg, grants_path=Path("/tmp/does-not-exist-grants.json"))
        d = pol.check("apps_launch", {"query": "x"}, summary="Launch x")
        self.assertFalse(d.allow)
        self.assertEqual(d.reason, "observe")

    def test_assist_confirms_kill(self) -> None:
        cfg = Config()
        cfg.policy.mode = "assist"
        with tempfile.TemporaryDirectory() as tmp:
            pol = Policy(cfg, grants_path=Path(tmp) / "g.json")
            d = pol.check("proc_kill", {"pid": 9}, summary="kill 9", comm="sleep", pid=9)
            self.assertTrue(d.needs_consent)
            self.assertFalse(d.allow)
            taken = pol.take(d.consent_id)
            self.assertIsNotNone(taken)

    def test_protected_kill_denied(self) -> None:
        cfg = Config()
        pol = Policy(cfg, grants_path=Path("/tmp/does-not-exist-grants.json"))
        d = pol.check("proc_kill", {"pid": 1}, summary="kill 1", comm="systemd", pid=1)
        self.assertFalse(d.allow)
        self.assertEqual(d.reason, "protected")


class SamplerTests(unittest.TestCase):
    def test_cgroup_is_not_the_group_key(self) -> None:
        """Children inherit the terminal's app scope; do not merge binaries."""
        with tempfile.TemporaryDirectory() as tmp:
            procfs = Path(tmp)
            (procfs / "stat").write_text(f"btime {int(time.time()) - 60}\n")
            uid = os.getuid()
            scope = (
                "0::/user.slice/user-1000.slice/user@1000.service/"
                "app.slice/app-org.kde.konsole-xx.scope"
            )
            _write_proc(
                procfs, 11, comm="konsole", uid=uid, exe="/usr/bin/konsole",
                cmdline=b"konsole\x00", cgroup=scope,
            )
            _write_proc(
                procfs, 12, comm="sleep", uid=uid, exe="/usr/bin/sleep",
                cmdline=b"sleep\x003600\x00", cgroup=scope,
            )
            sampler = Sampler(procfs=procfs, db_path=None, uid=uid)
            sampler.tick()
            keys = {g.key for g in sampler.grouped()}
            self.assertIn("konsole", keys)
            self.assertIn("sleep", keys)

    def test_running_elapsed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            procfs = Path(tmp)
            (procfs / "stat").write_text(f"btime {int(time.time()) - 120}\n")
            uid = os.getuid()
            _write_proc(procfs, 77, comm="firefox", start_ticks=0, uid=uid, rss_kb=8192)
            sampler = Sampler(procfs=procfs, db_path=None, uid=uid)
            sampler.tick()
            groups = sampler.grouped()
            self.assertTrue(groups)
            ff = next(g for g in groups if "firefox" in g.key or "firefox" in g.comms)
            self.assertGreaterEqual(ff.elapsed_sec, 100)
            self.assertIn(77, ff.pids)


class McpTests(unittest.TestCase):
    def test_newline_roundtrip(self) -> None:
        buf = io.BytesIO()
        write_message(buf, {"jsonrpc": "2.0", "id": 1, "method": "ping"}, framed=False)
        buf.seek(0)
        msg = read_message(buf)
        self.assertEqual(msg["method"], "ping")

    def test_framed_roundtrip(self) -> None:
        buf = io.BytesIO()
        write_message(buf, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, framed=True)
        buf.seek(0)
        msg = read_message(buf)
        self.assertEqual(msg["id"], 2)

    def test_core_initialize_and_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            procfs = Path(tmp)
            (procfs / "stat").write_text(f"btime {int(time.time()) - 30}\n")
            _write_proc(procfs, 5, comm="kate", start_ticks=0, uid=os.getuid(),
                        cgroup="0::/user.slice/app.slice/app-org.kde.kate-xx.scope",
                        exe="/usr/bin/kate", cmdline=b"kate\x00")
            core = Core(Config(), procfs=procfs, db_path=None)
            core.sampler.tick()
            reply = core.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"}, lambda m: None)
            self.assertEqual(reply["result"]["serverInfo"]["name"], "synapseos")
            reply = core.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, lambda m: None)
            names = {t["name"] for t in reply["result"]["tools"]}
            self.assertIn("apps_running", names)
            self.assertIn("proc_list", names)
            reply = core.handle(
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                 "params": {"name": "apps_running", "arguments": {}}},
                lambda m: None,
            )
            data = reply["result"]["structuredContent"]
            self.assertTrue(data["ok"])
            self.assertTrue(data["apps"])

    def test_shell_rejects_string(self) -> None:
        core = Core(Config(), procfs="/proc", db_path=None)
        tools = ToolBroker(core)
        result = tools.call("shell_run", {"argv": "rm -rf /"})
        self.assertFalse(result["ok"])
        self.assertIn("list", result["error"])

    def test_ask_needs_key(self) -> None:
        core = Core(Config(), procfs="/proc", db_path=None)
        reply = core.handle(
            {"jsonrpc": "2.0", "id": 4, "method": "synapse/ask",
             "params": {"text": "what is running"}},
            lambda m: None,
        )
        self.assertEqual(reply["result"]["status"], "needs_key")

    def test_sudo_blocked(self) -> None:
        core = Core(Config(), procfs="/proc", db_path=None)
        # skip consent so we hit the blocklist
        result = core.tools.call("shell_run", {"argv": ["sudo", "id"], "_confirmed": True})
        self.assertFalse(result["ok"])
        self.assertIn("sudo", result["error"])


class ConfigTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            cfg = Config()
            cfg.model.api_key = "xai-test"
            cfg.policy.mode = "observe"
            save(cfg, path)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            loaded = load(path)
            self.assertEqual(loaded.model.api_key, "xai-test")
            self.assertEqual(loaded.policy.mode, "observe")
            self.assertIn("[model]", _dump(cfg))


class DesktopConfigTests(unittest.TestCase):
    def test_kwin_uses_breeze_decorations(self) -> None:
        for rel in (
            "archiso/airootfs/etc/xdg/kwinrc",
            "archiso/airootfs/etc/skel/.config/kwinrc",
            "archiso/airootfs/usr/share/plasma/look-and-feel/"
            "Catppuccin-Macchiato-Mauve/contents/defaults",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("library=org.kde.breeze", text, rel)
            self.assertIn("theme=Breeze", text, rel)
            self.assertNotIn("aurorae", text, rel)

    def test_scale_bounce_and_firefox_ssd(self) -> None:
        effect = ROOT / "archiso/airootfs/usr/share/synapseos/kwin/scale-main.js"
        self.assertTrue(effect.is_file())
        self.assertIn("OutBounce", effect.read_text(encoding="utf-8"))
        pref = ROOT / "archiso/airootfs/usr/lib/firefox/defaults/pref/synapseos.js"
        self.assertIn("browser.tabs.inTitlebar", pref.read_text(encoding="utf-8"))
        kwinrc = (ROOT / "archiso/airootfs/etc/xdg/kwinrc").read_text(encoding="utf-8")
        self.assertIn("scaleEnabled=true", kwinrc)
        self.assertIn("synapseosjumpEnabled=false", kwinrc)
        self.assertIn("magiclampEnabled=true", kwinrc)
        self.assertIn("blurEnabled=true", kwinrc)
        self.assertIn("better_blur_dxEnabled=true", kwinrc)
        self.assertIn("synapseosfrostEnabled=true", kwinrc)

    def test_jetbrains_fonts_and_konsole_profile(self) -> None:
        kde = (ROOT / "archiso/airootfs/etc/skel/.config/kdeglobals").read_text(
            encoding="utf-8"
        )
        self.assertIn("JetBrainsMono Nerd Font Propo", kde)
        self.assertIn("JetBrainsMono Nerd Font Mono", kde)
        self.assertNotIn("JetBrainsMono NFP,", kde)
        profile = (
            ROOT / "archiso/airootfs/etc/skel/.local/share/konsole/SynapseOS.profile"
        ).read_text(encoding="utf-8")
        self.assertIn("JetBrainsMono Nerd Font Mono", profile)
        desk = (
            ROOT / "archiso/airootfs/etc/skel/.local/share/applications/"
            "org.kde.konsole.desktop"
        ).read_text(encoding="utf-8")
        self.assertIn("--profile SynapseOS.profile", desk)
        self.assertIn("NoDisplay=true", desk)
        kitty_conf = (
            ROOT / "archiso/airootfs/etc/skel/.config/kitty/kitty.conf"
        ).read_text(encoding="utf-8")
        self.assertIn("background_opacity 0.78", kitty_conf)
        self.assertIn("background_blur 32", kitty_conf)
        self.assertIn("JetBrainsMono Nerd Font Mono", kitty_conf)
        frost = (
            ROOT / "archiso/airootfs/usr/share/kwin/effects/synapseosfrost/"
            "contents/code/main.js"
        )
        self.assertTrue(frost.is_file())
        frost_js = frost.read_text(encoding="utf-8")
        self.assertIn("WindowForceBlurRole", frost_js)
        self.assertIn("window.dock", frost_js)
        frost_img = (
            ROOT / "archiso/airootfs/usr/share/backgrounds/synapseos/"
            "desktop-frost.jpg"
        )
        self.assertTrue(frost_img.is_file())
        self.assertGreater(frost_img.stat().st_size, 10_000)
        self.assertTrue(
            (ROOT / "archiso/airootfs/usr/share/synapseos/frost-noise.png").is_file()
        )
        self.assertTrue((ROOT / "tools/gen-frost.py").is_file())
        kde = ROOT / "archiso/airootfs/etc/skel/.config/kdeglobals"
        self.assertIn("TerminalApplication=kitty", kde.read_text(encoding="utf-8"))
        rules = (
            ROOT / "archiso/airootfs/etc/skel/.config/kwinrulesrc"
        ).read_text(encoding="utf-8")
        # Browsers must be listed before the catch-all or they stay translucent.
        self.assertIn(
            "rules=a11e0001-5e0f-4b10-9c0d-000000000004,a11e0001-5e0f-4b10-9c0d-000000000002,a11e0001-5e0f-4b10-9c0d-000000000003,a11e0001-5e0f-4b10-9c0d-000000000001",
            rules,
        )
        self.assertIn("org.synapseos.menu", rules)
        chrome = ROOT / "archiso/airootfs/usr/bin/synapseos-apply-chrome"
        self.assertTrue(chrome.is_file())
        text = chrome.read_text(encoding="utf-8")
        self.assertIn("isEffectLoaded better_blur_dx", text)
        self.assertIn("blurEnabled true", text)
        self.assertIn("loadEffect blur", text)
        self.assertIn("loadEffect synapseosfrost", text)
        # Better Blur DX reports loaded but composites nothing on virgl:
        # a VM must always end up on stock blur + frost, never DX.
        self.assertIn("systemd-detect-virt -q", text)
        self.assertIn("unloadEffect better_blur_dx", text)
        self.assertIn("desktop-frost.jpg", text)
        self.assertIn("BlurStrength 7", text)
        gfx = (
            ROOT / "archiso/airootfs/etc/profile.d/synapseos-graphics.sh"
        ).read_text(encoding="utf-8")
        # O is fatal when OpenGL cannot start. Prefer Vulkan-off instead.
        self.assertNotIn('KWIN_COMPOSE="${KWIN_COMPOSE:-O}"', gfx)
        self.assertIn('KWIN_COMPOSE="${KWIN_COMPOSE:-Q}"', gfx)
        self.assertIn('KWIN_DISABLE_VULKAN="${KWIN_DISABLE_VULKAN:-1}"', gfx)
        self.assertIn('QT_QUICK_BACKEND="${QT_QUICK_BACKEND:-software}"', gfx)
        self.assertIn("systemd-detect-virt", gfx)
        gen = (
            ROOT
            / "archiso/airootfs/usr/lib/systemd/user-environment-generators"
            / "30-synapseos-graphics"
        )
        self.assertTrue(gen.is_file())
        self.assertTrue(stat.S_IXUSR & gen.stat().st_mode)
        self.assertIn("synapseos-graphics.sh", gen.read_text(encoding="utf-8"))
        env = (
            ROOT / "archiso/airootfs/etc/xdg/plasma-workspace/env/"
            "synapseos-graphics.sh"
        )
        self.assertTrue(env.is_file())
        fix = ROOT / "archiso/airootfs/usr/bin/synapseos-fix-blur"
        self.assertTrue(fix.is_file())
        self.assertTrue(stat.S_IXUSR & fix.stat().st_mode)
        fix_text = fix.read_text(encoding="utf-8")
        self.assertIn("kwin_wayland --replace", fix_text)
        self.assertIn("systemd-detect-virt -q", fix_text)
        self.assertIn("unloadEffect better_blur_dx", fix_text)
        pkgs = (ROOT / "archiso/packages.x86_64").read_text(encoding="utf-8")
        self.assertRegex(pkgs, r"(?m)^vulkan-swrast$")
        self.assertRegex(pkgs, r"(?m)^vulkan-virtio$")
        hotfix = ROOT / "tools/live-hotfix-desktop.sh"
        self.assertIn("synapseosfrost", hotfix.read_text(encoding="utf-8"))
        runner = ROOT / "tools/run-iso.sh"
        self.assertTrue(runner.is_file())
        text = runner.read_text(encoding="utf-8")
        self.assertIn("virtio-vga-gl", text)
        self.assertIn("qcow2", text)
        self.assertIn("if=virtio", text)
        self.assertIn("sdl,gl=on", text)
        self.assertIn("do not use sudo", text)

    def test_aether_plasma_hook_prefers_rendered_template(self) -> None:
        hook = (
            ROOT / "archiso/airootfs/etc/skel/.config/aether/custom/plasma/"
            "post-apply.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("omarchy/themes/aether", hook)
        # Must not treat the installed scheme as the first source.
        first_src = hook.split("for cand in")[1].split("do")[0]
        self.assertIn("omarchy/themes/aether", first_src)
        self.assertNotIn("color-schemes/Aether.colors", first_src)
        pkgs = (ROOT / "archiso/packages.x86_64").read_text(encoding="utf-8")
        self.assertRegex(pkgs, r"(?m)^aether$")
        self.assertRegex(pkgs, r"(?m)^gtk-layer-shell$")
        desk = (
            ROOT / "archiso/airootfs/usr/share/synapseos/aether/aether.desktop"
        ).read_text(encoding="utf-8")
        self.assertIn("WEBKIT_DISABLE_COMPOSITING_MODE=1", desk)
        custom = (
            ROOT / "archiso/airootfs/root/customize_airootfs.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("aether.desktop", custom)
        self.assertIn("kwin-wayland/scripts/synapseostile", custom)

    def test_plymouth_is_wired(self) -> None:
        pkgs = (ROOT / "archiso/packages.x86_64").read_text(encoding="utf-8")
        self.assertRegex(pkgs, r"(?m)^plymouth$")
        hooks = (
            ROOT / "archiso/airootfs/etc/mkinitcpio.conf.d/archiso.conf"
        ).read_text(encoding="utf-8")
        self.assertRegex(hooks, r"HOOKS=\(.*\budev plymouth\b")
        ply = ROOT / "archiso/airootfs/usr/share/plymouth/themes/synapseos"
        self.assertTrue((ply / "synapseos.plymouth").is_file())
        self.assertTrue((ply / "synapseos.script").is_file())
        self.assertTrue((ply / "logo.png").is_file())
        conf = (
            ROOT / "archiso/airootfs/etc/plymouth/plymouthd.conf"
        ).read_text(encoding="utf-8")
        self.assertIn("Theme=synapseos", conf)
        settings = (
            ROOT / "archiso/airootfs/etc/calamares/settings.conf"
        ).read_text(encoding="utf-8")
        self.assertIn("shellprocess@plymouth", settings)
        inject = ROOT / "archiso/airootfs/usr/share/synapseos/inject-plymouth.sh"
        self.assertTrue(inject.is_file())

    def test_quiet_splash_is_the_default_boot(self) -> None:
        grub = (ROOT / "archiso/grub/grub.cfg").read_text(encoding="utf-8")
        default_block = grub.split("menuentry \"SynapseOS\"", 1)[1].split("submenu", 1)[0]
        self.assertIn("quiet", default_block)
        self.assertIn("splash", default_block)
        self.assertIn("copytoram=n", default_block)
        self.assertIn("cow_spacesize=1G", default_block)
        self.assertIn("systemd.gpt_auto=no", default_block)
        self.assertIn("libata.force=noncq", default_block)
        self.assertNotIn("copytoram=y", default_block)
        self.assertNotIn("safegfx", default_block)
        gen = (
            ROOT
            / "archiso/airootfs/etc/systemd/system-generators/"
            "systemd-gpt-auto-generator"
        ).read_text(encoding="utf-8")
        self.assertTrue(gen.startswith("#!"))
        self.assertIn("exit 0", gen)
        self.assertGreater(len(gen.strip()), 20)
        self.assertIn("timeout=5", grub)
        self.assertNotIn("selected_item_pixmap_style", grub)
        theme = (ROOT / "archiso/grub/theme/theme.txt").read_text(encoding="utf-8")
        self.assertNotIn("selected_item_pixmap_style", theme)
        installed = (
            ROOT / "archiso/airootfs/etc/default/grub"
        ).read_text(encoding="utf-8")
        self.assertIn("quiet splash", installed)
        self.assertIn('GRUB_TIMEOUT=3', installed)
        grubcfg = (
            ROOT / "archiso/airootfs/etc/calamares/modules/grubcfg.conf"
        ).read_text(encoding="utf-8")
        self.assertIn('"splash"', grubcfg)
        self.assertIn("GRUB_TIMEOUT: 3", grubcfg)

    def test_live_boot_does_not_copy_the_os_into_ram(self) -> None:
        grub = (ROOT / "archiso/grub/grub.cfg").read_text(encoding="utf-8")
        default_block = grub.split('menuentry "SynapseOS"', 1)[1].split("submenu", 1)[0]
        self.assertIn("copytoram=n", default_block)
        self.assertIn("systemd.gpt_auto=no", default_block)
        self.assertIn("libata.force=noncq", default_block)
        self.assertNotIn("copytoram=y", default_block)
        self.assertIn("archlinux-copytoram", grub)
        ram_block = grub.split("archlinux-copytoram", 1)[1].split("}", 1)[0]
        self.assertIn("copytoram=y", ram_block)
        self.assertIn("systemd.gpt_auto=no", ram_block)
        self.assertIn("libata.force=noncq", ram_block)
        loop = (ROOT / "archiso/grub/loopback.cfg").read_text(encoding="utf-8")
        loop_default = loop.split('menuentry "SynapseOS"', 1)[1].split("submenu", 1)[0]
        self.assertIn("copytoram=n", loop_default)
        self.assertIn("systemd.gpt_auto=no", loop_default)
        self.assertIn("libata.force=noncq", loop_default)
        syslinux = (
            ROOT / "archiso/syslinux/archiso_sys-linux.cfg"
        ).read_text(encoding="utf-8")
        first_append = [
            line for line in syslinux.splitlines() if line.startswith("APPEND ")
        ][0]
        self.assertIn("copytoram=n", first_append)
        self.assertIn("cow_spacesize=1G", first_append)
        self.assertIn("systemd.gpt_auto=no", first_append)
        self.assertIn("libata.force=noncq", first_append)
        self.assertIn("copytoram=y", syslinux)
        pxe = (
            ROOT / "archiso/syslinux/archiso_pxe-linux.cfg"
        ).read_text(encoding="utf-8")
        self.assertIn("copytoram=n", pxe)
        installed = (
            ROOT / "archiso/airootfs/etc/default/grub"
        ).read_text(encoding="utf-8")
        self.assertNotIn("copytoram", installed)

    def test_sddm_and_ksplash_are_synapseos(self) -> None:
        sddm = (
            ROOT / "archiso/airootfs/etc/sddm.conf.d/10-synapseos.conf"
        ).read_text(encoding="utf-8")
        self.assertIn("Current=breeze", sddm)
        breeze_user = (
            ROOT / "archiso/airootfs/usr/share/sddm/themes/breeze/theme.conf.user"
        )
        self.assertTrue(breeze_user.is_file())
        breeze_conf = breeze_user.read_text(encoding="utf-8")
        self.assertIn("/usr/share/backgrounds/synapseos/desktop.png", breeze_conf)
        self.assertIn("showClock=true", breeze_conf)
        self.assertTrue(
            (
                ROOT / "archiso/airootfs/usr/share/backgrounds/synapseos/desktop.png"
            ).is_file()
        )
        defaults = (
            ROOT
            / "archiso/airootfs/usr/share/plasma/look-and-feel/"
            "Catppuccin-Macchiato-Mauve/contents/defaults"
        ).read_text(encoding="utf-8")
        self.assertIn("Theme=Catppuccin-Macchiato-Mauve", defaults)
        self.assertNotIn("Catppuccin-Macchiato-Mauve-splash", defaults)
        splash = (
            ROOT
            / "archiso/airootfs/usr/share/plasma/look-and-feel/"
            "Catppuccin-Macchiato-Mauve/contents/splash/Splash.qml"
        )
        self.assertTrue(splash.is_file())

    def test_installed_system_gets_a_real_pacman_keyring(self) -> None:
        post = (
            ROOT / "archiso/airootfs/usr/share/synapseos/postinstall.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("pacman-key --init", post)
        self.assertIn("pacman-key --populate archlinux", post)
        # Must rebuild the keyring *after* the live tmpfs unit is removed,
        # otherwise we populate a directory that is about to vanish.
        self.assertLess(
            post.index("etc-pacman.d-gnupg.mount"),
            post.index("pacman-key --init"),
        )
        self.assertLess(
            post.index("pacman-key --init"),
            post.index("pacman -Rns --noconfirm calamares"),
        )
        pkgs = (ROOT / "archiso/packages.x86_64").read_text(encoding="utf-8")
        self.assertRegex(pkgs, r"(?m)^obs-studio$")

    def test_omarchy_style_workflow_is_wired(self) -> None:
        cli = ROOT / "archiso/airootfs/usr/bin/synapseos"
        self.assertTrue(cli.is_file())
        self.assertTrue(stat.S_IXUSR & cli.stat().st_mode)
        text = cli.read_text(encoding="utf-8")
        self.assertIn("synapseos-menu", text)
        self.assertIn("synapseos-install", text)
        self.assertIn("synapseos-pkg", text)
        for name in (
            "synapseos-menu",
            "synapseos-install",
            "synapseos-install-dev-env",
            "synapseos-install-docker-dbs",
            "synapseos-pkg",
            "synapseos-launch",
            "synapseos-keybindings",
            "synapseos-toggle",
        ):
            path = ROOT / "archiso/airootfs/usr/share/synapseos/bin" / name
            self.assertTrue(path.is_file(), name)
            self.assertTrue(stat.S_IXUSR & path.stat().st_mode, name)
        keys = (
            ROOT / "archiso/airootfs/usr/share/synapseos/keybindings.txt"
        ).read_text(encoding="utf-8")
        self.assertIn("Super + Space", keys)
        self.assertIn("Super + Return", keys)
        shortcuts = (
            ROOT / "archiso/airootfs/etc/xdg/kglobalshortcutsrc"
        ).read_text(encoding="utf-8")
        self.assertIn("Meta+Space", shortcuts)
        self.assertIn("Meta+Return", shortcuts)
        self.assertIn("Meta+Shift+F", shortcuts)
        self.assertIn("Meta+K", shortcuts)
        self.assertIn("synapseos-menu.desktop", shortcuts)
        skel_keys = (
            ROOT / "archiso/airootfs/etc/skel/.config/kglobalshortcutsrc"
        ).read_text(encoding="utf-8")
        self.assertEqual(shortcuts, skel_keys)
        menu_desk = (
            ROOT / "archiso/airootfs/usr/share/applications/synapseos-menu.desktop"
        ).read_text(encoding="utf-8")
        self.assertIn("Exec=synapseos menu", menu_desk)
        self.assertIn("X-KDE-Shortcuts=Meta+Space", menu_desk)
        zshrc = (ROOT / "archiso/airootfs/etc/skel/.zshrc.local").read_text(
            encoding="utf-8"
        )
        self.assertFalse(
            (ROOT / "archiso/airootfs/etc/skel/.zshrc").exists(),
            "airootfs must not ship /etc/skel/.zshrc; grml-zsh-config owns it",
        )
        self.assertIn("starship init zsh", zshrc)
        self.assertIn("zoxide init zsh", zshrc)
        self.assertIn("mise activate zsh", zshrc)
        pkgs = (ROOT / "archiso/packages.x86_64").read_text(encoding="utf-8")
        for pkg in (
            "btop",
            "starship",
            "zoxide",
            "gum",
            "mise",
            "lazydocker",
            "wl-clipboard",
            "mpv",
        ):
            self.assertRegex(pkgs, rf"(?m)^{pkg}$")
        install = (
            ROOT / "archiso/airootfs/usr/share/synapseos/bin/synapseos-install"
        ).read_text(encoding="utf-8")
        self.assertIn("dev-env", install)
        self.assertIn("docker-dbs", install)
        self.assertIn("browser", install)

    def test_hyprland_mode_toggle_is_wired(self) -> None:
        script = (
            ROOT / "archiso/airootfs/usr/share/kwin/scripts/synapseostile"
            / "contents/code/main.js"
        )
        self.assertTrue(script.is_file())
        js = script.read_text(encoding="utf-8")
        self.assertIn("Meta+Shift+Space", js)
        self.assertIn("saved[key]", js)
        self.assertIn("restoreAll", js)
        self.assertIn("dwindle", js)
        self.assertIn('"Meta+" + key', js)
        self.assertIn("desktopKeys", js)
        meta = (
            ROOT / "archiso/airootfs/usr/share/kwin/scripts/synapseostile"
            / "metadata.json"
        ).read_text(encoding="utf-8")
        self.assertIn('"Id": "synapseostile"', meta)
        for rel in (
            "archiso/airootfs/etc/xdg/kwinrc",
            "archiso/airootfs/etc/skel/.config/kwinrc",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("synapseostileEnabled=true", text, rel)
            self.assertIn("Number=10", text, rel)
        shortcuts = (
            ROOT / "archiso/airootfs/etc/xdg/kglobalshortcutsrc"
        ).read_text(encoding="utf-8")
        self.assertIn("activate task manager entry 1=none,Meta+1", shortcuts)
        self.assertIn("toggle tiling", (
            ROOT / "archiso/airootfs/usr/bin/synapseos"
        ).read_text(encoding="utf-8"))
        toggle = (
            ROOT / "archiso/airootfs/usr/share/synapseos/bin/synapseos-toggle"
        ).read_text(encoding="utf-8")
        self.assertIn("Toggle SynapseOS Hyprland mode", toggle)
        menu = (
            ROOT / "archiso/airootfs/usr/share/synapseos/bin/synapseos-menu"
        ).read_text(encoding="utf-8")
        self.assertIn("Hyprland tiling", menu)
        keys = (
            ROOT / "archiso/airootfs/usr/share/synapseos/keybindings.txt"
        ).read_text(encoding="utf-8")
        self.assertIn("Super + Shift + Space", keys)

    def test_calamares_branding_is_one_mark(self) -> None:
        desc = (
            ROOT / "archiso/airootfs/etc/calamares/branding/synapseos/branding.desc"
        ).read_text(encoding="utf-8")
        self.assertNotIn("welcome.png", desc)
        self.assertNotIn("banner.png", desc)
        self.assertIn("productLogo: \"logo.png\"", desc)
        welcome = (
            ROOT / "archiso/airootfs/etc/calamares/modules/welcome.conf"
        ).read_text(encoding="utf-8")
        self.assertIn("showSupportUrl: false", welcome)


if __name__ == "__main__":
    unittest.main()
