"""Очередь фоновых задач импорта реестра."""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from typing import Any

_jobs_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}
_job_payloads: dict[str, tuple[list[tuple[str, bytes]], str, str]] = {}
_job_queue: deque[str] = deque()
_queue_worker_lock = threading.Lock()
_queue_worker_started = False
_completed_job_sec: deque[float] = deque(maxlen=24)


def _set_job(job_id: str, **kwargs: Any) -> None:
    with _jobs_lock:
        cur = _jobs.setdefault(job_id, {})
        if kwargs and all(cur.get(k) == v for k, v in kwargs.items()):
            return
        cur.update(kwargs)


def get_job(job_id: str) -> dict[str, Any] | None:
    with _jobs_lock:
        j = _jobs.get(job_id)
        return dict(j) if j else None


def registry_import_in_progress() -> bool:
    """True, пока на сервере есть задача импорта в очереди или в работе (для UI у других пользователей)."""
    with _jobs_lock:
        for j in _jobs.values():
            st = str(j.get("status") or "").strip().lower()
            if st in {"done", "error"}:
                continue
            if st in {"queued", "running"}:
                return True
        return False


def _queue_snapshot_locked(current_job_id: str | None = None) -> dict[str, Any]:
    queued = list(_job_queue)
    size = len(queued) + (1 if current_job_id else 0)
    pos_by_job: dict[str, int] = {}
    for i, jid in enumerate(queued, start=1):
        pos_by_job[jid] = i
    return {"size": size, "positions": pos_by_job}


def _avg_job_sec_locked() -> int:
    if not _completed_job_sec:
        return 180
    return max(30, int(sum(_completed_job_sec) / len(_completed_job_sec)))


def _refresh_queue_metrics_locked(current_job_id: str | None = None) -> None:
    snap = _queue_snapshot_locked(current_job_id)
    avg_job_sec = _avg_job_sec_locked()
    for jid, j in _jobs.items():
        st = str(j.get("status") or "")
        if st in {"done", "error"}:
            continue
        m = dict(j.get("metrics") or {})
        if jid == current_job_id and st == "running":
            m["queue_position"] = 0
            m["queue_eta_sec"] = 0
        else:
            pos = int(snap["positions"].get(jid, 0))
            m["queue_position"] = pos
            m["queue_eta_sec"] = pos * avg_job_sec
        m["queue_size"] = int(snap["size"])
        m["avg_job_sec"] = avg_job_sec
        j["metrics"] = m


def _ensure_queue_worker() -> None:
    global _queue_worker_started
    with _queue_worker_lock:
        if _queue_worker_started:
            return
        _queue_worker_started = True

    def _worker() -> None:
        current_job_id: str | None = None
        while True:
            with _jobs_lock:
                if not _job_queue:
                    current_job_id = None
                    _refresh_queue_metrics_locked(current_job_id=None)
                    break
                current_job_id = _job_queue.popleft()
                job = _jobs.get(current_job_id)
                if not job:
                    _refresh_queue_metrics_locked(current_job_id=None)
                    continue
                payload = _job_payloads.get(current_job_id)
                job["status"] = "running"
                job["progress"] = 1
                job["message"] = "Задача взята в обработку…"
                job["started_at_monotonic"] = time.perf_counter()
                _refresh_queue_metrics_locked(current_job_id=current_job_id)
            try:
                if payload is not None:
                    payloads, fingerprint, import_mode = payload
                    from app.services.registry_import.job_runner import run_registry_import_job as _run_job
                    _run_job(current_job_id, payloads, fingerprint, import_mode=import_mode)
                else:
                    _set_job(
                        current_job_id,
                        status="error",
                        progress=0,
                        message="Ошибка",
                        error="IMPORT_JOB_PAYLOAD_MISSING",
                    )
            except Exception as e:
                _set_job(
                    current_job_id,
                    status="error",
                    progress=0,
                    message="Ошибка",
                    error=str(e),
                )
            finally:
                with _jobs_lock:
                    jfin = _jobs.get(current_job_id) if current_job_id else None
                    if jfin:
                        st_mono = jfin.get("started_at_monotonic")
                        if isinstance(st_mono, (int, float)):
                            dur = max(0.0, time.perf_counter() - float(st_mono))
                            if dur > 0:
                                _completed_job_sec.append(dur)
                    _job_payloads.pop(current_job_id, None)
                    _refresh_queue_metrics_locked(current_job_id=None)

        global _queue_worker_started
        with _queue_worker_lock:
            _queue_worker_started = False

    t = threading.Thread(target=_worker, name="registry-import-queue", daemon=True)
    t.start()


def create_job() -> str:
    job_id = uuid.uuid4().hex
    _set_job(
        job_id,
        status="queued",
        progress=0,
        message="В очереди…",
        error=None,
        records_count=0,
        metrics={},
    )
    return job_id


def enqueue_existing_job(
    job_id: str,
    payloads: list[tuple[str, bytes]],
    fingerprint: str,
    import_mode: str = "replace",
) -> str:
    if job_id not in _jobs:
        _set_job(
            job_id,
            status="queued",
            progress=0,
            message="В очереди…",
            error=None,
            records_count=0,
            metrics={},
        )
    _set_job(
        job_id,
        status="queued",
        progress=0,
        message="В очереди…",
        metrics={
            "stage": "queued",
            "queue_position": 0,
            "queue_size": 0,
            "queue_eta_sec": 0,
            "avg_job_sec": _avg_job_sec_locked(),
            "files_total": len(payloads),
            "files_done": 0,
            "ocr_total": 0,
            "ocr_done": 0,
            "ocr_inflight": 0,
            "ocr_workers": 0,
            "stage_done": 0,
            "stage_total": len(payloads),
            "stage_unit": "files",
        },
    )
    with _jobs_lock:
        _job_payloads[job_id] = (payloads, fingerprint, import_mode)
        _job_queue.append(job_id)
        _refresh_queue_metrics_locked(current_job_id=None)
    _ensure_queue_worker()
    return job_id


def enqueue_job(payloads: list[tuple[str, bytes]], fingerprint: str, import_mode: str = "replace") -> str:
    job_id = create_job()
    return enqueue_existing_job(job_id, payloads, fingerprint, import_mode=import_mode)
