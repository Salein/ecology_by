from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import admin, auth, geocode, objects, pdf, registry
from app.services.auth_users import ensure_bootstrap_owner_account


@asynccontextmanager
async def lifespan(app: FastAPI):
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

app.include_router(auth.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(objects.router, prefix="/api/v1")
app.include_router(geocode.router, prefix="/api/v1")
app.include_router(pdf.router, prefix="/api/v1")
app.include_router(registry.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}
