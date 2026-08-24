"""Radar Jurisprudencial — Camada 3, explicação por IA (PR 4, Commit 5).

A IA NUNCA decide que uma tese está superada — só explica um impacto que as
Camadas 1/2 já classificaram. O que mais importa cobrir aqui: o texto sempre
começa com o aviso padrão (nunca "tese superada"), o gate de citações
suprime texto suspeito, falha do gateway/gate nunca propaga, e toda chamada
grava AILog (mesmo quando o texto acaba suprimido).
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import Base
from app.models.ai_log import AILog
from app.services import radar_jurisprudencial_explicacao as mod
from app.services.radar_jurisprudencial_explicacao import AVISO_PADRAO, gerar_explicacao

_TABELAS = [AILog.__table__]


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABELAS))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@dataclass
class _RespostaFake:
    texto: str
    modelo: str = "modelo-x"
    provedor: str = "ollama"


class _RelatorioFake:
    def __init__(self, *, bloqueia=False, bloqueantes=None):
        self.bloqueia_aprovacao = bloqueia
        self.bloqueantes = bloqueantes or []


def _decisao():
    return {"titulo": "REsp 1.111.111/SP", "ementa": "Ementa da decisão nova."}


def _tese_afetada():
    return {"tese_id": "t1", "titulo": "Tese de teste", "severidade": "alta"}


# ── caminho feliz ─────────────────────────────────────────────────────────

async def test_explicacao_normal_comeca_com_aviso_padrao_e_grava_ailog(db, monkeypatch):
    async def _fake_chat(**kwargs):
        assert kwargs["task_type"] == "resumo"
        return _RespostaFake(texto=f"{AVISO_PADRAO} A decisão cita a mesma súmula da tese.")

    async def _fake_validar(db_, texto):
        return _RelatorioFake(bloqueia=False)

    monkeypatch.setattr(mod, "gw_chat", _fake_chat)
    monkeypatch.setattr(mod, "validar_citacoes", _fake_validar)

    resultado = await gerar_explicacao(db, _decisao(), _tese_afetada(), user_id="u1")
    assert resultado["texto"].startswith(AVISO_PADRAO)
    assert resultado["ai_log_id"]

    log = (await db.execute(select(AILog))).scalar_one()
    assert log.user_id == "u1"
    assert log.tipo_uso.value == "resumo_documento"


# ── nunca decide — texto nunca afirma "superada" sem o aviso padrão ────────

async def test_prompt_de_sistema_proibe_decidir_status_da_tese():
    assert "NÃO decida" in mod._SYS_PROMPT
    assert "sempre humana" in mod._SYS_PROMPT


# ── gate de citações suprime texto suspeito ─────────────────────────────────

async def test_citacao_bloqueante_suprime_texto_mas_ainda_grava_ailog(db, monkeypatch):
    async def _fake_chat(**kwargs):
        return _RespostaFake(texto=f"{AVISO_PADRAO} Cita a Súmula 999 do STJ.")

    async def _fake_validar(db_, texto):
        return _RelatorioFake(bloqueia=True)

    monkeypatch.setattr(mod, "gw_chat", _fake_chat)
    monkeypatch.setattr(mod, "validar_citacoes", _fake_validar)

    resultado = await gerar_explicacao(db, _decisao(), _tese_afetada(), user_id="u1")
    assert resultado["texto"].startswith(AVISO_PADRAO)
    assert "suprimida" in resultado["texto"]
    assert "Súmula 999" not in resultado["texto"]

    log = (await db.execute(select(AILog))).scalar_one()
    assert "Súmula 999" in log.resposta  # trilha auditável preserva o texto bruto


async def test_falha_do_gate_de_citacoes_trata_como_suspeita_fail_closed(db, monkeypatch):
    async def _fake_chat(**kwargs):
        return _RespostaFake(texto=f"{AVISO_PADRAO} Texto qualquer.")

    async def _fake_validar(db_, texto):
        raise RuntimeError("gate indisponível")

    monkeypatch.setattr(mod, "gw_chat", _fake_chat)
    monkeypatch.setattr(mod, "validar_citacoes", _fake_validar)

    resultado = await gerar_explicacao(db, _decisao(), _tese_afetada(), user_id="u1")
    assert "suprimida" in resultado["texto"]


# ── fail-open quanto ao alerta ───────────────────────────────────────────────

async def test_ai_desligada_nao_chama_gateway_e_nao_grava_ailog(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "AI_ENABLED", False)
    chamou = {"n": 0}

    async def _fake_chat(**kwargs):
        chamou["n"] += 1
        return _RespostaFake(texto="não deveria chegar aqui")

    monkeypatch.setattr(mod, "gw_chat", _fake_chat)

    resultado = await gerar_explicacao(db, _decisao(), _tese_afetada(), user_id="u1")
    assert resultado == {"texto": None, "ai_log_id": None}
    assert chamou["n"] == 0
    assert (await db.execute(select(AILog))).scalars().all() == []


async def test_gateway_indisponivel_nao_propaga_e_nao_grava_ailog(db, monkeypatch):
    async def _fake_chat(**kwargs):
        raise RuntimeError("provedor fora do ar")

    monkeypatch.setattr(mod, "gw_chat", _fake_chat)

    resultado = await gerar_explicacao(db, _decisao(), _tese_afetada(), user_id="u1")
    assert resultado == {"texto": None, "ai_log_id": None}
    assert (await db.execute(select(AILog))).scalars().all() == []


async def test_resposta_vazia_do_modelo_nao_grava_ailog(db, monkeypatch):
    async def _fake_chat(**kwargs):
        return _RespostaFake(texto="   ")

    monkeypatch.setattr(mod, "gw_chat", _fake_chat)

    resultado = await gerar_explicacao(db, _decisao(), _tese_afetada(), user_id="u1")
    assert resultado == {"texto": None, "ai_log_id": None}
    assert (await db.execute(select(AILog))).scalars().all() == []
