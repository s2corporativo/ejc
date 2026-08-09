"""Contrato jurídico da leitura documental — dados 100% fictícios."""
from __future__ import annotations

import json

import pytest

from app.services.documento_service import _montar_intake_result


def test_intake_result_popula_provas_necessarias():
    llm = {
        "classificacao": {"area": "civel"},
        "resumo_executivo": {"fatos": "Atraso fictício na entrega de imóvel."},
        "provas_necessarias": [
            {
                "titulo": "Contrato de promessa de compra e venda",
                "tipo": "documental",
                "fato_probando": "Prazo de entrega pactuado",
                "ja_disponivel": True,
            },
            {
                "titulo": "Comprovantes de aluguel",
                "tipo": "documental",
                "fato_probando": "Dano material pelo atraso",
                "ja_disponivel": False,
            },
        ],
    }

    resultado = _montar_intake_result(llm, {})

    assert [prova.titulo for prova in resultado.provas] == [
        "Contrato de promessa de compra e venda",
        "Comprovantes de aluguel",
    ]
    assert resultado.provas[0].tipo == "documental"
    assert resultado.provas[0].finalidade == "Prazo de entrega pactuado"
    assert resultado.necessita_revisao_humana is True


@pytest.mark.parametrize(
    "entrada",
    [
        {"provas_necessarias": "não é lista"},
        {"provas_necessarias": ["string", 42, None]},
        {"provas_necessarias": [{"tipo": "documental"}]},
        {},
    ],
)
def test_provas_malformadas_degradam_para_lista_vazia(entrada):
    assert _montar_intake_result(entrada, {}).provas == []


def test_prompt_estrategico_pede_plano_probatorio_e_brechas():
    from app.services.analise_estrategica import PROMPT_ANALISE

    prompt = PROMPT_ANALISE.format(contexto="CASO FICTÍCIO")
    for chave in (
        "provas_necessarias",
        "fato_probando",
        "brechas_preliminares",
        "prescricao",
        "decadencia",
        "incompetencia",
        "ilegitimidade",
        "nulidades",
        "pontos_fortes",
        "pontos_fracos",
    ):
        assert chave in prompt, f"prompt perdeu {chave}"

    inicio = prompt.index('{\n  "partes"')
    json.loads(prompt[inicio : prompt.rindex("}") + 1])


def test_prompt_mantem_antialucinacao_e_hipotese_a_verificar():
    from app.services.analise_estrategica import PROMPT_ANALISE

    prompt = PROMPT_ANALISE.format(contexto="CASO FICTÍCIO")
    assert "NUNCA invente jurisprudência" in prompt
    assert "HIPÓTESE A VERIFICAR" in prompt
    assert "BASE DE CONHECIMENTO INTERNA" in prompt
