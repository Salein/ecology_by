from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from app.core.security import get_current_user, require_admin
from app.domains.auth.service import UserRecord, is_bootstrap_owner_user
from app.domains.registry.application import create_job, enqueue_existing_job, get_job
from app.services.registry_import.queue import registry_import_in_progress
from app.domains.registry.persistence.registry_repository import (
    cache_meta,
    cached_registry_signature,
    clear_user_registry_cache,
    import_payload_sha256_digests_sorted,
    load_import_sources_detail,
    registry_record_count,
    registry_files_fingerprint,
)

router = APIRouter(prefix="/registry", tags=["registry"])

MAX_PDF_BYTES = 120 * 1024 * 1024
ALLOWED_IMPORT_EXTS = {"pdf", "jpg", "jpeg", "png", "webp", "bmp", "tif", "tiff", "html", "htm", "txt"}


def _prepare_and_enqueue_import_job(job_id: str, files: list[UploadFile], import_mode: str = "replace") -> None:
    try:
        payloads: list[tuple[str, bytes]] = []
        for f in files:
            name = f.filename or ""
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if not name or ext not in ALLOWED_IMPORT_EXTS:
                raise ValueError(
                    f"Неподдерживаемый формат: {name!r}. "
                    "Разрешены: PDF/JPG/JPEG/PNG/WEBP/BMP/TIF/TIFF/HTML/HTM/TXT."
                )
            try:
                f.file.seek(0)
            except Exception:
                pass
            raw = f.file.read()
            if len(raw) > MAX_PDF_BYTES:
                raise ValueError(
                    f"Файл {f.filename!r} слишком большой (макс. {MAX_PDF_BYTES // (1024 * 1024)} МБ)."
                )
            if not raw:
                raise ValueError(f"Пустой файл: {f.filename!r}")
            payloads.append((f.filename or "unknown", raw))

        n_cached = registry_record_count()
        incoming_digests = import_payload_sha256_digests_sorted(payloads)
        detail = load_import_sources_detail()
        skip = False
        # Для одного файла намеренно НЕ делаем skip даже при совпадающем SHA.
        if import_mode != "append" and n_cached > 0 and len(payloads) > 1:
            if detail:
                stored_digests = sorted(
                    str(x.get("sha256") or "")
                    for x in detail
                    if isinstance(x, dict) and x.get("sha256")
                )
                skip = bool(stored_digests) and stored_digests == incoming_digests
            else:
                fingerprint = registry_files_fingerprint(payloads)
                cached_sig = cached_registry_signature()
                skip = bool(cached_sig and fingerprint == cached_sig)
        if skip:
            # Просто отмечаем done: повторный импорт не нужен.
            from app.services.registry_import_jobs import _set_job  # local import to avoid public API change

            _set_job(
                job_id,
                status="done",
                progress=100,
                message="Загруженные файлы совпадают с данными в кэше — повторный импорт не выполняется.",
                error=None,
                records_count=registry_record_count(),
                metrics={"stage": "queued", "queue_position": 0, "queue_size": 0, "stage_done": 0, "stage_total": 0},
            )
            return

        fingerprint = registry_files_fingerprint(payloads)
        enqueue_existing_job(job_id, payloads, fingerprint, import_mode=import_mode)
    except Exception as e:
        from app.services.registry_import_jobs import _set_job  # local import to avoid public API change

        _set_job(
            job_id,
            status="error",
            progress=0,
            message="Ошибка подготовки импорта",
            error=str(e),
        )


@router.get("/cache")
async def registry_cache_info(_: UserRecord = Depends(get_current_user)):
    return {"cache": cache_meta(), "registry_import_in_progress": registry_import_in_progress()}


@router.delete("/cache")
async def registry_cache_delete(admin: UserRecord = Depends(require_admin)):
    if not is_bootstrap_owner_user(admin):
        raise HTTPException(status_code=403, detail="Очистка кэша доступна только владельцу системы")
    clear_user_registry_cache()
    return {"ok": True, "message": "Кэш реестра очищен."}


@router.post("/import")
async def registry_import(
    background_tasks: BackgroundTasks,
    files: Annotated[list[UploadFile], File(description="Файлы реестра: PDF/JPEG/PNG/WEBP/HTML/TXT")],
    import_mode: Annotated[str, Form()] = "replace",
    _: UserRecord = Depends(require_admin),
):
    import_mode = (import_mode or "replace").strip().lower()
    if import_mode not in {"replace", "append"}:
        raise HTTPException(status_code=400, detail="import_mode должен быть replace или append")
    if not files:
        raise HTTPException(status_code=400, detail="Добавьте один или несколько файлов реестра.")
    # Быстрая валидация только имени/расширения в request-потоке, без чтения всех bytes здесь.
    for f in files:
        name = f.filename or ""
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if not name or ext not in ALLOWED_IMPORT_EXTS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Неподдерживаемый формат: {name!r}. "
                    "Разрешены: PDF/JPG/JPEG/PNG/WEBP/BMP/TIF/TIFF/HTML/HTM/TXT."
                ),
            )

    job_id = create_job()
    from app.services.registry_import_jobs import _set_job  # local import to avoid public API change

    _set_job(
        job_id,
        status="queued",
        progress=1,
        message="Сервер принимает пакет файлов…",
        metrics={
            "stage": "queued",
            "queue_position": 0,
            "queue_size": 0,
            "stage_done": 0,
            "stage_total": len(files),
            "stage_unit": "files",
            "files_total": len(files),
            "files_done": 0,
        },
    )
    background_tasks.add_task(_prepare_and_enqueue_import_job, job_id, files, import_mode)
    return {"skipped": False, "job_id": job_id}


@router.get("/import/{job_id}")
async def registry_import_status(job_id: str, _: UserRecord = Depends(get_current_user)):
    j = get_job(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Задача не найдена.")
    return j
