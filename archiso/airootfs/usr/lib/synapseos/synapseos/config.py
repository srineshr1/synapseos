"""Load and save ~/.config/synapseos/config.toml."""

from __future__ import annotations

import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .paths import config_file

try:
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


MODES = ("observe", "assist", "act")
DEFAULT_MODEL = "grok-4.6"
DEFAULT_BASE_URL = "https://api.x.ai/v1"


@dataclass
class ModelConfig:
    provider: str = "xai"
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    api_key: str = ""


@dataclass
class PolicyConfig:
    mode: str = "assist"
    paused: bool = False


@dataclass
class OverlayConfig:
    hotkey: str = "Meta+S"


@dataclass
class Config:
    model: ModelConfig = field(default_factory=ModelConfig)
    policy: PolicyConfig = field(default_factory=PolicyConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)

    def api_key(self) -> str:
        return (
            os.environ.get("XAI_API_KEY")
            or os.environ.get("SYNAPSEOS_API_KEY")
            or self.model.api_key
            or ""
        ).strip()

    def has_key(self) -> bool:
        return bool(self.api_key())


def load(path: Path | None = None) -> Config:
    target = path or config_file()
    cfg = Config()
    if not target.is_file() or tomllib is None:
        return _clamp(cfg)
    try:
        data = tomllib.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _clamp(cfg)
    if not isinstance(data, dict):
        return _clamp(cfg)
    _apply(cfg.model, data.get("model"))
    _apply(cfg.policy, data.get("policy"))
    _apply(cfg.overlay, data.get("overlay"))
    return _clamp(cfg)


def save(cfg: Config, path: Path | None = None) -> None:
    target = path or config_file()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    text = _dump(cfg)
    fd, tmp = tempfile.mkstemp(prefix="cfg.", dir=str(target.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def set_api_key(key: str, path: Path | None = None) -> Config:
    cfg = load(path)
    cfg.model.api_key = key.strip()
    save(cfg, path)
    return cfg


def _clamp(cfg: Config) -> Config:
    if cfg.policy.mode not in MODES:
        cfg.policy.mode = "assist"
    cfg.model.base_url = (cfg.model.base_url or DEFAULT_BASE_URL).rstrip("/")
    cfg.model.model = cfg.model.model or DEFAULT_MODEL
    return cfg


def _apply(obj: Any, data: Any) -> None:
    if not isinstance(data, dict):
        return
    for key, value in data.items():
        if hasattr(obj, key):
            setattr(obj, key, value)


def _dump(cfg: Config) -> str:
    raw = asdict(cfg)
    lines = [
        "# SynapseOS assistant. Mode 0600. Prefer XAI_API_KEY in the environment.",
        "",
    ]
    for section, values in raw.items():
        lines.append(f"[{section}]")
        for key, value in values.items():
            lines.append(f"{key} = {_toml_value(value)}")
        lines.append("")
    return "\n".join(lines)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    text = "" if value is None else str(value)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
