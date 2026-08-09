# ── tests/test_consolidacao_fontes_ingestao.py ───────────────────────────────
# Onda 2 — Consolidação de fontes de ingestão duplicadas.
#
# Garante que a trilha on-demand usa os slugs canônicos e que a migration 138
# consolida o histórico sem apagar a linha antiga: quando há duplicidade, a
# origem vira `legacy_138_*`, inativa e preservada para auditoria.
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
assert _spec and _spec.loader
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)


def _agora() -> datetime:
    return datetime.now(UTC)


# ══════════════════════════════════════════════════════════════════════════════
# executar_importacao — slug unificado com a trilha agendada
# ══════════════════════════════════════════════════════════════════════════════

async def test_executar_importacao_usa_slug_unificado(monkeypatch):
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
        "job-slug", "stj", "dano moral", None, 10, "u1", "advogado"
    )

    assert slugs_registrados == ["stj"]
    assert slugs_marcados == ["stj"]
    assert not any(s.startswith("juris_import_") for s in slugs_registrados)


async def test_executar_importacao_erro_tambem_usa_slug_unificado(monkeypatch):
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
        "job-erro", "tjmg", "dano moral", None, 10, "u1", "advogado"
    )

    assert slugs and set(slugs) == {"tjmg"}


async def test_listar_fontes_consulta_pelo_slug_unico():
    from app.routers.juris_import import listar_fontes

    quando = _agora()
    linha_stj = SimpleNamespace(
        slug="stj",
        ultima_execucao=quando,
        ultimo_status="sucesso",
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
    assert por_slug["lexml"]["ultima_execucao"] is None


# ══════════════════════════════════════════════════════════════════════════════
# Migration 138 — especificação pura de merge
# ══════════════════════════════════════════════════════════════════════════════


def _linha(**kw) -> dict:
    base = {
        "slug": "stj",
        "descricao": "d",
        "categoria_rag": "jurisprudencia",
        "ativo": True,
        "ultima_execucao": None,
        "ultimo_status": None,
        "registros_novos": 0,
        "registros_total": 0,
        "ultimo_erro": None,
        "execucoes_zeradas_consecutivas": 0,
        "ja_produziu": False,
    }
    base.update(kw)
    return base


def test_mesclar_soma_contadores_e_preserva_status_mais_recente():
    antes = _agora() - timedelta(days=10)
    depois = _agora() - timedelta(days=1)
    origem = _linha(
        slug="juris_import_stj",
        ultima_execucao=antes,
        ultimo_status="sucesso",
        registros_novos=3,
        registros_total=10,
        ja_produziu=True,
    )
    destino = _linha(
        ultima_execucao=depois,
        ultimo_status="parcial",
        ultimo_erro="falha parcial",
        registros_novos=2,
        registros_total=5,
        execucoes_zeradas_consecutivas=1,
    )
    result = mig.mesclar_fontes(origem, destino)

    assert result["registros_novos"] == 5
    assert result["registros_total"] == 15
    assert result["ja_produziu"] is True
    assert result["ultima_execucao"] == depois
    assert result["ultimo_status"] == "parcial"
    assert result["ultimo_erro"] == "falha parcial"
    assert result["execucoes_zeradas_consecutivas"] == 1


def test_mesclar_origem_mais_recente_dita_status():
    antes = _agora() - timedelta(days=10)
    depois = _agora() - timedelta(hours=2)
    origem = _linha(
        slug="juris_import_tjmg",
        ultima_execucao=depois,
        ultimo_status="erro",
        ultimo_erro="timeout",
        execucoes_zeradas_consecutivas=4,
    )
    destino = _linha(
        slug="tjmg",
        ultima_execucao=antes,
        ultimo_status="sucesso",
        registros_novos=1,
        ja_produziu=True,
    )
    result = mig.mesclar_fontes(origem, destino)

    assert result["ultima_execucao"] == depois
    assert result["ultimo_status"] == "erro"
    assert result["ultimo_erro"] == "timeout"
    assert result["execucoes_zeradas_consecutivas"] == 4
    assert result["ja_produziu"] is True


def test_mesclar_destino_nunca_executado_herda_da_origem():
    quando = _agora() - timedelta(days=3)
    origem = _linha(
        slug="juris_import_lexml",
        ultima_execucao=quando,
        ultimo_status="sucesso",
        registros_novos=8,
        registros_total=8,
        ja_produziu=True,
    )
    destino = _linha(slug="lexml")
    result = mig.mesclar_fontes(origem, destino)

    assert result["ultima_execucao"] == quando
    assert result["ultimo_status"] == "sucesso"
    assert result["registros_novos"] == 8
    assert result["registros_total"] == 8
    assert result["ja_produziu"] is True


def test_mesclar_ativo_e_or_logico():
    assert mig.mesclar_fontes(
        _linha(slug="juris_import_stj", ativo=False),
        _linha(ativo=True),
    )["ativo"] is True
    assert mig.mesclar_fontes(
        _linha(slug="juris_import_stj", ativo=False),
        _linha(ativo=False),
    )["ativo"] is False


def test_mesclar_tolera_timestamp_em_string():
    origem = _linha(
        slug="juris_import_stj",
        ultima_execucao="2026-08-01 10:00:00.000000",
        ultimo_status="sucesso",
    )
    destino = _linha(
        ultima_execucao="2026-07-01 08:00:00.000000",
        ultimo_status="parcial",
    )
    assert mig.mesclar_fontes(origem, destino)["ultimo_status"] == "sucesso"


# ══════════════════════════════════════════════════════════════════════════════
# Migration 138 — SQL real, preservação e idempotência
# ══════════════════════════════════════════════════════════════════════════════


def _engine_com_tabela():
    from app.models.rag import FonteIngestao

    engine = sa.create_engine("sqlite://")
    FonteIngestao.__table__.create(engine)
    return engine


def _inserir(conn, linha: dict) -> None:
    campos = ", ".join(linha)
    marcadores = ", ".join(f":{campo}" for campo in linha)
    conn.execute(
        sa.text(f"INSERT INTO fontes_ingestao ({campos}) VALUES ({marcadores})"),
        linha,
    )


def _estado(conn) -> dict[str, dict]:
    rows = conn.execute(
        sa.text(
            "SELECT slug, ativo, registros_novos, registros_total, "
            "ja_produziu, ultimo_status FROM fontes_ingestao ORDER BY slug"
        )
    ).mappings().all()
    return {row["slug"]: dict(row) for row in rows}


def _executar_upgrade(conn, monkeypatch) -> None:
    monkeypatch.setattr(
        mig.op,
        "execute",
        lambda sql: conn.execute(sa.text(sql)),
    )
    mig.upgrade()


def test_upgrade_mescla_preserva_legado_renomeia_e_e_idempotente(monkeypatch):
    engine = _engine_com_tabela()
    antes = _agora() - timedelta(days=9)
    depois = _agora() - timedelta(days=2)
    with engine.begin() as conn:
        _inserir(
            conn,
            _linha(
                slug="stj",
                ultima_execucao=antes,
                ultimo_status="sucesso",
                registros_novos=4,
                registros_total=20,
                ja_produziu=True,
            ),
        )
        _inserir(
            conn,
            _linha(
                slug="juris_import_stj",
                ultima_execucao=depois,
                ultimo_status="sucesso",
                registros_novos=1,
                registros_total=3,
            ),
        )
        # Só trilha antiga: deve virar a linha canônica, sem criar legado.
        _inserir(
            conn,
            _linha(
                slug="juris_import_lexml",
                ultima_execucao=depois,
                ultimo_status="sucesso",
                registros_novos=2,
                registros_total=2,
                ja_produziu=True,
            ),
        )

    with engine.begin() as conn:
        _executar_upgrade(conn, monkeypatch)
        estado = _estado(conn)

    assert "juris_import_stj" not in estado
    assert "juris_import_lexml" not in estado
    assert set(estado) == {"stj", "lexml", "legacy_138_juris_import_stj"}
    assert estado["stj"]["registros_novos"] == 5
    assert estado["stj"]["registros_total"] == 23
    assert bool(estado["stj"]["ja_produziu"]) is True
    assert estado["lexml"]["registros_novos"] == 2
    assert bool(estado["lexml"]["ja_produziu"]) is True

    legado = estado["legacy_138_juris_import_stj"]
    assert bool(legado["ativo"]) is False
    assert legado["registros_novos"] == 1
    assert legado["registros_total"] == 3

    with engine.begin() as conn:
        _executar_upgrade(conn, monkeypatch)
        assert _estado(conn) == estado

    engine.dispose()


def test_upgrade_sem_linhas_e_no_op(monkeypatch):
    engine = _engine_com_tabela()
    with engine.begin() as conn:
        _executar_upgrade(conn, monkeypatch)
        assert _estado(conn) == {}
    engine.dispose()


def test_upgrade_nao_contem_delete_fisico():
    texto = MIGRATION.read_text(encoding="utf-8").upper()
    assert "DELETE FROM FONTES_INGESTAO" not in texto
    assert mig.deployment_policy == "additive_data_backfill"
    assert mig.data_backfill_targets == ("fontes_ingestao",)
