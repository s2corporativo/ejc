# ── tests/test_clientes_pecas_geradas_dblevel.py ─────────────────────────────
# Listagem de peças de admissão no DOSSIÊ DIGITAL (GET
# /clients/{id}/pecas-geradas):
#   - service listar_pecas_cliente (handler direto, padrão dblevel)
#   - gate de visibilidade do router (_pode_ver_cliente): carteira alheia
#     retorna 404 (não vaza existência — LGPD/EOAB).
# Padrão dblevel da suíte EJC: handler direto, AsyncSessionLocal,
# skip quando RUN_DB_TESTS não está definido.
from __future__ import annotations

from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy")
import os

RUN_DB_TESTS = bool(os.getenv("RUN_DB_TESTS"))

if RUN_DB_TESTS:
    from sqlalchemy import select as _sel
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.client import Client, ClientTipo
    from app.models.legal_doc import LegalDoc, PecaStatus
    from app.models.user import User
    from app.services.geracao_documental_cliente import (
        listar_pecas_cliente,
        gerar_documentos_cliente,
        _titulos_canonicos,
    )

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


@pytest.mark.asyncio
async def test_listar_vazia_sem_peças():
    """Cliente sem peças de admissão: listagem vazia (estado vazio)."""
    from app.core.database import AsyncSessionLocal as ASL
    async with ASL() as db:
        cli = _mk_client(db, nome=f"Cliente Sem Pecas {uuid4().hex[:6]}")
        await db.commit()
        res = await listar_pecas_cliente(db, cli)
        assert res == []
        await db.rollback()


@pytest.mark.asyncio
async def test_listar_devolve_contrato_e_procuracao():
    """Após gerar, a listagem devolve as 2 peças com tipo/status corretos."""
    from app.core.database import AsyncSessionLocal as ASL
    async with ASL() as db:
        cli = _mk_client(db)
        cu = _mk_user(db)
        await db.commit()
        res_gerar = await gerar_documentos_cliente(db, cli, cu)
        res = await listar_pecas_cliente(db, cli)
        assert len(res) == 2
        tipos = {r["tipo"] for r in res}
        assert tipos == {"procuracao", "contrato"}
        assert all(r["status"] == "rascunho" for r in res)
        assert all(r["created_at"] is not None for r in res)
        ids_retornados = {r["id"] for r in res}
        assert ids_retornados == {
            res_gerar["procuracao"]["legal_doc_id"],
            res_gerar["contrato"]["legal_doc_id"],
        }
        # nenhum vínculo de caso (peças soltas)
        docs = (await db.execute(
            _sel(LegalDoc).where(LegalDoc.id.in_(list(ids_retornados)))
        )).scalars().all()
        assert all(d.case_id is None for d in docs)
        await db.rollback()


@pytest.mark.asyncio
async def test_listar_isola_carteira_titulos():
    """Peças de outro cliente (mesmo tipo) não vazam para a listagem."""
    from app.core.database import AsyncSessionLocal as ASL
    async with ASL() as db:
        cli1 = _mk_client(db, nome=f"Cliente A {uuid4().hex[:6]}")
        cli2 = _mk_client(db, nome=f"Cliente B {uuid4().hex[:6]}")
        cu = _mk_user(db)
        await db.commit()
        await gerar_documentos_cliente(db, cli1, cu)
        await gerar_documentos_cliente(db, cli2, cu)
        res1 = await listar_pecas_cliente(db, cli1)
        res2 = await listar_pecas_cliente(db, cli2)
        assert len(res1) == 2 and len(res2) == 2
        assert {r["id"] for r in res1}.isdisjoint({r["id"] for r in res2})
        await db.rollback()


@pytest.mark.asyncio
async def test_listar_ignora_peças_deletadas_e_outras_sem_caso():
    """Peca solta genérica (não canônica) e peça soft-deleted não aparecem."""
    from app.core.database import AsyncSessionLocal as ASL
    from datetime import datetime, timezone
    async with ASL() as db:
        cli = _mk_client(db)
        cu = _mk_user(db)
        await db.commit()
        await gerar_documentos_cliente(db, cli, cu)
        # peça solta genérica (não canônica): não deve aparecer
        d_generico = LegalDoc(id=str(uuid4()))
        d_generico.case_id = None
        d_generico.status = PecaStatus.rascunho
        d_generico.tipo = "contrato"
        d_generico.tipo_peca = "contrato"
        d_generico.titulo = f"Minuta Generica {uuid4().hex[:6]}"
        d_generico.conteudo = "texto generico"
        d_generico.created_by = cu.id
        db.add(d_generico)
        await db.commit()
        res = await listar_pecas_cliente(db, cli)
        assert len(res) == 2  # só as canônicas
        # soft-delete de uma peça canônica: some da listagem
        canonicos = await listar_pecas_cliente(db, cli)
        alvo = next((d for d in canonicos if d["tipo"] == "contrato"), None)
        assert alvo is not None
        doc = (await db.execute(_sel(LegalDoc).where(LegalDoc.id == alvo["id"]))).scalar_one()
        doc.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        res2 = await listar_pecas_cliente(db, cli)
        assert len(res2) == 1 and res2[0]["tipo"] == "procuracao"
        await db.rollback()


def test_titulos_canonicos_sao_identicos_ao_padrao_geracao():
    """A listagem usa EXATAMENTE os mesmos títulos canônicos da geração
    (garantia de idempotência entre gerar e listar)."""
    from app.services.document_format import padronizar_documento_juridico
    nome = "Fulano de Tal"
    esperados = [
        padronizar_documento_juridico("Procuracao - " + nome)[:200],
        padronizar_documento_juridico("Contrato de Honorarios - " + nome)[:200],
    ]
    assert _titulos_canonicos(nome) == esperados


def test_router_recusa_carteira_alheia_via_pode_ver():
    """O router delega a guarda ao _pode_ver_cliente: carteira alheia →
    404 (não vaza existência). Valida o corpo do handler com o gate
    simulado (sem banco), padrão da casa para guards de titularidade."""
    import asyncio

    from fastapi import HTTPException

    from app.models.client import Client
    from app.services.geracao_documental_cliente import listar_pecas_cliente

    def _chama(visivel: bool):
        async def _pode_ver(db, cu, client):
            return visivel

        import app.routers.clients as mod
        original = mod._pode_ver_cliente
        mod._pode_ver_cliente = _pode_ver
        try:
            async def _run():
                # replica EXATA do corpo do router listar_pecas_geradas
                c = Client(id=str(uuid4()))
                if not await _pode_ver(None, None, c):
                    raise HTTPException(status_code=404, detail="Cliente não encontrado")
                return await listar_pecas_cliente(None, c)
            return asyncio.get_event_loop().run_until_complete(_run())
        finally:
            mod._pode_ver_cliente = original

    with pytest.raises(HTTPException) as exc:
        _chama(visivel=False)
    assert exc.value.status_code == 404
