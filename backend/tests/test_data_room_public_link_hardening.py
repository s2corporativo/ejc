"""P0 — links públicos do Data Room sem segredo em repouso ou listagens."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.data_room import DataRoom, DataRoomArquivo, DataRoomLink
from app.models.document import DocConfidencialidade, Document


class _Result:
    def __init__(self, value=None):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _DB:
    def __init__(self, results=()):
        self.results = list(results)
        self.added = []
        self.committed = False

    async def execute(self, _stmt):
        return self.results.pop(0) if self.results else _Result()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


@pytest.fixture
def advogado():
    return SimpleNamespace(id="u-adv", role=SimpleNamespace(value="advogado"))


@pytest.fixture
def socio():
    return SimpleNamespace(id="u-socio", role=SimpleNamespace(value="socio"))


def _doc(conf: DocConfidencialidade) -> Document:
    return Document(
        id="doc-1",
        titulo="Documento",
        filename="doc.pdf",
        filepath="/tmp/doc.pdf",
        confidencialidade=conf,
    )


def test_hash_token_e_deterministico_e_nao_retem_segredo():
    from app.routers.data_room import _hash_token

    token = "segredo-publico-de-teste"
    digest = _hash_token(token)

    assert len(digest) == 64
    assert digest != token
    assert digest == _hash_token(token)
    assert digest != _hash_token(token + "x")


def test_listagem_de_link_nunca_devolve_token_ou_hash():
    from app.routers.data_room import _out_link

    link = DataRoomLink(
        id="lk-1",
        data_room_id="room-1",
        token_hash="a" * 64,
        ativo=True,
        acessos_realizados=0,
    )

    payload = _out_link(link)

    assert "token" not in payload
    assert "token_hash" not in payload
    assert payload["id"] == "lk-1"


def test_publicacao_externa_exige_politica_explicita(advogado, socio):
    from app.routers.data_room import _pode_publicar_externamente

    assert _pode_publicar_externamente(advogado, _doc(DocConfidencialidade.normal))
    assert not _pode_publicar_externamente(
        advogado, _doc(DocConfidencialidade.interno)
    )
    assert not _pode_publicar_externamente(
        advogado, _doc(DocConfidencialidade.restrito)
    )
    assert _pode_publicar_externamente(
        socio, _doc(DocConfidencialidade.restrito)
    )
    assert _pode_publicar_externamente(
        socio, _doc(DocConfidencialidade.confidencial)
    )
    assert not _pode_publicar_externamente(
        socio, _doc(DocConfidencialidade.segredo_justica)
    )


def test_reclassificacao_invalida_exposicao_publica():
    from app.routers.data_room import _arquivo_publicavel

    arquivo = DataRoomArquivo(
        id="a-1",
        data_room_id="room-1",
        document_id="doc-1",
        publicado_externamente=True,
    )

    assert _arquivo_publicavel(arquivo, _doc(DocConfidencialidade.normal))
    assert _arquivo_publicavel(arquivo, _doc(DocConfidencialidade.restrito))
    assert not _arquivo_publicavel(arquivo, _doc(DocConfidencialidade.interno))
    assert not _arquivo_publicavel(
        arquivo, _doc(DocConfidencialidade.segredo_justica)
    )

    arquivo.publicado_externamente = False
    assert not _arquivo_publicavel(arquivo, _doc(DocConfidencialidade.normal))


@pytest.mark.asyncio
async def test_criacao_de_link_persiste_hash_e_exibe_token_uma_unica_vez(
    monkeypatch, advogado
):
    from app.routers.data_room import GerarLinkReq, _hash_token, gerar_link

    room = DataRoom(id="room-1", nome="Sala", case_id=None, client_id=None)
    db = _DB([_Result(room)])

    async def _gate_ok(*_args, **_kwargs):
        return room

    monkeypatch.setattr("app.routers.data_room._gate_room", _gate_ok)
    # FIX-001: a sala do teste tem documento para permitir gerar link.
    async def _qtd_sala_com_documento(*_args, **_kwargs):
        return 1

    monkeypatch.setattr(
        "app.routers.data_room._qtd_documentos_da_sala",
        _qtd_sala_com_documento,
    )
    monkeypatch.setattr(
        "app.routers.data_room.secrets.token_urlsafe",
        lambda _n: "token-claro-criado",
    )

    payload = await gerar_link(
        "room-1",
        GerarLinkReq(expira_horas=24),
        db=db,
        cu=advogado,
    )

    link = next(obj for obj in db.added if isinstance(obj, DataRoomLink))
    assert link.token_hash == _hash_token("token-claro-criado")
    assert not hasattr(link, "token")
    assert payload["token"] == "token-claro-criado"
    assert payload["url_acesso"].endswith("/token-claro-criado")
    assert db.committed is True


@pytest.mark.asyncio
async def test_segredo_de_justica_nao_pode_ser_publicado(monkeypatch, socio):
    from app.routers.data_room import PublicarArquivoReq, publicar_arquivo

    room = DataRoom(id="room-1", nome="Sala", case_id=None, client_id=None)
    arquivo = DataRoomArquivo(
        id="a-1",
        data_room_id="room-1",
        document_id="doc-1",
        publicado_externamente=False,
    )
    documento = _doc(DocConfidencialidade.segredo_justica)
    db = _DB([_Result(room), _Result(arquivo), _Result(documento)])

    async def _gate_ok(*_args, **_kwargs):
        return room

    monkeypatch.setattr("app.routers.data_room._gate_room", _gate_ok)

    with pytest.raises(HTTPException) as exc:
        await publicar_arquivo(
            "room-1",
            "a-1",
            PublicarArquivoReq(publicado=True),
            db=db,
            cu=socio,
        )

    assert exc.value.status_code == 403
    assert arquivo.publicado_externamente is False
    assert db.committed is False
