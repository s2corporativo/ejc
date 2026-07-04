# tests/test_estilo_advogado.py — Aprendizado de Estilo.
# Cobre: destilação com Gateway mockado (cria/refina + n_amostras), ownership
# estrito (advogado não acessa/apaga estilo de outro), toggle ativo e injeção
# condicional do estilo no prompt da etapa de redação do pipeline de peças.
#
# Tabelas criadas via Base.metadata em SQLite in-memory (sem Postgres/CI gate).
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.ai_log import AILog
from app.models.estilo_advogado import EstiloAdvogado
from app.services import estilo_service as es
from app.services import peca_service as ps
from app.services.estilo_service import (
    definir_ativo,
    destilar_amostra,
    instrucao_estilo,
    limpar_estilo,
    obter_estilo,
)

_PECA_A = (
    "Trata-se de demanda em que o autor pleiteia a reparação dos danos sofridos. "
    "Com efeito, resta demonstrado que a conduta da ré foi ilícita. Nesse diapasão, "
    "impõe-se a condenação, na medida em que preenchidos os requisitos legais."
)
_PECA_B = (
    "Cumpre destacar, de início, que a pretensão encontra amparo na legislação. "
    "Outrossim, a prova documental corrobora integralmente a tese autoral, razão "
    "pela qual o pedido merece integral procedência."
)


@pytest.fixture
async def db():
    """Sessão async SQLite in-memory com as tabelas de estilo e AILog."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(
                c, tables=[EstiloAdvogado.__table__, AILog.__table__]
            )
        )
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


def _fake_gw(texto: str):
    async def _chat(messages, **kw):
        _chat.capturado = messages
        return SimpleNamespace(
            texto=texto, modelo="fake", provedor="fake",
            input_tokens=10, output_tokens=20,
        )
    _chat.capturado = None
    return _chat


# ── 1. Destilação: cria perfil e incrementa n_amostras ───────────────────────

async def test_destilar_cria_perfil(db, monkeypatch):
    monkeypatch.setattr(es, "gw_chat", _fake_gw("PERFIL: tom formal, conectivos eruditos."))

    estilo = await destilar_amostra(db, "adv-1", _PECA_A)
    assert estilo.perfil_estilo == "PERFIL: tom formal, conectivos eruditos."
    assert estilo.n_amostras == 1
    assert estilo.ativo is True

    # AILog gravado (auditoria).
    from sqlalchemy import select, func as sqlfunc
    total = (await db.execute(select(sqlfunc.count()).select_from(AILog))).scalar()
    assert total == 1


async def test_destilar_refina_e_incrementa(db, monkeypatch):
    monkeypatch.setattr(es, "gw_chat", _fake_gw("PERFIL v1"))
    await destilar_amostra(db, "adv-1", _PECA_A)

    fake2 = _fake_gw("PERFIL v2 consolidado")
    monkeypatch.setattr(es, "gw_chat", fake2)
    estilo = await destilar_amostra(db, "adv-1", _PECA_B)

    assert estilo.n_amostras == 2
    assert estilo.perfil_estilo == "PERFIL v2 consolidado"
    # O prompt de refino carrega o perfil anterior para consolidação.
    prompt_user = fake2.capturado[1]["content"]
    assert "PERFIL v1" in prompt_user


async def test_substituir_reseta_amostras(db, monkeypatch):
    monkeypatch.setattr(es, "gw_chat", _fake_gw("P1"))
    await destilar_amostra(db, "adv-1", _PECA_A)
    await destilar_amostra(db, "adv-1", _PECA_B)  # n=2

    monkeypatch.setattr(es, "gw_chat", _fake_gw("P novo"))
    estilo = await destilar_amostra(db, "adv-1", _PECA_A, substituir=True)
    assert estilo.n_amostras == 1
    assert estilo.perfil_estilo == "P novo"


# ── 2. Ownership estrito: cada advogado só toca o próprio estilo ──────────────

async def test_ownership_get_e_delete(db, monkeypatch):
    monkeypatch.setattr(es, "gw_chat", _fake_gw("perfil do adv-1"))
    await destilar_amostra(db, "adv-1", _PECA_A)

    # adv-2 não enxerga o estilo do adv-1.
    assert await obter_estilo(db, "adv-2") is None
    assert await instrucao_estilo(db, "adv-2") is None

    # DELETE do adv-2 não afeta o estilo do adv-1.
    assert await limpar_estilo(db, "adv-2") is False
    assert await obter_estilo(db, "adv-1") is not None

    # DELETE do próprio remove.
    assert await limpar_estilo(db, "adv-1") is True
    assert await obter_estilo(db, "adv-1") is None


async def test_ownership_toggle_alheio_nao_cria(db, monkeypatch):
    monkeypatch.setattr(es, "gw_chat", _fake_gw("perfil do adv-1"))
    await destilar_amostra(db, "adv-1", _PECA_A)

    # toggle de quem não tem perfil retorna None (não cria nem afeta o alheio).
    assert await definir_ativo(db, "adv-2", True) is None
    assert await obter_estilo(db, "adv-2") is None


# ── 3. Toggle ativo controla a instrução de estilo ───────────────────────────

async def test_toggle_ativo_controla_instrucao(db, monkeypatch):
    monkeypatch.setattr(es, "gw_chat", _fake_gw("PERFIL: frases curtas e diretas."))
    await destilar_amostra(db, "adv-1", _PECA_A)

    instr = await instrucao_estilo(db, "adv-1")
    assert instr and "PERFIL: frases curtas e diretas." in instr

    await definir_ativo(db, "adv-1", False)
    assert await instrucao_estilo(db, "adv-1") is None

    await definir_ativo(db, "adv-1", True)
    assert await instrucao_estilo(db, "adv-1") is not None


# ── 4. Injeção condicional no pipeline de peças ──────────────────────────────

class _FakeDB:
    def add(self, obj):
        pass

    async def commit(self):
        pass

    async def execute(self, *a, **kw):
        raise RuntimeError("sem banco no teste")


def _mock_pipeline(monkeypatch):
    prompts: list[list[dict]] = []

    async def fake_chat(messages, **kw):
        prompts.append(messages)
        return SimpleNamespace(
            texto="ok", modelo="fake", provedor="fake",
            input_tokens=1, output_tokens=1,
        )

    async def fake_rag(db, query, limite=6, scope_client_id=None):
        return []

    monkeypatch.setattr(ps, "gw_chat", fake_chat)
    monkeypatch.setattr(ps, "buscar_contexto_rag", fake_rag)
    return prompts


_BLOCO = "ESTILO DO ADVOGADO (reproduza fielmente): frases curtas, tom incisivo."


async def _rodar(monkeypatch, usar_estilo):
    prompts = _mock_pipeline(monkeypatch)
    eventos = [
        e async for e in ps.gerar_peca_pipeline(
            db=_FakeDB(),
            user_id="adv-1",
            tipo_peca="parecer",
            area_direito="civil",
            descricao_fatos="Consulta sobre viabilidade de ação declaratória.",
            pedidos="Parecer fundamentado sobre o tema.",
            nomes_proteger=[],
            case_id=None,
            instrucoes_adicionais=None,
            usar_estilo=usar_estilo,
        )
    ]
    assert any("event: concluido" in e for e in eventos)
    return prompts[-1][0]["content"]  # system da etapa 7 (redação)


async def test_estilo_injetado_quando_ativo_e_flag(monkeypatch):
    async def fake_instr(db, user_id):
        return _BLOCO

    monkeypatch.setattr(ps, "instrucao_estilo", fake_instr)
    system_redacao = await _rodar(monkeypatch, usar_estilo=True)
    assert _BLOCO in system_redacao


async def test_estilo_nao_injetado_sem_flag(monkeypatch):
    async def fake_instr(db, user_id):
        return _BLOCO

    monkeypatch.setattr(ps, "instrucao_estilo", fake_instr)
    system_redacao = await _rodar(monkeypatch, usar_estilo=False)
    assert _BLOCO not in system_redacao
    assert "ESTILO DO ADVOGADO" not in system_redacao
