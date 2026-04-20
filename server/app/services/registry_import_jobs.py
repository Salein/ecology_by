from __future__ import annotations

import hashlib
import itertools
import logging
import re
import threading
import time
import uuid
from typing import Any

import httpx

from app.config import settings
from app.services.belarus_locality_centroids import approx_coords_from_by_text
from app.services.nominatim import forward_geocode_sync
from app.services.registry_record_parser import iter_registry_plain_text
from app.services.user_registry_cache import (
    extract_pdf_text_from_bytes,
    extract_pdf_text_pdfplumber_bytes,
    fingerprint_from_sha256_digests,
    load_cached_registry_records,
    load_geocode_cache,
    load_import_sources_detail,
    registry_row_dedupe_key,
    save_geocode_cache,
    save_user_registry_cache,
)

logger = logging.getLogger(__name__)

_jobs_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}
_POSTAL_RE = re.compile(r"\b\d{6}\b")
_ADDR_HINT_RE = re.compile(
    r"\b(г\.|г/п|аг\.|д\.|дер\.|п\.|пос\.|поселок|городок|ул\.|улица|пер\.|просп\.|б-р|шоссе)\b",
    re.IGNORECASE,
)


def _is_address_geocode_candidate(addr: str) -> bool:
    """
    Быстрый фильтр адресов перед Nominatim:
    - отсеивает заведомо пустые/служебные строки;
    - пропускает только строки с признаками адреса (индекс/маркеры населённого пункта или улицы).
    """
    a = " ".join((addr or "").replace("\xa0", " ").split()).strip()
    if len(a) < 8:
        return False
    low = a.casefold()
    if low in {"—", "-", "не указан", "не указано", "адрес отсутствует"}:
        return False
    if "не указано" in low and not _POSTAL_RE.search(a):
        return False
    if _POSTAL_RE.search(a):
        return True
    return bool(_ADDR_HINT_RE.search(a))


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


def _extract_accepts_external_by_object_id(pdf_bytes: bytes) -> dict[int, bool]:
    """
    Извлекает флаг "принимает от других" из чекбоксов PDF:
    - колонка 1: "Использует собственные"
    - колонка 2: "Принимает от других"
    Вектора чекбоксов в реестре стабильно стоят в правой части страницы
    (x ~ 700 и x ~ 754 для landscape-страниц ecoinfo).
    """
    try:
        import fitz
    except Exception:
        return {}

    out: dict[int, bool] = {}
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return {}

    try:
        for pi in range(doc.page_count):
            page = doc.load_page(pi)
            words = page.get_text("words") or []
            if not words:
                continue

            object_rows: list[tuple[int, float]] = []
            for w in words:
                tok = str(w[4] or "").strip()
                if tok != "Объект":
                    continue
                y = float(w[1])
                x = float(w[0])
                candidates: list[tuple[float, int]] = []
                for w2 in words:
                    t2 = str(w2[4] or "").strip()
                    if not t2.isdigit():
                        continue
                    if not (1 <= len(t2) <= 6):
                        continue
                    if float(w2[0]) <= x + 10:
                        continue
                    if abs(float(w2[1]) - y) > 3.5:
                        continue
                    try:
                        val = int(t2)
                    except ValueError:
                        continue
                    # Номер объекта в реестре обычно в левой части строки.
                    if val < 1 or val > 999999:
                        continue
                    candidates.append((float(w2[0]), val))
                # В части II ID часто вынесен на отдельную строку чуть выше метки "Объект".
                # Если на той же строке ID нет — ищем ближайший короткий numeric-token сверху.
                if not candidates:
                    vertical: list[tuple[float, float, int]] = []
                    for w2 in words:
                        t2 = str(w2[4] or "").strip()
                        if not t2.isdigit() or not (1 <= len(t2) <= 6):
                            continue
                        yy = float(w2[1])
                        xx = float(w2[0])
                        if yy > y + 1.0:
                            continue
                        if y - yy > 90.0:
                            continue
                        if xx > 280.0:
                            continue
                        try:
                            val = int(t2)
                        except ValueError:
                            continue
                        if val < 1 or val > 999999:
                            continue
                        vertical.append((y - yy, xx, val))
                    if vertical:
                        vertical.sort(key=lambda item: (item[0], item[1]))
                        candidates.append((x + 1.0, int(vertical[0][2])))
                if not candidates:
                    continue
                candidates.sort(key=lambda item: item[0])
                object_rows.append((candidates[0][1], y))

            if not object_rows:
                continue

            drawings = page.get_drawings() or []
            marks: list[tuple[float, float]] = []
            for it in drawings:
                r = it.get("rect")
                if not r:
                    continue
                w = float(r.x1 - r.x0)
                h = float(r.y1 - r.y0)
                # Маркер "галочки" в этом PDF — stroke-элемент внутри квадрата (примерно 5x4).
                if it.get("type") != "s":
                    continue
                if not (2.0 <= w <= 7.2 and 2.0 <= h <= 7.2):
                    continue
                cx = float((r.x0 + r.x1) / 2.0)
                cy = float((r.y0 + r.y1) / 2.0)
                marks.append((cx, cy))

            for obj_id, y in object_rows:
                first_mark = False
                second_mark = False
                for cx, cy in marks:
                    if abs(cy - (y + 4.5)) > 7.0:
                        continue
                    if 697.0 <= cx <= 706.5:
                        first_mark = True
                    if 751.0 <= cx <= 760.5:
                        second_mark = True

                if not first_mark and not second_mark:
                    continue
                # При спорном случае (обе) считаем, что "принимает от других" отмечено.
                out[obj_id] = bool(second_mark)
    finally:
        doc.close()

    return out


def _set_job(job_id: str, **kwargs: Any) -> None:
    with _jobs_lock:
        cur = _jobs.setdefault(job_id, {})
        if kwargs and all(cur.get(k) == v for k, v in kwargs.items()):
            return
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
        metrics={},
    )
    return job_id


def run_registry_import_job(
    job_id: str,
    files: list[tuple[str, bytes]],
    _router_fingerprint: str,
) -> None:
    """Фоновая задача: парсинг PDF и геокодирование с обновлением progress."""
    import_t0 = time.perf_counter()
    extract_elapsed = 0.0
    parse_elapsed = 0.0
    checkbox_elapsed = 0.0
    merge_elapsed = 0.0
    geocache: dict[str, dict[str, float]] = {}
    geocache_dirty_keys: set[str] = set()
    recs: list[dict[str, Any]] | None = None
    names_for_save: list[str] | None = None
    import_detail: list[dict[str, Any]] | None = None
    combined_sig: str | None = None
    try:
        _set_job(job_id, status="parsing", progress=2, message="Извлечение текста из PDF…")
        total_files = max(len(files), 1)
        text_sizes: list[tuple[str, int]] = []
        any_big = False
        parsed_recs: list[dict[str, Any]] = []
        parsed_seen_keys: set[tuple[object, ...]] = set()

        def _append_unique_parsed(rows: Any) -> None:
            for row in rows:
                key = registry_row_dedupe_key(row)
                if key in parsed_seen_keys:
                    continue
                parsed_seen_keys.add(key)
                parsed_recs.append(row)

        for fi, (name, raw) in enumerate(files):
            part = _guess_part(name, fi)

            def page_prog(cur: int, tot: int, fi=fi, name=name) -> None:
                base = 2 + int(25 * (fi + cur / max(tot, 1)) / total_files)
                _set_job(
                    job_id,
                    progress=min(base, 27),
                    message=f"Файл «{name}»: страница {cur}/{tot}",
                )

            t_extract0 = time.perf_counter()
            text = extract_pdf_text_from_bytes(raw, page_progress=page_prog)
            extract_elapsed += time.perf_counter() - t_extract0
            tlen = len(text or "")
            text_sizes.append((name, tlen))
            any_big = any_big or tlen > 15_000
            logger.info(
                "registry import %s: extracted text chars=%s part=%s",
                name,
                tlen,
                part,
            )
            t_parse0 = time.perf_counter()
            _append_unique_parsed(iter_registry_plain_text(text, part))
            parse_elapsed += time.perf_counter() - t_parse0

        _set_job(job_id, progress=28, message="Разбор записей реестра…")
        logger.info("registry import: parsed record count=%s", len(parsed_recs))

        if not parsed_recs and (settings.registry_pdf_text_backend or "").strip().lower() != "pdfplumber":
            if any_big:
                _set_job(
                    job_id,
                    progress=14,
                    message="Записей нет — повторное извлечение текста (pdfplumber)…",
                )
                text_sizes = []
                parsed_recs = []
                parsed_seen_keys = set()
                for fi, (name, raw) in enumerate(files):
                    part = _guess_part(name, fi)

                    def page_prog_pb(cur: int, tot: int, fi=fi, name=name) -> None:
                        base = 2 + int(25 * (fi + cur / max(tot, 1)) / total_files)
                        _set_job(
                            job_id,
                            progress=min(base, 27),
                            message=f"Файл «{name}» (pdfplumber): страница {cur}/{tot}",
                        )

                    t_extract1 = time.perf_counter()
                    t2 = extract_pdf_text_pdfplumber_bytes(raw, page_progress=page_prog_pb)
                    extract_elapsed += time.perf_counter() - t_extract1
                    tlen2 = len(t2 or "")
                    text_sizes.append((name, tlen2))
                    logger.info(
                        "registry import %s (pdfplumber): extracted text chars=%s part=%s",
                        name,
                        tlen2,
                        part,
                    )
                    t_parse1 = time.perf_counter()
                    _append_unique_parsed(iter_registry_plain_text(t2, part))
                    parse_elapsed += time.perf_counter() - t_parse1
                logger.info("registry import after pdfplumber: parsed record count=%s", len(parsed_recs))

        t_checkbox0 = time.perf_counter()
        accepts_by_part_obj: dict[tuple[int, int], bool] = {}
        for fi, (_name, raw) in enumerate(files):
            part = _guess_part(_name, fi)
            local = _extract_accepts_external_by_object_id(raw)
            for obj_id, flag in local.items():
                accepts_by_part_obj[(part, int(obj_id))] = bool(flag)
        if accepts_by_part_obj:
            patched = 0
            for row in parsed_recs:
                try:
                    part = int(row.get("source_part") or 0)
                    obj_id = int(row.get("id") or 0)
                except (TypeError, ValueError):
                    continue
                key = (part, obj_id)
                if key not in accepts_by_part_obj:
                    continue
                row["accepts_external_waste"] = bool(accepts_by_part_obj[key])
                patched += 1
            logger.info(
                "registry import: accepts_external_waste patched from PDF checkboxes: %s rows",
                patched,
            )
        checkbox_elapsed += time.perf_counter() - t_checkbox0

        if not parsed_recs:
            sizes = ", ".join(f"{n}:{sz}" for n, sz in text_sizes)
            any_text = sum(sz for _, sz in text_sizes)
            alt_hint = ""
            if any_text > 20_000:
                alt_hint = (
                    " Текст извлечён; выполнялись запасной разбор по «Объект» и (если не pdfplumber) "
                    "повторное извлечение pdfplumber. При нуле записей проверьте, что в PDF есть "
                    "метки «Объект» и 7-значные коды ФККО."
                )
            _set_job(
                job_id,
                status="error",
                progress=0,
                message=(
                    "Парсер не нашёл ни одной записи (ожидаются строки с 7-значным кодом ФККО и «Объект …»). "
                    f"Длины текста по файлам: {sizes}. Проверьте PDF с текстовым слоем."
                    + alt_hint
                ),
                error="PARSE_ZERO_RECORDS",
                records_count=0,
            )
            return

        merge_hint = ""
        t_merge0 = time.perf_counter()
        if len(files) == 1:
            fn, raw0 = files[0]
            part_guess = _guess_part(fn, 0)
            h = hashlib.sha256(raw0).hexdigest()
            prev_detail = load_import_sources_detail()
            existing_rows = load_cached_registry_records(repair_addresses=False)
            kept_other: list[dict[str, Any]] = []
            existing_by_key: dict[tuple[object, ...], dict[str, Any]] = {}
            for old in existing_rows:
                if int(old.get("source_part") or 0) == part_guess:
                    existing_by_key[registry_row_dedupe_key(old)] = old
                else:
                    kept_other.append(old)

            replaced = 0
            carry_coords = 0
            merged_part_rows: list[dict[str, Any]] = []
            for r in parsed_recs:
                key = registry_row_dedupe_key(r)
                old = existing_by_key.get(key)
                if old is not None:
                    replaced += 1
                    # Сохраняем ранее найденные координаты, чтобы не геокодировать заново.
                    if r.get("lat") is None and old.get("lat") is not None:
                        r["lat"] = old.get("lat")
                        carry_coords += 1
                    if r.get("lon") is None and old.get("lon") is not None:
                        r["lon"] = old.get("lon")
                merged_part_rows.append(r)

            recs = kept_other + merged_part_rows
            merge_hint = (
                f" Обновлено по PDF (часть {part_guess}): {len(merged_part_rows)}"
                f" (заменено существующих: {replaced}, с переносом координат: {carry_coords})."
            )
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

        # Дедупликация один раз до геокодирования/чекпоинтов:
        # это снимает повторный O(n) dedupe в каждом save_user_registry_cache(...).
        seen_keys: set[tuple[object, ...]] = set()
        deduped_recs: list[dict[str, Any]] = []
        for r in recs:
            key = registry_row_dedupe_key(r)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped_recs.append(r)
        recs = deduped_recs
        merge_elapsed += time.perf_counter() - t_merge0

        _set_job(
            job_id,
            progress=30,
            message=f"Найдено записей: {len(recs)}.{merge_hint} Геокодирование…",
            records_count=len(recs),
        )

        geocache = load_geocode_cache()
        delay = max(0.0, float(settings.registry_geocode_delay_sec))
        checkpoint_every_base = max(1, settings.registry_import_checkpoint_every)
        db_checkpoint_every = max(1, settings.registry_import_db_checkpoint_every)
        db_checkpoint_max_sec = max(0.0, float(settings.registry_import_db_checkpoint_max_sec))
        checkpoint_max_sec = max(0.0, float(settings.registry_import_checkpoint_max_sec))
        n = len(recs)
        max_checkpoints = max(1, int(settings.registry_import_max_checkpoints))
        adaptive_by_size = max(1, n // max_checkpoints) if n > 0 else 1
        checkpoint_every = max(checkpoint_every_base, adaptive_by_size)
        dynamic_db_checkpoint_every = db_checkpoint_every
        # Целевой интервал тяжёлого чекпоинта по скорости обработки (адаптивно пересчитывается).
        target_db_interval_sec = 60.0 if db_checkpoint_max_sec <= 0 else max(30.0, min(db_checkpoint_max_sec, 180.0))
        # Доп. порог прогресса между тяжёлыми snapshot'ами:
        # даже при низкой скорости не пишем full snapshot слишком часто.
        min_db_checkpoint_rows = max(checkpoint_every, min(2000, max(200, n // 40 if n > 0 else 1)))
        geo_headers = {"User-Agent": settings.nominatim_user_agent}
        # Не спамим UI обновлениями на каждой записи: ограничиваемся ~250 апдейтами за весь проход.
        progress_update_step = max(1, n // 250) if n > 0 else 1
        last_progress_sent = -1
        last_checkpoint_at = time.perf_counter()
        last_db_checkpoint_at = last_checkpoint_at
        last_db_checkpoint_done = 0
        geocode_stats = {
            "preset_coords": 0,       # координаты уже в записи
            "empty_addr": 0,          # адрес пустой
            "cache_hit": 0,           # попадание в geocode_cache
            "approx_hit": 0,          # локальный approx по адресу/НП
            "addr_skipped": 0,        # адрес отфильтрован как некандидат для Nominatim
            "cached_miss_skip": 0,    # адрес уже провалился в этом импорте (negative-cache)
            "nominatim_calls": 0,     # реальных внешних вызовов
            "nominatim_hit": 0,       # нашли координаты через Nominatim
            "nominatim_miss": 0,      # не нашли координаты через Nominatim
            "nominatim_budget_skip": 0,  # пропуски из-за soft-budget вызовов Nominatim
        }
        geocode_t0 = time.perf_counter()
        failed_geocode_keys: set[str] = set()
        approx_cache: dict[str, tuple[float, float] | None] = {}
        addr_candidate_cache: dict[str, bool] = {}
        addr_to_key_cache: dict[str, str] = {}
        nominatim_budget = max(0, int(settings.registry_import_geocode_max_calls))

        def _metrics_snapshot(done: int, now: float) -> dict[str, Any]:
            elapsed = max(0.001, now - geocode_t0)
            rows_per_sec = done / elapsed if done > 0 else 0.0
            remaining = max(0, n - done)
            eta_sec = int(remaining / rows_per_sec) if rows_per_sec > 0 else None
            return {
                "done": done,
                "total": n,
                "rows_per_sec": round(rows_per_sec, 2),
                "eta_sec": eta_sec,
                "nominatim_calls": geocode_stats["nominatim_calls"],
                "nominatim_hit": geocode_stats["nominatim_hit"],
                "nominatim_miss": geocode_stats["nominatim_miss"],
                "cache_hit": geocode_stats["cache_hit"],
                "approx_hit": geocode_stats["approx_hit"],
                "addr_skipped": geocode_stats["addr_skipped"],
                "cached_miss_skip": geocode_stats["cached_miss_skip"],
                "budget_skip": geocode_stats["nominatim_budget_skip"],
            }

        with httpx.Client(timeout=settings.nominatim_timeout_sec, headers=geo_headers) as nominatim_client:
            for idx, r in enumerate(recs):
                # При merge: строки «другой» части уже с координатами из БД — не дергаем Nominatim повторно.
                if r.get("lat") is not None and r.get("lon") is not None:
                    geocode_stats["preset_coords"] += 1
                else:
                    addr = (r.get("address") or "").strip()
                    if not addr:
                        geocode_stats["empty_addr"] += 1
                        r["lat"] = None
                        r["lon"] = None
                    else:
                        key = addr_to_key_cache.get(addr)
                        if key is None:
                            key = _normalize_addr_key(addr)
                            addr_to_key_cache[addr] = key
                        hit = geocache.get(key)
                        if hit and "lat" in hit and "lon" in hit:
                            geocode_stats["cache_hit"] += 1
                            r["lat"] = float(hit["lat"])
                            r["lon"] = float(hit["lon"])
                        elif key in failed_geocode_keys:
                            geocode_stats["cached_miss_skip"] += 1
                            r["lat"] = None
                            r["lon"] = None
                        else:
                            if key in approx_cache:
                                ap = approx_cache[key]
                            else:
                                oname = str(r.get("object_name") or "").strip()
                                ap = approx_coords_from_by_text(addr, oname)
                                approx_cache[key] = ap
                            if ap:
                                geocode_stats["approx_hit"] += 1
                                lat, lon = float(ap[0]), float(ap[1])
                                geocache[key] = {"lat": lat, "lon": lon}
                                geocache_dirty_keys.add(key)
                                r["lat"] = lat
                                r["lon"] = lon
                            elif not addr_candidate_cache.setdefault(key, _is_address_geocode_candidate(addr)):
                                # Не тратим сетевой вызов на заведомо нерелевантные адресные строки.
                                geocode_stats["addr_skipped"] += 1
                                failed_geocode_keys.add(key)
                                r["lat"] = None
                                r["lon"] = None
                            elif nominatim_budget > 0 and geocode_stats["nominatim_calls"] >= nominatim_budget:
                                # Soft-budget исчерпан: оставляем без координат, но не валим импорт.
                                geocode_stats["nominatim_budget_skip"] += 1
                                r["lat"] = None
                                r["lon"] = None
                            else:
                                geocode_stats["nominatim_calls"] += 1
                                t0 = time.perf_counter()
                                had_exc = False
                                try:
                                    pair = forward_geocode_sync(addr, client=nominatim_client)
                                except Exception:
                                    pair = None
                                    had_exc = True
                                elapsed = time.perf_counter() - t0
                                rest = max(0.0, delay - elapsed)
                                if rest > 0:
                                    time.sleep(rest)
                                if pair:
                                    geocode_stats["nominatim_hit"] += 1
                                    lat, lon = pair
                                    geocache[key] = {"lat": lat, "lon": lon}
                                    geocache_dirty_keys.add(key)
                                    r["lat"] = lat
                                    r["lon"] = lon
                                else:
                                    geocode_stats["nominatim_miss"] += 1
                                    # Negative-cache только для "чистого" miss без исключения.
                                    # При transient-ошибках сети допускаем повтор для дубликатов адреса.
                                    if not had_exc:
                                        failed_geocode_keys.add(key)
                                    r["lat"] = None
                                    r["lon"] = None

                pct = 30 + int(69 * (idx + 1) / max(n, 1))
                done = idx + 1
                if done == n or done % progress_update_step == 0:
                    pct = min(pct, 99)
                    if pct != last_progress_sent:
                        now = time.perf_counter()
                        _set_job(
                            job_id,
                            progress=pct,
                            message=f"Геокодирование: {done}/{n}",
                            metrics=_metrics_snapshot(done, now),
                        )
                        last_progress_sent = pct

                # Периодический чекпоинт: сохраняем уже обработанную часть реестра и geocode_cache.
                # Если сервис упадёт, в БД останется прогресс на момент последнего чекпоинта.
                now = time.perf_counter()
                checkpoint_by_count = done % checkpoint_every == 0
                checkpoint_by_time = checkpoint_max_sec > 0 and (now - last_checkpoint_at) >= checkpoint_max_sec
                if checkpoint_by_count or checkpoint_by_time or done == n:
                    # Подстройка частоты тяжёлых чекпоинтов под текущую скорость rows/sec.
                    elapsed_import = max(0.001, now - geocode_t0)
                    rows_per_sec = done / elapsed_import
                    suggested_db_every = int(rows_per_sec * target_db_interval_sec)
                    min_db_every = max(1, checkpoint_every)
                    max_db_every = max(min_db_every, n if n > 0 else min_db_every)
                    suggested_db_every = max(min_db_every, min(max_db_every, suggested_db_every))
                    # Сглаживаем изменения, чтобы шаг не "дёргался".
                    dynamic_db_checkpoint_every = max(
                        min_db_every,
                        int(dynamic_db_checkpoint_every * 0.7 + suggested_db_every * 0.3),
                    )

                    checkpoint_saved = False
                    if geocache_dirty_keys:
                        save_geocode_cache(geocache, geocache_dirty_keys)
                        geocache_dirty_keys.clear()
                        checkpoint_saved = True
                    # Полный частичный snapshot реестра — дорогая операция, выполняем реже.
                    db_progress_step = max(1, dynamic_db_checkpoint_every, min_db_checkpoint_rows)
                    db_checkpoint_by_count = (done - last_db_checkpoint_done) >= db_progress_step
                    db_checkpoint_by_time = (
                        db_checkpoint_max_sec > 0 and (now - last_db_checkpoint_at) >= db_checkpoint_max_sec
                    )
                    if db_checkpoint_by_count or db_checkpoint_by_time or done == n:
                        save_user_registry_cache(
                            names_for_save,
                            itertools.islice(recs, done),
                            combined_sig,
                            import_sources_detail=import_detail,
                            assume_deduped=True,
                        )
                        last_db_checkpoint_at = now
                        last_db_checkpoint_done = done
                        checkpoint_saved = True
                    last_checkpoint_at = now
                    if checkpoint_saved:
                        _set_job(
                            job_id,
                            message=f"Геокодирование: {done}/{n} (чекпоинт сохранён)",
                            records_count=done,
                            metrics=_metrics_snapshot(done, now),
                        )

        # Финальная фиксация (полный реестр).
        if geocache_dirty_keys:
            save_geocode_cache(geocache, geocache_dirty_keys)
            geocache_dirty_keys.clear()
        save_user_registry_cache(
            names_for_save,
            recs,
            combined_sig,
            import_sources_detail=import_detail,
            assume_deduped=True,
        )
        geocode_elapsed = time.perf_counter() - geocode_t0
        logger.info(
            "registry import geocode stats: total=%s preset=%s empty_addr=%s cache=%s approx=%s "
            "skip=%s cached_miss_skip=%s budget_skip=%s nominatim_calls=%s hit=%s miss=%s elapsed=%.2fs",
            n,
            geocode_stats["preset_coords"],
            geocode_stats["empty_addr"],
            geocode_stats["cache_hit"],
            geocode_stats["approx_hit"],
            geocode_stats["addr_skipped"],
            geocode_stats["cached_miss_skip"],
            geocode_stats["nominatim_budget_skip"],
            geocode_stats["nominatim_calls"],
            geocode_stats["nominatim_hit"],
            geocode_stats["nominatim_miss"],
            geocode_elapsed,
        )
        logger.info(
            "registry import checkpoint policy: base_every=%s adaptive_by_size=%s effective_every=%s "
            "db_checkpoint_every(base=%s dynamic=%s min_rows=%s) max_sec=%.1f db_max_sec=%.1f target_db_interval=%.1f",
            checkpoint_every_base,
            adaptive_by_size,
            checkpoint_every,
            db_checkpoint_every,
            dynamic_db_checkpoint_every,
            min_db_checkpoint_rows,
            checkpoint_max_sec,
            db_checkpoint_max_sec,
            target_db_interval_sec,
        )
        logger.info(
            "registry import stage timings: extract=%.2fs parse=%.2fs checkbox=%.2fs merge=%.2fs geocode=%.2fs total=%.2fs",
            extract_elapsed,
            parse_elapsed,
            checkbox_elapsed,
            merge_elapsed,
            geocode_elapsed,
            time.perf_counter() - import_t0,
        )

        _set_job(
            job_id,
            status="done",
            progress=100,
            message="Реестр сохранён в кэш",
            error=None,
            records_count=len(recs),
            metrics=_metrics_snapshot(len(recs), time.perf_counter()),
        )
    except Exception as e:
        # Даже при ошибке стараемся зафиксировать geocode_cache с уже найденными координатами.
        try:
            if geocache_dirty_keys:
                save_geocode_cache(geocache, geocache_dirty_keys)
                geocache_dirty_keys.clear()
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
                    assume_deduped=True,
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
