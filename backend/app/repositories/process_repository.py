"""Persistência canônica da entidade Processo."""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import exists, func, or_, select, text, update
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

    async def lock_cnj(self, db: AsyncSession, numero_cnj_normalizado: str) -> None:
        \"\"\"Serializa vínculos concorrentes do mesmo CNJ entre casos distintos.\"\"\"
        await db.execute(
            text(\"SELECT pg_advisory_xact_lock(hashtext(:chave))\"),
            {\"chave\": f\"process_cnj:{numero_cnj_normalizado}\"},
        )

    async def case_ids_for_cnj(
        self, db: AsyncSession, numero_cnj_normalizado: str
    ) -> list[str]:
        \"\"\"Resolve todos os casos que já referenciam o CNJ, inclusive excluídos.

        Process é a fonte canônica; Case.numero_processo entra como fallback
        legado. Não filtrar soft-delete aqui é deliberado: recriar um caso
        apagado sem perceber reintroduziria duplicidade e quebraria a trilha.
        \"\"\"
        cnj_process = (
            func.regexp_replace(func.coalesce(Process.numero_cnj, \"\"), r\"\\D\", \"\", \"g\")
            == numero_cnj_normalizado
        )
        cnj_case = (
            func.regexp_replace(func.coalesce(Case.numero_processo, \"\"), r\"\\D\", \"\", \"g\")
            == numero_cnj_normalizado
        )
        rows = (
            await db.execute(
                select(Case.id)
                .distinct()
                .where(
                    or_(
                        cnj_case,
                        exists().where(Process.case_id == Case.id, cnj_process),
                    )
                )
            )
        ).scalars().all()
        return list(rows)

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
