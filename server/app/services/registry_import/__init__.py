"""Модульная реализация фонового импорта реестра (очередь, OCR/PDF, парсинг, геокодирование)."""

from app.services.registry_import.geocode_filters import _is_address_geocode_candidate
from app.services.registry_import.job_runner import run_registry_import_job
from app.services.registry_import.llm_row_merge import _collect_selector_telemetry
from app.services.registry_import.ocr import _extract_text_from_image_bytes
from app.services.registry_import.queue import (
    _set_job,
    create_job,
    enqueue_existing_job,
    enqueue_job,
    get_job,
    registry_import_in_progress,
)

__all__ = [
    "create_job",
    "enqueue_existing_job",
    "enqueue_job",
    "get_job",
    "registry_import_in_progress",
    "run_registry_import_job",
    "_set_job",
    "_extract_text_from_image_bytes",
    "_is_address_geocode_candidate",
    "_collect_selector_telemetry",
]
