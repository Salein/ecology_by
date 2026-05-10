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


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _split_origins(raw: str | None) -> list[str]:
    if not raw:
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    return [x.strip() for x in raw.split(",") if x.strip()]


def _cors_origin_regex() -> str | None:
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


@dataclass
class Settings:
    api_title: str = "Ecology Objects API"
    cors_origins: list[str] = field(default_factory=lambda: _split_origins(os.getenv("CORS_ORIGINS")))
    cors_origin_regex: str | None = field(default_factory=_cors_origin_regex)
    nominatim_user_agent: str = os.getenv(
        "NOMINATIM_USER_AGENT",
        "ecology-demo/1.0 (local dev; contact@example.com)",
    )
    nominatim_timeout_sec: float = float(os.getenv("NOMINATIM_TIMEOUT_SEC", "3.0"))
    nominatim_base_url: str = (os.getenv("NOMINATIM_BASE_URL") or "https://nominatim.openstreetmap.org").strip().rstrip("/")
    registry_closest_limit: int = int(os.getenv("REGISTRY_CLOSEST_LIMIT", "7"))
    registry_geocode_delay_sec: float = float(os.getenv("REGISTRY_GEOCODE_DELAY_SEC", "1.1"))
    registry_search_geocode_max: int = _int_env("REGISTRY_SEARCH_GEOCODE_MAX", 8)
    registry_import_checkpoint_every: int = _int_env("REGISTRY_IMPORT_CHECKPOINT_EVERY", 50)
    registry_import_db_checkpoint_every: int = _int_env("REGISTRY_IMPORT_DB_CHECKPOINT_EVERY", 1000)
    registry_import_db_checkpoint_max_sec: float = _float_env("REGISTRY_IMPORT_DB_CHECKPOINT_MAX_SEC", 180.0)
    registry_import_geocode_max_calls: int = _int_env("REGISTRY_IMPORT_GEOCODE_MAX_CALLS", 0)
    registry_import_max_checkpoints: int = _int_env("REGISTRY_IMPORT_MAX_CHECKPOINTS", 120)
    registry_import_checkpoint_max_sec: float = _float_env("REGISTRY_IMPORT_CHECKPOINT_MAX_SEC", 20.0)
    registry_pdf_text_backend: str = (os.getenv("REGISTRY_PDF_TEXT_BACKEND") or "pymupdf").strip().lower()
    registry_pdf_hybrid_pymupdf_min_score: int = _int_env("REGISTRY_PDF_HYBRID_PYMUPDF_MIN_SCORE", 120)
    registry_pdfplumber_page_timeout_sec: float = float(os.getenv("REGISTRY_PDFPLUMBER_PAGE_TIMEOUT_SEC", "6.0"))
    registry_llm_enabled: bool = _bool_env("REGISTRY_LLM_ENABLED", False)
    openrouter_api_key: str = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    openrouter_base_url: str = (os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").strip().rstrip("/")
    openrouter_model: str = (os.getenv("OPENROUTER_MODEL") or "qwen/qwen3.6-plus").strip()
    openrouter_fallback_model: str = (os.getenv("OPENROUTER_FALLBACK_MODEL") or "").strip()
    openrouter_system_prompt: str = (os.getenv("OPENROUTER_SYSTEM_PROMPT") or "").strip()
    openrouter_timeout_sec: float = _float_env("OPENROUTER_TIMEOUT_SEC", 80.0)
    openrouter_max_output_tokens: int = _int_env("OPENROUTER_MAX_OUTPUT_TOKENS", 16_000)
    openrouter_upscale_model: str = (os.getenv("OPENROUTER_UPSCALE_MODEL") or "qwen/qwen3.6-plus").strip()
    registry_llm_batch_min_coverage_pct: int = _int_env("REGISTRY_LLM_BATCH_MIN_COVERAGE_PCT", 80)
    registry_llm_batch_upscale_enabled: bool = _bool_env("REGISTRY_LLM_BATCH_UPSCALE_ENABLED", False)
    registry_llm_max_chars: int = _int_env("REGISTRY_LLM_MAX_CHARS", 32000)
    registry_llm_chunk_chars: int = _int_env("REGISTRY_LLM_CHUNK_CHARS", 12000)
    registry_llm_overlap_chars: int = _int_env("REGISTRY_LLM_OVERLAP_CHARS", 1000)
    # Если parse_confidence строки ниже этого порога (0–100) — строка уходит в LLM-repair (шум/сомнение парсера).
    registry_llm_repair_if_parse_confidence_below: int = _int_env("REGISTRY_LLM_REPAIR_IF_PARSE_CONFIDENCE_BELOW", 98)
    registry_search_geocode_budget_sec: float = float(os.getenv("REGISTRY_SEARCH_GEOCODE_BUDGET_SEC", "8.0"))
    distance_mode: str = (os.getenv("DISTANCE_MODE") or "road").strip().lower()
    osrm_base_url: str = (os.getenv("OSRM_BASE_URL") or "https://router.project-osrm.org").strip().rstrip("/")
    osrm_timeout_sec: float = float(os.getenv("OSRM_TIMEOUT_SEC", "2.5"))
    road_distance_candidates: int = _int_env("ROAD_DISTANCE_CANDIDATES", 25)
    jwt_secret: str = os.getenv("JWT_SECRET", "ecology-dev-change-me-in-production")
    jwt_expire_hours: int = _int_env("JWT_EXPIRE_HOURS", 168)
    auth_cookie_name: str = os.getenv("AUTH_COOKIE_NAME", "ecology_access_token")
    auth_cookie_secure: bool = os.getenv("AUTH_COOKIE_SECURE", "").lower() in ("1", "true", "yes")
    auth_cookie_samesite: CookieSameSite = field(default_factory=_cookie_samesite)
    bootstrap_owner_email: str = (os.getenv("BOOTSTRAP_OWNER_EMAIL") or "eug.kulish@gmail.com").strip().lower()
    bootstrap_owner_password: str = (os.getenv("BOOTSTRAP_OWNER_PASSWORD") or "Bagamol42").strip()
    database_url: str = (os.getenv("DATABASE_URL") or "postgresql+psycopg://postgres:postgres@localhost:5432/ecology").strip()
    database_echo: bool = os.getenv("DATABASE_ECHO", "").lower() in ("1", "true", "yes")
    database_pool_size: int = _int_env("DATABASE_POOL_SIZE", 10)
    database_max_overflow: int = _int_env("DATABASE_MAX_OVERFLOW", 20)
    # Одна JSON-строка на событие для логгера `app` (удобно для Loki/ELK); импорт реестра добавляет job_id.
    log_json: bool = _bool_env("LOG_JSON", False)

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

__all__ = ["Settings", "settings"]
