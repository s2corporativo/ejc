"""Indicativo de encerramento (app/services/saneamento/encerramento.py).

Regra inegociável coberta: o módulo SINALIZA, nunca decide
(exige_revisao_humana é sempre True); reativador/suspensivo posterior ao
terminativo cancela o indicativo; código TPU ainda não classificado após o
terminativo REBAIXA a confiança em vez de assumir (falso negativo é barato,
falso positivo custa prazo).

Portado do pacote de referência ejc-saneamento/tests/test_saneamento.py.
Lógica pura — sem chamada de rede, sem banco.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.saneamento.encerramento import (
    Confianca,
    Movimento,
    avaliar_encerramento,
    extrair_movimentos,
)
from app.services.saneamento.tpu import CatalogoTPU

NUM_CNJ_OFICIAL = "00008323520184013202"

CATALOGO = CatalogoTPU.de_registros([
    {"codigo": 246, "nome": "Arquivado definitivamente", "classe": "terminativo",
     "fonte": "TJDFT"},
    {"codigo": 9001, "nome": "Suspensão (fictício de teste)", "classe": "suspensivo",
     "fonte": "teste"},
    {"codigo": 9002, "nome": "Desarquivamento (fictício de teste)",
     "classe": "reativador", "fonte": "teste"},
    {"codigo": 9003, "nome": "Juntada (fictício de teste)", "classe": "ordinario",
     "fonte": "teste"},
])

AGORA = datetime(2026, 8, 30, tzinfo=timezone.utc)


def _mov(codigo, dias_atras, nome="x"):
    return Movimento(codigo=codigo, nome=nome, data=AGORA - timedelta(days=dias_atras))


def test_terminativo_com_silencio_longo_e_candidato_com_confianca_alta():
    ind = avaliar_encerramento(
        NUM_CNJ_OFICIAL, [_mov(9003, 900), _mov(246, 400)], CATALOGO, referencia=AGORA
    )
    assert ind.candidato is True
    assert ind.confianca is Confianca.ALTA
    assert ind.exige_revisao_humana is True


def test_terminativo_recente_nao_e_candidato():
    ind = avaliar_encerramento(NUM_CNJ_OFICIAL, [_mov(246, 30)], CATALOGO, referencia=AGORA)
    assert ind.candidato is False
    assert ind.confianca is Confianca.BAIXA


def test_reativador_posterior_cancela_o_indicativo():
    ind = avaliar_encerramento(
        NUM_CNJ_OFICIAL, [_mov(246, 800), _mov(9002, 700)], CATALOGO, referencia=AGORA
    )
    assert ind.candidato is False
    assert "reativador" in " ".join(ind.motivos)


def test_suspensivo_posterior_cancela_o_indicativo():
    ind = avaliar_encerramento(
        NUM_CNJ_OFICIAL, [_mov(246, 800), _mov(9001, 700)], CATALOGO, referencia=AGORA
    )
    assert ind.candidato is False
    assert "suspensivo" in " ".join(ind.motivos)


def test_codigo_nao_classificado_posterior_rebaixa_confianca():
    ind = avaliar_encerramento(
        NUM_CNJ_OFICIAL, [_mov(246, 800), _mov(7777, 700)], CATALOGO, referencia=AGORA
    )
    assert ind.candidato is True
    assert ind.confianca is Confianca.MEDIA


def test_sem_terminativo_nunca_e_candidato():
    ind = avaliar_encerramento(
        NUM_CNJ_OFICIAL, [_mov(9003, 3000)], CATALOGO, referencia=AGORA
    )
    assert ind.candidato is False
    assert ind.confianca is Confianca.NENHUMA


def test_sem_movimentos_nao_quebra():
    ind = avaliar_encerramento(NUM_CNJ_OFICIAL, [], CATALOGO, referencia=AGORA)
    assert ind.candidato is False
    assert ind.confianca is Confianca.NENHUMA


def test_para_dict_sempre_marca_exige_revisao_humana():
    ind = avaliar_encerramento(
        NUM_CNJ_OFICIAL, [_mov(9003, 900), _mov(246, 400)], CATALOGO, referencia=AGORA
    )
    assert ind.para_dict()["exige_revisao_humana"] is True


def test_extrair_movimentos_descarta_data_invalida_e_ordena():
    doc = {
        "movimentos": [
            {"codigo": 246, "nome": "b", "dataHora": "2024-05-01T10:00:00Z"},
            {"codigo": 9003, "nome": "a", "dataHora": "2023-01-01T10:00:00Z"},
            {"codigo": 1, "nome": "sem data"},
            {"codigo": 2, "nome": "data suja", "dataHora": "não-é-data"},
        ]
    }
    movs = extrair_movimentos(doc)
    assert [m.nome for m in movs] == ["a", "b"]


def test_catalogo_cobertura_conta_classificados_e_pendentes():
    cat = CatalogoTPU.de_registros([
        {"codigo": 246, "nome": "x", "classe": "terminativo", "fonte": "y"},
        {"codigo": 999, "nome": "z", "classe": "nao_classificado", "fonte": ""},
    ])
    cob = cat.cobertura
    assert cob == {"total": 2, "classificados": 1, "pendentes": 1}
