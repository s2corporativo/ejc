"""Regressões focadas de Querido Diário e LexML extraídas do PR #1452.

Sem rede externa: fixa contratos de reação a indisponibilidade e proveniência.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.user import UserRole
from app.services.jurisprudencia_externa import (
    LexMLBloqueadoError,
    _e_intersticio_antibot,
)


class _RespostaFake:
    def __init__(self, content_type: str, texto: str):
        self.headers = {"content-type": content_type}
        self.text = texto


def test_querido_diario_usa_host_atual_e_timeout_nao_agressivo():
    from app.integrations.querido_diario_client import (
        QUERIDO_DIARIO_BASE,
        QueridoDiarioClient,
    )

    assert QUERIDO_DIARIO_BASE == "https://api.queridodiario.org.br"
    assert ".ok.org.br" not in QUERIDO_DIARIO_BASE
    assert QueridoDiarioClient().timeout.read >= 30.0


def test_lexml_distingue_html_de_desafio_de_xml_legitimo():
    html = (
        "<!doctype html><html><title>Verificação de segurança</title>"
        "<script>proof-of-work</script></html>"
    )
    xml = '<?xml version="1.0"?><feed><entry><title>Acórdão</title></entry></feed>'

    assert _e_intersticio_antibot(_RespostaFake("text/html; charset=utf-8", html))
    assert not _e_intersticio_antibot(_RespostaFake("application/xml", xml))
    assert not _e_intersticio_antibot(
        _RespostaFake("text/html", "resultado legítimo sem marcador de desafio")
    )


def test_conteudo_lexml_avisa_que_ementa_nao_e_inteiro_teor():
    from app.services.ingestors.lexml import _monta_conteudo

    conteudo = _monta_conteudo(
        {
            "titulo": "RE 1.234.567/MG",
            "tribunal": "STF",
            "ementa": "Resumo oficial do julgamento para teste.",
        },
        "jurisprudencia",
    )

    assert "NÃO É O INTEIRO TEOR" in conteudo
    assert "inteiro teor na fonte oficial" in conteudo
    assert conteudo.index("PROVENIÊNCIA") < conteudo.index("Resumo oficial")


@pytest.mark.asyncio
async def test_busca_agregada_distingue_vazio_de_fonte_indisponivel(monkeypatch):
    from app.services import jurisprudencia_externa as je

    async def _lexml_bloqueado(*_args, **_kwargs):
        raise LexMLBloqueadoError("desafio anti-bot")

    async def _tjmg_vazio(*_args, **_kwargs):
        return []

    monkeypatch.setattr(je, "buscar_lexml", _lexml_bloqueado)
    monkeypatch.setattr(je, "buscar_tjmg", _tjmg_vazio)

    resultado = await je.buscar_todas_fontes("dano moral")

    assert resultado["fontes"]["lexml"]["respondeu"] is False
    assert resultado["fontes"]["lexml"]["erro"] == "LexMLBloqueadoError"
    assert resultado["fontes"]["tjmg"]["respondeu"] is True
    assert resultado["fontes_com_falha"] == ["lexml"]


@pytest.mark.asyncio
async def test_endpoint_lexml_converte_bloqueio_em_503_controlado(monkeypatch):
    from app.routers import jurisprudencia_externa as router_mod

    async def _bloqueado(*_args, **_kwargs):
        raise LexMLBloqueadoError("desafio anti-bot")

    monkeypatch.setattr(router_mod, "buscar_lexml", _bloqueado)
    user = SimpleNamespace(role=UserRole.advogado)

    with pytest.raises(HTTPException) as exc:
        await router_mod.buscar_lexml_endpoint(
            q="teste juridico",
            tipo="jurisprudencia",
            pagina=1,
            por_pagina=10,
            cu=user,
        )

    assert exc.value.status_code == 503
    assert "anti-bot" in str(exc.value.detail).lower()
