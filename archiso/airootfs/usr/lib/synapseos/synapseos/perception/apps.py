"""Installed .desktop applications and fuzzy resolution."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


DESKTOP_DIRS_DEFAULT = (
    "/usr/share/applications",
    "/usr/local/share/applications",
    "/var/lib/flatpak/exports/share/applications",
)


@dataclass
class DesktopApp:
    id: str
    name: str
    exec: str
    try_exec: str = ""
    icon: str = ""
    wmclass: str = ""
    nodisplay: bool = False
    hidden: bool = False
    path: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "exec": self.exec,
            "icon": self.icon,
            "wmclass": self.wmclass,
        }


def xdg_data_dirs() -> list[Path]:
    dirs: list[Path] = []
    home = os.environ.get("XDG_DATA_HOME")
    dirs.append(Path(home) if home else Path.home() / ".local/share")
    extra = os.environ.get("XDG_DATA_DIRS", "")
    if extra:
        dirs.extend(Path(p) for p in extra.split(":") if p)
    else:
        dirs.extend(Path(p) for p in DESKTOP_DIRS_DEFAULT)
    # always include the stock locations
    for stock in DESKTOP_DIRS_DEFAULT:
        path = Path(stock)
        if path not in dirs:
            dirs.append(path)
    return dirs


def _unescape_exec(value: str) -> str:
    # strip field codes: %f %F %u %U %i %c %k %%
    cleaned = re.sub(r"%(?:[fFuUdDnNickvm]|%)", "", value)
    return " ".join(cleaned.split())


def parse_desktop_file(path: Path) -> DesktopApp | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    section = ""
    fields: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section != "Desktop Entry" or "=" not in line:
            continue
        key, value = line.split("=", 1)
        fields.setdefault(key.strip(), value.strip())
    if fields.get("Type", "Application") != "Application":
        return None
    name = (
        fields.get("Name")
        or fields.get("Name[en_US]")
        or fields.get("Name[en]")
        or path.stem
    )
    exe = _unescape_exec(fields.get("Exec", ""))
    if not exe and not fields.get("TryExec"):
        return None
    desktop_id = path.name
    if desktop_id.endswith(".desktop"):
        desktop_id = desktop_id[: -len(".desktop")]
    return DesktopApp(
        id=desktop_id,
        name=name,
        exec=exe,
        try_exec=fields.get("TryExec", ""),
        icon=fields.get("Icon", ""),
        wmclass=fields.get("StartupWMClass", ""),
        nodisplay=fields.get("NoDisplay", "").lower() in {"true", "1"},
        hidden=fields.get("Hidden", "").lower() in {"true", "1"},
        path=str(path),
    )


def list_desktop_apps(extra_dirs: list[Path] | None = None) -> list[DesktopApp]:
    seen: set[str] = set()
    apps: list[DesktopApp] = []
    dirs = extra_dirs if extra_dirs is not None else [d / "applications" for d in xdg_data_dirs()]
    for directory in dirs:
        if not directory.is_dir():
            continue
        try:
            names = sorted(directory.iterdir())
        except OSError:
            continue
        for path in names:
            if path.suffix != ".desktop" or path.name in seen:
                continue
            app = parse_desktop_file(path)
            if app is None:
                continue
            seen.add(path.name)
            apps.append(app)
    apps.sort(key=lambda a: a.name.lower())
    return apps


def visible_apps(apps: list[DesktopApp] | None = None) -> list[DesktopApp]:
    apps = apps if apps is not None else list_desktop_apps()
    return [a for a in apps if not a.hidden and not a.nodisplay]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def match_app(query: str, apps: list[DesktopApp] | None = None) -> DesktopApp | None:
    """Resolve a user/model query to one installed application."""
    apps = apps if apps is not None else list_desktop_apps()
    q = query.strip()
    if not q:
        return None
    q_low = q.lower()
    q_id = q_low.removesuffix(".desktop")
    q_n = _norm(q)

    for app in apps:
        if app.id.lower() == q_id or app.id.lower() == q_low:
            return app
    for app in apps:
        if app.name.lower() == q_low:
            return app
    for app in apps:
        if app.wmclass and app.wmclass.lower() == q_low:
            return app
    for app in apps:
        base = Path(app.exec.split()[0]).name.lower() if app.exec else ""
        if base and base == q_low:
            return app

    scored: list[tuple[int, DesktopApp]] = []
    for app in apps:
        score = 0
        name_l = app.name.lower()
        id_l = app.id.lower()
        if q_low in name_l:
            score += 40 if name_l.startswith(q_low) else 25
        if q_low in id_l:
            score += 35 if id_l.startswith(q_low) else 20
        if q_n and q_n in _norm(app.name):
            score += 10
        if app.wmclass and q_low in app.wmclass.lower():
            score += 15
        if score:
            scored.append((score, app))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], item[1].name.lower()))
    return scored[0][1]


def index_by_hint(apps: list[DesktopApp]) -> dict[str, DesktopApp]:
    """Maps lowercase id / wmclass / exec basename / name to an app."""
    out: dict[str, DesktopApp] = {}
    for app in apps:
        for key in filter(None, (
            app.id.lower(),
            app.name.lower(),
            app.wmclass.lower() if app.wmclass else "",
            Path(app.exec.split()[0]).name.lower() if app.exec else "",
            app.try_exec.lower() if app.try_exec else "",
        )):
            out.setdefault(key, app)
    return out
