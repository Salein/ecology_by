from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from app.services import user_registry_cache as cache


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return [type("Row", (), {"_mapping": r}) for r in self._rows]


class _FakeSession:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.last_stmt: Any = None

    def execute(self, stmt: Any) -> _FakeResult:
        self.last_stmt = stmt
        return _FakeResult(self._rows)


def _fake_scope(session: _FakeSession):
    @contextmanager
    def _scope():
        yield session

    return _scope


def test_load_search_records_prefilter_builds_expected_sql(monkeypatch) -> None:
    rows = [
        {
            "pk": 10,
            "source_part": 2,
            "record_id": 123,
            "owner": "ОАО Тест",
            "object_name": "Установка",
            "waste_code": "3141204",
            "waste_type_name": "Отход",
            "accepts_external_waste": True,
            "address": "г. Минск",
            "phones": "+375291112233",
            "lat": 53.9,
            "lon": 27.56,
        }
    ]
    fake = _FakeSession(rows)
    monkeypatch.setattr(cache, "session_scope", _fake_scope(fake))

    out = cache.load_search_records_prefilter(
        waste_code="3141204",
        record_id=123,
        accepts_external_only=True,
        repair_addresses=False,
    )

    sql = str(fake.last_stmt)
    assert "registry_records.waste_code" in sql
    assert "registry_records.record_id" in sql
    assert "registry_records.accepts_external_waste" in sql
    assert len(out) == 1
    assert out[0]["id"] == 123
    assert out[0]["waste_code"] == "3141204"
    assert out[0]["accepts_external_waste"] is True


def test_load_search_records_text_prefilter_maps_rows_without_payload(monkeypatch) -> None:
    rows = [
        {
            "pk": 44,
            "source_part": 1,
            "record_id": None,
            "owner": None,
            "object_name": None,
            "waste_code": None,
            "waste_type_name": None,
            "accepts_external_waste": False,
            "address": None,
            "phones": None,
            "lat": None,
            "lon": None,
        }
    ]
    fake = _FakeSession(rows)
    monkeypatch.setattr(cache, "session_scope", _fake_scope(fake))

    out = cache.load_search_records_text_prefilter(
        query="минск",
        accepts_external_only=True,
        limit=100,
        repair_addresses=False,
    )

    sql = str(fake.last_stmt).lower()
    assert "like" in sql
    assert "accepts_external_waste" in sql
    assert len(out) == 1
    # Fallback id from pk if record_id is missing.
    assert out[0]["id"] == 44
    assert out[0]["owner"] == ""
    assert out[0]["object_name"] == ""
    assert out[0]["accepts_external_waste"] is False
