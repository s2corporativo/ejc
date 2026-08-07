# ── tests/test_consolidacao_fontes_ingestao.py ───────────────────────────────
# Onda 2 — Consolidação de fontes de ingestão duplicadas.
#
# O painel mostrava a MESMA fonte duas vezes: a trilha agendada grava os slugs
# `stj`/`tjmg`/`lexml` e a on-demand gravava `juris_import_*`. Cobertura
# (tudo SEM Postgres, padrão fake/factory local do repo):
#   • executar_importacao usa o slug ÚNICO (sem prefixo juris_import_);
#   • listar_fontes (router) consulta fontes_ingestao pelo slug único;
#   • migration 138: lógica PURA de merge (soma contadores, OR de ja_produziu,
#     timestamp mais recente) + upgrade idempotente contra SQLite.
from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import sqlalchemy as sa

from app.services.juris_import import FONTES
from app.services.juris_import import ingest as ji_ingest

UTC = timezone.utc

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "138_consolida_fontes_ingestao.py"
)
_spec = importlib.util.spec_from_file_location("mig_138_consolida_fontes", MIGRATION)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)


def _agora() -> datetime:
    return datetime.now(UTC)


# ══════════════════════════════════════════════════════════════════════════════
# executar_importacao — slug unificado com a trilha agendada
# ══════════════════════════════════════════════════════════════════════════════

async def test_executar_importacao_usa_slug_unificado(monkeypatch):
    """A execução on-demand alimenta a MESMA linha de fontes_ingestao que a
    trilha agendada: slug `stj`, nunca `juris_import_stj`."""
    slugs_registrados: list[str] = []
    slugs_marcados: list[str] = []

    async def fake_buscar(consulta, tribunal=None, limite=20, ano=None):
        return []

    async def fake_registrar(db, slug, descricao, categoria=None):
        slugs_registrados.append(slug)

    async def fake_marcar(db, slug, **kw):
        slugs_marcados.append(slug)

    async def _noop(*a, **kw):
        return None

    class _DB:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def commit(self):
            pass

    monkeypatch.setitem(FONTES, "stj", {**FONTES["stj"], "buscar": fake_buscar})
    monkeypatch.setattr(ji_ingest, "registrar_fonte", fake_registrar)
    monkeypatch.setattr(ji_ingest, "marcar_execucao", fake_marcar)
    monkeypatch.setattr(ji_ingest, "criar_audit_log", _noop)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", _DB)

    await ji_ingest.executar_importacao(
        "job-slug", "stj", "dano moral", None, 10, "u1", "advogado")

    assert slugs_registrados == ["stj"]
    assert slugs_marcados == ["stj"]
    assert not any(s.startswith("juris_import_") for s in slugs_registrados)


async def test_executar_importacao_erro_tambem_usa_slug_unificado(monkeypatch):
    """A trilha de erro (fail-safe) grava na mesma linha unificada."""
    slugs: list[str] = []

    async def fake_buscar(consulta, tribunal=None, limite=20, ano=None):
        raise RuntimeError("fonte fora do ar")

    async def fake_registrar(db, slug, descricao, categoria=None):
        slugs.append(slug)

    async def fake_marcar(db, slug, **kw):
        slugs.append(slug)

    class _DB:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def commit(self):
            pass

    monkeypatch.setitem(FONTES, "tjmg", {**FONTES["tjmg"], "buscar": fake_buscar})
    monkeypatch.setattr(ji_ingest, "registrar_fonte", fake_registrar)
    monkeypatch.setattr(ji_ingest, "marcar_execucao", fake_marcar)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", _DB)

    await ji_ingest.executar_importacao(
        "job-erro", "tjmg", "dano moral", None, 10, "u1", "advogado")

    assert slugs and set(slugs) == {"tjmg"}


async def test_listar_fontes_consulta_pelo_slug_unico():
    """O painel de fontes do router lê a linha `stj` (não `juris_import_stj`)."""
    from app.routers.juris_import import listar_fontes

    quando = _agora()
    linha_stj = SimpleNamespace(
        slug="stj", ultima_execucao=quando, ultimo_status="sucesso",
        registros_novos=7,
    )

    class _Res:
        def scalars(self):
            return self

        def all(self):
            return [linha_stj]

    class _FakeDB:
        async def execute(self, stmt):
            return _Res()

    out = await listar_fontes(db=_FakeDB(), cu=SimpleNamespace(id="u1"))
    por_slug = {f["slug"]: f for f in out["fontes"]}
    assert por_slug["stj"]["ultima_execucao"] == quando
    assert por_slug["stj"]["registros_novos"] == 7
    # Fonte sem linha no controle segue vindo vazia (não casa com prefixo velho).
    assert por_slug["lexml"]["ultima_execucao"] is None


# ══════════════════════════════════════════════════════════════════════════════
# Migration 138 — lógica pura de merge
# ══════════════════════════════════════════════════════════════════════════════

def _linha(**kw) -> dict:
    base = {
        "slug": "stj", "descricao": "d", "categoria_rag": "jurisprudencia",
        "ativo": True, "ultima_execucao": None, "ultimo_status": None,
        "registros_novos": 0, "registros_total": 0, "ultimo_erro": None,
        "execucoes_zeradas_consecutivas": 0, "ja_produziu": False,
    }
    base.update(kw)
    return base


def test_mesclar_soma_contadores_e_or_de_ja_produziu():
    antes = _agora() - timedelta(days=10)
    depois = _agora() - timedelta(days=1)
    origem = _linha(slug="juris_import_stj", ultima_execucao=antes,
                    ultimo_status="sucesso", registros_novos=3,
                    registros_total=10, ja_produziu=True)
    destino = _linha(ultima_execucao=depois, ultimo_status="parcial",
                     ultimo_erro="falha parcial", registros_novos=2,
                     registros_total=5, ja_produziu=False,
                     execucoes_zeradas_consecutivas=1)
    m = mig.mesclar_fontes(origem, destino)
    assert m["registros_novos"] == 5
    assert m["registros_total"] == 15
    assert m["ja_produziu"] is True            # OR lógico — vitalício
    assert m["ultima_execucao"] == depois      # timestamp mais recente
    # Status/erro/sequência de zeradas acompanham a execução mais recente.
    assert m["ultimo_status"] == "parcial"
    assert m["ultimo_erro"] == "falha parcial"
    assert m["execucoes_zeradas_consecutivas"] == 1


def test_mesclar_origem_mais_recente_dita_status():
    antes = _agora() - timedelta(days=10)
    depois = _agora() - timedelta(hours=2)
    origem = _linha(slug="juris_import_tjmg", ultima_execucao=depois,
                    ultimo_status="erro", ultimo_erro="timeout",
                    execucoes_zeradas_consecutivas=4)
    destino = _linha(slug="tjmg", ultima_execucao=antes,
                     ultimo_status="sucesso", registros_novos=1,
                     ja_produziu=True)
    m = mig.mesclar_fontes(origem, destino)
    assert m["ultima_execucao"] == depois
    assert m["ultimo_status"] == "erro"
    assert m["ultimo_erro"] == "timeout"
    assert m["execucoes_zeradas_consecutivas"] == 4
    assert m["ja_produziu"] is True


def test_mesclar_destino_nunca_executado_herda_da_origem():
    quando = _agora() - timedelta(days=3)
    origem = _linha(slug="juris_import_lexml", ultima_execucao=quando,
                    ultimo_status="sucesso", registros_novos=8,
                    registros_total=8, ja_produziu=True)
    destino = _linha(slug="lexml")            # linha criada e nunca executada
    m = mig.mesclar_fontes(origem, destino)
    assert m["ultima_execucao"] == quando
    assert m["ultimo_status"] == "sucesso"
    assert m["registros_novos"] == 8 and m["registros_total"] == 8
    assert m["ja_produziu"] is True


def test_mesclar_ativo_e_or_logico():
    origem = _linha(slug="juris_import_stj", ativo=False)
    destino = _linha(ativo=True)
    assert mig.mesclar_fontes(origem, destino)["ativo"] is True
    origem2 = _linha(slug="juris_import_stj", ativo=False)
    destino2 = _linha(ativo=False)
    assert mig.mesclar_fontes(origem2, destino2)["ativo"] is False


def test_mesclar_tolera_timestamp_em_string():
    """SELECT bruto em SQLite devolve datetime como texto — não pode quebrar."""
    origem = _linha(slug="juris_import_stj",
                    ultima_execucao="2026-08-01 10:00:00.000000",
                    ultimo_status="sucesso")
    destino = _linha(ultima_execucao="2026-07-01 08:00:00.000000",
                     ultimo_status="parcial")
    m = mig.mesclar_fontes(origem, destino)
    assert m["ultimo_status"] == "sucesso"


# ══════════════════════════════════════════════════════════════════════════════
# Migration 138 — upgrade idempotente (SQLite síncrono, sem Postgres)
# ══════════════════════════════════════════════════════════════════════════════

def _engine_com_tabela():
    from app.models.rag import FonteIngestao

    engine = sa.create_engine("sqlite://")
    FonteIngestao.__table__.create(engine)
    return engine


def _inserir(conn, linha: dict) -> None:
    campos = ", ".join(linha)
    marcadores = ", ".join(f":{c}" for c in linha)
    conn.execute(
        sa.text(f"INSERT INTO fontes_ingestao ({campos}) VALUES ({marcadores})"),
        linha,
    )


def _estado(conn) -> dict[str, dict]:
    rows = conn.execute(sa.text(
        "SELECT slug, registros_novos, registros_total, ja_produziu, "
        "ultimo_status FROM fontes_ingestao ORDER BY slug"
    )).mappings().all()
    return {r["slug"]: dict(r) for r in rows}


def test_upgrade_mescla_renomeia_e_e_idempotente(monkeypatch):
    engine = _engine_com_tabela()
    antes = _agora() - timedelta(days=9)
    depois = _agora() - timedelta(days=2)
    with engine.begin() as conn:
        # stj: linhas nas DUAS trilhas → merge.
        _inserir(conn, _linha(slug="stj", ultima_execucao=antes,
                              ultimo_status="sucesso", registros_novos=4,
                              registros_total=20, ja_produziu=True))
        _inserir(conn, _linha(slug="juris_import_stj", ultima_execucao=depois,
                              ultimo_status="sucesso", registros_novos=1,
                              registros_total=3))
        # lexml: só a trilha on-demand → renomeada para o slug canônico.
        _inserir(conn, _linha(slug="juris_import_lexml",
                              ultima_execucao=depois, ultimo_status="sucesso",
                              registros_novos=2, registros_total=2,
                              ja_produziu=True))
        # tjmg: nenhuma linha — nada acontece.

    with engine.begin() as conn:
        monkeypatch.setattr(mig.op, "get_bind", lambda: conn)
        mig.upgrade()
        estado = _estado(conn)

    assert set(estado) == {"stj", "lexml"}     # nenhuma linha juris_import_*
    assert estado["stj"]["registros_novos"] == 5          # 4 + 1
    assert estado["stj"]["registros_total"] == 23         # 20 + 3
    assert bool(estado["stj"]["ja_produziu"]) is True     # OR lógico
    assert estado["lexml"]["registros_novos"] == 2        # renomeada intacta
    assert bool(estado["lexml"]["ja_produziu"]) is True

    # Idempotência: reexecutar sem linhas juris_import_* é no-op.
    with engine.begin() as conn:
        monkeypatch.setattr(mig.op, "get_bind", lambda: conn)
        mig.upgrade()
        assert _estado(conn) == estado

    engine.dispose()


def test_upgrade_sem_linhas_e_no_op(monkeypatch):
    engine = _engine_com_tabela()
    with engine.begin() as conn:
        monkeypatch.setattr(mig.op, "get_bind", lambda: conn)
        mig.upgrade()
        assert _estado(conn) == {}
    engine.dispose()
