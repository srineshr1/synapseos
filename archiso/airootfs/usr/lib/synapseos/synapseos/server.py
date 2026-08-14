"""synapse-core: sampler + MCP unix socket + stdio adapter."""

from __future__ import annotations

import argparse
import os
import signal
import socket
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, BinaryIO

from . import __version__, audit, config as config_mod
from .config import Config
from .mcp import (
    RpcError,
    error,
    initialize_result,
    notify,
    read_message,
    result,
    write_message,
)
from .paths import perception_db, socket_path
from .perception.apps import list_desktop_apps
from .perception.store import Sampler
from .planner import Planner, PlannerError, transcribe
from .policy import Policy
from .tools import ToolBroker

SAMPLE_EVERY = 2.0


class Core:
    def __init__(self, cfg: Config, procfs: str | Path = "/proc",
                 db_path: Path | None = None):
        self.cfg = cfg
        self.policy = Policy(cfg)
        self.sampler = Sampler(procfs=procfs, db_path=db_path)
        self.tools = ToolBroker(self)
        self.planner = Planner(cfg, self.tools)
        self._apps = list_desktop_apps()
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def desktop_apps(self):
        return self._apps

    def set_mode(self, mode: str) -> None:
        self.policy.mode = mode
        config_mod.save(self.cfg)
        audit.record("mode", mode=mode)

    def set_paused(self, paused: bool) -> None:
        self.policy.paused = paused
        config_mod.save(self.cfg)
        audit.record("pause" if paused else "resume")

    def set_key(self, key: str) -> None:
        self.cfg.model.api_key = key.strip()
        config_mod.save(self.cfg)
        audit.record("key", status="set")

    def snapshot_text(self, limit: int = 12) -> str:
        from .perception.proc import fmt_duration
        groups = self.sampler.grouped()
        if not groups:
            return "(no user apps in the current snapshot)"
        lines = []
        for grp in groups[:limit]:
            extra = f", windows: {', '.join(grp.windows[:2])}" if grp.windows else ""
            pids = ",".join(str(p) for p in grp.pids[:4])
            if len(grp.pids) > 4:
                pids += f"+{len(grp.pids) - 4}"
            lines.append(
                f"- {grp.name} [{grp.desktop_id or grp.key}] "
                f"pids={pids} cpu={grp.cpu_pct:.0f}% rss={grp.rss_kb}KB "
                f"up={fmt_duration(grp.elapsed_sec)} "
                f"session={fmt_duration(grp.session_elapsed_sec)}{extra}"
            )
        return "\n".join(lines)

    def handle(self, req: dict[str, Any], emit) -> dict[str, Any] | None:
        method = req.get("method")
        id_ = req.get("id")
        params = req.get("params") if isinstance(req.get("params"), dict) else {}
        if not method:
            if id_ is None:
                return None
            return error(id_, -32600, "missing method")
        try:
            if method == "initialize":
                return result(id_, initialize_result())
            if method in {"notifications/initialized", "initialized", "ping"}:
                return None if id_ is None else result(id_, {})
            if method == "tools/list":
                return result(id_, {"tools": self.tools.specs})
            if method == "tools/call":
                name = str(params.get("name") or "")
                args = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
                payload = self.tools.call(name, args)
                text = _tool_text(payload)
                return result(id_, {
                    "content": [{"type": "text", "text": text}],
                    "isError": not bool(payload.get("ok")),
                    "structuredContent": payload,
                })
            if method in {"synapse/status", "status"}:
                return result(id_, self._status())
            if method in {"synapse/ask", "ask"}:
                return result(id_, self._ask(str(params.get("text") or ""), emit))
            if method in {"synapse/consent", "consent"}:
                return result(id_, self._consent(params, emit))
            if method in {"synapse/set_mode", "set_mode"}:
                mode = str(params.get("mode") or "")
                if mode in {"observe", "assist", "act"}:
                    if mode == "act":
                        # still a mutating policy change; allow from the local socket
                        self.set_mode(mode)
                    else:
                        self.set_mode(mode)
                    return result(id_, self._status())
                return error(id_, -32602, "mode must be observe, assist or act")
            if method in {"synapse/set_paused", "set_paused", "pause", "resume"}:
                if method == "pause":
                    paused = True
                elif method == "resume":
                    paused = False
                else:
                    paused = bool(params.get("paused"))
                self.set_paused(paused)
                return result(id_, self._status())
            if method in {"synapse/set_key", "set_key"}:
                key = str(params.get("key") or "").strip()
                if not key:
                    return error(id_, -32602, "key is required")
                self.set_key(key)
                return result(id_, {"ok": True, "has_key": True})
            if method in {"synapse/transcribe", "transcribe"}:
                return result(id_, self._transcribe(params))
            if method in {"synapse/audit", "audit"}:
                limit = int(params.get("limit") or 50)
                return result(id_, {"ok": True, "entries": audit.tail(limit)})
            if method in {"synapse/snapshot", "snapshot"}:
                return result(id_, {"ok": True, "text": self.snapshot_text()})
            return error(id_, -32601, f"unknown method {method}")
        except RpcError as exc:
            return error(id_, exc.code, exc.message, exc.data)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return error(id_, -32603, f"{type(exc).__name__}: {exc}")

    def _status(self) -> dict[str, Any]:
        st = self.policy.status()
        st["ok"] = True
        st["version"] = __version__
        st["has_key"] = self.cfg.has_key()
        st["model"] = self.cfg.model.model
        st["apps"] = len(self.sampler.grouped())
        st["pid"] = os.getpid()
        return st

    def _ask(self, text: str, emit) -> dict[str, Any]:
        if not text.strip():
            return {"status": "error", "error": "empty request"}
        audit.record("ask", text=text[:240])

        def on_event(kind: str, payload: dict[str, Any]) -> None:
            emit(notify("synapse/event", {"type": kind, **payload}))

        try:
            snap = self.snapshot_text()
        except Exception as exc:  # noqa: BLE001
            snap = f"(snapshot failed: {exc})"
        return self.planner.ask(text, snapshot=snap, on_event=on_event)

    def _consent(self, params: dict[str, Any], emit) -> dict[str, Any]:
        consent_id = str(params.get("id") or params.get("consent_id") or "")
        decision = str(params.get("decision") or params.get("allow") or "").lower()
        allow = decision in {"allow", "yes", "true", "1"} or params.get("allow") is True
        remember = bool(params.get("remember"))
        pending = self.policy.take(consent_id)
        if pending is None:
            return {"status": "error", "error": "unknown or expired consent id"}
        if not allow:
            audit.record("consent", status="denied", id=consent_id, tool=pending.tool)
            return {"status": "denied", "summary": pending.summary}
        if remember:
            self.policy.remember(pending.grant_key)
        args = dict(pending.arguments)
        args["_confirmed"] = True
        payload = self.tools.call(pending.tool, args, skip_consent=True)
        audit.record("consent", status="allowed", id=consent_id, tool=pending.tool)
        # Continue the original utterance if the client sent it back.
        follow = str(params.get("continue_text") or "").strip()
        if follow and payload.get("ok"):
            def on_event(kind: str, data: dict[str, Any]) -> None:
                emit(notify("synapse/event", {"type": kind, **data}))
            more = self.planner.ask(
                follow + "\n\n(The user allowed: " + pending.summary + ")",
                snapshot=self.snapshot_text(),
                on_event=on_event,
            )
            more["executed"] = payload
            more["summary"] = pending.summary
            return more
        return {"status": "done", "executed": payload, "summary": pending.summary}

    def _transcribe(self, params: dict[str, Any]) -> dict[str, Any]:
        import base64
        b64 = params.get("audio_b64") or params.get("audio")
        if not b64:
            return {"ok": False, "error": "audio_b64 is required"}
        try:
            audio = base64.b64decode(b64)
        except (TypeError, ValueError) as exc:
            return {"ok": False, "error": f"bad audio: {exc}"}
        try:
            text = transcribe(self.cfg, audio)
        except PlannerError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "text": text}

    def sampler_loop(self) -> None:
        self.sampler.refresh_apps()
        self.sampler.tick()
        while not self._stop.wait(SAMPLE_EVERY):
            try:
                self.sampler.tick()
            except Exception:  # noqa: BLE001
                traceback.print_exc()

    def stop(self) -> None:
        self._stop.set()


def serve_unix(core: Core, path: Path) -> socket.socket:
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(path))
    os.chmod(path, 0o600)
    sock.listen(16)
    sock.settimeout(0.5)
    return sock


def accept_loop(core: Core, sock: socket.socket) -> None:
    while not core._stop.is_set():
        try:
            conn, _ = sock.accept()
        except socket.timeout:
            continue
        except OSError:
            if core._stop.is_set():
                return
            raise
        thread = threading.Thread(target=client_loop, args=(core, conn), daemon=True)
        thread.start()


def client_loop(core: Core, conn: socket.socket, *, framed: bool | None = None) -> None:
    conn.settimeout(None)
    fp = conn.makefile("rwb")
    use_framed = bool(framed)
    try:
        while not core._stop.is_set():
            try:
                peek = conn.recv(64, socket.MSG_PEEK)
            except OSError:
                return
            if not peek:
                return
            if framed is None:
                use_framed = peek.lower().startswith(b"content-length:")
                framed = use_framed
            try:
                req = read_message(fp)
            except RpcError as exc:
                write_message(fp, error(None, exc.code, exc.message), framed=use_framed)
                continue
            if req is None:
                return

            pending: list[dict[str, Any]] = []

            def emit(msg: dict[str, Any]) -> None:
                pending.append(msg)

            reply = core.handle(req, emit)
            for msg in pending:
                write_message(fp, msg, framed=use_framed)
            if reply is not None:
                write_message(fp, reply, framed=use_framed)
    finally:
        try:
            fp.close()
        except OSError:
            pass
        try:
            conn.close()
        except OSError:
            pass


def stdio_loop(core: Core) -> int:
    stdin: BinaryIO = sys.stdin.buffer
    stdout: BinaryIO = sys.stdout.buffer
    framed = True  # MCP stdio clients expect Content-Length
    while not core._stop.is_set():
        try:
            req = read_message(stdin)
        except RpcError as exc:
            write_message(stdout, error(None, exc.code, exc.message), framed=framed)
            continue
        if req is None:
            return 0
        pending: list[dict[str, Any]] = []

        def emit(msg: dict[str, Any]) -> None:
            pending.append(msg)

        reply = core.handle(req, emit)
        for msg in pending:
            write_message(stdout, msg, framed=framed)
        if reply is not None:
            write_message(stdout, reply, framed=framed)
    return 0


def stdio_proxy() -> int:
    """Speak MCP stdio; forward to the user-session core so policy is shared."""
    from .client import ClientError, CoreClient

    cli = CoreClient()
    try:
        cli.connect(start=True)
    except ClientError as exc:
        print(f"synapseos-mcp: {exc}", file=sys.stderr)
        return 1
    stdin: BinaryIO = sys.stdin.buffer
    stdout: BinaryIO = sys.stdout.buffer
    while True:
        try:
            req = read_message(stdin)
        except RpcError as exc:
            write_message(stdout, error(None, exc.code, exc.message), framed=True)
            continue
        if req is None:
            return 0
        method = req.get("method")
        id_ = req.get("id")
        if not method or method in {"notifications/initialized", "initialized"}:
            continue
        params = req.get("params")
        if params is not None and not isinstance(params, dict):
            params = {}
        try:
            value = cli.call(str(method), params or {})
        except ClientError as exc:
            if id_ is not None:
                write_message(stdout, error(id_, -32603, str(exc)), framed=True)
            continue
        if id_ is not None:
            write_message(stdout, result(id_, value), framed=True)


def _tool_text(payload: dict[str, Any]) -> str:
    import json
    return json.dumps(payload, ensure_ascii=False, default=str, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="synapseos-core")
    parser.add_argument("--stdio", action="store_true",
                        help="MCP over stdin/stdout (proxies to the session core)")
    parser.add_argument("--standalone-stdio", action="store_true",
                        help="stdio MCP in this process, no unix socket")
    parser.add_argument("--socket", default="", help="override unix socket path")
    parser.add_argument("--procfs", default="/proc")
    args = parser.parse_args(argv)

    if args.stdio and not args.standalone_stdio:
        return stdio_proxy()

    cfg = config_mod.load()
    db = None if args.standalone_stdio else perception_db()
    core = Core(cfg, procfs=args.procfs, db_path=db)

    def handle_stop(signum, frame):  # noqa: ARG001
        core.stop()

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    if args.standalone_stdio:
        sampler = threading.Thread(target=core.sampler_loop, daemon=True)
        sampler.start()
        try:
            return stdio_loop(core)
        finally:
            core.stop()

    path = Path(args.socket) if args.socket else socket_path()
    sock = serve_unix(core, path)
    print(f"synapse-core {__version__} listening on {path}", file=sys.stderr)
    sampler = threading.Thread(target=core.sampler_loop, daemon=True)
    sampler.start()
    try:
        accept_loop(core, sock)
    finally:
        core.stop()
        try:
            sock.close()
        except OSError:
            pass
        try:
            path.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
