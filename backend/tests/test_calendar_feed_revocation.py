"""Regressão de revogação individual do feed ICS."""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from fastapi import Request, Response

from app.routers import calendar_feed


class _Result:
    def __init__(self, value=None):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value


class _DB:
    def __init__(self, *values):
        self.results = [_Result(value) for value in values]
        self.executed = []
        self.commits = 0

    async def execute(self, statement):
        self.executed.append(statement)
        return self.results.pop(0)

    async def commit(self):
        self.commits += 1


def _user(uid: str = "user-1"):
    return SimpleNamespace(
        id=uid,
        role=SimpleNamespace(value="advogado"),
    )


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/calendar/me/rotate",
            "headers": [],
            "client": ("127.0.0.1", 54321),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


def test_token_v1_preserva_algoritmo_legado(monkeypatch):
    monkeypatch.setattr(calendar_feed.settings, "SECRET_KEY", "segredo-teste")
    token_padrao = calendar_feed.gerar_token_calendario("abc")
    token_v1 = calendar_feed.gerar_token_calendario("abc", 1)
    assert token_padrao == token_v1
    assert len(token_v1) == 32


def test_rotacao_muda_token_sem_mudar_usuario(monkeypatch):
    monkeypatch.setattr(calendar_feed.settings, "SECRET_KEY", "segredo-teste")
    legado = calendar_feed.gerar_token_calendario("abc", 1)
    novo = calendar_feed.gerar_token_calendario("abc", 2)
    assert novo != legado
    assert novo == calendar_feed.gerar_token_calendario("abc", 2)


@pytest.mark.asyncio
async def test_versao_ausente_equivale_a_legado_v1():
    assert await calendar_feed._versao_feed(_DB(None), "user-1") == 1


@pytest.mark.asyncio
async def test_url_autenticada_usa_versao_persistida_e_nao_aceita_cache(monkeypatch):
    monkeypatch.setattr(
        calendar_feed.settings,
        "FRONTEND_URL",
        "https://ejc.exemplo.test/",
    )
    http_response = Response()
    payload = await calendar_feed.minha_url_calendario_revogavel(
        response=http_response,
        db=_DB(4),
        cu=_user(),
    )
    assert payload["version"] == 4
    assert payload["revogavel"] is True
    assert payload["url"].startswith(
        "https://ejc.exemplo.test/api/calendar/user-1/"
    )
    assert payload["url"].endswith(".ics")
    assert "no-store" in http_response.headers["Cache-Control"]
    assert http_response.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.asyncio
async def test_rotacao_incrementa_audita_e_nao_aceita_cache(monkeypatch):
    auditorias = []

    async def _audit(*args, **kwargs):
        auditorias.append((args, kwargs))

    monkeypatch.setattr(calendar_feed, "criar_audit_log", _audit)
    monkeypatch.setattr(
        calendar_feed.settings,
        "FRONTEND_URL",
        "https://ejc.exemplo.test",
    )
    db = _DB(7)
    http_response = Response()
    payload = await calendar_feed.rotacionar_url_calendario(
        request=_request(),
        response=http_response,
        db=db,
        cu=_user(),
    )

    assert payload["version"] == 7
    assert payload["revogado"] is True
    assert db.commits == 1
    assert len(db.executed) == 1
    assert auditorias and auditorias[0][0][3] == "ROTATE_ICS"
    assert "version=7" in auditorias[0][1]["detalhes"]
    assert "no-store" in http_response.headers["Cache-Control"]
    assert http_response.headers["X-Content-Type-Options"] == "nosniff"


def test_headers_do_feed_impedem_cache():
    headers = calendar_feed._headers_ics()
    assert "no-store" in headers["Cache-Control"]
    assert headers["X-Content-Type-Options"] == "nosniff"


def test_rotacao_tem_rate_limit_por_usuario():
    source = inspect.getsource(calendar_feed)
    assert 'rate_limit("calendar-ics-rotate", 5)' in source

# Revalidação contra a base consolidada da main após os PRs #438 e #431.
