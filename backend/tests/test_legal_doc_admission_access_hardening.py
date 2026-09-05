"""Regressões do gate unificado de LegalDoc de admissão (#1460)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException


class _Result:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _DB:
    def __init__(self, row):
        self.row = row
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(self.row)


def _request(doc_id: str = "doc-admissao"):
    return SimpleNamespace(path_params={"doc_id": doc_id})


@pytest.mark.asyncio
async def test_secretaria_nao_le_documento_de_admissao(monkeypatch):
    from app.services import legal_doc_access_hardening as hardening

    async def _visivel(_db, _cu, _client_id):
        return True

    monkeypatch.setattr(hardening, "cliente_id_visivel", _visivel)
    db = _DB(("client-1", "procuracao"))
    cu = SimpleNamespace(id="sec-1", role="secretaria")

    with pytest.raises(HTTPException) as exc:
        await hardening._gate_admissao_advogado(_request(), db=db, cu=cu)

    assert exc.value.status_code == 403
    assert "equipe jurídica" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_advogado_le_documento_de_admissao(monkeypatch):
    from app.services import legal_doc_access_hardening as hardening

    async def _visivel(_db, _cu, _client_id):
        return True

    monkeypatch.setattr(hardening, "cliente_id_visivel", _visivel)
    db = _DB(("client-1", "contrato_honorarios"))
    cu = SimpleNamespace(id="adv-1", role="advogado")

    await hardening._gate_admissao_advogado(_request(), db=db, cu=cu)
    assert db.statements


@pytest.mark.asyncio
async def test_documento_crm_nao_admissao_preserva_regra_de_ownership(monkeypatch):
    """A correção não transforma toda visão de CRM em conteúdo advogado-only."""
    from app.services import legal_doc_access_hardening as hardening

    async def _visivel(_db, _cu, _client_id):
        return True

    monkeypatch.setattr(hardening, "cliente_id_visivel", _visivel)
    db = _DB(("client-1", None))
    cu = SimpleNamespace(id="sec-1", role="secretaria")

    await hardening._gate_admissao_advogado(_request(), db=db, cu=cu)


@pytest.mark.asyncio
async def test_ownership_404_prevalece_antes_do_gate_de_papel(monkeypatch):
    from app.services import legal_doc_access_hardening as hardening

    async def _invisivel(_db, _cu, _client_id):
        return False

    monkeypatch.setattr(hardening, "cliente_id_visivel", _invisivel)
    db = _DB(("client-outro", "procuracao"))
    cu = SimpleNamespace(id="adv-1", role="advogado")

    with pytest.raises(HTTPException) as exc:
        await hardening._gate_admissao_advogado(_request(), db=db, cu=cu)

    assert exc.value.status_code == 404


def _calls_do_dependant(dependant):
    calls = []
    if dependant is None:
        return calls
    for dep in getattr(dependant, "dependencies", ()) or ():
        calls.append(getattr(dep, "call", None))
        calls.extend(_calls_do_dependant(dep))
    return calls


def test_startup_substitui_gate_antigo_em_todas_as_rotas_legal_docs():
    from app.main import app  # noqa: F401
    from app.routers import legal_docs

    gate = legal_docs._enforce_client_legal_doc_scope
    assert getattr(legal_docs.router, "_ejc_admission_access_installed", False) is True
    assert getattr(gate, "__wrapped__", None) is not None

    original = gate.__wrapped__
    chamadas = []
    for route in legal_docs.router.routes:
        chamadas.extend(_calls_do_dependant(getattr(route, "dependant", None)))

    assert gate in chamadas
    assert original not in chamadas
