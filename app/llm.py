import os
from typing import Any

import httpx


_TRUE_VALUES = {"1", "true", "yes", "on"}


def _strip(value: str | None) -> str:
    return (value or "").strip()


def llm_settings(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    overrides = overrides or {}
    base_url = _strip(os.getenv("LLM_BASE_URL"))
    model = _strip(os.getenv("LLM_MODEL"))
    api_key = _strip(os.getenv("LLM_API_KEY"))
    enabled_raw = _strip(os.getenv("LLM_ENABLED"))
    temperature_raw = _strip(os.getenv("LLM_TEMPERATURE"))
    timeout_raw = _strip(os.getenv("LLM_TIMEOUT"))

    enabled = enabled_raw.lower() in _TRUE_VALUES if enabled_raw else bool(base_url and model)
    try:
        temperature = float(temperature_raw) if temperature_raw else 0.2
    except ValueError:
        temperature = 0.2
    try:
        timeout = float(timeout_raw) if timeout_raw else 60.0
    except ValueError:
        timeout = 60.0

    if overrides.get("model") is not None:
        model = _strip(str(overrides["model"]))
    if overrides.get("temperature") is not None:
        try:
            temperature = float(overrides["temperature"])
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
        if item.get("page_start") is not None or item.get("page_end") is not None:
            location.append(f"页码 {item.get('page_start')}-{item.get('page_end')}")
        loc_text = f" / {' / '.join(location)}" if location else ""
        context_lines.append(
            f"[{idx}] 书名: {item.get('book')}{loc_text}\n"
            f"chunk_id: {item.get('chunk_id')}\n"
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
