from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Literal


def _try_load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except ImportError:
        pass


_try_load_dotenv()


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return max(0, int(str(raw).strip(), 10))
    except ValueError:
        return default


def _split_origins(raw: str | None) -> list[str]:
    if not raw:
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    return [x.strip() for x in raw.split(",") if x.strip()]


CookieSameSite = Literal["lax", "strict", "none"]


def _cookie_samesite() -> CookieSameSite:
    v = (os.getenv("AUTH_COOKIE_SAMESITE") or "lax").strip().lower()
    if v in ("lax", "strict", "none"):
        return v  # type: ignore[return-value]
    return "lax"


@dataclass
class Settings:
    api_title: str = "Ecology Objects API"
    cors_origins: list[str] = field(
        default_factory=lambda: _split_origins(os.getenv("CORS_ORIGINS"))
    )
    nominatim_user_agent: str = os.getenv(
        "NOMINATIM_USER_AGENT",
        "ecology-demo/1.0 (local dev; contact@example.com)",
    )
    nominatim_timeout_sec: float = float(os.getenv("NOMINATIM_TIMEOUT_SEC", "3.0"))
    registry_closest_limit: int = int(os.getenv("REGISTRY_CLOSEST_LIMIT", "7"))
    registry_geocode_delay_sec: float = float(os.getenv("REGISTRY_GEOCODE_DELAY_SEC", "1.1"))
    # За один поиск — не больше запросов к Nominatim по адресам без координат (остальные без расстояния)
    registry_search_geocode_max: int = _int_env("REGISTRY_SEARCH_GEOCODE_MAX", 8)
    # Общий бюджет времени на on-demand геокодирование в одном поиске
    registry_search_geocode_budget_sec: float = float(os.getenv("REGISTRY_SEARCH_GEOCODE_BUDGET_SEC", "8.0"))
    # JWT (в продакшене задайте свой секрет)
    jwt_secret: str = os.getenv("JWT_SECRET", "ecology-dev-change-me-in-production")
    jwt_expire_hours: int = _int_env("JWT_EXPIRE_HOURS", 168)
    # HttpOnly cookie с JWT (не отдаём токен в JSON — только Set-Cookie)
    auth_cookie_name: str = os.getenv("AUTH_COOKIE_NAME", "ecology_access_token")
    # Для HTTPS в продакшене: AUTH_COOKIE_SECURE=1
    auth_cookie_secure: bool = os.getenv("AUTH_COOKIE_SECURE", "").lower() in ("1", "true", "yes")
    # Для фронта на другом домене (Vercel/Netlify + API по публичному URL): none + AUTH_COOKIE_SECURE=1
    auth_cookie_samesite: CookieSameSite = field(default_factory=_cookie_samesite)
    # При старте API: гарантировать владельца-админа (пароль лучше переопределить в .env / переменных на проде)
    bootstrap_owner_email: str = (
        os.getenv("BOOTSTRAP_OWNER_EMAIL") or "eug.kulish@gmail.com"
    ).strip().lower()
    bootstrap_owner_password: str = (os.getenv("BOOTSTRAP_OWNER_PASSWORD") or "Bagamol42").strip()
    database_url: str = (
        os.getenv("DATABASE_URL")
        or "postgresql+psycopg://postgres:postgres@localhost:5432/ecology"
    ).strip()
    database_echo: bool = os.getenv("DATABASE_ECHO", "").lower() in ("1", "true", "yes")
    database_pool_size: int = _int_env("DATABASE_POOL_SIZE", 10)
    database_max_overflow: int = _int_env("DATABASE_MAX_OVERFLOW", 20)


settings = Settings()
