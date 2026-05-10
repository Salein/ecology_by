"""Метрики качества парсинга и флаги review."""
from __future__ import annotations

import re
from typing import Any

from app.core.config import settings

from app.services.registry_import.geocode_filters import _ADDR_HINT_RE, _POSTAL_RE

def _collect_parse_quality(rows: list[dict[str, Any]]) -> dict[str, int]:
    stats = {
        "rows_total": len(rows),
        "owner_empty": 0,
        "address_empty": 0,
        "address_no_locality": 0,
        "phones_empty": 0,
        "object_placeholder": 0,
        "low_confidence": 0,
        "needs_review": 0,
    }
    for r in rows:
        owner = str(r.get("owner") or "").strip()
        addr = str(r.get("address") or "").strip()
        phones = str(r.get("phones") or "").strip()
        obj = str(r.get("object_name") or "").strip()
        if not owner:
            stats["owner_empty"] += 1
        if not addr:
            stats["address_empty"] += 1
        elif not _ADDR_HINT_RE.search(addr) and not _POSTAL_RE.search(addr):
            stats["address_no_locality"] += 1
        if not phones:
            stats["phones_empty"] += 1
        if obj in {"", "—", "-"}:
            stats["object_placeholder"] += 1
        try:
            conf = int(r.get("parse_confidence") or 0)
        except Exception:
            conf = 0
        if conf < 60:
            stats["low_confidence"] += 1
        if bool(r.get("needs_review")):
            stats["needs_review"] += 1
    return stats


def _parse_confidence_int(row: dict[str, Any]) -> int:
    try:
        return int(row.get("parse_confidence") or 0)
    except Exception:
        return 0


def _postal_city_mismatch(addr: str, postal_map: dict[str, str]) -> bool:
    m = _POSTAL_RE.search(addr or "")
    if not m:
        return False
    postal = m.group(0)
    city = postal_map.get(postal)
    if not city:
        return False
    return city.casefold() not in (addr or "").casefold()


def _waste_code_weak(row: dict[str, Any]) -> bool:
    wc = str(row.get("waste_code") or "").strip()
    if not wc:
        return True
    return not re.fullmatch(r"\d{7}", wc)


def _waste_type_weak(row: dict[str, Any]) -> bool:
    w = str(row.get("waste_type_name") or "").strip()
    return w in {"", "—", "-"} or len(w) < 3


def _parse_notes_suggest_llm(row: dict[str, Any]) -> bool:
    notes = row.get("parse_notes")
    if not isinstance(notes, list) or not notes:
        return False
    for n in notes:
        s = str(n)
        if "repair_pass_applied" in s:
            return True
        if "_alternative" in s:
            return True
        if "checkbox" in s.casefold() and ("missing" in s.casefold() or "uncertain" in s.casefold()):
            return True
    return False


def _needs_llm_repair(row: dict[str, Any], postal_map: dict[str, str]) -> bool:
    """Строка с ошибкой/пробелом парсера или сомнением — отправляем в LLM (все релевантные поля)."""
    owner = str(row.get("owner") or "").strip()
    phones = str(row.get("phones") or "").strip()
    addr = str(row.get("address") or "").strip()
    obj = str(row.get("object_name") or "").strip()
    if not owner:
        return True
    if not phones:
        return True
    if not addr:
        return True
    if obj in {"", "—", "-"}:
        return True
    if _waste_type_weak(row):
        return True
    if _waste_code_weak(row):
        return True
    thr = max(1, min(100, int(settings.registry_llm_repair_if_parse_confidence_below)))
    if _parse_confidence_int(row) < thr:
        return True
    if _parse_notes_suggest_llm(row):
        return True
    if addr and _postal_city_mismatch(addr, postal_map):
        return True
    if addr and not _ADDR_HINT_RE.search(addr) and not _POSTAL_RE.search(addr):
        return True
    if addr and _POSTAL_RE.search(addr) and not _ADDR_HINT_RE.search(addr):
        return True
    return False


def _checkbox_pdf_missing_for_row(row: dict[str, Any], accepts_by_part_obj: dict[tuple[int, int], bool]) -> bool:
    """По объекту не удалось прочитать чекбоксы на страницах PDF (нет ключа в карте извлечения)."""
    if not accepts_by_part_obj:
        return False
    try:
        part = int(row.get("source_part") or 0)
        oid = int(row.get("id") or 0)
    except (TypeError, ValueError):
        return False
    if oid <= 0:
        return False
    return (part, oid) not in accepts_by_part_obj


def _still_bad_for_review(
    row: dict[str, Any],
    postal_map: dict[str, str],
    accepts_by_part_obj: dict[tuple[int, int], bool] | None = None,
) -> bool:
    if _needs_llm_repair(row, postal_map):
        return True
    if accepts_by_part_obj and _checkbox_pdf_missing_for_row(row, accepts_by_part_obj):
        return True
    return False
