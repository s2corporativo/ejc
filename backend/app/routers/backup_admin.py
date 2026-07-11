# ── app/routers/backup_admin.py ──────────────────────────────────────────────
# Administração do backup automatizado → Google Drive.
# Restrito a superadmin/admin; nenhuma resposta expõe segredos (.env).
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import require_roles
from app.models.audit_log import criar_audit_log
from app.models.user import User
from app.services import backup_service

logger = logging.getLogger("ejc.backup.admin")

router = APIRouter(prefix="/admin/backup", tags=["Admin / Backup"])


@router.post("/executar", status_code=202)
@limiter.limit("2/minute")
async def executar_backup_manual(
    request: Request,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin"])),
):
    """Dispara um backup manual em background e retorna 202 imediatamente.

    Decisão: o disparo manual NÃO exige BACKUP_ENABLED=true — a flag governa
    só o agendamento diário. Chave de criptografia e pasta do Drive continuam
    obrigatórias (o artefato nunca sai do VPS sem cifrar — LGPD).
    """
    cfg = backup_service.configuracao_status()
    if not cfg["chave_configurada"] or not cfg["pasta_configurada"]:
        raise HTTPException(
            status_code=503,
            detail=(
                "Backup não configurado: defina BACKUP_ENCRYPTION_KEY e "
                "BACKUP_DRIVE_FOLDER_ID no .env (ver .env.example)."
            ),
        )
    if backup_service.em_execucao():
        raise HTTPException(status_code=409, detail="Já existe um backup em andamento.")

    role = getattr(cu.role, "value", str(cu.role))
    await criar_audit_log(
        db, user_id=cu.id, user_role=role,
        acao="CREATE", entidade="backup",
        detalhes="Backup manual disparado via /admin/backup/executar",
    )
    await db.commit()

    # Sessão própria dentro da task — a sessão desta request fecha no retorno.
    asyncio.create_task(backup_service.executar_backup_background(
        origem="manual", usuario_id=cu.id, usuario_role=role,
    ))
    logger.info("[Backup] disparo manual aceito (user=%s)", cu.id)
    return {
        "aceito": True,
        "detail": "Backup iniciado em background. Acompanhe em GET /admin/backup/status.",
    }


@router.get("/status")
async def status_backup(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin"])),
):
    """Último resultado + próximo agendamento + booleans de configuração.
    Nunca retorna valores de segredos — apenas *_configurada booleans."""
    estado = await backup_service.obter_estado(db)
    return {
        "configuracao": backup_service.configuracao_status(),
        "retencao_dias": backup_service.settings.BACKUP_RETENCAO_DIAS,
        "hora_utc": "%02d:%02d" % backup_service.hora_backup_utc(),
        "em_execucao": backup_service.em_execucao(),
        "ultimo_resultado": estado,
        "proximo_agendamento": backup_service.proximo_agendamento(),
    }
