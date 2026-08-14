"""XDG locations for the SynapseOS core daemon and its clients."""

from __future__ import annotations

import os
from pathlib import Path


APP = "synapseos"


def _xdg(env: str, default: str) -> Path:
    raw = os.environ.get(env)
    return Path(raw) if raw else Path.home() / default


def runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR")
    root = Path(base) / APP if base else Path(f"/tmp/{APP}-{os.getuid()}")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root


def config_dir() -> Path:
    path = _xdg("XDG_CONFIG_HOME", ".config") / APP
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    path = _xdg("XDG_DATA_HOME", ".local/share") / APP
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    path = _xdg("XDG_CACHE_HOME", ".cache") / APP
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def config_file() -> Path:
    return config_dir() / "config.toml"


def grants_file() -> Path:
    return config_dir() / "grants.json"


def audit_file() -> Path:
    return data_dir() / "audit.jsonl"


def perception_db() -> Path:
    return data_dir() / "perception.sqlite"


def socket_path() -> Path:
    return runtime_dir() / "mcp.sock"


def overlay_pidfile() -> Path:
    return runtime_dir() / "overlay.pid"


def package_dir() -> Path:
    return Path(__file__).resolve().parent
