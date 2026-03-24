import os
from typing import Any

import httpx

from settings_store import load_llm_settings


_TRUE_VALUES = {"1", "true", "yes", "on"}


def _strip(value: str | None) -> str:
    return (value or "").strip()


def _coalesce(*values: object) -> str:
    for value in values:
        text = _strip(None if value is None else str(value))
        if text:
            return text
    return ""


def llm_settings(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    overrides = overrides or {}
    persisted = load_llm_settings()

    env_base_url = _strip(os.getenv("LLM_BASE_URL"))
    env_model = _strip(os.getenv("LLM_MODEL"))
    env_api_key = _strip(os.getenv("LLM_API_KEY"))
    env_enabled_raw = _strip(os.getenv("LLM_ENABLED"))
    env_temperature_raw = _strip(os.getenv("LLM_TEMPERATURE"))
    env_timeout_raw = _strip(os.getenv("LLM_TIMEOUT"))

    base_url = _coalesce(env_base_url, persisted.get("base_url"))
    model = _coalesce(env_model, persisted.get("model"))
    api_key = _coalesce(env_api_key, persisted.get("api_key"))
    enabled_raw = _coalesce(
        env_enabled_raw,
        persisted.get("enabled") if persisted.get("enabled") is not None else None,
    )
    temperature_raw = _coalesce(
        env_temperature_raw,
        persisted.get("temperature") if persisted.get("temperature") is not None else None,
    )
    timeout_raw = _coalesce(
        env_timeout_raw,
        persisted.get("timeout") if persisted.get("timeout") is not None else None,
    )

    enabled = enabled_raw.lower() in _TRUE_VALUES if enabled_raw else bool(base_url and model)
    try:
        temperature = float(temperature_raw) if temperature_raw else 0.2
    except ValueError:
        temperature = 0.2
    try:
        timeout = float(timeout_raw) if timeout_raw else 60.0
    except ValueError:
        timeout = 60.0

    if overrides.get("base_url") is not None:
        base_url = _strip(str(overrides["base_url"]))
    if overrides.get("api_key") is not None:
        api_key = _strip(str(overrides["api_key"]))
    if overrides.get("model") is not None:
        model = _strip(str(overrides["model"]))
    if overrides.get("temperature") is not None:
        try:
            temperature = float(overrides["temperature"])
        except (TypeError, ValueError):
            pass
    if overrides.get("timeout") is not None:
        try:
            timeout = float(overrides["timeout"])
        except (TypeError, ValueError):
            pass
    if overrides.get("enabled") is not None:
        enabled = bool(overrides["enabled"])

    return {
        "enabled": enabled and bool(base_url and model),
        "base_url": base_url.rstrip("/"),
        "model": model,
        "api_key": api_key,
        "temperature": temperature,
        "timeout": timeout,
    }


async def generate_rag_answer(
    *,
    question: str,
    contexts: list[dict[str, Any]],
    overrides: dict[str, Any] | None = None,
) -> str:
    settings = llm_settings(overrides)
    if not settings["enabled"]:
        raise RuntimeError("LLM is not enabled")

    context_lines: list[str] = []
    for idx, item in enumerate(contexts, start=1):
        location: list[str] = []
        if item.get("chapter"):
            location.append(str(item["chapter"]))
        if item.get("section"):
            location.append(str(item["section"]))
        if item.get("page_start") is not None or item.get("page_end") is not None:
            location.append(f"页码 {item.get('page_start')}-{item.get('page_end')}")
        loc_text = f" / {' / '.join(location)}" if location else ""
        context_lines.append(
            f"[{idx}] 书名: {item.get('book')}{loc_text}\n"
            f"内容:\n{item.get('chunk_text', '').strip()}"
        )

    system_prompt = (
        "你是一个严格基于检索证据回答问题的知识库助手。"
        "只能根据提供的上下文作答，不要编造未出现的事实。"
        "如果证据不足，要明确说证据不足。"
        "回答默认使用中文，尽量简洁清楚。"
        "当你引用证据时，请在相关句子后使用 [1] [2] 这样的编号。"
    )
    user_prompt = (
        f"用户问题：\n{question}\n\n"
        "下面是检索到的证据片段，请仅基于这些内容回答：\n\n"
        + "\n\n".join(context_lines)
    )

    headers = {"Content-Type": "application/json"}
    if settings["api_key"]:
        headers["Authorization"] = f"Bearer {settings['api_key']}"

    payload = {
        "model": settings["model"],
        "temperature": settings["temperature"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    endpoint = f"{settings['base_url']}/chat/completions"
    async with httpx.AsyncClient(timeout=settings["timeout"]) as client:
        response = await client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected LLM response shape: {data}") from exc
