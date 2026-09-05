# ── tests/test_djen_geo_bloqueio.py ──────────────────────────────────────────
# `comunicaapi.pje.jus.br` fica atrás de uma distribuição CloudFront com
# restrição por país: de fora do Brasil devolve 403 em qualquer rota, inclusive
# `/swagger` (verificado em 04/09/2026, egress IAD55 — no mesmo túnel a
# BrasilAPI respondeu 200 e o DataJud 401, o que descarta bloqueio genérico a
# serviço brasileiro).
#
# Classificado como `http_4xx` genérico, o diagnóstico mandava o operador
# procurar defeito no cadastro de OAB — quando a causa é a localização do
# servidor, que nenhum ajuste de cadastro corrige.
from __future__ import annotations

import httpx

from app.services.djen_service import _classificar_erro_fonte

_CORPO_CLOUDFRONT = (
    "<HTML><HEAD><TITLE>ERROR: The request could not be satisfied</TITLE></HEAD>"
    "<BODY><H1>403 ERROR</H1>The Amazon CloudFront distribution is configured "
    "to block access from your country.</BODY></HTML>"
)


def _erro_http(status: int, corpo: str = "", content_type: str = "text/html") -> httpx.HTTPStatusError:
    requisicao = httpx.Request("GET", "https://comunicaapi.pje.jus.br/api/v1/comunicacao")
    resposta = httpx.Response(
        status, text=corpo, request=requisicao, headers={"content-type": content_type}
    )
    return httpx.HTTPStatusError("erro", request=requisicao, response=resposta)


def test_403_do_cloudfront_por_pais_e_identificado():
    assert _classificar_erro_fonte(_erro_http(403, _CORPO_CLOUDFRONT)) == "geo_bloqueado"


def test_403_comum_continua_http_4xx():
    """Um 403 do próprio CNJ (rate limit, bloqueio de agente) não é geográfico
    — confundir os dois mandaria o operador mexer em infraestrutura à toa."""
    assert _classificar_erro_fonte(_erro_http(403, '{"erro":"acesso negado"}')) == "http_4xx"


def test_outros_status_nao_mudam():
    assert _classificar_erro_fonte(_erro_http(404)) == "http_4xx"
    assert _classificar_erro_fonte(_erro_http(500)) == "http_5xx"
    assert _classificar_erro_fonte(_erro_http(302)) == "http_status"


def test_marcador_e_insensivel_a_caixa():
    assert (
        _classificar_erro_fonte(_erro_http(403, _CORPO_CLOUDFRONT.upper()))
        == "geo_bloqueado"
    )


def test_demais_falhas_seguem_classificadas_como_antes():
    requisicao = httpx.Request("GET", "https://exemplo")
    assert _classificar_erro_fonte(httpx.ConnectTimeout("t", request=requisicao)) == "timeout"
    assert _classificar_erro_fonte(httpx.ConnectError("c", request=requisicao)) == "transporte"
    assert _classificar_erro_fonte(ValueError("payload")) == "payload_invalido"
    assert _classificar_erro_fonte(RuntimeError("x")) == "erro_interno"
