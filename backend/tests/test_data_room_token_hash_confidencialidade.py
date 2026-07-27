"""Regressão dos achados DOC-097 / DOC-098 / DOC-101 do Data Room.

- DOC-097: documento de um caso não pode entrar em sala de outro caso/cliente.
- DOC-098: token de link é autenticado por hash; não é reexibido em listagens,
  só na criação; o acesso público continua válido buscando por sha256(token).
- DOC-101: documento elevado a restrito/confidencial some do link público.

Segue o padrão local (fake DB + SimpleNamespace), sem banco real.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routers.data_room import (
    _hash_token,
    _out_link,
    acessar_link_publico,
    adicionar_arquivo,
    gerar_link,
    AdicionarArquivoReq,
    GerarLinkReq,
)


class _Res:
    def __init__(self, *, scalar_one=None, all=None):
        self._scalar_one = scalar_one
        self._all = [] if all is None else all

    def scalar_one_or_none(self):
        return self._scalar_one

    def scalars(self):
        return self

    def all(self):
        return self._all


class _DB:
    def __init__(self, results=()):
        self.results = list(results)
        self.executed = []
        self.added = []
        self.committed = False

    async def execute(self, stmt, *args, **kwargs):
        self.executed.append(stmt)
        if self.results:
            return self.results.pop(0)
        return _Res()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def flush(self):
        pass


def _user(role: str, uid: str = "u1"):
    return SimpleNamespace(id=uid, role=SimpleNamespace(value=role))


def _sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": False}))


def _doc(*, doc_id="d1", case_id=None, client_id=None, conf="normal"):
    return SimpleNamespace(
        id=doc_id,
        case_id=case_id,
        client_id=client_id,
        confidencialidade=SimpleNamespace(value=conf),
    )


def _room(*, case_id=None, client_id=None):
    return SimpleNamespace(
        id="r1", case_id=case_id, client_id=client_id, deleted_at=None
    )


# ── DOC-097 ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_doc097_doc_de_caso_a_rejeitado_em_sala_de_caso_b(monkeypatch):
    async def _acesso_ok(*a, **k):
        return None

    monkeypatch.setattr(
        "app.routers.data_room.verificar_acesso_caso", _acesso_ok
    )

    room = _room(case_id="B")
    doc = _doc(case_id="A")
    db = _DB(
        [
            _Res(scalar_one=room),          # room select
            _Res(scalar_one=doc),           # doc select
            _Res(scalar_one="clB"),         # _client_do_caso(room.case_id=B)
            _Res(scalar_one="clA"),         # _client_do_caso(doc.case_id=A)
        ]
    )
    with pytest.raises(Exception) as exc:
        await adicionar_arquivo(
            "r1",
            AdicionarArquivoReq(document_id="d1"),
            db,
            _user("socio"),
        )
    assert getattr(exc.value, "status_code", None) == 403


@pytest.mark.asyncio
async def test_doc097_doc_do_mesmo_caso_e_aceito(monkeypatch):
    async def _acesso_ok(*a, **k):
        return None

    monkeypatch.setattr(
        "app.routers.data_room.verificar_acesso_caso", _acesso_ok
    )

    room = _room(case_id="A")
    doc = _doc(case_id="A")
    db = _DB(
        [
            _Res(scalar_one=room),          # room
            _Res(scalar_one=doc),           # doc
            _Res(scalar_one="clA"),         # cliente da sala (via caso A)
            _Res(scalar_one="clA"),         # cliente do doc (via caso A)
        ]
    )
    out = await adicionar_arquivo(
        "r1",
        AdicionarArquivoReq(document_id="d1"),
        db,
        _user("socio"),
    )
    assert out["document_id"] == "d1"
    assert db.committed is True


# ── DOC-098 ────────────────────────────────────────────────────────────────
def test_doc098_out_link_nao_expoe_token():
    lk = SimpleNamespace(
        id="lk1",
        token="segredo",
        descricao="perito",
        expira_em=None,
        max_acessos=None,
        acessos_realizados=0,
        ativo=True,
        created_at=None,
    )
    out = _out_link(lk)
    assert "token" not in out
    assert out["id"] == "lk1"


@pytest.mark.asyncio
async def test_doc098_gerar_link_armazena_hash_e_retorna_token_uma_vez():
    room = _room()
    db = _DB([_Res(scalar_one=room)])
    out = await gerar_link(
        "r1",
        GerarLinkReq(expira_horas=72),
        db,
        _user("socio"),
    )
    assert "token" in out and out["token"]
    assert out["url_acesso"].endswith(out["token"])
    lk = db.added[0]
    # Em repouso existe SÓ o hash: dump/backup do banco não entrega o link.
    assert lk.token is None
    assert lk.token_hash == _hash_token(out["token"])
    assert lk.token_hash != out["token"]


@pytest.mark.asyncio
async def test_doc098_acesso_publico_busca_por_hash(monkeypatch):
    monkeypatch.setattr(
        "app.routers.data_room.obter_ip_real", lambda r: "1.2.3.4"
    )
    token = "tok-forte-xyz"
    lk = SimpleNamespace(
        id="lk1",
        token_hash=_hash_token(token),
        ativo=True,
        expira_em=datetime.now(timezone.utc) + timedelta(hours=1),
        max_acessos=None,
        acessos_realizados=0,
        data_room_id="r1",
    )
    db = _DB(
        [
            _Res(scalar_one=lk),        # link por token_hash
            _Res(scalar_one=_room()),   # room
            _Res(all=[]),               # arquivos (vazio)
        ]
    )
    request = SimpleNamespace(headers={})
    out = await acessar_link_publico(token, request, db)
    assert out["data_room_id"] == "r1"
    # o lookup usa token_hash, não o token em claro
    assert "token_hash" in _sql(db.executed[0])


# ── DOC-101 ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_doc101_doc_elevado_a_restrito_some_do_link_publico(monkeypatch):
    monkeypatch.setattr(
        "app.routers.data_room.obter_ip_real", lambda r: "1.2.3.4"
    )
    token = "tok-forte-abc"
    lk = SimpleNamespace(
        id="lk1",
        token_hash=_hash_token(token),
        ativo=True,
        expira_em=datetime.now(timezone.utc) + timedelta(hours=1),
        max_acessos=None,
        acessos_realizados=0,
        data_room_id="r1",
    )
    arq_ok = SimpleNamespace(document_id="d1", nome_exibicao="Contrato")
    arq_restrito = SimpleNamespace(document_id="d2", nome_exibicao="Sigiloso")
    db = _DB(
        [
            _Res(scalar_one=lk),                    # link
            _Res(scalar_one=_room()),               # room
            _Res(all=[arq_ok, arq_restrito]),       # arquivos da sala
            _Res(                                    # confidencialidade atual
                all=[
                    ("d1", SimpleNamespace(value="normal")),
                    ("d2", SimpleNamespace(value="restrito")),
                ]
            ),
        ]
    )
    request = SimpleNamespace(headers={})
    out = await acessar_link_publico(token, request, db)
    ids = {a["document_id"] for a in out["arquivos"]}
    assert ids == {"d1"}
    assert "d2" not in ids
