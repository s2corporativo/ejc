"""Fachada operacional do backup canônico com exclusão cross-process.

Regra arquitetural:
    callers -> backup_execution_service -> backup_lock -> backup_service

`backup_service` continua responsável por dump/cifragem/offsite/auditoria. Esta
fachada é a única entrada operacional e não duplica regra de negócio do motor.
"""
from __future__ import annotations

import logging
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services import backup_service
from app.services.backup_lock import (
    BackupAlreadyRunning,
    BackupLockError,
    acquire_backup_lock,
)

logger = logging.getLogger("ejc.backup.execution")
settings = get_settings()

BackupLockStatus = Literal["livre", "ocupado", "indisponivel"]


def _busy_result(origem: str) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "em_execucao",
        "origem": origem,
        "detail": "Já existe um backup em andamento.",
    }


def _lock_error_result(origem: str) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "erro_lock",
        "origem": origem,
        "erro": "Não foi possível garantir exclusão mútua do backup.",
    }


def status_mutex_backup() -> BackupLockStatus:
    """Probe instantâneo do mutex compartilhado, sem manter seção crítica.

    É útil apenas para UX/telemetria. Há TOCTOU inevitável entre este probe e
    um disparo posterior; `executar_backup_exclusivo` continua sendo o gate
    autoritativo.
    """
    try:
        lock = acquire_backup_lock(settings.BACKUP_DIR)
    except BackupAlreadyRunning:
        return "ocupado"
    except BackupLockError as exc:
        logger.error(
            "[Backup] probe do mutex falhou (tipo=%s)",
            type(exc).__name__,
        )
        return "indisponivel"
    try:
        return "livre"
    finally:
        lock.release()


async def executar_backup_exclusivo(
    db: AsyncSession,
    *,
    origem: str = "agendado",
    usuario_id: str | None = None,
    usuario_role: str | None = None,
) -> dict[str, Any]:
    """Executa o motor canônico somente após adquirir o mutex compartilhado.

    Lock contention é estado operacional esperado e retorna `em_execucao`.
    Qualquer falha ao preparar/validar o mutex é fail-closed (`erro_lock`).
    """
    try:
        lock = acquire_backup_lock(settings.BACKUP_DIR)
    except BackupAlreadyRunning:
        logger.info("[Backup] execução concorrente recusada (origem=%s)", origem)
        return _busy_result(origem)
    except BackupLockError as exc:
        logger.error(
            "[Backup] mutex indisponível; execução bloqueada (origem=%s, tipo=%s)",
            origem,
            type(exc).__name__,
        )
        return _lock_error_result(origem)

    try:
        return await backup_service.executar_backup(
            db,
            origem=origem,
            usuario_id=usuario_id,
            usuario_role=usuario_role,
        )
    finally:
        lock.release()


async def executar_backup_background_exclusivo(
    *,
    origem: str = "manual",
    usuario_id: str | None = None,
    usuario_role: str | None = None,
) -> dict[str, Any]:
    """Background wrapper com sessão própria e resultado estruturado."""
    from app.core.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            return await executar_backup_exclusivo(
                db,
                origem=origem,
                usuario_id=usuario_id,
                usuario_role=usuario_role,
            )
    except Exception as exc:
        logger.error(
            "[Backup] execução background falhou fora do motor (tipo=%s)",
            type(exc).__name__,
            exc_info=True,
        )
        return {
            "ok": False,
            "status": "erro",
            "origem": origem,
            "erro": "Falha operacional ao executar backup.",
        }


async def job_backup_drive_exclusivo() -> dict[str, Any] | None:
    """Job APScheduler canônico; gate BACKUP_ENABLED permanece centralizado.

    DEVOLVE o resultado estruturado (ou ``None`` quando o gate está desligado).
    O motor já converte falha em ``{"ok": False, "status": "erro"}`` em vez de
    exceção: sem devolver esse dicionário, quem monitora o job só enxerga
    "retornou sem exceção" e registraria SUCESSO num backup que falhou.
    """
    if not settings.BACKUP_ENABLED:
        logger.debug("[Backup] BACKUP_ENABLED=false — job diário pulado")
        return None
    result = await executar_backup_background_exclusivo(origem="agendado")
    if result.get("status") == "em_execucao":
        logger.info("[Backup] job diário não iniciou: outro backup já estava em curso")
    return result
