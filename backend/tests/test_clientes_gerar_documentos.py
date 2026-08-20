# ── tests/test_clientes_gerar_documentos.py ──────────────────────────────────
# Geração documental no CADASTRO DO CLIENTE (sem caso vinculado):
# procuração ad judicia + contrato de honorários padrão OAB/MG.
# Padrão dblevel da suíte EJC: handler direto, AsyncSessionLocal,
# skip quando RUN_DB_TESTS não está definido (testes sem banco não rodam
# este cenário por depender de ORM — mantido alinhado à suíte).
from __future__ import annotations

from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy")
import os

RUN_DB_TESTS = bool(os.getenv("RUN_DB_TESTS"))

if RUN_DB_TESTS:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.client import Client, ClientTipo
    from app.models.legal_doc import LegalDoc, PecaStatus
    from app.models.user import User
    from app.services.geracao_documental_cliente import gerar_documentos_cliente

pytestmark = pytest.mark.skipif(not RUN_DB_TESTS, reason="requer banco (RUN_DB_TESTS=1)")


def _mk_client(db: AsyncSession, nome: str = f"Cliente Teste {uuid4().hex[:8]}") -> Client:
    cli = Client(id=str(uuid4()))
    cli.tipo = ClientTipo.PF
    cli.nome = nome
    cli.cidade = "Betim"
    cli.estado = "MG"
    db.add(cli)
    return cli


def _mk_user(db: AsyncSession, role: str = "advogado") -> User:
    """User REAL (audit_logs tem FK para users — MagicMock viola a FK)."""
    uid = f"ut-{role}-{uuid4().hex}"
    cu = User(id=uid[:36])
    cu.full_name = f"Adv Teste {role}"
    cu.email = f"adv-teste-{role}-{uuid4().hex[:8]}@ejc-homologacao.com"
    cu.hashed_password = "$2b$12$placeholderhashplaceholderhashplaceholderhashpl"  # teste: nunca usado p/ login
    from app.models.user import UserRole
    cu.role = UserRole(role) if hasattr(UserRole, role) else UserRole.advogado
    cu.is_active = True
    db.add(cu)
    return cu


async def _executa(db, cli, cu, **kwargs):
    return await gerar_documentos_cliente(db, cli, cu, **kwargs)


@pytest.mark.asyncio
async def test_geracao_cria_dois_rascunhos():
    from app.core.database import AsyncSessionLocal as ASL
    async with ASL() as db:
        cli = _mk_client(db)
        cu = _mk_user(db)
        await db.commit()
        res = await _executa(db, cli, cu)
        assert res["status"] == "rascunho"
        assert res["ja_existia"] is False
        assert "OUTORGANTE" in res["procuracao"]["conteudo"]
        assert "OAB/MG" in res["contrato"]["conteudo"]
        assert "LGPD" in res["contrato"]["conteudo"]
        # ambos soltos (sem caso) — vínculo por título canônico:
        # query pelos títulos canônicos gerados para ESTE cliente
        from sqlalchemy import select as _sel
        docs = (await db.execute(
            _sel(LegalDoc).where(
                LegalDoc.case_id.is_(None),
                LegalDoc.status == PecaStatus.rascunho,
                LegalDoc.titulo.in_([res["procuracao"]["titulo"],
                                        res["contrato"]["titulo"]]),
            )
        )).scalars().all()
        assert len(docs) == 2
        assert all(d.ai_generated and not d.human_reviewed for d in docs)
        await db.rollback()


@pytest.mark.asyncio
async def test_idempotencia_reaproveita_rascunhos():
    from app.core.database import AsyncSessionLocal as ASL
    async with ASL() as db:
        cli = _mk_client(db)
        cu = _mk_user(db)
        await db.commit()
        res1 = await _executa(db, cli, cu)
        res2 = await _executa(db, cli, cu)
        assert res2["ja_existia"] is True
        assert res2["procuracao"]["legal_doc_id"] == res1["procuracao"]["legal_doc_id"]
        assert res2["contrato"]["legal_doc_id"] == res1["contrato"]["legal_doc_id"]
        # nenhuma duplicata mesmo após reaproveitamento
        from sqlalchemy import select as _sel
        n = (await db.execute(
            _sel(LegalDoc).where(
                LegalDoc.case_id.is_(None),
                LegalDoc.status == PecaStatus.rascunho,
                LegalDoc.titulo.in_([res1["procuracao"]["titulo"],
                                        res1["contrato"]["titulo"]]),
            )
        )).scalars().all()
        assert len(n) == 2
        await db.rollback()


@pytest.mark.asyncio
async def test_tipo_poderes_invalido_levanta():
    from app.core.database import AsyncSessionLocal as ASL
    async with ASL() as db:
        cli = _mk_client(db)
        cu = _mk_user(db)
        await db.commit()
        with pytest.raises(Exception):  # HTTPException 422 (fastapi)
            await _executa(db, cli, cu, tipo_poderes="inexistente")
        await db.rollback()
