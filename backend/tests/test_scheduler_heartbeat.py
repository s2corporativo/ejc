# ── tests/test_scheduler_heartbeat.py ────────────────────────────────────────
# Heartbeat honesto dos jobs do scheduler (achado nº 1 da auditoria:
# "monitoramento pode parar em silêncio e o painel fica verde para sempre").
#
# Cobertura (tudo SEM Postgres):
#   • registrar_heartbeat: UPSERT por job_name (SQLite in-memory) + best-effort
#     (falha da sessão não propaga);
#   • avaliar_job / avaliar_jobs: lógica PURA de defasagem (ok/defasado/
#     nunca_executou/erro), tz-naive tolerado, defasagem prevalece sobre erro;
#   • diagnostico._probe_heartbeat_jobs: desligado / tabela ausente / ok /
#     defasado / erro;
#   • diagnostico._probe_backup: produção sem backup → alerta; com → ok; dev → neutro;
#   • intimacoes.status_captura: heartbeat defasado → sucesso=False/defasado=True,
#     último run com erro, e fallback legado quando não há heartbeat.
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.models.scheduler_heartbeat import SchedulerHeartbeat
from app.services import diagnostico_service as dg
from app.services import heartbeat_service as hb

UTC = timezone.utc


def _agora() -> datetime:
    return datetime.now(UTC)


# ══════════════════════════════════════════════════════════════════════════════
# registrar_heartbeat — UPSERT (SQLite in-memory, ON CONFLICT portável)
# ══════════════════════════════════════════════════════════════════════════════
@pytest.fixture
async def sqlite_db():
    """Sessão SQLite in-memory com a tabela scheduler_heartbeat criada.

    StaticPool + check_same_thread=False: uma única conexão física é reusada, de
    forma que a tabela sobrevive a commits do UPSERT (o `:memory:` por si só
    daria um banco novo por conexão)."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SchedulerHeartbeat.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def test_registrar_heartbeat_insere(sqlite_db):
    ok = await hb.registrar_heartbeat(sqlite_db, hb.JOB_DJEN, "ok")
    assert ok is True
    rows = (await sqlite_db.execute(select(SchedulerHeartbeat))).scalars().all()
    assert len(rows) == 1
    assert rows[0].job_name == hb.JOB_DJEN
    assert rows[0].last_status == "ok"
    assert rows[0].last_run_at is not None


async def test_registrar_heartbeat_upsert_nao_duplica(sqlite_db):
    await hb.registrar_heartbeat(sqlite_db, hb.JOB_DJEN, "ok")
    await hb.registrar_heartbeat(sqlite_db, hb.JOB_DJEN, "erro", "boom no DJEN")
    rows = (await sqlite_db.execute(select(SchedulerHeartbeat))).scalars().all()
    assert len(rows) == 1                       # UPSERT por job_name — não duplica
    assert rows[0].last_status == "erro"
    assert rows[0].detail == "boom no DJEN"


async def test_registrar_heartbeat_jobs_distintos_coexistem(sqlite_db):
    await hb.registrar_heartbeat(sqlite_db, hb.JOB_DJEN, "ok")
    await hb.registrar_heartbeat(sqlite_db, hb.JOB_DATAJUD, "ok")
    rows = (await sqlite_db.execute(select(SchedulerHeartbeat))).scalars().all()
    assert {r.job_name for r in rows} == {hb.JOB_DJEN, hb.JOB_DATAJUD}


async def test_registrar_heartbeat_normaliza_status_invalido(sqlite_db):
    await hb.registrar_heartbeat(sqlite_db, hb.JOB_DJEN, "banana")
    row = (await sqlite_db.execute(select(SchedulerHeartbeat))).scalars().one()
    assert row.last_status == "erro"            # status fora do domínio → 'erro'


class _RaisingDB:
    """Sessão que sempre falha — valida o best-effort (não propaga)."""

    async def execute(self, *a, **k):
        raise RuntimeError("relation scheduler_heartbeat does not exist")

    async def commit(self):
        raise RuntimeError("commit indisponível")

    async def rollback(self):
        return None


async def test_registrar_heartbeat_best_effort_nao_propaga():
    ok = await hb.registrar_heartbeat(_RaisingDB(), hb.JOB_DJEN, "ok")
    assert ok is False                          # falhou, mas NÃO levantou exceção


# ══════════════════════════════════════════════════════════════════════════════
# avaliar_job / avaliar_jobs — lógica pura de defasagem
# ══════════════════════════════════════════════════════════════════════════════
def test_avaliar_job_nunca_executou():
    r = hb.avaliar_job(None, None, max_age_horas=26)
    assert r["status"] == "nunca_executou"
    assert r["idade_horas"] is None


def test_avaliar_job_ok():
    r = hb.avaliar_job(_agora() - timedelta(hours=2), "ok", max_age_horas=26)
    assert r["status"] == "ok"


def test_avaliar_job_defasado():
    r = hb.avaliar_job(_agora() - timedelta(hours=40), "ok", max_age_horas=26)
    assert r["status"] == "defasado"
    assert r["idade_horas"] >= 39


def test_avaliar_job_erro_no_ultimo_run():
    r = hb.avaliar_job(_agora() - timedelta(hours=1), "erro", max_age_horas=26)
    assert r["status"] == "erro"


def test_avaliar_job_defasado_prevalece_sobre_erro():
    # Rodou há muito tempo E o último foi erro: defasagem (parada) é o sinal-alvo.
    r = hb.avaliar_job(_agora() - timedelta(hours=100), "erro", max_age_horas=26)
    assert r["status"] == "defasado"


def test_avaliar_job_datetime_naive_assume_utc():
    naive = datetime.utcnow() - timedelta(hours=2)      # sem tzinfo
    r = hb.avaliar_job(naive, "ok", max_age_horas=26)
    assert r["status"] == "ok"


def test_avaliar_jobs_sem_heartbeat_todos_nunca():
    jobs = hb.avaliar_jobs({})
    assert {j["job_name"] for j in jobs} == set(hb.JOBS_MONITORADOS)
    assert all(j["status"] == "nunca_executou" for j in jobs)


def test_avaliar_jobs_mistura_estados():
    agora = _agora()
    heartbeats = {
        hb.JOB_DJEN:    {"last_run_at": agora - timedelta(hours=2),  "last_status": "ok"},
        hb.JOB_DATAJUD: {"last_run_at": agora - timedelta(hours=40), "last_status": "ok"},
        hb.JOB_DIARIO:  {"last_run_at": agora - timedelta(hours=1),  "last_status": "erro",
                         "detail": "x"},
    }
    jobs = {j["job_name"]: j for j in hb.avaliar_jobs(heartbeats, agora=agora)}
    assert jobs[hb.JOB_DJEN]["status"] == "ok"
    assert jobs[hb.JOB_DATAJUD]["status"] == "defasado"     # 40h > 14h (2x/dia)
    assert jobs[hb.JOB_DIARIO]["status"] == "erro"
    assert jobs[hb.JOB_PRESCRICAO]["status"] == "nunca_executou"


def test_prescricao_semanal_tolera_uma_semana():
    # Prescrição roda semanal → 6 dias NÃO é defasagem (limite ~8 dias).
    r = hb.avaliar_job(_agora() - timedelta(days=6), "ok",
                       max_age_horas=hb.JOBS_MONITORADOS[hb.JOB_PRESCRICAO]["max_age_horas"])
    assert r["status"] == "ok"


# ══════════════════════════════════════════════════════════════════════════════
# diagnostico._probe_heartbeat_jobs
# ══════════════════════════════════════════════════════════════════════════════
class _FakeHBRes:
    def __init__(self, lista):
        self._lista = lista

    def scalars(self):
        return self

    def all(self):
        return self._lista


class _FakeHBSession:
    def __init__(self, heartbeats=None, raise_=False):
        self._heartbeats = heartbeats or []
        self._raise = raise_

    async def execute(self, stmt, params=None):
        if self._raise:
            raise RuntimeError("relation scheduler_heartbeat does not exist")
        return _FakeHBRes(self._heartbeats)


def _hb_row(job_name, last_run_at, last_status="ok", detail=None):
    return SimpleNamespace(job_name=job_name, last_run_at=last_run_at,
                           last_status=last_status, detail=detail)


async def test_probe_heartbeat_desligado(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "ENABLE_SCHEDULER", False)
    r = await dg._probe_heartbeat_jobs(_FakeHBSession(), s)
    assert r["status"] == "desligado"


async def test_probe_heartbeat_tabela_ausente(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "ENABLE_SCHEDULER", True)
    r = await dg._probe_heartbeat_jobs(_FakeHBSession(raise_=True), s)
    assert r["status"] == "alerta"
    assert "scheduler_heartbeat" in r["detalhe"]


async def test_probe_heartbeat_ok(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "ENABLE_SCHEDULER", True)
    agora = _agora()
    linhas = [_hb_row(name, agora - timedelta(hours=1)) for name in hb.JOBS_MONITORADOS]
    r = await dg._probe_heartbeat_jobs(_FakeHBSession(linhas), s)
    assert r["status"] == "ok"
    assert r["resumo"]["ok"] == len(hb.JOBS_MONITORADOS)


async def test_probe_heartbeat_defasado(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "ENABLE_SCHEDULER", True)
    agora = _agora()
    # Só o DJEN tem heartbeat (defasado); os demais nunca executaram.
    r = await dg._probe_heartbeat_jobs(
        _FakeHBSession([_hb_row(hb.JOB_DJEN, agora - timedelta(hours=40))]), s
    )
    assert r["status"] == "alerta"
    assert r["resumo"]["defasado"] == 1
    assert r["resumo"]["nunca_executou"] == len(hb.JOBS_MONITORADOS) - 1
    dj = [j for j in r["jobs"] if j["job_name"] == hb.JOB_DJEN][0]
    assert isinstance(dj["last_run_at"], str)          # datetime serializado p/ JSON


async def test_probe_heartbeat_erro(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "ENABLE_SCHEDULER", True)
    agora = _agora()
    nomes = list(hb.JOBS_MONITORADOS)
    linhas = [_hb_row(n, agora - timedelta(hours=1)) for n in nomes]
    linhas[0] = _hb_row(nomes[0], agora - timedelta(hours=1), "erro", "boom")
    r = await dg._probe_heartbeat_jobs(_FakeHBSession(linhas), s)
    assert r["status"] == "erro"
    assert r["resumo"]["erro"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# diagnostico._probe_backup
# ══════════════════════════════════════════════════════════════════════════════
async def test_probe_backup_producao_desligado_alerta(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "APP_ENV", "production")
    monkeypatch.setattr(s, "BACKUP_ENABLED", False)
    r = await dg._probe_backup(s)
    assert r["status"] == "alerta"
    assert r["backup_enabled"] is False
    assert "produção" in r["detalhe"].lower()


async def test_probe_backup_producao_ligado_ok(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "APP_ENV", "production")
    monkeypatch.setattr(s, "BACKUP_ENABLED", True)
    r = await dg._probe_backup(s)
    assert r["status"] == "ok"


async def test_probe_backup_dev_desligado_neutro(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "APP_ENV", "development")
    monkeypatch.setattr(s, "BACKUP_ENABLED", False)
    r = await dg._probe_backup(s)
    assert r["status"] == "desligado"          # fora de produção não alarma


# ══════════════════════════════════════════════════════════════════════════════
# intimacoes.status_captura — saúde a partir do heartbeat REAL
# ══════════════════════════════════════════════════════════════════════════════
class _ResScalar:
    def __init__(self, v):
        self._v = v

    def scalar(self):
        return self._v


class _ResObj:
    def __init__(self, v):
        self._v = v

    def scalar_one_or_none(self):
        return self._v


class _FakeStatusDB:
    def __init__(self, heartbeat=None, ultimo=None, count=0):
        self.heartbeat = heartbeat
        self.ultimo = ultimo
        self.count = count

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "scheduler_heartbeat" in sql:
            return _ResObj(self.heartbeat)
        if "max(created_at)" in sql:
            return _ResScalar(self.ultimo)
        return _ResScalar(self.count)          # count(*) das intimações


_CU = SimpleNamespace(id="u1", role=SimpleNamespace(value="advogado"))


def _heartbeat(last_run_at, last_status="ok", detail=None):
    return SimpleNamespace(job_name=hb.JOB_DJEN, last_run_at=last_run_at,
                           last_status=last_status, detail=detail)


async def test_status_captura_defasado_nao_fica_verde():
    from app.routers.intimacoes import status_captura
    heartbeat = _heartbeat(_agora() - timedelta(hours=40))   # limite DJEN = 26h
    out = await status_captura(db=_FakeStatusDB(heartbeat=heartbeat, count=3), cu=_CU)
    assert out["sucesso"] is False
    assert out["defasado"] is True
    assert "parada" in out["erro"].lower()
    assert out["ultima_execucao"] == heartbeat.last_run_at


async def test_status_captura_ok_verde():
    from app.routers.intimacoes import status_captura
    heartbeat = _heartbeat(_agora() - timedelta(hours=2))
    out = await status_captura(db=_FakeStatusDB(heartbeat=heartbeat, count=5), cu=_CU)
    assert out["sucesso"] is True
    assert out["defasado"] is False
    assert out["intimacoes_encontradas"] == 5
    assert out["erro"] is None


async def test_status_captura_ultimo_run_com_erro():
    from app.routers.intimacoes import status_captura
    heartbeat = _heartbeat(_agora() - timedelta(hours=1), "erro", "timeout DJEN")
    out = await status_captura(db=_FakeStatusDB(heartbeat=heartbeat), cu=_CU)
    assert out["sucesso"] is False
    assert out["erro"] == "timeout DJEN"


async def test_status_captura_fallback_sem_heartbeat():
    from app.routers.intimacoes import status_captura
    out = await status_captura(
        db=_FakeStatusDB(heartbeat=None, ultimo=_agora(), count=2), cu=_CU
    )
    assert out["sucesso"] is True              # comportamento legado preservado
    assert out["defasado"] is False


async def test_status_captura_vazio():
    from app.routers.intimacoes import status_captura
    out = await status_captura(db=_FakeStatusDB(heartbeat=None, ultimo=None), cu=_CU)
    assert out["executado_em"] is None
    assert out["sucesso"] is False
