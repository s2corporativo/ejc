"""Invariante de reabertura de Case nos fluxos ORM canônicos."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def test_desarquivar_limpa_desfecho_e_metadados_terminais():
    from app.core.database import AsyncSessionLocal
    from app.models.case import CaseStatus
    from app.models.user import User
    from app.routers.cases import desarquivar_caso

    uid, client_id, case_id = str(uuid4()), str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO users (id,email,hashed_password,full_name,role,is_active) "
                "VALUES (:id,:email,'x','Sócio Reabertura','socio',true)"
            ),
            {"id": uid, "email": f"reab-{uid[:8]}@teste.local"},
        )
        await db.execute(
            text(
                "INSERT INTO clients (id,tipo,nome,email,status) "
                "VALUES (:id,'PF','Cliente Reabertura',:email,'ativo')"
            ),
            {"id": client_id, "email": f"{client_id[:8]}@teste.local"},
        )
        await db.execute(
            text(
                "INSERT INTO cases (id,titulo,area,status,client_id,advogado_responsavel_id,"
                "proxima_acao,archived_at,archive_reason,data_encerramento,resultado,"
                "motivo_resultado,provas_determinantes,licoes_aprendidas) VALUES "
                "(:id,'Caso Reabertura','civil','arquivado',:cid,:uid,'Revisar',:agora,"
                "'Arquivado após encerramento',:agora,'exito_total','Acordo',"
                "'Contrato','Documentar cedo')"
            ),
            {
                "id": case_id,
                "cid": client_id,
                "uid": uid,
                "agora": datetime.now(timezone.utc),
            },
        )
        await db.commit()
        try:
            cu = (await db.execute(select(User).where(User.id == uid))).scalar_one()
            caso = await desarquivar_caso(
                case_id=case_id,
                background=BackgroundTasks(),
                db=db,
                cu=cu,
            )
            assert caso.status == CaseStatus.aberto
            assert caso.archived_at is None
            assert caso.archive_reason is None
            assert caso.data_encerramento is None
            assert caso.resultado is None
            assert caso.motivo_resultado is None
            assert caso.provas_determinantes is None
            assert caso.licoes_aprendidas is None
        finally:
            await db.execute(text("DELETE FROM case_movimentos WHERE case_id=:id"), {"id": case_id})
            await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo='on'"))
            await db.execute(text("DELETE FROM audit_logs WHERE user_id=:id"), {"id": uid})
            await db.execute(text("DELETE FROM cases WHERE id=:id"), {"id": case_id})
            await db.execute(text("DELETE FROM users WHERE id=:id"), {"id": uid})
            await db.execute(text("DELETE FROM clients WHERE id=:id"), {"id": client_id})
            await db.commit()
