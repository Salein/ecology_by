import httpx

from app.config import settings


def _nominatim_search_url() -> str:
    return f"{settings.nominatim_base_url}/search"


def _nominatim_reverse_url() -> str:
    return f"{settings.nominatim_base_url}/reverse"


def forward_geocode_sync(query: str, *, client: httpx.Client | None = None) -> tuple[float, float] | None:
    """Прямое геокодирование (синхронно). Для Беларуси добавляется уточнение страны."""
    q = (query or "").strip()
    if len(q) < 4:
        return None
    if "беларус" not in q.casefold() and "belarus" not in q.casefold():
        q = f"{q}, Беларусь"
    url = _nominatim_search_url()
    params = {
        "q": q,
        "format": "json",
        "limit": 1,
        "accept-language": "ru",
        "countrycodes": "by",
    }
    headers = {"User-Agent": settings.nominatim_user_agent}
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=settings.nominatim_timeout_sec, headers=headers)
    try:
        r = client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
    finally:
        if own_client:
            client.close()
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"])


def forward_geocode_sync_relaxed(query: str, *, client: httpx.Client | None = None) -> tuple[float, float] | None:
    """
    Второй шаг при поиске расстояний: без countrycodes=by (часть адресов из реестра не находится в привязке только к BY).
    """
    q = (query or "").strip()
    if len(q) < 4:
        return None
    if "беларус" not in q.casefold() and "belarus" not in q.casefold():
        q = f"{q}, Беларусь"
    url = _nominatim_search_url()
    params = {
        "q": q,
        "format": "json",
        "limit": 1,
        "accept-language": "ru",
    }
    headers = {"User-Agent": settings.nominatim_user_agent}
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=settings.nominatim_timeout_sec, headers=headers)
    try:
        r = client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None
    finally:
        if own_client:
            client.close()
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"])


async def reverse_geocode(lat: float, lon: float) -> str | None:
    url = _nominatim_reverse_url()
    params = {"lat": lat, "lon": lon, "format": "json", "accept-language": "ru"}
    headers = {"User-Agent": settings.nominatim_user_agent}
    async with httpx.AsyncClient(timeout=settings.nominatim_timeout_sec) as client:
        r = await client.get(url, params=params, headers=headers)
        r.raise_for_status()
        data = r.json()
    return data.get("display_name")


async def search_places(q: str, limit: int = 5) -> list[dict]:
    url = _nominatim_search_url()
    params = {"q": q, "format": "json", "limit": limit, "accept-language": "ru"}
    headers = {"User-Agent": settings.nominatim_user_agent}
    async with httpx.AsyncClient(timeout=settings.nominatim_timeout_sec) as client:
        r = await client.get(url, params=params, headers=headers)
        r.raise_for_status()
        return r.json()
