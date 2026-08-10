"""Versionamento explícito e concorrente de ``Document``.

A identidade de uma revisão deve ser o documento predecessor/grupo, nunca a
coincidência de título. Este serviço prepara metadados de versão sob locks da
mesma transação que persistirá o novo ``Document``.

Não há autorização aqui: o caller deve provar acesso ao predecessor antes de
usar o resultado e deve registrar AuditLog junto da criação da nova versão.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document


class DocumentoVersaoError(RuntimeError):
    """Erro de integridade do versionamento documental."""


class DocumentoAnteriorNaoEncontradoError(DocumentoVersaoError):
    pass


class DocumentoContextoDivergenteError(DocumentoVersaoError):
    pass


class DocumentoAnteriorObsoletoError(DocumentoVersaoError):
    pass


class DocumentoGrupoInconsistenteError(DocumentoVersaoError):
    pass


@dataclass(frozen=True, slots=True)
class VersaoDocumentoPreparada:
    grupo_id: str
    versao: int
    anterior_id: str | None


def configurar_documento_raiz(documento: Document) -> VersaoDocumentoPreparada:
    """Inicializa um documento independente como versão 1 do próprio grupo."""

    if not documento.id:
        raise DocumentoVersaoError("documento novo sem identificador")
    documento.versao = 1
    documento.versao_grupo_id = documento.id
    documento.versao_anterior_id = None
    return VersaoDocumentoPreparada(
        grupo_id=documento.id,
        versao=1,
        anterior_id=None,
    )


def _escopo_grupo(grupo_id: str):
    """Inclui raiz legada cujo ``versao_grupo_id`` ainda seja nulo."""

    return or_(
        Document.versao_grupo_id == grupo_id,
        Document.id == grupo_id,
    )


async def preparar_nova_versao(
    db: AsyncSession,
    documento: Document,
    *,
    documento_anterior_id: str,
) -> VersaoDocumentoPreparada:
    """Configura ``documento`` como próxima revisão explícita do predecessor.

    O PostgreSQL advisory lock serializa escritores de um mesmo grupo, inclusive
    quando dois callers escolheram predecessores diferentes. O lock é
    ``transaction-level`` e portanto só protege corretamente se este método e o
    INSERT/commit do novo ``Document`` ocorrerem na mesma transação/sessão.

    A ausência de UNIQUE(grupo, versão) é tratada fail-closed: grupos que já
    possuem numeração duplicada não recebem novas versões até auditoria/backfill.
    """

    if not documento.id or not documento_anterior_id:
        raise DocumentoVersaoError("identificador de versão ausente")
    if documento.id == documento_anterior_id:
        raise DocumentoVersaoError("documento não pode versionar a si mesmo")

    anterior = (
        await db.execute(
            select(Document)
            .where(
                Document.id == documento_anterior_id,
                Document.deleted_at.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if anterior is None:
        raise DocumentoAnteriorNaoEncontradoError("documento predecessor indisponível")

    if documento.case_id != anterior.case_id or documento.client_id != anterior.client_id:
        raise DocumentoContextoDivergenteError("versões pertencem a contextos diferentes")

    grupo_id = anterior.versao_grupo_id or anterior.id

    # Lock de transação, liberado automaticamente em commit/rollback. Colisões
    # do hash apenas serializam grupos não relacionados; não reduzem segurança.
    await db.execute(
        select(
            func.pg_advisory_xact_lock(
                func.hashtextextended(grupo_id, 0)
            )
        )
    )

    escopo = _escopo_grupo(grupo_id)

    # Um grupo histórico cruzando caso/cliente é inconsistente e não deve ser
    # prolongado silenciosamente. ``IS DISTINCT FROM`` trata NULL corretamente.
    contexto_invalido = (
        await db.execute(
            select(Document.id)
            .where(
                escopo,
                or_(
                    Document.case_id.is_distinct_from(anterior.case_id),
                    Document.client_id.is_distinct_from(anterior.client_id),
                ),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if contexto_invalido is not None:
        raise DocumentoGrupoInconsistenteError("grupo documental possui contexto inconsistente")

    versao_duplicada = (
        await db.execute(
            select(Document.versao)
            .where(escopo)
            .group_by(Document.versao)
            .having(func.count(Document.id) > 1)
            .limit(1)
        )
    ).scalar_one_or_none()
    if versao_duplicada is not None:
        raise DocumentoGrupoInconsistenteError("grupo documental possui numeração duplicada")

    maior_versao = await db.scalar(
        select(func.max(Document.versao)).where(escopo)
    )
    maior_versao_ativa = await db.scalar(
        select(func.max(Document.versao)).where(
            escopo,
            Document.deleted_at.is_(None),
        )
    )

    versao_anterior = anterior.versao or 1
    if maior_versao_ativa is None or versao_anterior != maior_versao_ativa:
        raise DocumentoAnteriorObsoletoError("documento predecessor não é a versão vigente")

    proxima_versao = int(maior_versao or 1) + 1
    documento.versao = proxima_versao
    documento.versao_grupo_id = grupo_id
    documento.versao_anterior_id = anterior.id

    return VersaoDocumentoPreparada(
        grupo_id=grupo_id,
        versao=proxima_versao,
        anterior_id=anterior.id,
    )
