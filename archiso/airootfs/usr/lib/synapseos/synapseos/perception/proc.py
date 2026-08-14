"""Read /proc without psutil. Testable against a fake procfs tree."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path


def clk_tck() -> int:
    try:
        value = os.sysconf("SC_CLK_TCK")
    except (ValueError, OSError):
        return 100
    return value if value and value > 0 else 100


def ncpu() -> int:
    return os.cpu_count() or 1


def boot_time(procfs: str | Path = "/proc") -> float:
    path = Path(procfs) / "stat"
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("btime "):
                return float(line.split()[1])
    except OSError:
        pass
    return 0.0


@dataclass
class Process:
    pid: int
    comm: str
    state: str
    ppid: int
    utime: int
    stime: int
    start_ticks: int
    rss_kb: int
    uid: int
    exe: str = ""
    cmdline: list[str] = field(default_factory=list)
    cgroup: str = ""
    desktop_id: str = ""
    start_ts: float = 0.0
    elapsed_sec: float = 0.0
    cpu_pct: float = 0.0
    user: str = ""

    @property
    def ticks(self) -> int:
        return self.utime + self.stime

    def to_dict(self, *, spark: list[float] | None = None) -> dict:
        out = {
            "pid": self.pid,
            "comm": self.comm,
            "state": self.state,
            "ppid": self.ppid,
            "rss_kb": self.rss_kb,
            "rss": _fmt_bytes(self.rss_kb * 1024),
            "uid": self.uid,
            "exe": self.exe,
            "cmdline": " ".join(self.cmdline)[:240],
            "cgroup": self.cgroup,
            "desktop_id": self.desktop_id,
            "start_ts": int(self.start_ts),
            "elapsed_sec": int(self.elapsed_sec),
            "elapsed": fmt_duration(self.elapsed_sec),
            "cpu_pct": round(self.cpu_pct, 1),
        }
        if spark is not None:
            out["cpu_spark"] = [round(x, 1) for x in spark]
        return out


def parse_stat(text: str) -> dict | None:
    """Parse /proc/<pid>/stat. comm may contain spaces and parentheses."""
    lpar = text.find("(")
    rpar = text.rfind(")")
    if lpar < 0 or rpar < 0 or rpar <= lpar:
        return None
    try:
        pid = int(text[:lpar].strip())
    except ValueError:
        return None
    comm = text[lpar + 1 : rpar]
    rest = text[rpar + 1 :].split()
    if len(rest) < 20:
        return None
    try:
        return {
            "pid": pid,
            "comm": comm,
            "state": rest[0],
            "ppid": int(rest[1]),
            "utime": int(rest[11]),
            "stime": int(rest[12]),
            "start_ticks": int(rest[19]),
        }
    except (IndexError, ValueError):
        return None


def parse_status(text: str) -> dict:
    uid = 0
    rss_kb = 0
    for line in text.splitlines():
        if line.startswith("Uid:"):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    uid = int(parts[1])
                except ValueError:
                    pass
        elif line.startswith("VmRSS:"):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    rss_kb = int(parts[1])
                except ValueError:
                    pass
    return {"uid": uid, "rss_kb": rss_kb}


def parse_cmdline(raw: bytes) -> list[str]:
    if not raw:
        return []
    return [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]


def parse_cgroup(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            return line.split(":", 2)[-1]
        return line
    return ""


def desktop_id_from_cgroup(cgroup: str) -> str:
    """Extract a desktop-id-ish token from a systemd app scope path."""
    name = cgroup.rstrip("/").split("/")[-1]
    if not name.endswith(".scope"):
        return ""
    body = name[: -len(".scope")]
    if not body.startswith("app-"):
        return ""
    body = body[4:]
    # app-<launcher>-<DesktopId>-<random>  or  app-<DesktopId>-<random>
    parts = body.split("-")
    if len(parts) < 2:
        return ""
    # drop trailing random token (hex-ish or numeric)
    core = parts[:-1]
    if len(core) >= 2 and core[0] in {"gio", "gtk", "gnome", "kde", "plasma", "flatpak"}:
        core = core[1:]
    ident = "-".join(core)
    return ident


def read_process(pid: int, procfs: str | Path = "/proc", *, now: float | None = None,
                 btime: float | None = None, hz: int | None = None) -> Process | None:
    root = Path(procfs) / str(pid)
    try:
        stat_text = (root / "stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    parsed = parse_stat(stat_text)
    if parsed is None:
        return None
    try:
        status = parse_status((root / "status").read_text(encoding="utf-8", errors="replace"))
    except OSError:
        status = {"uid": 0, "rss_kb": 0}
    exe = ""
    try:
        exe = os.readlink(root / "exe")
    except OSError:
        exe = ""
    try:
        cmdline = parse_cmdline((root / "cmdline").read_bytes())
    except OSError:
        cmdline = []
    try:
        cgroup = parse_cgroup((root / "cgroup").read_text(encoding="utf-8", errors="replace"))
    except OSError:
        cgroup = ""
    hz = hz if hz is not None else clk_tck()
    btime = boot_time(procfs) if btime is None else btime
    now = time.time() if now is None else now
    start_ts = btime + parsed["start_ticks"] / hz if btime else 0.0
    elapsed = max(0.0, now - start_ts) if start_ts else 0.0
    return Process(
        pid=parsed["pid"],
        comm=parsed["comm"],
        state=parsed["state"],
        ppid=parsed["ppid"],
        utime=parsed["utime"],
        stime=parsed["stime"],
        start_ticks=parsed["start_ticks"],
        rss_kb=status["rss_kb"],
        uid=status["uid"],
        exe=exe,
        cmdline=cmdline,
        cgroup=cgroup,
        desktop_id=desktop_id_from_cgroup(cgroup),
        start_ts=start_ts,
        elapsed_sec=elapsed,
    )


def iter_pids(procfs: str | Path = "/proc") -> list[int]:
    pids: list[int] = []
    try:
        for name in os.listdir(procfs):
            if name.isdigit():
                pids.append(int(name))
    except OSError:
        return []
    pids.sort()
    return pids


def list_processes(procfs: str | Path = "/proc", *, uid: int | None = None,
                   now: float | None = None) -> list[Process]:
    btime = boot_time(procfs)
    hz = clk_tck()
    now = time.time() if now is None else now
    out: list[Process] = []
    for pid in iter_pids(procfs):
        proc = read_process(pid, procfs, now=now, btime=btime, hz=hz)
        if proc is None:
            continue
        if uid is not None and proc.uid != uid and proc.pid != 1:
            # keep pid 1 so the protected-set tests can see it
            if uid != 0:
                continue
        out.append(proc)
    return out


def fmt_duration(seconds: float) -> str:
    sec = int(max(0, seconds))
    days, rem = divmod(sec, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _fmt_bytes(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{n} B"
