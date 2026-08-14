"""Append-only JSONL audit log."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .paths import audit_file


def record(event: str, **fields: Any) -> None:
    payload = {"ts": round(time.time(), 3), "event": event, **fields}
    path = audit_file()
    line = json.dumps(payload, ensure_ascii=False, default=str) + "\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def tail(limit: int = 50, path: Path | None = None) -> list[dict[str, Any]]:
    target = path or audit_file()
    if not target.is_file():
        return []
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-max(1, limit) :]:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out
