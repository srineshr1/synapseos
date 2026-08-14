"""Load, memory, disk, battery, thermals."""

from __future__ import annotations

import os
from pathlib import Path


def snapshot(procfs: str | Path = "/proc", sysfs: str | Path = "/sys") -> dict:
    procfs = Path(procfs)
    sysfs = Path(sysfs)
    return {
        "load": _load(procfs),
        "memory": _mem(procfs),
        "disk": _disk("/"),
        "battery": _battery(sysfs),
        "thermals": _thermals(sysfs),
        "hostname": _hostname(procfs),
        "user": _user(),
    }


def _load(procfs: Path) -> dict:
    try:
        parts = (procfs / "loadavg").read_text(encoding="utf-8").split()
        return {
            "m1": float(parts[0]),
            "m5": float(parts[1]),
            "m15": float(parts[2]),
        }
    except (OSError, IndexError, ValueError):
        return {"m1": 0.0, "m5": 0.0, "m15": 0.0}


def _mem(procfs: Path) -> dict:
    values: dict[str, int] = {}
    try:
        for line in (procfs / "meminfo").read_text(encoding="utf-8").splitlines():
            if ":" not in line:
                continue
            key, rest = line.split(":", 1)
            num = rest.strip().split()[0]
            try:
                values[key] = int(num)
            except ValueError:
                continue
    except OSError:
        return {"total_kb": 0, "available_kb": 0, "used_pct": 0.0}
    total = values.get("MemTotal", 0)
    avail = values.get("MemAvailable", values.get("MemFree", 0))
    used_pct = 0.0 if not total else round(100.0 * (total - avail) / total, 1)
    return {"total_kb": total, "available_kb": avail, "used_pct": used_pct}


def _disk(path: str) -> dict:
    try:
        st = os.statvfs(path)
    except OSError:
        return {"path": path, "total_kb": 0, "free_kb": 0, "used_pct": 0.0}
    total = (st.f_frsize * st.f_blocks) // 1024
    free = (st.f_frsize * st.f_bavail) // 1024
    used_pct = 0.0 if not total else round(100.0 * (total - free) / total, 1)
    return {"path": path, "total_kb": total, "free_kb": free, "used_pct": used_pct}


def _battery(sysfs: Path) -> dict | None:
    root = sysfs / "class/power_supply"
    if not root.is_dir():
        return None
    try:
        names = sorted(root.iterdir())
    except OSError:
        return None
    for entry in names:
        try:
            typ = (entry / "type").read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if typ != "Battery":
            continue
        cap = _read_int(entry / "capacity")
        status = _read_text(entry / "status") or "Unknown"
        return {"name": entry.name, "percent": cap, "status": status}
    return None


def _thermals(sysfs: Path) -> list[dict]:
    root = sysfs / "class/thermal"
    if not root.is_dir():
        return []
    out: list[dict] = []
    try:
        names = sorted(root.iterdir())
    except OSError:
        return []
    for entry in names:
        if not entry.name.startswith("thermal_zone"):
            continue
        milli = _read_int(entry / "temp")
        if milli is None:
            continue
        out.append({
            "zone": entry.name,
            "type": _read_text(entry / "type") or "",
            "celsius": round(milli / 1000.0, 1),
        })
        if len(out) >= 6:
            break
    return out


def _hostname(procfs: Path) -> str:
    try:
        return (procfs / "sys/kernel/hostname").read_text(encoding="utf-8").strip()
    except OSError:
        return os.uname().nodename


def _user() -> str:
    return os.environ.get("USER") or os.environ.get("LOGNAME") or str(os.getuid())


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def _read_int(path: Path) -> int | None:
    text = _read_text(path)
    if text is None:
        return None
    try:
        return int(text.split()[0])
    except (ValueError, IndexError):
        return None
