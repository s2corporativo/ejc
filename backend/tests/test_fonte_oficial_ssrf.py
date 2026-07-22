"""Auditoria RAG — endurecimento de `_fonte_oficial` (ia_governanca).

Antes: `any(dominio in url.lower() ...)` — substring em TODA a URL, burlável por
`https://evil.com/?x=tjmg.jus.br` ou `https://tjmg.jus.br.evil.net/`. Agora valida
o HOSTNAME normalizado (via urlparse), exige https e aceita apenas correspondência
exata de domínio oficial ou subdomínio legítimo.

Teste puro (sem rede/DB): valida a lógica de decisão de domínio oficial.
"""
from __future__ import annotations

import pytest

from app.routers.ia_governanca import _fonte_oficial


@pytest.mark.parametrize("url", [
    "https://tjmg.jus.br/consulta/123",
    "https://www.tjmg.jus.br/",
    "https://portal.stj.jus.br/x",
    "https://stf.jus.br/pauta",
    "https://cnj.jus.br/a",
    "https://fonaje.amb.com.br/enunciados",
    # Federador oficial LexML (Senado) — face da federação RAG. As URLs de
    # consulta/URN geradas pelo ingestor lexml precisam passar nesta allowlist.
    "https://www.lexml.gov.br/busca/pesquisa?palavras=x&tipo=legislacao",
    "https://lexml.gov.br/urn/urn:lex:br;minas.gerais:assembleia.legislativa",
])
def test_dominios_oficiais_aceitos(url):
    assert _fonte_oficial(url) is True


@pytest.mark.parametrize("url", [
    # substring na query/path não é mais aceita (bypass antigo)
    "https://evil.com/?x=tjmg.jus.br",
    "https://evil.com/tjmg.jus.br",
    # domínio de fachada com o oficial como prefixo do host
    "https://tjmg.jus.br.evil.net/",
    "https://lexml.gov.br.evil.net/urn/x",
    # userinfo com '@' — hostname real é evil.com
    "https://tjmg.jus.br@evil.com/",
    # http não é aceito (exige https)
    "http://tjmg.jus.br/",
    # domínios não oficiais
    "https://jusbrasil.com.br/",
    "https://google.com/",
    # vazios / malformados
    "",
    None,
    "not a url",
    "ftp://tjmg.jus.br/",
])
def test_urls_nao_oficiais_ou_burla_rejeitadas(url):
    assert _fonte_oficial(url) is False
