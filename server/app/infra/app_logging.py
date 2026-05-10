"""Настройка логирования приложения (опционально JSON для прод-наблюдаемости)."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from app.core.config import settings

_CONFIGURED = False

# Поля стандартного LogRecord — всё остальное в __dict__ считаем контекстом (например job_id).
_STANDARD_LOGRECORD_KEYS = frozenset(
    {
        "name",
        "msg",
        "args",
        "created",
        "msecs",
        "relativeCreated",
        "levelno",
        "levelname",
        "pathname",
        "filename",
        "module",
        "lineno",
        "funcName",
        "exc_text",
        "exc_info",
        "stack_info",
        "process",
        "processName",
        "thread",
        "threadName",
        "message",
        "taskName",
    }
)


class JsonStreamFormatter(logging.Formatter):
    """Одна строка JSON на событие; поля из `extra=` / LoggerAdapter попадают в корень объекта."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        payload: dict[str, object] = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, val in record.__dict__.items():
            if key in _STANDARD_LOGRECORD_KEYS or key.startswith("_"):
                continue
            payload[key] = val
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str) + "\n"


def configure_app_logging() -> None:
    """Вешает JSON-handler на логгер `app`, чтобы не дублировать с корнем и не смешивать с uvicorn."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True
    if not settings.log_json:
        return
    app_log = logging.getLogger("app")
    if app_log.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonStreamFormatter())
    app_log.addHandler(handler)
    app_log.setLevel(logging.INFO)
    app_log.propagate = False
