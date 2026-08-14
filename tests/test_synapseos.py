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
        chrome = ROOT / "archiso/airootfs/usr/bin/synapseos-apply-chrome"
        self.assertTrue(chrome.is_file())

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


if __name__ == "__main__":
    unittest.main()
