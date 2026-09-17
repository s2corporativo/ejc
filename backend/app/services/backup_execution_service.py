"""Fachada operacional do backup canônico com exclusão cross-process.

Regra arquitetural:
    callers -> backup_execution_service -> backup_lock -> backup_service

`backup_service` continua responsável por dump/cifragem/offsite/auditoria. Esta
fachada é a única entrada operacional e não duplica regra de negócio do motor.
Também concentra invariantes do storage compartilhado que precisam valer ANTES
e DEPOIS do motor, enquanto o mutex cross-process está adquirido.
"""
from __future__ import annotations

import logging
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services import backup_service
from app.services.backup_lock import (
    BackupAlreadyRunning,
    BackupLockError,
    acquire_backup_lock,
    open_backup_dir_fd,
)

logger = logging.getLogger("ejc.backup.execution")
settings = get_settings()

BackupLockStatus = Literal["livre", "ocupado", "indisponivel"]

_CANONICAL_LOCAL_RE = re.compile(
    r"^ejc_backup_(?P<ts>\d{8}T\d{6}Z)_.+\.enc$"
)
_CANONICAL_TMP_RE = re.compile(
    r"^\.ejc_backup_\d{8}T\d{6}Z_.+\.enc\.\d+\.\d+\.tmp$"
)


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


def _storage_error_result(origem: str, status: str = "erro_storage") -> dict[str, Any]:
    return {
        "ok": False,
        "status": status,
        "origem": origem,
        "erro": "O storage local de continuidade não passou nas validações de segurança.",
    }


def _retencao_local_validada() -> int:
    """Retorna a retenção local ou falha fechado para configuração inválida."""
    try:
        dias = int(settings.BACKUP_RETENTION_DAYS)
    except (TypeError, ValueError) as exc:
        raise ValueError("BACKUP_RETENTION_DAYS deve ser inteiro >= 1") from exc
    if dias < 1:
        raise ValueError("BACKUP_RETENTION_DAYS deve ser >= 1")
    return dias


def _cleanup_temporarios_locais_sync(backup_dir: str) -> int:
    """Remove somente temporários canônicos deixados por uma tentativa anterior.

    A chamada ocorre com o mutex global adquirido, portanto não há escritor
    legítimo concorrente. Symlinks e nomes fora do contrato são preservados.
    """
    dir_fd = open_backup_dir_fd(backup_dir)
    removidos = 0
    try:
        for nome in os.listdir(dir_fd):
            if not _CANONICAL_TMP_RE.fullmatch(nome):
                continue
            try:
                st = os.stat(nome, dir_fd=dir_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            os.unlink(nome, dir_fd=dir_fd)
            removidos += 1
        if removidos:
            os.fsync(dir_fd)
        return removidos
    finally:
        os.close(dir_fd)


def _pre_rotacionar_local_sync(
    backup_dir: str,
    retencao_dias: int,
    *,
    agora: datetime | None = None,
) -> int:
    """Libera conjuntos expirados ANTES de persistir o próximo backup.

    Preserva sempre o grupo temporal canônico mais recente. Se todos os backups
    existentes estiverem expirados, o último conjunto conhecido continua
    disponível até que o novo conjunto seja publicado com sucesso; a rotação
    pós-backup do motor pode removê-lo depois disso.
    """
    if retencao_dias < 1:
        raise ValueError("BACKUP_RETENTION_DAYS deve ser >= 1")

    dir_fd = open_backup_dir_fd(backup_dir)
    try:
        candidatos: list[tuple[str, str, float]] = []
        for nome in os.listdir(dir_fd):
            match = _CANONICAL_LOCAL_RE.fullmatch(nome)
            if not match:
                continue
            try:
                st = os.stat(nome, dir_fd=dir_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            candidatos.append((nome, match.group("ts"), st.st_mtime))

        if not candidatos:
            return 0

        newest_group = max(ts for _nome, ts, _mtime in candidatos)
        corte = (agora or datetime.now(timezone.utc)) - timedelta(days=retencao_dias)
        corte_ts = corte.timestamp()
        removidos = 0
        for nome, grupo, mtime in candidatos:
            if grupo == newest_group:
                continue
            if mtime < corte_ts:
                os.unlink(nome, dir_fd=dir_fd)
                removidos += 1
        if removidos:
            os.fsync(dir_fd)
        return removidos
    finally:
        os.close(dir_fd)


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


def em_execucao_global() -> bool:
    """Estado best-effort para UI; combina mutex global e fast-path local."""
    if backup_service.em_execucao():
        return True
    return status_mutex_backup() == "ocupado"


async def executar_backup_exclusivo(
    db: AsyncSession,
    *,
    origem: str = "agendado",
    usuario_id: str | None = None,
    usuario_role: str | None = None,
) -> dict[str, Any]:
    """Executa o motor canônico somente após adquirir o mutex compartilhado.

    Além da exclusão mútua, esta fachada valida a retenção antes de qualquer
    dump, remove temporários canônicos de tentativas falhas e faz pré-rotação
    segura para evitar deadlock de ENOSPC. O conjunto local mais recente nunca
    é apagado na pré-rotação.
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

    resultado: dict[str, Any] | None = None
    try:
        try:
            retencao = _retencao_local_validada()
            temporarios_pre = _cleanup_temporarios_locais_sync(settings.BACKUP_DIR)
            pre_rotacao = _pre_rotacionar_local_sync(
                settings.BACKUP_DIR,
                retencao,
            )
        except ValueError as exc:
            logger.error(
                "[Backup] configuração de retenção inválida; execução bloqueada (origem=%s, tipo=%s)",
                origem,
                type(exc).__name__,
            )
            return _storage_error_result(origem, "erro_configuracao")
        except Exception as exc:
            logger.error(
                "[Backup] preflight do storage falhou; execução bloqueada (origem=%s, tipo=%s)",
                origem,
                type(exc).__name__,
            )
            return _storage_error_result(origem)

        resultado = await backup_service.executar_backup(
            db,
            origem=origem,
            usuario_id=usuario_id,
            usuario_role=usuario_role,
        )
        if pre_rotacao:
            resultado["pre_rotacao_local_removidos"] = pre_rotacao
        if temporarios_pre:
            resultado["temporarios_locais_saneados"] = temporarios_pre
        return resultado
    finally:
        # Se copy/fsync falhar no motor antes que ele registre o nome temporário
        # para cleanup, esta varredura remove o resíduo ainda sob o mesmo mutex.
        # Falha de cleanup não mascara o resultado original; é registrada e,
        # quando o ciclo foi bem-sucedido, vira aviso operacional explícito.
        try:
            temporarios_pos = _cleanup_temporarios_locais_sync(settings.BACKUP_DIR)
            if resultado is not None and temporarios_pos:
                resultado["temporarios_locais_saneados_pos"] = temporarios_pos
        except Exception as exc:
            logger.error(
                "[Backup] cleanup pós-execução falhou (origem=%s, tipo=%s)",
                origem,
                type(exc).__name__,
            )
            if resultado is not None and bool(resultado.get("ok")):
                avisos = resultado.setdefault("avisos", [])
                avisos.append("cleanup de temporário local requer verificação operacional")
                if resultado.get("status") == "sucesso":
                    resultado["status"] = "parcial"
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
