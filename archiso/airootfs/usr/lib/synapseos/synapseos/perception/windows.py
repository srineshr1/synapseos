"""Window list / focus / close. KWin on Plasma, hyprctl on Hyprland."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Window:
    id: str
    title: str
    app_id: str
    pid: int
    focused: bool = False
    desktop: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "app_id": self.app_id,
            "pid": self.pid,
            "focused": self.focused,
            "desktop": self.desktop,
        }


def list_windows() -> list[Window]:
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        found = _hypr_list()
        if found is not None:
            return found
    found = _kwin_list()
    if found is not None:
        return found
    focused = _kwin_focused()
    return [focused] if focused else []


def focus_window(query: str, windows: list[Window] | None = None) -> Window | None:
    target = _resolve(query, windows)
    if target is None:
        return None
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        if _run(["hyprctl", "dispatch", "focuswindow", f"pid:{target.pid}"], ok=True):
            return target
        if _run(["hyprctl", "dispatch", "focuswindow", f"address:{target.id}"], ok=True):
            return target
    if _kwin_activate(target):
        return target
    return None


def close_window(query: str, windows: list[Window] | None = None) -> Window | None:
    target = _resolve(query, windows)
    if target is None:
        return None
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        if _run(["hyprctl", "dispatch", "closewindow", f"pid:{target.pid}"], ok=True):
            return target
        if _run(["hyprctl", "dispatch", "closewindow", f"address:{target.id}"], ok=True):
            return target
    if _kwin_close(target):
        return target
    return None


def windows_by_pid() -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for win in list_windows():
        if win.pid <= 0:
            continue
        out.setdefault(win.pid, []).append(win.title)
    return out


def _resolve(query: str, windows: list[Window] | None) -> Window | None:
    wins = windows if windows is not None else list_windows()
    q = query.strip()
    if not q:
        return None
    if q.isdigit():
        pid = int(q)
        for win in wins:
            if win.pid == pid:
                return win
    q_low = q.lower()
    for win in wins:
        if win.id.lower() == q_low or win.app_id.lower() == q_low:
            return win
    for win in wins:
        if q_low in win.title.lower() or q_low in win.app_id.lower():
            return win
    return None


def _hypr_list() -> list[Window] | None:
    raw = _run(["hyprctl", "-j", "clients"])
    if raw is None:
        return None
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(items, list):
        return None
    focused = _hypr_focused_addr()
    out: list[Window] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        addr = str(item.get("address") or "")
        out.append(Window(
            id=addr,
            title=str(item.get("title") or ""),
            app_id=str(item.get("class") or item.get("initialClass") or ""),
            pid=int(item.get("pid") or 0),
            focused=addr == focused or bool(item.get("focusHistoryID") == 0),
            desktop=str(item.get("workspace", {}).get("name") or ""),
        ))
    return out


def _hypr_focused_addr() -> str:
    raw = _run(["hyprctl", "-j", "activewindow"])
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    if isinstance(data, dict):
        return str(data.get("address") or "")
    return ""


def _kwin_focused() -> Window | None:
    raw = _qdbus("org.kde.KWin", "/KWin", "org.kde.KWin.queryWindowInfo")
    if not raw:
        return None
    info = _parse_qv(raw)
    if not info:
        return None
    try:
        pid = int(info.get("pid") or info.get("PID") or 0)
    except ValueError:
        pid = 0
    return Window(
        id=str(info.get("uuid") or info.get("resourceClass") or "focused"),
        title=str(info.get("caption") or info.get("title") or ""),
        app_id=str(info.get("resourceClass") or info.get("desktopFile") or ""),
        pid=pid,
        focused=True,
        desktop=str(info.get("desktop") or ""),
    )


def _kwin_list() -> list[Window] | None:
    """Run a one-shot KWin script that prints JSON to a runtime file."""
    script = r"""
const out = [];
const wins = workspace.windowList();
for (let i = 0; i < wins.length; i++) {
    const w = wins[i];
    out.push({
        id: String(w.internalId || w.frameId || i),
        title: String(w.caption || ""),
        app_id: String(w.desktopFileName || w.resourceClass || ""),
        pid: Number(w.pid || 0),
        focused: !!w.active,
        desktop: String(w.desktops && w.desktops.length ? w.desktops[0].name : "")
    });
}
const path = "__OUT__";
const cmd = `sh -c 'printf %s ${JSON.stringify(JSON.stringify(out))} > ${path}'`;
// KWin scripts cannot write files; dump via print for journal scrapers.
print("SYNAPSEOS_WINDOWS " + JSON.stringify(out));
"""
    # Prefer a helper that uses qdbus loadScript if available. Many sessions
    # will fail closed; caller falls back to focused-window-only.
    dest = Path(tempfile.gettempdir()) / f"synapseos-windows-{os.getuid()}.json"
    text = script.replace("__OUT__", str(dest))
    path = Path(tempfile.gettempdir()) / f"synapseos-kwin-{os.getuid()}.js"
    try:
        path.write_text(text, encoding="utf-8")
    except OSError:
        return None
    loaded = _qdbus(
        "org.kde.KWin", "/Scripting",
        "org.kde.kwin.Scripting.loadScript",
        str(path), "synapseos-wm-oneshot",
    )
    if loaded is None:
        return None
    script_id = loaded.strip()
    if not script_id:
        return None
    _qdbus("org.kde.KWin", f"/Scripting/Script{script_id}", "org.kde.kwin.Script.run")
    _qdbus("org.kde.KWin", f"/Scripting/Script{script_id}", "org.kde.kwin.Script.stop")
    # Best-effort: if the script managed to write dest, read it.
    if dest.is_file():
        try:
            data = json.loads(dest.read_text(encoding="utf-8"))
            dest.unlink(missing_ok=True)
            if isinstance(data, list):
                return [_win_from_dict(x) for x in data if isinstance(x, dict)]
        except (OSError, json.JSONDecodeError):
            pass
    return None


def _kwin_activate(win: Window) -> bool:
    # queryWindowInfo + activate by caption is the portable KWin 6 path.
    if win.title:
        js = (
            "const wins = workspace.windowList();"
            f"const want = {json.dumps(win.title)};"
            "for (let i = 0; i < wins.length; i++) {"
            "  if (wins[i].caption === want) { workspace.activeWindow = wins[i]; break; }"
            "}"
        )
        return _kwin_eval(js)
    return False


def _kwin_close(win: Window) -> bool:
    if win.title:
        js = (
            "const wins = workspace.windowList();"
            f"const want = {json.dumps(win.title)};"
            "for (let i = 0; i < wins.length; i++) {"
            "  if (wins[i].caption === want) { wins[i].closeWindow(); break; }"
            "}"
        )
        return _kwin_eval(js)
    return False


def _kwin_eval(js: str) -> bool:
    path = Path(tempfile.gettempdir()) / f"synapseos-kwin-eval-{os.getuid()}.js"
    try:
        path.write_text(js, encoding="utf-8")
    except OSError:
        return False
    loaded = _qdbus(
        "org.kde.KWin", "/Scripting",
        "org.kde.kwin.Scripting.loadScript",
        str(path), "synapseos-wm-eval",
    )
    if loaded is None:
        return False
    script_id = loaded.strip()
    _qdbus("org.kde.KWin", f"/Scripting/Script{script_id}", "org.kde.kwin.Script.run")
    _qdbus("org.kde.KWin", f"/Scripting/Script{script_id}", "org.kde.kwin.Script.stop")
    return True


def _win_from_dict(item: dict) -> Window:
    try:
        pid = int(item.get("pid") or 0)
    except (TypeError, ValueError):
        pid = 0
    return Window(
        id=str(item.get("id") or ""),
        title=str(item.get("title") or ""),
        app_id=str(item.get("app_id") or ""),
        pid=pid,
        focused=bool(item.get("focused")),
        desktop=str(item.get("desktop") or ""),
    )


def _qdbus(service: str, path: str, method: str, *args: str) -> str | None:
    exe = shutil.which("qdbus6") or shutil.which("qdbus")
    if not exe:
        return None
    cmd = [exe, service, path, method, *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _parse_qv(text: str) -> dict[str, str]:
    """Parse qdbus variant dump (`caption: foo`) into a dict."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        out[key.strip()] = value.strip()
    return out


def _run(cmd: list[str], ok: bool = False) -> str | None:
    if not shutil.which(cmd[0]):
        return None
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return "" if ok else None
    return proc.stdout if not ok else ""
