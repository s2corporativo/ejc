from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import select

from app.models.document import DocConfidencialidade, Document
from app.services.case_timeline_visibility_service import (
    _apply_document_visibility,
    _requires_document_filter,
    _targets_documents,
)


def _user(role: str):
    return SimpleNamespace(role=SimpleNamespace(value=role))


def test_document_query_receives_confidentiality_predicate_before_execution():
    statement = select(Document).order_by(Document.created_at.desc()).limit(25)
    protected = _apply_document_visibility(statement)
    compiled = str(protected.compile(compile_kwargs={"literal_binds": True}))

    assert _targets_documents(statement) is True
    assert "documents.confidencialidade NOT IN" in compiled
    assert DocConfidencialidade.restrito.value in compiled
    assert DocConfidencialidade.confidencial.value in compiled
    assert DocConfidencialidade.segredo_justica.value in compiled
    assert compiled.index("documents.confidencialidade NOT IN") < compiled.index("ORDER BY")
    assert compiled.index("documents.confidencialidade NOT IN") < compiled.index("LIMIT")


def test_non_document_query_is_not_mutated():
    statement = select(Document.id).where(Document.id == "doc-1")
    # Continua sendo uma consulta à tabela documents e, portanto, deve ser filtrada.
    protected = _apply_document_visibility(statement)
    assert protected is not statement

    unrelated = select(1)
    assert _targets_documents(unrelated) is False
    assert _apply_document_visibility(unrelated) is unrelated


def test_roles_below_partner_are_filtered_and_partner_plus_are_not():
    assert _requires_document_filter(_user("advogado")) is True
    assert _requires_document_filter(_user("advogado_auxiliar")) is True
    assert _requires_document_filter(_user("estagiario")) is True
    assert _requires_document_filter(_user("socio")) is False
    assert _requires_document_filter(_user("admin")) is False
    assert _requires_document_filter(_user("superadmin")) is False
