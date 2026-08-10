"""Preflight complementar de linearidade do versionamento documental.

Complementa ``document_version_audit_service`` sem substituir seu contrato.
Executa somente SELECTs agregados e detecta estados que o writer endurecido não
aceita: ramificação, salto de número entre predecessor/sucessor e ponta histórica
soft-deleted acima da maior versão ativa.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.document import Document


@dataclass(frozen=True, slots=True)
class AuditoriaLinearidadeVersoes:
    predecessores_com_multiplos_sucessores: int
    arestas_versao_invalidas: int
    grupos_ponta_historica_deletada: int

    @property
    def cadeia_linear(self) -> bool:
        return all(
            valor == 0
            for valor in (
                self.predecessores_com_multiplos_sucessores,
                self.arestas_versao_invalidas,
                self.grupos_ponta_historica_deletada,
            )
        )


def _grupo_canonico(model=Document):
    return func.coalesce(model.versao_grupo_id, model.id)


async def auditar_linearidade_versionamento(
    db: AsyncSession,
) -> AuditoriaLinearidadeVersoes:
    """Retorna somente contagens agregadas; nenhum ID/metadado livre sai do DB."""

    ramificacoes = (
        select(Document.versao_anterior_id)
        .where(Document.versao_anterior_id.is_not(None))
        .group_by(Document.versao_anterior_id)
        .having(func.count(Document.id) > 1)
        .subquery()
    )
    predecessores_com_multiplos_sucessores = int(
        (await db.scalar(select(func.count()).select_from(ramificacoes))) or 0
    )

    filho = aliased(Document)
    pai = aliased(Document)
    arestas_versao_invalidas = int(
        (
            await db.scalar(
                select(func.count(filho.id))
                .select_from(filho)
                .join(pai, pai.id == filho.versao_anterior_id)
                .where(filho.versao.is_distinct_from(pai.versao + 1))
            )
        )
        or 0
    )

    grupo = _grupo_canonico()
    pontas = (
        select(
            grupo.label("grupo_id"),
            func.max(Document.versao).label("max_historica"),
            func.max(Document.versao)
            .filter(Document.deleted_at.is_(None))
            .label("max_ativa"),
        )
        .group_by(grupo)
        .subquery()
    )
    grupos_ponta_historica_deletada = int(
        (
            await db.scalar(
                select(func.count())
                .select_from(pontas)
                .where(
                    pontas.c.max_ativa.is_not(None),
                    pontas.c.max_historica > pontas.c.max_ativa,
                )
            )
        )
        or 0
    )

    return AuditoriaLinearidadeVersoes(
        predecessores_com_multiplos_sucessores=predecessores_com_multiplos_sucessores,
        arestas_versao_invalidas=arestas_versao_invalidas,
        grupos_ponta_historica_deletada=grupos_ponta_historica_deletada,
    )
