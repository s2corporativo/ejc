"""Preflight read-only da topologia de storage documental.

O objetivo é detectar inconsistências de metadados antes de qualquer backfill de
SHA-256, outbox ou migration que passe a tratar storage como identidade forte.
O serviço não lê arquivos locais, não chama Google Drive e não retorna paths,
filenames ou IDs; apenas contagens agregadas.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document


@dataclass(frozen=True, slots=True)
class AuditoriaStorageDocumental:
    documentos_ativos: int
    ativos_drive: int
    ativos_local: int
    drive_id_duplicado: int
    drive_id_sem_marcador: int
    marcador_drive_sem_id: int
    paths_ativos_duplicados: int

    @property
    def metadados_consistentes(self) -> bool:
        return all(
            valor == 0
            for valor in (
                self.drive_id_duplicado,
                self.drive_id_sem_marcador,
                self.marcador_drive_sem_id,
                self.paths_ativos_duplicados,
            )
        )


async def auditar_storage_documental(db: AsyncSession) -> AuditoriaStorageDocumental:
    """Executa somente SELECTs agregados sobre documentos ativos.

    ``drive://`` é o marcador persistido pelo B1 para documentos remotos. Linhas
    legadas com ``drive_file_id`` mas filepath antigo são reportadas como
    inconsistência/readiness, não corrigidas automaticamente.
    """

    ativos = Document.deleted_at.is_(None)
    marcador_drive = Document.filepath.like("drive://%")

    documentos_ativos = await db.scalar(
        select(func.count(Document.id)).where(ativos)
    ) or 0
    ativos_drive = await db.scalar(
        select(func.count(Document.id)).where(
            ativos,
            Document.drive_file_id.is_not(None),
        )
    ) or 0
    ativos_local = await db.scalar(
        select(func.count(Document.id)).where(
            ativos,
            Document.drive_file_id.is_(None),
            ~marcador_drive,
        )
    ) or 0

    drive_ids_duplicados = (
        select(Document.drive_file_id)
        .where(
            ativos,
            Document.drive_file_id.is_not(None),
        )
        .group_by(Document.drive_file_id)
        .having(func.count(Document.id) > 1)
        .subquery()
    )
    drive_id_duplicado = await db.scalar(
        select(func.count()).select_from(drive_ids_duplicados)
    ) or 0

    drive_id_sem_marcador = await db.scalar(
        select(func.count(Document.id)).where(
            ativos,
            Document.drive_file_id.is_not(None),
            ~marcador_drive,
        )
    ) or 0

    marcador_drive_sem_id = await db.scalar(
        select(func.count(Document.id)).where(
            ativos,
            Document.drive_file_id.is_(None),
            marcador_drive,
        )
    ) or 0

    paths_duplicados = (
        select(Document.filepath)
        .where(ativos)
        .group_by(Document.filepath)
        .having(func.count(Document.id) > 1)
        .subquery()
    )
    paths_ativos_duplicados = await db.scalar(
        select(func.count()).select_from(paths_duplicados)
    ) or 0

    return AuditoriaStorageDocumental(
        documentos_ativos=int(documentos_ativos),
        ativos_drive=int(ativos_drive),
        ativos_local=int(ativos_local),
        drive_id_duplicado=int(drive_id_duplicado),
        drive_id_sem_marcador=int(drive_id_sem_marcador),
        marcador_drive_sem_id=int(marcador_drive_sem_id),
        paths_ativos_duplicados=int(paths_ativos_duplicados),
    )
