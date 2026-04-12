from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from app.config import settings
from app.services.nominatim import forward_geocode_sync
from app.services.registry_record_parser import parse_registry_plain_text
from app.services.user_registry_cache import (
    extract_pdf_text_from_bytes,
    load_geocode_cache,
    save_geocode_cache,
    save_user_registry_cache,
)

_jobs_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}


def _normalize_addr_key(s: str) -> str:
    s = " ".join((s or "").replace("\xa0", " ").split()).casefold()
    return s[:280]


def _guess_part(filename: str, file_index: int) -> int:
    fn = filename.casefold().replace(" ", "")
    if "частьii" in fn or "часть2" in fn or "part2" in fn or fn.endswith("ii.pdf"):
        return 2
    if "ii)" in fn or "_ii." in fn or "-ii." in fn:
        return 2
    if file_index == 0:
        return 1
    return 2


def _set_job(job_id: str, **kwargs: Any) -> None:
    with _jobs_lock:
        cur = _jobs.setdefault(job_id, {})
        cur.update(kwargs)


def get_job(job_id: str) -> dict[str, Any] | None:
    with _jobs_lock:
        j = _jobs.get(job_id)
        return dict(j) if j else None


def create_job() -> str:
    job_id = uuid.uuid4().hex
    _set_job(
        job_id,
        status="queued",
        progress=0,
        message="В очереди…",
        error=None,
        records_count=0,
    )
    return job_id


def run_registry_import_job(
    job_id: str,
    files: list[tuple[str, bytes]],
    source_signature: str,
) -> None:
    """Фоновая задача: парсинг PDF и геокодирование с обновлением progress."""
    try:
        _set_job(job_id, status="parsing", progress=2, message="Извлечение текста из PDF…")
        all_texts: list[tuple[str, int, str]] = []
        total_files = max(len(files), 1)

        for fi, (name, raw) in enumerate(files):
            part = _guess_part(name, fi)

            def page_prog(cur: int, tot: int, fi=fi, name=name) -> None:
                base = 2 + int(25 * (fi + cur / max(tot, 1)) / total_files)
                _set_job(
                    job_id,
                    progress=min(base, 27),
                    message=f"Файл «{name}»: страница {cur}/{tot}",
                )

            text = extract_pdf_text_from_bytes(raw, page_progress=page_prog)
            all_texts.append((name, part, text))

        _set_job(job_id, progress=28, message="Разбор записей реестра…")
        recs: list[dict[str, Any]] = []
        for name, part, text in all_texts:
            recs.extend(parse_registry_plain_text(text, part))

        _set_job(
            job_id,
            progress=30,
            message=f"Найдено записей: {len(recs)}. Геокодирование…",
            records_count=len(recs),
        )

        geocache = load_geocode_cache()
        delay = settings.registry_geocode_delay_sec
        n = len(recs)

        for idx, r in enumerate(recs):
            addr = (r.get("address") or "").strip()
            if not addr:
                r["lat"] = None
                r["lon"] = None
            else:
                key = _normalize_addr_key(addr)
                hit = geocache.get(key)
                if hit and "lat" in hit and "lon" in hit:
                    r["lat"] = float(hit["lat"])
                    r["lon"] = float(hit["lon"])
                else:
                    try:
                        pair = forward_geocode_sync(addr)
                    except Exception:
                        pair = None
                    time.sleep(delay)
                    if pair:
                        lat, lon = pair
                        geocache[key] = {"lat": lat, "lon": lon}
                        r["lat"] = lat
                        r["lon"] = lon
                    else:
                        r["lat"] = None
                        r["lon"] = None

            pct = 30 + int(69 * (idx + 1) / max(n, 1))
            _set_job(
                job_id,
                progress=min(pct, 99),
                message=f"Геокодирование: {idx + 1}/{n}",
            )

        save_geocode_cache(geocache)
        names = [n for n, _ in files]
        save_user_registry_cache(names, recs, source_signature)

        _set_job(
            job_id,
            status="done",
            progress=100,
            message="Реестр сохранён в кэш",
            error=None,
            records_count=len(recs),
        )
    except Exception as e:
        _set_job(
            job_id,
            status="error",
            progress=0,
            message="Ошибка",
            error=str(e),
        )
