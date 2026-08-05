"""Entrada Universal — leitura estruturada por IA e sua rastreabilidade.

Regressão do teste de campo de 2026-08-05, que reprovou três itens P1 ao subir
um TXT de 43 KB:

  * "Estrutura da resposta da IA" — o pacote era analisado com
    task_type="document_analysis", que resolve DocumentAgent/TarefaIA.RESUMO
    (teto de 900 tokens). O JSON do schema (~15 chaves de topo com listas
    aninhadas) era cortado no meio, o parse falhava e o chamador caía num
    fallback silencioso que despejava o texto cru em `resumo_executivo.fatos` —
    dali o pré-preenchimento do caso o gravava como se fosse fato extraído.
  * "Rastreabilidade das fontes" — modelo, provedor, id do AILog e fontes RAG
    ficavam sepultados em `analise_ia`, sem chegar ao topo da resposta.

Padrão dos vizinhos: fakes locais, sem banco e sem rede.
"""
from __future__ import annotations

import json

import pytest

from app.routers import entrada_universal as router
from app.services.ai.core.agent_registry import AGENT_REGISTRY
from app.services.ai.core.intent_classifier import classify_intent
from app.services.system_prompts import TarefaIA
from app.services.system_prompts.router import get_configuracao

_SCHEMA_COMPLETO = {
    "tipo_documento_principal": "peticao_inicial",
    "fase": "conhecimento",
    "area": "civel",
    "identificacao_processual": {"numero_processo": "0000000-00.0000.0.00.0000"},
    "partes": {"autor": "Fulano", "reu": "Empresa X", "terceiros": []},
    "resumo_executivo": {"fatos": "Contratou e não foi atendido.",
                         "situacao": "Aguardando contestação",
                         "providencia_principal": "Réplica"},
    "prazo": {"data_expressa": "2026-09-01", "requer_confirmacao_humana": True},
}


class _NucleoFake:
    """Substitui o orchestrator: devolve o conteúdo combinado, sem rede."""

    def __init__(self, conteudo: str, **extras):
        self.conteudo = conteudo
        self.extras = extras
        self.chamadas: list[dict] = []

    async def run(self, **kwargs):
        self.chamadas.append(kwargs)
        return {
            "conteudo": self.conteudo,
            "fontes": self.extras.get("fontes", [{"titulo": "Súmula 297 STJ",
                                                  "categoria": "sumula",
                                                  "fonte": "STJ"}]),
            "citacoes": self.extras.get("citacoes", []),
            "alertas": self.extras.get("alertas", []),
            "modelo": "anthropic/claude-x",
            "provider": "anthropic",
            "log_id": "log-123",
            "sem_base_verificavel": self.extras.get("sem_base_verificavel", False),
        }


async def _analisar(monkeypatch, conteudo: str, **extras) -> dict:
    fake = _NucleoFake(conteudo, **extras)
    monkeypatch.setattr(router, "orchestrator", fake)
    resultado = await router._analisar_ia(
        None, None, modalidade=None, case_id=None,
        dossie="D" * 200, deterministico={},
    )
    resultado["_chamadas"] = fake.chamadas
    return resultado


# ── Orçamento de tokens: a causa raiz ────────────────────────────────────────

def test_extracao_estruturada_nao_usa_o_orcamento_de_resumo():
    """document_extraction precisa de teto de dossiê, não de resumo (900)."""
    resumo = get_configuracao(AGENT_REGISTRY["DocumentAgent"].tarefa_padrao)
    extracao = get_configuracao(AGENT_REGISTRY["DocumentExtractionAgent"].tarefa_padrao)
    assert resumo.max_tokens == 900, "premissa do teste: RESUMO segue econômico"
    assert extracao.max_tokens == 5000
    assert AGENT_REGISTRY["DocumentExtractionAgent"].tarefa_padrao is TarefaIA.DOSSIE


def test_task_type_da_entrada_universal_resolve_o_agente_de_extracao():
    intent = classify_intent("document_extraction", "entrada_universal:geral", "")
    assert intent.agente == "DocumentExtractionAgent"
    assert intent.tarefa is TarefaIA.DOSSIE


@pytest.mark.asyncio
async def test_analise_chama_o_nucleo_com_document_extraction(monkeypatch):
    resultado = await _analisar(monkeypatch, json.dumps(_SCHEMA_COMPLETO))
    assert resultado["_chamadas"][0]["task_type"] == "document_extraction"


# ── Estrutura da resposta ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_json_completo_preenche_a_leitura_estruturada(monkeypatch):
    resultado = await _analisar(monkeypatch, json.dumps(_SCHEMA_COMPLETO))
    assert resultado["estrutura_valida"] is True
    assert resultado["area"] == "civel"
    assert resultado["partes"]["autor"] == "Fulano"
    assert "texto_bruto_ia" not in resultado


@pytest.mark.asyncio
async def test_json_truncado_e_reparado_em_vez_de_perdido(monkeypatch):
    # Corte no meio de uma lista aninhada — o que o teto de 900 tokens produzia.
    truncado = (
        '{"area": "civel", "fase": "conhecimento", '
        '"partes": {"autor": "Fulano", "reu": "Empresa'
    )
    resultado = await _analisar(monkeypatch, truncado)
    assert resultado["estrutura_valida"] is True
    assert resultado["area"] == "civel"
    assert resultado["fase"] == "conhecimento"


@pytest.mark.asyncio
async def test_resposta_sem_json_nao_vira_fato_extraido(monkeypatch):
    """O texto cru não pode ocupar `resumo_executivo.fatos`.

    Era daí que o pré-preenchimento tirava `descricao_fatos` do caso: o caso
    nascia com a resposta bruta do modelo gravada como fato do documento.
    """
    resultado = await _analisar(monkeypatch, "Não consegui analisar o documento.")
    assert resultado["estrutura_valida"] is False
    assert resultado.get("resumo_executivo") is None
    assert "Não consegui" in resultado["texto_bruto_ia"]
    assert any("JSON válido" in alerta for alerta in resultado["alertas"])


@pytest.mark.asyncio
async def test_falha_do_nucleo_degrada_sem_derrubar_o_lote(monkeypatch):
    class _Explode:
        async def run(self, **kwargs):
            raise RuntimeError("provedor fora do ar")

    monkeypatch.setattr(router, "orchestrator", _Explode())
    resultado = await router._analisar_ia(
        None, None, modalidade=None, case_id=None,
        dossie="D" * 200, deterministico={},
    )
    assert resultado["ia_disponivel"] is False
    assert resultado["estrutura_valida"] is False
    assert resultado["requer_revisao_humana"] is True


# ── Rastreabilidade ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analise_carrega_modelo_provedor_log_e_fontes(monkeypatch):
    resultado = await _analisar(monkeypatch, json.dumps(_SCHEMA_COMPLETO))
    assert resultado["modelo"] == "anthropic/claude-x"
    assert resultado["provider"] == "anthropic"
    assert resultado["log_id"] == "log-123"
    assert resultado["fontes"][0]["titulo"] == "Súmula 297 STJ"


# ── Reparo de JSON (função pura) ─────────────────────────────────────────────

def test_parse_json_aceita_cerca_markdown():
    assert router._parse_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_fecha_objeto_e_lista_abertos():
    # O último valor está completo (`"c"`), então só faltam os fechamentos.
    parsed = router._parse_json('{"a": [1, 2, {"b": "c"')
    assert parsed == {"a": [1, 2, {"b": "c"}]}


def test_parse_json_descarta_string_cortada_no_meio():
    # Corte DENTRO da string: o valor incompleto é descartado, o resto sobrevive.
    parsed = router._parse_json('{"a": 1, "b": "texto que foi cortado no me')
    assert parsed == {"a": 1}


def test_parse_json_descarta_par_incompleto_da_cauda():
    parsed = router._parse_json('{"a": 1, "b": 2, "c"')
    assert parsed == {"a": 1, "b": 2}


def test_parse_json_sem_objeto_devolve_none():
    assert router._parse_json("texto livre sem chaves") is None
    assert router._parse_json("") is None
