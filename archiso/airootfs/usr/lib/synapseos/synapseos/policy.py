"""Capability gate: observe / assist / act, protected set, pending consent."""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import audit
from .config import MODES, Config
from .paths import grants_file


READ_TOOLS = {
    "apps_list",
    "apps_running",
    "windows_list",
    "browser_tabs",
    "proc_list",
    "proc_explain",
    "sys_status",
    "policy_status",
}

# Side effects that ASSIST will run without a prompt.
AUTO_TOOLS = {
    "apps_launch",
    "apps_focus",
    "browser_open",
    "browser_navigate",
    "notify_send",
    "files_open",
}

# Always confirm in ASSIST. ACT may auto-run if granted.
CONFIRM_TOOLS = {
    "apps_close",
    "proc_throttle",
    "proc_kill",
    "shell_run",
    "policy_set_mode",
}

# Confirm even in ACT unless a matching grant exists.
ALWAYS_CONFIRM = {"shell_run"}

PROTECTED_COMM = {
    "systemd",
    "init",
    "kwin",
    "kwin_wayland",
    "kwin_x11",
    "plasmashell",
    "kded6",
    "kglobalacceld",
    "ksmserver",
    "kwin_rules_dialog",
    "sddm",
    "sddm-helper",
    "Xorg",
    "Xwayland",
    "dbus-daemon",
    "dbus-broker",
    "dbus-broker-launch",
    "pipewire",
    "pipewire-pulse",
    "wireplumber",
    "gnome-keyring-d",
    "gnome-keyring-daemon",
    "gcr-ssh-agent",
    "synapseos-core",
    "synapseos-overlay",
    "synapseos-mcp",
    "sshd",
    "login",
    "agetty",
    "hyprland",
    "Hyprland",
    "quickshell",
    "qs",
    "caelestia-shell",
    "greetd",
    "tuigreet",
    "waybar",
}

PROTECTED_PREFIXES = (
    "systemd",
    "kwin",
    "plasma",
    "ksmserver",
    "klauncher",
    "xdg-desktop-portal",
)

PROTECTED_PIDS = {1}

PENDING_TTL = 300.0


@dataclass
class Pending:
    id: str
    tool: str
    arguments: dict[str, Any]
    summary: str
    created: float
    grant_key: str = ""


@dataclass
class Decision:
    allow: bool
    needs_consent: bool = False
    consent_id: str = ""
    summary: str = ""
    error: str = ""
    reason: str = ""

    def denied(self, error: str, reason: str = "") -> "Decision":
        self.allow = False
        self.error = error
        self.reason = reason or "denied"
        return self


class Policy:
    def __init__(self, cfg: Config, grants_path: Path | None = None):
        self.cfg = cfg
        self.grants_path = grants_path or grants_file()
        self.pending: dict[str, Pending] = {}
        self._grants: set[str] = set()
        self._load_grants()

    @property
    def mode(self) -> str:
        return self.cfg.policy.mode if self.cfg.policy.mode in MODES else "assist"

    @mode.setter
    def mode(self, value: str) -> None:
        if value not in MODES:
            raise ValueError(f"unknown mode {value!r}")
        self.cfg.policy.mode = value

    @property
    def paused(self) -> bool:
        return bool(self.cfg.policy.paused)

    @paused.setter
    def paused(self, value: bool) -> None:
        self.cfg.policy.paused = bool(value)

    def status(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "paused": self.paused,
            "pending": [
                {"id": p.id, "tool": p.tool, "summary": p.summary}
                for p in self.pending.values()
            ],
        }

    def check(self, tool: str, arguments: dict[str, Any], *,
              summary: str,
              comm: str = "",
              pid: int | None = None,
              exe: str = "",
              skip_consent: bool = False) -> Decision:
        self._expire()
        if self.paused and tool not in {"policy_status", "policy_set_mode"}:
            if tool not in READ_TOOLS:
                return Decision(False).denied(
                    "Synapse is paused (kill switch). Resume with synapsectl resume.",
                    "paused",
                )
        if tool in {"proc_kill", "proc_throttle", "apps_close"}:
            if is_protected(comm=comm, pid=pid, exe=exe):
                return Decision(False).denied(
                    f"protected process refused: {comm or pid}",
                    "protected",
                )
        if self.mode == "observe" and tool not in READ_TOOLS and tool != "policy_set_mode":
            return Decision(False).denied(
                f"{tool} is blocked in observe mode",
                "observe",
            )
        if skip_consent:
            return Decision(True, reason="confirmed")
        grant = grant_key(tool, arguments, comm=comm)
        if grant in self._grants:
            return Decision(True, reason="grant")
        needs = tool in ALWAYS_CONFIRM or (
            self.mode == "assist" and tool in CONFIRM_TOOLS
        )
        if self.mode == "act" and tool in ALWAYS_CONFIRM:
            needs = True
        if not needs:
            return Decision(True, reason="auto")
        item = Pending(
            id=uuid.uuid4().hex[:12],
            tool=tool,
            arguments=arguments,
            summary=summary,
            created=time.time(),
            grant_key=grant,
        )
        self.pending[item.id] = item
        audit.record("consent", status="pending", tool=tool, summary=summary, id=item.id)
        return Decision(
            False,
            needs_consent=True,
            consent_id=item.id,
            summary=summary,
            reason="consent",
        )

    def take(self, consent_id: str) -> Pending | None:
        self._expire()
        return self.pending.pop(consent_id, None)

    def remember(self, grant: str) -> None:
        if not grant:
            return
        self._grants.add(grant)
        self._save_grants()

    def _expire(self) -> None:
        now = time.time()
        dead = [k for k, p in self.pending.items() if now - p.created > PENDING_TTL]
        for key in dead:
            self.pending.pop(key, None)

    def _load_grants(self) -> None:
        if not self.grants_path.is_file():
            return
        try:
            data = json.loads(self.grants_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(data, list):
            self._grants = {str(x) for x in data}

    def _save_grants(self) -> None:
        try:
            self.grants_path.write_text(
                json.dumps(sorted(self._grants), indent=2) + "\n",
                encoding="utf-8",
            )
            os.chmod(self.grants_path, 0o600)
        except OSError:
            pass


def is_protected(*, comm: str = "", pid: int | None = None, exe: str = "") -> bool:
    if pid is not None and (pid in PROTECTED_PIDS or pid == os.getpid()):
        return True
    name = (comm or "").strip()
    if name in PROTECTED_COMM:
        return True
    low = name.lower()
    if any(low.startswith(p) for p in PROTECTED_PREFIXES):
        return True
    base = Path(exe).name.lower() if exe else ""
    if base in {c.lower() for c in PROTECTED_COMM}:
        return True
    if any(base.startswith(p) for p in PROTECTED_PREFIXES):
        return True
    if "synapseos" in name.lower() or "synapseos" in base:
        return True
    return False


def grant_key(tool: str, arguments: dict[str, Any], *, comm: str = "") -> str:
    """Stable-ish grant: tool + comm (or dest), not the raw pid."""
    material = {"tool": tool, "comm": comm}
    if tool == "shell_run":
        material["argv0"] = _argv0(arguments)
    elif tool in {"browser_open", "browser_navigate"}:
        material["host"] = str(arguments.get("url") or "")
    elif tool == "files_open":
        material["path"] = str(arguments.get("path") or "")
    blob = json.dumps(material, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:20]


def _argv0(arguments: dict[str, Any]) -> str:
    argv = arguments.get("argv") or arguments.get("command")
    if isinstance(argv, list) and argv:
        return str(argv[0])
    if isinstance(argv, str):
        return argv.split()[0] if argv.split() else ""
    return ""


def describe_kill(comm: str, pid: int, signal: str = "TERM") -> str:
    return f"Send SIG{signal} to {comm} (pid {pid})"


def describe_throttle(comm: str, pid: int, percent: int) -> str:
    return f"Throttle {comm} (pid {pid}) to {percent}% CPU"


def describe_close(title: str) -> str:
    return f"Close the window “{title}”"


def describe_shell(argv: list[str]) -> str:
    return "Run command: " + " ".join(argv)


# Used by the planner to render a pending card.
SummaryFn = Callable[[str, dict[str, Any]], str]
