"""Contrato público do Data Room — manifesto + download token-bound."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from inspect import getsource
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request

from app.models.data_room import DataRoom, DataRoomAcessoLog, DataRoomArquivo, DataRoomLink
from app.models.document import DocConfidencialidade, Document
from app.routers import data_room
from app.services import data_room_public as public


class _Scalars:
    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return self._items


class _Result:
    def __init__(self, *, one=None, items=None):
        self._one = one
        self._items = items

    def scalar_one_or_none(self):
        return self._one

    def scalars(self):
        return _Scalars(self._items or [])


class _FakeDB:
    def __init__(self, results):
        self.results = list(results)
        self.added = []
        self.commits = 0

    async def execute(self, stmt, *args, **kwargs):
        del stmt, args, kwargs
        assert self.results, "execute inesperado no fake do Data Room público"
        return self.results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/data-rooms/acesso/token/manifesto",
            "headers": [(b"user-agent", b"pytest")],
            "client": ("127.0.0.1", 12345),
            "scheme": "https",
            "server": ("testserver", 443),
        }
    )


def _ids():
    return tuple(str(uuid4()) for _ in range(4))


def _fixture_publica(*, max_acessos=2, acessos=0, conf=DocConfidencialidade.normal):
    link_id, room_id, arquivo_id, doc_id = _ids()
    token = "token-publico-ficticio"
    link = DataRoomLink(
        id=link_id,
        data_room_id=room_id,
        token_hash=public._hash_token(token),
        ativo=True,
        acessos_realizados=acessos,
        max_acessos=max_acessos,
        expira_em=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    room = DataRoom(id=room_id, nome="Sala teste", descricao="Compartilhamento")
    arquivo = DataRoomArquivo(
        id=arquivo_id,
        data_room_id=room_id,
        document_id=doc_id,
        nome_exibicao="Documento público.pdf",
        publicado_externamente=True,
    )
    doc = Document(
        id=doc_id,
        titulo="Documento público",
        filename="documento.pdf",
        filepath="drive://geral/documento.pdf",
        mimetype="application/pdf",
        confidencialidade=conf,
        drive_file_id="drive-ficticio",
    )
    return token, link, room, arquivo, doc


def test_hash_token_permanece_compativel_com_link_legado():
    token = "segredo-ficticio"
    assert public._hash_token(token) == data_room._hash_token(token)


def test_grant_e_vinculado_a_link_arquivo_acesso_e_expiracao():
    agora = datetime.now(timezone.utc)
    exp = int((agora + timedelta(minutes=3)).timestamp())
    grant = public.gerar_grant("link-1", "arquivo-1", 2, exp)

    assert public.grant_valido(
        grant,
        link_id="link-1",
        arquivo_id="arquivo-1",
        acesso_numero=2,
        exp=exp,
        agora=agora,
    )
    assert not public.grant_valido(
        grant,
        link_id="link-1",
        arquivo_id="arquivo-trocado",
        acesso_numero=2,
        exp=exp,
        agora=agora,
    )
    assert not public.grant_valido(
        grant,
        link_id="link-1",
        arquivo_id="arquivo-1",
        acesso_numero=2,
        exp=exp,
        agora=agora + timedelta(minutes=4),
    )


async def test_manifesto_conta_uma_visita_e_retorna_id_opaco_sem_document_id():
    token, link, room, arquivo, doc = _fixture_publica(max_acessos=1)
    db = _FakeDB(
        [
            _Result(one=link),
            _Result(one=room),
            _Result(items=[arquivo]),
            _Result(items=[doc]),
        ]
    )

    payload = await public.abrir_manifesto(db, token, _request())

    assert payload["acesso_numero"] == 1
    assert link.acessos_realizados == 1
    assert db.commits == 1
    assert len(payload["arquivos"]) == 1
    item = payload["arquivos"][0]
    assert item["arquivo_id"] == arquivo.id
    assert "document_id" not in item
    assert f"/arquivos/{arquivo.id}?" in item["download_url"]
    assert any(isinstance(obj, DataRoomAcessoLog) for obj in db.added)


async def test_manifesto_max_acessos_um_nao_cria_segunda_sessao():
    token, link, *_ = _fixture_publica(max_acessos=1, acessos=1)
    db = _FakeDB([_Result(one=link)])

    with pytest.raises(HTTPException) as exc:
        await public.abrir_manifesto(db, token, _request())
    assert exc.value.status_code == 403
    assert db.commits == 0


async def test_manifesto_filtra_reclassificacao_para_interno():
    token, link, room, arquivo, doc = _fixture_publica(conf=DocConfidencialidade.interno)
    db = _FakeDB(
        [
            _Result(one=link),
            _Result(one=room),
            _Result(items=[arquivo]),
            _Result(items=[doc]),
        ]
    )

    payload = await public.abrir_manifesto(db, token, _request())
    assert payload["arquivos"] == []


async def test_download_drive_revalida_e_audita_depois_do_storage(monkeypatch):
    token, link, room, arquivo, doc = _fixture_publica(max_acessos=1, acessos=1)
    agora = datetime.now(timezone.utc)
    exp = int((agora + timedelta(minutes=3)).timestamp())
    grant = public.gerar_grant(link.id, arquivo.id, 1, exp)
    eventos = []

    def fake_download(*args, **kwargs):
        del args, kwargs
        eventos.append("storage")
        return b"pdf-ficticio"

    async def fake_audit(*args, **kwargs):
        del args, kwargs
        eventos.append("audit")

    monkeypatch.setattr(public.gd, "download_file", fake_download)
    monkeypatch.setattr(public, "criar_audit_log", fake_audit)
    db = _FakeDB(
        [
            _Result(one=link),
            _Result(one=room),
            _Result(one=arquivo),
            _Result(one=doc),
        ]
    )

    entrega = await public.preparar_download(
        db,
        token,
        arquivo.id,
        acesso_numero=1,
        exp=exp,
        grant=grant,
        request=_request(),
    )

    assert entrega.content == b"pdf-ficticio"
    assert eventos == ["storage", "audit"]
    assert db.commits == 1


async def test_download_storage_falha_nao_grava_auditoria(monkeypatch):
    token, link, room, arquivo, doc = _fixture_publica(max_acessos=1, acessos=1)
    exp = int((datetime.now(timezone.utc) + timedelta(minutes=3)).timestamp())
    grant = public.gerar_grant(link.id, arquivo.id, 1, exp)
    auditou = False

    def fake_download(*args, **kwargs):
        del args, kwargs
        raise public.gd.DriveObjetoNaoEncontradoError("ausente")

    async def fake_audit(*args, **kwargs):
        nonlocal auditou
        del args, kwargs
        auditou = True

    monkeypatch.setattr(public.gd, "download_file", fake_download)
    monkeypatch.setattr(public, "criar_audit_log", fake_audit)
    db = _FakeDB(
        [
            _Result(one=link),
            _Result(one=room),
            _Result(one=arquivo),
            _Result(one=doc),
        ]
    )

    with pytest.raises(HTTPException) as exc:
        await public.preparar_download(
            db,
            token,
            arquivo.id,
            acesso_numero=1,
            exp=exp,
            grant=grant,
            request=_request(),
        )
    assert exc.value.status_code == 410
    assert auditou is False
    assert db.commits == 0


def test_download_query_prende_arquivo_a_sala_e_revalida_publicacao():
    fonte = getsource(public.preparar_download)
    assert "DataRoomArquivo.id == arquivo_id" in fonte
    assert "DataRoomArquivo.data_room_id == room.id" in fonte
    assert "DataRoomArquivo.publicado_externamente.is_(True)" in fonte
    assert "Document.deleted_at.is_(None)" in fonte
    assert "_arquivo_publicavel(arquivo, doc)" in fonte


def test_headers_nao_permitem_crlf_ou_path_traversal():
    headers = public.headers_publicos('../../cliente\r\nX-Evil: 1.pdf')
    disposition = headers["Content-Disposition"]
    assert "\r" not in disposition
    assert "\n" not in disposition
    assert "../" not in disposition
    assert headers["Cache-Control"] == "private, no-store, max-age=0"
    assert headers["X-Content-Type-Options"] == "nosniff"
