"""
Поиск по кэшу реестра: расстояние до выбранной точки — по формуле Haversine.
Координаты объекта: из записи реестра, из geocode_cache или запрос к Nominatim по полю address
(оценка по адресу, не точное измерение).
"""

from __future__ import annotations

import time
import threading
from typing import Any

import httpx

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
_DISTANCE_NOTE_AIR_FALLBACK = "По прямой (роутинг по дорогам недоступен)"
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


def _road_distance_km(ulat: float, ulon: float, la: float, lo: float) -> tuple[float | None, str | None]:
    base = settings.osrm_base_url
    if not base:
        return None, "OSRM не настроен"
    url = (
        f"{base}/route/v1/driving/"
        f"{ulon:.7f},{ulat:.7f};{lo:.7f},{la:.7f}"
        "?overview=false&alternatives=false&steps=false"
    )
    try:
        with httpx.Client(timeout=settings.osrm_timeout_sec) as client:
            r = client.get(url)
        if r.status_code != 200:
            return None, f"OSRM HTTP {r.status_code}"
        data = r.json()
        routes = data.get("routes") if isinstance(data, dict) else None
        if not isinstance(routes, list) or not routes:
            code = data.get("code") if isinstance(data, dict) else None
            if isinstance(code, str) and code:
                return None, f"Маршрут не найден ({code})"
            return None, "Маршрут не найден"
        dist_m = routes[0].get("distance") if isinstance(routes[0], dict) else None
        if dist_m is None:
            return None, "OSRM не вернул distance"
        return float(dist_m) / 1000.0, None
    except httpx.TimeoutException:
        return None, "Таймаут OSRM"
    except Exception:
        return None, "Ошибка запроса к OSRM"


def _distance_spread_km(distance_km: float, approx_only: bool, by_road: bool) -> tuple[float, str]:
    """
    Возвращает ориентировочный разброс (±км) для UI.
    Это не статистическая гарантия, а практическая оценка погрешности по типу источника.
    """
    d = max(0.1, float(distance_km))
    if approx_only:
        # Координаты по справочнику населённых пунктов/областей: разброс заметный.
        return round(max(8.0, d * 0.35), 1), "Оценка по адресу/населённому пункту, возможен больший разброс."
    if by_road:
        # Роутинг по дорогам точнее "по воздуху", но координаты объекта всё ещё адресные.
        return round(max(1.0, d * 0.12), 1), "По дорогам, координаты объекта оценены по адресу."
    # По воздуху (Haversine) + адресные координаты объекта.
    return round(max(2.0, d * 0.2), 1), "По прямой; дорожная сеть и точный подъезд не учитываются."


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
        return ObjectSearchResponse(items=[_row_to_out(r) for r in picked])

    ulat, ulon = float(body.lat), float(body.lon)
    geocache = load_geocode_cache()
    geocache_dirty = False

    scored: list[tuple[float, dict[str, Any], float, float, bool]] = []

    for row in filtered:
        la, lo, approx = _resolve_coords_for_distance(row, geocache)
        if la is None:
            continue
        d = haversine_km(ulat, ulon, la, lo)
        scored.append((d, row, la, lo, approx))

    scored.sort(key=lambda x: x[0])

    # Не блокируем ответ сетью: on-demand геокодирование уходит в фон.
    _start_async_geocache_warmup(filtered, delay, max_on_demand)

    picked: list[dict[str, Any]] = []
    air_distance_by_row: dict[int, float] = {}
    road_distance_by_row: dict[int, float] = {}
    road_error_by_row: dict[int, str] = {}
    note_by_row: dict[int, str] = {}
    road_mode = settings.distance_mode == "road"
    if road_mode and scored:
        n_candidates = min(len(scored), max(limit, settings.road_distance_candidates))
        ranked: list[tuple[float, dict[str, Any]]] = []
        for air_d, row, la, lo, approx_only in scored[:n_candidates]:
            road_d, road_err = _road_distance_km(ulat, ulon, la, lo)
            used_d = road_d if road_d is not None else air_d
            ranked.append((used_d, row))
            k = id(row)
            air_distance_by_row[k] = air_d
            if road_d is None:
                if road_err:
                    road_error_by_row[k] = road_err
                note_by_row[k] = _DISTANCE_NOTE_AIR_FALLBACK
            else:
                road_distance_by_row[k] = road_d
            if approx_only and k not in note_by_row:
                note_by_row[k] = _DISTANCE_NOTE_APPROX
        ranked.sort(key=lambda x: x[0])
        picked = [r for _, r in ranked[:limit]]
    else:
        picked = [r for _, r, _, _, _ in scored[:limit]]

    if len(picked) < limit:
        for row in filtered:
            if len(picked) >= limit:
                break
            picked.append(row)

    if geocache_dirty:
        save_geocode_cache(geocache)

    items: list[WasteObjectOut] = []
    for row in picked:
        la, lo, approx_only = _resolve_coords_for_distance(row, geocache)
        dist_air: float | None = None
        dist_road: float | None = None
        road_error: str | None = None
        spread_km: float | None = None
        spread_note: str | None = None
        note: str | None = None
        if la is not None:
            k = id(row)
            if road_mode:
                dist_air = round(air_distance_by_row.get(k, haversine_km(ulat, ulon, la, lo)), 1)
                if k in road_distance_by_row:
                    dist_road = round(road_distance_by_row[k], 1)
                    spread_km, spread_note = _distance_spread_km(dist_road, approx_only, by_road=True)
                elif k in road_error_by_row:
                    road_error = road_error_by_row[k]
                    spread_km, spread_note = _distance_spread_km(dist_air, approx_only, by_road=False)
                note = note_by_row.get(k)
            else:
                dist_air = round(haversine_km(ulat, ulon, la, lo), 1)
                spread_km, spread_note = _distance_spread_km(dist_air, approx_only, by_road=False)
                if approx_only:
                    note = _DISTANCE_NOTE_APPROX
        items.append(
            _row_to_out(
                row,
                distance_air_km=dist_air,
                distance_road_km=dist_road,
                distance_road_error=road_error,
                distance_spread_km=spread_km,
                distance_spread_note=spread_note,
                distance_note=note,
            )
        )

    return ObjectSearchResponse(items=items)


def _row_to_out(
    row: dict[str, Any],
    distance_air_km: float | None = None,
    distance_road_km: float | None = None,
    distance_road_error: str | None = None,
    distance_spread_km: float | None = None,
    distance_spread_note: str | None = None,
    distance_note: str | None = None,
) -> WasteObjectOut:
    addr_s = str(row.get("address") or "").strip()
    ph_s = str(row.get("phones") or "").strip()
    wc = row.get("waste_code")
    waste_code = None if wc is None or wc == "" else str(wc)
    wtn = row.get("waste_type_name")
    waste_type_name = None if wtn is None or wtn == "" else str(wtn)
    return WasteObjectOut(
        id=int(row["id"]),
        owner=str(row.get("owner") or ""),
        object_name=str(row.get("object_name") or ""),
        address=addr_s or None,
        phones=ph_s or None,
        waste_code=waste_code,
        waste_type_name=waste_type_name,
        accepts_external_waste=bool(row.get("accepts_external_waste", True)),
        distance_km=distance_road_km if distance_road_km is not None else distance_air_km,
        distance_air_km=distance_air_km,
        distance_road_km=distance_road_km,
        distance_road_error=distance_road_error,
        distance_is_approx=True,
        distance_spread_km=distance_spread_km,
        distance_spread_note=distance_spread_note,
        distance_note=distance_note,
    )
