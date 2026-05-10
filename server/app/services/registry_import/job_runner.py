"""Основной цикл импорта реестра (извлечение, парсинг, merge, геокодирование)."""
from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any

import httpx

from app.core.config import settings
from app.services.belarus_locality_centroids import approx_coords_from_by_text
from app.services.nominatim import forward_geocode_sync
from app.services.registry_import.constants import PARSER_REPORT_VERSION
from app.services.registry_import.geocode_filters import (
    _ADDR_HINT_RE,
    _POSTAL_RE,
    _is_address_geocode_candidate,
    _normalize_addr_key,
)
from app.services.registry_import.llm_row_merge import (
    _apply_row_dict_updates_inplace,
    _collect_selector_telemetry,
    _merge_llm_repair_into_seed,
)
from app.services.registry_import.ocr import (
    _extract_accepts_external_from_ocr_text,
    _extract_text_from_image_bytes,
)
from app.services.registry_import.parse_row_quality import (
    _checkbox_pdf_missing_for_row,
    _collect_parse_quality,
    _needs_llm_repair,
    _still_bad_for_review,
)
from app.services.registry_import.pdf_part import (
    _extract_accepts_external_by_object_id,
    _extract_text_from_html_or_txt_bytes,
    _guess_part,
)
from app.services.registry_import.queue import _set_job
from app.services.registry_record_parser import iter_registry_plain_text, preprocess_registry_plaintext
from app.services.user_registry_cache import (
    apply_registry_address_repairs_inplace,
    extract_pdf_text_from_bytes,
    extract_pdf_text_pdfplumber_bytes,
    fingerprint_from_sha256_digests,
    load_cached_registry_records,
    load_geocode_cache,
    load_import_sources_detail,
    registry_postal_city_consensus,
    registry_row_dedupe_key,
    save_geocode_cache,
    save_geocode_checkpoint_progress,
    save_user_registry_cache,
)

logger = logging.getLogger(__name__)

def run_registry_import_job(
    job_id: str,
    files: list[tuple[str, bytes]],
    _router_fingerprint: str,
    import_mode: str = "replace",
) -> None:
    """Фоновая задача: парсинг PDF и геокодирование с обновлением progress."""
    import_t0 = time.perf_counter()
    log = logging.LoggerAdapter(logger, {"job_id": job_id})
    extract_elapsed = 0.0
    parse_elapsed = 0.0
    checkbox_elapsed = 0.0
    merge_elapsed = 0.0
    geocache: dict[str, dict[str, float]] = {}
    geocache_dirty_keys: set[str] = set()
    geocache_flushes = 0
    db_snapshots = 0
    checkpoint_events = 0
    parse_quality = {
        "rows_total": 0,
        "owner_empty": 0,
        "address_empty": 0,
        "address_no_locality": 0,
        "phones_empty": 0,
        "object_placeholder": 0,
        "low_confidence": 0,
        "needs_review": 0,
    }
    selector_telemetry: dict[str, Any] = {}
    llm_stats: dict[str, Any] = {
        "enabled": False,
        "used_files": 0,
        "rows": 0,
        "status": [],
        "selective_targets_total": 0,
        "post_checkbox": {"targets": 0, "rows_merged": 0, "batches": 0},
    }
    recs: list[dict[str, Any]] | None = None
    names_for_save: list[str] | None = None
    import_detail: list[dict[str, Any]] | None = None
    combined_sig: str | None = None
    ocr_executor: ThreadPoolExecutor | None = None
    try:
        _set_job(job_id, status="parsing", progress=2, message="Извлечение текста из PDF…")
        total_files = max(len(files), 1)
        text_sizes: list[tuple[str, int]] = []
        any_big = False
        parsed_recs: list[dict[str, Any]] = []
        parsed_seen_keys: set[tuple[object, ...]] = set()
        registry_plaintext_by_part: defaultdict[int, list[str]] = defaultdict(list)
        image_exts = {"jpg", "jpeg", "png", "webp", "bmp", "tif", "tiff"}
        image_indexes = {
            i
            for i, (n, _) in enumerate(files)
            if (n.rsplit(".", 1)[-1].lower() if "." in n else "") in image_exts
        }
        # Слишком агрессивный OCR-параллелизм может "забить" CPU и сделать API внешне недоступным.
        ocr_workers = min(2, max(1, (os.cpu_count() or 2) // 3))
        ocr_futures: dict[int, Future[str]] = {}
        if image_indexes:
            ocr_executor = ThreadPoolExecutor(max_workers=ocr_workers)
        ocr_done = 0

        def _ocr_inflight_count() -> int:
            return sum(1 for f in ocr_futures.values() if not f.done())

        def _submit_ocr(idx: int) -> None:
            if ocr_executor is None or idx in ocr_futures or idx not in image_indexes:
                return
            _name, _raw = files[idx]
            ocr_futures[idx] = ocr_executor.submit(_extract_text_from_image_bytes, _raw)

        def _prefetch_ocr(start_idx: int) -> None:
            if ocr_executor is None:
                return
            max_inflight = max(4, ocr_workers * 2)
            if len(ocr_futures) >= max_inflight:
                return
            for j in range(start_idx, len(files)):
                if len(ocr_futures) >= max_inflight:
                    break
                _submit_ocr(j)

        def _registry_plaintext_join(part: int) -> str:
            return "\n\n".join(registry_plaintext_by_part.get(part) or [])

        def _append_unique_parsed(rows: Any, *, tick: Callable[[int], None] | None = None) -> None:
            n = 0
            for row in rows:
                key = registry_row_dedupe_key(row)
                if key in parsed_seen_keys:
                    continue
                parsed_seen_keys.add(key)
                parsed_recs.append(row)
                n += 1
                if tick is not None and n > 0 and n % 4000 == 0:
                    tick(n)

        for fi, (name, raw) in enumerate(files):
            part = _guess_part(name, fi)
            file_extract_t0 = time.perf_counter()
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            _prefetch_ocr(fi)

            def page_prog(cur: int, tot: int, fi=fi, name=name) -> None:
                base = 2 + int(25 * (fi + cur / max(tot, 1)) / total_files)
                elapsed = max(0.001, time.perf_counter() - file_extract_t0)
                rate = cur / elapsed if cur > 0 else 0.0
                stage_eta = int((tot - cur) / rate) if rate > 0 else None
                _set_job(
                    job_id,
                    progress=min(base, 27),
                    message=f"Файл «{name}»: страница {cur}/{tot}",
                    metrics={
                        "stage": "extract",
                        "file_name": name,
                        "file_index": fi + 1,
                        "files_total": total_files,
                        "files_done": fi,
                        "ocr_total": len(image_indexes),
                        "ocr_done": ocr_done,
                        "ocr_inflight": _ocr_inflight_count(),
                        "ocr_workers": ocr_workers,
                        "page": cur,
                        "pages_total": tot,
                        "parsed_records": len(parsed_recs),
                        "stage_done": cur,
                        "stage_total": tot,
                        "stage_unit": "pages",
                        "stage_eta_sec": stage_eta,
                    },
                )

            t_extract0 = time.perf_counter()
            if ext == "pdf":
                text = extract_pdf_text_from_bytes(raw, page_progress=page_prog)
            elif ext in {"jpg", "jpeg", "png", "webp", "bmp", "tif", "tiff"}:
                fut = ocr_futures.pop(fi, None)
                if fut is None:
                    _submit_ocr(fi)
                    fut = ocr_futures.pop(fi)
                try:
                    text = fut.result(timeout=180)
                except FutureTimeoutError as e:
                    raise RuntimeError(f"OCR таймаут для файла {name!r} (>{180} сек)") from e
                _set_job(
                    job_id,
                    progress=min(27, 2 + int(25 * (fi + 1) / total_files)),
                    message=f"Файл «{name}»: OCR изображения завершён",
                    metrics={
                        "stage": "ocr",
                        "file_name": name,
                        "file_index": fi + 1,
                        "files_total": total_files,
                        "files_done": fi,
                        "ocr_total": len(image_indexes),
                        "ocr_done": ocr_done,
                        "ocr_inflight": _ocr_inflight_count(),
                        "ocr_workers": ocr_workers,
                        "stage_done": fi + 1,
                        "stage_total": total_files,
                        "stage_unit": "files",
                    },
                )
            elif ext in {"html", "htm", "txt"}:
                text = _extract_text_from_html_or_txt_bytes(raw)
                _set_job(
                    job_id,
                    progress=min(27, 2 + int(25 * (fi + 1) / total_files)),
                    message=f"Файл «{name}»: извлечение текста из {ext.upper()} завершено",
                    metrics={
                        "stage": "extract",
                        "file_name": name,
                        "file_index": fi + 1,
                        "files_total": total_files,
                        "files_done": fi,
                        "ocr_total": len(image_indexes),
                        "ocr_done": ocr_done,
                        "ocr_inflight": _ocr_inflight_count(),
                        "ocr_workers": ocr_workers,
                        "stage_done": fi + 1,
                        "stage_total": total_files,
                        "stage_unit": "files",
                    },
                )
            else:
                raise ValueError(f"Неподдерживаемый формат файла: {name}")
            if ext in image_exts:
                ocr_done += 1
            _prefetch_ocr(fi + 1)
            extract_elapsed += time.perf_counter() - t_extract0
            tlen = len(text or "")
            text_sizes.append((name, tlen))
            any_big = any_big or tlen > 15_000
            log.info(
                "registry import %s: extracted text chars=%s part=%s",
                name,
                tlen,
                part,
            )
            _set_job(
                job_id,
                progress=27,
                message=f"Файл «{name}»: нормализация текста ({tlen} симв., 1–5 мин для очень больших частей)…",
            )
            t_norm0 = time.perf_counter()
            text = preprocess_registry_plaintext(text)
            registry_plaintext_by_part[part].append(f"### PDF:{name}\n{text}")
            log.info(
                "registry import %s: plaintext preprocess done in %.2fs",
                name,
                time.perf_counter() - t_norm0,
            )
            before_parse = len(parsed_recs)
            t_parse0 = time.perf_counter()
            seed_rows = list(iter_registry_plain_text(text, part, text_preprocessed=True))
            batch_size = 20
            file_sha = hashlib.sha256(raw).hexdigest()
            working = [dict(r) for r in seed_rows]
            apply_registry_address_repairs_inplace(working)
            postal_for_flags = registry_postal_city_consensus(working)
            if ext in image_exts and working:
                # Для импортов из изображений пытаемся восстановить checkbox-колонку из OCR-текста.
                # Это менее надёжно, чем PDF-вектор, поэтому применяем только уверенные совпадения.
                ocr_accepts = _extract_accepts_external_from_ocr_text(text)
                if ocr_accepts:
                    patched_img = 0
                    for r in working:
                        try:
                            oid = int(r.get("id") or 0)
                        except (TypeError, ValueError):
                            continue
                        if oid <= 0 or oid not in ocr_accepts:
                            continue
                        r["accepts_external_waste"] = bool(ocr_accepts[oid])
                        patched_img += 1
                    if patched_img > 0:
                        log.info(
                            "registry import %s: accepts_external_waste inferred from OCR for %s rows",
                            name,
                            patched_img,
                        )

            if False and working:
                all_source_names = [n for n, _ in files]
                repair_targets = [r for r in working if _needs_llm_repair(r, postal_for_flags)]
                llm_stats["selective_targets_total"] = int(llm_stats.get("selective_targets_total") or 0) + len(
                    repair_targets
                )
                repair_plan: list[list[dict[str, Any]]] = [
                    repair_targets[i : i + batch_size] for i in range(0, len(repair_targets), batch_size)
                ]
                total_rb = len(repair_plan)
                llm_used_total = 0
                llm_rows_raw = 0
                llm_batch_statuses: list[str] = []

                parsed_recs.extend(working)
                if total_rb == 0:
                    llm_batch_statuses.append("selective_skip:all_rows_ok")
                    pm_end = registry_postal_city_consensus(working)
                    for r in working:
                        r["needs_review"] = bool(_still_bad_for_review(r, pm_end))
                    save_user_registry_cache(
                        all_source_names,
                        parsed_recs,
                        _router_fingerprint,
                        import_sources_detail=[
                            {
                                "sha256": file_sha,
                                "part": part,
                                "name": name,
                                "parse_quality_report": {
                                    "version": PARSER_REPORT_VERSION,
                                    "stats": {"rows_total": len(parsed_recs)},
                                },
                            }
                        ],
                        assume_deduped=True,
                    )
                    db_snapshots += 1
                else:
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        llm_stage_t0 = time.perf_counter()
                        future: Future[tuple[list[dict[str, Any]], str]] | None = None
                        for bi, batch in enumerate(repair_plan):
                            part_batch = int(batch[0].get("source_part") or part)
                            if future is None:
                                future = executor.submit(
                                    repair_registry_records_with_llm,
                                    batch,
                                    part_batch,
                                    batch_index=bi + 1,
                                    total_batches=total_rb,
                                    repair_kind="full",
                                    registry_plaintext=text,
                                )
                            next_future: Future[tuple[list[dict[str, Any]], str]] | None = None
                            if bi + 1 < total_rb:
                                nb = repair_plan[bi + 1]
                                next_part = int(nb[0].get("source_part") or part)
                                next_future = executor.submit(
                                    repair_registry_records_with_llm,
                                    nb,
                                    next_part,
                                    batch_index=bi + 2,
                                    total_batches=total_rb,
                                    repair_kind="full",
                                    registry_plaintext=text,
                                )
                            llm_batch_rows, llm_status = future.result()
                            coverage_pct = int(round((len(llm_batch_rows) * 100.0) / max(1, len(batch))))
                            merged_batch, llm_used = _merge_llm_repair_into_seed(batch, llm_batch_rows)
                            _apply_row_dict_updates_inplace(batch, merged_batch)
                            llm_rows_raw += len(llm_batch_rows)
                            llm_used_total += llm_used
                            llm_batch_statuses.append(f"full:{llm_status}:{coverage_pct}%")
                            _set_job(
                                job_id,
                                progress=27,
                                message=(
                                    f"Файл «{name}»: LLM-repair {bi + 1}/{total_rb} "
                                    f"(поля), записей {len(parsed_recs)} — {llm_status}"
                                ),
                                metrics={
                                    "stage": "llm_repair",
                                    "file_name": name,
                                    "file_index": fi + 1,
                                    "files_total": total_files,
                                    "llm_batch_index": bi + 1,
                                    "llm_batches_total": total_rb,
                                    "parsed_records": len(parsed_recs),
                                    "llm_batch_coverage_pct": coverage_pct,
                                    "llm_batch_escalated": False,
                                    "llm_parse_conf_below": settings.registry_llm_repair_if_parse_confidence_below,
                                    "llm_selective_targets_total": int(
                                        llm_stats.get("selective_targets_total") or 0
                                    ),
                                    "llm_repair_rows_this_file": len(repair_targets),
                                    "llm_rows_merged_total": int(llm_stats.get("rows") or 0) + llm_used_total,
                                    "stage_done": bi + 1,
                                    "stage_total": total_rb,
                                    "stage_unit": "batches",
                                    "stage_eta_sec": (
                                        int(
                                            (total_rb - (bi + 1))
                                            / max(0.0001, (bi + 1) / max(0.001, time.perf_counter() - llm_stage_t0))
                                        )
                                        if bi + 1 < total_rb
                                        else 0
                                    ),
                                },
                            )
                            save_user_registry_cache(
                                all_source_names,
                                parsed_recs,
                                _router_fingerprint,
                                import_sources_detail=[
                                    {
                                        "sha256": file_sha,
                                        "part": part,
                                        "name": name,
                                        "parse_quality_report": {
                                            "version": PARSER_REPORT_VERSION,
                                            "stats": {"rows_total": len(parsed_recs)},
                                        },
                                    }
                                ],
                                assume_deduped=True,
                            )
                            db_snapshots += 1
                            _set_job(
                                job_id,
                                message=f"Файл «{name}»: repair-батч {bi + 1}/{total_rb} сохранён в БД",
                                records_count=len(parsed_recs),
                                metrics={
                                    "stage": "db_save_batch",
                                    "file_name": name,
                                    "file_index": fi + 1,
                                    "files_total": total_files,
                                    "llm_parse_conf_below": settings.registry_llm_repair_if_parse_confidence_below,
                                    "llm_selective_targets_total": int(
                                        llm_stats.get("selective_targets_total") or 0
                                    ),
                                    "llm_repair_rows_this_file": len(repair_targets),
                                    "llm_rows_merged_total": int(llm_stats.get("rows") or 0) + llm_used_total,
                                    "llm_batch_index": bi + 1,
                                    "llm_batches_total": total_rb,
                                    "saved_records": len(parsed_recs),
                                    "stage_done": bi + 1,
                                    "stage_total": total_rb,
                                    "stage_unit": "batches",
                                    "stage_eta_sec": (
                                        int(
                                            (total_rb - (bi + 1))
                                            / max(0.0001, (bi + 1) / max(0.001, time.perf_counter() - llm_stage_t0))
                                        )
                                        if bi + 1 < total_rb
                                        else 0
                                    ),
                                },
                            )
                            future = next_future

                    pm_end = registry_postal_city_consensus(working)
                    for r in working:
                        r["needs_review"] = bool(_still_bad_for_review(r, pm_end))
                    save_user_registry_cache(
                        all_source_names,
                        parsed_recs,
                        _router_fingerprint,
                        import_sources_detail=[
                            {
                                "sha256": file_sha,
                                "part": part,
                                "name": name,
                                "parse_quality_report": {
                                    "version": PARSER_REPORT_VERSION,
                                    "stats": {"rows_total": len(parsed_recs)},
                                },
                            }
                        ],
                        assume_deduped=True,
                    )
                    db_snapshots += 1

                llm_stats["used_files"] += 1
                llm_stats["rows"] += llm_used_total
                llm_stats["status"].append(
                    {
                        "file": name,
                        "status": "; ".join(llm_batch_statuses[:12])
                        + ("; ..." if len(llm_batch_statuses) > 12 else ""),
                        "rows": llm_used_total,
                        "rows_raw": llm_rows_raw,
                        "batches": total_rb,
                        "batch_size": batch_size,
                        "repair_rows": len(repair_targets),
                    }
                )
            else:
                pm_end = registry_postal_city_consensus(working)
                for r in working:
                    r["needs_review"] = bool(_still_bad_for_review(r, pm_end))
                _append_unique_parsed(working)
                llm_stats["status"].append({"file": name, "status": "disabled_or_no_seed_rows", "rows": 0})

            parse_elapsed += time.perf_counter() - t_parse0
            parsed_delta = len(parsed_recs) - before_parse
            log.info("registry import %s: parse rows delta=%s", name, parsed_delta)

        log.info("registry import: parsed record count=%s", len(parsed_recs))

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
                    log.info(
                        "registry import %s (pdfplumber): extracted text chars=%s part=%s",
                        name,
                        tlen2,
                        part,
                    )
                    _set_job(
                        job_id,
                        progress=27,
                        message=f"Файл «{name}» (pdfplumber): нормализация текста ({tlen2} симв.)…",
                    )
                    t2 = preprocess_registry_plaintext(t2)
                    registry_plaintext_by_part[part].append(f"### PDF:{name} (pdfplumber)\n{t2}")
                    t_parse1 = time.perf_counter()

                    def _parse_tick_pb(n_done: int) -> None:
                        _set_job(
                            job_id,
                            progress=27,
                            message=f"Файл «{name}» (pdfplumber): разбор записей, уже {n_done}…",
                        )

                    _append_unique_parsed(
                        iter_registry_plain_text(t2, part, text_preprocessed=True),
                        tick=_parse_tick_pb,
                    )
                    parse_elapsed += time.perf_counter() - t_parse1
                log.info("registry import after pdfplumber: parsed record count=%s", len(parsed_recs))

        _set_job(
            job_id,
            progress=28,
            message=f"Записей в реестре: {len(parsed_recs)}. Чекбоксы «принимает от других» в PDF…",
        )
        t_checkbox0 = time.perf_counter()
        accepts_by_part_obj: dict[tuple[int, int], bool] = {}
        for fi, (_name, raw) in enumerate(files):
            part = _guess_part(_name, fi)
            ext = _name.rsplit(".", 1)[-1].lower() if "." in _name else ""
            if ext != "pdf":
                continue
            file_checkbox_t0 = time.perf_counter()

            def _cb_pages(cur: int, tot: int, fn=_name) -> None:
                elapsed = max(0.001, time.perf_counter() - file_checkbox_t0)
                rate = cur / elapsed if cur > 0 else 0.0
                stage_eta = int((tot - cur) / rate) if rate > 0 else None
                _set_job(
                    job_id,
                    progress=29,
                    message=f"Файл «{fn}»: чекбоксы PDF, страница {cur}/{tot}",
                    metrics={
                        "stage": "checkbox",
                        "file_name": fn,
                        "file_index": fi + 1,
                        "files_total": len(files),
                        "files_done": fi,
                        "page": cur,
                        "pages_total": tot,
                        "stage_done": cur,
                        "stage_total": tot,
                        "stage_unit": "pages",
                        "stage_eta_sec": stage_eta,
                    },
                )

            local = _extract_accepts_external_by_object_id(raw, page_progress=_cb_pages)
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
            log.info(
                "registry import: accepts_external_waste patched from PDF checkboxes: %s rows",
                patched,
            )

        # LLM после чекбоксов: объекты, для которых в PDF не найдены векторы — пробуем восстановить поля из контекста.
        if False and accepts_by_part_obj and parsed_recs:
            cb_targets = [r for r in parsed_recs if _checkbox_pdf_missing_for_row(r, accepts_by_part_obj)]
            if cb_targets:
                batch_size_cb = 20
                by_part_cb: dict[int, list[dict[str, Any]]] = defaultdict(list)
                for r in cb_targets:
                    by_part_cb[int(r.get("source_part") or 1)].append(r)
                cb_plan: list[tuple[int, list[dict[str, Any]]]] = []
                for p in sorted(by_part_cb.keys()):
                    lst = by_part_cb[p]
                    for i in range(0, len(lst), batch_size_cb):
                        cb_plan.append((p, lst[i : i + batch_size_cb]))
                total_cb = len(cb_plan)
                llm_stats["post_checkbox"]["targets"] = len(cb_targets)
                llm_stats["post_checkbox"]["batches"] = total_cb
                src_names_cb = [n for n, _ in files]
                pc_used = 0
                pc_raw = 0
                cb_statuses: list[str] = []
                with ThreadPoolExecutor(max_workers=1) as ex:
                    fut: Future[tuple[list[dict[str, Any]], str]] | None = None
                    for bi, (pb, batch) in enumerate(cb_plan):
                        pooled_plain = _registry_plaintext_join(pb)
                        if fut is None:
                            fut = ex.submit(
                                repair_registry_records_with_llm,
                                batch,
                                pb,
                                batch_index=bi + 1,
                                total_batches=total_cb,
                                repair_kind="full",
                                registry_plaintext=pooled_plain,
                            )
                        nf: Future[tuple[list[dict[str, Any]], str]] | None = None
                        if bi + 1 < total_cb:
                            pb2, b2 = cb_plan[bi + 1]
                            pooled2 = _registry_plaintext_join(pb2)
                            nf = ex.submit(
                                repair_registry_records_with_llm,
                                b2,
                                pb2,
                                batch_index=bi + 2,
                                total_batches=total_cb,
                                repair_kind="full",
                                registry_plaintext=pooled2,
                            )
                        rows_out, st = fut.result()
                        cov = int(round(len(rows_out) * 100.0 / max(1, len(batch))))
                        merged_b, used_n = _merge_llm_repair_into_seed(batch, rows_out)
                        _apply_row_dict_updates_inplace(batch, merged_b)
                        pc_raw += len(rows_out)
                        pc_used += used_n
                        cb_statuses.append(f"{st}:{cov}%")
                        _set_job(
                            job_id,
                            progress=30,
                            message=(
                                f"LLM после чекбоксов PDF: батч {bi + 1}/{total_cb}, "
                                f"записей {len(parsed_recs)} — {st}"
                            ),
                            metrics={
                                "stage": "llm_post_checkbox",
                                "file_index": 1,
                                "files_total": len(files),
                                "llm_batch_index": bi + 1,
                                "llm_batches_total": total_cb,
                                "parsed_records": len(parsed_recs),
                                "llm_batch_coverage_pct": cov,
                                "llm_post_checkbox_targets": len(cb_targets),
                                "llm_post_checkbox_batches": total_cb,
                                "llm_post_checkbox_rows_merged": pc_used,
                                "llm_rows_merged_total": int(llm_stats.get("rows") or 0) + pc_used,
                                "llm_parse_conf_below": settings.registry_llm_repair_if_parse_confidence_below,
                                "llm_selective_targets_total": int(llm_stats.get("selective_targets_total") or 0),
                                "stage_done": bi + 1,
                                "stage_total": total_cb,
                                "stage_unit": "batches",
                            },
                        )
                        save_user_registry_cache(
                            src_names_cb,
                            parsed_recs,
                            _router_fingerprint,
                            import_sources_detail=load_import_sources_detail(),
                            assume_deduped=True,
                        )
                        db_snapshots += 1
                        fut = nf
                llm_stats["post_checkbox"]["rows_merged"] = pc_used
                llm_stats["rows"] += pc_used
                llm_stats["status"].append(
                    {
                        "phase": "post_checkbox",
                        "status": "; ".join(cb_statuses[:10]) + ("; ..." if len(cb_statuses) > 10 else ""),
                        "rows": pc_used,
                        "rows_raw": pc_raw,
                    }
                )

        pm_flags_final = registry_postal_city_consensus(parsed_recs)
        for r in parsed_recs:
            r["needs_review"] = bool(_still_bad_for_review(r, pm_flags_final, accepts_by_part_obj or None))

        checkbox_elapsed += time.perf_counter() - t_checkbox0

        parse_quality = _collect_parse_quality(parsed_recs)
        selector_telemetry = _collect_selector_telemetry(parsed_recs)
        log.info(
            "registry parse quality: total=%s owner_empty=%s address_empty=%s "
            "address_no_locality=%s phones_empty=%s object_placeholder=%s low_confidence=%s "
            "needs_review=%s repair_pass_rows=%s",
            parse_quality["rows_total"],
            parse_quality["owner_empty"],
            parse_quality["address_empty"],
            parse_quality["address_no_locality"],
            parse_quality["phones_empty"],
            parse_quality["object_placeholder"],
            parse_quality["low_confidence"],
            parse_quality.get("needs_review", 0),
            selector_telemetry.get("repair_pass_rows", 0),
        )
        log.info(
            "registry parse quality json: %s",
            {
                "version": PARSER_REPORT_VERSION,
                "stats": parse_quality,
                "selector_telemetry": selector_telemetry,
                "llm": llm_stats,
                "files": [n for n, _ in files],
            },
        )

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
        parse_quality_report = {
            "version": PARSER_REPORT_VERSION,
            "stats": parse_quality,
            "selector_telemetry": selector_telemetry,
            "llm": llm_stats,
        }
        if len(files) == 1 and import_mode != "append":
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
                import_detail = od + [
                    {
                        "sha256": h,
                        "part": part_guess,
                        "name": fn,
                        "parse_quality_report": parse_quality_report,
                    }
                ]
                import_detail.sort(
                    key=lambda m: (int(m.get("part") or 0), str(m.get("name") or "")),
                )
                other_names = [str(m.get("name") or "") for m in od if m.get("name")]
                names_for_save = sorted(set(other_names + [fn]))
            else:
                import_detail = [
                    {
                        "sha256": h,
                        "part": part_guess,
                        "name": fn,
                        "parse_quality_report": parse_quality_report,
                    }
                ]
                names_for_save = [fn]
            combined_sig = fingerprint_from_sha256_digests(m["sha256"] for m in import_detail)
        else:
            prev_detail = load_import_sources_detail()
            existing_rows = load_cached_registry_records(repair_addresses=False) if import_mode == "append" else []
            added_rows = len(parsed_recs)
            existing_before = len(existing_rows)
            recs = existing_rows + parsed_recs
            merge_hint = (
                f" Добавлено записей: {added_rows} к существующим {existing_before} (режим append)."
                if import_mode == "append"
                else ""
            )
            names_for_save = [n for n, _ in files]
            new_detail = [
                {
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "part": _guess_part(n, i),
                    "name": n,
                    "parse_quality_report": parse_quality_report,
                }
                for i, (n, raw) in enumerate(files)
            ]
            if import_mode == "append" and prev_detail:
                existing_sha = {
                    str(m.get("sha256") or "")
                    for m in prev_detail
                    if isinstance(m, dict) and m.get("sha256")
                }
                import_detail = list(prev_detail)
                for m in new_detail:
                    sha = str(m.get("sha256") or "")
                    if not sha or sha in existing_sha:
                        continue
                    import_detail.append(m)
                    existing_sha.add(sha)
                old_names = [str(m.get("name") or "") for m in prev_detail if isinstance(m, dict) and m.get("name")]
                names_for_save = sorted(set(old_names + names_for_save))
            else:
                import_detail = new_detail

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

        # Важно: фиксируем JSON-результат парсинга в БД ДО геокодирования.
        # Это даёт быстрый доступ к свежим записям и убирает конфликт "старый JSON vs новая БД".
        _set_job(
            job_id,
            progress=30,
            message=f"Найдено записей: {len(recs)}.{merge_hint} Сохраняем JSON в БД…",
            records_count=len(recs),
        )
        save_user_registry_cache(
            names_for_save,
            recs,
            combined_sig,
            import_sources_detail=import_detail,
            assume_deduped=True,
        )
        db_snapshots += 1

        _set_job(
            job_id,
            progress=30,
            message=f"JSON сохранён: {len(recs)} записей. Геокодирование…",
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
                "stage": "geocode",
                "queue_position": 0,
                "stage_done": done,
                "stage_total": n,
                "stage_unit": "rows",
                "stage_eta_sec": eta_sec,
                "done": done,
                "total": n,
                "rows_per_sec": round(rows_per_sec, 2),
                "eta_sec": eta_sec,
                "ocr_total": len(image_indexes),
                "ocr_done": ocr_done,
                "ocr_inflight": _ocr_inflight_count(),
                "ocr_workers": ocr_workers,
                "files_total": len(files),
                "files_done": len(files),
                "nominatim_calls": geocode_stats["nominatim_calls"],
                "nominatim_hit": geocode_stats["nominatim_hit"],
                "nominatim_miss": geocode_stats["nominatim_miss"],
                "cache_hit": geocode_stats["cache_hit"],
                "approx_hit": geocode_stats["approx_hit"],
                "addr_skipped": geocode_stats["addr_skipped"],
                "cached_miss_skip": geocode_stats["cached_miss_skip"],
                "budget_skip": geocode_stats["nominatim_budget_skip"],
                "checkpoints": checkpoint_events,
                "db_snapshots": db_snapshots,
                "geocache_flushes": geocache_flushes,
                "parse_rows_total": parse_quality["rows_total"],
                "parse_owner_empty": parse_quality["owner_empty"],
                "parse_address_empty": parse_quality["address_empty"],
                "parse_address_no_locality": parse_quality["address_no_locality"],
                "parse_phones_empty": parse_quality["phones_empty"],
                "parse_object_placeholder": parse_quality["object_placeholder"],
                "parse_low_confidence": parse_quality["low_confidence"],
                "parse_needs_review": int(parse_quality.get("needs_review") or 0),
                "parse_repair_pass_rows": int(selector_telemetry.get("repair_pass_rows") or 0),
                "llm_parse_conf_below": settings.registry_llm_repair_if_parse_confidence_below,
                "llm_rows_merged_total": int(llm_stats.get("rows") or 0),
                "llm_selective_targets_total": int(llm_stats.get("selective_targets_total") or 0),
                "llm_post_checkbox_targets": int(llm_stats.get("post_checkbox", {}).get("targets") or 0),
                "llm_post_checkbox_rows_merged": int(
                    llm_stats.get("post_checkbox", {}).get("rows_merged") or 0
                ),
                "llm_post_checkbox_batches": int(llm_stats.get("post_checkbox", {}).get("batches") or 0),
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
                    checkpoint_events += 1
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
                        geocache_flushes += 1
                        checkpoint_saved = True
                    # Инкрементальный чекпоинт реестра (UPDATE по pk) — дешевле TRUNCATE+INSERT, выполняем реже.
                    db_progress_step = max(1, dynamic_db_checkpoint_every, min_db_checkpoint_rows)
                    db_checkpoint_by_count = (done - last_db_checkpoint_done) >= db_progress_step
                    db_checkpoint_by_time = (
                        db_checkpoint_max_sec > 0 and (now - last_db_checkpoint_at) >= db_checkpoint_max_sec
                    )
                    if db_checkpoint_by_count or db_checkpoint_by_time or done == n:
                        save_geocode_checkpoint_progress(recs, done)
                        last_db_checkpoint_at = now
                        last_db_checkpoint_done = done
                        db_snapshots += 1
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
            geocache_flushes += 1
        save_user_registry_cache(
            names_for_save,
            recs,
            combined_sig,
            import_sources_detail=import_detail,
            assume_deduped=True,
        )
        db_snapshots += 1
        geocode_elapsed = time.perf_counter() - geocode_t0
        total_elapsed = time.perf_counter() - import_t0
        log.info(
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
        log.info(
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
        log.info(
            "registry import stage timings: extract=%.2fs parse=%.2fs checkbox=%.2fs merge=%.2fs geocode=%.2fs total=%.2fs",
            extract_elapsed,
            parse_elapsed,
            checkbox_elapsed,
            merge_elapsed,
            geocode_elapsed,
            total_elapsed,
        )
        log.info(
            "registry import summary rows=%s checkpoints=%s db_snapshots=%s geocache_flushes=%s "
            "avg_rows_sec=%.2f parse_rows_sec=%.2f",
            len(recs),
            checkpoint_events,
            db_snapshots,
            geocache_flushes,
            (len(recs) / max(0.001, geocode_elapsed)),
            (len(parsed_recs) / max(0.001, parse_elapsed)),
        )

        _set_job(
            job_id,
            status="done",
            progress=100,
            message="Реестр сохранён в кэш",
            error=None,
            records_count=len(recs),
            metrics={
                **_metrics_snapshot(len(recs), time.perf_counter()),
                "extract_sec": round(extract_elapsed, 2),
                "parse_sec": round(parse_elapsed, 2),
                "checkbox_sec": round(checkbox_elapsed, 2),
                "merge_sec": round(merge_elapsed, 2),
                "geocode_sec": round(geocode_elapsed, 2),
                "total_sec": round(total_elapsed, 2),
            },
        )
    except Exception as e:
        # Даже при ошибке стараемся зафиксировать geocode_cache с уже найденными координатами.
        try:
            if geocache_dirty_keys:
                save_geocode_cache(geocache, geocache_dirty_keys)
                geocache_dirty_keys.clear()
                geocache_flushes += 1
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
                db_snapshots += 1
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
    finally:
        if ocr_executor is not None:
            ocr_executor.shutdown(wait=False, cancel_futures=False)
