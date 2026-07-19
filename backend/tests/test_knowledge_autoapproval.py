"""Política: todo KnowledgeDoc do módulo nasce aprovado para o RAG."""
from sqlalchemy import event

from app.models.rag import KnowledgeDoc
from app.services.knowledge_autoapproval import (
    POLITICA,
    _aprovar_no_flush,
    aplicar_aprovacao_automatica,
)


def _doc(extra=None) -> KnowledgeDoc:
    return KnowledgeDoc(
        id="doc-teste",
        titulo="Documento excepcional",
        categoria="legislacao",
        extra=extra,
    )


def test_documento_pendente_vira_aprovado():
    doc = _doc({"rag_status": "pendente", "confidence_level": "alta"})
    extra = aplicar_aprovacao_automatica(doc)

    assert extra["rag_status"] == "aprovado"
    assert extra["confidence_level"] == "alta"
    assert extra["auto_approval"]["policy"] == POLITICA
    assert extra["auto_approval"]["previous_rag_status"] == "pendente"


def test_bloqueio_legado_nao_impede_uso_pela_ia():
    doc = _doc({"rag_status": "bloqueado", "confidence_level": "bloqueado"})
    extra = aplicar_aprovacao_automatica(doc)

    assert extra["rag_status"] == "aprovado"
    assert extra["confidence_level"] == "media"
    assert extra["auto_approval"]["previous_confidence_level"] == "bloqueado"


def test_metadados_de_fonte_nao_sao_falsificados():
    doc = _doc({
        "fonte_validada": False,
        "fonte_url": "https://exemplo.invalid/documento",
        "requires_human_review": True,
    })
    extra = aplicar_aprovacao_automatica(doc)

    assert extra["fonte_validada"] is False
    assert extra["requires_human_review"] is True
    assert extra["rag_status"] == "aprovado"


def test_listener_orm_esta_registrado():
    assert event.contains(KnowledgeDoc, "before_insert", _aprovar_no_flush)
    assert event.contains(KnowledgeDoc, "before_update", _aprovar_no_flush)
