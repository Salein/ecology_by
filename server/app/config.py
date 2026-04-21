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


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return max(0.0, float(str(raw).strip()))
    except ValueError:
        return default


def _split_origins(raw: str | None) -> list[str]:
    if not raw:
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    return [x.strip() for x in raw.split(",") if x.strip()]


def _cors_origin_regex() -> str | None:
    """Доп. Origin по regex (например quick Cloudflare Tunnel). См. CORS_ORIGIN_REGEX / CORS_RELAX_TRY_TUNNEL."""
    explicit = (os.getenv("CORS_ORIGIN_REGEX") or "").strip()
    if explicit:
        return explicit
    v = os.getenv("CORS_RELAX_TRY_TUNNEL")
    if v is None:
        return None
    if str(v).strip().lower() in ("0", "false", "no"):
        return None
    return r"^https://[a-zA-Z0-9-]+\.trycloudflare\.com$"


CookieSameSite = Literal["lax", "strict", "none"]


def _cookie_samesite() -> CookieSameSite:
    v = (os.getenv("AUTH_COOKIE_SAMESITE") or "lax").strip().lower()
    if v in ("lax", "strict", "none"):
        return v  # type: ignore[return-value]
    return "lax"


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    api_title: str = "Ecology Objects API"
    cors_origins: list[str] = field(
        default_factory=lambda: _split_origins(os.getenv("CORS_ORIGINS"))
    )
    cors_origin_regex: str | None = field(default_factory=_cors_origin_regex)
    nominatim_user_agent: str = os.getenv(
        "NOMINATIM_USER_AGENT",
        "ecology-demo/1.0 (local dev; contact@example.com)",
    )
    nominatim_timeout_sec: float = float(os.getenv("NOMINATIM_TIMEOUT_SEC", "3.0"))
    # Свой Nominatim (Docker) — можно снизить REGISTRY_GEOCODE_DELAY_SEC до 0.
    nominatim_base_url: str = (
        os.getenv("NOMINATIM_BASE_URL") or "https://nominatim.openstreetmap.org"
    ).strip().rstrip("/")
    registry_closest_limit: int = int(os.getenv("REGISTRY_CLOSEST_LIMIT", "7"))
    # Минимум секунд между запросами к публичному Nominatim (учитывается время самого HTTP-запроса).
    registry_geocode_delay_sec: float = float(os.getenv("REGISTRY_GEOCODE_DELAY_SEC", "1.1"))
    # За один поиск — не больше запросов к Nominatim по адресам без координат (остальные без расстояния)
    registry_search_geocode_max: int = _int_env("REGISTRY_SEARCH_GEOCODE_MAX", 8)
    # Во время импорта реестра сохраняем промежуточный прогресс каждые N записей.
    # Это позволяет не терять уже обработанные записи при аварийной остановке сервиса.
    registry_import_checkpoint_every: int = _int_env("REGISTRY_IMPORT_CHECKPOINT_EVERY", 50)
    # Тяжёлый чекпоинт (полная фиксация частичного реестра в БД) — реже, чтобы снизить I/O.
    registry_import_db_checkpoint_every: int = _int_env("REGISTRY_IMPORT_DB_CHECKPOINT_EVERY", 1000)
    # Дополнительный триггер тяжёлого чекпоинта по времени (сек). 0 — отключить.
    registry_import_db_checkpoint_max_sec: float = _float_env("REGISTRY_IMPORT_DB_CHECKPOINT_MAX_SEC", 180.0)
    # Soft-budget внешних вызовов Nominatim за один импорт (0 — без лимита).
    registry_import_geocode_max_calls: int = _int_env("REGISTRY_IMPORT_GEOCODE_MAX_CALLS", 0)
    # Верхняя оценка количества чекпоинтов на один импорт (адаптивный шаг по размеру импорта).
    registry_import_max_checkpoints: int = _int_env("REGISTRY_IMPORT_MAX_CHECKPOINTS", 120)
    # Дополнительный триггер чекпоинта по времени (сек). 0 — отключить.
    registry_import_checkpoint_max_sec: float = _float_env("REGISTRY_IMPORT_CHECKPOINT_MAX_SEC", 20.0)
    # Извлечение текста из PDF реестра: pymupdf обычно быстрее и не зависает на «тяжёлых» страницах pdfplumber.
    # pdfplumber — прежнее поведение; pymupdf — по умолчанию.
    registry_pdf_text_backend: str = (os.getenv("REGISTRY_PDF_TEXT_BACKEND") or "pymupdf").strip().lower()
    # Таймаут (сек) на одну страницу pdfplumber при fallback-извлечении.
    # Если страница «залипла», пропускаем только её, а не весь файл.
    registry_pdfplumber_page_timeout_sec: float = float(
        os.getenv("REGISTRY_PDFPLUMBER_PAGE_TIMEOUT_SEC", "6.0")
    )
    # Общий бюджет времени на on-demand геокодирование в одном поиске
    registry_search_geocode_budget_sec: float = float(os.getenv("REGISTRY_SEARCH_GEOCODE_BUDGET_SEC", "8.0"))
    # Режим дистанции: road (по дорогам, OSRM) или air (по прямой, Haversine)
    distance_mode: str = (os.getenv("DISTANCE_MODE") or "road").strip().lower()
    # OSRM endpoint для расчёта дистанции по дорогам
    osrm_base_url: str = (
        os.getenv("OSRM_BASE_URL") or "https://router.project-osrm.org"
    ).strip().rstrip("/")
    osrm_timeout_sec: float = float(os.getenv("OSRM_TIMEOUT_SEC", "2.5"))
    # Сколько кандидатов максимум проверять роутингом за один поиск
    road_distance_candidates: int = _int_env("ROAD_DISTANCE_CANDIDATES", 25)
    # LLM fallback для особо проблемных PDF-сегментов (селективно, не основной парсер).
    llm_fallback_enabled: bool = _bool_env("LLM_FALLBACK_ENABLED", False)
    llm_fallback_shadow_mode: bool = _bool_env("LLM_FALLBACK_SHADOW_MODE", True)
    llm_fallback_timeout_sec: float = _float_env("LLM_FALLBACK_TIMEOUT_SEC", 20.0)
    llm_fallback_max_calls_per_import: int = _int_env("LLM_FALLBACK_MAX_CALLS_PER_IMPORT", 60)
    llm_fallback_chunk_records: int = _int_env("LLM_FALLBACK_CHUNK_RECORDS", 2)
    llm_fallback_max_retries: int = _int_env("LLM_FALLBACK_MAX_RETRIES", 2)
    llm_fallback_openrouter_base_url: str = (
        os.getenv("LLM_FALLBACK_OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1"
    ).strip().rstrip("/")
    llm_fallback_openrouter_model: str = (
        os.getenv("LLM_FALLBACK_OPENROUTER_MODEL") or "google/gemini-2.0-flash-exp:free"
    ).strip()
    llm_fallback_openrouter_api_key: str = (os.getenv("OPENROUTER_API_KEY") or "").strip()
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

    def __post_init__(self) -> None:
        extra_origin = (os.getenv("PUBLIC_ORIGIN") or "").strip()
        if extra_origin:
            seen = {x.strip() for x in self.cors_origins}
            if extra_origin not in seen:
                self.cors_origins = [*self.cors_origins, extra_origin]
        key_len = len(self.jwt_secret.encode("utf-8"))
        if key_len < 32:
            raise ValueError(
                "JWT_SECRET must be at least 32 bytes for HS256 (RFC 7518). "
                f"Current length is {key_len}."
            )


settings = Settings()
