import json
import logging

from app.infra.app_logging import JsonStreamFormatter


def test_json_stream_formatter_includes_extra_job_id() -> None:
    fmt = JsonStreamFormatter()
    record = logging.LogRecord(
        name="app.services.registry_import.job_runner",
        level=logging.INFO,
        pathname="x.py",
        lineno=1,
        msg="done %s",
        args=(3,),
        exc_info=None,
    )
    record.job_id = "abc-123"
    line = fmt.format(record)
    data = json.loads(line)
    assert data["message"] == "done 3"
    assert data["job_id"] == "abc-123"
    assert data["level"] == "INFO"
