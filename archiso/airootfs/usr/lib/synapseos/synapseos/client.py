"""JSON-RPC client for the synapse-core unix socket."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from .mcp import error as _error  # noqa: F401
from .paths import socket_path


class ClientError(Exception):
    pass


class CoreClient:
    def __init__(self, path: Path | None = None, timeout: float = 120.0):
        self.path = path or socket_path()
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._fp = None
        self._next_id = 1

    def connect(self, start: bool = True) -> None:
        if self._sock is not None:
            return
        if start:
            _ensure_core(self.path)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect(str(self.path))
        except OSError as exc:
            sock.close()
            raise ClientError(f"cannot connect to {self.path}: {exc}") from exc
        self._sock = sock
        self._fp = sock.makefile("rwb")

    def close(self) -> None:
        if self._fp is not None:
            try:
                self._fp.close()
            except OSError:
                pass
            self._fp = None
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def __enter__(self) -> "CoreClient":
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def call(self, method: str, params: dict[str, Any] | None = None,
             on_event: Callable[[dict[str, Any]], None] | None = None) -> Any:
        self.connect()
        assert self._fp is not None
        req_id = self._next_id
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
        blob = json.dumps(payload).encode("utf-8") + b"\n"
        self._fp.write(blob)
        self._fp.flush()
        deadline = time.time() + self.timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise ClientError(f"timeout waiting for {method}")
            if self._sock is not None:
                self._sock.settimeout(remaining)
            line = self._fp.readline()
            if not line:
                raise ClientError("core closed the connection")
            try:
                msg = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ClientError(f"bad response: {exc}") from exc
            if msg.get("method") == "synapse/event":
                if on_event:
                    on_event(msg.get("params") or {})
                continue
            if msg.get("id") != req_id:
                continue
            if "error" in msg:
                err = msg["error"]
                raise ClientError(err.get("message") if isinstance(err, dict) else str(err))
            return msg.get("result")


def _ensure_core(path: Path) -> None:
    if _socket_alive(path):
        return
    exe = _core_executable()
    if exe is None:
        raise ClientError(
            f"synapse-core is not running and no synapseos-core binary was found "
            f"(socket {path})"
        )
    subprocess.Popen(
        [exe],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=os.environ.copy(),
    )
    for _ in range(40):
        if _socket_alive(path):
            return
        time.sleep(0.05)
    raise ClientError("started synapse-core but the socket never appeared")


def _socket_alive(path: Path) -> bool:
    if not path.exists():
        return False
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(0.4)
    try:
        sock.connect(str(path))
    except OSError:
        return False
    finally:
        sock.close()
    return True


def _core_executable() -> str | None:
    here = Path(__file__).resolve()
    # .../usr/lib/synapseos/synapseos/client.py → .../usr/bin/synapseos-core
    cand = here.parents[2] / "bin" / "synapseos-core"
    if cand.is_file() and os.access(cand, os.X_OK):
        return str(cand)
    from shutil import which
    return which("synapseos-core")
