"""
Поиск по кэшу реестра: расстояние до выбранной точки — по формуле Haversine.
Координаты объекта: из записи реестра, из geocode_cache или запрос к Nominatim по полю address
(оценка по адресу, не точное измерение).

Без координат пользователя — в выборку попадают все совпадения по запросу (полный реестр в БД).
С координатами — ранжирование и добор до лимита только среди записей, где accepts_external_waste
не False (в БД после импорта False только при явной отметке «не принимает» в тексте карточки).
"""

from __future__ import annotations

import logging
import time
import threading
from typing import Any

import httpx

from app.config import settings
from app.schemas import ObjectSearchRequest, ObjectSearchResponse, WasteObjectOut
from app.services.belarus_locality_centroids import approx_coords_from_by_text, approx_coords_from_locality_in_address
from app.services.distance import haversine_km
from app.services.nominatim import forward_geocode_sync, forward_geocode_sync_relaxed
from app.services.user_registry_cache import (
    load_geocode_cache_subset,
    load_search_records,
    load_search_records_prefilter,
    load_search_records_text_prefilter,
    save_geocode_cache,
)

logger = logging.getLogger(__name__)


def _normalize_addr_key(s: str) -> str:
    s = " ".join((s or "").replace("\xa0", " ").split()).casefold()
    return s[:280]


def _row_accepts_external_waste(row: dict[str, Any]) -> bool:
    """Совпадает с полем в ответе API: False — не принимает от других; без ключа — True (старые записи)."""
    v = row.get("accepts_external_waste", True)
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().casefold()
        if s in ("false", "0", "no", "n", "нет", "не принимает", "off"):
            return False
        if s in ("true", "1", "yes", "y", "да", "принимает", "on"):
            return True
    return bool(v)


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


def _address_key_from_row(row: dict[str, Any]) -> str | None:
    addr = str(row.get("address") or "").strip()
    if len(addr) < 4:
        return None
    return _normalize_addr_key(addr)


def _norm_text(v: object) -> str:
    return " ".join(str(v or "").replace("\xa0", " ").split()).casefold()


def _search_row_key(row: dict[str, Any]) -> tuple[object, ...]:
    """
    Ключ дедупликации выдачи поиска.
    Убирает полностью повторяющиеся записи, которые могут появляться в кэше после повторных импортов.
    """
    rid: int | None
    part: int | None
    try:
        rid = int(row.get("id")) if row.get("id") is not None else None
    except (TypeError, ValueError):
        rid = None
    try:
        part = int(row.get("source_part")) if row.get("source_part") is not None else None
    except (TypeError, ValueError):
        part = None
    return (
        part,
        rid,
        _norm_text(row.get("waste_code")),
        _norm_text(row.get("owner")),
        _norm_text(row.get("object_name")),
        _norm_text(row.get("address")),
        _norm_text(row.get("phones")),
    )


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
_MAX_COORD_CITY_DEVIATION_KM = 120.0
_WARMUP_LOCK = threading.Lock()
_WARMUP_IN_PROGRESS = False
_WARMUP_COOLDOWN_SEC = 12.0
_WARMUP_LAST_STARTED_AT = 0.0


def _resolve_coords_for_distance(
    row: dict[str, Any], geocache: dict[str, dict[str, float]]
) -> tuple[float | None, float | None, bool]:
    """Координаты для расчёта расстояния: реестр / кэш геокода / справочник НП РБ. Третий флаг — только справочник."""
    la, lo = _resolve_coords_no_network(row, geocache)
    addr = str(row.get("address") or "").strip()
    oname = str(row.get("object_name") or "").strip()
    owner = str(row.get("owner") or "").strip()
    # Строгий ориентир по явному маркеру населённого пункта в адресе (г./аг./д.).
    city_ap = approx_coords_from_locality_in_address(addr) or approx_coords_from_locality_in_address(owner)
    ap = city_ap or approx_coords_from_by_text(addr, f"{oname} {owner}".strip())

    # Санити-чек: если координаты из БД/кэша слишком далеко от населённого пункта из адреса,
    # считаем их недостоверными и используем адресный ориентир.
    if la is not None and ap:
        ala, alo = float(ap[0]), float(ap[1])
        if haversine_km(float(la), float(lo), ala, alo) > _MAX_COORD_CITY_DEVIATION_KM:
            return ala, alo, True
    if la is not None:
        return la, lo, False
    if ap:
        return float(ap[0]), float(ap[1]), True
    return None, None, False


def _geocode_pair_with_nominatim(
    q: str,
    delay_sec: float,
    *,
    client: httpx.Client | None = None,
) -> tuple[float, float] | None:
    """До двух запросов: строгий BY, затем без countrycodes. Пауза после каждого шага."""
    pair: tuple[float, float] | None = None
    try:
        pair = forward_geocode_sync(q, client=client)
    except Exception:
        pair = None
    time.sleep(delay_sec)
    if pair:
        return pair
    try:
        pair = forward_geocode_sync_relaxed(q, client=client)
    except Exception:
        pair = None
    return pair


def _geocode_address_into_cache(
    row: dict[str, Any],
    geocache: dict[str, dict[str, float]],
    delay_sec: float,
    *,
    client: httpx.Client | None = None,
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
        pair = _geocode_pair_with_nominatim(q, delay_sec, client=client)
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
            addr_keys = [k for k in (_address_key_from_row(r) for r in filtered_rows) if k]
            geocache = load_geocode_cache_subset(addr_keys)
            geocache_dirty = False
            updated_keys: set[str] = set()
            api_calls = 0
            with httpx.Client(
                timeout=settings.nominatim_timeout_sec,
                headers={"User-Agent": settings.nominatim_user_agent},
            ) as nominatim_client:
                for row in filtered_rows:
                    if api_calls >= max_on_demand:
                        break
                    la, lo = _resolve_coords_no_network(row, geocache)
                    if la is not None:
                        continue
                    _la, _lo, attempted, updated = _geocode_address_into_cache(
                        row,
                        geocache,
                        delay_sec,
                        client=nominatim_client,
                    )
                    if attempted:
                        api_calls += 1
                    if updated:
                        geocache_dirty = True
                        key = _address_key_from_row(row)
                        if key:
                            updated_keys.add(key)
            if geocache_dirty:
                save_geocode_cache(geocache, keys=updated_keys)
        finally:
            with _WARMUP_LOCK:
                _WARMUP_IN_PROGRESS = False

    t = threading.Thread(target=_worker, name="geocache-warmup", daemon=True)
    t.start()


def _road_distance_km(
    ulat: float,
    ulon: float,
    la: float,
    lo: float,
    *,
    client: httpx.Client | None = None,
) -> tuple[float | None, str | None]:
    base = settings.osrm_base_url
    if not base:
        return None, "OSRM не настроен"
    url = (
        f"{base}/route/v1/driving/"
        f"{ulon:.7f},{ulat:.7f};{lo:.7f},{la:.7f}"
        "?overview=false&alternatives=false&steps=false"
    )
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=settings.osrm_timeout_sec)
    try:
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
    finally:
        if own_client and client is not None:
            try:
                client.close()
            except Exception:
                pass


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


def _road_candidates_limit(total_scored: int, limit: int) -> int:
    """
    Адаптивно ограничивает число OSRM-кандидатов:
    при очень больших выборках уменьшаем сетевую нагрузку, сохраняя качество топ-N.
    """
    if total_scored <= 0:
        return 0
    base = max(limit, settings.road_distance_candidates)
    if total_scored <= base:
        return total_scored
    if total_scored >= 600:
        tuned = max(limit, min(base, limit * 2 + 4))
        return min(total_scored, tuned)
    if total_scored >= 200:
        tuned = max(limit, min(base, limit * 3 + 6))
        return min(total_scored, tuned)
    return min(total_scored, base)


def run_object_search(body: ObjectSearchRequest) -> ObjectSearchResponse:
    t0 = time.perf_counter()
    q = body.query.strip().lower()
    code = (body.waste_code or "").strip()
    location_selected = body.lat is not None and body.lon is not None
    limit = max(1, settings.registry_closest_limit)
    numeric_id_hint: int | None = None
    if q.isdigit() and 1 <= len(q) <= 6:
        try:
            numeric_id_hint = int(q)
        except ValueError:
            numeric_id_hint = None

    # Крупная оптимизация: в частых сценариях фильтруем в SQL до загрузки в память.
    sql_text_filtered = False
    if code or numeric_id_hint is not None:
        rows = load_search_records_prefilter(
            waste_code=code or None,
            record_id=numeric_id_hint,
            accepts_external_only=location_selected,
        )
    elif q:
        rows = load_search_records_text_prefilter(
            query=q,
            accepts_external_only=location_selected,
            limit=5000,
        )
        sql_text_filtered = True
    elif location_selected:
        rows = load_search_records(accepts_external_only=True)
    else:
        rows = load_search_records()
    t_fetch_rows = time.perf_counter()

    filtered: list[dict[str, Any]] = []
    for row in rows:
        if code and str(row.get("waste_code") or "") != code:
            continue
        if q and not sql_text_filtered:
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
    if filtered:
        seen_keys: set[tuple[object, ...]] = set()
        uniq: list[dict[str, Any]] = []
        max_unique = None if location_selected else limit
        for row in filtered:
            key = _search_row_key(row)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            uniq.append(row)
            if max_unique is not None and len(uniq) >= max_unique:
                break
        filtered = uniq
    t_filtered = time.perf_counter()

    delay = settings.registry_geocode_delay_sec
    max_on_demand = max(0, settings.registry_search_geocode_max)

    if body.lat is None or body.lon is None:
        picked = filtered[:limit]
        logger.debug(
            "object_search no-location q=%r code=%r rows=%d filtered=%d picked=%d fetch_ms=%d filter_ms=%d total_ms=%d",
            q,
            code,
            len(rows),
            len(filtered),
            len(picked),
            int((t_fetch_rows - t0) * 1000),
            int((t_filtered - t_fetch_rows) * 1000),
            int((time.perf_counter() - t0) * 1000),
        )
        return ObjectSearchResponse(items=[_row_to_out(r) for r in picked])

    # При выбранной точке показываем только объекты, принимающие отходы от других.
    if not (code or numeric_id_hint is not None or sql_text_filtered or not q):
        filtered = [r for r in filtered if _row_accepts_external_waste(r)]
    if not filtered:
        logger.debug(
            "object_search location-empty q=%r code=%r rows=%d fetch_ms=%d filter_ms=%d total_ms=%d",
            q,
            code,
            len(rows),
            int((t_fetch_rows - t0) * 1000),
            int((time.perf_counter() - t_fetch_rows) * 1000),
            int((time.perf_counter() - t0) * 1000),
        )
        return ObjectSearchResponse(items=[])

    ulat, ulon = float(body.lat), float(body.lon)
    addr_keys = [k for k in (_address_key_from_row(r) for r in filtered) if k]
    geocache = load_geocode_cache_subset(addr_keys)
    distance_pool = filtered

    scored: list[tuple[float, dict[str, Any], float, float, bool]] = []

    for row in distance_pool:
        la, lo, approx = _resolve_coords_for_distance(row, geocache)
        if la is None:
            continue
        d = haversine_km(ulat, ulon, la, lo)
        scored.append((d, row, la, lo, approx))

    scored.sort(key=lambda x: x[0])
    t_scored = time.perf_counter()

    # Не блокируем ответ сетью: on-demand геокодирование уходит в фон.
    _start_async_geocache_warmup(distance_pool, delay, max_on_demand)

    picked: list[dict[str, Any]] = []
    air_distance_by_row: dict[int, float] = {}
    road_distance_by_row: dict[int, float] = {}
    road_error_by_row: dict[int, str] = {}
    note_by_row: dict[int, str] = {}
    road_mode = settings.distance_mode == "road"
    osrm_checked = 0
    if road_mode and scored:
        n_candidates = _road_candidates_limit(len(scored), limit)
        ranked: list[tuple[float, dict[str, Any]]] = []
        with httpx.Client(timeout=settings.osrm_timeout_sec) as osrm_client:
            for air_d, row, la, lo, approx_only in scored[:n_candidates]:
                road_d, road_err = _road_distance_km(ulat, ulon, la, lo, client=osrm_client)
                osrm_checked += 1
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
    t_ranked = time.perf_counter()

    def _dist_row_key(r: dict[str, Any]) -> tuple[Any, Any]:
        return (r.get("id"), r.get("waste_code"))

    picked_keys = {_dist_row_key(r) for r in picked}
    if len(picked) < limit:
        for row in distance_pool:
            if len(picked) >= limit:
                break
            if _dist_row_key(row) in picked_keys:
                continue
            picked.append(row)
            picked_keys.add(_dist_row_key(row))

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
                distance_is_approx=approx_only,
            )
        )

    logger.debug(
        "object_search location q=%r code=%r rows=%d filtered=%d scored=%d picked=%d osrm_checked=%d "
        "fetch_ms=%d filter_ms=%d score_ms=%d rank_ms=%d total_ms=%d",
        q,
        code,
        len(rows),
        len(filtered),
        len(scored),
        len(items),
        osrm_checked,
        int((t_fetch_rows - t0) * 1000),
        int((t_filtered - t_fetch_rows) * 1000),
        int((t_scored - t_filtered) * 1000),
        int((t_ranked - t_scored) * 1000),
        int((time.perf_counter() - t0) * 1000),
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
    distance_is_approx: bool = False,
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
        distance_is_approx=distance_is_approx,
        distance_spread_km=distance_spread_km,
        distance_spread_note=distance_spread_note,
        distance_note=distance_note,
    )
