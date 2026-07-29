"""Política de aprovação automática da Base de Conhecimento.

``KnowledgeDoc`` criado ou alterado pelo EJC fica disponível para o RAG com
``rag_status=aprovado``. A regra é aplicada no nível ORM, portanto alcança
importações manuais, PDF, URL, fontes oficiais, seeds e demais ingestores que
usam o modelo nativo do EJC.

EXCEÇÃO OBRIGATÓRIA (auditoria 2026-07-26, achado AI-079): documento marcado
``requires_human_review=True`` que ainda não foi revisado
(``human_reviewed`` falsy) NUNCA é auto-aprovado — o rag_status explícito do
ingestor (ex.: ``pendente`` no feed cognitivo do DataJud) é preservado, e a
promoção a ``aprovado`` só acontece por ato explícito da governança
(ia_governanca / revisão de conhecimento).

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
# AI-079: docs aguardando revisão humana ficam FORA da auto-aprovação.
POLITICA_REVISAO_PENDENTE = "human_review_required_not_auto_approved"
# Documento JÁ revisado por humano: o status escolhido pelo revisor prevalece
# sobre a auto-aprovação (inclusive uma recusa).
POLITICA_DECISAO_HUMANA = "human_decision_respected"
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

    # AI-079: pendência de revisão humana BLOQUEIA a auto-aprovação. 'aprovado'
    # sem human_reviewed é rebaixado a 'pendente' (nenhum ingestor pode gravar
    # aprovação junto com requires_human_review); status explícitos não-aprovados
    # (ex.: 'disponivel_informativo') são preservados.
    #
    # DECISÃO HUMANA MANDA (review do Codex no PR #496): quando `human_reviewed`
    # está marcado, o status escolhido pelo revisor é RESPEITADO — inclusive
    # `recusado`. Sem esta cláusula, a auto-aprovação caía no `else` e
    # transformava uma RECUSA em 'aprovado', liberando ao RAG justamente o
    # documento que o curador rejeitou.
    requer_revisao = bool(extra.get("requires_human_review"))
    revisado = bool(extra.get("human_reviewed"))
    if requer_revisao and not revisado:
        if _texto(extra.get("rag_status")) in ("", "aprovado"):
            extra["rag_status"] = "pendente"
        auditoria["policy"] = POLITICA_REVISAO_PENDENTE
    elif revisado:
        # Só define default se o revisor não tiver gravado status algum.
        extra.setdefault("rag_status", "aprovado")
        auditoria["policy"] = POLITICA_DECISAO_HUMANA
    else:
        extra["rag_status"] = "aprovado"
    extra["confidence_level"] = confianca
    extra["auto_approval"] = auditoria
    documento.extra = extra
    return extra


@event.listens_for(KnowledgeDoc, "before_insert", propagate=True)
@event.listens_for(KnowledgeDoc, "before_update", propagate=True)
def _aprovar_no_flush(_mapper, _connection, target: KnowledgeDoc) -> None:
    aplicar_aprovacao_automatica(target)
