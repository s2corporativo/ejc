# Testes da FONTE ÚNICA de taxonomia de áreas (app/core/taxonomia.py — Fase 0
# do Orquestrador Jurídico): canônico == CaseArea, normalização de aliases,
# mapas explícitos dos vocabulários restritos e aceitação de valores legados.
import pytest

from app.core.taxonomia import (
    AREA_PECA_EXTRA_RITO,
    AREAS_ANALISE_DOCUMENTAL,
    AREAS_CANONICAS,
    AREAS_PECA,
    AREAS_TRIAGEM,
    MAPA_CANONICO_PARA_ANALISE,
    MAPA_CANONICO_PARA_PECA,
    MAPA_CANONICO_PARA_TRIAGEM,
    SENTINELA_OUTRO,
    areas_para_prompt,
    areas_validas,
    normalizar_area,
)
from app.models.case import CaseArea


# ── Canônico == CaseArea ─────────────────────────────────────────────────────

def test_canonico_e_espelho_exato_do_enum_case_area():
    assert list(AREAS_CANONICAS) == [a.value for a in CaseArea]
    assert areas_validas() == list(AREAS_CANONICAS)
    assert len(AREAS_CANONICAS) == len(set(AREAS_CANONICAS))


def test_sentinela_outro_nao_e_area():
    assert SENTINELA_OUTRO not in AREAS_CANONICAS


# ── normalizar_area: identidade e valores legados do banco ───────────────────

def test_todo_valor_ja_gravado_no_banco_normaliza_para_si_mesmo():
    # MUDANÇA ADITIVA: nenhum valor legado de cases.area pode ficar inválido.
    for a in CaseArea:
        assert normalizar_area(a.value) == a.value


@pytest.mark.parametrize("entrada,esperado", [
    # grafias/acentos/caixa
    ("Civil", "civil"),
    ("civel", "civil"),
    ("Cível", "civil"),
    ("CÍVEL", "civil"),
    ("família", "familia"),
    ("Direito de Família", "familia"),
    ("previdenciário", "previdenciario"),
    ("Tributário", "tributario"),
    ("Direito Tributário", "tributario"),
    ("trânsito", "transito"),
    ("sucessões", "sucessoes"),
    # sinônimos evidentes
    ("penal", "criminal"),
    ("Direito Penal", "criminal"),
    ("direito do trabalho", "trabalhista"),
    ("fiscal", "tributario"),
    ("comercial", "empresarial"),
    ("consumerista", "consumidor"),
    ("LGPD", "digital_lgpd"),
    ("Direito Digital / LGPD", "digital_lgpd"),
    ("seguranca_lgpd", "digital_lgpd"),
    ("licitação", "licitacoes"),
])
def test_normalizar_area_aliases(entrada, esperado):
    assert normalizar_area(entrada) == esperado


@pytest.mark.parametrize("entrada", [
    None, "", "   ", "outro", "juizados", "Juizados Especiais",
    "área totalmente inexistente", "público", 123,
])
def test_normalizar_area_sem_correspondencia_segura_devolve_none(entrada):
    # "juizados" é rito (não área) e "outro" é sentinela — nunca canônicos.
    assert normalizar_area(entrada) is None


# ── areas_para_prompt ────────────────────────────────────────────────────────

def test_areas_para_prompt_todas_e_subconjunto():
    assert areas_para_prompt() == ", ".join(AREAS_CANONICAS)
    assert areas_para_prompt(["civil", "criminal"], separador="|") == "civil|criminal"


def test_areas_para_prompt_rejeita_vocabulario_fantasma():
    with pytest.raises(ValueError):
        areas_para_prompt(["civil", "area_inventada"])


# ── mapa (a): análise documental (9 áreas) ───────────────────────────────────

def test_mapa_analise_cobre_todo_o_canonico_e_so_o_subconjunto():
    assert set(AREAS_ANALISE_DOCUMENTAL) <= set(AREAS_CANONICAS)
    assert len(AREAS_ANALISE_DOCUMENTAL) == 9
    assert set(MAPA_CANONICO_PARA_ANALISE) == set(AREAS_CANONICAS)
    for v in MAPA_CANONICO_PARA_ANALISE.values():
        assert v is None or v in AREAS_ANALISE_DOCUMENTAL


def test_mapa_analise_nunca_mapeia_para_area_juridicamente_diversa():
    # O bug histórico: documento médico virava "civil" e licitação virava
    # área errada. Sem correspondência segura → None (decisão humana/HITL).
    assert MAPA_CANONICO_PARA_ANALISE["medico"] is None
    assert MAPA_CANONICO_PARA_ANALISE["saude"] is None
    assert MAPA_CANONICO_PARA_ANALISE["licitacoes"] is None
    assert MAPA_CANONICO_PARA_ANALISE["administrativo"] is None
    assert MAPA_CANONICO_PARA_ANALISE["bancario"] is None
    # correspondências seguras (sub-ramos do civil/empresarial)
    assert MAPA_CANONICO_PARA_ANALISE["imobiliario"] == "civil"
    assert MAPA_CANONICO_PARA_ANALISE["sucessoes"] == "civil"
    assert MAPA_CANONICO_PARA_ANALISE["contratual"] == "civil"
    assert MAPA_CANONICO_PARA_ANALISE["societario"] == "empresarial"
    # identidade nas 9 originais
    for a in AREAS_ANALISE_DOCUMENTAL:
        assert MAPA_CANONICO_PARA_ANALISE[a] == a


# ── mapa (b): triagem automática ─────────────────────────────────────────────

def test_mapa_triagem_cobre_todo_o_canonico():
    assert set(AREAS_TRIAGEM) <= set(AREAS_CANONICAS)
    assert set(MAPA_CANONICO_PARA_TRIAGEM) == set(AREAS_CANONICAS)
    for v in MAPA_CANONICO_PARA_TRIAGEM.values():
        assert v == SENTINELA_OUTRO or v in AREAS_TRIAGEM


def test_mapa_triagem_decisoes_juridicas():
    assert MAPA_CANONICO_PARA_TRIAGEM["licitacoes"] == "administrativo"
    assert MAPA_CANONICO_PARA_TRIAGEM["societario"] == "empresarial"
    assert MAPA_CANONICO_PARA_TRIAGEM["imobiliario"] == "civil"
    # ambíguos vão para a sentinela, nunca para área diversa
    assert MAPA_CANONICO_PARA_TRIAGEM["medico"] == SENTINELA_OUTRO
    assert MAPA_CANONICO_PARA_TRIAGEM["transito"] == SENTINELA_OUTRO
    assert MAPA_CANONICO_PARA_TRIAGEM["digital_lgpd"] == SENTINELA_OUTRO


def test_vocabulario_legado_da_triagem_segue_aceito():
    # O prompt antigo emitia "civel" e "penal": parsers devem seguir aceitando.
    assert normalizar_area("civel") == "civil"
    assert normalizar_area("penal") == "criminal"
    # e todo slug do vocabulário atual da triagem é canônico (identidade)
    for a in AREAS_TRIAGEM:
        assert normalizar_area(a) == a


# ── mapa (c): gerador de peças (AREAS_DIREITO) ───────────────────────────────

def test_areas_peca_identicas_ao_vocabulario_do_pipeline():
    from app.services.peca_service import AREAS_DIREITO

    # mesma lista, MESMA ORDEM (o /pecas/meta e a numeração dependem dela)
    assert list(AREAS_PECA) == list(AREAS_DIREITO)
    assert AREA_PECA_EXTRA_RITO == "juizados"
    assert set(AREAS_PECA) - {AREA_PECA_EXTRA_RITO} <= set(AREAS_CANONICAS)


def test_mapa_peca_cobre_todo_o_canonico():
    assert set(MAPA_CANONICO_PARA_PECA) == set(AREAS_CANONICAS)
    for v in MAPA_CANONICO_PARA_PECA.values():
        assert v is None or v in AREAS_PECA
    # "juizados" é do pipeline, não do canônico — nunca é chave do mapa
    assert AREA_PECA_EXTRA_RITO not in MAPA_CANONICO_PARA_PECA
    assert MAPA_CANONICO_PARA_PECA["licitacoes"] == "administrativo"
    assert MAPA_CANONICO_PARA_PECA["medico"] is None
    assert MAPA_CANONICO_PARA_PECA["saude"] is None


# ── consumidores usam a fonte única ──────────────────────────────────────────

def test_prompt_da_triagem_deriva_da_fonte_unica():
    from app.services.case_intel import SYS_TRIAGEM

    esperado = '"<' + "|".join(AREAS_TRIAGEM) + f'|{SENTINELA_OUTRO}>"'
    assert esperado in SYS_TRIAGEM
    # grafias antigas saíram do PROMPT (mas seguem aceitas no parse)
    assert "civel" not in SYS_TRIAGEM
    assert "|penal|" not in SYS_TRIAGEM


def test_esquema_da_analise_documental_deriva_da_fonte_unica():
    from app.services.documento_service import ESQUEMA

    assert '"area" deve ser uma de: ' + ", ".join(AREAS_ANALISE_DOCUMENTAL) + "." in ESQUEMA
    assert "__AREAS_ANALISE__" not in ESQUEMA
