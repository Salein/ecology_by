from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import settings


class LlmProviderError(RuntimeError):
    pass


def _build_prompt(chunk_text: str) -> str:
    return (
        "Извлеки данные из реестра отходов в строгом JSON формате.\n"
        "Формат ответа: {\"records\": [{...}]}\n"
        "Поля записи:\n"
        "- waste_code (7 цифр)\n"
        "- waste_name\n"
        "- object_name\n"
        "- owner_name\n"
        "- user_address\n"
        "- user_phone\n"
        "- object_id (число)\n"
        "- owner_address\n"
        "- owner_phone\n"
        "- accepts_from_others (boolean)\n"
        "Правила:\n"
        "- Игнорируй колонтитулы/служебный текст.\n"
        "- Если поле не найдено — null.\n"
        "- Верни только JSON, без markdown.\n\n"
        f"Текст:\n{chunk_text}"
    )


def request_openrouter_json(chunk_text: str, *, timeout_sec: float) -> dict[str, Any]:
    api_key = (settings.llm_fallback_openrouter_api_key or "").strip()
    if not api_key:
        raise LlmProviderError("OPENROUTER_API_KEY отсутствует")
    model = settings.llm_fallback_openrouter_model
    if not model:
        raise LlmProviderError("LLM_FALLBACK_OPENROUTER_MODEL не задан")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": _build_prompt(chunk_text)}],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=timeout_sec) as client:
        r = client.post(
            f"{settings.llm_fallback_openrouter_base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
        )
    if r.status_code >= 400:
        raise LlmProviderError(f"openrouter HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception as e:  # pragma: no cover - defensive
        raise LlmProviderError(f"openrouter malformed response: {e}") from e
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise LlmProviderError(f"openrouter invalid json: {e}") from e
