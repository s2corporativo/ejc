"""PATCH /cases/{case_id}/kanban não pode sincronizar status para
arquivado/encerrado sem passar pelo endpoint dedicado.

Achado do security-auditor sobre o PR que fechou o mesmo gap no PATCH
genérico (docs/PLANO_FUSAO_CASO_UNICO.md §4.3-5): `update_case_kanban`
(`kanban.py`) era o SEGUNDO caminho que gravava `Case.status` direto por SQL
cru — sem `require_roles(_ARQUIVAMENTO_ROLES)`, sem pós-mortem, sem
`AuditLog`, sem `CaseMovimento` — e não limpava os campos de desfecho na
reabertura. Qualquer usuário de `_TEAM` (inclusive `estagiario` vinculado
como auxiliar do caso) conseguia arquivar ou encerrar um caso só arrastando
o cartão para uma coluna com nome "Arquivado"/"Encerrado"/"Entregue"/"Acordo".

Postgres é OBRIGATÓRIO (mesmo padrão dos demais *_dblevel.py: chama o handler
direto com AsyncSessionLocal). Sem RUN_DB_TESTS=1, pula.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_user(db, role: str = "estagiario") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Kanban Teste', :role, true)"),
        {"id": uid, "email": f"kanban-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _criar_cliente(db, nome: str) -> str:
    cid = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, email, status) "
             "VALUES (:id, 'PF', :nome, :email, 'ativo')"),
        {"id": cid, "nome": nome, "email": f"{cid[:8]}@teste.local"},
    )
    return cid


async def _criar_caso(
    db, client_id: str, titulo: str, *, resp_id: str, auxiliar_id: str | None = None,
    status: str = "em_instrucao",
) -> str:
    assert status in ("em_instrucao", "encerrado", "arquivado", "aberto")
    case_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO cases (id, titulo, area, status, client_id, "
            "advogado_responsavel_id, advogado_auxiliar_id, proxima_acao, kanban_column) "
            f"VALUES (:id, :titulo, 'civil', '{status}', :cid, :resp, :aux, "
            "'Providenciar X', 'Em andamento')"
        ),
        {"id": case_id, "titulo": titulo, "cid": client_id, "resp": resp_id, "aux": auxiliar_id},
    )
    return case_id


async def _carregar_user(db, uid: str):
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _limpar(db, *, case_ids=(), user_ids=(), client_ids=()):
    for cid in case_ids:
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": cid})
    for uid in user_ids:
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def test_estagiario_nao_arquiva_nem_encerra_arrastando_cartao():
    from app.core.database import AsyncSessionLocal
    from app.routers.kanban import update_case_kanban

    tok = f"Kan{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        estagiario = await _criar_user(db, "estagiario")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        # Estagiário vinculado como AUXILIAR do caso — passa por
        # verificar_acesso_caso mesmo sem papel de gestão.
        caso = await _criar_caso(db, cli, f"Caso {tok}", resp_id=socio, auxiliar_id=estagiario)
        await db.commit()
        try:
            cu = await _carregar_user(db, estagiario)

            with pytest.raises(HTTPException) as exc:
                await update_case_kanban(
                    caso, {"kanban_column": "Arquivado", "kanban_position": 0}, db, cu,
                )
            assert exc.value.status_code == 422
            assert "arquivar" in str(exc.value.detail).lower()

            with pytest.raises(HTTPException) as exc:
                await update_case_kanban(
                    caso, {"kanban_column": "Encerrado", "kanban_position": 0}, db, cu,
                )
            assert exc.value.status_code == 422
            assert "encerrar" in str(exc.value.detail).lower()

            status_atual = (await db.execute(
                text("SELECT status FROM cases WHERE id = :id"), {"id": caso},
            )).scalar()
            assert status_atual == "em_instrucao"
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[socio, estagiario], client_ids=[cli])


async def test_kanban_move_livre_para_coluna_nao_terminal():
    """Mover o cartão entre colunas que não mapeiam para status terminal
    continua funcionando sem nenhum gate extra — só a sincronização de
    status para arquivado/encerrado é bloqueada."""
    from app.core.database import AsyncSessionLocal
    from app.routers.kanban import update_case_kanban

    tok = f"Kan{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        estagiario = await _criar_user(db, "estagiario")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}", resp_id=estagiario)
        await db.commit()
        try:
            cu = await _carregar_user(db, estagiario)
            resultado = await update_case_kanban(
                caso, {"kanban_column": "Em elaboração", "kanban_position": 2}, db, cu,
            )
            assert resultado["status_sincronizado"] is None
            row = (await db.execute(
                text("SELECT status, kanban_column, kanban_position FROM cases WHERE id = :id"),
                {"id": caso},
            )).one()
            assert row[0] == "em_instrucao"
            assert row[1] == "Em elaboração"
            assert row[2] == 2
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[estagiario], client_ids=[cli])


async def test_kanban_reabertura_limpa_campos_de_desfecho():
    from app.core.database import AsyncSessionLocal
    from app.routers.kanban import update_case_kanban

    tok = f"Kan{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}", resp_id=socio, status="encerrado")
        await db.execute(
            text("""
                UPDATE cases SET
                    data_encerramento = :agora,
                    resultado = 'exito_total',
                    motivo_resultado = 'Acordo homologado',
                    provas_determinantes = 'Contrato assinado',
                    licoes_aprendidas = 'Documentar cedo',
                    kanban_column = 'Encerrado'
                WHERE id = :id
            """),
            {"id": caso, "agora": datetime.now(timezone.utc)},
        )
        await db.commit()
        try:
            cu = await _carregar_user(db, socio)
            resultado = await update_case_kanban(
                caso, {"kanban_column": "Aguardando prazo", "kanban_position": 0}, db, cu,
            )
            assert resultado["status_sincronizado"] == "aberto"
            row = (await db.execute(
                text(
                    "SELECT status, data_encerramento, resultado, motivo_resultado, "
                    "provas_determinantes, licoes_aprendidas FROM cases WHERE id = :id"
                ),
                {"id": caso},
            )).one()
            assert row[0] == "aberto"
            assert all(v is None for v in row[1:])
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[socio], client_ids=[cli])
