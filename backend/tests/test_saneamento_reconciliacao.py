"""Reconciliação base interna × DataJud (app/services/saneamento/reconciliacao.py).

Regra inegociável coberta: toda divergência é APONTAMENTO, nunca correção
automática — o DataJud nunca sobrescreve a base interna; nivelSigilo > 0 gera
divergência do tipo SIGILO (tratamento restrito).

Portado do pacote de referência ejc-saneamento/tests/test_saneamento.py.
Lógica pura — sem chamada de rede, sem banco.
"""
from __future__ import annotations

from app.services.saneamento.reconciliacao import TipoDivergencia, reconciliar

NUM_CNJ_OFICIAL = "00008323520184013202"


def test_reconciliacao_aponta_ausencias_e_divergencias():
    interno = {
        NUM_CNJ_OFICIAL: {"classe": {"codigo": 7}, "orgao_julgador": {"codigo": 1},
                          "data_ajuizamento": "2018-01-10"},
        "11111111111111111111": {"classe": {"codigo": 1}},
    }
    datajud = {
        NUM_CNJ_OFICIAL: [{
            "grau": "G1",
            "classe": {"codigo": 9},
            "orgaoJulgador": {"codigo": 1},
            "dataAjuizamento": "2018-01-10T00:00:00Z",
            "nivelSigilo": 0,
        }],
        "22222222222222222222": [{"grau": "G1", "nivelSigilo": 0}],
    }
    rel = reconciliar(interno, datajud)
    tipos = {d.tipo for d in rel.divergencias}
    assert TipoDivergencia.CLASSE_DIVERGENTE in tipos
    assert TipoDivergencia.AUSENTE_NO_DATAJUD in tipos
    assert TipoDivergencia.AUSENTE_NA_BASE in tipos
    assert TipoDivergencia.ORGAO_DIVERGENTE not in tipos


def test_sigilo_e_sinalizado():
    rel = reconciliar(
        {NUM_CNJ_OFICIAL: {}},
        {NUM_CNJ_OFICIAL: [{"grau": "G1", "nivelSigilo": 2}]},
    )
    assert any(d.tipo is TipoDivergencia.SIGILO for d in rel.divergencias)


def test_sem_divergencia_quando_tudo_confere():
    interno = {NUM_CNJ_OFICIAL: {
        "classe": {"codigo": 9}, "orgao_julgador": {"codigo": 1},
        "data_ajuizamento": "2018-01-10",
    }}
    datajud = {NUM_CNJ_OFICIAL: [{
        "grau": "G1", "classe": {"codigo": 9}, "orgaoJulgador": {"codigo": 1},
        "dataAjuizamento": "2018-01-10T00:00:00Z", "nivelSigilo": 0,
    }]}
    rel = reconciliar(interno, datajud)
    assert rel.divergencias == []


def test_usa_documento_de_menor_grau_como_referencia():
    interno = {NUM_CNJ_OFICIAL: {"orgao_julgador": {"codigo": 5}}}
    datajud = {NUM_CNJ_OFICIAL: [
        {"grau": "G2", "orgaoJulgador": {"codigo": 999}, "nivelSigilo": 0},
        {"grau": "G1", "orgaoJulgador": {"codigo": 5}, "nivelSigilo": 0},
    ]}
    rel = reconciliar(interno, datajud)
    # G1 (menor grau) confere com a base interna — não deveria apontar
    # ORGAO_DIVERGENTE usando o valor de G2 por engano.
    assert not any(d.tipo is TipoDivergencia.ORGAO_DIVERGENTE for d in rel.divergencias)


def test_resumo_agrupa_por_tipo():
    rel = reconciliar(
        {NUM_CNJ_OFICIAL: {}},
        {NUM_CNJ_OFICIAL: [{"grau": "G1", "nivelSigilo": 1}]},
    )
    assert rel.resumo() == {"sigilo": 1}
