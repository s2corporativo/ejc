"""Regressões P0.1 para a situação jurídica extraída do Planalto.

Estes testes fixam o princípio fail-closed: o parser pode reconhecer uma
revogação declarada, mas não pode transformar silêncio da fonte em prova
positiva de vigência nem ampliar revogação parcial para o diploma inteiro.
"""
from __future__ import annotations

from app.services.ingestors.planalto import situacao_juridica


def _blocos(preambulo: str):
    # O parser só considera preâmbulo identificável a partir de MIN_PREAMBULO.
    cabecalho = preambulo + " " + ("Texto oficial compilado. " * 6)
    return [(None, cabecalho), ("Art. 1", "Art. 1º Conteúdo vigente do artigo.")]


def test_revogacao_total_declarada_continua_bloqueando():
    resultado = situacao_juridica(
        _blocos("LEI Nº 1.234. Revogada pela Lei nº 9.999, de 2024.")
    )

    assert resultado["legal_status"] == "revogada"
    assert resultado["legal_status_origem"] == "planalto:texto_compilado"
    assert resultado.get("legal_status_verificado_em")


def test_revogacao_parcial_nao_pode_ser_promovida_a_revogacao_total():
    resultado = situacao_juridica(
        _blocos("LEI Nº 1.234. Parcialmente revogada pela Lei nº 9.999, de 2024.")
    )

    assert resultado["legal_status"] == "parcialmente_revogada"
    assert resultado["legal_status"] != "revogada"
    assert resultado.get("legal_status_verificado_em")


def test_ausencia_de_marcacao_nao_prova_vigencia_positiva():
    resultado = situacao_juridica(
        _blocos("LEI Nº 1.234. Dispõe sobre matéria administrativa e dá outras providências.")
    )

    assert resultado.get("legal_status") == "vigencia_nao_verificada"
    assert resultado.get("legal_status") != "vigente"
    assert resultado.get("legal_status_inferido_em")
    assert not resultado.get("legal_status_verificado_em")


def test_sem_preambulo_identificavel_continua_fail_closed():
    resultado = situacao_juridica(
        [("Art. 1", "Art. 1º A página começou diretamente no articulado.")]
    )

    assert resultado == {}
