"""Fase 6 — model_router: complexidade determinística → tier → provedor.

Contrato:
  - score determinístico por task_type + tamanho + contexto + citações;
  - score → tier (leve/medio/pesado) pelos limiares configuráveis;
  - tier → provedor configurável; Anthropic diferencia RAPIDO vs COMPLEXO;
  - roteador só PROPÕE (elegibilidade/PII ficam no gateway).
"""
from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.services.ai import model_router as mr


def _cfg(monkeypatch, **kw):
    s = get_settings()
    for k, v in kw.items():
        monkeypatch.setattr(s, k, v)


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    _cfg(
        monkeypatch,
        ROTEAMENTO_LIMIAR_MEDIO=3,
        ROTEAMENTO_LIMIAR_PESADO=6,
        ROTEAMENTO_PROVIDER_LEVE="groq",
        ROTEAMENTO_PROVIDER_MEDIO="ollama",
        ROTEAMENTO_PROVIDER_PESADO="anthropic",
        ANTHROPIC_MODEL_RAPIDO="claude-haiku-4-5-20251001",
        ANTHROPIC_MODEL_COMPLEXO="claude-opus-4-8",
    )


# ── Complexidade → tier ───────────────────────────────────────────────────────

def test_tarefa_leve_input_pequeno_e_leve():
    d = mr.escolher_modelo("resumo", "resumo curto")
    assert d.tier == "leve"
    assert d.provider == "groq"
    assert d.model is None  # groq resolve default no gateway


def test_tarefa_media_por_task_type():
    d = mr.escolher_modelo("analise_contrato", "contrato pequeno")
    assert d.tier == "medio"
    assert d.provider == "ollama"


def test_tarefa_pesada_por_task_type():
    d = mr.escolher_modelo("estrategia", "questão estratégica")
    assert d.tier == "pesado"
    assert d.provider == "anthropic"
    assert d.model == "claude-opus-4-8"  # tier pesado → COMPLEXO


def test_input_grande_eleva_tier():
    # resumo (peso 0) + input >=8000 (+3) = score 3 → medio
    d = mr.escolher_modelo("resumo", "x" * 8500)
    assert d.score >= 3
    assert d.tier in ("medio", "pesado")


def test_contexto_e_citacoes_elevam_score():
    texto = "análise " + "art. 5 " * 6  # >=5 citações
    d = mr.escolher_modelo(
        "analise_contrato", texto, contexto={"case_id": "abc"},
    )
    # analise_contrato (3) + citações>=5 (+2) + contexto (+1) = 6 → pesado
    assert d.score >= 6
    assert d.tier == "pesado"


def test_tamanho_override_para_preview():
    # sem texto, mas tamanho grande via override
    d = mr.escolher_modelo("resumo", tamanho_override=9000)
    assert d.score >= 3


# ── Limiares configuráveis ────────────────────────────────────────────────────

def test_limiares_configuraveis(monkeypatch):
    _cfg(monkeypatch, ROTEAMENTO_LIMIAR_MEDIO=1, ROTEAMENTO_LIMIAR_PESADO=2)
    # resumo peso 0, input médio (+1) → score 1 → agora medio (limiar_medio=1)
    d = mr.escolher_modelo("resumo", "x" * 900)
    assert d.tier == "medio"


# ── Anthropic RAPIDO vs COMPLEXO por tier ─────────────────────────────────────

def test_anthropic_leve_usa_rapido(monkeypatch):
    _cfg(monkeypatch, ROTEAMENTO_PROVIDER_LEVE="anthropic")
    d = mr.escolher_modelo("resumo", "curto")
    assert d.tier == "leve"
    assert d.model == "claude-haiku-4-5-20251001"  # leve → RAPIDO


# ── calcular_score é puro/testável ────────────────────────────────────────────

def test_calcular_score_retorna_motivos():
    score, motivos = mr.calcular_score("estrategia", "texto")
    assert isinstance(score, int)
    assert any("task_type" in m for m in motivos)
