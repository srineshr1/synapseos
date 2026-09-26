"""One decision per request.

Jev (TypeSafe /v1/systemone) returns a tool and closed-set arguments with a
confidence. A local or other chat model is asked for the same JSON object.
Neither path writes the reply the user sees. The caller does that from the
tool result.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from .runtime import Route


class DecideError(Exception):
    pass

JEV_TIMEOUT = 8
CHAT_TIMEOUT = 45
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

TOOL_BLURB = {
    "apps_list": "List installed applications, optionally filtered by name.",
    "apps_running": "What is running in this session, and for how long.",
    "apps_launch": "Open an installed application.",
    "apps_focus": "Bring an open window to the front.",
    "apps_close": "Close an open window.",
    "windows_list": "List open windows.",
    "browser_open": "Open a web page or search.",
    "browser_navigate": "Open a web page or search.",
    "browser_tabs": "List browser windows.",
    "proc_list": "Show processes, CPU, memory, and elapsed time.",
    "proc_explain": "Explain one process.",
    "proc_throttle": "Slow a process down.",
    "proc_kill": "Stop a process.",
    "sys_status": "Machine status: load, memory, battery, thermals.",
    "notify_send": "Show a desktop notification.",
    "files_open": "Open a file or folder.",
    "shell_run": "Run a shell command. Prefer a specific tool instead.",
    "policy_status": "Show assistant mode and whether it is paused.",
    "policy_set_mode": "Change assistant mode, or pause or resume it.",
}


def say(route: Route, key: str, user: str, factual: str) -> str:
    """Turn a finished tool result into the sentence the user reads."""
    body = {
        "model": route.model,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Synapse, the assistant on this Linux desktop. "
                    "Write one or two short sentences. Use only the facts you "
                    "are given. Do not invent apps, numbers, or actions."
                ),
            },
            {
                "role": "user",
                "content": f"The user said: {user.strip()}\n\nWhat happened:\n{factual.strip()}",
            },
        ],
    }
    data = _post(route.base_url + "/chat/completions", key, body, CHAT_TIMEOUT, "reply model")
    return _message_text(data).strip()


def choose(route: Route, key: str, text: str, snapshot: str,
           tool_names: list[str]) -> dict[str, Any]:
    state = text.strip()
    if snapshot:
        state += "\n\nSession:\n" + snapshot
    if route.wire == "jev":
        answers = _jev(route, key, state, tool_names)
        return decision_from_jev(answers)
    raw = _chat(route, key, state, tool_names)
    return decision_from_chat(raw)


def decision_from_jev(answers: dict[str, Any]) -> dict[str, Any]:
    tool_ans = answers.get("tool") if isinstance(answers.get("tool"), dict) else {}
    tool = str(tool_ans.get("choice") or "none")
    confidence = _float(tool_ans.get("confidence"), 0.0)
    app = _choice(answers.get("app"))
    pid_choice = _choice(answers.get("pid"))
    sort = _choice(answers.get("sort"))
    percent = _choice(answers.get("percent"))
    mode = _choice(answers.get("mode"))
    force = _noul(answers.get("force")) >= 0.6
    pause_p = _noul(answers.get("paused"))
    paused: bool | None
    if pause_p >= 0.6:
        paused = True
    elif pause_p <= 0.3:
        paused = False
    else:
        paused = None
    used = [confidence]
    if app != "none":
        used.append(_float(_answer(answers, "app").get("confidence"), confidence))
    if pid_choice != "none":
        used.append(_float(_answer(answers, "pid").get("confidence"), confidence))
    return _decision(
        tool=tool,
        confidence=min(used) if used else 0.0,
        query="" if app == "none" else app,
        pid=_pid(pid_choice),
        sort="" if sort == "none" else sort,
        percent=_percent(percent),
        mode="" if mode == "none" else mode,
        force=force,
        paused=paused,
    )


def decision_from_chat(raw: str) -> dict[str, Any]:
    payload = _json_object(raw)
    tool = str(payload.get("tool") or "none").strip()
    confidence = payload.get("confidence")
    if confidence is None:
        confidence_f = 0.6 if tool and tool != "none" else 0.0
    else:
        confidence_f = _float(confidence, 0.0)
    paused_raw = payload.get("paused")
    paused: bool | None
    if paused_raw is None or paused_raw == "":
        paused = None
    else:
        paused = bool(paused_raw)
    return _decision(
        tool=tool,
        confidence=confidence_f,
        query=str(payload.get("query") or "").strip(),
        pid=_pid(payload.get("pid")),
        url=str(payload.get("url") or "").strip(),
        sort=str(payload.get("sort") or "").strip(),
        percent=_percent(payload.get("percent")),
        mode=str(payload.get("mode") or "").strip(),
        force=bool(payload.get("force")),
        paused=paused,
    )


def _decision(**fields: Any) -> dict[str, Any]:
    base = {
        "tool": "none",
        "confidence": 0.0,
        "query": "",
        "pid": None,
        "url": "",
        "sort": "",
        "percent": None,
        "mode": "",
        "force": False,
        "paused": None,
    }
    base.update(fields)
    return base


def _jev(route: Route, key: str, state: str, tool_names: list[str]) -> dict[str, Any]:
    questions: dict[str, Any] = {
        "tool": {
            "type": "choice",
            "instructions": "Which tool should handle this request?",
            "criteria": _tool_criteria(tool_names),
        },
        "app": {
            "type": "choice",
            "instructions": "Which app or window does the request name?",
            "criteria": _app_criteria(state),
        },
        "pid": {
            "type": "choice",
            "instructions": "Which process id is the target, when the request names one?",
            "criteria": _pid_criteria(state),
        },
        "sort": {
            "type": "choice",
            "instructions": "How should a process list be ordered, if the user said?",
            "criteria": {
                "cpu": "highest CPU first",
                "rss": "largest memory first",
                "elapsed": "longest running first",
                "none": "the user did not say",
            },
        },
        "percent": {
            "type": "choice",
            "instructions": "What CPU cap does the user want, if they asked to slow a process?",
            "criteria": {
                "10": "a small share, about ten percent",
                "25": "a quarter of one CPU",
                "50": "half of one CPU",
                "75": "most of one CPU",
                "none": "the user did not give a cap",
            },
        },
        "mode": {
            "type": "choice",
            "instructions": "Which assistant mode does the user want, if they named one?",
            "criteria": {
                "observe": "watch only, no actions",
                "assist": "act, but confirm destructive actions",
                "act": "act with less confirmation",
                "none": "the user did not name a mode",
            },
        },
        "force": {
            "type": "noul",
            "instructions": "Does the user want a forced kill rather than a normal stop?",
        },
        "paused": {
            "type": "noul",
            "instructions": "Does the user want the assistant paused?",
        },
    }
    body = {"model": route.model or "jev-latest", "state": state, "questions": questions}
    data = _post(route.base_url + "/systemone", key, body, JEV_TIMEOUT, "TypeSafe")
    answers = data.get("answers")
    if not isinstance(answers, dict):
        raise DecideError("TypeSafe returned no answers")
    return answers


def _chat(route: Route, key: str, state: str, tool_names: list[str]) -> str:
    names = ", ".join([*tool_names, "none"])
    prompt = (
        "Route this OS request. Reply with one JSON object and no other text. "
        "Keys: tool, query, pid, url, sort, percent, mode, force, paused, confidence. "
        f"tool is one of: {names}. "
        "query is an app or file name taken from the request, or empty. "
        "pid is an integer from the session, or null. "
        "url is a web address, or empty. sort is cpu, rss, elapsed, or empty. "
        "percent is 10, 25, 50, 75, or null. mode is observe, assist, act, or empty. "
        "force and paused are booleans. confidence is from 0 to 1.\n\n"
        + state
    )
    body = {
        "model": route.model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": "You only output JSON."},
            {"role": "user", "content": prompt},
        ],
    }
    data = _post(route.base_url + "/chat/completions", key, body, CHAT_TIMEOUT, "local model")
    return _message_text(data)


def _message_text(data: dict[str, Any]) -> str:
    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices:
        raise DecideError("reply model returned no choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else ""
    if isinstance(content, list):
        content = "".join(
            str(part.get("text") or "") for part in content if isinstance(part, dict)
        )
    return str(content or "")


def _post(url: str, key: str, body: dict[str, Any], timeout: int, who: str) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method="POST", headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise DecideError(f"{who} HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise DecideError(f"{who} request failed: {exc}") from exc


def _tool_criteria(tool_names: list[str]) -> dict[str, str]:
    criteria = {
        name: TOOL_BLURB.get(name, name)
        for name in tool_names
    }
    criteria["none"] = "The request is not something these tools do."
    return criteria


def _app_criteria(state: str) -> dict[str, str]:
    criteria = {"none": "No particular app is named."}
    for match in re.finditer(r"^- (?P<name>.+?) \[", state, re.MULTILINE):
        name = match.group("name").strip()
        if name and name not in criteria and len(criteria) < 80:
            criteria[name] = "an app in this session"
    return criteria


def _pid_criteria(state: str) -> dict[str, str]:
    criteria = {"none": "No particular process is named."}
    for match in re.finditer(r"pids=([0-9,]+)", state):
        for piece in match.group(1).split(","):
            if piece.isdigit() and piece not in criteria and len(criteria) < 60:
                criteria[piece] = "a process in this session"
    return criteria


def _answer(answers: dict[str, Any], key: str) -> dict[str, Any]:
    value = answers.get(key)
    return value if isinstance(value, dict) else {}


def _choice(value: Any) -> str:
    if not isinstance(value, dict):
        return "none"
    return str(value.get("choice") or "none")


def _noul(value: Any) -> float:
    if not isinstance(value, dict):
        return 0.0
    return _float(value.get("noul"), 0.0)


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _pid(value: Any) -> int | None:
    if value is None or value == "" or value == "none":
        return None
    try:
        pid = int(value)
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def _percent(value: Any) -> int | None:
    if value is None or value == "" or value == "none":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return max(1, min(100, number))


def _json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DecideError(f"model did not return JSON: {raw[:180]}") from exc
    if not isinstance(payload, dict):
        raise DecideError("model JSON was not an object")
    return payload
