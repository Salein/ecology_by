from __future__ import annotations

import hashlib
import io
import re
from datetime import datetime, timezone
from typing import Any, Callable

import pdfplumber
from sqlalchemy import delete, func, select

from app.db.models import GeocodeCacheModel, RegistryCacheMetaModel, RegistryRecordModel
from app.db.session import session_scope
from app.services.registry_record_parser import repair_registry_address


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def registry_files_fingerprint(files: list[tuple[str, bytes]]) -> str:
    digests = sorted(hashlib.sha256(data).hexdigest() for _, data in files)
    return hashlib.sha256("\n".join(digests).encode("utf-8")).hexdigest()


def save_user_registry_cache(
    sources: list[str],
    records: list[dict[str, Any]],
    source_signature: str,
) -> None:
    with session_scope() as session:
        session.execute(delete(RegistryRecordModel))
        session.execute(delete(RegistryCacheMetaModel))
        meta = RegistryCacheMetaModel(
            id=1,
            version=2,
            updated_at=_utc_iso(),
            source_signature=source_signature,
            sources=sources,
        )
        session.add(meta)
        for row in records:
            if not isinstance(row, dict):
                continue
            rec = RegistryRecordModel(
                source_part=_safe_int(row.get("source_part")),
                record_id=_safe_int(row.get("id")),
                owner=str(row.get("owner") or ""),
                object_name=str(row.get("object_name") or ""),
                waste_code=str(row.get("waste_code")) if row.get("waste_code") is not None else None,
                waste_type_name=str(row.get("waste_type_name")) if row.get("waste_type_name") is not None else None,
                accepts_external_waste=bool(row.get("accepts_external_waste", True)),
                address=str(row.get("address")) if row.get("address") is not None else None,
                phones=str(row.get("phones")) if row.get("phones") is not None else None,
                lat=_safe_float(row.get("lat")),
                lon=_safe_float(row.get("lon")),
                payload=row,
            )
            session.add(rec)


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


def load_cached_registry_records() -> list[dict[str, Any]]:
    with session_scope() as session:
        db_rows = session.execute(select(RegistryRecordModel).order_by(RegistryRecordModel.pk.asc())).scalars().all()
    rows = [_db_row_to_payload(row) for row in db_rows]
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


def cache_meta() -> dict[str, Any] | None:
    with session_scope() as session:
        meta = session.get(RegistryCacheMetaModel, 1)
        if not meta:
            return None
        records_count = session.execute(select(func.count(RegistryRecordModel.pk))).scalar_one()
        return {
            "updated_at": meta.updated_at,
            "record_count": int(records_count),
            "sources": meta.sources or [],
            "source_signature": meta.source_signature,
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


def save_geocode_cache(cache: dict[str, dict[str, float]]) -> None:
    with session_scope() as session:
        for key, pair in cache.items():
            if not isinstance(pair, dict):
                continue
            lat = _safe_float(pair.get("lat"))
            lon = _safe_float(pair.get("lon"))
            if lat is None or lon is None:
                continue
            row = session.get(GeocodeCacheModel, key)
            if row:
                row.lat = lat
                row.lon = lon
                session.add(row)
                continue
            session.add(GeocodeCacheModel(key=key, lat=lat, lon=lon))


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
    with session_scope() as session:
        session.execute(delete(GeocodeCacheModel))
        session.execute(delete(RegistryRecordModel))
        session.execute(delete(RegistryCacheMetaModel))
