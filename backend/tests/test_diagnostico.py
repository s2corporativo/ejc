"""Central Eletrônica de Diagnóstico — probes com dependências mockadas.

Cobre cada probe isoladamente (banco ok/erro/sem-pgvector, migrations
ok/pendente/sem-tabela, IA, integração ligada-sem-credencial → alerta, RAG,
scheduler, disco baixo → alerta, erros) + a agregação de status_geral e a
montagem da rota. Sem rede, sem banco real.
"""
from __future__ import annotations

from collections import namedtuple
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.services import diagnostico_service as dg

_Usage = namedtuple("_Usage", "total used free")


# ── Fakes ─────────────────────────────────────────────────────────────────────
class _Res:
    def __init__(self, scalar=None, lista=None):
        self._scalar = scalar
        self._lista = lista or []

    def scalar(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return self._lista


class _FakeSession:
    """AsyncSession fake que responde por conteúdo do SQL."""

    def __init__(self, *, select1_erro=False, tem_vetor=True, conexoes=5,
                 alembic=None, alembic_erro=False, fontes=None):
        self.select1_erro = select1_erro
        self.tem_vetor = tem_vetor
        self.conexoes = conexoes
        self.alembic = alembic or []
        self.alembic_erro = alembic_erro
        self.fontes = fontes or []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "pg_extension" in sql:
            return _Res(scalar=(1 if self.tem_vetor else None))
        if sql.strip().upper().startswith("SELECT 1"):
            if self.select1_erro:
                raise RuntimeError("db down")
            return _Res(scalar=1)
        if "pg_stat_activity" in sql:
            return _Res(scalar=self.conexoes)
        if "alembic_version" in sql:
            if self.alembic_erro:
                raise RuntimeError("relation alembic_version does not exist")
            return _Res(lista=self.alembic)
        if "fontes_ingestao" in sql:
            return _Res(lista=self.fontes)
        return _Res()


class _FakeScheduler:
    def __init__(self, running=True, jobs=None):
        self.running = running
        self._jobs = jobs or []

    def get_jobs(self):
        return self._jobs


def _fonte(slug, status="sucesso"):
    return SimpleNamespace(slug=slug, ultima_execucao=None,
                           ultimo_status=status, registros_novos=1)


# ── Banco ─────────────────────────────────────────────────────────────────────
async def test_probe_banco_ok():
    r = await dg._probe_banco(_FakeSession(tem_vetor=True, conexoes=7))
    assert r["status"] == "ok"
    assert r["pgvector"] is True
    assert r["conexoes_ativas"] == 7
    assert r["latencia_ms"] is not None


async def test_probe_banco_erro():
    r = await dg._probe_banco(_FakeSession(select1_erro=True))
    assert r["status"] == "erro"
    assert "conex" in r["detalhe"].lower()


async def test_probe_banco_sem_pgvector():
    r = await dg._probe_banco(_FakeSession(tem_vetor=False))
    assert r["status"] == "alerta"
    assert r["pgvector"] is False


# ── Migrations ────────────────────────────────────────────────────────────────
async def test_probe_migrations_ok():
    r = await dg._probe_migrations(_FakeSession(alembic=["rev123"]), heads=["rev123"])
    assert r["status"] == "ok"


async def test_probe_migrations_pendente():
    r = await dg._probe_migrations(_FakeSession(alembic=["antiga"]), heads=["nova"])
    assert r["status"] == "alerta"
    assert r["revisoes_aplicadas"] == ["antiga"]
    assert r["heads_esperadas"] == ["nova"]


async def test_probe_migrations_sem_tabela():
    r = await dg._probe_migrations(_FakeSession(alembic_erro=True), heads=["x"])
    assert r["status"] == "alerta"
    assert "alembic_version" in r["detalhe"]


# ── IA ────────────────────────────────────────────────────────────────────────
async def test_probe_ia_desligado(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "AI_ENABLED", False)
    r = await dg._probe_ia(s)
    assert r["status"] == "desligado"


async def test_probe_ia_sem_provedor(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "AI_ENABLED", True)
    monkeypatch.setattr(s, "ANTHROPIC_ENABLED", False)
    monkeypatch.setattr(s, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(s, "GROQ_API_KEY", "")
    monkeypatch.setattr(s, "OLLAMA_ENABLED", False)
    r = await dg._probe_ia(s)
    assert r["status"] == "alerta"
    assert r["provedores"] == []


async def test_probe_ia_ok(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "AI_ENABLED", True)
    monkeypatch.setattr(s, "OLLAMA_ENABLED", True)
    monkeypatch.setattr(s, "OLLAMA_BASE_URL", "http://ollama:11434")
    r = await dg._probe_ia(s)
    assert r["status"] == "ok"
    assert "ollama" in r["provedores"]


# ── Integrações (ligada sem credencial → alerta) ──────────────────────────────
async def test_probe_integracoes_ligada_sem_credencial(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "INFOSIMPLES_ENABLED", True)
    monkeypatch.setattr(s, "INFOSIMPLES_TOKEN", "")  # ligada, sem token
    r = await dg._probe_integracoes(s)
    assert r["status"] == "alerta"
    infos = [i for i in r["itens"] if i["chave"] == "infosimples"]
    assert infos and infos[0]["status"] == "alerta"


async def test_probe_integracoes_indices_bcb_ok(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "INDICES_BCB_ENABLED", True)
    r = await dg._probe_integracoes(s)
    bcb = [i for i in r["itens"] if i["chave"] == "indices_bcb"]
    assert bcb and bcb[0]["status"] == "ok"


# ── RAG / embeddings ──────────────────────────────────────────────────────────
async def test_probe_rag_desligado(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "EMBEDDINGS_ENABLED", False)
    r = await dg._probe_rag(s, disponivel_fn=lambda: True)
    assert r["status"] == "desligado"
    assert r["busca"] == "fallback_textual"


async def test_probe_rag_ok(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "EMBEDDINGS_ENABLED", True)
    r = await dg._probe_rag(s, disponivel_fn=lambda: True)
    assert r["status"] == "ok"
    assert r["busca"] == "semantica"


async def test_probe_rag_fallback(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "EMBEDDINGS_ENABLED", True)
    r = await dg._probe_rag(s, disponivel_fn=lambda: False)
    assert r["status"] == "alerta"
    assert r["busca"] == "fallback_textual"


# ── Scheduler ─────────────────────────────────────────────────────────────────
async def test_probe_scheduler_ok(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "ENABLE_SCHEDULER", True)
    sched = _FakeScheduler(running=True, jobs=[SimpleNamespace(id="brief", next_run_time=None)])
    sess = _FakeSession(fontes=[_fonte("bcb"), _fonte("stj")])
    r = await dg._probe_scheduler(sess, s, scheduler=sched)
    assert r["status"] == "ok"
    assert r["jobs"][0]["id"] == "brief"
    assert r["fontes_com_erro"] == []


async def test_probe_scheduler_nao_rodando(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "ENABLE_SCHEDULER", True)
    r = await dg._probe_scheduler(_FakeSession(), s, scheduler=_FakeScheduler(running=False))
    assert r["status"] == "alerta"
    assert r["rodando"] is False


async def test_probe_scheduler_fonte_com_erro(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "ENABLE_SCHEDULER", True)
    sched = _FakeScheduler(running=True, jobs=[])
    sess = _FakeSession(fontes=[_fonte("bcb", status="erro")])
    r = await dg._probe_scheduler(sess, s, scheduler=sched)
    assert r["status"] == "alerta"
    assert r["fontes_com_erro"] == ["bcb"]


async def test_probe_scheduler_desligado(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "ENABLE_SCHEDULER", False)
    r = await dg._probe_scheduler(_FakeSession(), s)
    assert r["status"] == "desligado"


# ── Disco ─────────────────────────────────────────────────────────────────────
async def test_probe_disco_baixo():
    s = get_settings()
    # 5% livre → alerta
    fn = lambda _p: _Usage(total=100, used=95, free=5)
    r = await dg._probe_disco(s, disk_usage_fn=fn, path="/")
    assert r["status"] == "alerta"
    assert r["percentual_livre"] == 5.0


async def test_probe_disco_ok():
    s = get_settings()
    fn = lambda _p: _Usage(total=100, used=40, free=60)
    r = await dg._probe_disco(s, disk_usage_fn=fn, path="/")
    assert r["status"] == "ok"
    assert r["percentual_livre"] == 60.0


async def test_probe_disco_caminho_nao_expoe_path_absoluto(tmp_path):
    """Regressão: extras['caminho'] deve ser o rótulo do MOUNT, nunca o path
    absoluto do host (vazamento de layout interno de disco)."""
    s = get_settings()
    fn = lambda _p: _Usage(total=100, used=40, free=60)
    r = await dg._probe_disco(s, disk_usage_fn=fn, path=str(tmp_path))
    assert r["caminho"] != str(tmp_path)          # não é o path absoluto
    assert str(tmp_path) not in r["caminho"]       # nem o contém


# ── Erros ─────────────────────────────────────────────────────────────────────
async def test_probe_erros_sem_coletor(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "SENTRY_DSN", "")
    r = await dg._probe_erros(s)
    assert r["status"] == "ok"
    assert r["coletor"] is None
    assert "sem coletor" in r["detalhe"].lower()


async def test_probe_erros_sentry(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "SENTRY_DSN", "https://x@sentry.example/1")
    r = await dg._probe_erros(s)
    assert r["coletor"] == "sentry"


# ── Agregação status_geral ────────────────────────────────────────────────────
def test_agregar_pior_status_erro():
    subs = [{"status": "ok"}, {"status": "alerta"}, {"status": "erro"}, {"status": "desligado"}]
    geral, resumo = dg.agregar(subs)
    assert geral == "erro"
    assert resumo == {"ok": 1, "alerta": 1, "erro": 1, "desligado": 1}


def test_agregar_alerta_quando_sem_erro():
    geral, _ = dg.agregar([{"status": "ok"}, {"status": "alerta"}, {"status": "desligado"}])
    assert geral == "alerta"


def test_agregar_ok():
    geral, _ = dg.agregar([{"status": "ok"}, {"status": "desligado"}])
    assert geral == "ok"


def test_agregar_desligado_e_neutro():
    geral, _ = dg.agregar([{"status": "desligado"}, {"status": "desligado"}])
    assert geral == "desligado"


# ── Rota montada ──────────────────────────────────────────────────────────────
def test_rota_montada_em_main():
    from app.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p.endswith("/diagnostico/central") for p in paths)
