"""Geração documental de admissão no cadastro do cliente."""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy")
RUN_DB_TESTS = bool(os.getenv("RUN_DB_TESTS"))
pytestmark = pytest.mark.skipif(not RUN_DB_TESTS, reason="requer banco (RUN_DB_TESTS=1)")

if RUN_DB_TESTS:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.client import Client, ClientTipo
    from app.models.legal_doc import LegalDoc, PecaStatus
    from app.models.fee import Fee, FeePayment, FeeStatus, FeeTipo
    from app.models.user import User, UserRole
    from app.services.geracao_documental_cliente import (
        ADMISSION_KINDS,
        gerar_documentos_cliente,
    )


def _mk_client(db: AsyncSession) -> Client:
    cli = Client(id=str(uuid4()), tipo=ClientTipo.PF, nome=f"Cliente {uuid4().hex[:8]}")
    cli.cidade = "Betim"
    cli.estado = "MG"
    db.add(cli)
    return cli


def _mk_user(db: AsyncSession, role: UserRole = UserRole.advogado) -> User:
    uid = str(uuid4())
    user = User(
        id=uid,
        full_name="Advogado Teste Documental",
        email=f"docs-{uid[:8]}@ejc-homologacao.com",
        hashed_password="$2b$12$placeholderhashplaceholderhashplaceholderhashpl",
        role=role,
        is_active=True,
    )
    db.add(user)
    return user


@pytest.mark.asyncio
async def test_geracao_cria_dois_rascunhos_deterministicos():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        cli = _mk_client(db)
        user = _mk_user(db)
        await db.commit()
        res = await gerar_documentos_cliente(db, cli, user)
        assert res["status"] == "rascunho"
        assert res["ja_existia"] is False
        assert "OUTORGANTE" in res["procuracao"]["conteudo"]
        assert "CONTRATO" in res["contrato"]["conteudo"]

        docs = (
            await db.execute(
                select(LegalDoc).where(
                    LegalDoc.client_id == cli.id,
                    LegalDoc.case_id.is_(None),
                    LegalDoc.status == PecaStatus.rascunho,
                )
            )
        ).scalars().all()
        assert len(docs) == 2
        assert {d.client_admission_kind for d in docs} == set(ADMISSION_KINDS)
        # Não é saída de LLM. Continua rascunho e depende dos gates canônicos
        # de validação/revisão antes de chegar a aprovada/final/protocolada.
        assert all(d.ai_generated is False for d in docs)
        assert all(d.human_reviewed is False for d in docs)
        await db.rollback()


@pytest.mark.asyncio
async def test_forcar_novo_cria_nova_versao_do_kit():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        cli = _mk_client(db)
        user = _mk_user(db)
        await db.commit()
        primeiro = await gerar_documentos_cliente(db, cli, user)
        segundo = await gerar_documentos_cliente(db, cli, user, forcar_novo=True)
        assert primeiro["procuracao"]["legal_doc_id"] != segundo["procuracao"]["legal_doc_id"]
        assert primeiro["contrato"]["legal_doc_id"] != segundo["contrato"]["legal_doc_id"]
        await db.rollback()


@pytest.mark.asyncio
async def test_tipo_poderes_invalido_retorna_erro_controlado():
    from app.core.database import AsyncSessionLocal
    from fastapi import HTTPException

    async with AsyncSessionLocal() as db:
        cli = _mk_client(db)
        user = _mk_user(db)
        await db.commit()
        with pytest.raises(HTTPException) as exc:
            await gerar_documentos_cliente(db, cli, user, tipo_poderes="inexistente")
        assert exc.value.status_code == 422
        await db.rollback()


@pytest.mark.asyncio
async def test_contrato_financeiro_cria_entrada_parcelas_e_exito():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        cli = _mk_client(db)
        user = _mk_user(db, UserRole.socio)
        await db.commit()

        res = await gerar_documentos_cliente(
            db,
            cli,
            user,
            valor_contratual=Decimal("5000.00"),
            entrada=Decimal("1000.00"),
            numero_parcelas=3,
            percentual_exito=Decimal("20.00"),
            data_vencimento=date(2026, 11, 10),
            sincronizar_financeiro=True,
            forcar_novo=True,
        )

        fees = (
            await db.execute(
                select(Fee).where(
                    Fee.client_id == cli.id,
                    Fee.deleted_at.is_(None),
                    Fee.status == FeeStatus.pendente,
                )
            )
        ).scalars().all()
        fixos = [fee for fee in fees if fee.tipo == FeeTipo.fixo]
        exito = [fee for fee in fees if fee.tipo == FeeTipo.exito]

        assert len(fixos) == 4
        assert sum((fee.valor or Decimal("0")) for fee in fixos) == Decimal("5000.00")
        assert sorted(fee.valor for fee in fixos if fee.valor) == [
            Decimal("1000.00"),
            Decimal("1333.33"),
            Decimal("1333.33"),
            Decimal("1333.34"),
        ]
        assert sorted(
            fee.data_vencimento for fee in fixos if "Parcela" in fee.descricao
        ) == [
            date(2026, 11, 10),
            date(2026, 12, 10),
            date(2027, 1, 10),
        ]
        assert len(exito) == 1
        assert exito[0].percentual_exito == Decimal("20.00")
        assert res["parcelas_criadas"] == 4
        assert len(res["financeiro_fee_ids"]) == 5


@pytest.mark.asyncio
async def test_reemissao_preserva_pagamento_e_recalcula_apenas_saldo():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        cli = _mk_client(db)
        user = _mk_user(db, UserRole.socio)
        await db.commit()

        await gerar_documentos_cliente(
            db,
            cli,
            user,
            valor_contratual=Decimal("3000.00"),
            numero_parcelas=3,
            data_vencimento=date(2026, 11, 10),
            sincronizar_financeiro=True,
            forcar_novo=True,
        )
        primeira = (
            await db.execute(
                select(Fee)
                .where(
                    Fee.client_id == cli.id,
                    Fee.status == FeeStatus.pendente,
                    Fee.observacoes.ilike("%component=fixo%"),
                )
                .order_by(Fee.data_vencimento.asc())
            )
        ).scalars().first()
        assert primeira is not None

        pagamento = FeePayment(
            id=str(uuid4()),
            fee_id=primeira.id,
            valor=Decimal("500.00"),
            data_pagamento=date(2026, 11, 5),
            forma="pix",
        )
        db.add(pagamento)
        await db.commit()

        res = await gerar_documentos_cliente(
            db,
            cli,
            user,
            valor_contratual=Decimal("3000.00"),
            numero_parcelas=3,
            data_vencimento=date(2026, 12, 10),
            sincronizar_financeiro=True,
            forcar_novo=True,
        )

        ativas = (
            await db.execute(
                select(Fee).where(
                    Fee.client_id == cli.id,
                    Fee.status.in_([FeeStatus.pendente, FeeStatus.atrasado]),
                    Fee.observacoes.ilike("%component=fixo%"),
                )
            )
        ).scalars().all()
        assert sum((fee.valor or Decimal("0")) for fee in ativas) == Decimal("2500.00")
        assert res["pago_fixo_preservado"] == 500.0

        pagamento_preservado = (
            await db.execute(select(FeePayment).where(FeePayment.id == pagamento.id))
        ).scalar_one()
        assert pagamento_preservado.valor == Decimal("500.00")
