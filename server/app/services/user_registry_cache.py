from __future__ import annotations

import hashlib
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pdfplumber
from app.services.registry_record_parser import repair_registry_address

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


_POSTAL_CITY_RE = re.compile(r"\b(\d{6})\b[\s,;:\-–—]{0,40}\bг\.\s*([А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+(?:\s+[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+){0,2})")


def _build_postal_city_map(rows: list[dict[str, Any]]) -> dict[str, str]:
    """
    Извлекает вероятный город по индексу на основе всех текстов карточек.
    Если по индексу встречается несколько городов с сопоставимой частотой, индекс пропускаем.
    """
    stats: dict[str, dict[str, int]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        texts = [
            str(row.get("address") or ""),
            str(row.get("owner") or ""),
            str(row.get("object_name") or ""),
        ]
        for text in texts:
            t = text.replace("\xa0", " ")
            for m in _POSTAL_CITY_RE.finditer(t):
                postal = m.group(1)
                city = re.sub(r"[,\s]+$", "", m.group(2)).strip()
                if len(city) < 2:
                    continue
                by_city = stats.setdefault(postal, {})
                by_city[city] = by_city.get(city, 0) + 1

    out: dict[str, str] = {}
    for postal, by_city in stats.items():
        if not by_city:
            continue
        ranked = sorted(by_city.items(), key=lambda x: x[1], reverse=True)
        best_city, best_count = ranked[0]
        second_count = ranked[1][1] if len(ranked) > 1 else 0
        # Берём город только если он уверенно доминирует по этому индексу.
        if best_count >= 2 and best_count >= second_count + 2:
            out[postal] = best_city
    return out


def _repair_truncated_city_suffix(address: str, postal_to_city: dict[str, str]) -> str:
    compact = re.sub(r"\s+", " ", (address or "").replace("\xa0", " ")).strip()
    if not compact:
        return compact
    if not re.search(r"(?:,\s*|\s+)г\.\s*$", compact, flags=re.IGNORECASE):
        return compact
    pm = re.search(r"\b(\d{6})\b", compact)
    if not pm:
        return re.sub(r"(?:,\s*|\s+)г\.\s*$", "", compact, flags=re.IGNORECASE).strip()
    postal = pm.group(1)
    city = postal_to_city.get(postal)
    if not city:
        return re.sub(r"(?:,\s*|\s+)г\.\s*$", "", compact, flags=re.IGNORECASE).strip()
    base = re.sub(r"(?:,\s*|\s+)г\.\s*$", "", compact, flags=re.IGNORECASE).strip().rstrip(",")
    return f"{base}, г. {city}"


def load_cached_registry_records() -> list[dict[str, Any]]:
    data = _load_json(USER_CACHE_PATH)
    if not data or not isinstance(data.get("records"), list):
        return []
    rows = dedupe_registry_records_by_id(list(data["records"]))
    postal_to_city = _build_postal_city_map(rows)
    # Мягкая починка старого кэша: исправляем явно битые адресные хвосты.
    for row in rows:
        if not isinstance(row, dict):
            continue
        addr = str(row.get("address") or "").strip()
        if not addr:
            continue
        owner = str(row.get("owner") or "")
        obj = str(row.get("object_name") or "")
        repaired = repair_registry_address(addr, owner, obj)
        row["address"] = _repair_truncated_city_suffix(repaired, postal_to_city)
    return rows


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
