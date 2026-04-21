from __future__ import annotations

import logging
import re
import time
from typing import Any

from pydantic import ValidationError

from app.config import settings
from app.services.llm_fallback.chunking import split_into_record_chunks
from app.services.llm_fallback.client import LlmProviderError, request_openrouter_json
from app.services.llm_fallback.schemas import LlmExtractionBatch

logger = logging.getLogger(__name__)

_WASTE_CODE_RE = re.compile(r"^\d{7}$")


def _clean_text(v: object) -> str:
    return " ".join(str(v or "").replace("\xa0", " ").split()).strip()


def _normalize_phone_pair(user_phone: str, owner_phone: str) -> str | None:
    items = [_clean_text(user_phone), _clean_text(owner_phone)]
    uniq: list[str] = []
    seen: set[str] = set()
    for it in items:
        if not it:
            continue
        key = it.casefold()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    if not uniq:
        return None
    return " ; ".join(uniq)


def validate_llm_rows(rows: list[dict[str, Any]], source_part: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        wc = _clean_text(row.get("waste_code"))
        if not _WASTE_CODE_RE.fullmatch(wc):
            continue
        try:
            obj_id = int(row.get("object_id"))
        except (TypeError, ValueError):
            continue
        if obj_id < 1 or obj_id > 999999:
            continue

        waste_name = _clean_text(row.get("waste_name"))
        object_name = _clean_text(row.get("object_name"))
        owner_name = _clean_text(row.get("owner_name"))
        address = _clean_text(row.get("owner_address")) or _clean_text(row.get("user_address")) or None
        phones = _normalize_phone_pair(_clean_text(row.get("user_phone")), _clean_text(row.get("owner_phone")))
        accepts = row.get("accepts_from_others")
        accepts_flag = bool(accepts) if accepts is not None else True

        out.append(
            {
                "id": obj_id,
                "source_part": int(source_part),
                "waste_code": wc,
                "waste_type_name": waste_name or None,
                "object_name": object_name,
                "owner": owner_name,
                "address": address,
                "phones": phones,
                "accepts_external_waste": accepts_flag,
            }
        )
    return out


def should_run_llm_fallback(text: str, parsed_rows_count: int) -> bool:
    if not settings.llm_fallback_enabled:
        return False
    if parsed_rows_count > 0:
        return False
    t = _clean_text(text)
    # LLM имеет смысл только если текста заметно и в нем есть хотя бы косвенные якоря.
    if len(t) < 1500:
        return False
    return "объект" in t.casefold() and bool(re.search(r"\d{7}", t))


def extract_records_with_llm_fallback(
    text: str,
    *,
    source_part: int,
    max_calls: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    stats = {
        "calls": 0,
        "success": 0,
        "fail": 0,
        "accepted": 0,
        "rejected": 0,
    }
    if max_calls <= 0:
        return [], stats

    chunks = split_into_record_chunks(text, records_per_chunk=settings.llm_fallback_chunk_records)
    if not chunks:
        return [], stats
    chunks = chunks[: max_calls]
    out: list[dict[str, Any]] = []

    for chunk in chunks:
        if stats["calls"] >= max_calls:
            break
        stats["calls"] += 1
        payload: dict[str, Any] | None = None
        for attempt in range(max(1, settings.llm_fallback_max_retries)):
            try:
                payload = request_openrouter_json(chunk, timeout_sec=settings.llm_fallback_timeout_sec)
                break
            except LlmProviderError as e:
                msg = str(e).lower()
                if "http 429" in msg and attempt + 1 < settings.llm_fallback_max_retries:
                    time.sleep(min(20.0, 5.0 * (attempt + 1)))
                    continue
                logger.warning("llm fallback chunk failed: %s", e)
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("llm fallback unexpected error: %s", e)
            payload = None
            break

        if not payload:
            stats["fail"] += 1
            continue
        try:
            parsed = LlmExtractionBatch(**payload)
            rows = [r.model_dump() for r in parsed.records]
        except ValidationError:
            stats["fail"] += 1
            continue
        valid = validate_llm_rows(rows, source_part)
        stats["success"] += 1
        stats["accepted"] += len(valid)
        stats["rejected"] += max(0, len(rows) - len(valid))
        out.extend(valid)

    return out, stats
