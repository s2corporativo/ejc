"""Regressão: conflitos de vínculo não revelam metadados de peça."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
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


async def test_conflito_de_protocolo_usa_mensagem_generica():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.services.document_case_link_service import vincular_documento_existente

    uid = str(uuid4())
    cli = str(uuid4())
    caso = str(uuid4())
    doc = str(uuid4())
    legal_doc = str(uuid4())
    titulo_reservado = "Titulo interno de outra peca"

    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO users (id,email,hashed_password,full_name,role,is_active) "
                "VALUES (:id,:email,'x','Metadata Link','advogado',true)"
            ),
            {"id": uid, "email": f"metadata-{uid[:8]}@teste.local"},
        )
        await db.execute(
            text(
                "INSERT INTO clients (id,tipo,nome,email,status) "
                "VALUES (:id,'PF','Cliente metadata',:email,'ativo')"
            ),
            {"id": cli, "email": f"{cli[:8]}@teste.local"},
        )
        await db.execute(
            text(
                "INSERT INTO cases "
                "(id,titulo,area,status,client_id,advogado_responsavel_id,proxima_acao) "
                "VALUES (:id,'Caso metadata','civil','aberto',:cli,:uid,'Revisar')"
            ),
            {"id": caso, "cli": cli, "uid": uid},
        )
        await db.execute(
            text(
                "INSERT INTO documents "
                "(id,titulo,filename,filepath,confidencialidade,client_id,uploaded_by) "
                "VALUES (:id,'Documento metadata',:filename,:filepath,'normal',:cli,:uid)"
            ),
            {
                "id": doc,
                "filename": f"{doc}.pdf",
                "filepath": f"tests/{doc}.pdf",
                "cli": cli,
                "uid": uid,
            },
        )
        await db.execute(
            text(
                "INSERT INTO legal_docs "
                "(id,titulo,tipo_peca,status,conteudo,case_id,"
                "protocolo_comprovante_doc_id,ai_generated,human_reviewed) "
                "VALUES (:id,:titulo,'outro','protocolada','conteudo',:case_id,:doc,false,true)"
            ),
            {
                "id": legal_doc,
                "titulo": titulo_reservado,
                "case_id": caso,
                "doc": doc,
            },
        )
        await db.commit()

        try:
            cu = await db.get(User, uid)
            with pytest.raises(HTTPException) as exc:
                await vincular_documento_existente(db, cu, caso, doc)
            assert exc.value.status_code == 409
            assert titulo_reservado not in str(exc.value.detail)
            assert "comprovante de protocolo" in str(exc.value.detail).lower()
        finally:
            await db.rollback()
            await db.execute(
                text("DELETE FROM legal_docs WHERE id=:id"), {"id": legal_doc}
            )
            await db.execute(text("DELETE FROM documents WHERE id=:id"), {"id": doc})
            await db.execute(text("DELETE FROM cases WHERE id=:id"), {"id": caso})
            await db.execute(text("DELETE FROM users WHERE id=:id"), {"id": uid})
            await db.execute(text("DELETE FROM clients WHERE id=:id"), {"id": cli})
            await db.commit()
