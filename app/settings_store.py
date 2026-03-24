from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


SETTINGS_PATH = Path(os.getenv("LLM_SETTINGS_PATH", "/data/cache/ui_llm_settings.json"))


def _ensure_parent() -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_llm_settings() -> dict[str, Any]:
    try:
        if not SETTINGS_PATH.exists():
            return {}
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_llm_settings(settings: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "enabled": settings.get("enabled"),
        "base_url": settings.get("base_url"),
        "api_key": settings.get("api_key"),
        "model": settings.get("model"),
        "temperature": settings.get("temperature"),
        "timeout": settings.get("timeout"),
    }
    cleaned = {k: v for k, v in allowed.items() if v not in (None, "")}
    _ensure_parent()
    SETTINGS_PATH.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    return cleaned
