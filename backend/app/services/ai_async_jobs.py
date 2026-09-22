"""Registro de jobs assíncronos de IA para a primeira fatia do W8.2.

O armazenamento em memória é deliberadamente experimental e fica atrás de
feature flag. A implementação estabelece o contrato de estados, idempotência,
ownership e TTL antes de introduzir Redis/Celery ou alterar o proxy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import threading
import time
from typing import Any

from fastapi import HTTPException


TERMINAL = {"completed", "failed", "cancelled"}


@dataclass
class AIAsyncJob:
    task_id: str
    request_id: str
    user_id: str
    case_id: str | None
    created_at: str
    created_ts: float
    status: str = "queued"
    result: Any = None
    error: str | None = None
    updated_ts: float = field(default_factory=time.time)


class AIAsyncJobStore:
    def __init__(self, ttl_seconds: int = 900) -> None:
        self.ttl_seconds = ttl_seconds
        self._jobs: dict[str, AIAsyncJob] = {}
        self._by_request: dict[tuple[str, str], str] = {}
        self._lock = threading.Lock()

    def _purge(self) -> None:
        now = time.time()
        expired = [
            task_id for task_id, job in self._jobs.items()
            if now - job.updated_ts > self.ttl_seconds
        ]
        for task_id in expired:
            job = self._jobs.pop(task_id)
            self._by_request.pop((job.user_id, job.request_id), None)

    @staticmethod
    def _task_id(user_id: str, request_id: str, created_ts: float) -> str:
        raw = f"{user_id}:{request_id}:{created_ts}".encode()
        return hashlib.sha256(raw).hexdigest()[:24]

    def create_or_get(
        self, *, user_id: str, request_id: str, case_id: str | None
    ) -> tuple[AIAsyncJob, bool]:
        request_id = request_id.strip()
        if not request_id or len(request_id) > 100:
            raise HTTPException(422, "request_id inválido")
        with self._lock:
            self._purge()
            key = (user_id, request_id)
            existing_id = self._by_request.get(key)
            if existing_id:
                existing = self._jobs[existing_id]
                if existing.case_id != case_id:
                    raise HTTPException(409, "request_id já usado para outro caso")
                return existing, False
            now = time.time()
            job = AIAsyncJob(
                task_id=self._task_id(user_id, request_id, now),
                request_id=request_id,
                user_id=user_id,
                case_id=case_id,
                created_at=datetime.now(timezone.utc).isoformat(),
                created_ts=now,
            )
            self._jobs[job.task_id] = job
            self._by_request[key] = job.task_id
            return job, True

    def get_for_user(self, task_id: str, user_id: str) -> AIAsyncJob:
        with self._lock:
            self._purge()
            job = self._jobs.get(task_id)
            if job is None:
                raise HTTPException(404, "Tarefa não encontrada ou expirada")
            if job.user_id != user_id:
                raise HTTPException(404, "Tarefa não encontrada ou expirada")
            return job

    def update(self, task_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs.get(task_id)
            if job is None:
                return
            for key, value in changes.items():
                setattr(job, key, value)
            job.updated_ts = time.time()

    def public(self, job: AIAsyncJob) -> dict[str, Any]:
        out = {
            "task_id": job.task_id,
            "request_id": job.request_id,
            "case_id": job.case_id,
            "status": job.status,
            "criado_em": job.created_at,
        }
        if job.status == "completed":
            out["resultado"] = job.result
        if job.status == "failed":
            out["erro"] = job.error or "Falha ao executar análise"
        return out


_store = AIAsyncJobStore()


def get_store(ttl_seconds: int = 900) -> AIAsyncJobStore:
    _store.ttl_seconds = ttl_seconds
    return _store
