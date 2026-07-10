"""honorarios_oab._parse_json: função pura que extrai o JSON da resposta da IA.

Ramos: JSON limpo, JSON embutido em prosa (fallback por regex), aninhado
(regex guloso pega até a última chave), e entradas inválidas/vazias -> None.
"""
from __future__ import annotations

from app.routers.honorarios_oab import _parse_json


def test_json_limpo_e_parseado():
    assert _parse_json('{"minimo": "R$ 1000", "recomendado": "R$ 2000"}') == {
        "minimo": "R$ 1000",
        "recomendado": "R$ 2000",
    }


def test_json_embutido_em_prosa_usa_fallback_regex():
    txt = 'Segue a estimativa:\n{"minimo": "R$ 500"}\nEspero ter ajudado.'
    assert _parse_json(txt) == {"minimo": "R$ 500"}


def test_regex_guloso_captura_objeto_aninhado_completo():
    txt = 'resposta {"a": {"b": 2}} fim'
    assert _parse_json(txt) == {"a": {"b": 2}}


def test_string_vazia_retorna_none():
    assert _parse_json("") is None


def test_none_retorna_none():
    assert _parse_json(None) is None


def test_texto_sem_json_retorna_none():
    assert _parse_json("nenhuma chave aqui") is None


def test_chave_aberta_sem_fechamento_retorna_none():
    assert _parse_json('{"minimo": ') is None
