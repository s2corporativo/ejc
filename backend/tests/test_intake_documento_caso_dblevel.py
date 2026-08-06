"""Item 4.2 — Importação Inteligente: o documento fica VINCULADO ao caso (ROW-LEVEL).

A correção do item 4.2 é o frontend reenviar o arquivo analisado para
POST /documents/upload com o case_id do caso recém-criado. Este teste valida o
contrato de backend do qual essa correção depende, contra Postgres REAL: chamar o
handler upload() com um case_id persiste um Document e o VINCULA ao caso (aparece
na listagem de documentos do caso). Antes, o fluxo de IA só analisava e descartava
o arquivo — a aba Documentos ficava em "Documentos (0)".

Mesmo gate de CI dos demais *_dblevel.py (RUN_DB_TESTS=1). Sem Postgres, pula.

Notas de isolamento (para não quebrar outros *_dblevel):
- UPLOAD_DIR aponta para tmp_path (o padrão /app/uploads não é gravável no runner).
- usa um engine DEDICADO com NullPool, descartado ao fim, para não deixar conexão
  no pool async compartilhado ligada ao event loop deste teste.
"""
from __future__ import annotations

import io
import os
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, UploadFile
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from starlette.datastructures import Headers

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


def _upload_pdf(nome="peticao_importada.pdf") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(b"%PDF-1.4 conteudo de teste do intake"),
        filename=nome,
        headers=Headers({"content-type": "application/pdf"}),
    )


async def test_upload_com_case_id_vincula_documento_ao_caso(monkeypatch, tmp_path):
    from app.core.config import get_settings
    from app.models.user import User, UserRole
    from app.models.document import Document
    import app.routers.documents as documents

    # Determinismo: sem libmagic (valida como PDF), sem OCR do PDF falso, e
    # UPLOAD_DIR gravável (o default /app/uploads não é gravável no CI runner).
    monkeypatch.setattr(documents.settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(documents, "_validar_conteudo",
                        lambda ext, conteudo: "application/pdf")
    monkeypatch.setattr(documents, "extrair_texto", lambda *a, **k: None)

    uid = str(uuid4())
    client_id = str(uuid4())
    case_id = str(uuid4())

    # Engine dedicado (NullPool + dispose): teste hermético, não contamina o pool
    # async compartilhado que o próximo *_dblevel usaria.
    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as db:
            try:
                # ── Setup: usuário socio (dono do caso), cliente e caso ──────
                await db.execute(text(
                    "INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
                    "VALUES (:id, :email, 'x', 'Socio Intake 4.2', 'socio', true)"
                ), {"id": uid, "email": f"intake-{uid[:8]}@teste.local"})
                await db.execute(text(
                    "INSERT INTO clients (id, tipo, nome, email, status) "
                    "VALUES (:id, 'PF', 'Cliente Intake 4.2', :email, 'ativo')"
                ), {"id": client_id, "email": f"{client_id[:8]}@teste.local"})
                await db.execute(text(
                    "INSERT INTO cases (id, titulo, area, status, client_id, advogado_responsavel_id) "
                    "VALUES (:id, 'Caso Intake 4.2', 'civil', 'aberto', :cid, :uid)"
                ), {"id": case_id, "cid": client_id, "uid": uid})
                await db.commit()

                cu = User(id=uid, role=UserRole.socio)

                # ── Ação: reenvio do arquivo à GED com o case_id (o que o front faz) ──
                resp = await documents.upload(
                    background_tasks=BackgroundTasks(),
                    file=_upload_pdf(),
                    titulo="Peticao importada (IA)",
                    tipo=None,
                    confidencialidade="normal",
                    case_id=case_id,
                    client_id=client_id,
                    db=db,
                    cu=cu,
                )
                assert resp["detail"] == "Documento enviado"
                doc_id = resp["id"]

                # ── Verificação: Document persistido e VINCULADO ao caso ─────
                doc = (await db.execute(
                    select(Document).where(Document.id == doc_id)
                )).scalar_one_or_none()
                assert doc is not None
                assert doc.case_id == case_id           # vínculo caso<->documento
                assert doc.client_id == client_id
                assert doc.uploaded_by == uid
                assert doc.titulo == "Peticao importada (IA)"

                # Aparece na listagem de documentos do caso (o que a aba Documentos lê).
                do_caso = (await db.execute(
                    select(Document).where(
                        Document.case_id == case_id,
                        Document.deleted_at.is_(None),
                    )
                )).scalars().all()
                assert doc_id in [d.id for d in do_caso]
            finally:
                # Limpeza (ordem de FK): documentos, movimentos, audit_logs,
                # caso, cliente, user. O upload com case_id agora dispara a
                # transição automática de estado (status_transicao), que grava
                # um CaseMovimento — sem apagá-lo o DELETE do caso viola FK.
                await db.execute(text("DELETE FROM documents WHERE case_id = :c"), {"c": case_id})
                await db.execute(text("DELETE FROM case_movimentos WHERE case_id = :c"), {"c": case_id})
                await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
                await db.execute(text("DELETE FROM audit_logs WHERE user_id = :u"), {"u": uid})
                await db.execute(text("DELETE FROM cases WHERE id = :c"), {"c": case_id})
                await db.execute(text("DELETE FROM clients WHERE id = :c"), {"c": client_id})
                await db.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
                await db.commit()
    finally:
        await engine.dispose()
        # arquivo gravado fica em tmp_path (limpo automaticamente pelo pytest).
