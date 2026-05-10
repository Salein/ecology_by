"""Слой сохранения снимка реестра в БД (TRUNCATE + мета + пакетная вставка)."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, insert, select, text
from sqlalchemy.orm import Session

from app.infra.db.models import RegistryCacheMetaModel, RegistryRecordModel

REGISTRY_INSERT_BATCH_SIZE = 2000
REGISTRY_CHECKPOINT_UPDATE_CHUNK = 500


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def flush_registry_snapshot(
    session: Session,
    *,
    sources: list[str],
    source_signature: str,
    import_sources_detail: list[dict[str, Any]] | None,
    insert_rows: Iterable[dict[str, Any]],
) -> None:
    """Полностью заменяет содержимое `registry_records` и `registry_cache_meta` одним снимком."""
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        session.execute(text("TRUNCATE TABLE registry_records RESTART IDENTITY"))
        session.execute(text("TRUNCATE TABLE registry_cache_meta"))
    else:
        session.execute(delete(RegistryRecordModel))
        session.execute(delete(RegistryCacheMetaModel))
    meta = RegistryCacheMetaModel(
        id=1,
        version=2,
        updated_at=_utc_iso(),
        source_signature=source_signature,
        sources=sources,
        import_sources_detail=import_sources_detail,
    )
    session.add(meta)
    chunk: list[dict[str, Any]] = []
    for row in insert_rows:
        chunk.append(row)
        if len(chunk) >= REGISTRY_INSERT_BATCH_SIZE:
            session.execute(insert(RegistryRecordModel), chunk)
            chunk.clear()
    if chunk:
        session.execute(insert(RegistryRecordModel), chunk)


def touch_registry_cache_meta_updated_at(session: Session) -> None:
    meta = session.get(RegistryCacheMetaModel, 1)
    if meta is not None:
        meta.updated_at = _utc_iso()


def apply_geocode_checkpoint_updates(session: Session, rows_data: list[dict[str, Any]]) -> None:
    """
    Обновляет первые len(rows_data) строк `registry_records` по порядку pk (ASC),
    не трогая хвост таблицы. Ожидается, что порядок pk совпадает с порядком строк
    после последнего полного `flush_registry_snapshot` (импорт до геокодирования).
    """
    n = len(rows_data)
    if n == 0:
        return
    pks = list(session.scalars(select(RegistryRecordModel.pk).order_by(RegistryRecordModel.pk.asc()).limit(n)))
    if len(pks) != n:
        raise RuntimeError(
            f"geocode checkpoint: в БД {len(pks)} строк с pk по порядку, ожидалось {n} — "
            "чекпоинт отменён, чтобы не повредить данные."
        )
    for i in range(0, n, REGISTRY_CHECKPOINT_UPDATE_CHUNK):
        chunk_rows = rows_data[i : i + REGISTRY_CHECKPOINT_UPDATE_CHUNK]
        chunk_pks = pks[i : i + REGISTRY_CHECKPOINT_UPDATE_CHUNK]
        mappings: list[dict[str, Any]] = []
        for pk, data in zip(chunk_pks, chunk_rows, strict=True):
            row = {"pk": int(pk)}
            row.update(data)
            mappings.append(row)
        session.bulk_update_mappings(RegistryRecordModel, mappings)
