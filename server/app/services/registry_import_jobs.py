from __future__ import annotations

import hashlib
import threading
import time
import uuid
from typing import Any

import httpx

from app.config import settings
from app.services.belarus_locality_centroids import approx_coords_from_by_text
from app.services.nominatim import forward_geocode_sync
from app.services.registry_record_parser import parse_registry_plain_text
from app.services.user_registry_cache import (
    extract_pdf_text_from_bytes,
    fingerprint_from_sha256_digests,
    load_cached_registry_records,
    load_geocode_cache,
    load_import_sources_detail,
    registry_row_dedupe_key,
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
    _router_fingerprint: str,
) -> None:
    """Фоновая задача: парсинг PDF и геокодирование с обновлением progress."""
    geocache: dict[str, dict[str, float]] = {}
    recs: list[dict[str, Any]] | None = None
    names_for_save: list[str] | None = None
    import_detail: list[dict[str, Any]] | None = None
    combined_sig: str | None = None
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
        parsed_recs: list[dict[str, Any]] = []
        for name, part, text in all_texts:
            parsed_recs.extend(parse_registry_plain_text(text, part))

        merge_hint = ""
        if len(files) == 1:
            fn, raw0 = files[0]
            part_guess = _guess_part(fn, 0)
            h = hashlib.sha256(raw0).hexdigest()
            prev_detail = load_import_sources_detail()
            existing_rows = load_cached_registry_records()
            kept_other = [r for r in existing_rows if int(r.get("source_part") or 0) != part_guess]
            same_part_rows = [r for r in existing_rows if int(r.get("source_part") or 0) == part_guess]
            keys_existing = {registry_row_dedupe_key(r) for r in same_part_rows}
            new_from_pdf = [r for r in parsed_recs if registry_row_dedupe_key(r) not in keys_existing]
            skipped_same = len(parsed_recs) - len(new_from_pdf)
            recs = kept_other + same_part_rows + new_from_pdf
            merge_hint = f" Новых из PDF: {len(new_from_pdf)}, уже в БД (часть {part_guess}): {skipped_same}."
            if prev_detail:
                od = [m for m in prev_detail if int(m.get("part") or 0) != part_guess]
                import_detail = od + [{"sha256": h, "part": part_guess, "name": fn}]
                import_detail.sort(
                    key=lambda m: (int(m.get("part") or 0), str(m.get("name") or "")),
                )
                other_names = [str(m.get("name") or "") for m in od if m.get("name")]
                names_for_save = sorted(set(other_names + [fn]))
            else:
                import_detail = [{"sha256": h, "part": part_guess, "name": fn}]
                names_for_save = [fn]
            combined_sig = fingerprint_from_sha256_digests(m["sha256"] for m in import_detail)
        else:
            recs = parsed_recs
            names_for_save = [n for n, _ in files]
            import_detail = [
                {
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "part": _guess_part(n, i),
                    "name": n,
                }
                for i, (n, raw) in enumerate(files)
            ]
            import_detail.sort(
                key=lambda m: (int(m.get("part") or 0), str(m.get("name") or "")),
            )
            combined_sig = fingerprint_from_sha256_digests(m["sha256"] for m in import_detail)

        _set_job(
            job_id,
            progress=30,
            message=f"Найдено записей: {len(recs)}.{merge_hint} Геокодирование…",
            records_count=len(recs),
        )

        geocache = load_geocode_cache()
        delay = max(0.0, float(settings.registry_geocode_delay_sec))
        checkpoint_every = max(1, settings.registry_import_checkpoint_every)
        n = len(recs)
        geo_headers = {"User-Agent": settings.nominatim_user_agent}

        with httpx.Client(timeout=settings.nominatim_timeout_sec, headers=geo_headers) as nominatim_client:
            for idx, r in enumerate(recs):
                # При merge: строки «другой» части уже с координатами из БД — не дергаем Nominatim повторно.
                if r.get("lat") is not None and r.get("lon") is not None:
                    pass
                else:
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
                            oname = str(r.get("object_name") or "").strip()
                            ap = approx_coords_from_by_text(addr, oname)
                            if ap:
                                lat, lon = float(ap[0]), float(ap[1])
                                geocache[key] = {"lat": lat, "lon": lon}
                                r["lat"] = lat
                                r["lon"] = lon
                            else:
                                t0 = time.perf_counter()
                                try:
                                    pair = forward_geocode_sync(addr, client=nominatim_client)
                                except Exception:
                                    pair = None
                                elapsed = time.perf_counter() - t0
                                rest = max(0.0, delay - elapsed)
                                if rest > 0:
                                    time.sleep(rest)
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

                # Периодический чекпоинт: сохраняем уже обработанную часть реестра и geocode_cache.
                # Если сервис упадёт, в БД останется прогресс на момент последнего чекпоинта.
                done = idx + 1
                if done % checkpoint_every == 0 or done == n:
                    save_geocode_cache(geocache)
                    save_user_registry_cache(
                        names_for_save,
                        recs[:done],
                        combined_sig,
                        import_sources_detail=import_detail,
                    )
                    _set_job(
                        job_id,
                        message=f"Геокодирование: {done}/{n} (чекпоинт сохранён)",
                        records_count=done,
                    )

        # Финальная фиксация (полный реестр).
        save_geocode_cache(geocache)
        save_user_registry_cache(
            names_for_save,
            recs,
            combined_sig,
            import_sources_detail=import_detail,
        )

        _set_job(
            job_id,
            status="done",
            progress=100,
            message="Реестр сохранён в кэш",
            error=None,
            records_count=len(recs),
        )
    except Exception as e:
        # Даже при ошибке стараемся зафиксировать geocode_cache с уже найденными координатами.
        try:
            if geocache:
                save_geocode_cache(geocache)
        except Exception:
            pass
        # Сохраняем реестр как есть в памяти (после парсинга и частичного геокодирования).
        partial_note = ""
        try:
            if (
                recs is not None
                and names_for_save is not None
                and combined_sig is not None
                and len(recs) > 0
            ):
                save_user_registry_cache(
                    names_for_save,
                    recs,
                    combined_sig,
                    import_sources_detail=import_detail,
                )
                partial_note = f" Сохранён прогресс: {len(recs)} запис(ей) (координаты — по мере обработки)."
        except Exception:
            pass
        _set_job(
            job_id,
            status="error",
            progress=0,
            message="Ошибка" + partial_note,
            error=str(e),
        )
