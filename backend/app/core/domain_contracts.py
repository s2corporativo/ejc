"""Vocabulário canônico do domínio EJC, sem alterar enums físicos do banco."""
from __future__ import annotations

from enum import StrEnum


class CaseLifecycleStatus(StrEnum):
    TRIAGEM = "triagem"
    EM_ANALISE = "em_analise"
    AGUARDANDO_DOCUMENTOS = "aguardando_documentos"
    PROPOSTA_APRESENTADA = "proposta_apresentada"
    CONTRATACAO_PENDENTE = "contratacao_pendente"
    CONTRATADO = "contratado"
    EM_ANDAMENTO = "em_andamento"
    SUSPENSO = "suspenso"
    ENCERRADO = "encerrado"
    ARQUIVADO = "arquivado"
    NAO_CONTRATADO = "nao_contratado"


class TaskLifecycleStatus(StrEnum):
    PENDENTE = "pendente"
    EM_EXECUCAO = "em_execucao"
    AGUARDANDO_TERCEIRO = "aguardando_terceiro"
    CONCLUIDA = "concluida"
    CANCELADA = "cancelada"
    VENCIDA = "vencida"


class DocumentLifecycleStatus(StrEnum):
    RASCUNHO = "rascunho"
    EM_ELABORACAO = "em_elaboracao"
    EM_REVISAO = "em_revisao"
    APROVADO = "aprovado"
    ASSINADO = "assinado"
    PROTOCOLADO = "protocolado"
    SUBSTITUIDO = "substituido"
    ARQUIVADO = "arquivado"


class FinancialLifecycleStatus(StrEnum):
    PREVISTO = "previsto"
    FATURADO = "faturado"
    PARCIALMENTE_RECEBIDO = "parcialmente_recebido"
    RECEBIDO = "recebido"
    VENCIDO = "vencido"
    RENEGOCIADO = "renegociado"
    CANCELADO = "cancelado"


LEGACY_CASE_STATUS_TO_CANONICAL: dict[str, CaseLifecycleStatus] = {
    "triagem": CaseLifecycleStatus.TRIAGEM,
    "ativo": CaseLifecycleStatus.EM_ANDAMENTO,
    "suspenso": CaseLifecycleStatus.SUSPENSO,
    "acordo": CaseLifecycleStatus.ENCERRADO,
    "encerrado": CaseLifecycleStatus.ENCERRADO,
    "arquivado": CaseLifecycleStatus.ARQUIVADO,
}


def canonical_case_status(value: str) -> CaseLifecycleStatus:
    """Normaliza status novo ou legado sem modificar a persistência existente."""
    try:
        return CaseLifecycleStatus(value)
    except ValueError:
        if value in LEGACY_CASE_STATUS_TO_CANONICAL:
            return LEGACY_CASE_STATUS_TO_CANONICAL[value]
        raise ValueError(f"Status de caso desconhecido: {value}") from None
