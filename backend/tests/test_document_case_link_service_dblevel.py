"""Vínculo de documento existente ao caso — gates e efeitos de domínio."""
from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _user(db, role: str = "advogado") -> str:
    uid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id,email,hashed_password,full_name,role,is_active) "
            "VALUES (:id,:email,'x','Doc Link',:role,true)"
        ),
        {"id": uid, "email": f"doc-link-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _client(db, nome: str) -> str:
    cid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO clients (id,tipo,nome,email,status) "
            "VALUES (:id,'PF',:nome,:email,'ativo')"
        ),
        {"id": cid, "nome": nome, "email": f"{cid[:8]}@teste.local"},
    )
    return cid


async def _case(db, client_id: str, user_id: str, *, status: str = "aberto") -> str:
    case_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO cases (id,titulo,area,status,client_id,advogado_responsavel_id,proxima_acao) "
            f"VALUES (:id,'Caso documento','civil','{status}',:cid,:uid,'Revisar documento')"
        ),
        {"id": case_id, "cid": client_id, "uid": user_id},
    )
    return case_id


async def _document(
    db,
    *,
    client_id: str | None,
    uploaded_by: str,
    case_id: str | None = None,
    titulo: str = "Documento teste",
) -> str:
    did = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO documents "
            "(id,titulo,filename,filepath,confidencialidade,client_id,case_id,uploaded_by) "
            "VALUES (:id,:titulo,:filename,:filepath,'normal',:cid,:case_id,:uid)"
        ),
        {
            "id": did,
            "titulo": titulo,
            "filename": f"{did}.pdf",
            "filepath": f"tests/{did}.pdf",
            "cid": client_id,
            "case_id": case_id,
            "uid": uploaded_by,
        },
    )
    return did


async def _legal_doc_comprovante(db, *, case_id: str, document_id: str) -> str:
    lid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO legal_docs "
            "(id,titulo,tipo_peca,status,conteudo,case_id,protocolo_comprovante_doc_id,"
            "ai_generated,human_reviewed) VALUES "
            "(:id,'Peça protocolada','outro','protocolada','conteúdo',:case_id,:doc,false,true)"
        ),
        {"id": lid, "case_id": case_id, "doc": document_id},
    )
    return lid


async def _prova(db, *, case_id: str, document_id: str) -> str:
    pid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO provas "
            "(id,case_id,tipo,titulo,document_id,ordem) "
            "VALUES (:id,:case_id,'documental','Prova vinculada',:doc,0)"
        ),
        {"id": pid, "case_id": case_id, "doc": document_id},
    )
    return pid


async def _cleanup(
    db,
    *,
    users=(),
    clients=(),
    cases=(),
    documents=(),
    legal_docs=(),
    provas=(),
):
    for pid in provas:
        await db.execute(text("DELETE FROM provas WHERE id=:id"), {"id": pid})
    for lid in legal_docs:
        await db.execute(text("DELETE FROM legal_docs WHERE id=:id"), {"id": lid})
    for did in documents:
        await db.execute(text("DELETE FROM documents WHERE id=:id"), {"id": did})
    for cid in cases:
        await db.execute(text("DELETE FROM case_movimentos WHERE case_id=:id"), {"id": cid})
    await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo='on'"))
    for uid in users:
        await db.execute(text("DELETE FROM audit_logs WHERE user_id=:id"), {"id": uid})
    for cid in cases:
        await db.execute(text("DELETE FROM cases WHERE id=:id"), {"id": cid})
    for uid in users:
        await db.execute(text("DELETE FROM users WHERE id=:id"), {"id": uid})
    for cid in clients:
        await db.execute(text("DELETE FROM clients WHERE id=:id"), {"id": cid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine

    await engine.dispose()


async def test_vinculo_e_status_atomicos_e_auditados():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.services.document_case_link_service import vincular_documento_existente

    async with AsyncSessionLocal() as db:
        uid = await _user(db)
        cli = await _client(db, "Cliente vínculo")
        caso = await _case(db, cli, uid, status="aberto")
        doc = await _document(db, client_id=cli, uploaded_by=uid)
        await db.commit()
        try:
            cu = await db.get(User, uid)
            out = await vincular_documento_existente(db, cu, caso, doc)
            assert out["alterado"] is True
            assert out["status_caso_avancou"] is True

            row = (
                await db.execute(
                    text("SELECT case_id, client_id FROM documents WHERE id=:id"),
                    {"id": doc},
                )
            ).one()
            assert row[0] == caso
            assert row[1] == cli
            status = (
                await db.execute(
                    text("SELECT status FROM cases WHERE id=:id"), {"id": caso}
                )
            ).scalar_one()
            assert status == "em_instrucao"
            assert (
                await db.execute(
                    text(
                        "SELECT count(*) FROM case_movimentos "
                        "WHERE case_id=:id AND descricao LIKE '%documento_vinculado%'"
                    ),
                    {"id": caso},
                )
            ).scalar_one() == 1
            audit = (
                await db.execute(
                    text(
                        "SELECT dados_depois FROM audit_logs "
                        "WHERE user_id=:uid AND entidade='documents' AND registro_id=:doc "
                        "AND acao='VINCULAR' ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"uid": uid, "doc": doc},
                )
            ).scalar_one()
            assert audit["case_id_origem"] is None
            assert audit["case_id_destino"] == caso
            assert audit["status_caso_avancou"] is True
        finally:
            await _cleanup(db, users=[uid], clients=[cli], cases=[caso], documents=[doc])


async def test_cross_client_e_negado():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.services.document_case_link_service import vincular_documento_existente

    async with AsyncSessionLocal() as db:
        uid = await _user(db)
        cli1 = await _client(db, "Cliente A")
        cli2 = await _client(db, "Cliente B")
        caso = await _case(db, cli1, uid)
        doc = await _document(db, client_id=cli2, uploaded_by=uid)
        await db.commit()
        try:
            cu = await db.get(User, uid)
            with pytest.raises(HTTPException) as exc:
                await vincular_documento_existente(db, cu, caso, doc)
            assert exc.value.status_code == 400
            assert "outro cliente" in str(exc.value.detail).lower()
        finally:
            await db.rollback()
            await _cleanup(
                db,
                users=[uid],
                clients=[cli1, cli2],
                cases=[caso],
                documents=[doc],
            )


async def test_documento_de_outro_caso_sem_acesso_nao_vaza_existencia():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.services.document_case_link_service import vincular_documento_existente

    async with AsyncSessionLocal() as db:
        u1 = await _user(db)
        u2 = await _user(db)
        cli = await _client(db, "Cliente origem")
        destino = await _case(db, cli, u1)
        origem = await _case(db, cli, u2)
        doc = await _document(db, client_id=cli, uploaded_by=u2, case_id=origem)
        await db.commit()
        try:
            cu = await db.get(User, u1)
            with pytest.raises(HTTPException) as exc:
                await vincular_documento_existente(db, cu, destino, doc)
            assert exc.value.status_code == 403
            atual = (
                await db.execute(
                    text("SELECT case_id FROM documents WHERE id=:id"), {"id": doc}
                )
            ).scalar_one()
            assert atual == origem
        finally:
            await db.rollback()
            await _cleanup(
                db,
                users=[u1, u2],
                clients=[cli],
                cases=[destino, origem],
                documents=[doc],
            )


async def test_documento_de_outro_caso_nao_pode_ser_movido_mesmo_com_acesso():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.services.document_case_link_service import vincular_documento_existente

    async with AsyncSessionLocal() as db:
        uid = await _user(db)
        cli = await _client(db, "Cliente imutável")
        origem = await _case(db, cli, uid)
        destino = await _case(db, cli, uid)
        doc = await _document(db, client_id=None, uploaded_by=uid, case_id=origem)
        await db.commit()
        try:
            cu = await db.get(User, uid)
            with pytest.raises(HTTPException) as exc:
                await vincular_documento_existente(db, cu, destino, doc)
            assert exc.value.status_code == 409
            assert "não pode ser movido" in str(exc.value.detail).lower()
            row = (
                await db.execute(
                    text("SELECT case_id, client_id FROM documents WHERE id=:id"),
                    {"id": doc},
                )
            ).one()
            assert row[0] == origem
            assert row[1] is None
        finally:
            await db.rollback()
            await _cleanup(
                db,
                users=[uid],
                clients=[cli],
                cases=[origem, destino],
                documents=[doc],
            )


async def test_comprovante_de_protocolo_nao_e_candidato_nem_vinculavel():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.services.document_case_link_service import (
        buscar_documentos_vinculaveis,
        vincular_documento_existente,
    )

    async with AsyncSessionLocal() as db:
        uid = await _user(db, "socio")
        cli = await _client(db, "Cliente protocolo")
        destino = await _case(db, cli, uid)
        doc = await _document(
            db,
            client_id=cli,
            uploaded_by=uid,
            titulo="Comprovante candidato",
        )
        lid = await _legal_doc_comprovante(db, case_id=destino, document_id=doc)
        await db.commit()
        try:
            cu = await db.get(User, uid)
            busca = await buscar_documentos_vinculaveis(
                db, cu, destino, search="Comprovante candidato"
            )
            assert busca["total"] == 0

            with pytest.raises(HTTPException) as exc:
                await vincular_documento_existente(db, cu, destino, doc)
            assert exc.value.status_code == 409
            assert "comprovante" in str(exc.value.detail).lower()
        finally:
            await db.rollback()
            await _cleanup(
                db,
                users=[uid],
                clients=[cli],
                cases=[destino],
                documents=[doc],
                legal_docs=[lid],
            )


async def test_documento_de_prova_ativa_nao_e_candidato_nem_vinculavel():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.services.document_case_link_service import (
        buscar_documentos_vinculaveis,
        vincular_documento_existente,
    )

    async with AsyncSessionLocal() as db:
        uid = await _user(db, "socio")
        cli = await _client(db, "Cliente prova")
        destino = await _case(db, cli, uid)
        doc = await _document(
            db,
            client_id=cli,
            uploaded_by=uid,
            titulo="Documento de prova",
        )
        prova = await _prova(db, case_id=destino, document_id=doc)
        await db.commit()
        try:
            cu = await db.get(User, uid)
            busca = await buscar_documentos_vinculaveis(
                db, cu, destino, search="Documento de prova"
            )
            assert busca["total"] == 0

            with pytest.raises(HTTPException) as exc:
                await vincular_documento_existente(db, cu, destino, doc)
            assert exc.value.status_code == 409
            assert "prova" in str(exc.value.detail).lower()
        finally:
            await db.rollback()
            await _cleanup(
                db,
                users=[uid],
                clients=[cli],
                cases=[destino],
                documents=[doc],
                provas=[prova],
            )


async def test_busca_filtra_inelegiveis_antes_da_paginacao():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.services.document_case_link_service import buscar_documentos_vinculaveis

    async with AsyncSessionLocal() as db:
        uid = await _user(db, "socio")
        cli = await _client(db, "Cliente busca")
        outro_cli = await _client(db, "Outro cliente busca")
        caso = await _case(db, cli, uid)
        outro_caso = await _case(db, cli, uid)
        vinculado = await _document(
            db,
            client_id=cli,
            uploaded_by=uid,
            case_id=outro_caso,
            titulo="Mesmo termo",
        )
        cross = await _document(
            db,
            client_id=outro_cli,
            uploaded_by=uid,
            titulo="Mesmo termo",
        )
        protocolo = await _document(
            db,
            client_id=cli,
            uploaded_by=uid,
            titulo="Mesmo termo",
        )
        livre = await _document(
            db,
            client_id=cli,
            uploaded_by=uid,
            titulo="Mesmo termo",
        )
        lid = await _legal_doc_comprovante(db, case_id=caso, document_id=protocolo)
        await db.commit()
        try:
            cu = await db.get(User, uid)
            out = await buscar_documentos_vinculaveis(
                db, cu, caso, search="Mesmo termo", page=1, page_size=1
            )
            assert out["total"] == 1
            assert [d["id"] for d in out["data"]] == [livre]
        finally:
            await _cleanup(
                db,
                users=[uid],
                clients=[cli, outro_cli],
                cases=[caso, outro_caso],
                documents=[vinculado, cross, protocolo, livre],
                legal_docs=[lid],
            )


async def test_concorrencia_no_mesmo_caso_gera_uma_unica_transicao():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.services.document_case_link_service import vincular_documento_existente

    async with AsyncSessionLocal() as db:
        uid = await _user(db, "socio")
        cli = await _client(db, "Cliente concorrência")
        caso = await _case(db, cli, uid, status="aberto")
        doc1 = await _document(db, client_id=cli, uploaded_by=uid)
        doc2 = await _document(db, client_id=cli, uploaded_by=uid)
        await db.commit()

    async def _vincular(doc_id: str):
        async with AsyncSessionLocal() as sessao:
            cu = await sessao.get(User, uid)
            return await vincular_documento_existente(sessao, cu, caso, doc_id)

    try:
        r1, r2 = await asyncio.gather(_vincular(doc1), _vincular(doc2))
        assert sorted([r1["status_caso_avancou"], r2["status_caso_avancou"]]) == [
            False,
            True,
        ]

        async with AsyncSessionLocal() as check:
            assert (
                await check.execute(
                    text(
                        "SELECT count(*) FROM case_movimentos "
                        "WHERE case_id=:id AND descricao LIKE '%documento_vinculado%'"
                    ),
                    {"id": caso},
                )
            ).scalar_one() == 1
            assert (
                await check.execute(
                    text("SELECT count(*) FROM documents WHERE id IN (:d1,:d2) AND case_id=:case_id"),
                    {"d1": doc1, "d2": doc2, "case_id": caso},
                )
            ).scalar_one() == 2
    finally:
        async with AsyncSessionLocal() as cleanup:
            await _cleanup(
                cleanup,
                users=[uid],
                clients=[cli],
                cases=[caso],
                documents=[doc1, doc2],
            )
