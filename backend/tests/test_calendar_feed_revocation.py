from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.routers.calendar_feed import (
    _url_feed,
    gerar_token_calendario,
    rotacionar_url_ics,
)


def _user(version: int = 1):
    return SimpleNamespace(
        id="user-1",
        role=SimpleNamespace(value="advogado"),
        calendar_token_version=version,
    )


class _DB:
    def __init__(self):
        self.committed = False
        self.refreshed = False

    async def commit(self):
        self.committed = True

    async def refresh(self, obj):
        self.refreshed = True


class _Request:
    headers = {}
    client = SimpleNamespace(host="127.0.0.1")


def test_token_v1_preserva_compatibilidade_e_v2_muda():
    legado = gerar_token_calendario("user-1")
    assert legado == gerar_token_calendario("user-1", 1)
    assert legado != gerar_token_calendario("user-1", 2)
    assert gerar_token_calendario("user-1", 2) != gerar_token_calendario("user-2", 2)


def test_url_feed_usa_versao_atual():
    user = _user(3)
    url = _url_feed(user)
    assert gerar_token_calendario(user.id, 3) in url
    assert url.endswith(".ics")


@pytest.mark.asyncio
async def test_rotacao_incrementa_versao_e_revoga_token_anterior(monkeypatch):
    user = _user(1)
    db = _DB()
    auditado = False

    async def _audit(*args, **kwargs):
        nonlocal auditado
        auditado = True

    monkeypatch.setattr("app.routers.calendar_feed.criar_audit_log", _audit)
    monkeypatch.setattr("app.routers.calendar_feed.obter_ip_real", lambda request: "127.0.0.1")

    token_antigo = gerar_token_calendario(user.id, 1)
    resposta = await rotacionar_url_ics(_Request(), db=db, cu=user)

    assert user.calendar_token_version == 2
    assert token_antigo not in resposta["url"]
    assert gerar_token_calendario(user.id, 2) in resposta["url"]
    assert resposta["version"] == 2
    assert db.committed is True
    assert db.refreshed is True
    assert auditado is True
