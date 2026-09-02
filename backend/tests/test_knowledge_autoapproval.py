"""Política central de disponibilidade da Base de Conhecimento."""
from sqlalchemy import event

from app.models.rag import KnowledgeDoc
from app.services.knowledge_autoapproval import (
    POLITICA,
    POLITICA_CONFIANCA_BLOQUEADA,
    POLITICA_DECISAO_HUMANA,
    POLITICA_JURIDICO_PENDENTE,
    POLITICA_QUARENTENA,
    POLITICA_REVISAO_PENDENTE,
    POLITICA_STATUS_EXPLICITO,
    _aprovar_no_flush,
    aplicar_aprovacao_automatica,
)


def _doc(extra=None, categoria="legislacao") -> KnowledgeDoc:
    return KnowledgeDoc(
        id="doc-teste",
        titulo="Documento excepcional",
        categoria=categoria,
        extra=extra,
    )


def test_conteudo_juridico_sem_status_explicito_nasce_pendente():
    doc = _doc({"confidence_level": "alta"})
    extra = aplicar_aprovacao_automatica(doc)

    assert extra["rag_status"] == "pendente"
    assert extra["confidence_level"] == "alta"
    assert extra["auto_approval"]["policy"] == POLITICA_JURIDICO_PENDENTE
    assert extra["auto_approval"]["previous_rag_status"] is None
    assert "approved_at" not in extra["auto_approval"]


def test_conteudo_nao_juridico_sem_status_mantem_compatibilidade_autoaprovada():
    doc = _doc({"confidence_level": "alta"}, categoria="manual_operacional_interno")
    extra = aplicar_aprovacao_automatica(doc)

    assert extra["rag_status"] == "aprovado"
    assert extra["confidence_level"] == "alta"
    assert extra["auto_approval"]["policy"] == POLITICA
    assert "approved_at" in extra["auto_approval"]


def test_status_pendente_explicito_nao_e_autoaprovado():
    doc = _doc({"rag_status": "pendente", "confidence_level": "alta"})
    extra = aplicar_aprovacao_automatica(doc)

    assert extra["rag_status"] == "pendente"
    assert extra["confidence_level"] == "alta"
    assert extra["auto_approval"]["policy"] == POLITICA_STATUS_EXPLICITO
    assert "approved_at" not in extra["auto_approval"]


def test_status_aprovado_explicito_de_ingestor_e_preservado():
    doc = _doc({"rag_status": "aprovado", "confidence_level": "alta"})
    extra = aplicar_aprovacao_automatica(doc)

    assert extra["rag_status"] == "aprovado"
    assert extra["confidence_level"] == "alta"
    assert extra["auto_approval"]["policy"] == POLITICA_STATUS_EXPLICITO
    assert "approved_at" in extra["auto_approval"]


def test_status_bloqueado_explicito_e_confianca_bloqueada_sao_preservados():
    doc = _doc({"rag_status": "bloqueado", "confidence_level": "bloqueado"})
    extra = aplicar_aprovacao_automatica(doc)

    assert extra["rag_status"] == "bloqueado"
    assert extra["confidence_level"] == "bloqueado"
    assert extra["auto_approval"]["policy"] == POLITICA_STATUS_EXPLICITO


def test_confianca_bloqueada_sem_status_nao_e_autoaprovada():
    doc = _doc({"confidence_level": "bloqueado"})
    extra = aplicar_aprovacao_automatica(doc)

    assert extra["rag_status"] == "bloqueado"
    assert extra["confidence_level"] == "bloqueado"
    assert extra["auto_approval"]["policy"] == POLITICA_CONFIANCA_BLOQUEADA


def test_metadados_de_fonte_nao_sao_falsificados():
    doc = _doc({
        "fonte_validada": False,
        "fonte_url": "https://exemplo.invalid/documento",
        "requires_human_review": True,
    })
    extra = aplicar_aprovacao_automatica(doc)

    assert extra["fonte_validada"] is False
    assert extra["requires_human_review"] is True
    assert extra["rag_status"] == "pendente"
    assert extra["auto_approval"]["policy"] == POLITICA_REVISAO_PENDENTE


def test_revisao_pendente_preserva_status_explicito_e_nao_auto_aprova():
    doc = _doc({"requires_human_review": True, "rag_status": "pendente"})
    extra = aplicar_aprovacao_automatica(doc)
    assert extra["rag_status"] == "pendente"

    doc2 = _doc({"requires_human_review": True, "rag_status": "aprovado"})
    extra2 = aplicar_aprovacao_automatica(doc2)
    assert extra2["rag_status"] == "pendente"

    doc2b = _doc({
        "requires_human_review": True,
        "rag_status": "disponivel_informativo",
    })
    extra2b = aplicar_aprovacao_automatica(doc2b)
    assert extra2b["rag_status"] == "disponivel_informativo"

    doc3 = _doc({
        "requires_human_review": True,
        "human_reviewed": True,
        "rag_status": "pendente",
    })
    extra3 = aplicar_aprovacao_automatica(doc3)
    assert extra3["rag_status"] == "pendente"
    assert extra3["auto_approval"]["policy"] == POLITICA_DECISAO_HUMANA


def test_recusa_humana_nao_vira_aprovacao():
    doc = _doc({
        "requires_human_review": True,
        "human_reviewed": True,
        "rag_status": "recusado",
    })
    extra = aplicar_aprovacao_automatica(doc)
    assert extra["rag_status"] == "recusado"

    doc_ok = _doc({
        "requires_human_review": True,
        "human_reviewed": True,
        "rag_status": "aprovado",
    })
    assert aplicar_aprovacao_automatica(doc_ok)["rag_status"] == "aprovado"

    doc_sem = _doc({"human_reviewed": True})
    assert aplicar_aprovacao_automatica(doc_sem)["rag_status"] == "aprovado"


def test_quarentena_tem_precedencia_sobre_revisao_e_status_aprovado():
    doc = _doc({
        "requires_human_review": True,
        "human_reviewed": True,
        "rag_status": "aprovado",
        "quarantine_active": True,
    })
    extra = aplicar_aprovacao_automatica(doc)
    assert extra["rag_status"] == "pendente"
    assert extra["quarantine_active"] is True
    assert extra["auto_approval"]["policy"] == POLITICA_QUARENTENA


def test_quarentena_preserva_recusa_humana_mais_restritiva():
    doc = _doc({
        "requires_human_review": True,
        "human_reviewed": True,
        "rag_status": "recusado",
        "quarantine_active": True,
    })
    extra = aplicar_aprovacao_automatica(doc)
    assert extra["rag_status"] == "recusado"
    assert extra["auto_approval"]["policy"] == POLITICA_QUARENTENA


def test_listener_orm_esta_registrado():
    assert event.contains(KnowledgeDoc, "before_insert", _aprovar_no_flush)
    assert event.contains(KnowledgeDoc, "before_update", _aprovar_no_flush)
