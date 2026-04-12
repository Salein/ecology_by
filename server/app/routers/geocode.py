from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import get_current_user
from app.services.auth_users import UserRecord
from app.services.nominatim import reverse_geocode, search_places

router = APIRouter(prefix="/geocode", tags=["geocode"])


@router.get("/reverse")
async def reverse(
    lat: float = Query(...),
    lon: float = Query(...),
    _: UserRecord = Depends(get_current_user),
):
    """
    Всегда 200 + display_name (строка или null), чтобы фронт не ловил 502/404 в консоли
    при сбоях Nominatim или пустом ответе — подпись к точке можно показать по координатам.
    """
    try:
        name = await reverse_geocode(lat, lon)
    except Exception:
        name = None
    if not name:
        return {"display_name": None}
    return {"display_name": name}


@router.get("/search")
async def search(
    q: str = Query(..., min_length=2),
    limit: int = Query(5, ge=1, le=10),
    _: UserRecord = Depends(get_current_user),
):
    try:
        results = await search_places(q, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {
        "results": [
            {
                "display_name": r.get("display_name"),
                "lat": float(r["lat"]),
                "lon": float(r["lon"]),
            }
            for r in results
            if r.get("lat") and r.get("lon")
        ]
    }
