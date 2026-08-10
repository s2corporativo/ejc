"""Preflight read-only para o schema de versionamento documental.

A futura constraint ``UNIQUE (versao_grupo_id, versao)`` só deve ser criada
depois de provar que os dados históricos estão coerentes. Este serviço executa
somente SELECTs e retorna contagens agregadas, sem título, filename, conteúdo ou
outro metadado livre do documento.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.document import Document


@dataclass(frozen=True, slots=True)
class AuditoriaVersionamentoDocumental:
    total_documentos: int
    documentos_sem_grupo: int
    numeracoes_duplicadas: int
    grupos_contexto_inconsistente: int
    grupos_multiplas_raizes: int
    predecessores_ausentes: int
    predecessores_fora_grupo: int
    predecessores_contexto_divergente: int
    cadeias_ciclicas: int
    versoes_invalidas: int

    @property
    def apto_para_constraint(self) -> bool:
        """Aptidão lógica; não substitui backup/CI/migration review."""

        return all(
            valor == 0
            for valor in (
                self.documentos_sem_grupo,
                self.numeracoes_duplicadas,
                self.grupos_contexto_inconsistente,
                self.grupos_multiplas_raizes,
                self.predecessores_ausentes,
                self.predecessores_fora_grupo,
                self.predecessores_contexto_divergente,
                self.cadeias_ciclicas,
                self.versoes_invalidas,
            )
        )


def _grupo_canonico(model=Document):
    return func.coalesce(model.versao_grupo_id, model.id)


async def _contar_cadeias_ciclicas(db: AsyncSession) -> int:
    """Conta origens cuja cadeia de predecessor alcança um ciclo.

    O caminho é mantido dentro do PostgreSQL somente durante o SELECT. Nenhum ID
    é retornado ao caller; o resultado é uma única contagem agregada. A recursão
    para uma origem termina assim que encontra repetição ou predecessor nulo/
    ausente, evitando loop infinito mesmo com histórico corrompido.
    """

    stmt = text(
        """
        WITH RECURSIVE cadeia AS (
            SELECT
                d.id AS origem_id,
                d.id AS atual_id,
                d.versao_anterior_id AS anterior_id,
                ARRAY[d.id]::varchar[] AS caminho,
                FALSE AS ciclo
            FROM documents AS d
            WHERE d.versao_anterior_id IS NOT NULL

            UNION ALL

            SELECT
                c.origem_id,
                p.id AS atual_id,
                p.versao_anterior_id AS anterior_id,
                c.caminho || p.id,
                p.id = ANY(c.caminho) AS ciclo
            FROM cadeia AS c
            JOIN documents AS p ON p.id = c.anterior_id
            WHERE c.anterior_id IS NOT NULL
              AND NOT c.ciclo
        )
        SELECT COUNT(DISTINCT origem_id)
        FROM cadeia
        WHERE ciclo
        """
    )
    return int((await db.scalar(stmt)) or 0)


async def auditar_versionamento_documental(
    db: AsyncSession,
) -> AuditoriaVersionamentoDocumental:
    """Executa apenas leituras agregadas sobre toda a história de ``documents``.

    Soft-deleted também participam: histórico não pode reutilizar número nem
    esconder inconsistência que impediria uma constraint global futura.
    """

    grupo = _grupo_canonico()

    total_documentos = await db.scalar(select(func.count(Document.id))) or 0
    documentos_sem_grupo = await db.scalar(
        select(func.count(Document.id)).where(Document.versao_grupo_id.is_(None))
    ) or 0

    slots_duplicados = (
        select(
            grupo.label("grupo_id"),
            Document.versao.label("versao"),
        )
        .group_by(grupo, Document.versao)
        .having(func.count(Document.id) > 1)
        .subquery()
    )
    numeracoes_duplicadas = await db.scalar(
        select(func.count()).select_from(slots_duplicados)
    ) or 0

    grupos_contexto = (
        select(grupo.label("grupo_id"))
        .group_by(grupo)
        .having(
            or_(
                func.count(
                    func.distinct(func.coalesce(Document.case_id, "__NULL__"))
                )
                > 1,
                func.count(
                    func.distinct(func.coalesce(Document.client_id, "__NULL__"))
                )
                > 1,
            )
        )
        .subquery()
    )
    grupos_contexto_inconsistente = await db.scalar(
        select(func.count()).select_from(grupos_contexto)
    ) or 0

    multiplas_raizes = (
        select(grupo.label("grupo_id"))
        .where(Document.versao_anterior_id.is_(None))
        .group_by(grupo)
        .having(func.count(Document.id) > 1)
        .subquery()
    )
    grupos_multiplas_raizes = await db.scalar(
        select(func.count()).select_from(multiplas_raizes)
    ) or 0

    filho = aliased(Document)
    pai = aliased(Document)
    grupo_filho = _grupo_canonico(filho)
    grupo_pai = _grupo_canonico(pai)

    predecessores_ausentes = await db.scalar(
        select(func.count(filho.id))
        .select_from(filho)
        .outerjoin(pai, pai.id == filho.versao_anterior_id)
        .where(
            filho.versao_anterior_id.is_not(None),
            pai.id.is_(None),
        )
    ) or 0

    predecessores_fora_grupo = await db.scalar(
        select(func.count(filho.id))
        .select_from(filho)
        .join(pai, pai.id == filho.versao_anterior_id)
        .where(grupo_filho.is_distinct_from(grupo_pai))
    ) or 0

    predecessores_contexto_divergente = await db.scalar(
        select(func.count(filho.id))
        .select_from(filho)
        .join(pai, pai.id == filho.versao_anterior_id)
        .where(
            or_(
                filho.case_id.is_distinct_from(pai.case_id),
                filho.client_id.is_distinct_from(pai.client_id),
            )
        )
    ) or 0

    cadeias_ciclicas = await _contar_cadeias_ciclicas(db)

    versoes_invalidas = await db.scalar(
        select(func.count(Document.id)).where(
            or_(
                Document.versao.is_(None),
                Document.versao < 1,
            )
        )
    ) or 0

    return AuditoriaVersionamentoDocumental(
        total_documentos=int(total_documentos),
        documentos_sem_grupo=int(documentos_sem_grupo),
        numeracoes_duplicadas=int(numeracoes_duplicadas),
        grupos_contexto_inconsistente=int(grupos_contexto_inconsistente),
        grupos_multiplas_raizes=int(grupos_multiplas_raizes),
        predecessores_ausentes=int(predecessores_ausentes),
        predecessores_fora_grupo=int(predecessores_fora_grupo),
        predecessores_contexto_divergente=int(predecessores_contexto_divergente),
        cadeias_ciclicas=int(cadeias_ciclicas),
        versoes_invalidas=int(versoes_invalidas),
    )
