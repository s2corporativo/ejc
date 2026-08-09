"""Hardening operacional sem migration — dados integralmente fictícios."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import produtividade, trash


class _FakeScalarDB:
    def __init__(self, resultado):
        self.resultado = resultado

    async def scalar(self, _query):
        return self.resultado


@pytest.mark.asyncio
async def test_lixeira_bloqueia_restauração_quando_pai_nao_existe():
    db = _FakeScalarDB(None)
    registro = SimpleNamespace(case_id="caso-ficticio", client_id=None)

    with pytest.raises(HTTPException) as exc:
        await trash._validar_dependencias_restauração(db, "documents", registro)

    assert exc.value.status_code == 409
    assert "não existe" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_lixeira_bloqueia_restauração_quando_pai_esta_na_lixeira():
    db = _FakeScalarDB(SimpleNamespace(deleted_at="2026-08-09T00:00:00Z"))
    registro = SimpleNamespace(case_id="caso-ficticio", client_id=None)

    with pytest.raises(HTTPException) as exc:
        await trash._validar_dependencias_restauração(db, "documents", registro)

    assert exc.value.status_code == 409
    assert "restaure a dependência primeiro" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_lixeira_permite_filhos_quando_pai_esta_ativo():
    db = _FakeScalarDB(SimpleNamespace(deleted_at=None))
    registro = SimpleNamespace(case_id="caso-ficticio", client_id=None)

    await trash._validar_dependencias_restauração(db, "documents", registro)


class _FakeCommitDB:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_exportacao_produtividade_registra_auditoria_sem_conteudo_do_relatorio(
    monkeypatch,
):
    chamadas: list[dict] = []

    async def fake_audit(
        db,
        user_id,
        papel,
        acao,
        entidade,
        entidade_id,
        **kwargs,
    ):
        chamadas.append(
            {
                "user_id": user_id,
                "papel": papel,
                "acao": acao,
                "entidade": entidade,
                "entidade_id": entidade_id,
                **kwargs,
            }
        )

    monkeypatch.setattr(produtividade, "criar_audit_log", fake_audit)
    db = _FakeCommitDB()
    user = SimpleNamespace(id="usuario-ficticio", role=SimpleNamespace(value="admin"))
    body = produtividade.ProdutividadeExportEvent(
        periodo="30d", formato="csv", linhas=12
    )

    resultado = await produtividade.registrar_exportacao_produtividade(
        body=body, db=db, cu=user
    )

    assert resultado == {"ok": True}
    assert db.commits == 1
    assert len(chamadas) == 1
    evento = chamadas[0]
    assert evento["acao"] == "EXPORT"
    assert evento["entidade"] == "produtividade"
    assert evento["dados_depois"] == {
        "periodo": "30d",
        "formato": "csv",
        "linhas": 12,
    }
    serializado = repr(evento).lower()
    assert "nome" not in serializado
    assert "email" not in serializado
    assert "cpf" not in serializado


@pytest.mark.asyncio
async def test_exportacao_produtividade_rejeita_quantidade_de_linhas_invalida():
    db = _FakeCommitDB()
    user = SimpleNamespace(id="usuario-ficticio", role=SimpleNamespace(value="admin"))
    body = produtividade.ProdutividadeExportEvent(
        periodo="30d", formato="csv", linhas=100_001
    )

    with pytest.raises(HTTPException) as exc:
        await produtividade.registrar_exportacao_produtividade(
            body=body, db=db, cu=user
        )

    assert exc.value.status_code == 422
    assert db.commits == 0
