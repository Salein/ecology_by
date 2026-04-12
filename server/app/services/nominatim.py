import httpx

from app.config import settings


def forward_geocode_sync(query: str) -> tuple[float, float] | None:
    """Прямое геокодирование (синхронно). Для Беларуси добавляется уточнение страны."""
    q = (query or "").strip()
    if len(q) < 4:
        return None
    if "беларус" not in q.casefold() and "belarus" not in q.casefold():
        q = f"{q}, Беларусь"
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": q,
        "format": "json",
        "limit": 1,
        "accept-language": "ru",
        "countrycodes": "by",
    }
    headers = {"User-Agent": settings.nominatim_user_agent}
    with httpx.Client(timeout=25.0) as client:
        r = client.get(url, params=params, headers=headers)
        r.raise_for_status()
        data = r.json()
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"])


def forward_geocode_sync_relaxed(query: str) -> tuple[float, float] | None:
    """
    Второй шаг при поиске расстояний: без countrycodes=by (часть адресов из реестра не находится в привязке только к BY).
    """
    q = (query or "").strip()
    if len(q) < 4:
        return None
    if "беларус" not in q.casefold() and "belarus" not in q.casefold():
        q = f"{q}, Беларусь"
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": q,
        "format": "json",
        "limit": 1,
        "accept-language": "ru",
    }
    headers = {"User-Agent": settings.nominatim_user_agent}
    try:
        with httpx.Client(timeout=25.0) as client:
            r = client.get(url, params=params, headers=headers)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return None
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"])


async def reverse_geocode(lat: float, lon: float) -> str | None:
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {"lat": lat, "lon": lon, "format": "json", "accept-language": "ru"}
    headers = {"User-Agent": settings.nominatim_user_agent}
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url, params=params, headers=headers)
        r.raise_for_status()
        data = r.json()
    return data.get("display_name")


async def search_places(q: str, limit: int = 5) -> list[dict]:
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": q, "format": "json", "limit": limit, "accept-language": "ru"}
    headers = {"User-Agent": settings.nominatim_user_agent}
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url, params=params, headers=headers)
        r.raise_for_status()
        return r.json()
