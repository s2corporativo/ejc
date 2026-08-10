"""Persistência transacional do documento local já preparado pela ingestão.

Esta camada conecta a UoW física ao ``Document``/AuditLog sem assumir
responsabilidades de autorização, OCR ou seleção de tipo jurídico. O caller deve
entregar contexto já autorizado e, se houver extração, ``ocr_text`` já sanitizado.

Invariante central:

    staging -> validar/versionar -> promover -> add audit -> COMMIT -> confirmar

Não existe ``await`` entre o retorno bem-sucedido de ``db.commit()`` e
``ingestao.confirmar()``. Assim, depois que o banco confirma o registro, a UoW
é marcada como confirmada imediatamente e o context manager não pode compensar
um arquivo cujo ``Document`` já foi commitado.

Importante: esta camada persiste somente atributos confirmados no model atual de
``Document``. SHA-256, malware status, OCR-used e metadados extraídos continuam
fora do model até migration canônica futura.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import criar_audit_log
from app.models.document import DocConfidencialidade, Document
from app.services.document_ingestion_service import IngestaoDocumentoLocal
from app.services.document_version_service import (
    configurar_documento_raiz,
    preparar_nova_versao,
)

logger = logging.getLogger(__name__)


class PersistenciaDocumentoInvalidaError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ConteudoDocumentoPreparado:
    """Texto de OCR já sanitizado pelo caller."""

    ocr_text: str | None = None


@dataclass(frozen=True, slots=True)
class DadosPersistenciaDocumento:
    titulo: str | None
    tipo: str | None
    confidencialidade: DocConfidencialidade
    case_id: str | None = None
    client_id: str | None = None
    uploaded_by: str | None = None
    user_role: str | None = None
    documento_anterior_id: str | None = None


def _texto_limitado(
    valor: str | None,
    *,
    campo: str,
    limite: int,
    obrigatorio: bool = False,
) -> str | None:
    if valor is None:
        if obrigatorio:
            raise PersistenciaDocumentoInvalidaError(f"{campo} obrigatório")
        return None
    if not isinstance(valor, str):
        raise PersistenciaDocumentoInvalidaError(f"{campo} inválido")
    normalizado = valor.strip()
    if not normalizado:
        if obrigatorio:
            raise PersistenciaDocumentoInvalidaError(f"{campo} obrigatório")
        return None
    if len(normalizado) > limite:
        raise PersistenciaDocumentoInvalidaError(f"{campo} excede o limite permitido")
    return normalizado


def _validar_dados(
    ingestao: IngestaoDocumentoLocal,
    dados: DadosPersistenciaDocumento,
) -> tuple[
    str,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
]:
    titulo = _texto_limitado(
        dados.titulo or ingestao.filename,
        campo="titulo",
        limite=255,
        obrigatorio=True,
    )
    # Document.tipo é String(50) no model atual; não ampliar por service.
    tipo = _texto_limitado(dados.tipo, campo="tipo", limite=50)
    case_id = _texto_limitado(dados.case_id, campo="case_id", limite=36)
    client_id = _texto_limitado(dados.client_id, campo="client_id", limite=36)
    uploaded_by = _texto_limitado(dados.uploaded_by, campo="uploaded_by", limite=36)
    user_role = _texto_limitado(dados.user_role, campo="user_role", limite=30)
    predecessor = _texto_limitado(
        dados.documento_anterior_id,
        campo="documento_anterior_id",
        limite=36,
    )

    if not isinstance(dados.confidencialidade, DocConfidencialidade):
        raise PersistenciaDocumentoInvalidaError("confidencialidade inválida")

    return (
        titulo,
        tipo,
        case_id,
        client_id,
        uploaded_by,
        user_role,
        predecessor,
    )


def _validar_conteudo(
    conteudo: ConteudoDocumentoPreparado,
) -> ConteudoDocumentoPreparado:
    if conteudo.ocr_text is not None and not isinstance(conteudo.ocr_text, str):
        raise PersistenciaDocumentoInvalidaError("ocr_text inválido")
    return conteudo


async def _rollback_sem_mascarar(db: AsyncSession) -> None:
    """Conclui rollback mesmo se houver novo cancelamento durante a limpeza.

    Esta função só é chamada enquanto uma exceção original já está sendo
    tratada. Cancelamento/erro do próprio rollback nunca substitui essa exceção.
    """

    tarefa = asyncio.create_task(db.rollback())
    try:
        await asyncio.shield(tarefa)
    except asyncio.CancelledError:
        try:
            await tarefa
        except BaseException:
            logger.error("Falha ao executar rollback da persistência documental")
    except BaseException:
        # Não incluir DSN, SQL, errno ou mensagem da exceção de rollback.
        logger.error("Falha ao executar rollback da persistência documental")


async def persistir_documento_local(
    db: AsyncSession,
    ingestao: IngestaoDocumentoLocal,
    *,
    dados: DadosPersistenciaDocumento,
    conteudo: ConteudoDocumentoPreparado | None = None,
) -> Document:
    """Persiste um documento local e confirma a UoW somente após commit.

    A função assume a responsabilidade pelo staging desde a entrada no contexto:
    falha de metadado, versionamento, audit ou commit compensa o arquivo. É seguro
    o caller também manter um ``async with ingestao`` externo durante OCR; a saída
    aninhada vê estado confirmado/compensado e é idempotente.
    """

    conteudo = conteudo or ConteudoDocumentoPreparado()

    async with ingestao:
        try:
            (
                titulo,
                tipo,
                case_id,
                client_id,
                uploaded_by,
                user_role,
                predecessor,
            ) = _validar_dados(ingestao, dados)
            conteudo = _validar_conteudo(conteudo)

            documento = Document(
                id=ingestao.doc_id,
                case_id=case_id,
                client_id=client_id,
                titulo=titulo,
                tipo=tipo,
                filename=ingestao.filename,
                filepath=ingestao.filepath,
                mimetype=ingestao.mimetype,
                size_bytes=ingestao.size_bytes,
                confidencialidade=dados.confidencialidade,
                ocr_text=conteudo.ocr_text,
                uploaded_by=uploaded_by,
            )

            # Adicionar antes de preparar versão é intencional: C1 usa
            # ``db.no_autoflush`` e prova que nenhum INSERT prematuro ocorre.
            db.add(documento)
            if predecessor:
                await preparar_nova_versao(
                    db,
                    documento,
                    documento_anterior_id=predecessor,
                )
            else:
                configurar_documento_raiz(documento)

            # Somente depois das validações/versionamento o arquivo sai da
            # quarentena e ganha o path final.
            ingestao.promover()

            await criar_audit_log(
                db,
                user_id=uploaded_by,
                user_role=user_role,
                acao="UPLOAD",
                entidade="documents",
                registro_id=documento.id,
                detalhes="Documento armazenado no GED",
                dados_depois={
                    "case_id": case_id,
                    "client_id": client_id,
                    "tipo": tipo,
                    "confidencialidade": dados.confidencialidade.value,
                    "versao": documento.versao,
                    "size_bytes": ingestao.size_bytes,
                    "storage": "local",
                    "malware_scan_status": ingestao.malware_scan_status.value,
                },
            )
            await db.commit()
        except BaseException:
            await _rollback_sem_mascarar(db)
            raise

        # Sem await entre commit e confirmação física: cancellation não cria a
        # janela DB-confirmado/UoW-ainda-compensável.
        ingestao.confirmar()

    return documento
