"""`GET /users/me/calendar-url` tem de respeitar a revogação do feed ICS.

Auditoria funcional de 22/08/2026 (Issue #1237), achado 27. Duas rotas
entregavam a MESMA credencial assinada:

    GET /calendar/me/url        -> obter_url_calendario(), lê a versão vigente
    GET /users/me/calendar-url  -> gerar_token_calendario(cu.id)   ← version=1

O default `version=1` de `gerar_token_calendario` nunca consultava
`calendar_feed_credentials`. Medido contra a stack local: depois de um
`POST /calendar/me/rotate` (version=2), a rota canônica devolvia o token v2
(feed HTTP 200) e o alias devolvia o v1 — que `feed_ics` recusa com **403**.
Ou seja, o usuário rotacionava justamente porque o link havia vazado, e a API
lhe devolvia o link morto, sem dizer que estava morto.

Segundo achado no mesmo endereço: a resposta carrega uma credencial assinada e
saía **sem** `Cache-Control: no-store` — a canônica já marcava. Uma URL
assinada numa resposta cacheável é a mesma classe de erro, um passo antes.

Os dois testes falham na versão anterior do endpoint:
  - o primeiro devolvia a URL v1 depois da rotação;
  - o segundo não tinha cabeçalho de cache nenhum.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import Response

from app.routers import calendar_feed, users


class _Result:
    def __init__(self, value=None):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _DB:
    """Banco mínimo: devolve a versão vigente do feed, como `_versao_feed` lê."""

    def __init__(self, version):
        self.version = version

    async def execute(self, statement):  # noqa: ARG002
        return _Result(self.version)


def _user(uid: str = "user-1"):
    return SimpleNamespace(id=uid, role=SimpleNamespace(value="advogado"))


@pytest.mark.asyncio
async def test_alias_acompanha_a_rotacao_e_nao_reemite_token_revogado(monkeypatch):
    monkeypatch.setattr(calendar_feed.settings, "SECRET_KEY", "segredo-teste")
    monkeypatch.setattr(
        calendar_feed.settings, "FRONTEND_URL", "https://exemplo.invalid"
    )
    cu = _user()

    # version=2: o v1 está revogado — `feed_ics` recusaria aquele token.
    alias = await users.minha_url_calendario(Response(), _DB(2), cu)
    canonica = await calendar_feed.obter_url_calendario(_DB(2), cu.id)

    assert alias == canonica, "alias divergiu da fonte da verdade"
    assert alias["version"] == 2

    revogado = calendar_feed.gerar_token_calendario(cu.id, 1)
    assert revogado not in alias["url"], (
        "o alias reemitiu o token v1, que o feed recusa com 403"
    )
    assert calendar_feed.gerar_token_calendario(cu.id, 2) in alias["url"]


@pytest.mark.asyncio
async def test_alias_sem_rotacao_continua_valendo_o_link_legado(monkeypatch):
    """Compatibilidade: quem nunca rotacionou mantém exatamente a URL de antes."""
    monkeypatch.setattr(calendar_feed.settings, "SECRET_KEY", "segredo-teste")
    monkeypatch.setattr(
        calendar_feed.settings, "FRONTEND_URL", "https://exemplo.invalid"
    )
    cu = _user()

    alias = await users.minha_url_calendario(Response(), _DB(None), cu)

    assert alias["version"] == 1
    assert calendar_feed.gerar_token_calendario(cu.id, 1) in alias["url"]


@pytest.mark.asyncio
async def test_credencial_assinada_nao_e_cacheavel(monkeypatch):
    monkeypatch.setattr(calendar_feed.settings, "SECRET_KEY", "segredo-teste")
    monkeypatch.setattr(
        calendar_feed.settings, "FRONTEND_URL", "https://exemplo.invalid"
    )
    resposta = Response()

    await users.minha_url_calendario(resposta, _DB(1), _user())

    assert resposta.headers["Cache-Control"] == "private, no-store, max-age=0"
    assert resposta.headers["Pragma"] == "no-cache"
    assert resposta.headers["X-Content-Type-Options"] == "nosniff"
