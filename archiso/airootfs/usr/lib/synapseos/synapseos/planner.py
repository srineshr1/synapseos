"""Route a request through Jev or a local small model. Tools run locally."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from . import audit
from .config import Config
from .decide import DecideError, choose, say
from .policy import CONFIRM_TOOLS, READ_TOOLS
from .runtime import reply_key, resolve, resolve_reply
from .tools import ConsentNeeded, ToolBroker

MIN_CONFIDENCE = 0.45
_URL = re.compile(r"https?://\S+")
_PATH = re.compile(r"(?:~|/|\./)[^\s\"']+")

EventFn = Callable[[str, dict[str, Any]], None]


class Planner:
    def __init__(self, cfg: Config, tools: ToolBroker):
        self.cfg = cfg
        self.tools = tools

    def ask(self, text: str, *, snapshot: str = "", on_event: EventFn | None = None,
            extra_messages: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        del extra_messages
        route = resolve(self.cfg)
        if route.kind == "needs_key":
            return {
                "status": "needs_key",
                "error": route.message,
                "providers": list(route_providers()),
                "capable": route.capable,
            }
        if route.kind == "needs_runtime":
            return {
                "status": "needs_runtime",
                "error": route.message,
                "capable": True,
                "ram_mb": route.ram_mb,
            }

        names = [spec["name"] for spec in self.tools.specs]
        try:
            decision = choose(
                route, self.cfg.api_key(), text, snapshot, names,
            )
        except DecideError as exc:
            audit.record("ask", status="error", error=str(exc))
            return {"status": "error", "error": str(exc)}

        tool = str(decision.get("tool") or "none")
        confidence = float(decision.get("confidence") or 0)
        if tool not in names:
            audit.record("ask", status="done", tool="none")
            return self._done(
                text, route,
                "Say what to open, focus, close, or inspect. I only run the OS tools.",
            )
        if confidence < MIN_CONFIDENCE and tool not in READ_TOOLS:
            return self._done(
                text, route,
                f"Not sure enough to run {tool} ({confidence:.0%}). "
                "Say the app or the process more plainly.",
                confidence=confidence,
            )
        if tool == "shell_run":
            return self._done(
                text, route,
                "I won't invent a shell command. Use a specific tool, "
                "or synapsectl call shell_run with an argv list.",
            )

        args = _arguments(tool, decision, text)
        missing = _missing_arg(tool, args)
        if missing:
            return self._done(text, route, missing)
        if on_event:
            on_event("tool", {"name": tool, "arguments": args, "phase": "start"})
        try:
            result = self.tools.call(tool, args)
        except ConsentNeeded as exc:
            if on_event:
                on_event("consent", {"id": exc.consent_id, "summary": exc.summary})
            return _consent(exc.consent_id, exc.summary, tool, args)
        if result.get("status") == "needs_consent":
            if on_event:
                on_event("consent", {
                    "id": result.get("consent_id"),
                    "summary": result.get("summary"),
                })
            return _consent(
                str(result.get("consent_id") or ""),
                str(result.get("summary") or ""),
                tool,
                args,
            )
        if on_event:
            on_event("tool", {"name": tool, "phase": "done", "ok": bool(result.get("ok"))})
        factual = speak(tool, result)
        spoken = self._voice(text, factual)
        audit.record("ask", status="done", tool=tool, backend=route.kind)
        return {
            "status": "done" if result.get("ok") else "error",
            "text": spoken,
            "tool": tool,
            "confidence": confidence,
            "backend": route.kind,
            "model": route.model,
            "result": result,
        }

    def _done(self, user: str, route: Any, factual: str, **extra: Any) -> dict[str, Any]:
        payload = {
            "status": "done",
            "text": self._voice(user, factual),
            "backend": route.kind,
            "model": route.model,
        }
        payload.update(extra)
        return payload

    def _voice(self, user: str, factual: str) -> str:
        """Jev picked the action. A chat model writes the reply, when one is up."""
        reply_route = resolve_reply(self.cfg)
        if reply_route is None:
            return factual
        try:
            written = say(reply_route, reply_key(self.cfg, reply_route), user, factual)
        except DecideError:
            return factual
        return written or factual


class PlannerError(Exception):
    pass


def transcribe(cfg: Config, audio: bytes, filename: str = "utt.wav") -> str:
    del cfg, audio, filename
    raise PlannerError("Voice input is off. Type the request.")


def speak(tool: str, result: dict[str, Any]) -> str:
    if not result.get("ok"):
        return str(result.get("error") or "That did not work.")
    if tool == "apps_running":
        return _lines("Running", [
            f"{app.get('name')}  {app.get('elapsed') or ''}  cpu {app.get('cpu_pct')}%"
            for app in (result.get("apps") or [])[:12]
        ], "Nothing is running in this session.")
    if tool == "apps_list":
        return _lines("Installed", [
            str(app.get("name") or app.get("id"))
            for app in (result.get("apps") or [])[:20]
        ], "No matching applications.")
    if tool == "windows_list":
        return _lines("Windows", [
            f"{win.get('title') or win.get('app_id')}  pid {win.get('pid')}"
            for win in (result.get("windows") or [])[:12]
        ], "No open windows.")
    if tool == "proc_list":
        return _lines("Processes", [
            f"{proc.get('pid')}  {proc.get('comm')}  {proc.get('cpu_pct')}%  {proc.get('elapsed')}"
            for proc in (result.get("processes") or [])[:12]
        ], "No processes.")
    if tool == "browser_tabs":
        return _lines("Browser windows", [
            str(tab.get("title") or tab.get("app_id"))
            for tab in (result.get("tabs") or [])[:12]
        ], "No browser windows.")
    if tool == "sys_status":
        load = result.get("load")
        mem = result.get("memory") or result.get("mem")
        return "Status: " + ", ".join(
            part for part in (
                f"load {load}" if load else "",
                f"memory {mem}" if mem else "",
                f"battery {result.get('battery')}" if result.get("battery") else "",
            ) if part
        ) or "Status collected."
    launched = result.get("launched")
    if isinstance(launched, dict):
        return f"Launched {launched.get('name') or launched.get('id')}."
    window = result.get("window")
    if isinstance(window, dict) and tool == "apps_focus":
        return f"Focused {window.get('title') or window.get('app_id')}."
    if isinstance(window, dict) and tool == "apps_close":
        return f"Closed {window.get('title') or window.get('app_id')}."
    if result.get("url"):
        return f"Opened {result['url']}."
    if result.get("signal"):
        return f"Sent {result['signal']} to {result.get('pid')}."
    if result.get("percent") and result.get("pid"):
        return f"Capped pid {result['pid']} at {result['percent']}% of one CPU."
    if tool == "policy_status":
        return json.dumps(
            {k: result.get(k) for k in ("mode", "paused") if k in result},
            ensure_ascii=False,
        ) or "Policy unchanged."
    return "Done."


def route_providers() -> list[dict[str, str]]:
    from .runtime import PROVIDERS
    return [
        {"id": key, "label": str(spec["label"])}
        for key, spec in PROVIDERS.items()
    ]


def _consent(consent_id: str, summary: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "needs_consent",
        "consent_id": consent_id,
        "summary": summary,
        "text": summary,
        "pending_call": {"name": tool, "arguments": args},
    }


def _arguments(tool: str, decision: dict[str, Any], text: str) -> dict[str, Any]:
    query = str(decision.get("query") or "").strip()
    if tool in {"apps_launch", "apps_focus", "apps_close", "apps_list"}:
        return {"query": query}
    if tool == "proc_explain":
        return {"pid": decision.get("pid")}
    if tool == "proc_kill":
        return {"pid": decision.get("pid"), "force": bool(decision.get("force"))}
    if tool == "proc_throttle":
        percent = decision.get("percent") or 25
        return {"pid": decision.get("pid"), "percent": percent}
    if tool == "proc_list":
        args: dict[str, Any] = {}
        if decision.get("sort") in {"cpu", "rss", "elapsed"}:
            args["sort"] = decision["sort"]
        return args
    if tool in {"browser_open", "browser_navigate"}:
        url = str(decision.get("url") or "").strip()
        if not url:
            found = _URL.search(text)
            url = found.group(0) if found else text.strip()
        return {"url": url}
    if tool == "files_open":
        path = query
        if not path:
            found = _PATH.search(text)
            path = found.group(0) if found else ""
        return {"path": path}
    if tool == "notify_send":
        return {"title": "Synapse", "body": text.strip()}
    if tool == "policy_set_mode":
        args = {}
        if decision.get("mode") in {"observe", "assist", "act"}:
            args["mode"] = decision["mode"]
        if decision.get("paused") is not None:
            args["paused"] = bool(decision["paused"])
        return args
    return {}


def _missing_arg(tool: str, args: dict[str, Any]) -> str:
    if tool in {"apps_launch", "apps_focus", "apps_close"} and not args.get("query"):
        return "Which app?"
    if tool in {"proc_explain", "proc_kill", "proc_throttle"} and not args.get("pid"):
        return "Which process? Give me one that is actually running."
    if tool == "files_open" and not args.get("path"):
        return "Which file?"
    if tool == "policy_set_mode" and "mode" not in args and "paused" not in args:
        return "Say observe, assist, act, pause, or resume."
    if tool in CONFIRM_TOOLS and tool == "proc_kill" and not args.get("pid"):
        return "Which process?"
    return ""


def _lines(title: str, rows: list[str], empty: str) -> str:
    clean = [row.strip() for row in rows if row and row.strip()]
    if not clean:
        return empty
    return title + ":\n" + "\n".join(clean)
