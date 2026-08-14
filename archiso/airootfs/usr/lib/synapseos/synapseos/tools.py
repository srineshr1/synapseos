"""Typed OS tools the model is allowed to call."""

from __future__ import annotations

import os
import signal
import shutil
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any, Callable

from . import audit
from .mcp import tool_spec
from .perception import apps as apps_mod
from .perception import sysinfo, windows as win_mod
from .perception.proc import fmt_duration
from .policy import (
    Policy,
    describe_close,
    describe_kill,
    describe_shell,
    describe_throttle,
    is_protected,
)

Handler = Callable[[dict[str, Any]], dict[str, Any]]

SHELL_BLOCKLIST = {
    "sudo", "su", "pkexec", "doas", "passwd", "chpasswd",
    "visudo", "newgrp", "sg",
}


class ToolBroker:
    def __init__(self, core: Any):
        self.core = core
        self.specs = _SPECS
        self._handlers: dict[str, Handler] = {
            "apps_list": self.apps_list,
            "apps_running": self.apps_running,
            "apps_launch": self.apps_launch,
            "apps_focus": self.apps_focus,
            "apps_close": self.apps_close,
            "windows_list": self.windows_list,
            "browser_open": self.browser_open,
            "browser_navigate": self.browser_navigate,
            "browser_tabs": self.browser_tabs,
            "proc_list": self.proc_list,
            "proc_explain": self.proc_explain,
            "proc_throttle": self.proc_throttle,
            "proc_kill": self.proc_kill,
            "sys_status": self.sys_status,
            "notify_send": self.notify_send,
            "files_open": self.files_open,
            "shell_run": self.shell_run,
            "policy_status": self.policy_status,
            "policy_set_mode": self.policy_set_mode,
        }

    def names(self) -> list[str]:
        return list(self._handlers)

    def xai_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": spec["name"],
                "description": spec["description"],
                "parameters": spec["inputSchema"],
            }
            for spec in self.specs
        ]

    def call(self, name: str, arguments: dict[str, Any] | None, *,
             skip_consent: bool = False) -> dict[str, Any]:
        arguments = arguments or {}
        handler = self._handlers.get(name)
        if handler is None:
            return {"ok": False, "error": f"unknown tool {name}"}
        try:
            result = handler(arguments) if name in {
                "apps_list", "apps_running", "windows_list", "browser_tabs",
                "proc_list", "sys_status", "policy_status",
            } else handler(arguments)
            # Gate mutating tools that haven't already decided.
            if name not in {
                "apps_list", "apps_running", "windows_list", "browser_tabs",
                "proc_list", "proc_explain", "sys_status", "policy_status",
            }:
                pass
            return result
        except ConsentNeeded as exc:
            return {
                "ok": False,
                "status": "needs_consent",
                "consent_id": exc.consent_id,
                "summary": exc.summary,
            }
        except ToolError as exc:
            audit.record("tool", tool=name, status="error", error=str(exc))
            return {"ok": False, "error": str(exc), "reason": exc.reason}
        except Exception as exc:  # noqa: BLE001 — surface to the model, don't crash
            audit.record("tool", tool=name, status="crash", error=str(exc))
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # The mutating helpers call _gate themselves so they can build a
    # human summary from resolved targets (pid, title, argv).

    def apps_list(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query") or "").strip()
        apps = apps_mod.visible_apps(self.core.desktop_apps())
        if query:
            q = query.lower()
            apps = [a for a in apps if q in a.name.lower() or q in a.id.lower()]
        return {"ok": True, "apps": [a.to_dict() for a in apps[:80]]}

    def apps_running(self, arguments: dict[str, Any]) -> dict[str, Any]:
        limit = _int(arguments.get("limit"), 24)
        groups = self.core.sampler.grouped(win_mod.windows_by_pid())
        return {"ok": True, "apps": [g.to_dict() for g in groups[:limit]]}

    def apps_launch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query") or arguments.get("app") or "").strip()
        if not query:
            raise ToolError("query is required")
        self._gate("apps_launch", arguments, summary=f"Launch {query}")
        app = apps_mod.match_app(query, self.core.desktop_apps())
        if app is None:
            raise ToolError(f"no installed app matches {query!r}")
        if not _launch_desktop(app.id):
            raise ToolError(f"failed to launch {app.id}")
        audit.record("tool", tool="apps_launch", status="ok", app=app.id)
        return {"ok": True, "launched": app.to_dict()}

    def apps_focus(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query") or arguments.get("app") or "").strip()
        if not query:
            raise ToolError("query is required")
        self._gate("apps_focus", arguments, summary=f"Focus {query}")
        win = win_mod.focus_window(query)
        if win is not None:
            audit.record("tool", tool="apps_focus", status="ok", title=win.title)
            return {"ok": True, "window": win.to_dict(), "method": "window"}
        # Single-instance apps raise themselves when launched again.
        app = apps_mod.match_app(query, self.core.desktop_apps())
        if app is None:
            raise ToolError(f"no window or app matches {query!r}")
        if not _launch_desktop(app.id):
            raise ToolError(f"could not focus {query!r}")
        audit.record("tool", tool="apps_focus", status="ok", app=app.id, method="relaunch")
        return {"ok": True, "app": app.to_dict(), "method": "relaunch"}

    def apps_close(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query") or arguments.get("app") or "").strip()
        if not query:
            raise ToolError("query is required")
        wins = win_mod.list_windows()
        win = None
        for item in wins:
            if query.lower() in (item.title.lower() + " " + item.app_id.lower()):
                win = item
                break
        comm = win.app_id if win else query
        pid = win.pid if win else None
        title = win.title if win else query
        self._gate(
            "apps_close", arguments,
            summary=describe_close(title),
            comm=comm, pid=pid,
        )
        closed = win_mod.close_window(query, wins)
        if closed is None:
            raise ToolError(f"could not close {query!r}")
        audit.record("tool", tool="apps_close", status="ok", title=closed.title)
        return {"ok": True, "window": closed.to_dict()}

    def windows_list(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "windows": [w.to_dict() for w in win_mod.list_windows()]}

    def browser_open(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.browser_navigate(arguments)

    def browser_navigate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        url = _normalize_url(str(arguments.get("url") or arguments.get("query") or ""))
        if not url:
            raise ToolError("url is required")
        self._gate("browser_navigate", arguments, summary=f"Open {url}")
        if not _xdg_open(url):
            raise ToolError(f"xdg-open failed for {url}")
        audit.record("tool", tool="browser_navigate", status="ok", url=url)
        return {"ok": True, "url": url}

    def browser_tabs(self, arguments: dict[str, Any]) -> dict[str, Any]:
        # plasma-browser-integration does not expose a stable public D-Bus
        # navigate API. Surface whatever window titles look like browser tabs.
        tabs = []
        for win in win_mod.list_windows():
            app = win.app_id.lower()
            if any(token in app for token in ("firefox", "helium", "chrom", "brave", "librewolf")):
                tabs.append(win.to_dict())
        return {"ok": True, "tabs": tabs, "note": "titles from the window manager"}

    def proc_list(self, arguments: dict[str, Any]) -> dict[str, Any]:
        limit = _int(arguments.get("limit"), 30)
        sort = str(arguments.get("sort") or "cpu")
        procs = list(self.core.sampler.processes())
        if sort == "rss":
            procs.sort(key=lambda p: (-p.rss_kb, p.comm))
        elif sort == "elapsed":
            procs.sort(key=lambda p: (-p.elapsed_sec, p.comm))
        else:
            procs.sort(key=lambda p: (-p.cpu_pct, -p.rss_kb, p.comm))
        return {
            "ok": True,
            "processes": [p.to_dict() for p in procs[:limit]],
        }

    def proc_explain(self, arguments: dict[str, Any]) -> dict[str, Any]:
        pid = _int(arguments.get("pid"), 0)
        if pid <= 0:
            raise ToolError("pid is required")
        proc = self.core.sampler.process(pid)
        if proc is None:
            raise ToolError(f"pid {pid} is not in the current snapshot")
        key = proc.desktop_id or Path(proc.exe).name or proc.comm
        spark = self.core.sampler.spark(key)
        first = self.core.sampler.first_seen(key)
        return {
            "ok": True,
            "process": proc.to_dict(spark=spark),
            "session_elapsed": fmt_duration(
                max(0.0, (self.core.sampler._last_tick or 0) - first) if first else proc.elapsed_sec
            ),
            "protected": is_protected(comm=proc.comm, pid=proc.pid, exe=proc.exe),
        }

    def proc_throttle(self, arguments: dict[str, Any]) -> dict[str, Any]:
        pid = _int(arguments.get("pid"), 0)
        percent = _int(arguments.get("percent"), 25)
        percent = max(1, min(100, percent))
        proc = self._need_proc(pid)
        self._gate(
            "proc_throttle", arguments,
            summary=describe_throttle(proc.comm, proc.pid, percent),
            comm=proc.comm, pid=proc.pid, exe=proc.exe,
        )
        path = _cpu_max_path(proc)
        if path is None:
            raise ToolError("no writable cgroup cpu.max for this process")
        quota = int(100000 * percent / 100)  # usec of each 100ms period
        try:
            path.write_text(f"{quota} 100000\n", encoding="utf-8")
        except OSError as exc:
            raise ToolError(f"cannot write cpu.max: {exc}") from exc
        audit.record("tool", tool="proc_throttle", status="ok", pid=pid, percent=percent)
        return {"ok": True, "pid": pid, "percent": percent, "cgroup": str(path)}

    def proc_kill(self, arguments: dict[str, Any]) -> dict[str, Any]:
        pid = _int(arguments.get("pid"), 0)
        hard = bool(arguments.get("force") or arguments.get("kill"))
        sig = signal.SIGKILL if hard else signal.SIGTERM
        proc = self._need_proc(pid)
        self._gate(
            "proc_kill", arguments,
            summary=describe_kill(proc.comm, proc.pid, "KILL" if hard else "TERM"),
            comm=proc.comm, pid=proc.pid, exe=proc.exe,
        )
        try:
            os.kill(pid, sig)
        except OSError as exc:
            raise ToolError(f"kill({pid}) failed: {exc}") from exc
        audit.record("tool", tool="proc_kill", status="ok", pid=pid, signal=sig.name)
        return {"ok": True, "pid": pid, "signal": sig.name}

    def sys_status(self, arguments: dict[str, Any]) -> dict[str, Any]:
        snap = sysinfo.snapshot()
        snap["ok"] = True
        snap["policy"] = self.core.policy.status()
        return snap

    def notify_send(self, arguments: dict[str, Any]) -> dict[str, Any]:
        title = str(arguments.get("title") or "SynapseOS")
        body = str(arguments.get("body") or arguments.get("message") or "")
        self._gate("notify_send", arguments, summary=f"Notify: {title}")
        exe = shutil.which("notify-send")
        if not exe:
            raise ToolError("notify-send is not installed")
        subprocess.Popen(
            [exe, "-a", "SynapseOS", title, body],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        audit.record("tool", tool="notify_send", status="ok", title=title)
        return {"ok": True}

    def files_open(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raw = str(arguments.get("path") or "").strip()
        if not raw:
            raise ToolError("path is required")
        path = Path(raw).expanduser()
        try:
            resolved = path.resolve()
        except OSError as exc:
            raise ToolError(str(exc)) from exc
        home = Path.home().resolve()
        if self.core.policy.mode != "act" and not _is_relative_to(resolved, home):
            raise ToolError("assist mode can only open paths under your home directory")
        self._gate("files_open", arguments, summary=f"Open {resolved}")
        if not _xdg_open(str(resolved)):
            raise ToolError(f"xdg-open failed for {resolved}")
        audit.record("tool", tool="files_open", status="ok", path=str(resolved))
        return {"ok": True, "path": str(resolved)}

    def shell_run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        argv = arguments.get("argv")
        if isinstance(argv, str):
            raise ToolError("argv must be a list of strings, not a shell string")
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
            raise ToolError("argv must be a non-empty list of strings")
        base = Path(argv[0]).name
        if base in SHELL_BLOCKLIST:
            raise ToolError(f"{base} is not allowed")
        cwd = arguments.get("cwd")
        cwd_path = Path(cwd).expanduser() if cwd else Path.home()
        timeout = _int(arguments.get("timeout"), 30)
        timeout = max(1, min(120, timeout))
        self._gate("shell_run", arguments, summary=describe_shell(argv))
        try:
            proc = subprocess.run(
                argv,
                cwd=str(cwd_path),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolError(f"timed out after {timeout}s") from exc
        except OSError as exc:
            raise ToolError(str(exc)) from exc
        audit.record(
            "tool", tool="shell_run", status="ok" if proc.returncode == 0 else "exit",
            argv=argv, code=proc.returncode,
        )
        return {
            "ok": proc.returncode == 0,
            "code": proc.returncode,
            "stdout": (proc.stdout or "")[:8000],
            "stderr": (proc.stderr or "")[:4000],
        }

    def policy_status(self, arguments: dict[str, Any]) -> dict[str, Any]:
        st = self.core.policy.status()
        st["ok"] = True
        st["has_key"] = self.core.cfg.has_key()
        return st

    def policy_set_mode(self, arguments: dict[str, Any]) -> dict[str, Any]:
        mode = str(arguments.get("mode") or "").strip().lower()
        if mode == "pause" or arguments.get("paused") is True:
            self._gate("policy_set_mode", arguments, summary="Pause Synapse (kill switch)")
            self.core.set_paused(True)
            return {"ok": True, "paused": True, "mode": self.core.policy.mode}
        if mode == "resume" or arguments.get("paused") is False:
            self.core.set_paused(False)
            return {"ok": True, "paused": False, "mode": self.core.policy.mode}
        if mode not in {"observe", "assist", "act"}:
            raise ToolError("mode must be observe, assist, act, pause, or resume")
        if mode == "act":
            self._gate("policy_set_mode", arguments, summary="Switch Synapse to ACT mode")
        self.core.set_mode(mode)
        audit.record("tool", tool="policy_set_mode", status="ok", mode=mode)
        return {"ok": True, "mode": mode, "paused": self.core.policy.paused}

    def _need_proc(self, pid: int):
        if pid <= 0:
            raise ToolError("pid is required")
        proc = self.core.sampler.process(pid)
        if proc is None:
            # last-chance live read so we can still refuse protected pids
            from .perception.proc import read_process
            proc = read_process(pid)
        if proc is None:
            raise ToolError(f"pid {pid} not found")
        return proc

    def _gate(self, tool: str, arguments: dict[str, Any], *, summary: str,
              comm: str = "", pid: int | None = None, exe: str = "") -> None:
        skip = bool(arguments.pop("_confirmed", False))
        decision = self.core.policy.check(
            tool, arguments, summary=summary, comm=comm, pid=pid, exe=exe,
            skip_consent=skip,
        )
        if decision.needs_consent:
            raise ConsentNeeded(decision.consent_id, decision.summary)
        if not decision.allow:
            raise ToolError(decision.error, reason=decision.reason)


class ToolError(Exception):
    def __init__(self, message: str, reason: str = "error"):
        super().__init__(message)
        self.reason = reason


class ConsentNeeded(Exception):
    def __init__(self, consent_id: str, summary: str):
        super().__init__(summary)
        self.consent_id = consent_id
        self.summary = summary


def _launch_desktop(desktop_id: str) -> bool:
    exe = shutil.which("gtk-launch")
    if exe:
        try:
            proc = subprocess.Popen(
                [exe, desktop_id],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return proc.returncode is None or proc.returncode == 0
        except OSError:
            return False
    kio = shutil.which("kioclient")
    if kio:
        try:
            subprocess.Popen(
                [kio, "exec", f"applications:{desktop_id}.desktop"],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except OSError:
            return False
    return False


def _xdg_open(target: str) -> bool:
    exe = shutil.which("xdg-open")
    if not exe:
        return False
    try:
        subprocess.Popen(
            [exe, target],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except OSError:
        return False


def _normalize_url(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""
    lower = text.lower()
    if lower.startswith(("http://", "https://", "file://", "about:")):
        return text
    if " " not in text and "." in text:
        return "https://" + text
    return "https://duckduckgo.com/?q=" + urllib.parse.quote(text)


def _cpu_max_path(proc) -> Path | None:
    # cgroup v2: last path in /proc/<pid>/cgroup
    cg = proc.cgroup
    if not cg:
        return None
    # strip leading controller leftovers
    rel = cg[1:] if cg.startswith("/") else cg
    path = Path("/sys/fs/cgroup") / rel / "cpu.max"
    if path.is_file() and os.access(path, os.W_OK):
        return path
    return None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


_SPECS = [
    tool_spec("apps_list", "List installed desktop applications.", {
        "query": {"type": "string", "description": "Optional name filter"},
    }),
    tool_spec("apps_running", "Apps in this session with CPU, RAM, start time and elapsed time.", {
        "limit": {"type": "integer", "description": "Max rows (default 24)"},
    }),
    tool_spec("apps_launch", "Launch an installed application by name or desktop id.", {
        "query": {"type": "string", "description": "App name or desktop id"},
    }, ["query"]),
    tool_spec("apps_focus", "Focus an open window, or raise a single-instance app.", {
        "query": {"type": "string", "description": "Window title, app id, or pid"},
    }, ["query"]),
    tool_spec("apps_close", "Close a window by title or app id.", {
        "query": {"type": "string"},
    }, ["query"]),
    tool_spec("windows_list", "List open windows (title, app, pid, focused)."),
    tool_spec("browser_open", "Open a URL in the default browser (alias of browser_navigate).", {
        "url": {"type": "string"},
    }, ["url"]),
    tool_spec("browser_navigate", "Open a URL in the default browser.", {
        "url": {"type": "string"},
    }, ["url"]),
    tool_spec("browser_tabs", "List browser windows/tabs visible to the window manager."),
    tool_spec("proc_list", "Process table for the current user, with elapsed time.", {
        "limit": {"type": "integer"},
        "sort": {"type": "string", "enum": ["cpu", "rss", "elapsed"]},
    }),
    tool_spec("proc_explain", "Details for one PID, including a CPU sparkline.", {
        "pid": {"type": "integer"},
    }, ["pid"]),
    tool_spec("proc_throttle", "Cap a process via cgroup cpu.max. Reversible.", {
        "pid": {"type": "integer"},
        "percent": {"type": "integer", "description": "1-100, percent of one CPU"},
    }, ["pid"]),
    tool_spec("proc_kill", "Send SIGTERM (or SIGKILL if force) to a pid. Blocked for the protected set.", {
        "pid": {"type": "integer"},
        "force": {"type": "boolean"},
    }, ["pid"]),
    tool_spec("sys_status", "Load, memory, disk, battery, thermals, hostname."),
    tool_spec("notify_send", "Show a desktop notification.", {
        "title": {"type": "string"},
        "body": {"type": "string"},
    }, ["title"]),
    tool_spec("files_open", "Open a file or directory with the default handler.", {
        "path": {"type": "string"},
    }, ["path"]),
    tool_spec("shell_run", "Run argv (no shell). Always needs consent. sudo/su/pkexec are refused.", {
        "argv": {"type": "array", "items": {"type": "string"}},
        "cwd": {"type": "string"},
        "timeout": {"type": "integer"},
    }, ["argv"]),
    tool_spec("policy_status", "Current mode (observe/assist/act), pause flag, pending consents."),
    tool_spec("policy_set_mode", "Set mode to observe, assist, or act, or pause/resume the kill switch.", {
        "mode": {"type": "string"},
        "paused": {"type": "boolean"},
    }),
]
