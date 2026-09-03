"""F4 (análise E2E 03/09/2026): heartbeat de backup/reembed e misfire_grace_time."""
from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.services import heartbeat_service as hb
from app.services import scheduler as sch


def test_jobs_de_backup_e_reembed_sao_monitorados():
    assert hb.JOB_BACKUP_DRIVE in hb.JOBS_MONITORADOS
    assert hb.JOB_REEMBED_RAG in hb.JOBS_MONITORADOS
    assert hb.JOBS_MONITORADOS[hb.JOB_REEMBED_RAG]["max_age_horas"] <= 3


def test_scheduler_nasce_com_misfire_grace_time(monkeypatch):
    monkeypatch.setattr(sch, "_scheduler", None)
    s = sch.get_scheduler()
    assert s._job_defaults["misfire_grace_time"] == int(
        get_settings().SCHEDULER_MISFIRE_GRACE_SECONDS
    )
    assert s._job_defaults["coalesce"] is True


def test_backup_monitorado_bate_ponto_ok_e_erro(monkeypatch):
    batidas: list[tuple] = []

    async def _fake_ponto(job, status, detail=None):
        batidas.append((job, status, detail))

    monkeypatch.setattr(sch, "_bater_ponto", _fake_ponto)

    async def _ok():
        return None

    from app.services import backup_execution_service as bes

    monkeypatch.setattr(bes, "job_backup_drive_exclusivo", _ok)
    asyncio.run(sch._job_backup_drive_monitorado())
    assert batidas[-1][:2] == (hb.JOB_BACKUP_DRIVE, "ok")

    async def _boom():
        raise RuntimeError("rclone caiu")

    monkeypatch.setattr(bes, "job_backup_drive_exclusivo", _boom)
    try:
        asyncio.run(sch._job_backup_drive_monitorado())
    except RuntimeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("erro do backup deve propagar após o heartbeat")
    assert batidas[-1][:2] == (hb.JOB_BACKUP_DRIVE, "erro")
    assert "rclone" in (batidas[-1][2] or "")


def test_reembed_bate_ponto(monkeypatch):
    batidas: list[tuple] = []

    async def _fake_ponto(job, status, detail=None):
        batidas.append((job, status))

    monkeypatch.setattr(sch, "_bater_ponto", _fake_ponto)
    from app.services import embedding_service

    monkeypatch.setattr(embedding_service, "disponivel", lambda: True)
    import scripts.reembedar_chunks_orfaos as reemb

    async def _reembedar(batch_size=20):
        return None

    monkeypatch.setattr(reemb, "reembedar", _reembedar)
    asyncio.run(sch._reembedar_rag_orfaos())
    assert batidas[-1] == (hb.JOB_REEMBED_RAG, "ok")
