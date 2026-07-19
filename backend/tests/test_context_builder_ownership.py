"""Auditoria RAG — guard de IDOR cross-tenant em context_builder.

Antes: `document_id`/`process_id` chegavam por IDs independentes do corpo e eram
buscados só por id, sem provar vínculo ao caso/cliente/usuário — qualquer usuário
interno podia injetar documento/processo de OUTRO cliente no prompt da IA.

Estes testes (puros, com os gates de acesso mockados) travam o comportamento
fail-closed dos helpers de autorização.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.core.ownership as ownership
from app.services.ai.core import context_builder as cb


@pytest.fixture
def _mock_acesso(monkeypatch):
    """Controla verificar_acesso_caso/is_gestao no namespace de ownership
    (importados de forma lazy dentro dos helpers)."""
    estado = {"casos_permitidos": set(), "gestao": False}

    async def fake_verificar(db, user, case_id):
        if case_id in estado["casos_permitidos"]:
            return SimpleNamespace(id=case_id)
        raise HTTPException(status_code=403, detail="sem acesso")

    def fake_is_gestao(user):
        return estado["gestao"]

    monkeypatch.setattr(ownership, "verificar_acesso_caso", fake_verificar)
    monkeypatch.setattr(ownership, "is_gestao", fake_is_gestao)
    return estado


_USER = SimpleNamespace(id="user-1", role=SimpleNamespace(value="advogado"))


async def test_documento_de_outro_caso_e_bloqueado(_mock_acesso):
    _mock_acesso["casos_permitidos"] = {"caso-A"}
    doc = SimpleNamespace(case_id="caso-B", uploaded_by="outro")
    # contexto é do caso-A, mas o doc é do caso-B → bloqueado
    assert await cb._documento_autorizado(None, _USER, doc, "caso-A") is False


async def test_documento_do_mesmo_caso_com_acesso_e_liberado(_mock_acesso):
    _mock_acesso["casos_permitidos"] = {"caso-A"}
    doc = SimpleNamespace(case_id="caso-A", uploaded_by="outro")
    assert await cb._documento_autorizado(None, _USER, doc, "caso-A") is True


async def test_documento_do_caso_sem_acesso_do_usuario_e_bloqueado(_mock_acesso):
    _mock_acesso["casos_permitidos"] = set()  # usuário não tem acesso a nenhum caso
    doc = SimpleNamespace(case_id="caso-A", uploaded_by="outro")
    assert await cb._documento_autorizado(None, _USER, doc, "caso-A") is False


async def test_documento_sem_usuario_e_bloqueado(_mock_acesso):
    doc = SimpleNamespace(case_id="caso-A", uploaded_by="outro")
    assert await cb._documento_autorizado(None, None, doc, "caso-A") is False


async def test_documento_sem_caso_liberado_para_uploader(_mock_acesso):
    _mock_acesso["gestao"] = False
    doc = SimpleNamespace(case_id=None, uploaded_by="user-1")
    assert await cb._documento_autorizado(None, _USER, doc, None) is True


async def test_documento_sem_caso_de_terceiro_bloqueado_para_nao_gestao(_mock_acesso):
    _mock_acesso["gestao"] = False
    doc = SimpleNamespace(case_id=None, uploaded_by="outro")
    assert await cb._documento_autorizado(None, _USER, doc, None) is False


async def test_documento_sem_caso_liberado_para_gestao(_mock_acesso):
    _mock_acesso["gestao"] = True
    doc = SimpleNamespace(case_id=None, uploaded_by="outro")
    assert await cb._documento_autorizado(None, _USER, doc, None) is True


async def test_processo_de_outro_caso_e_bloqueado(_mock_acesso):
    _mock_acesso["casos_permitidos"] = {"caso-A"}
    proc = SimpleNamespace(case_id="caso-B")
    assert await cb._processo_autorizado(None, _USER, proc, "caso-A") is False


async def test_processo_do_mesmo_caso_com_acesso_e_liberado(_mock_acesso):
    _mock_acesso["casos_permitidos"] = {"caso-A"}
    proc = SimpleNamespace(case_id="caso-A")
    assert await cb._processo_autorizado(None, _USER, proc, "caso-A") is True


async def test_processo_sem_usuario_e_bloqueado(_mock_acesso):
    proc = SimpleNamespace(case_id="caso-A")
    assert await cb._processo_autorizado(None, None, proc, "caso-A") is False
