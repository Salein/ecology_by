from __future__ import annotations

from app.services.llm_fallback.service import (
    extract_records_with_llm_fallback,
    should_run_llm_fallback,
    validate_llm_rows,
)


def test_should_run_llm_fallback_requires_problem_segment(monkeypatch) -> None:
    monkeypatch.setattr("app.services.llm_fallback.service.settings.llm_fallback_enabled", True)
    assert not should_run_llm_fallback("короткий текст", 0)
    assert not should_run_llm_fallback("Объект 1 1234567 " * 300, 2)
    assert should_run_llm_fallback("Объект 1 1234567 " * 300, 0)


def test_validate_llm_rows_filters_invalid() -> None:
    rows = [
        {
            "waste_code": "1110700",
            "waste_name": "Отходы зерновые 3 категории",
            "object_name": "Биогазовая установка",
            "owner_name": "ООО Тест",
            "user_address": "г. Минск",
            "user_phone": "123",
            "object_id": 42,
            "owner_address": None,
            "owner_phone": "456",
            "accepts_from_others": True,
        },
        {"waste_code": "bad", "object_id": "x"},
    ]
    out = validate_llm_rows(rows, source_part=2)
    assert len(out) == 1
    assert out[0]["id"] == 42
    assert out[0]["source_part"] == 2
    assert out[0]["waste_code"] == "1110700"
    assert out[0]["phones"] == "123 ; 456"


def test_extract_records_with_llm_fallback_uses_chunks(monkeypatch) -> None:
    monkeypatch.setattr("app.services.llm_fallback.service.settings.llm_fallback_chunk_records", 1)
    monkeypatch.setattr("app.services.llm_fallback.service.settings.llm_fallback_max_retries", 1)
    monkeypatch.setattr("app.services.llm_fallback.service.settings.llm_fallback_timeout_sec", 1.0)

    def _fake_request(_chunk_text: str, *, timeout_sec: float):
        assert timeout_sec == 1.0
        return {
            "records": [
                {
                    "waste_code": "1110700",
                    "waste_name": "Отходы зерновые 3 категории",
                    "object_name": "Объект",
                    "owner_name": "Собственник",
                    "user_address": "г. Минск",
                    "user_phone": None,
                    "object_id": 7,
                    "owner_address": None,
                    "owner_phone": None,
                    "accepts_from_others": False,
                }
            ]
        }

    monkeypatch.setattr("app.services.llm_fallback.service.request_openrouter_json", _fake_request)
    text = "1110700 Отходы\nОбъект 7\n---\n1110701 Другое\nОбъект 8"
    rows, stats = extract_records_with_llm_fallback(text, source_part=1, max_calls=1)
    assert len(rows) == 1
    assert rows[0]["id"] == 7
    assert stats["calls"] == 1
    assert stats["accepted"] == 1
