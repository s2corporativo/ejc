"""Regressões focadas do contrato atual do índice do DOU.

Sem rede externa: valida parse fail-closed, complexidade linear e sanitização.
"""
from __future__ import annotations

import json
import time

import pytest

from app.services import diario_oficial_service as dou


def _html_indice(itens: list[dict]) -> str:
    payload = json.dumps({"jsonArray": itens})
    return f'<html><script id="params" type="application/json">{payload}</script></html>'


def test_extrai_json_embutido_e_keyword_sem_acento():
    itens = [
        {
            "title": "PORTARIA SOBRE LICITAÇÃO Nº 42",
            "content": "Contratação pública.",
            "urlTitle": "portaria-42",
        }
    ]
    extraidos = dou._extrair_json_do_indice(_html_indice(itens))

    assert extraidos == itens
    assert dou._casa_keyword(extraidos[0], "licitacao") is True
    assert dou._casa_keyword(extraidos[0], "tributário") is False


def test_indice_sem_params_e_malformado_falham_fechado():
    with pytest.raises(dou.DOUIndisponivelError, match="contrato do portal mudou"):
        dou._extrair_json_do_indice("<html><body>portal reformulado</body></html>")

    with pytest.raises(dou.DOUIndisponivelError, match="malformado"):
        dou._extrair_json_do_indice('<html><script id="params"')


def test_json_invalido_ou_sem_jsonarray_nao_vira_zero_resultados():
    with pytest.raises(dou.DOUIndisponivelError, match="JSON inválido"):
        dou._extrair_json_do_indice('<script id="params">{INVALIDO}</script>')

    with pytest.raises(dou.DOUIndisponivelError, match="sem jsonArray"):
        dou._extrair_json_do_indice('<script id="params">{"outro": []}</script>')


def test_parse_de_corpo_hostil_nao_reintroduz_backtracking_quadratico():
    hostil = "<script" * 200_000
    inicio = time.monotonic()
    with pytest.raises(dou.DOUIndisponivelError):
        dou._extrair_json_do_indice(hostil)
    assert time.monotonic() - inicio < 5.0


def test_email_escapa_conteudo_de_terceiro():
    assert dou._esc("Portaria 'X' & <b>Y</b>") == (
        "Portaria &#x27;X&#x27; &amp; &lt;b&gt;Y&lt;/b&gt;"
    )
    assert dou._esc(None) == ""


def test_cache_pode_ser_limpo_entre_execucoes():
    dou._INDICE_CACHE[("01-01-2026", "do1")] = [{"title": "x"}]
    dou.limpar_cache_indice()
    assert dou._INDICE_CACHE == {}
