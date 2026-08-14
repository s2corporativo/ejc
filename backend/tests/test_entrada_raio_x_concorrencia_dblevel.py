"""Regressões P1 de concorrência da Entrada Única e do Raio-X.

Estes cenários dependem de ``SELECT ... FOR UPDATE`` real. SQLite ignora a
semântica de row lock e portanto não é uma prova válida. A suíte CI com
PostgreSQL executa o arquivo quando ``RUN_DB_TESTS=1``.
"""
from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.models.case import Case
from app.models.document import Document
from app.models.document_intake import DocumentIntakeBatch, DocumentIntakeItem
from app.models.raio_x import RaioXAnalise
from app.models.user import User
from app.schemas.entrada import CriarCasoEntradaRequest
from app.schemas.raio_x import RaioXConverterRequest
from app.services.entrada_service import criar_caso_do_rascunho
from app.services.raio_x_service import converter_em_caso

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer PostgreSQL com row locking real (RUN_DB_TESTS=1)",
)


async def _criar_advogado(db, *, prefixo: str) -> str:
    user_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
            "VALUES (:id, :email, 'x', 'Advogado Concorrência', 'advogado', true)"
        ),
        {"id": user_id, "email": f"{prefixo}-{user_id[:8]}@teste.local"},
    )
    return user_id


async def _criar_cliente_e_caso_externo(db, *, user_id: str) -> tuple[str, str]:
    client_id = str(uuid4())
    case_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO clients (id, tipo, nome, email, status, responsavel_id) "
            "VALUES (:id, 'PF', 'Cliente Externo da Corrida', :email, 'ativo', :resp)"
        ),
        {
            "id": client_id,
            "email": f"cliente-{client_id[:8]}@teste.local",
            "resp": user_id,
        },
    )
    await db.execute(
        text(
            "INSERT INTO cases (id, titulo, area, status, client_id, "
            "advogado_responsavel_id, proxima_acao) VALUES "
            "(:id, 'Caso externo da corrida', 'civil', 'aberto', :cid, :resp, "
            "'Revisar caso externo')"
        ),
        {"id": case_id, "cid": client_id, "resp": user_id},
    )
    return client_id, case_id


async def _semear_entrada() -> tuple[str, str, str, str, str]:
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "DELETE FROM case_intelligence_snapshots "
                "WHERE case_id IN (SELECT id FROM cases "
                "WHERE titulo = 'Caso concorrente da Entrada')"
            )
        )
        await db.execute(
            text(
                "DELETE FROM document_intake_items WHERE batch_id IN "
                "(SELECT id FROM document_intake_batches WHERE resultado::text LIKE '%entrada_unica%')"
            )
        )
        await db.execute(
            text(
                "DELETE FROM document_intake_batches WHERE resultado::text LIKE '%entrada_unica%'"
            )
        )
        await db.execute(text("DELETE FROM documents WHERE titulo = 'Documento disputado'"))
        await db.execute(
            text(
                "DELETE FROM cases WHERE titulo IN "
                "('Caso concorrente da Entrada', 'Caso externo da corrida')"
            )
        )
        await db.execute(
            text("DELETE FROM clients WHERE nome = 'Cliente Externo da Corrida'")
        )
        await db.commit()
        user_id = await _criar_advogado(db, prefixo="entrada-race")
        external_client_id, external_case_id = await _criar_cliente_e_caso_externo(
            db, user_id=user_id
        )
        batch_id = str(uuid4())
        doc_id = str(uuid4())
        db.add(
            DocumentIntakeBatch(
                id=batch_id,
                status="concluido",
                created_by=user_id,
                document_count=1,
                resultado={"entrada_unica": {"rascunho_id": batch_id}},
            )
        )
        db.add(
            Document(
                id=doc_id,
                titulo="Documento disputado",
                filename="disputado.pdf",
                filepath=f"tests/{doc_id}.pdf",
            )
        )
        await db.flush()
        db.add(
            DocumentIntakeItem(
                id=str(uuid4()),
                batch_id=batch_id,
                document_id=doc_id,
                filename="disputado.pdf",
                original_filename="disputado.pdf",
                extension=".pdf",
                size_bytes=10,
                sha256="a" * 64,
            )
        )
        await db.commit()
        return user_id, external_client_id, external_case_id, batch_id, doc_id


def _payload_entrada(*, user_id: str, doc_id: str) -> CriarCasoEntradaRequest:
    return CriarCasoEntradaRequest(
        cliente={"novo_nome": f"Cliente Novo {uuid4().hex[:8]}"},
        area="civil",
        titulo="Caso concorrente da Entrada",
        fatos="Fatos confirmados pelo advogado.",
        documentos_ids=[doc_id],
        advogado_responsavel_id=user_id,
        confirmo_dados_revisados=True,
        duplicate_confirmed=True,
        conflict_confirmed=True,
    )


@pytest.mark.anyio
async def test_entrada_revalida_documento_sob_lock_antes_de_vincular():
    """Outro fluxo toma o documento primeiro; a Entrada deve esperar o lock,
    reler o vínculo já commitado e abortar sem sobrescrever cadeia probatória."""
    user_id, external_client_id, external_case_id, batch_id, doc_id = (
        await _semear_entrada()
    )
    payload = _payload_entrada(user_id=user_id, doc_id=doc_id)

    async def _vinculo_concorrente():
        async with AsyncSessionLocal() as db_a:
            doc = (
                await db_a.execute(
                    select(Document)
                    .where(Document.id == doc_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).scalar_one()
            doc.case_id = external_case_id
            doc.client_id = external_client_id
            await asyncio.sleep(0.6)
            await db_a.commit()

    async def _entrada():
        async with AsyncSessionLocal() as db_b:
            await asyncio.sleep(0.1)
            user = await db_b.get(User, user_id)
            with pytest.raises(HTTPException) as exc:
                await criar_caso_do_rascunho(db_b, user, batch_id, payload)
            assert exc.value.status_code == 422
            assert "já vinculado" in str(exc.value.detail)
            await db_b.rollback()

    await asyncio.gather(_vinculo_concorrente(), _entrada())

    async with AsyncSessionLocal() as db_check:
        doc = await db_check.get(Document, doc_id)
        batch = await db_check.get(DocumentIntakeBatch, batch_id)
        cases = (
            await db_check.execute(
                select(Case).where(Case.titulo == "Caso concorrente da Entrada")
            )
        ).scalars().all()

    assert doc.case_id == external_case_id
    assert doc.client_id == external_client_id
    assert batch.case_id is None
    assert cases == [], "a transação abortada deixou caso órfão"


async def _semear_raio_x() -> tuple[str, str]:
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "DELETE FROM case_intelligence_snapshots "
                "WHERE case_id IN (SELECT id FROM cases "
                "WHERE advogado_responsavel_id IN "
                "(SELECT id FROM users WHERE email LIKE 'raiox-race-%'))"
            )
        )
        await db.execute(
            text(
                "DELETE FROM case_intelligence_snapshots "
                "WHERE case_id IN (SELECT id FROM cases "
                "WHERE advogado_responsavel_id IN "
                "(SELECT id FROM users WHERE email LIKE 'raiox-race-%')) "
                "OR criado_por IN (SELECT id FROM users WHERE email LIKE 'raiox-race-%')"
            )
        )
        await db.execute(
            text(
                "UPDATE raio_x_analises SET convertido_case_id = NULL "
                "WHERE titulo = 'Raio-X concorrente'"
            )
        )
        await db.execute(
            text(
                "DELETE FROM cases "
                "WHERE advogado_responsavel_id IN "
                "(SELECT id FROM users WHERE email LIKE 'raiox-race-%')"
            )
        )
        await db.execute(
            text(
                "DELETE FROM clients "
                "WHERE responsavel_id IN (SELECT id FROM users WHERE email LIKE 'raiox-race-%')"
            )
        )
        await db.execute(
            text(
                "DELETE FROM raio_x_analises WHERE titulo = 'Raio-X concorrente'"
            )
        )
        await db.commit()
        user_id = await _criar_advogado(db, prefixo="raiox-race")
        analise_id = str(uuid4())
        db.add(
            RaioXAnalise(
                id=analise_id,
                titulo="Raio-X concorrente",
                potencial_cliente=None,
                status="aguardando_conferencia",
                relatorio={
                    "sintese_executiva": "Análise preliminar revisável.",
                    "fontes": [],
                    "prazos_potenciais": [],
                    "proximos_passos": [],
                },
                created_by=user_id,
            )
        )
        await db.commit()
        return user_id, analise_id


def _payload_raio_x() -> RaioXConverterRequest:
    return RaioXConverterRequest(
        cliente={"modo": "novo", "nome": f"Cliente RX {uuid4().hex[:8]}"},
        caso={
            "titulo": f"Caso convertido uma única vez {uuid4().hex[:8]}",
            "area": "civil",
            "prioridade": "media",
            "case_type": "judicial",
        },
        documento_ids=[],
        transferir_prazos=False,
        transferir_tarefas=False,
        duplicate_confirmed=True,
        conflict_confirmed=True,
        confirmacao="TRANSFORMAR EM CASO DO ESCRITÓRIO",
    )


@pytest.mark.anyio
async def test_raio_x_duas_conversoes_concorrentes_criam_um_unico_caso():
    user_id, analise_id = await _semear_raio_x()
    payload = _payload_raio_x()

    async def _converter(atraso: float):
        async with AsyncSessionLocal() as db:
            await asyncio.sleep(atraso)
            user = await db.get(User, user_id)
            analise = (
                await db.execute(
                    select(RaioXAnalise)
                    .options(selectinload(RaioXAnalise.documentos))
                    .where(RaioXAnalise.id == analise_id)
                )
            ).scalar_one()
            return await converter_em_caso(db, analise, payload, user)

    primeiro, segundo = await asyncio.gather(_converter(0.0), _converter(0.05))

    assert primeiro["case_id"] == segundo["case_id"]
    assert {primeiro["ja_convertido"], segundo["ja_convertido"]} == {False, True}

    async with AsyncSessionLocal() as db_check:
        analise = await db_check.get(RaioXAnalise, analise_id)
        casos = (
            await db_check.execute(
                select(Case).where(Case.id == primeiro["case_id"])
            )
        ).scalars().all()

    assert len(casos) == 1
    assert analise.convertido_case_id == casos[0].id
