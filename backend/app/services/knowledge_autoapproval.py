"""Política permanente de aprovação automática da Base de Conhecimento.

Todo ``KnowledgeDoc`` criado ou alterado pelo EJC fica disponível para o RAG
com ``rag_status=aprovado``. A regra é aplicada no nível ORM, portanto alcança
importações manuais, PDF, URL, fontes oficiais, seeds e demais ingestores que
usam o modelo nativo do EJC.

A aprovação significa autorização para recuperação pela inteligência jurídica;
não transforma uma fonte não oficial em fonte oficial e não remove as regras de
isolamento por cliente/caso, vigência, exclusão de corpus fictício ou revisão
humana de peças finais.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import event

from app.models.rag import KnowledgeDoc
from app.services.knowledge_governance import inferir_autoridade

POLITICA = "knowledge_module_always_approved"
_CONFIANCAS_VALIDAS = {"alta", "media", "baixa"}


def _texto(valor: Any) -> str:
    return str(valor or "").strip().lower()


def aplicar_aprovacao_automatica(documento: KnowledgeDoc) -> dict:
    """Aplica aprovação e metadados mínimos de governança ao documento.

    ``confidence_level=bloqueado`` também impediria a recuperação mesmo com
    ``rag_status=aprovado``; por isso é normalizado para ``media``. Confianças
    válidas já definidas (alta/media/baixa) são preservadas.

    A autoridade é inferida de categoria/fonte, sem elevar material não oficial.
    Para legislação sem declaração expressa, a vigência jurídica permanece como
    ``vigencia_nao_verificada`` — versão atual no EJC não equivale a lei vigente.
    """
    extra = dict(documento.extra or {})
    status_anterior = _texto(extra.get("rag_status")) or None
    confianca_anterior = _texto(
        extra.get("confidence_level") or extra.get("confianca")
    ) or None

    confianca = confianca_anterior
    if confianca not in _CONFIANCAS_VALIDAS:
        confianca = "media"

    auditoria = extra.get("auto_approval")
    if not isinstance(auditoria, dict):
        auditoria = {}
    auditoria = dict(auditoria)
    auditoria.setdefault("approved_at", datetime.now(timezone.utc).isoformat())
    auditoria.setdefault("previous_rag_status", status_anterior)
    auditoria.setdefault("previous_confidence_level", confianca_anterior)
    auditoria["policy"] = POLITICA

    authority = inferir_autoridade(documento.categoria, documento.fonte, extra)
    extra.setdefault("authority_level", authority["code"])
    extra.setdefault("source_official", authority["official"])
    if "legisl" in _texto(documento.categoria):
        extra.setdefault("legal_status", "vigencia_nao_verificada")

    extra["rag_status"] = "aprovado"
    extra["confidence_level"] = confianca
    extra["auto_approval"] = auditoria
    documento.extra = extra
    return extra


@event.listens_for(KnowledgeDoc, "before_insert", propagate=True)
@event.listens_for(KnowledgeDoc, "before_update", propagate=True)
def _aprovar_no_flush(_mapper, _connection, target: KnowledgeDoc) -> None:
    aplicar_aprovacao_automatica(target)
