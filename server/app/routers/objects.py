import anyio

from fastapi import APIRouter, Depends, Query

from app.core.security import get_current_user
from app.schemas import ObjectSearchRequest, ObjectSearchResponse
from app.domains.auth.service import UserRecord
from app.domains.search.service import run_object_search, suggest_waste_variants

router = APIRouter(prefix="/objects", tags=["objects"])


def _run_search_in_thread(
    lat: float | None,
    lon: float | None,
    query: str,
    waste_code: str | None,
) -> ObjectSearchResponse:
    """Примитивы вместо Pydantic-модели — надёжнее для anyio.to_thread.run_sync."""
    return run_object_search(
        ObjectSearchRequest(lat=lat, lon=lon, query=query or "", waste_code=waste_code),
    )


@router.post("/search", response_model=ObjectSearchResponse)
async def search_objects(
    body: ObjectSearchRequest,
    _: UserRecord = Depends(get_current_user),
) -> ObjectSearchResponse:
    return await anyio.to_thread.run_sync(
        _run_search_in_thread,
        body.lat,
        body.lon,
        body.query,
        body.waste_code,
    )


@router.get("/waste-suggest")
async def waste_suggest(
    q: str = Query("", min_length=0, max_length=120),
    limit: int = Query(12, ge=1, le=30),
    _: UserRecord = Depends(get_current_user),
):
    items = await anyio.to_thread.run_sync(suggest_waste_variants, q, limit)
    return {"items": items}
