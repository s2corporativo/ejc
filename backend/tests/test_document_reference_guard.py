"""Testes da guarda canônica de referências do GED.

A prova DB-level das relações principais já existe nos fluxos de vínculo; aqui
travamos a política agregadora, o único round-trip e a minimização do erro.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services.document_reference_guard import (
    EscopoGuardaDocumento,
    exigir_documento_sem_referencias_bloqueantes,
    referencias_ativas_documento,
)


class _Mappings:
    def __init__(self, payload: dict[str, bool]):
        self._payload = payload

    def one(self) -> dict[str, bool]:
        return self._payload


class _Result:
    def __init__(self, payload: dict[str, bool]):
        self._payload = payload

    def mappings(self) -> _Mappings:
        return _Mappings(self._payload)


class _DB:
    def __init__(self, payload: dict[str, bool]):
        self.payload = payload
        self.calls = 0
        self.statement = None

    async def execute(self, statement):
        self.calls += 1
        self.statement = statement
        return _Result(self.payload)


_TODOS = {
    "protocolo": True,
    "prova": True,
    "assinatura": True,
    "centro_custo": True,
    "fee_payment": True,
    "deadline": True,
    "solicitacao_cliente": True,
    "contrato": True,
    "processo_eletronico": True,
    "data_room": True,
    "intake": True,
    "versao_posterior": True,
}


@pytest.mark.asyncio
async def test_exclusao_agrega_grafo_em_um_unico_roundtrip():
    db = _DB(dict(_TODOS))

    refs = await referencias_ativas_documento(db, "doc-1")

    assert db.calls == 1
    assert [ref.codigo for ref in refs] == list(_TODOS)

    sql = str(db.statement)
    for tabela in (
        "legal_docs",
        "provas",
        "signature_requests",
        "centro_custos",
        "fee_payments",
        "deadlines",
        "solicitacao_documento_itens",
        "contratos_societarios",
        "documentos_processo_eletronico_dedup",
        "data_room_arquivos",
        "document_intake_items",
        "documents",
    ):
        assert tabela in sql


@pytest.mark.asyncio
async def test_vinculo_preserva_contrato_f3_2_sem_ampliar_bloqueios():
    db = _DB(dict(_TODOS))

    refs = await referencias_ativas_documento(
        db,
        "doc-1",
        escopo=EscopoGuardaDocumento.VINCULO,
    )

    assert db.calls == 1
    assert [ref.codigo for ref in refs] == ["protocolo", "prova"]


@pytest.mark.asyncio
async def test_sem_referencia_nao_bloqueia():
    db = _DB({chave: False for chave in _TODOS})

    await exigir_documento_sem_referencias_bloqueantes(
        db,
        "doc-1",
        acao="excluído",
    )

    assert db.calls == 1


@pytest.mark.asyncio
async def test_conflito_e_minimizado_e_nao_expõe_metadados_de_registro():
    payload = {chave: False for chave in _TODOS}
    payload["protocolo"] = True
    payload["centro_custo"] = True
    db = _DB(payload)

    with pytest.raises(HTTPException) as exc:
        await exigir_documento_sem_referencias_bloqueantes(
            db,
            "doc-segredo@cliente.example",
            acao="excluído",
        )

    assert exc.value.status_code == 409
    detalhe = str(exc.value.detail)
    assert "comprovante de protocolo" in detalhe
    assert "lançamento de centro de custos" in detalhe
    assert "doc-segredo" not in detalhe
    assert "cliente.example" not in detalhe
