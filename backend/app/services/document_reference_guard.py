"""Guarda canônica de integridade referencial do GED.

Um ``Document`` é parte do histórico jurídico/probatório do EJC e pode ser
referenciado por vários módulos além do próprio GED. Como a exclusão normal do
sistema é *soft delete*, confiar somente em ``ON DELETE`` de FKs é incorreto:
a referência continuaria apontando para uma linha ocultada pela aplicação.

Este serviço mantém a política em uma única camada neutra e faz uma única ida
ao banco por verificação. O custo é O(k) predicados de existência, onde ``k`` é
um conjunto fixo de tipos de referência; não cresce em memória com o número de
registros associados e não materializa conteúdo, títulos ou PII.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from fastapi import HTTPException
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.centro_custo import CentroCusto
from app.models.contrato_societario import ContratoSocietario
from app.models.data_room import DataRoomArquivo
from app.models.deadline import Deadline
from app.models.document import Document
from app.models.document_intake import DocumentIntakeItem
from app.models.fee import FeePayment
from app.models.legal_doc import LegalDoc
from app.models.processo_eletronico import DocumentoProcessoEletronicoDedup
from app.models.prova import Prova
from app.models.signature import SignatureRequest
from app.models.solicitacao_documento import SolicitacaoDocumentoItem


class EscopoGuardaDocumento(str, Enum):
    """Mutação documental cuja segurança precisa ser verificada."""

    EXCLUSAO = "exclusao"
    VINCULO = "vinculo"


@dataclass(frozen=True, slots=True)
class ReferenciaDocumento:
    """Metadado mínimo de uma classe de referência ativa.

    ``codigo`` é estável para testes/telemetria e ``rotulo`` é deliberadamente
    genérico: nunca carrega título de peça, nome de cliente ou outro metadado
    potencialmente cross-tenant.
    """

    codigo: str
    rotulo: str


_REFERENCIAS: tuple[ReferenciaDocumento, ...] = (
    ReferenciaDocumento("protocolo", "comprovante de protocolo"),
    ReferenciaDocumento("prova", "prova do caso"),
    ReferenciaDocumento("assinatura", "solicitação de assinatura"),
    ReferenciaDocumento("centro_custo", "lançamento de centro de custos"),
    ReferenciaDocumento("fee_payment", "comprovante financeiro"),
    ReferenciaDocumento("deadline", "prazo originado do documento"),
    ReferenciaDocumento("solicitacao_cliente", "solicitação documental do cliente"),
    ReferenciaDocumento("contrato", "contrato societário"),
    ReferenciaDocumento("processo_eletronico", "sincronização de processo eletrônico"),
    ReferenciaDocumento("data_room", "arquivo de Data Room"),
    ReferenciaDocumento("intake", "proveniência de ingestão documental"),
    ReferenciaDocumento("versao_posterior", "versão documental posterior"),
)


async def referencias_ativas_documento(
    db: AsyncSession,
    document_id: str,
    *,
    escopo: EscopoGuardaDocumento = EscopoGuardaDocumento.EXCLUSAO,
) -> tuple[ReferenciaDocumento, ...]:
    """Retorna somente as classes de referência que bloqueiam a mutação.

    Para exclusão, preserva todo o grafo operacional/probatório conhecido. Para
    vínculo de documento ainda solto, mantém a política já consolidada pelo F3.2:
    referências de protocolo e Prova são bloqueantes, pois já atribuem contexto
    jurídico ao arquivo mesmo que ``Document.case_id`` esteja ausente por legado.
    """

    # EXISTS evita materializar coleções ou conteúdo. A consulta devolve uma
    # única linha com booleanos e, portanto, memória O(1) por requisição.
    stmt = select(
        exists(
            select(LegalDoc.id).where(
                LegalDoc.protocolo_comprovante_doc_id == document_id,
                LegalDoc.deleted_at.is_(None),
            )
        ).label("protocolo"),
        exists(
            select(Prova.id).where(
                Prova.document_id == document_id,
                Prova.deleted_at.is_(None),
            )
        ).label("prova"),
        exists(
            select(SignatureRequest.id).where(
                SignatureRequest.document_id == document_id,
                SignatureRequest.deleted_at.is_(None),
            )
        ).label("assinatura"),
        exists(
            select(CentroCusto.id).where(
                CentroCusto.comprovante_id == document_id,
                CentroCusto.deleted_at.is_(None),
            )
        ).label("centro_custo"),
        exists(
            select(FeePayment.id).where(FeePayment.comprovante_doc_id == document_id)
        ).label("fee_payment"),
        exists(
            select(Deadline.id).where(
                Deadline.origem_documento_id == document_id,
                Deadline.deleted_at.is_(None),
            )
        ).label("deadline"),
        exists(
            select(SolicitacaoDocumentoItem.id).where(
                SolicitacaoDocumentoItem.documento_id == document_id
            )
        ).label("solicitacao_cliente"),
        exists(
            select(ContratoSocietario.id).where(
                ContratoSocietario.documento_id == document_id,
                ContratoSocietario.deleted_at.is_(None),
            )
        ).label("contrato"),
        exists(
            select(DocumentoProcessoEletronicoDedup.id).where(
                DocumentoProcessoEletronicoDedup.document_id == document_id
            )
        ).label("processo_eletronico"),
        exists(
            select(DataRoomArquivo.id).where(DataRoomArquivo.document_id == document_id)
        ).label("data_room"),
        exists(
            select(DocumentIntakeItem.id).where(
                DocumentIntakeItem.document_id == document_id
            )
        ).label("intake"),
        exists(
            select(Document.id).where(
                Document.versao_anterior_id == document_id,
                Document.deleted_at.is_(None),
            )
        ).label("versao_posterior"),
    )
    flags = (await db.execute(stmt)).mappings().one()

    codigos_bloqueantes = (
        {"protocolo", "prova"}
        if escopo == EscopoGuardaDocumento.VINCULO
        else {ref.codigo for ref in _REFERENCIAS}
    )
    return tuple(
        ref
        for ref in _REFERENCIAS
        if ref.codigo in codigos_bloqueantes and bool(flags.get(ref.codigo))
    )


async def exigir_documento_sem_referencias_bloqueantes(
    db: AsyncSession,
    document_id: str,
    *,
    acao: str,
    escopo: EscopoGuardaDocumento = EscopoGuardaDocumento.EXCLUSAO,
) -> None:
    """Falha fechado quando a mutação quebraria referência jurídica/operacional."""

    referencias = await referencias_ativas_documento(db, document_id, escopo=escopo)
    if not referencias:
        return

    tipos = ", ".join(ref.rotulo for ref in referencias)
    raise HTTPException(
        status_code=409,
        detail=(
            f"Documento possui referência ativa ({tipos}) e não pode ser {acao}. "
            "Remova ou substitua a referência no módulo de origem antes de continuar."
        ),
    )
