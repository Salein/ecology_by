from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile

from app.deps import get_current_user, require_admin
from app.services.auth_users import UserRecord, is_bootstrap_owner_user
from app.services.registry_import_jobs import create_job, get_job, run_registry_import_job
from app.services.user_registry_cache import (
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


@router.get("/cache")
async def registry_cache_info(_: UserRecord = Depends(get_current_user)):
    return {"cache": cache_meta()}


@router.delete("/cache")
async def registry_cache_delete(admin: UserRecord = Depends(require_admin)):
    if not is_bootstrap_owner_user(admin):
        raise HTTPException(status_code=403, detail="Очистка кэша доступна только владельцу системы")
    clear_user_registry_cache()
    return {"ok": True, "message": "Кэш реестра очищен."}


@router.post("/import")
async def registry_import(
    background_tasks: BackgroundTasks,
    files: Annotated[list[UploadFile], File(description="PDF реестра, можно несколько файлов")],
    _: UserRecord = Depends(require_admin),
):
    if not files:
        raise HTTPException(status_code=400, detail="Добавьте один или несколько PDF-файлов.")
    payloads: list[tuple[str, bytes]] = []
    for f in files:
        if not f.filename or not f.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"Ожидаются только PDF: {f.filename!r}")
        raw = await f.read()
        if len(raw) > MAX_PDF_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Файл {f.filename!r} слишком большой (макс. {MAX_PDF_BYTES // (1024 * 1024)} МБ).",
            )
        if not raw:
            raise HTTPException(status_code=400, detail=f"Пустой файл: {f.filename!r}")
        payloads.append((f.filename, raw))

    n_cached = registry_record_count()
    incoming_digests = import_payload_sha256_digests_sorted(payloads)
    detail = load_import_sources_detail()
    skip = False
    # Для одного файла намеренно НЕ делаем skip даже при совпадающем SHA:
    # это позволяет догружать пропущенные записи при повторном импорте той же части.
    if n_cached > 0 and len(payloads) > 1:
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
        return {
            "skipped": True,
            "job_id": None,
            "message": (
                "Загруженные PDF совпадают с данными в кэше — повторный импорт не выполняется."
            ),
            "cache": cache_meta(),
        }

    job_id = create_job()
    fingerprint = registry_files_fingerprint(payloads)
    background_tasks.add_task(run_registry_import_job, job_id, payloads, fingerprint)
    return {"skipped": False, "job_id": job_id}


@router.get("/import/{job_id}")
async def registry_import_status(job_id: str, _: UserRecord = Depends(get_current_user)):
    j = get_job(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Задача не найдена.")
    return j
