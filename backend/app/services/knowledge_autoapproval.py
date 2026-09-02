"""Política central de disponibilidade da Base de Conhecimento.

O listener ORM alcança importações manuais, fontes oficiais, seeds e ingestores.
Por isso ele não pode contradizer um estado de governança explicitamente gravado
pelo produtor do documento.

Ordem de precedência:
1. quarentena ativa;
2. revisão humana pendente;
3. decisão humana já registrada;
4. ``rag_status`` explícito do ingestor/curador;
5. confiança explicitamente bloqueada;
6. conteúdo jurídico sem estado explícito nasce pendente;
7. compatibilidade legada: somente documento não jurídico sem estado explícito
   pode nascer automaticamente aprovado.

Aprovação significa apenas autorização para retrieval; não transforma conteúdo
não oficial em fonte oficial nem supera isolamento, vigência ou HITL de peças.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import event

from app.models.rag import KnowledgeDoc
from app.services.knowledge_governance import inferir_autoridade

POLITICA = "knowledge_module_default_approved_when_unspecified"
POLITICA_STATUS_EXPLICITO = "explicit_rag_status_respected"
POLITICA_REVISAO_PENDENTE = "human_review_required_not_auto_approved"
POLITICA_DECISAO_HUMANA = "human_decision_respected"
POLITICA_QUARENTENA = "quarantine_active_not_auto_approved"
POLITICA_CONFIANCA_BLOQUEADA = "blocked_confidence_not_auto_approved"
POLITICA_JURIDICO_PENDENTE = "legal_content_requires_explicit_approval"
_CONFIANCAS_VALIDAS = {"alta", "media", "baixa", "bloqueado"}
_CATEGORIA_JURIDICA_TOKENS = (
    "legisl",
    "norma",
    "regulamento",
    "sumula",
    "juris",
    "acordao",
    "precedente",
    "proposicao",
    "peca",
    "tese",
    "parecer",
    "enunciado",
    "datajud",
    "juridic",
)
_AUTORIDADES_JURIDICAS = {
    "oficial_normativa",
    "precedente_vinculante",
    "jurisprudencia_oficial",
}


def _texto(valor: Any) -> str:
    return str(valor or "").strip().lower()


def _conteudo_juridico_exige_status(
    documento: KnowledgeDoc, authority: dict[str, Any]
) -> bool:
    categoria = _texto(documento.categoria)
    return (
        any(token in categoria for token in _CATEGORIA_JURIDICA_TOKENS)
        or _texto(authority.get("code")) in _AUTORIDADES_JURIDICAS
    )


def aplicar_aprovacao_automatica(documento: KnowledgeDoc) -> dict:
    """Aplica o contrato de governança sem sobrepor decisões explícitas."""
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
    agora = datetime.now(timezone.utc).isoformat()
    auditoria.setdefault("evaluated_at", agora)
    auditoria.setdefault("previous_rag_status", status_anterior)
    auditoria.setdefault("previous_confidence_level", confianca_anterior)

    authority = inferir_autoridade(documento.categoria, documento.fonte, extra)
    extra.setdefault("authority_level", authority["code"])
    extra.setdefault("source_official", authority["official"])
    if "legisl" in _texto(documento.categoria):
        extra.setdefault("legal_status", "vigencia_nao_verificada")

    quarentena = bool(extra.get("quarantine_active"))
    requer_revisao = bool(extra.get("requires_human_review"))
    revisado = bool(extra.get("human_reviewed"))
    status_atual = _texto(extra.get("rag_status"))

    if quarentena:
        # Recusa humana já é mais restritiva; qualquer outro estado fica pendente.
        if status_atual != "recusado":
            extra["rag_status"] = "pendente"
        auditoria["policy"] = POLITICA_QUARENTENA
    elif requer_revisao and not revisado:
        # Nenhum produtor pode contornar a exigência declarando 'aprovado'.
        if status_atual in ("", "aprovado"):
            extra["rag_status"] = "pendente"
        auditoria["policy"] = POLITICA_REVISAO_PENDENTE
    elif revisado:
        # A decisão humana prevalece; ausência de status significa aprovação
        # compatível com o comportamento histórico do fluxo de revisão.
        extra.setdefault("rag_status", "aprovado")
        auditoria["policy"] = POLITICA_DECISAO_HUMANA
    elif status_anterior is not None:
        # P0: estado explicitamente escolhido pelo ingestor/curador não pode ser
        # promovido silenciosamente por um listener genérico.
        extra["rag_status"] = status_anterior
        auditoria["policy"] = POLITICA_STATUS_EXPLICITO
    elif confianca == "bloqueado":
        # Confiança bloqueada sem status explícito continua fora do RAG.
        extra["rag_status"] = "bloqueado"
        auditoria["policy"] = POLITICA_CONFIANCA_BLOQUEADA
    elif _conteudo_juridico_exige_status(documento, authority):
        # P0 #985: conteúdo jurídico não pode receber aprovação por ausência de
        # estado. Ingestores/curadores precisam declarar a decisão explicitamente.
        extra["rag_status"] = "pendente"
        auditoria["policy"] = POLITICA_JURIDICO_PENDENTE
    else:
        # Compatibilidade legada limitada ao conteúdo não jurídico realmente
        # não governado. Não concede força jurídica; só disponibilidade no RAG.
        extra["rag_status"] = "aprovado"
        auditoria["policy"] = POLITICA

    if _texto(extra.get("rag_status")) == "aprovado":
        auditoria.setdefault("approved_at", agora)

    extra["confidence_level"] = confianca
    extra["auto_approval"] = auditoria
    documento.extra = extra
    return extra


@event.listens_for(KnowledgeDoc, "before_insert", propagate=True)
@event.listens_for(KnowledgeDoc, "before_update", propagate=True)
def _aprovar_no_flush(_mapper, _connection, target: KnowledgeDoc) -> None:
    aplicar_aprovacao_automatica(target)
