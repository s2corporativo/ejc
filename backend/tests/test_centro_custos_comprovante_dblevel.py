"""Centro de custos: comprovante precisa pertencer ao mesmo caso e ser visível."""
from __future__ import annotations

import os
from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _user(db, *, role: str = "advogado") -> str:
    uid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id,email,hashed_password,full_name,role,is_active) "
            "VALUES (:id,:email,'x','Centro Custo Teste',:role,true)"
        ),
        {"id": uid, "email": f"cc-doc-{uid[:8]}@teste.local", "role": role},
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


async def _case(db, client_id: str, user_id: str) -> str:
    case_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO cases "
            "(id,titulo,area,status,client_id,advogado_responsavel_id,proxima_acao) "
            "VALUES (:id,'Caso centro custo','civil','aberto',:cid,:uid,'Revisar')"
        ),
        {"id": case_id, "cid": client_id, "uid": user_id},
    )
    return case_id


async def _document(
    db,
    *,
    case_id: str,
    client_id: str,
    user_id: str,
    confidencialidade: str = "normal",
) -> str:
    did = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO documents "
            "(id,titulo,filename,filepath,confidencialidade,case_id,client_id,uploaded_by) "
            "VALUES (:id,'Comprovante','comprovante.pdf',:path,:conf,:case_id,:client_id,:uid)"
        ),
        {
            "id": did,
            "path": f"tests/{did}.pdf",
            "conf": confidencialidade,
            "case_id": case_id,
            "client_id": client_id,
            "uid": user_id,
        },
    )
    return did


async def _cleanup(db, *, users=(), clients=(), cases=(), documents=()):
    await db.rollback()
    await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo='on'"))
    for case_id in cases:
        await db.execute(
            text("DELETE FROM centro_custos WHERE case_id=:id"), {"id": case_id}
        )
    for document_id in documents:
        await db.execute(
            text("DELETE FROM documents WHERE id=:id"), {"id": document_id}
        )
    for user_id in users:
        await db.execute(
            text("DELETE FROM audit_logs WHERE user_id=:id"), {"id": user_id}
        )
    for case_id in cases:
        await db.execute(text("DELETE FROM cases WHERE id=:id"), {"id": case_id})
    for user_id in users:
        await db.execute(text("DELETE FROM users WHERE id=:id"), {"id": user_id})
    for client_id in clients:
        await db.execute(text("DELETE FROM clients WHERE id=:id"), {"id": client_id})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine

    await engine.dispose()


def _payload(case_id: str, document_id: str):
    from app.models.centro_custo import CentroCustoCategoria, CentroCustoTipo
    from app.routers.centro_custos import CentroCustoIn

    return CentroCustoIn(
        case_id=case_id,
        tipo=CentroCustoTipo.despesa,
        categoria=CentroCustoCategoria.custas,
        valor=123.45,
        moeda="BRL",
        descricao="Custas processuais de teste",
        data_lancamento=date(2026, 8, 10),
        pago=True,
        comprovante_id=document_id,
    )


async def test_criacao_aceita_comprovante_do_mesmo_caso_e_audita():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.routers.centro_custos import criar_lancamento

    async with AsyncSessionLocal() as db:
        uid = await _user(db)
        client_id = await _client(db, "Cliente centro custo")
        case_id = await _case(db, client_id, uid)
        document_id = await _document(
            db,
            case_id=case_id,
            client_id=client_id,
            user_id=uid,
        )
        await db.commit()
        try:
            cu = await db.get(User, uid)
            out = await criar_lancamento(_payload(case_id, document_id), db=db, cu=cu)
            assert out["case_id"] == case_id
            assert out["comprovante_id"] == document_id

            audit = (
                await db.execute(
                    text(
                        "SELECT dados_depois FROM audit_logs "
                        "WHERE user_id=:uid AND entidade='centro_custos' "
                        "AND acao='CREATE' ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"uid": uid},
                )
            ).scalar_one()
            assert audit["case_id"] == case_id
            assert audit["comprovante_id"] == document_id
            assert audit["valor"] == "123.45"
        finally:
            await _cleanup(
                db,
                users=[uid],
                clients=[client_id],
                cases=[case_id],
                documents=[document_id],
            )


async def test_criacao_rejeita_comprovante_de_outro_caso():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.routers.centro_custos import criar_lancamento

    async with AsyncSessionLocal() as db:
        uid = await _user(db)
        client_id = await _client(db, "Cliente cross case")
        case_a = await _case(db, client_id, uid)
        case_b = await _case(db, client_id, uid)
        document_id = await _document(
            db,
            case_id=case_b,
            client_id=client_id,
            user_id=uid,
        )
        await db.commit()
        try:
            cu = await db.get(User, uid)
            with pytest.raises(HTTPException) as exc:
                await criar_lancamento(_payload(case_a, document_id), db=db, cu=cu)
            assert exc.value.status_code == 400
            assert "não pertence ao caso" in str(exc.value.detail)
            total = (
                await db.execute(
                    text("SELECT count(*) FROM centro_custos WHERE case_id=:id"),
                    {"id": case_a},
                )
            ).scalar_one()
            assert total == 0
        finally:
            await _cleanup(
                db,
                users=[uid],
                clients=[client_id],
                cases=[case_a, case_b],
                documents=[document_id],
            )


async def test_advogado_nao_pode_usar_comprovante_do_cofre():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.routers.centro_custos import criar_lancamento

    async with AsyncSessionLocal() as db:
        uid = await _user(db, role="advogado")
        client_id = await _client(db, "Cliente cofre")
        case_id = await _case(db, client_id, uid)
        document_id = await _document(
            db,
            case_id=case_id,
            client_id=client_id,
            user_id=uid,
            confidencialidade="confidencial",
        )
        await db.commit()
        try:
            cu = await db.get(User, uid)
            with pytest.raises(HTTPException) as exc:
                await criar_lancamento(_payload(case_id, document_id), db=db, cu=cu)
            assert exc.value.status_code == 403
            total = (
                await db.execute(
                    text("SELECT count(*) FROM centro_custos WHERE case_id=:id"),
                    {"id": case_id},
                )
            ).scalar_one()
            assert total == 0
        finally:
            await _cleanup(
                db,
                users=[uid],
                clients=[client_id],
                cases=[case_id],
                documents=[document_id],
            )
