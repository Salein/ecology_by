from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.infra.app_logging import configure_app_logging
from app.domains.auth.service import ensure_bootstrap_owner_account
from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.geocode import router as geocode_router
from app.routers.objects import router as objects_router
from app.routers.pdf import router as pdf_router
from app.routers.registry import router as registry_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_app_logging()
    if settings.bootstrap_owner_email and settings.bootstrap_owner_password:
        ensure_bootstrap_owner_account(
            settings.bootstrap_owner_email,
            settings.bootstrap_owner_password,
        )
    yield


app = FastAPI(title=settings.api_title, version="1.0.0", lifespan=lifespan)

_cors_kw: dict = {
    "allow_origins": settings.cors_origins,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
if settings.cors_origin_regex:
    _cors_kw["allow_origin_regex"] = settings.cors_origin_regex
app.add_middleware(CORSMiddleware, **_cors_kw)

_auth_admin = APIRouter()
_auth_admin.include_router(auth_router)
_auth_admin.include_router(admin_router)
app.include_router(_auth_admin, prefix="/api/v1")
app.include_router(objects_router, prefix="/api/v1")
app.include_router(geocode_router, prefix="/api/v1")
app.include_router(pdf_router, prefix="/api/v1")
app.include_router(registry_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}
