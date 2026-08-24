"""Importador do lote inicial de teses candidatas (PR 3 da série de
consolidação do Banco de Teses — `app/services/teses_seed_importador.py`).

`criar_audit_log` é monkeypatchado (mesmo padrão de
`test_teses_extensoes_validacao.py`): a coluna real usa `JSONB`, tipo
Postgres-only que não existe em sqlite; aqui cobrimos só a lógica do
importador, não a trilha de auditoria em si.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.tese import Tese, TeseStatus, TeseTipo
from app.services import teses_seed_importador as importador

_TABELAS = [Tese.__table__]


@pytest.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABELAS))
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _audit_log_fake(*a, **kw):
        return None

    monkeypatch.setattr(importador, "criar_audit_log", _audit_log_fake)

    async with maker() as session:
        yield session
    await engine.dispose()


def _linha(**overrides) -> dict:
    base = {
        "codigo": "BAN-001",
        "titulo": "Aplicação do CDC às instituições financeiras",
        "area_juridica": "bancario",
        "orientacao": "ambos",
        "tipo": "escritorio",
        "status_validacao": "descoberta",
        "descricao": "As instituições financeiras submetem-se às normas do CDC.",
        "fundamentacao": None,
        "jurisprudencia": None,
        "contra_argumento": None,
        "pressupostos": None,
        "excecoes": None,
        "estrategia": None,
        "instancia": None,
        "procedimento": None,
        "parte_favorecida": None,
        "tribunal": None,
        "magistrado": None,
        "tags": "cdc,bancario",
        "observacoes": None,
        "requisitos": [],
        "provas_necessarias": [],
        "riscos": [],
        "fontes": [{"referencia": "Súmula 297/STJ", "situacao": "conferir", "url_oficial": None}],
    }
    base.update(overrides)
    return base


def _escrever_jsonl(tmp_path, registros: list[dict], nome: str = "lote.jsonl"):
    caminho = tmp_path / nome
    with caminho.open("w", encoding="utf-8") as f:
        for r in registros:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return caminho


# ── caminho feliz + idempotência ─────────────────────────────────────────────

async def test_importa_lote_e_grava_status_descoberta_e_rascunho(db, tmp_path):
    caminho = _escrever_jsonl(tmp_path, [_linha(), _linha(codigo="CON-001", titulo="Outra tese", area_juridica="consumidor")])
    resumo = await importador.importar_theses_master(db, caminho)
    assert resumo["importados"] == 2
    assert resumo["ja_existentes"] == 0
    assert set(resumo["codigos_criados"]) == {"BAN-001", "CON-001"}

    rows = (await db.execute(select(Tese))).scalars().all()
    assert len(rows) == 2
    for r in rows:
        assert r.status_validacao == "descoberta"
        assert r.status == TeseStatus.rascunho
        assert r.tipo == TeseTipo.escritorio


async def test_segunda_execucao_com_mesmo_arquivo_nao_muda_nada(db, tmp_path):
    caminho = _escrever_jsonl(tmp_path, [_linha()])
    r1 = await importador.importar_theses_master(db, caminho)
    assert r1["importados"] == 1

    r2 = await importador.importar_theses_master(db, caminho)
    assert r2["importados"] == 0
    assert r2["ja_existentes"] == 1

    rows = (await db.execute(select(Tese))).scalars().all()
    assert len(rows) == 1


async def test_nao_sobrescreve_texto_editado_por_humano(db, tmp_path):
    caminho = _escrever_jsonl(tmp_path, [_linha(fundamentacao=None)])
    await importador.importar_theses_master(db, caminho)

    tese = (await db.execute(select(Tese))).scalar_one()
    tese.fundamentacao = "Texto que um advogado escreveu depois da importação."
    await db.commit()

    await importador.importar_theses_master(db, caminho)

    tese_depois = (await db.execute(select(Tese))).scalar_one()
    assert tese_depois.fundamentacao == "Texto que um advogado escreveu depois da importação."


# ── validação — falha alta e visível ─────────────────────────────────────────

async def test_rejeita_status_validacao_diferente_de_descoberta(db, tmp_path):
    caminho = _escrever_jsonl(tmp_path, [_linha(status_validacao="validada")])
    with pytest.raises(importador.ImportacaoSeedInvalida, match="status_validacao"):
        await importador.importar_theses_master(db, caminho)


async def test_rejeita_area_nao_mapeavel(db, tmp_path):
    caminho = _escrever_jsonl(tmp_path, [_linha(area_juridica="area-que-nao-existe")])
    with pytest.raises(importador.ImportacaoSeedInvalida, match="area_juridica"):
        await importador.importar_theses_master(db, caminho)


async def test_rejeita_codigo_fora_do_formato(db, tmp_path):
    caminho = _escrever_jsonl(tmp_path, [_linha(codigo="banco-1")])
    with pytest.raises(importador.ImportacaoSeedInvalida, match="codigo"):
        await importador.importar_theses_master(db, caminho)


async def test_rejeita_orientacao_invalida(db, tmp_path):
    caminho = _escrever_jsonl(tmp_path, [_linha(orientacao="neutra")])
    with pytest.raises(importador.ImportacaoSeedInvalida, match="orientacao"):
        await importador.importar_theses_master(db, caminho)


async def test_rejeita_titulo_vazio(db, tmp_path):
    caminho = _escrever_jsonl(tmp_path, [_linha(titulo="  ")])
    with pytest.raises(importador.ImportacaoSeedInvalida, match="titulo"):
        await importador.importar_theses_master(db, caminho)


async def test_arquivo_inexistente_leva_a_erro_explicito(db, tmp_path):
    with pytest.raises(FileNotFoundError):
        await importador.importar_theses_master(db, tmp_path / "nao-existe.jsonl")


# ── dedup ─────────────────────────────────────────────────────────────────────

async def test_dedup_por_codigo_duplicado_dentro_do_proprio_arquivo(db, tmp_path):
    caminho = _escrever_jsonl(tmp_path, [_linha(), _linha()])
    resumo = await importador.importar_theses_master(db, caminho)
    assert resumo["importados"] == 1
    assert resumo["duplicados_no_arquivo"] == 1


async def test_dedup_por_titulo_e_area_similares_mesmo_com_codigo_novo(db, tmp_path):
    caminho1 = _escrever_jsonl(tmp_path, [_linha()], nome="lote1.jsonl")
    await importador.importar_theses_master(db, caminho1)

    caminho2 = _escrever_jsonl(
        tmp_path,
        [_linha(codigo="BAN-999", titulo="Aplicação do Código de Defesa do Consumidor às instituições financeiras")],
        nome="lote2.jsonl",
    )
    resumo = await importador.importar_theses_master(db, caminho2)
    assert resumo["importados"] == 0
    assert resumo["ja_existentes"] == 1

    rows = (await db.execute(select(Tese))).scalars().all()
    assert len(rows) == 1


async def test_titulo_similar_em_area_diferente_nao_deduplica(db, tmp_path):
    caminho1 = _escrever_jsonl(tmp_path, [_linha(titulo="Responsabilidade objetiva do fornecedor")], nome="lote1.jsonl")
    await importador.importar_theses_master(db, caminho1)

    caminho2 = _escrever_jsonl(
        tmp_path,
        [_linha(codigo="TRA-001", area_juridica="trabalhista", titulo="Responsabilidade objetiva do empregador")],
        nome="lote2.jsonl",
    )
    resumo = await importador.importar_theses_master(db, caminho2)
    assert resumo["importados"] == 1

    rows = (await db.execute(select(Tese))).scalars().all()
    assert len(rows) == 2
