"""Radar Jurisprudencial — Camada 1, determinística (PR 4 da série de
consolidação do Banco de Teses).

`services/radar_jurisprudencial.py` é uma função pura, sem banco: reusa
`tese_caso_matcher.pontuar_texto` (mesmo peso do resto do repo) e acrescenta
o casamento por citação estruturada (súmula/recurso/processo/artigo), via
`verificador_jurisprudencia.analisar_texto`. O que mais importa cobrir aqui é
a composição score+citação → severidade, que é a única regra nova.
"""
from __future__ import annotations

from app.services.radar_jurisprudencial import avaliar_decisao
from app.services.tese_caso_matcher import extrair_termos


def _tese(titulo, *, tid="t1", area=None, fundamentacao="", jurisprudencia=""):
    return {
        "id": tid, "titulo": titulo, "area_juridica": area,
        "termos": extrair_termos(titulo, fundamentacao),
        "fundamentacao": fundamentacao, "jurisprudencia": jurisprudencia,
    }


def _decisao(titulo, ementa, *, area=None):
    return {
        "id": "d1", "titulo": titulo, "ementa": ementa, "tribunal": "STJ",
        "numero_processo": "REsp 1.111.111/SP", "data_julgamento": "2026-08-01",
        "link": "https://stj.jus.br/x", "area_juridica": area,
    }


# ── score textual (reuso do tese_caso_matcher) ───────────────────────────────

def test_decisao_sem_termo_em_comum_nao_gera_alerta():
    tese = _tese("Aplicação do CDC às instituições financeiras", area="bancario")
    decisao = _decisao("Recurso sobre pensão alimentícia", "Ementa de família.", area="civil")
    assert avaliar_decisao(decisao, [tese]) == []


def test_score_textual_com_area_alinhada_gera_severidade_alta_ou_media():
    tese = _tese("Responsabilidade civil das instituições financeiras", area="bancario")
    decisao = _decisao(
        "Responsabilidade civil das instituições financeiras",
        "Decisão sobre responsabilidade civil de instituições financeiras.",
        area="bancario",
    )
    saida = avaliar_decisao(decisao, [tese])
    assert len(saida) == 1
    assert saida[0]["tese_id"] == "t1"
    assert saida[0]["area_alinhada"] is True
    assert saida[0]["severidade"] in ("alta", "media")
    assert saida[0]["citacoes_casadas"] == []


def test_score_abaixo_do_piso_e_descartado():
    tese = _tese("Guarda compartilhada em ação de família", area="familia")
    decisao = _decisao("Nota sobre honorários", "Texto qualquer sem relação.", area="civil")
    assert avaliar_decisao(decisao, [tese]) == []


# ── citação estruturada — camada 1 "número de súmula/tema/artigo" ───────────

def test_sumula_identica_eleva_severidade_para_critica():
    tese = _tese(
        "Correção monetária em contrato bancário", area="bancario",
        fundamentacao="Aplica-se a Súmula 297 do STJ ao caso.",
    )
    decisao = _decisao(
        "Correção monetária em contrato bancário",
        "Nos termos da Súmula 297 do STJ, aplica-se o CDC às instituições financeiras.",
        area="bancario",
    )
    saida = avaliar_decisao(decisao, [tese])
    assert len(saida) == 1
    assert saida[0]["severidade"] == "critica"
    assert saida[0]["citacoes_casadas"] == [{"tipo": "sumula", "trecho": "Súmula 297 do STJ"}]


def test_sumula_diferente_nao_conta_como_citacao_casada():
    tese = _tese(
        "Correção monetária em contrato bancário", area="bancario",
        fundamentacao="Aplica-se a Súmula 297 do STJ ao caso.",
    )
    decisao = _decisao(
        "Correção monetária em contrato bancário",
        "Nos termos da Súmula 121 do STJ, aplica-se o CDC às instituições financeiras.",
        area="bancario",
    )
    saida = avaliar_decisao(decisao, [tese])
    assert len(saida) == 1
    assert saida[0]["citacoes_casadas"] == []
    assert saida[0]["severidade"] != "critica"


def test_sumula_implausivel_fora_de_faixa_nao_conta_como_citacao_casada():
    """SUMULA_TETO filtra número acima do teto plausível (indício de
    alucinação) — mesmo que a tese cite o mesmo número inválido, isso não
    deve virar match de citação estruturada."""
    tese = _tese(
        "Tema qualquer", area="bancario",
        fundamentacao="Súmula 999 do STJ garante o direito.",
    )
    decisao = _decisao(
        "Tema qualquer",
        "Conforme a Súmula 999 do STJ, o direito está garantido.",
        area="bancario",
    )
    saida = avaliar_decisao(decisao, [tese])
    # Ainda pode gerar alerta pelo score textual, mas nunca por citação.
    for item in saida:
        assert item["citacoes_casadas"] == []


def test_artigo_identico_eleva_severidade_para_critica():
    tese = _tese(
        "Vício do produto e responsabilidade do fornecedor", area="consumidor",
        fundamentacao="Aplicação do art. 18 do CDC.",
    )
    decisao = _decisao(
        "Vício do produto e responsabilidade do fornecedor",
        "O art. 18 do CDC impõe responsabilidade solidária ao fornecedor.",
        area="consumidor",
    )
    saida = avaliar_decisao(decisao, [tese])
    assert len(saida) == 1
    assert saida[0]["severidade"] == "critica"
    assert saida[0]["citacoes_casadas"][0]["tipo"] == "artigo"


# ── múltiplas teses — ordenação, teto e piso custom ─────────────────────────

def test_multiplas_teses_ordenadas_por_severidade_depois_score():
    tese_critica = _tese(
        "Correção monetária em contrato bancário", tid="t-critica", area="bancario",
        fundamentacao="Súmula 297 do STJ.",
    )
    tese_media = _tese("Correção monetária em contrato bancário", tid="t-media", area="bancario")
    decisao = _decisao(
        "Correção monetária em contrato bancário",
        "Nos termos da Súmula 297 do STJ, aplica-se o CDC às instituições financeiras.",
        area="bancario",
    )
    saida = avaliar_decisao(decisao, [tese_media, tese_critica])
    assert [t["tese_id"] for t in saida] == ["t-critica", "t-media"]


def test_teses_sem_termos_sao_ignoradas_sem_erro():
    tese_vazia = {"id": "vazia", "titulo": "", "area_juridica": None, "termos": [],
                  "fundamentacao": "", "jurisprudencia": ""}
    decisao = _decisao("Qualquer título", "Qualquer ementa.")
    assert avaliar_decisao(decisao, [tese_vazia]) == []


def test_lista_de_teses_vazia_devolve_lista_vazia():
    decisao = _decisao("Qualquer título", "Qualquer ementa.")
    assert avaliar_decisao(decisao, []) == []


def test_limite_restringe_quantidade_de_teses_na_saida():
    teses = [
        _tese("Responsabilidade civil das instituições financeiras", tid=f"t{i}", area="bancario")
        for i in range(5)
    ]
    decisao = _decisao(
        "Responsabilidade civil das instituições financeiras",
        "Decisão sobre responsabilidade civil de instituições financeiras.",
        area="bancario",
    )
    saida = avaliar_decisao(decisao, teses, limite=2)
    assert len(saida) == 2
