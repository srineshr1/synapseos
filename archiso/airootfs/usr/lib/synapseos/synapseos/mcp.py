"""JSON-RPC 2.0 MCP: newline-delimited or LSP Content-Length framing."""

from __future__ import annotations

import json
from typing import Any, BinaryIO, Callable, Iterable

PROTOCOL = "2024-11-05"
SERVER_NAME = "synapseos"
SERVER_VERSION = "0.1.0"

Handler = Callable[[str, dict[str, Any], Any], Any]


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def read_message(fp: BinaryIO) -> dict[str, Any] | None:
    header = fp.readline()
    if not header:
        return None
    if header.lower().startswith(b"content-length:"):
        length = _content_length(header)
        while True:
            line = fp.readline()
            if not line:
                return None
            if line.lower().startswith(b"content-length:"):
                length = _content_length(line)
                continue
            if line in (b"\r\n", b"\n"):
                break
        raw = fp.read(length)
        if len(raw) < length:
            return None
        return _loads(raw)
    # newline-delimited JSON (and tolerate a BOM / whitespace)
    raw = header.strip()
    if not raw:
        return read_message(fp)
    return _loads(raw)


def write_message(fp: BinaryIO, payload: dict[str, Any], *, framed: bool) -> None:
    blob = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    if framed:
        fp.write(f"Content-Length: {len(blob)}\r\n\r\n".encode("ascii"))
        fp.write(blob)
    else:
        fp.write(blob + b"\n")
    fp.flush()


def detect_framing(first_line: bytes) -> bool:
    return first_line.lower().startswith(b"content-length:")


def result(id_: Any, value: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "result": value}


def error(id_: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": id_, "error": err}


def notify(method: str, params: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "method": method, "params": params}


def initialize_result() -> dict[str, Any]:
    return {
        "protocolVersion": PROTOCOL,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
    }


def tool_spec(name: str, description: str, properties: dict[str, Any] | None = None,
              required: Iterable[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties or {}}
    req = list(required or [])
    if req:
        schema["required"] = req
    return {"name": name, "description": description, "inputSchema": schema}


def _content_length(line: bytes) -> int:
    try:
        return int(line.split(b":", 1)[1].strip())
    except (IndexError, ValueError) as exc:
        raise RpcError(-32700, "invalid Content-Length") from exc


def _loads(raw: bytes) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RpcError(-32700, f"parse error: {exc}") from exc
    if not isinstance(data, dict):
        raise RpcError(-32600, "request must be an object")
    return data
