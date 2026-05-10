"""Слияние результатов LLM-repair (ветка сейчас отключена в job_runner)."""
from __future__ import annotations

from typing import Any

def _merge_llm_repair_into_seed(
    seed_batch: list[dict[str, Any]],
    llm_batch: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    llm_by_key: dict[tuple[int, str], dict[str, Any]] = {}
    for row in llm_batch:
        try:
            rid = int(row.get("id") or 0)
        except (TypeError, ValueError):
            rid = 0
        wcode = str(row.get("waste_code") or "").strip()
        if rid <= 0 or not wcode:
            continue
        llm_by_key[(rid, wcode)] = row

    merged: list[dict[str, Any]] = []
    llm_used = 0
    for seed in seed_batch:
        base = dict(seed)
        key = (int(base.get("id") or 0), str(base.get("waste_code") or "").strip())
        llm_row = llm_by_key.pop(key, None)
        if llm_row is None:
            merged.append(base)
            continue
        llm_used += 1
        for fld in (
            "owner",
            "object_name",
            "waste_type_name",
            "accepts_external_waste",
            "address",
            "phones",
            "parse_confidence",
            "parse_notes",
        ):
            if fld in llm_row and llm_row.get(fld) not in (None, ""):
                base[fld] = llm_row.get(fld)
        notes = [str(x) for x in (base.get("parse_notes") or []) if x]
        if "llm_repair_full" not in notes:
            notes.append("llm_repair_full")
        base["parse_notes"] = notes
        merged.append(base)
    return merged, llm_used


def _apply_row_dict_updates_inplace(batch: list[dict[str, Any]], merged: list[dict[str, Any]]) -> None:
    for i, mrow in enumerate(merged):
        if i >= len(batch):
            break
        batch[i].clear()
        batch[i].update(mrow)


_SELECTOR_NOTE_FIELDS: tuple[tuple[str, str], ...] = (
    ("owner", "owner_selected_"),
    ("object_name", "object_selected_"),
    ("phones", "phones_selected_"),
    ("address", "address_selected_"),
)


def _collect_selector_telemetry(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Агрегирует заметки repair-pass селекторов из parse_notes (см. registry_record_parser).
    Пишется в parse_quality_report в import_sources_detail для анализа импорта.
    """
    repair_rows = 0
    by_field: dict[str, dict[str, int]] = {
        name: {"primary": 0, "alternative": 0, "other": 0} for name, _ in _SELECTOR_NOTE_FIELDS
    }
    for r in rows:
        notes = r.get("parse_notes")
        if not isinstance(notes, list):
            continue
        str_notes = [str(n) for n in notes if n]
        if "repair_pass_applied" not in str_notes:
            continue
        repair_rows += 1
        for name, prefix in _SELECTOR_NOTE_FIELDS:
            for n in str_notes:
                if not n.startswith(prefix):
                    continue
                head = n.split("(", 1)[0]
                if "_alternative" in head:
                    by_field[name]["alternative"] += 1
                elif "_primary" in head:
                    by_field[name]["primary"] += 1
                else:
                    by_field[name]["other"] += 1
                break
    return {
        "repair_pass_rows": repair_rows,
        "rows_total": len(rows),
        "by_field": by_field,
    }
