from __future__ import annotations

import json
import threading
import traceback
from pathlib import Path
from typing import Any
from typing import Callable

from oeg.storage.io import ensure_directory
from oeg.storage.io import timestamp_id
from oeg.storage.io import utc_now_iso
from oeg.storage.io import write_json

from apps.api.models import JobStatusResponse


class JobRegistry:
    def __init__(self, root: Path) -> None:
        self.root = ensure_directory(root)
        self._lock = threading.Lock()
        self._jobs: dict[str, JobStatusResponse] = {}

    def create_job(self, job_type: str, request_payload: dict[str, Any]) -> JobStatusResponse:
        job = JobStatusResponse(
            id=timestamp_id(f"job_{job_type}"),
            job_type=job_type,
            status="queued",
            submitted_at=utc_now_iso(),
            request_payload=request_payload,
        )
        with self._lock:
            self._jobs[job.id] = job
        self._persist(job)
        return job

    def start_job(self, job: JobStatusResponse, runner: Callable[[], dict[str, Any]]) -> None:
        thread = threading.Thread(target=self._run_job, args=(job.id, runner), daemon=True)
        thread.start()

    def get_job(self, job_id: str) -> JobStatusResponse | None:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is not None:
            return job

        path = self.root / f"{job_id}.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        job = JobStatusResponse.model_validate(payload)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def _run_job(self, job_id: str, runner: Callable[[], dict[str, Any]]) -> None:
        self._update_job(job_id, status="running", started_at=utc_now_iso(), error=None)
        try:
            result = runner()
        except Exception as exc:
            self._update_job(
                job_id,
                status="failed",
                completed_at=utc_now_iso(),
                error=f"{exc}\n{traceback.format_exc()}",
            )
            return

        self._update_job(
            job_id,
            status="succeeded",
            completed_at=utc_now_iso(),
            result=result,
            error=None,
        )

    def _update_job(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            updated = job.model_copy(update=fields)
            self._jobs[job_id] = updated
        self._persist(updated)

    def _persist(self, job: JobStatusResponse) -> None:
        write_json(self.root / f"{job.id}.json", job)
