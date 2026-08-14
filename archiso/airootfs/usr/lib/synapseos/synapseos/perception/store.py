"""In-memory + sqlite sampler: CPU deltas, sparklines, first-seen keys."""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

from .apps import DesktopApp, index_by_hint, list_desktop_apps
from .proc import Process, fmt_duration, list_processes, ncpu


SPARK_KEEP = 180          # 30 min at 10s
SPARK_EVERY = 10.0
CPU_FLOOR = 0.0


@dataclass
class AppGroup:
    key: str
    name: str
    desktop_id: str
    pids: list[int] = field(default_factory=list)
    comms: list[str] = field(default_factory=list)
    rss_kb: int = 0
    cpu_pct: float = 0.0
    start_ts: float = 0.0
    elapsed_sec: float = 0.0
    session_elapsed_sec: float = 0.0
    windows: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "desktop_id": self.desktop_id,
            "pids": self.pids[:12],
            "pid_count": len(self.pids),
            "comms": self.comms,
            "rss_kb": self.rss_kb,
            "rss": _fmt_rss(self.rss_kb),
            "cpu_pct": round(self.cpu_pct, 1),
            "start_ts": int(self.start_ts),
            "elapsed_sec": int(self.elapsed_sec),
            "elapsed": fmt_duration(self.elapsed_sec),
            "session_elapsed_sec": int(self.session_elapsed_sec),
            "session_elapsed": fmt_duration(self.session_elapsed_sec),
            "windows": self.windows,
        }


def _fmt_rss(kb: int) -> str:
    if kb >= 1024 * 1024:
        return f" {kb / 1024 / 1024:.1f} GB".strip()
    if kb >= 1024:
        return f"{kb / 1024:.1f} MB"
    return f"{kb} KB"


class Sampler:
    def __init__(self, procfs: str | Path = "/proc", db_path: Path | None = None,
                 uid: int | None = None):
        self.procfs = Path(procfs)
        self.uid = os.getuid() if uid is None else uid
        self.db_path = db_path
        self._lock = threading.Lock()
        self._prev: dict[int, tuple[float, int]] = {}
        self._cpu: dict[int, float] = {}
        self._spark: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=SPARK_KEEP))
        self._last_spark_ts = 0.0
        self._first_seen: dict[str, float] = {}
        self._procs: list[Process] = []
        self._apps: list[DesktopApp] = []
        self._hints: dict[str, DesktopApp] = {}
        self._last_tick = 0.0
        if db_path is not None:
            self._init_db()
            self._load_first_seen()

    def refresh_apps(self) -> None:
        self._apps = list_desktop_apps()
        self._hints = index_by_hint(self._apps)

    def tick(self, now: float | None = None) -> list[Process]:
        now = time.time() if now is None else now
        if not self._hints:
            self.refresh_apps()
        procs = list_processes(self.procfs, uid=self.uid, now=now)
        cpus = ncpu()
        with self._lock:
            live = {p.pid for p in procs}
            for pid in list(self._prev):
                if pid not in live:
                    self._prev.pop(pid, None)
                    self._cpu.pop(pid, None)
            for proc in procs:
                self._attribute(proc)
                prev = self._prev.get(proc.pid)
                if prev is not None:
                    dt = now - prev[0]
                    d_ticks = proc.ticks - prev[1]
                    if dt > 0 and d_ticks >= 0:
                        # ticks are summed across CPUs; divide by ncpu for "of the machine"
                        pct = (d_ticks / clk_safe() / dt) * 100.0
                        # report per-core style (top's default) — do not divide by ncpu
                        # so a 2-thread hog can read ~200%. Cap at 100*ncpu.
                        proc.cpu_pct = max(CPU_FLOOR, min(100.0 * cpus, pct))
                    else:
                        proc.cpu_pct = self._cpu.get(proc.pid, 0.0)
                else:
                    proc.cpu_pct = 0.0
                self._prev[proc.pid] = (now, proc.ticks)
                self._cpu[proc.pid] = proc.cpu_pct
                key = _group_key(proc)
                if key not in self._first_seen:
                    self._first_seen[key] = proc.start_ts or now
                    self._persist_first_seen(key, self._first_seen[key])
            if now - self._last_spark_ts >= SPARK_EVERY:
                buckets: dict[str, float] = defaultdict(float)
                for proc in procs:
                    buckets[_group_key(proc)] += proc.cpu_pct
                for key, cpu in buckets.items():
                    self._spark[key].append(cpu)
                self._last_spark_ts = now
                self._persist_samples(now, buckets, procs)
            self._procs = procs
            self._last_tick = now
        return procs

    def processes(self) -> list[Process]:
        with self._lock:
            return list(self._procs)

    def process(self, pid: int) -> Process | None:
        with self._lock:
            for proc in self._procs:
                if proc.pid == pid:
                    return proc
        return None

    def spark(self, key: str) -> list[float]:
        with self._lock:
            return list(self._spark.get(key, ()))

    def first_seen(self, key: str) -> float | None:
        with self._lock:
            return self._first_seen.get(key)

    def grouped(self, windows_by_pid: dict[int, list[str]] | None = None) -> list[AppGroup]:
        windows_by_pid = windows_by_pid or {}
        with self._lock:
            procs = list(self._procs)
            first = dict(self._first_seen)
            now = self._last_tick or time.time()
        groups: dict[str, AppGroup] = {}
        for proc in procs:
            if _skip_from_apps(proc):
                continue
            key = _group_key(proc)
            grp = groups.get(key)
            if grp is None:
                name = proc.comm
                desktop_id = proc.desktop_id
                hint = (
                    self._hints.get(proc.comm.lower())
                    or self._hints.get(key.lower())
                    or (self._hints.get(proc.desktop_id.lower()) if proc.desktop_id else None)
                )
                if hint and _exe_matches_app(proc, hint):
                    name = hint.name
                    desktop_id = hint.id
                elif proc.cmdline:
                    name = Path(proc.cmdline[0]).name or proc.comm
                grp = AppGroup(
                    key=key,
                    name=name,
                    desktop_id=desktop_id,
                    start_ts=proc.start_ts,
                )
                groups[key] = grp
            grp.pids.append(proc.pid)
            if proc.comm not in grp.comms:
                grp.comms.append(proc.comm)
            grp.rss_kb += proc.rss_kb
            grp.cpu_pct += proc.cpu_pct
            if proc.start_ts and (not grp.start_ts or proc.start_ts < grp.start_ts):
                grp.start_ts = proc.start_ts
            titles = windows_by_pid.get(proc.pid) or []
            for title in titles:
                if title and title not in grp.windows:
                    grp.windows.append(title)
        for grp in groups.values():
            grp.elapsed_sec = max(0.0, now - grp.start_ts) if grp.start_ts else 0.0
            seen = first.get(grp.key, grp.start_ts or now)
            grp.session_elapsed_sec = max(grp.elapsed_sec, now - seen if seen else 0.0)
        rows = list(groups.values())
        rows.sort(key=lambda g: (-g.cpu_pct, -g.rss_kb, g.name.lower()))
        return rows

    def _attribute(self, proc: Process) -> None:
        exe_base = Path(proc.exe).name.lower() if proc.exe else ""
        for hint in (proc.comm.lower(), exe_base):
            if hint and hint in self._hints:
                proc.desktop_id = self._hints[hint].id
                return
        # Cgroup is inherited by children of a terminal, so only keep it
        # when it already names a known desktop id AND matches this binary.
        if proc.desktop_id:
            app = self._hints.get(proc.desktop_id.lower())
            if app is not None and _exe_matches_app(proc, app):
                proc.desktop_id = app.id
                return
            proc.desktop_id = ""

    def _init_db(self) -> None:
        assert self.db_path is not None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS first_seen (key TEXT PRIMARY KEY, ts REAL NOT NULL)"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS samples "
                "(ts REAL NOT NULL, key TEXT NOT NULL, cpu REAL, rss INTEGER)"
            )
            con.execute("CREATE INDEX IF NOT EXISTS samples_ts ON samples(ts)")

    def _load_first_seen(self) -> None:
        if self.db_path is None:
            return
        try:
            with sqlite3.connect(self.db_path) as con:
                for key, ts in con.execute("SELECT key, ts FROM first_seen"):
                    self._first_seen[str(key)] = float(ts)
        except sqlite3.Error:
            pass

    def _persist_first_seen(self, key: str, ts: float) -> None:
        if self.db_path is None:
            return
        try:
            with sqlite3.connect(self.db_path) as con:
                con.execute(
                    "INSERT OR IGNORE INTO first_seen(key, ts) VALUES (?, ?)",
                    (key, ts),
                )
        except sqlite3.Error:
            pass

    def _persist_samples(self, now: float, buckets: dict[str, float],
                         procs: list[Process]) -> None:
        if self.db_path is None:
            return
        rss: dict[str, int] = defaultdict(int)
        for proc in procs:
            rss[_group_key(proc)] += proc.rss_kb
        rows = [(now, key, cpu, rss.get(key, 0)) for key, cpu in buckets.items()]
        try:
            with sqlite3.connect(self.db_path) as con:
                con.executemany(
                    "INSERT INTO samples(ts, key, cpu, rss) VALUES (?, ?, ?, ?)",
                    rows,
                )
                con.execute("DELETE FROM samples WHERE ts < ?", (now - 1800.0,))
        except sqlite3.Error:
            pass


_INTERPRETERS = {
    "python", "python3", "python3.14", "node", "nodejs", "ruby", "perl",
    "bash", "zsh", "sh", "dash", "fish",
}


def _group_key(proc: Process) -> str:
    """Identity of the *binary*, not the inherited systemd app scope."""
    if proc.exe:
        base = Path(proc.exe).name
        if base in _INTERPRETERS and proc.cmdline:
            args = proc.cmdline[1:]
            i = 0
            while i < len(args):
                arg = args[i]
                if arg in {"-c", "-m", "-e"}:
                    i += 2
                    continue
                if arg.startswith("-"):
                    i += 1
                    continue
                name = Path(arg).name
                if name:
                    return f"{base}:{name}"
                i += 1
        return base
    if proc.desktop_id:
        return proc.desktop_id
    return proc.comm


def _exe_matches_app(proc: Process, app) -> bool:
    exe = Path(proc.exe).name.lower() if proc.exe else ""
    comm = proc.comm.lower()
    want = {
        app.id.lower(),
        app.wmclass.lower() if app.wmclass else "",
        Path(app.exec.split()[0]).name.lower() if app.exec else "",
        app.try_exec.lower() if app.try_exec else "",
    }
    want.discard("")
    return exe in want or comm in want or (proc.desktop_id or "").lower() in want


def _skip_from_apps(proc: Process) -> bool:
    if proc.pid == 1:
        return True
    # kernel threads have no cmdline and no exe
    if not proc.cmdline and not proc.exe:
        return True
    return False


def clk_safe() -> float:
    from .proc import clk_tck
    return float(clk_tck())
