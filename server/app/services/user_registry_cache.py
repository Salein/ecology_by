from __future__ import annotations

import hashlib
import io
import logging
import re
import signal
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Iterator

import pdfplumber
from sqlalchemy import String, cast, or_, text
from sqlalchemy import delete, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.infra.db.models import GeocodeCacheModel, RegistryCacheMetaModel, RegistryRecordModel
from app.infra.db.session import session_scope
from app.services.registry_cache_persistence import (
    apply_geocode_checkpoint_updates,
    flush_registry_snapshot,
    touch_registry_cache_meta_updated_at,
)
from app.services.registry_record_parser import repair_registry_address

logger = logging.getLogger(__name__)
_GEOCODE_UPSERT_BATCH_SIZE = 3000


class _PdfPlumberPageTimeout(Exception):
    pass


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fingerprint_from_sha256_digests(digests: Iterable[str]) -> str:
    ds = sorted(digests)
    return hashlib.sha256("\n".join(ds).encode("utf-8")).hexdigest()


def registry_files_fingerprint(files: list[tuple[str, bytes]]) -> str:
    return fingerprint_from_sha256_digests(hashlib.sha256(data).hexdigest() for _, data in files)


def import_payload_sha256_digests_sorted(payloads: list[tuple[str, bytes]]) -> list[str]:
    return sorted(hashlib.sha256(raw).hexdigest() for _, raw in payloads)


def _norm_text(v: object) -> str:
    return " ".join(str(v or "").replace("\xa0", " ").split()).casefold()


def load_import_sources_detail() -> list[dict[str, Any]] | None:
    """None — мета до миграции или пусто; иначе список {sha256, part, name}."""
    with session_scope() as session:
        meta = session.get(RegistryCacheMetaModel, 1)
        if not meta:
            return None
        raw = getattr(meta, "import_sources_detail", None)
        if raw is None:
            return None
        if not isinstance(raw, list):
            return None
        out: list[dict[str, Any]] = []
        for x in raw:
            if isinstance(x, dict):
                out.append(dict(x))
        return out


def _coerce_accepts_external_for_db(v: object) -> bool | None:
    if v is True:
        return True
    if v is False:
        return False
    return None


def _registry_record_insert_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_part": _safe_int(row.get("source_part")),
        "record_id": _safe_int(row.get("id")),
        "owner": str(row.get("owner") or ""),
        "object_name": str(row.get("object_name") or ""),
        "waste_code": str(row.get("waste_code")) if row.get("waste_code") is not None else None,
        "waste_type_name": str(row.get("waste_type_name")) if row.get("waste_type_name") is not None else None,
        "accepts_external_waste": _coerce_accepts_external_for_db(row.get("accepts_external_waste")),
        "address": str(row.get("address")) if row.get("address") is not None else None,
        "phones": str(row.get("phones")) if row.get("phones") is not None else None,
        "lat": _safe_float(row.get("lat")),
        "lon": _safe_float(row.get("lon")),
        "payload": row,
    }


def save_user_registry_cache(
    sources: list[str],
    records: Iterable[dict[str, Any]],
    source_signature: str,
    import_sources_detail: list[dict[str, Any]] | None = None,
    assume_deduped: bool = False,
) -> None:
    rows_iter = records if assume_deduped else _iter_deduped_registry_records(records)
    insert_rows = (_registry_record_insert_row(row) for row in rows_iter)
    with session_scope() as session:
        flush_registry_snapshot(
            session,
            sources=sources,
            source_signature=source_signature,
            import_sources_detail=import_sources_detail,
            insert_rows=insert_rows,
        )


def save_geocode_checkpoint_progress(recs: list[dict[str, Any]], done: int) -> None:
    """
    Чекпоинт во время геокодирования: обновляет первые `done` строк по pk (ASC),
    без TRUNCATE — хвост таблицы остаётся до финального полного сохранения.
    """
    if done <= 0:
        return
    prefix = recs[:done]
    rows_data = [_registry_record_insert_row(r) for r in prefix]
    with session_scope() as session:
        apply_geocode_checkpoint_updates(session, rows_data)
        touch_registry_cache_meta_updated_at(session)


def _safe_int(v: object) -> int | None:
    try:
        if v is None:
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def _safe_float(v: object) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def registry_row_dedupe_key(row: dict[str, Any]) -> tuple[object, ...]:
    """Ключ совпадения записи реестра (как при дедупе перед INSERT)."""
    return (
        _safe_int(row.get("source_part")),
        _safe_int(row.get("id")),
        _norm_text(row.get("waste_code")),
        _norm_text(row.get("owner")),
        _norm_text(row.get("object_name")),
        _norm_text(row.get("address")),
    )


def _iter_deduped_registry_records(records: Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Итератор dedupe: не создаёт второй большой список в памяти."""
    seen: set[tuple[object, ...]] = set()
    for row in records:
        if not isinstance(row, dict):
            continue
        key = registry_row_dedupe_key(row)
        if key in seen:
            continue
        seen.add(key)
        yield row


_POSTAL_LOCALITY_RE = re.compile(
    r"\b(\d{6})\b[\s,;:\-–—]{0,40}\b"
    r"(г\.\s*[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+(?:\s+[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+){0,2}"
    r"|г/п\s*[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+(?:\s+[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+){0,2}"
    r"|аг\.\s*[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+(?:\s+[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+){0,2}"
    r"|д\.\s*[А-ЯЁA-ZА-ЯЁа-яё0-9][А-ЯЁA-Za-zа-яё0-9\-]+(?:\s+[А-ЯЁA-ZА-ЯЁа-яё0-9][А-ЯЁA-Za-zа-яё0-9\-]+){0,2}"
    r"|дер\.\s*[А-ЯЁA-ZА-ЯЁа-яё0-9][А-ЯЁA-Za-zа-яё0-9\-]+(?:\s+[А-ЯЁA-ZА-ЯЁа-яё0-9][А-ЯЁA-Za-zа-яё0-9\-]+){0,2}"
    r"|п\.\s*[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+(?:\s+[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+){0,2}"
    r"|пос\.\s*[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+(?:\s+[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+){0,2}"
    r"|пос[её]лок\s*[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+(?:\s+[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+){0,2}"
    r"|городок\s*[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+(?:\s+[А-ЯЁA-Z][А-ЯЁA-Za-zа-яё\-]+){0,2})",
    flags=re.IGNORECASE,
)


def _build_postal_city_map(rows: list[dict[str, Any]]) -> dict[str, str]:
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
            for m in _POSTAL_LOCALITY_RE.finditer(t):
                postal = m.group(1)
                locality = re.sub(r"[,\s]+$", "", m.group(2)).strip()
                if len(locality) < 3:
                    continue
                by_city = stats.setdefault(postal, {})
                by_city[locality] = by_city.get(locality, 0) + 1

    out: dict[str, str] = {}
    for postal, by_city in stats.items():
        if not by_city:
            continue
        ranked = sorted(by_city.items(), key=lambda x: x[1], reverse=True)
        best_city, best_count = ranked[0]
        second_count = ranked[1][1] if len(ranked) > 1 else 0
        # Хотим заполнять город/НП всегда: если для индекса есть хотя бы один вариант,
        # выбираем самый частый. При равенстве — берём лексикографически первый,
        # чтобы результат был детерминированным.
        if best_count >= 1:
            tied = [x for x in ranked if x[1] == best_count]
            out[postal] = sorted((x[0] for x in tied), key=lambda s: s.casefold())[0]
    return out


def _repair_truncated_city_suffix(address: str, postal_to_city: dict[str, str]) -> str:
    compact = re.sub(r"\s+", " ", (address or "").replace("\xa0", " ")).strip()
    if not compact:
        return compact
    # Если населённого пункта в адресе нет вовсе, пробуем вставить город по индексу.
    # Это позволяет стабильно показывать город в UI даже для строк вида "223141," или
    # "211730, Витебская область,".
    has_locality = bool(
        re.search(
            r"\b(г\.|г/п|город|п\.|пос\.|поселок|посёлок|аг\.|д\.|дер\.|городок)\b",
            compact,
            flags=re.IGNORECASE,
        )
    )
    if not has_locality:
        pm0 = re.search(r"\b(\d{6})\b", compact)
        if pm0:
            postal0 = pm0.group(1)
            loc0 = postal_to_city.get(postal0)
            if loc0:
                # Вставляем сразу после индекса.
                injected = re.sub(
                    r"^\s*" + re.escape(postal0) + r"\s*,?\s*",
                    f"{postal0}, {loc0}, ",
                    compact,
                    count=1,
                    flags=re.IGNORECASE,
                )
                injected = re.sub(r",\s*,", ",", injected)
                injected = re.sub(r"[,\s]+$", "", injected).strip()
                return injected
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


def _db_row_to_payload(row: RegistryRecordModel) -> dict[str, Any]:
    if isinstance(row.payload, dict):
        out = dict(row.payload)
    else:
        out = {
            "id": row.record_id,
            "owner": row.owner,
            "object_name": row.object_name,
            "waste_code": row.waste_code,
            "waste_type_name": row.waste_type_name,
            "accepts_external_waste": row.accepts_external_waste,
            "address": row.address,
            "phones": row.phones,
            "source_part": row.source_part,
            "lat": row.lat,
            "lon": row.lon,
        }
    out["accepts_external_waste"] = row.accepts_external_waste
    # После импорта из JSON в payload иногда бывает id: null — поиск падал с 500 (int(None)).
    rid = out.get("id")
    nid: int | None = None
    if rid is not None and rid != "":
        try:
            nid = int(rid)
        except (TypeError, ValueError):
            nid = None
    if nid is None:
        nid = int(row.record_id) if row.record_id is not None else int(row.pk)
    out["id"] = nid
    return out


def _apply_address_repairs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    postal_to_city = _build_postal_city_map(rows)
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


def apply_registry_address_repairs_inplace(rows: list[dict[str, Any]]) -> None:
    """Нормализация адреса + подстановка НП по индексу (детерминированно, без LLM)."""
    _apply_address_repairs(rows)


def registry_postal_city_consensus(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Индекс → самый частый фрагмент населённого пункта по всему набору строк импорта."""
    return _build_postal_city_map(rows)


def _search_select_stmt():
    return select(
        RegistryRecordModel.pk,
        RegistryRecordModel.source_part,
        RegistryRecordModel.record_id,
        RegistryRecordModel.owner,
        RegistryRecordModel.object_name,
        RegistryRecordModel.waste_code,
        RegistryRecordModel.waste_type_name,
        RegistryRecordModel.accepts_external_waste,
        RegistryRecordModel.address,
        RegistryRecordModel.phones,
        RegistryRecordModel.lat,
        RegistryRecordModel.lon,
    )


def _search_row_to_payload(row: Any) -> dict[str, Any]:
    m = row._mapping if hasattr(row, "_mapping") else row
    rid = m.get("record_id")
    nid: int | None = None
    if rid is not None and rid != "":
        try:
            nid = int(rid)
        except (TypeError, ValueError):
            nid = None
    if nid is None:
        nid = int(m.get("pk"))
    return {
        "id": nid,
        "source_part": m.get("source_part"),
        "owner": str(m.get("owner") or ""),
        "object_name": str(m.get("object_name") or ""),
        "waste_code": str(m.get("waste_code")) if m.get("waste_code") is not None else None,
        "waste_type_name": str(m.get("waste_type_name")) if m.get("waste_type_name") is not None else None,
        "accepts_external_waste": _coerce_accepts_external_for_db(m.get("accepts_external_waste")),
        "address": str(m.get("address")) if m.get("address") is not None else None,
        "phones": str(m.get("phones")) if m.get("phones") is not None else None,
        "lat": _safe_float(m.get("lat")),
        "lon": _safe_float(m.get("lon")),
    }


def load_cached_registry_records(*, repair_addresses: bool = True) -> list[dict[str, Any]]:
    with session_scope() as session:
        db_rows = session.execute(select(RegistryRecordModel).order_by(RegistryRecordModel.pk.asc())).scalars().all()
    rows = [_db_row_to_payload(row) for row in db_rows]
    if not repair_addresses:
        return rows
    return _apply_address_repairs(rows)


def load_search_records(
    *,
    accepts_external_only: bool = False,
    repair_addresses: bool = True,
) -> list[dict[str, Any]]:
    with session_scope() as session:
        stmt = _search_select_stmt().order_by(RegistryRecordModel.pk.asc())
        if accepts_external_only:
            stmt = stmt.where(RegistryRecordModel.accepts_external_waste.is_(True))
        db_rows = session.execute(stmt).all()
    rows = [_search_row_to_payload(row) for row in db_rows]
    if not repair_addresses:
        return rows
    return _apply_address_repairs(rows)


def load_cached_registry_records_prefilter(
    *,
    waste_code: str | None = None,
    record_id: int | None = None,
    accepts_external_only: bool = False,
    repair_addresses: bool = True,
) -> list[dict[str, Any]]:
    with session_scope() as session:
        stmt = select(RegistryRecordModel).order_by(RegistryRecordModel.pk.asc())
        if waste_code:
            stmt = stmt.where(RegistryRecordModel.waste_code == str(waste_code))
        if record_id is not None:
            stmt = stmt.where(RegistryRecordModel.record_id == int(record_id))
        if accepts_external_only:
            stmt = stmt.where(RegistryRecordModel.accepts_external_waste.is_(True))
        db_rows = session.execute(stmt).scalars().all()
    rows = [_db_row_to_payload(row) for row in db_rows]
    if not repair_addresses:
        return rows
    return _apply_address_repairs(rows)


def load_search_records_prefilter(
    *,
    waste_code: str | None = None,
    record_id: int | None = None,
    accepts_external_only: bool = False,
    repair_addresses: bool = True,
) -> list[dict[str, Any]]:
    with session_scope() as session:
        stmt = _search_select_stmt().order_by(RegistryRecordModel.pk.asc())
        if waste_code:
            stmt = stmt.where(RegistryRecordModel.waste_code == str(waste_code))
        if record_id is not None:
            stmt = stmt.where(RegistryRecordModel.record_id == int(record_id))
        if accepts_external_only:
            stmt = stmt.where(RegistryRecordModel.accepts_external_waste.is_(True))
        db_rows = session.execute(stmt).all()
    rows = [_search_row_to_payload(row) for row in db_rows]
    if not repair_addresses:
        return rows
    return _apply_address_repairs(rows)


def load_cached_registry_records_text_prefilter(
    *,
    query: str,
    waste_code: str | None = None,
    accepts_external_only: bool = False,
    limit: int = 5000,
    repair_addresses: bool = True,
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    like_q = f"%{q}%"
    with session_scope() as session:
        stmt = select(RegistryRecordModel).order_by(RegistryRecordModel.pk.asc())
        if waste_code:
            stmt = stmt.where(RegistryRecordModel.waste_code == str(waste_code))
        if accepts_external_only:
            stmt = stmt.where(RegistryRecordModel.accepts_external_waste.is_(True))
        stmt = stmt.where(
            or_(
                cast(RegistryRecordModel.waste_code, String).ilike(like_q),
                cast(RegistryRecordModel.waste_type_name, String).ilike(like_q),
            )
        ).limit(max(1, int(limit)))
        db_rows = session.execute(stmt).scalars().all()
    rows = [_db_row_to_payload(row) for row in db_rows]
    if not repair_addresses:
        return rows
    return _apply_address_repairs(rows)


def load_search_records_text_prefilter(
    *,
    query: str,
    waste_code: str | None = None,
    accepts_external_only: bool = False,
    limit: int = 5000,
    repair_addresses: bool = True,
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    like_q = f"%{q}%"
    with session_scope() as session:
        stmt = _search_select_stmt().order_by(RegistryRecordModel.pk.asc())
        if waste_code:
            stmt = stmt.where(RegistryRecordModel.waste_code == str(waste_code))
        if accepts_external_only:
            stmt = stmt.where(RegistryRecordModel.accepts_external_waste.is_(True))
        stmt = stmt.where(
            or_(
                cast(RegistryRecordModel.waste_code, String).ilike(like_q),
                cast(RegistryRecordModel.waste_type_name, String).ilike(like_q),
            )
        ).limit(max(1, int(limit)))
        db_rows = session.execute(stmt).all()
    rows = [_search_row_to_payload(row) for row in db_rows]
    if not repair_addresses:
        return rows
    return _apply_address_repairs(rows)


def registry_record_count() -> int:
    with session_scope() as session:
        total = session.execute(select(func.count(RegistryRecordModel.pk))).scalar_one()
    return int(total or 0)


def _build_parse_quality_summary(parse_quality_report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(parse_quality_report, dict):
        return None
    stats = parse_quality_report.get("stats")
    if not isinstance(stats, dict):
        return None

    total = int(stats.get("rows_total") or 0)
    if total <= 0:
        return {
            "verdict": "warn",
            "total_rows": 0,
            "empty_owner_pct": None,
            "empty_address_pct": None,
            "empty_phones_pct": None,
            "address_no_locality_pct": None,
            "object_placeholder_pct": None,
        }

    def _pct(key: str) -> float:
        return round((int(stats.get(key) or 0) * 100.0) / total, 2)

    owner_empty_pct = _pct("owner_empty")
    address_empty_pct = _pct("address_empty")
    phones_empty_pct = _pct("phones_empty")
    addr_no_locality_pct = _pct("address_no_locality")
    object_placeholder_pct = _pct("object_placeholder")
    severe = owner_empty_pct >= 30.0 or address_empty_pct >= 10.0
    low_conf_pct = _pct("low_confidence")
    warn = severe or phones_empty_pct >= 20.0 or addr_no_locality_pct >= 20.0 or object_placeholder_pct >= 10.0 or low_conf_pct >= 15.0

    out: dict[str, Any] = {
        "verdict": "warn" if warn else "good",
        "total_rows": total,
        "empty_owner_pct": owner_empty_pct,
        "empty_address_pct": address_empty_pct,
        "empty_phones_pct": phones_empty_pct,
        "address_no_locality_pct": addr_no_locality_pct,
        "object_placeholder_pct": object_placeholder_pct,
        "low_confidence_pct": low_conf_pct,
    }

    telemetry = parse_quality_report.get("selector_telemetry")
    if isinstance(telemetry, dict):
        repair_n = int(telemetry.get("repair_pass_rows") or 0)
        out["repair_pass_rows"] = repair_n
        out["repair_pass_pct"] = round((repair_n * 100.0) / total, 2) if total else None
        by_field = telemetry.get("by_field")
        if isinstance(by_field, dict) and repair_n > 0:

            def _repair_alt_pct(field: str) -> float | None:
                fc = by_field.get(field)
                if not isinstance(fc, dict):
                    return None
                alt = int(fc.get("alternative") or 0)
                return round((alt * 100.0) / repair_n, 2)

            out["repair_owner_alt_pct"] = _repair_alt_pct("owner")
            out["repair_object_alt_pct"] = _repair_alt_pct("object_name")
            out["repair_phones_alt_pct"] = _repair_alt_pct("phones")
            out["repair_address_alt_pct"] = _repair_alt_pct("address")
        elif isinstance(by_field, dict):
            out["repair_owner_alt_pct"] = None
            out["repair_object_alt_pct"] = None
            out["repair_phones_alt_pct"] = None
            out["repair_address_alt_pct"] = None

    return out


def cache_meta() -> dict[str, Any] | None:
    with session_scope() as session:
        meta = session.get(RegistryCacheMetaModel, 1)
        if not meta:
            return None
        records_count = session.execute(select(func.count(RegistryRecordModel.pk))).scalar_one()
        accepts_true_count = session.execute(
            select(func.count(RegistryRecordModel.pk)).where(RegistryRecordModel.accepts_external_waste.is_(True))
        ).scalar_one()
        accepts_false_count = session.execute(
            select(func.count(RegistryRecordModel.pk)).where(RegistryRecordModel.accepts_external_waste.is_(False))
        ).scalar_one()
        accepts_unknown_count = session.execute(
            select(func.count(RegistryRecordModel.pk)).where(RegistryRecordModel.accepts_external_waste.is_(None))
        ).scalar_one()
        parse_quality_report: dict[str, Any] | None = None
        detail = meta.import_sources_detail if isinstance(meta.import_sources_detail, list) else []
        for item in detail:
            if not isinstance(item, dict):
                continue
            report = item.get("parse_quality_report")
            if isinstance(report, dict):
                parse_quality_report = dict(report)

        return {
            "updated_at": meta.updated_at,
            "record_count": int(records_count),
            "accepts_true_count": int(accepts_true_count),
            "accepts_false_count": int(accepts_false_count),
            "accepts_unknown_count": int(accepts_unknown_count),
            "sources": meta.sources or [],
            "source_signature": meta.source_signature,
            "parse_quality_report": parse_quality_report,
            "parse_quality_summary": _build_parse_quality_summary(parse_quality_report),
        }


def cached_registry_signature() -> str | None:
    with session_scope() as session:
        meta = session.get(RegistryCacheMetaModel, 1)
        if not meta:
            return None
        sig = meta.source_signature
        return str(sig) if sig else None


def load_geocode_cache() -> dict[str, dict[str, float]]:
    with session_scope() as session:
        rows = session.execute(select(GeocodeCacheModel)).scalars().all()
        return {r.key: {"lat": float(r.lat), "lon": float(r.lon)} for r in rows}


def load_geocode_cache_subset(keys: Iterable[str]) -> dict[str, dict[str, float]]:
    uniq_keys = sorted({str(k or "").strip() for k in keys if str(k or "").strip()})
    if not uniq_keys:
        return {}
    out: dict[str, dict[str, float]] = {}
    with session_scope() as session:
        for i in range(0, len(uniq_keys), _GEOCODE_UPSERT_BATCH_SIZE):
            chunk = uniq_keys[i : i + _GEOCODE_UPSERT_BATCH_SIZE]
            rows = session.execute(select(GeocodeCacheModel).where(GeocodeCacheModel.key.in_(chunk))).scalars().all()
            for r in rows:
                out[r.key] = {"lat": float(r.lat), "lon": float(r.lon)}
    return out


def save_geocode_cache(cache: dict[str, dict[str, float]], keys: Iterable[str] | None = None) -> None:
    def _iter_chunks(items: list[str], size: int):
        for i in range(0, len(items), size):
            yield items[i : i + size]

    with session_scope() as session:
        selected_keys = list(keys) if keys is not None else list(cache.keys())
        if not selected_keys:
            return

        payload: dict[str, dict[str, float]] = {}
        for key in selected_keys:
            pair = cache.get(key)
            if not isinstance(pair, dict):
                continue
            lat = _safe_float(pair.get("lat"))
            lon = _safe_float(pair.get("lon"))
            if lat is None or lon is None:
                continue
            payload[key] = {"lat": lat, "lon": lon}
        if not payload:
            return

        # Быстрый путь для PostgreSQL: upsert одной командой на чанк.
        if session.bind is not None and session.bind.dialect.name == "postgresql":
            payload_keys = list(payload.keys())
            for keys_chunk in _iter_chunks(payload_keys, _GEOCODE_UPSERT_BATCH_SIZE):
                rows = [{"key": k, "lat": payload[k]["lat"], "lon": payload[k]["lon"]} for k in keys_chunk]
                stmt = pg_insert(GeocodeCacheModel.__table__).values(rows)
                stmt = stmt.on_conflict_do_update(
                    index_elements=[GeocodeCacheModel.__table__.c.key],
                    set_={"lat": stmt.excluded.lat, "lon": stmt.excluded.lon},
                )
                session.execute(stmt)
            return

        payload_keys = list(payload.keys())
        for keys_chunk in _iter_chunks(payload_keys, _GEOCODE_UPSERT_BATCH_SIZE):
            existing_keys = set(
                session.execute(select(GeocodeCacheModel.key).where(GeocodeCacheModel.key.in_(keys_chunk))).scalars().all()
            )
            to_insert: list[dict[str, Any]] = []
            to_update: list[dict[str, Any]] = []
            for key in keys_chunk:
                pair = payload[key]
                row = {"key": key, "lat": pair["lat"], "lon": pair["lon"]}
                if key in existing_keys:
                    to_update.append(row)
                else:
                    to_insert.append(row)

            if to_insert:
                session.bulk_insert_mappings(GeocodeCacheModel, to_insert)
            if to_update:
                session.bulk_update_mappings(GeocodeCacheModel, to_update)


def score_registry_pdf_plaintext_for_import(text: str) -> int:
    """
    Эвристическая оценка «похожести» текста на реестр ecoinfo (до парсера).
    Используется в режиме hybrid: сравнение PyMuPDF vs pdfplumber.
    """
    s = (text or "").replace("\xa0", " ")
    if not s.strip():
        return 0
    fkko = len(re.findall(r"(?<![0-9])[0-9]{7}(?![0-9])", s))
    objects = len(re.findall(r"(?i)(?:Объект|[Oo]bject)\s*(?:№\.?)?\s*\d+", s))
    owners = len(re.findall(r"(?i)\bСобственник\b", s))
    # Длина без кода ФККО не должна «перебить» отсутствие якорей.
    len_bonus = min(len(s), 400_000) // 3000
    return fkko * 200 + objects * 18 + owners * 6 + len_bonus


def normalize_registry_pdf_extracted_text(text: str) -> str:
    """
    Нормализация «сырого» текста после PDF-движка: переносы, мягкий дефис, типичные разрывы слов по строкам.
    Улучшает последующий разбор реестра без смены бэкенда.
    """
    if not text:
        return ""
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("\x0c", "\n")
    t = t.replace("\u00ad", "")
    t = t.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "").replace("\ufeff", "")
    # «слово-\nпродолжение» (кириллица/латиница), без склейки цифр (телефоны, индексы).
    t = re.sub(
        r"(?<=[A-Za-zА-Яа-яёЁ])-\n(?=[A-Za-zА-Яа-яёЁ])",
        "",
        t,
    )
    t = re.sub(r"\n{5,}", "\n\n\n\n", t)
    return t


def _pymupdf_page_get_plaintext(page: Any) -> str:
    """Текст страницы: чтение по блокам с сортировкой + дефисация (PyMuPDF)."""
    import fitz

    try:
        return page.get_text(sort=True, flags=fitz.TEXT_DEHYPHENATE) or ""
    except TypeError:
        try:
            return page.get_text(flags=fitz.TEXT_DEHYPHENATE) or ""
        except Exception:
            return page.get_text() or ""
    except Exception:
        try:
            return page.get_text() or ""
        except Exception:
            return ""


def _extract_pdf_text_pdfplumber(
    data: bytes,
    page_progress: Callable[[int, int], None] | None,
) -> str:
    """Прежний путь; на отдельных страницах pdfplumber может «висеть» без исключения."""
    parts: list[str] = []
    page_timeout_sec = max(0.0, float(settings.registry_pdfplumber_page_timeout_sec))
    pymupdf_doc: Any = None
    pymupdf_fallback_pages = 0
    bio = io.BytesIO(data)
    try:
        with pdfplumber.open(bio) as pdf:
            n = len(pdf.pages)
            for i in range(n):
                use_alarm = False
                prev_handler: Any = None
                if page_timeout_sec > 0 and hasattr(signal, "SIGALRM"):
                    try:
                        prev_handler = signal.getsignal(signal.SIGALRM)

                        def _on_alarm(_signum: int, _frame: object) -> None:
                            raise _PdfPlumberPageTimeout()

                        signal.signal(signal.SIGALRM, _on_alarm)
                        signal.setitimer(signal.ITIMER_REAL, page_timeout_sec)
                        use_alarm = True
                    except (AttributeError, ValueError):
                        # Например, не-main thread / платформа без SIGALRM.
                        use_alarm = False
                try:
                    t = pdf.pages[i].extract_text() or ""
                except _PdfPlumberPageTimeout:
                    logger.warning(
                        "pdfplumber: таймаут страницы %s/%s (%.1fs), fallback на PyMuPDF",
                        i + 1,
                        n,
                        page_timeout_sec,
                    )
                    t = ""
                    try:
                        if pymupdf_doc is None:
                            import fitz

                            pymupdf_doc = fitz.open(stream=data, filetype="pdf")
                        t = _pymupdf_page_get_plaintext(pymupdf_doc.load_page(i))
                        if t.strip():
                            pymupdf_fallback_pages += 1
                    except Exception:
                        logger.warning(
                            "pymupdf fallback: пропуск страницы %s/%s (ошибка get_text)",
                            i + 1,
                            n,
                        )
                        t = ""
                except Exception:
                    logger.warning("pdfplumber: пропуск страницы %s/%s (ошибка extract_text)", i + 1, n)
                    t = ""
                finally:
                    if use_alarm:
                        try:
                            signal.setitimer(signal.ITIMER_REAL, 0.0)
                            signal.signal(signal.SIGALRM, prev_handler)
                        except Exception:
                            pass
                if t.strip():
                    parts.append(t)
                if page_progress:
                    page_progress(i + 1, n)
    finally:
        if pymupdf_doc is not None:
            try:
                pymupdf_doc.close()
            except Exception:
                pass
    if pymupdf_fallback_pages > 0:
        logger.info("pdfplumber fallback via PyMuPDF used on %s page(s)", pymupdf_fallback_pages)
    return normalize_registry_pdf_extracted_text("\n".join(parts))


def _extract_pdf_text_pymupdf(
    data: bytes,
    page_progress: Callable[[int, int], None] | None,
) -> str:
    import fitz

    parts: list[str] = []
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        n = doc.page_count
        for i in range(n):
            try:
                t = _pymupdf_page_get_plaintext(doc.load_page(i))
            except Exception:
                logger.warning("pymupdf: пропуск страницы %s/%s (ошибка get_text)", i + 1, n)
                t = ""
            if t.strip():
                parts.append(t)
            if page_progress:
                page_progress(i + 1, n)
    finally:
        doc.close()
    return normalize_registry_pdf_extracted_text("\n".join(parts))


def extract_pdf_text_pdfplumber_bytes(
    data: bytes,
    page_progress: Callable[[int, int], None] | None = None,
) -> str:
    """Извлечение текста pdfplumber (второй проход при импорте, если PyMuPDF не даёт записей)."""
    return _extract_pdf_text_pdfplumber(data, page_progress)


def extract_pdf_text_from_bytes(
    data: bytes,
    page_progress: Callable[[int, int], None] | None = None,
) -> str:
    """
    Текст для импорта реестра. По умолчанию PyMuPDF: быстрее и обычно не залипает на страницах,
    где pdfplumber зависает. Режимы REGISTRY_PDF_TEXT_BACKEND:
    - pymupdf — только PyMuPDF (с пустым текстом — fallback на pdfplumber);
    - pdfplumber — только pdfplumber;
    - hybrid — PyMuPDF, затем при низкой эвристической оценке текста сравнение с pdfplumber, лучший результат.
    """
    backend = (settings.registry_pdf_text_backend or "pymupdf").strip().lower()
    if backend == "pdfplumber":
        return _extract_pdf_text_pdfplumber(data, page_progress)

    text_m = ""
    try:
        text_m = _extract_pdf_text_pymupdf(data, page_progress)
    except Exception as e:
        logger.warning("pymupdf: открытие/разбор PDF не удалось (%s), пробуем pdfplumber", e)
        return _extract_pdf_text_pdfplumber(data, page_progress)

    if not text_m.strip() and len(data) > 500:
        logger.warning("pymupdf: пустой текст для PDF %s байт, пробуем pdfplumber", len(data))
        return _extract_pdf_text_pdfplumber(data, page_progress)

    if backend != "hybrid":
        return text_m

    min_ok = max(0, int(settings.registry_pdf_hybrid_pymupdf_min_score))
    s_m = score_registry_pdf_plaintext_for_import(text_m)
    if s_m >= min_ok:
        logger.debug("registry PDF hybrid: pymupdf score=%s >= %s, pdfplumber не вызываем", s_m, min_ok)
        return text_m

    text_p = _extract_pdf_text_pdfplumber(data, page_progress)
    s_p = score_registry_pdf_plaintext_for_import(text_p)
    if s_p > s_m:
        logger.info(
            "registry PDF hybrid: выбран pdfplumber (score %s > pymupdf %s, min_ok=%s)",
            s_p,
            s_m,
            min_ok,
        )
        return text_p
    logger.info(
        "registry PDF hybrid: оставлен pymupdf (score %s >= pdfplumber %s, min_ok=%s)",
        s_m,
        s_p,
        min_ok,
    )
    return text_m


def clear_user_registry_cache() -> None:
    with session_scope() as session:
        session.execute(delete(GeocodeCacheModel))
        session.execute(delete(RegistryRecordModel))
        session.execute(delete(RegistryCacheMetaModel))
