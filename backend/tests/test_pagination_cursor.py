"""Testes unitários do cursor de paginação keyset assinado (Tarefa 2).

Sem banco: exercita HMAC, canonização de filtros e invalidação
determinística. A prova de comportamento com dados reais (walk página a
página == conjunto completo, RBAC por carteira) vive em
``test_tasks_pagination_dblevel.py`` (requer RUN_DB_TESTS=1).
"""
from __future__ import annotations

import pytest

from app.core.pagination_cursor import (
    CursorInvalido,
    canon_filters,
    make_cursor,
    parse_cursor,
)


class _Viewer:
    def __init__(self, uid: str) -> None:
        self.id = uid


V_A = _Viewer("11111111-1111-1111-1111-111111111111")
V_B = _Viewer("22222222-2222-2222-2222-222222222222")

EP = "tasks"
ORDER = "data_limite.asc.nullslast|created_at.asc|id.asc"


# ── Canonização de filtros ───────────────────────────────────────────────────
def test_canon_bool_none_e_ordem_de_chaves():
    assert canon_filters({"b": True, "a": None, "c": "x"}) == '{"b":"1","c":"x"}'
    assert canon_filters({"c": "x", "b": False}) == '{"b":"0","c":"x"}'


def test_canon_status_vazio_e_ausente():
    # convenção /deadlines/: status="" significa TODOS — não pode diferir
    # de não enviar status.
    assert canon_filters({"status": "", "minhas": True}) == canon_filters(
        {"minhas": True}
    )


def test_canon_none_e_ausente():
    assert canon_filters({"case_id": None}) == canon_filters({})


def test_canon_estavel_entre_chamadas():
    f = {"case_id": "abc", "minhas": False, "outro": "文本"}
    assert canon_filters(f) == canon_filters(dict(reversed(list(f.items()))))


# ── Roundtrip ────────────────────────────────────────────────────────────────
def test_roundtrip_devolve_last_key():
    tok = make_cursor(EP, V_A, {"minhas": True}, ORDER,
                      [None, "2026-10-01T10:00:00", "abc-id"])
    assert parse_cursor(tok, EP, V_A, {"minhas": True}, ORDER) == [
        None, "2026-10-01T10:00:00", "abc-id",
    ]


def test_roundtrip_sem_filtros():
    tok = make_cursor(EP, V_A, None, ORDER, ["x"])
    assert parse_cursor(tok, EP, V_A, None, ORDER) == ["x"]


# ── Invalidação determinística ──────────────────────────────────────────────
def test_outro_usuario_invalida():
    tok = make_cursor(EP, V_A, None, ORDER, ["k"])
    with pytest.raises(CursorInvalido):
        parse_cursor(tok, EP, V_B, None, ORDER)


def test_filtro_diferente_invalida():
    tok = make_cursor(EP, V_A, {"minhas": True}, ORDER, ["k"])
    with pytest.raises(CursorInvalido):
        parse_cursor(tok, EP, V_A, {"minhas": False}, ORDER)


def test_filtro_equivalente_valido():
    # mesmos filtros, formas diferentes de enviar (ordem/None/bool)
    tok = make_cursor(EP, V_A, {"minhas": True, "case_id": None}, ORDER, ["k"])
    assert parse_cursor(tok, EP, V_A, {"case_id": None, "minhas": True},
                        ORDER) == ["k"]


def test_ordenacao_diferente_invalida():
    tok = make_cursor(EP, V_A, None, ORDER, ["k"])
    with pytest.raises(CursorInvalido):
        parse_cursor(tok, EP, V_A, None, "created_at.asc|id.asc")


def test_endpoint_diferente_invalida():
    tok = make_cursor(EP, V_A, None, ORDER, ["k"])
    with pytest.raises(CursorInvalido):
        parse_cursor(tok, "cases", V_A, None, ORDER)


# ── Tampering / malformed ───────────────────────────────────────────────────
def test_tampering_no_body():
    tok = make_cursor(EP, V_A, None, ORDER, ["k"])
    body, sig = tok.rsplit(".", 1)
    body_mod = body[:-2] + ("AA" if not body.endswith("AA") else "BB")
    with pytest.raises(CursorInvalido):
        parse_cursor(body_mod + "." + sig, EP, V_A, None, ORDER)


def test_tampering_last_key_sem_reassinar():
    # forjar um payload com k maior (skipping) exige nova assinatura — sem a
    # chave, qualquer mutação cai no HMAC.
    tok = make_cursor(EP, V_A, None, ORDER, ["k1"])
    body, sig = tok.rsplit(".", 1)
    import base64, json

    pad = "=" * (-len(body) % 4)
    payload = json.loads(base64.urlsafe_b64decode(body + pad))
    payload["k"] = ["pulado-ate-o-fim"]
    novo_body = base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    with pytest.raises(CursorInvalido):
        parse_cursor(novo_body + "." + sig, EP, V_A, None, ORDER)


@pytest.mark.parametrize("token", ["", ".", "sem-separador", "a.b", "...."])
def test_malformados_nao_explodem(token):
    with pytest.raises(CursorInvalido):
        parse_cursor(token, EP, V_A, None, ORDER)


def test_base64_invalido():
    with pytest.raises(CursorInvalido):
        parse_cursor("%%%.$$$", EP, V_A, None, ORDER)


# ── Chave ────────────────────────────────────────────────────────────────────
def test_rotacao_de_chave_invalida_cursor(monkeypatch):
    tok = make_cursor(EP, V_A, None, ORDER, ["k"])
    from app.core import pagination_cursor as pc

    monkeypatch.setattr(pc.settings, "PAGINATION_CURSOR_SECRET", "chave-nova-rotacionada")
    with pytest.raises(CursorInvalido):
        parse_cursor(tok, EP, V_A, None, ORDER)
    monkeypatch.setattr(pc.settings, "PAGINATION_CURSOR_SECRET", "")
    assert parse_cursor(tok, EP, V_A, None, ORDER) == ["k"]


def test_fallback_dev_sem_segredos(monkeypatch):
    from app.core import pagination_cursor as pc

    monkeypatch.setattr(pc.settings, "PAGINATION_CURSOR_SECRET", "")
    monkeypatch.setattr(pc.settings, "SECRET_KEY", "")
    tok = make_cursor(EP, V_A, None, ORDER, ["k"])
    assert parse_cursor(tok, EP, V_A, None, ORDER) == ["k"]
