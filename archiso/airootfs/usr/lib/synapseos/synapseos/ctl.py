"""synapsectl — talk to synapse-core from a terminal."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from typing import Any

from . import __version__
from .client import ClientError, CoreClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="synapsectl")
    parser.add_argument("--version", action="version", version=f"synapsectl {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ask = sub.add_parser("ask", help="send a natural-language request")
    p_ask.add_argument("text", nargs="+")

    sub.add_parser("status", help="daemon status")
    sub.add_parser("apps", help="running apps with elapsed time")
    p_list = sub.add_parser("list", help="installed desktop apps")
    p_list.add_argument("query", nargs="?")
    p_proc = sub.add_parser("proc", help="process table (or one pid)")
    p_proc.add_argument("pid", nargs="?", type=int)
    p_mode = sub.add_parser("mode", help="observe | assist | act")
    p_mode.add_argument("value")
    sub.add_parser("pause", help="kill switch on")
    sub.add_parser("resume", help="kill switch off")
    p_audit = sub.add_parser("audit", help="recent audit log")
    p_audit.add_argument("-n", type=int, default=20)
    p_key = sub.add_parser("key", help="set or check the xAI API key")
    p_key.add_argument("action", choices=("set", "check"))
    sub.add_parser("ping", help="is the core up?")
    p_call = sub.add_parser("call", help="raw MCP tool call")
    p_call.add_argument("tool")
    p_call.add_argument("json_args", nargs="?", default="{}")

    args = parser.parse_args(argv)
    try:
        with CoreClient() as cli:
            return _dispatch(cli, args)
    except ClientError as exc:
        print(f"synapsectl: {exc}", file=sys.stderr)
        return 1


def _dispatch(cli: CoreClient, args: argparse.Namespace) -> int:
    if args.cmd == "ask":
        text = " ".join(args.text)
        result = cli.call("synapse/ask", {"text": text}, on_event=_print_event)
        _print_ask(result)
        return 0 if result.get("status") in {"done", "needs_consent", "needs_key"} else 1
    if args.cmd == "status":
        _pp(cli.call("synapse/status"))
        return 0
    if args.cmd == "apps":
        payload = cli.call("tools/call", {"name": "apps_running", "arguments": {}})
        data = payload.get("structuredContent") or {}
        for app in data.get("apps") or []:
            pids = app.get("pids") or []
            extra = app.get("pid_count") or len(pids)
            pid_s = ",".join(str(p) for p in pids[:4])
            if extra > 4:
                pid_s += f" +{extra - 4}"
            print(
                f"{str(app.get('name'))[:28]:<28}  {app.get('elapsed'):>8}  "
                f"cpu {float(app.get('cpu_pct') or 0):>5.1f}  {str(app.get('rss') or ''):>8}  "
                f"pids {pid_s}"
            )
        return 0
    if args.cmd == "list":
        payload = cli.call(
            "tools/call",
            {"name": "apps_list", "arguments": {"query": args.query or ""}},
        )
        data = payload.get("structuredContent") or {}
        for app in data.get("apps") or []:
            print(f"{app.get('id'):<40} {app.get('name')}")
        return 0
    if args.cmd == "proc":
        if args.pid:
            payload = cli.call(
                "tools/call",
                {"name": "proc_explain", "arguments": {"pid": args.pid}},
            )
            _pp(payload.get("structuredContent") or payload)
            return 0
        payload = cli.call("tools/call", {"name": "proc_list", "arguments": {"limit": 25}})
        data = payload.get("structuredContent") or {}
        for proc in data.get("processes") or []:
            print(
                f"{proc.get('pid'):>7}  {proc.get('cpu_pct'):>6}  "
                f"{proc.get('rss'):>8}  {proc.get('elapsed'):>8}  {proc.get('comm')}"
            )
        return 0
    if args.cmd == "mode":
        _pp(cli.call("synapse/set_mode", {"mode": args.value}))
        return 0
    if args.cmd == "pause":
        _pp(cli.call("synapse/set_paused", {"paused": True}))
        return 0
    if args.cmd == "resume":
        _pp(cli.call("synapse/set_paused", {"paused": False}))
        return 0
    if args.cmd == "audit":
        data = cli.call("synapse/audit", {"limit": args.n})
        for entry in data.get("entries") or []:
            ts = entry.get("ts")
            ev = entry.get("event")
            rest = {k: v for k, v in entry.items() if k not in {"ts", "event"}}
            print(f"{ts}\t{ev}\t{json.dumps(rest, default=str)}")
        return 0
    if args.cmd == "key":
        if args.action == "check":
            st = cli.call("synapse/status")
            print("configured" if st.get("has_key") else "missing")
            return 0 if st.get("has_key") else 2
        key = getpass.getpass("XAI_API_KEY: ").strip()
        if not key:
            print("empty key", file=sys.stderr)
            return 2
        cli.call("synapse/set_key", {"key": key})
        print("saved")
        return 0
    if args.cmd == "ping":
        st = cli.call("synapse/status")
        print(f"ok  pid={st.get('pid')}  mode={st.get('mode')}  key={st.get('has_key')}")
        return 0
    if args.cmd == "call":
        try:
            arguments = json.loads(args.json_args)
        except json.JSONDecodeError as exc:
            print(f"bad json: {exc}", file=sys.stderr)
            return 2
        _pp(cli.call("tools/call", {"name": args.tool, "arguments": arguments}))
        return 0
    return 2


def _print_event(event: dict[str, Any]) -> None:
    kind = event.get("type")
    if kind == "text":
        sys.stdout.write(str(event.get("text") or ""))
        sys.stdout.flush()
    elif kind == "tool":
        phase = event.get("phase")
        name = event.get("name")
        if phase == "start":
            print(f"\n→ {name}", file=sys.stderr)
    elif kind == "consent":
        print(f"\nconsent required: {event.get('summary')}", file=sys.stderr)
        print(f"  synapsectl call  (or use the overlay)  id={event.get('id')}", file=sys.stderr)


def _print_ask(result: dict[str, Any]) -> None:
    status = result.get("status")
    if status == "needs_key":
        print("No API key. Run:  synapsectl key set", file=sys.stderr)
        return
    if status == "needs_consent":
        print(f"\nNeeds consent: {result.get('summary')}")
        print(f"consent_id={result.get('consent_id')}")
        return
    if status == "error":
        print(result.get("error") or "error", file=sys.stderr)
        return
    text = result.get("text") or ""
    if text and not text.endswith("\n"):
        print()
    elif not text:
        print(json.dumps(result, indent=2, default=str))


def _pp(value: Any) -> None:
    print(json.dumps(value, indent=2, default=str, ensure_ascii=False))
