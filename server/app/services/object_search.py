"""
Поиск по кэшу реестра: расстояние до выбранной точки — по формуле Haversine.
Координаты объекта: из записи реестра, из geocode_cache или запрос к Nominatim по полю address
(оценка по адресу, не точное измерение).
"""

from __future__ import annotations

import time
import threading
from typing import Any

from app.config import settings
from app.schemas import ObjectSearchRequest, ObjectSearchResponse, WasteObjectOut
from app.services.belarus_locality_centroids import approx_coords_from_by_text
from app.services.distance import haversine_km
from app.services.nominatim import forward_geocode_sync, forward_geocode_sync_relaxed
from app.services.user_registry_cache import (
    load_cached_registry_records,
    load_geocode_cache,
    save_geocode_cache,
)


def _normalize_addr_key(s: str) -> str:
    s = " ".join((s or "").replace("\xa0", " ").split()).casefold()
    return s[:280]


def _coords_from_row(row: dict[str, Any]) -> tuple[float | None, float | None]:
    la, lo = row.get("lat"), row.get("lon")
    if la is None or lo is None:
        return None, None
    try:
        return float(la), float(lo)
    except (TypeError, ValueError):
        return None, None


def _coords_from_geocache(
    addr: str, geocache: dict[str, dict[str, float]]
) -> tuple[float | None, float | None]:
    key = _normalize_addr_key(addr)
    hit = geocache.get(key)
    if not hit:
        return None, None
    try:
        return float(hit["lat"]), float(hit["lon"])
    except (KeyError, TypeError, ValueError):
        return None, None


def _resolve_coords_no_network(
    row: dict[str, Any], geocache: dict[str, dict[str, float]]
) -> tuple[float | None, float | None]:
    la, lo = _coords_from_row(row)
    if la is not None:
        return la, lo
    addr = str(row.get("address") or "").strip()
    if len(addr) < 4:
        return None, None
    return _coords_from_geocache(addr, geocache)


_DISTANCE_NOTE_APPROX = "Ориентир по названию населённого пункта или области в адресе"
_WARMUP_LOCK = threading.Lock()
_WARMUP_IN_PROGRESS = False
_WARMUP_COOLDOWN_SEC = 12.0
_WARMUP_LAST_STARTED_AT = 0.0


def _resolve_coords_for_distance(
    row: dict[str, Any], geocache: dict[str, dict[str, float]]
) -> tuple[float | None, float | None, bool]:
    """Координаты для расчёта расстояния: реестр / кэш геокода / справочник НП РБ. Третий флаг — только справочник."""
    la, lo = _resolve_coords_no_network(row, geocache)
    if la is not None:
        return la, lo, False
    addr = str(row.get("address") or "").strip()
    oname = str(row.get("object_name") or "").strip()
    ap = approx_coords_from_by_text(addr, oname)
    if ap:
        return float(ap[0]), float(ap[1]), True
    return None, None, False


def _geocode_pair_with_nominatim(q: str, delay_sec: float) -> tuple[float, float] | None:
    """До двух запросов: строгий BY, затем без countrycodes. Пауза после каждого шага."""
    pair: tuple[float, float] | None = None
    try:
        pair = forward_geocode_sync(q)
    except Exception:
        pair = None
    time.sleep(delay_sec)
    if pair:
        return pair
    try:
        pair = forward_geocode_sync_relaxed(q)
    except Exception:
        pair = None
    return pair


def _geocode_address_into_cache(
    row: dict[str, Any],
    geocache: dict[str, dict[str, float]],
    delay_sec: float,
) -> tuple[float | None, float | None, bool, bool]:
    """
    Возвращает (lat, lon, nominatim_запрашивали, cache_updated).
    """
    la, lo = _resolve_coords_no_network(row, geocache)
    if la is not None:
        return la, lo, False, False
    addr = str(row.get("address") or "").strip()
    if len(addr) < 4:
        return None, None, False, False
    key = _normalize_addr_key(addr)
    queries: list[str] = [addr]
    oname = str(row.get("object_name") or "").strip()
    if oname and oname.casefold() not in addr.casefold():
        queries.append(f"{addr}, {oname}"[:280])

    pair: tuple[float, float] | None = None
    for q in queries:
        pair = _geocode_pair_with_nominatim(q, delay_sec)
        if pair:
            break

    if not pair:
        return None, None, True, False
    la, lo = float(pair[0]), float(pair[1])
    geocache[key] = {"lat": la, "lon": lo}
    return la, lo, True, True


def _start_async_geocache_warmup(filtered_rows: list[dict[str, Any]], delay_sec: float, max_on_demand: int) -> None:
    """
    Фоновый догрев geocode_cache, чтобы текущий ответ не блокировался ожиданием Nominatim.
    Запускается не чаще, чем раз в _WARMUP_COOLDOWN_SEC, и только одним воркером одновременно.
    """
    if max_on_demand <= 0:
        return

    global _WARMUP_IN_PROGRESS, _WARMUP_LAST_STARTED_AT
    now = time.perf_counter()
    with _WARMUP_LOCK:
        if _WARMUP_IN_PROGRESS:
            return
        if now - _WARMUP_LAST_STARTED_AT < _WARMUP_COOLDOWN_SEC:
            return
        _WARMUP_IN_PROGRESS = True
        _WARMUP_LAST_STARTED_AT = now

    def _worker() -> None:
        global _WARMUP_IN_PROGRESS
        try:
            geocache = load_geocode_cache()
            geocache_dirty = False
            api_calls = 0
            for row in filtered_rows:
                if api_calls >= max_on_demand:
                    break
                la, lo = _resolve_coords_no_network(row, geocache)
                if la is not None:
                    continue
                _la, _lo, attempted, updated = _geocode_address_into_cache(row, geocache, delay_sec)
                if attempted:
                    api_calls += 1
                if updated:
                    geocache_dirty = True
            if geocache_dirty:
                save_geocode_cache(geocache)
        finally:
            with _WARMUP_LOCK:
                _WARMUP_IN_PROGRESS = False

    t = threading.Thread(target=_worker, name="geocache-warmup", daemon=True)
    t.start()


def run_object_search(body: ObjectSearchRequest) -> ObjectSearchResponse:
    rows = load_cached_registry_records()
    q = body.query.strip().lower()
    code = (body.waste_code or "").strip()

    filtered: list[dict[str, Any]] = []
    for row in rows:
        if code and str(row.get("waste_code") or "") != code:
            continue
        if q:
            id_s = str(row.get("id", ""))
            wc = str(row.get("waste_code") or "")
            wtn = str(row.get("waste_type_name") or "")
            blob = (
                f"{id_s} {wc} {wtn} {row.get('owner', '')} {row.get('object_name', '')} "
                f"{row.get('address', '')} {row.get('phones', '')}"
            ).lower()
            if q not in blob:
                continue
        filtered.append(row)

    limit = max(1, settings.registry_closest_limit)
    delay = settings.registry_geocode_delay_sec
    max_on_demand = max(0, settings.registry_search_geocode_max)

    if body.lat is None or body.lon is None:
        picked = filtered[:limit]
        return ObjectSearchResponse(
            items=[_row_to_out(r, None) for r in picked],
        )

    ulat, ulon = float(body.lat), float(body.lon)
    geocache = load_geocode_cache()
    geocache_dirty = False

    scored: list[tuple[float, dict[str, Any]]] = []
    scored_ids: set[int] = set()

    for row in filtered:
        rid = int(row["id"])
        if rid in scored_ids:
            continue
        la, lo, _approx = _resolve_coords_for_distance(row, geocache)
        if la is None:
            continue
        d = haversine_km(ulat, ulon, la, lo)
        scored.append((d, row))
        scored_ids.add(rid)

    scored.sort(key=lambda x: x[0])

    # Не блокируем ответ сетью: on-demand геокодирование уходит в фон.
    _start_async_geocache_warmup(filtered, delay, max_on_demand)

    picked: list[dict[str, Any]] = [r for _, r in scored[:limit]]
    picked_ids = {int(r["id"]) for r in picked}

    if len(picked) < limit:
        for row in filtered:
            if len(picked) >= limit:
                break
            rid = int(row["id"])
            if rid in picked_ids:
                continue
            picked.append(row)
            picked_ids.add(rid)

    if geocache_dirty:
        save_geocode_cache(geocache)

    items: list[WasteObjectOut] = []
    for row in picked:
        la, lo, approx_only = _resolve_coords_for_distance(row, geocache)
        dist: float | None = None
        note: str | None = None
        if la is not None:
            dist = round(haversine_km(ulat, ulon, la, lo), 1)
            if approx_only:
                note = _DISTANCE_NOTE_APPROX
        items.append(_row_to_out(row, dist, note))

    return ObjectSearchResponse(items=items)


def _row_to_out(
    row: dict[str, Any], distance_km: float | None, distance_note: str | None = None
) -> WasteObjectOut:
    addr_s = str(row.get("address") or "").strip()
    ph_s = str(row.get("phones") or "").strip()
    return WasteObjectOut(
        id=int(row["id"]),
        owner=str(row.get("owner") or ""),
        object_name=str(row.get("object_name") or ""),
        address=addr_s or None,
        phones=ph_s or None,
        waste_code=row.get("waste_code"),
        waste_type_name=row.get("waste_type_name"),
        accepts_external_waste=bool(row.get("accepts_external_waste", True)),
        distance_km=distance_km,
        distance_note=distance_note,
    )
