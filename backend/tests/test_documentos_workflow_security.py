"""Travas de segurança do workflow simplificado de Documentos/GED."""
from __future__ import annotations

import inspect
from types import SimpleNamespace

from app.models.document import DocConfidencialidade, Document
from app.services import document_ux_service


def _user(role: str, *, user_id="u1", client_id=None):
    return SimpleNamespace(
        id=user_id,
        role=SimpleNamespace(value=role),
        client_id=client_id,
    )


def _doc(**overrides):
    data = dict(
        id="d1",
        titulo="Doc",
        filename="doc.pdf",
        filepath="x/d1.pdf",
        confidencialidade=DocConfidencialidade.normal,
        case_id="c1",
        client_id="cli1",
        uploaded_by="u1",
    )
    data.update(overrides)
    return Document(**data)


def test_cofre_requer_socio_ou_superior():
    assert document_ux_service.pode_acessar_confidencial(_user("advogado"), "normal") is True
    assert document_ux_service.pode_acessar_confidencial(_user("advogado"), "confidencial") is False
    assert document_ux_service.pode_acessar_confidencial(_user("socio"), "confidencial") is True


def test_visibilidade_cliente_externo_filtra_cliente_e_normal():
    from sqlalchemy import select

    query = document_ux_service.aplicar_visibilidade_documentos(
        select(Document),
        _user("cliente_externo", client_id="cli1"),
    )
    sql = str(query).lower()
    assert "documents.client_id" in sql
    assert "documents.confidencialidade" in sql


def test_dedupe_e_limitado_ao_contexto_autorizado():
    fonte = inspect.getsource(document_ux_service.buscar_duplicado_exato_contexto)
    assert "Document.sha256 == sha256" in fonte
    assert "Document.case_id == case_id" in fonte
    assert "Document.client_id == client_id" in fonte
    assert "Document.uploaded_by == uploaded_by" in fonte
    assert "Document.deleted_at.is_(None)" in fonte


def test_inbox_aplica_visibilidade_antes_do_filtro_operacional():
    fonte = inspect.getsource(document_ux_service.aplicar_visibilidade_documentos)
    assert "ROLE_LEVEL" in fonte
    assert 'user.role.value == "cliente_externo"' in fonte
    assert "Case.advogado_responsavel_id == user.id" in fonte
    assert "Case.advogado_auxiliar_id == user.id" in fonte
