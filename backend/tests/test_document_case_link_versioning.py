"""Regressão DB-level do versionamento ao vincular documento solto."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine

    await engine.dispose()


async def test_vinculo_inicializa_grupo_de_versao_e_preserva_ocr():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.services.document_case_link_service import (
        obter_ocr_documento_vinculado,
        vincular_documento_existente,
    )

    uid = str(uuid4())
    cli = str(uuid4())
    caso = str(uuid4())
    doc = str(uuid4())

    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO users (id,email,hashed_password,full_name,role,is_active) "
                "VALUES (:id,:email,'x','Version Link','advogado',true)"
            ),
            {"id": uid, "email": f"version-{uid[:8]}@teste.local"},
        )
        await db.execute(
            text(
                "INSERT INTO clients (id,tipo,nome,email,status) "
                "VALUES (:id,'PF','Cliente versão',:email,'ativo')"
            ),
            {"id": cli, "email": f"{cli[:8]}@teste.local"},
        )
        await db.execute(
            text(
                "INSERT INTO cases "
                "(id,titulo,area,status,client_id,advogado_responsavel_id,proxima_acao) "
                "VALUES (:id,'Caso versão','civil','aberto',:cli,:uid,'Revisar')"
            ),
            {"id": caso, "cli": cli, "uid": uid},
        )
        await db.execute(
            text(
                "INSERT INTO documents "
                "(id,titulo,filename,filepath,confidencialidade,client_id,uploaded_by,ocr_text) "
                "VALUES (:id,'Documento versão',:filename,:filepath,'normal',:cli,:uid,:ocr)"
            ),
            {
                "id": doc,
                "filename": f"{doc}.pdf",
                "filepath": f"tests/{doc}.pdf",
                "cli": cli,
                "uid": uid,
                "ocr": "conteúdo OCR para análise posterior",
            },
        )
        await db.commit()

        try:
            cu = await db.get(User, uid)
            out = await vincular_documento_existente(db, cu, caso, doc)
            assert out["alterado"] is True

            row = (
                await db.execute(
                    text(
                        "SELECT case_id, versao_grupo_id FROM documents WHERE id=:id"
                    ),
                    {"id": doc},
                )
            ).one()
            assert row[0] == caso
            assert row[1] == doc
            assert (
                await obter_ocr_documento_vinculado(db, caso, doc)
                == "conteúdo OCR para análise posterior"
            )
        finally:
            await db.execute(text("DELETE FROM documents WHERE id=:id"), {"id": doc})
            await db.execute(
                text("DELETE FROM case_movimentos WHERE case_id=:id"), {"id": caso}
            )
            await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo='on'"))
            await db.execute(
                text("DELETE FROM audit_logs WHERE user_id=:id"), {"id": uid}
            )
            await db.execute(text("DELETE FROM cases WHERE id=:id"), {"id": caso})
            await db.execute(text("DELETE FROM users WHERE id=:id"), {"id": uid})
            await db.execute(text("DELETE FROM clients WHERE id=:id"), {"id": cli})
            await db.commit()
