"""Tarefa 2 — contrato do cursor de paginação (puro, sem banco).

Cobre os casos do plano:
  - roundtrip make/parse devolve a mesma last_key
  - tampering (payload e assinatura) é rejeitado
  - usuário/papel trocados invalidam o cursor
  - filtros distintos invalidam
  - ordem/endpoint distintos invalidam
  - expiração invalida
  - normalização determinística (booleanos, None, ordenação de chaves)
  - nulos dentro da last_key sobrevivem ao roundtrip
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.pagination_cursor import (
    CURSOR_TTL_PADRAO,
    make_cursor,
    normalize_filters,
    parse_cursor,
)

ENDPOINT = "/tasks"
ORDER = "data_limite:asc_nulls_last,created_at:asc,id:asc"


class _Viewer:
    def __init__(self, uid: str = "u-1", role: str = "advogado"):
        self.id = uid
        self.role = role


def _mk(viewer=None, filters=None, last_key=None, endpoint=ENDPOINT, order=ORDER):
    return make_cursor(
        endpoint=endpoint,
        viewer=viewer or _Viewer(),
        filters=filters if filters is not None else {"case_id": None, "minhas": False},
        order=order,
        last_key=last_key or ["2026-10-01", "2026-09-01T10:00:00", "abc"],
    )


# ── roundtrip ────────────────────────────────────────────────────────────────

def test_roundtrip_devolve_last_key():
    key = ["2026-10-01", "2026-09-01T10:00:00", "abc"]
    tok = _mk(last_key=key)
    out = parse_cursor(tok, ENDPOINT, _Viewer(), {"case_id": None, "minhas": False}, ORDER)
    assert out == key


def test_nulos_na_last_key_sobrevivem_roundtrip():
    key = [None, None, "zzz"]
    tok = _mk(last_key=key)
    out = parse_cursor(tok, ENDPOINT, _Viewer(), {"case_id": None, "minhas": False}, ORDER)
    assert out == key
    assert all(a == b for a, b in zip(out, key))


# ── tampering ────────────────────────────────────────────────────────────────

def test_payload_violado_rejeitado():
    tok = _mk()
    corpo, assinatura = tok.rsplit(".", 1)
    # muda a last_key sem reassinar
    import base64, json
    payload = json.loads(base64.urlsafe_b64decode(corpo + "=="))
    payload["k"] = ["1999-01-01", None, "hackeado"]
    novo_corpo = base64.urlsafe_b64encode(
        json.dumps(payload).encode()).decode().rstrip("=")
    with pytest.raises(HTTPException):
        parse_cursor(f"{novo_corpo}.{assinatura}", ENDPOINT, _Viewer(),
                     {"case_id": None, "minhas": False}, ORDER)


def test_assinatura_violada_rejeitada():
    tok = _mk()
    corpo, _ = tok.rsplit(".", 1)
    assinatura_falsa = "0" * 64
    with pytest.raises(HTTPException):
        parse_cursor(f"{corpo}.{assinatura_falsa}", ENDPOINT, _Viewer(),
                     {"case_id": None, "minhas": False}, ORDER)


def test_token_aleatorio_rejeitado():
    with pytest.raises(HTTPException):
        parse_cursor("nao-e-um-token", ENDPOINT, _Viewer(),
                     {"case_id": None, "minhas": False}, ORDER)


# ── usuário / papel / filtros / ordem / endpoint ─────────────────────────────

def test_usuario_trocado_invalida():
    tok = _mk(viewer=_Viewer(uid="u-1"))
    with pytest.raises(HTTPException):
        parse_cursor(tok, ENDPOINT, _Viewer(uid="u-2"),
                     {"case_id": None, "minhas": False}, ORDER)


def test_papel_trocado_invalida():
    tok = _mk(viewer=_Viewer(uid="u-1", role="advogado"))
    with pytest.raises(HTTPException):
        parse_cursor(tok, ENDPOINT, _Viewer(uid="u-1", role="socio"),
                     {"case_id": None, "minhas": False}, ORDER)


def test_filtros_distintos_invalida():
    tok = _mk(filters={"case_id": "caso-A", "minhas": False})
    with pytest.raises(HTTPException):
        parse_cursor(tok, ENDPOINT, _Viewer(),
                     {"case_id": "caso-B", "minhas": False}, ORDER)


def test_minhas_trocado_invalida():
    tok = _mk(filters={"case_id": None, "minhas": False})
    with pytest.raises(HTTPException):
        parse_cursor(tok, ENDPOINT, _Viewer(),
                     {"case_id": None, "minhas": True}, ORDER)


def test_ordem_distinta_invalida():
    tok = _mk(order=ORDER)
    with pytest.raises(HTTPException):
        parse_cursor(tok, ENDPOINT, _Viewer(),
                     {"case_id": None, "minhas": False},
                     "created_at:asc,id:asc")


def test_endpoint_distinto_invalida():
    tok = _mk()
    with pytest.raises(HTTPException):
        parse_cursor(tok, "/atividades", _Viewer(),
                     {"case_id": None, "minhas": False}, ORDER)


# ── expiração ────────────────────────────────────────────────────────────────

def test_expiracao_invalida(monkeypatch):
    tok = _mk()
    # simula relógio adiantado além do TTL
    from app.core import pagination_cursor as pc
    futuro = __import__("time").time() + CURSOR_TTL_PADRAO + 120
    class _FakeTime:
        @staticmethod
        def time():
            return futuro
    monkeypatch.setattr(pc.time, "time", _FakeTime.time)
    with pytest.raises(HTTPException):
        parse_cursor(tok, ENDPOINT, _Viewer(), {"case_id": None, "minhas": False}, ORDER)


# ── normalização determinística ──────────────────────────────────────────────

def test_normalizacao_ordem_de_chaves_e_deterministica():
    a = normalize_filters({"minhas": True, "case_id": None, "outro": "x"})
    b = normalize_filters({"outro": "x", "case_id": None, "minhas": True})
    assert a == b


def test_normalizacao_booleanos_e_none():
    n = normalize_filters({"a": True, "b": False, "c": None, "d": 3, "e": "s"})
    assert n["a"] is True and n["b"] is False and n["c"] is None
    assert n["d"] == 3 and n["e"] == "s"
    # serialização canônica estável
    import json
    canon = json.dumps(n, sort_keys=True, separators=(",", ":"))
    assert canon == '{"a":true,"b":false,"c":null,"d":3,"e":"s"}'


def test_normalizacao_strips_strings_e_none_vazio():
    # string vazia vira None (filtro ausente) — determinístico entre chamadas
    n = normalize_filters({"case_id": "", "minhas": False})
    assert n["case_id"] is None
