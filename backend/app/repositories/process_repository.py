"""Persistência canônica da entidade Processo."""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case
from app.models.process import Process


class ProcessRepository:
    async def list_for_case(
        self, db: AsyncSession, case_id: str, archive_filter: str = "ativos"
    ) -> Sequence[Process]:
        query = select(Process).where(
            Process.case_id == case_id,
            Process.deleted_at.is_(None),
        )
        if archive_filter == "ativos":
            query = query.where(Process.status != "arquivado")
        elif archive_filter == "arquivados":
            query = query.where(Process.status == "arquivado")
        query = query.order_by(Process.is_principal.desc(), Process.created_at.asc())
        return (await db.execute(query)).scalars().all()

    async def get(self, db: AsyncSession, process_id: str) -> Process | None:
        return (
            await db.execute(
                select(Process).where(
                    Process.id == process_id,
                    Process.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()

    async def principal(self, db: AsyncSession, case_id: str) -> Process | None:
        return (
            await db.execute(
                select(Process)
                .where(
                    Process.case_id == case_id,
                    Process.is_principal.is_(True),
                    Process.deleted_at.is_(None),
                )
                .limit(1)
            )
        ).scalar_one_or_none()

    async def first_active_except(
        self, db: AsyncSession, case_id: str, excluded_id: str
    ) -> Process | None:
        return (
            await db.execute(
                select(Process)
                .where(
                    Process.case_id == case_id,
                    Process.id != excluded_id,
                    Process.status != "arquivado",
                    Process.deleted_at.is_(None),
                )
                .order_by(Process.created_at.asc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def lock_case(self, db: AsyncSession, case_id: str) -> None:
        """Serializa mudanças que podem trocar o processo principal.

        O índice parcial do banco continua sendo a última barreira de unicidade,
        mas o lock pessimista da linha do Caso evita que duas transações façam
        simultaneamente `clear_principal` + promoção e uma delas termine em 500.
        Todas as mutações do serviço canônico adquirem este mesmo lock.
        """
        await db.execute(
            select(Case.id)
            .where(Case.id == case_id, Case.deleted_at.is_(None))
            .with_for_update()
        )

    async def clear_principal(self, db: AsyncSession, case_id: str) -> None:
        await db.execute(
            update(Process)
            .where(
                Process.case_id == case_id,
                Process.is_principal.is_(True),
                Process.deleted_at.is_(None),
            )
            .values(is_principal=False)
        )


process_repository = ProcessRepository()
