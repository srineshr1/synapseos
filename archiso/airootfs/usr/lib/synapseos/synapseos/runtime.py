"""Pick Jev, another API provider, or a local small model.

A machine with enough RAM or GPU memory runs a local model when one is
already being served (Ollama or llama.cpp). Otherwise the user chooses a
provider and an API key. TypeSafe Jev is the fast default.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .config import Config

MIN_RAM_MB = 8192
MIN_VRAM_MB = 4096
PROBE_TIMEOUT = 0.25

# id, label, default base URL, default model, env vars that hold the key.
PROVIDERS: dict[str, dict[str, object]] = {
    "typesafe": {
        "label": "TypeSafe Jev",
        "base_url": "https://api.typesafe.ai/v1",
        "model": "jev-latest",
        "env": ("TYPESAFE_API_KEY", "SYNAPSEOS_API_KEY"),
        "kind": "jev",
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-5-nano",
        "env": ("OPENAI_API_KEY", "SYNAPSEOS_API_KEY"),
        "kind": "chat",
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-5-nano",
        "env": ("OPENROUTER_API_KEY", "SYNAPSEOS_API_KEY"),
        "kind": "chat",
    },
    "custom": {
        "label": "Other (OpenAI-compatible URL)",
        "base_url": "",
        "model": "",
        "env": ("SYNAPSEOS_API_KEY",),
        "kind": "chat",
    },
}

API_PROVIDER_IDS = tuple(PROVIDERS)

_probe_at = 0.0
_probe_url: str | None = None
_probe_model: str = ""


@dataclass
class Route:
    kind: str
    provider: str = ""
    model: str = ""
    base_url: str = ""
    wire: str = ""
    message: str = ""
    capable: bool = False
    ram_mb: int = 0


def memory_mb() -> int:
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        return 0
    return 0


def gpu_vram_mb() -> int:
    sysfs = "/sys/class/drm"
    best = 0
    try:
        cards = os.listdir(sysfs)
    except OSError:
        cards = []
    for card in cards:
        path = os.path.join(sysfs, card, "device", "mem_info_vram_total")
        try:
            with open(path, encoding="utf-8") as fh:
                best = max(best, int(fh.read().strip()) // (1024 * 1024))
        except (OSError, ValueError):
            continue
    return best


def can_run_small_model() -> bool:
    flag = os.environ.get("SYNAPSEOS_LOCAL", "").strip()
    if flag == "0":
        return False
    if flag == "1":
        return True
    return memory_mb() >= MIN_RAM_MB or gpu_vram_mb() >= MIN_VRAM_MB


def key_env_names(provider: str) -> tuple[str, ...]:
    spec = PROVIDERS.get(provider)
    if spec is None:
        return ("TYPESAFE_API_KEY", "SYNAPSEOS_API_KEY")
    return tuple(spec["env"])  # type: ignore[arg-type]


def apply_provider(cfg: Config, provider: str, key: str = "",
                   base_url: str = "", model: str = "") -> None:
    provider = (provider or "typesafe").strip().lower()
    if provider == "local":
        cfg.model.provider = "local"
        cfg.model.base_url = ""
        cfg.model.model = model.strip()
        return
    spec = PROVIDERS.get(provider)
    if spec is None:
        raise ValueError(
            "provider must be " + ", ".join((*API_PROVIDER_IDS, "local"))
        )
    cfg.model.provider = provider
    cfg.model.base_url = (base_url or str(spec["base_url"])).rstrip("/")
    cfg.model.model = model.strip() or str(spec["model"])
    if key.strip():
        cfg.model.api_key = key.strip()
    if provider == "custom" and not cfg.model.base_url:
        raise ValueError("custom provider needs a base URL")


def local_base_url() -> tuple[str, str] | None:
    """Return (openai-compatible base, model id) if a local server answers."""
    global _probe_at, _probe_url, _probe_model
    now = time.monotonic()
    if now - _probe_at < 5:
        if _probe_url:
            return _probe_url, _probe_model
        return None
    explicit = os.environ.get("SYNAPSEOS_LOCAL_URL", "").strip().rstrip("/")
    candidates = [explicit] if explicit else [
        "http://127.0.0.1:11434/v1",
        "http://127.0.0.1:8080/v1",
    ]
    found = _first_model(candidates)
    if found is None and not explicit and shutil.which("ollama"):
        _ensure_ollama()
        found = _first_model(["http://127.0.0.1:11434/v1"])
    _probe_at = now
    _probe_url = found[0] if found else None
    _probe_model = found[1] if found else ""
    return found


def reset_probe_cache() -> None:
    global _probe_at, _probe_url, _probe_model
    _probe_at = 0.0
    _probe_url = None
    _probe_model = ""


def jev_key(cfg: Config) -> str:
    """Key for the decision call. Jev never writes the sentence the user reads."""
    for name in ("TYPESAFE_API_KEY",):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    provider = (cfg.model.provider or "auto").strip().lower()
    if provider in {"", "auto", "typesafe"}:
        for name in ("SYNAPSEOS_API_KEY",):
            value = os.environ.get(name, "").strip()
            if value:
                return value
        return (cfg.model.api_key or "").strip()
    return ""


def resolve_reply(cfg: Config) -> Route | None:
    """Chat model that turns a tool result into a sentence. None keeps the facts."""
    capable = can_run_small_model()
    choice = (cfg.model.reply_provider or "auto").strip().lower()
    if choice in {"", "auto", "local"}:
        found = local_base_url()
        if found is not None and (choice == "local" or capable):
            base, model = found
            if choice == "local" and cfg.model.reply_model:
                model = cfg.model.reply_model
            return Route(
                kind="local", provider="local", model=model, base_url=base,
                wire="chat", capable=capable, ram_mb=memory_mb(),
            )
        if choice == "local":
            return None
    provider = choice if choice in PROVIDERS and choice != "typesafe" else ""
    if not provider:
        main = (cfg.model.provider or "").strip().lower()
        if main in PROVIDERS and main != "typesafe":
            provider = main
    if not provider:
        return None
    spec = PROVIDERS[provider]
    key = _reply_key(cfg, provider)
    if not key and provider != "custom":
        return None
    base = (cfg.model.reply_base_url or (cfg.model.base_url if provider == (cfg.model.provider or "") else "") or str(spec["base_url"])).rstrip("/")
    model = cfg.model.reply_model or (cfg.model.model if provider == (cfg.model.provider or "") else "") or str(spec["model"])
    if not base or not model:
        return None
    return Route(
        kind="api", provider=provider, model=model, base_url=base,
        wire="chat", capable=capable, ram_mb=memory_mb(),
    )


def reply_key(cfg: Config, route: Route) -> str:
    if route.kind == "local":
        return ""
    return _reply_key(cfg, route.provider)


def _reply_key(cfg: Config, provider: str) -> str:
    for name in key_env_names(provider):
        if name == "TYPESAFE_API_KEY":
            continue
        value = os.environ.get(name, "").strip()
        if value:
            return value
    if (cfg.model.reply_api_key or "").strip():
        return cfg.model.reply_api_key.strip()
    if (cfg.model.provider or "").strip().lower() == provider:
        return (cfg.model.api_key or "").strip()
    return ""


def resolve(cfg: Config) -> Route:
    capable = can_run_small_model()
    ram = memory_mb()
    provider = (cfg.model.provider or "auto").strip().lower()
    # Jev picks the tool. A chat model, resolved separately, writes the reply.
    if provider in {"", "auto", "typesafe"} and jev_key(cfg):
        spec = PROVIDERS["typesafe"]
        return Route(
            kind="api", provider="typesafe",
            model=cfg.model.model or str(spec["model"]),
            base_url=(cfg.model.base_url or str(spec["base_url"])).rstrip("/"),
            wire="jev", capable=capable, ram_mb=ram,
        )
    if provider == "local" or (provider == "auto" and capable):
        local = local_base_url()
        if local is not None:
            base, model = local
            if cfg.model.model and provider == "local":
                model = cfg.model.model
            return Route(
                kind="local", provider="local", model=model, base_url=base,
                wire="chat", capable=capable, ram_mb=ram,
            )
        if provider == "local" or not cfg.has_key():
            return Route(
                kind="needs_runtime", provider="local", capable=True, ram_mb=ram,
                message=_local_message(ram),
            )
    api_provider = provider if provider in PROVIDERS else "typesafe"
    if not cfg.has_key():
        return Route(
            kind="needs_key", provider=api_provider, capable=capable, ram_mb=ram,
            message=_api_message(ram),
        )
    spec = PROVIDERS[api_provider]
    base = (cfg.model.base_url or str(spec["base_url"])).rstrip("/")
    model = cfg.model.model or str(spec["model"])
    if api_provider == "custom" and not base:
        return Route(
            kind="needs_key", provider="custom", capable=capable, ram_mb=ram,
            message="Custom provider needs a base URL. Run: synapsectl key set",
        )
    return Route(
        kind="api", provider=api_provider, model=model, base_url=base,
        wire=str(spec["kind"]), capable=capable, ram_mb=ram,
    )


def _local_message(ram: int) -> str:
    if shutil.which("ollama"):
        return (
            f"This PC can run a small model locally ({ram} MB RAM) and Ollama "
            "is installed, but no model is pulled yet. Run: ollama pull qwen2.5:0.5b. "
            "Or set an API provider with: synapsectl key set"
        )
    return (
        f"This PC can run a small model locally ({ram} MB RAM). "
        "Nothing is serving one. Install Ollama or llama.cpp and pull a small "
        "model, for example: ollama pull qwen2.5:0.5b. "
        "Or set an API provider with: synapsectl key set"
    )


def _api_message(ram: int) -> str:
    return (
        f"Jev has no key yet ({ram} MB RAM). "
        "In a terminal: synapsectl key set"
    )


def _first_model(candidates: list[str]) -> tuple[str, str] | None:
    for base in candidates:
        if not base:
            continue
        model = _pick_model(_model_ids(base))
        if model:
            return base, model
    return None


def _ensure_ollama() -> None:
    if _model_ids("http://127.0.0.1:11434/v1") is not None:
        return
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if _model_ids("http://127.0.0.1:11434/v1") is not None:
            return
        time.sleep(0.25)


def _model_ids(base: str) -> list[str] | None:
    """None when the server is down. Empty list when it is up with no models."""
    import json
    req = urllib.request.Request(base.rstrip("/") + "/models", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        models = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(models, list):
            return []
        rows = [
            {"id": item.get("name") or item.get("model")}
            for item in models if isinstance(item, dict)
        ]
    return [str(row.get("id") or "") for row in rows if isinstance(row, dict) and row.get("id")]


def _pick_model(ids: list[str] | None) -> str:
    if not ids:
        return ""
    preferred = ("0.5", "1.5b", "1b", "3b", "mini", "small", "qwen", "jev")
    lowered = [(model_id, model_id.lower()) for model_id in ids]
    for needle in preferred:
        for model_id, low in lowered:
            if needle in low:
                return model_id
    return ids[0]
