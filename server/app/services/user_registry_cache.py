from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pdfplumber

_DATA = Path(__file__).resolve().parent.parent / "data"
USER_CACHE_PATH = _DATA / "user_registry_cache.json"
GEOCODE_CACHE_PATH = _DATA / "geocode_cache.json"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Any:
    if not path.is_file():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def registry_files_fingerprint(files: list[tuple[str, bytes]]) -> str:
    """
    Отпечаток набора PDF по содержимому (SHA-256 каждого файла, без учёта имён и порядка выбора).
    Один и тот же набор байтов даёт тот же отпечаток.
    """
    digests = sorted(hashlib.sha256(data).hexdigest() for _, data in files)
    return hashlib.sha256("\n".join(digests).encode("utf-8")).hexdigest()


def save_user_registry_cache(
    sources: list[str],
    records: list[dict[str, Any]],
    source_signature: str,
) -> None:
    USER_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    records = dedupe_registry_records_by_id(records)
    payload = {
        "version": 2,
        "updated_at": _utc_iso(),
        "sources": sources,
        "source_signature": source_signature,
        "records": records,
    }
    tmp = USER_CACHE_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(USER_CACHE_PATH)


def dedupe_registry_records_by_id(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Первая запись на каждый id (дубликаты строк в PDF / при импорте)."""
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for row in records:
        if not isinstance(row, dict):
            continue
        try:
            rid = int(row["id"])
        except (KeyError, TypeError, ValueError):
            out.append(row)
            continue
        if rid in seen:
            continue
        seen.add(rid)
        out.append(row)
    return out


def load_cached_registry_records() -> list[dict[str, Any]]:
    data = _load_json(USER_CACHE_PATH)
    if not data or not isinstance(data.get("records"), list):
        return []
    return dedupe_registry_records_by_id(list(data["records"]))


def cache_meta() -> dict[str, Any] | None:
    data = _load_json(USER_CACHE_PATH)
    if not data:
        return None
    raw = data.get("records") or []
    recs = dedupe_registry_records_by_id(list(raw)) if isinstance(raw, list) else []
    return {
        "updated_at": data.get("updated_at"),
        "record_count": len(recs),
        "sources": data.get("sources") or [],
        "source_signature": data.get("source_signature"),
    }


def cached_registry_signature() -> str | None:
    data = _load_json(USER_CACHE_PATH)
    if not data:
        return None
    sig = data.get("source_signature")
    return str(sig) if sig else None


def load_geocode_cache() -> dict[str, dict[str, float]]:
    return _load_json(GEOCODE_CACHE_PATH) or {}


def save_geocode_cache(cache: dict[str, dict[str, float]]) -> None:
    GEOCODE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = GEOCODE_CACHE_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    tmp.replace(GEOCODE_CACHE_PATH)


def extract_pdf_text_from_bytes(
    data: bytes,
    page_progress: Callable[[int, int], None] | None = None,
) -> str:
    parts: list[str] = []
    bio = io.BytesIO(data)
    with pdfplumber.open(bio) as pdf:
        n = len(pdf.pages)
        for i in range(n):
            t = pdf.pages[i].extract_text() or ""
            if t.strip():
                parts.append(t)
            if page_progress:
                page_progress(i + 1, n)
    return "\n".join(parts)


def clear_user_registry_cache() -> None:
    if USER_CACHE_PATH.is_file():
        USER_CACHE_PATH.unlink()
