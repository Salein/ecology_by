import anyio

from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.schemas import ObjectSearchRequest, ObjectSearchResponse
from app.services.auth_users import UserRecord
from app.services.object_search import run_object_search

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
