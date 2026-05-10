"""
Фон импорта реестра: публичный модуль-фасад.

Реализация разнесена по пакету `app.services.registry_import` (очередь, OCR, PDF, парсинг, геокодирование).
"""

from app.services.registry_import import (
    _collect_selector_telemetry,
    _extract_text_from_image_bytes,
    _is_address_geocode_candidate,
    _set_job,
    create_job,
    enqueue_existing_job,
    enqueue_job,
    get_job,
    run_registry_import_job,
)

__all__ = [
    "create_job",
    "enqueue_existing_job",
    "enqueue_job",
    "get_job",
    "run_registry_import_job",
    "_set_job",
    "_extract_text_from_image_bytes",
    "_is_address_geocode_candidate",
    "_collect_selector_telemetry",
]
