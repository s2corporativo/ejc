"""PATCH /cases/{case_id} não pode ser atalho para arquivar/encerrar.

Achado da auditoria (docs/PLANO_FUSAO_CASO_UNICO.md §4.3-5): o PATCH genérico
não tinha `require_roles` nem exigia pós-mortem, então qualquer usuário com
visibilidade sobre o caso conseguia arquivar (contornando `_ARQUIVAMENTO_ROLES`
de `POST /arquivar`) ou encerrar (contornando o pós-mortem obrigatório de
`POST /encerrar`) só chamando `PATCH {"status": "arquivado"|"encerrado"}`.

Cobre também a reabertura: sair de `encerrado`/`arquivado` via PATCH continua
livre (nenhum endpoint dedicado exige isso), mas agora limpa os campos de
desfecho (`data_encerramento`, `resultado`, `motivo_resultado`,
`provas_determinantes`, `licoes_aprendidas`) — um caso reaberto não é mais um
caso encerrado, e deixá-los preenchidos contaminava jurimetria/case_health.

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
from starlette.background import BackgroundTasks

from app.schemas.case import CaseUpdate

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_user(db, role: str = "socio") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Gate Teste', :role, true)"),
        {"id": uid, "email": f"gate-{uid[:8]}@teste.local", "role": role},
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


async def _criar_caso(db, client_id: str, titulo: str, resp_id: str, *, status: str = "em_instrucao") -> str:
    # `status` é literal fixo do teste (não input externo) — inlinado na
    # query, como nos demais *_dblevel.py, porque o enum casestatus rejeita
    # bind de parâmetro sem cast explícito.
    assert status in ("em_instrucao", "encerrado", "arquivado", "aberto")
    case_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO cases (id, titulo, area, status, client_id, "
            "advogado_responsavel_id, proxima_acao) VALUES "
            f"(:id, :titulo, 'civil', '{status}', :cid, :resp, 'Providenciar X')"
        ),
        {"id": case_id, "titulo": titulo, "cid": client_id, "resp": resp_id},
    )
    return case_id


async def _carregar_user(db, uid: str):
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _limpar(db, *, case_ids=(), user_ids=(), client_ids=()):
    for cid in case_ids:
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": cid})
    # audit_logs.user_id tem FK real para users.id (sem ON DELETE) e a tabela
    # é WORM (migration 131_audit_logs_worm bloqueia DELETE direto) — o PATCH
    # bem-sucedido em test_patch_reabertura_limpa_campos_de_desfecho grava um
    # audit_log via criar_audit_log(), então o usuário não pode ser apagado
    # sem primeiro expurgar o próprio log de teste. Mesmo padrão dos demais
    # *_dblevel.py (ex.: test_casos_dblevel.py::_limpar).
    for uid in user_ids:
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": uid})
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def test_patch_nao_arquiva_nem_encerra_mesmo_com_papel_de_gestao():
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import atualizar

    tok = f"Gate{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}", socio)
        await db.commit()
        try:
            cu = await _carregar_user(db, socio)

            with pytest.raises(HTTPException) as exc:
                await atualizar(
                    caso, CaseUpdate(status="arquivado"), BackgroundTasks(),
                    db, cu,
                )
            assert exc.value.status_code == 422
            assert "arquivar" in str(exc.value.detail).lower()

            with pytest.raises(HTTPException) as exc:
                await atualizar(
                    caso, CaseUpdate(status="encerrado"), BackgroundTasks(),
                    db, cu,
                )
            assert exc.value.status_code == 422
            assert "encerrar" in str(exc.value.detail).lower()

            # O caso não mudou de status em nenhuma das duas tentativas.
            status_atual = (await db.execute(
                text("SELECT status FROM cases WHERE id = :id"), {"id": caso},
            )).scalar()
            assert status_atual == "em_instrucao"
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[socio], client_ids=[cli])


async def test_patch_reenvio_do_mesmo_status_arquivado_preserva_registro():
    """Achado do code-reviewer: um PATCH que reenvia {"status": "arquivado"}
    para um caso JÁ arquivado (payload "salvar tudo" reenviando o objeto
    inteiro) não é uma transição — o gate de 422 não dispara porque o status
    não mudou — mas não pode, por isso, apagar `archived_at`/`archive_reason`
    como se o caso estivesse saindo do arquivamento."""
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import atualizar

    tok = f"Reenv{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}", socio, status="arquivado")
        agora = datetime.now(timezone.utc)
        await db.execute(
            text("UPDATE cases SET archived_at = :agora, archive_reason = 'Cliente desistiu' WHERE id = :id"),
            {"id": caso, "agora": agora},
        )
        await db.commit()
        try:
            cu = await _carregar_user(db, socio)
            # Reenvia o MESMO status, junto de outro campo qualquer (simula
            # uma tela que sempre manda o objeto inteiro no PATCH).
            await atualizar(
                caso, CaseUpdate(status="arquivado", prioridade="alta"),
                BackgroundTasks(), db, cu,
            )
            row = (await db.execute(
                text("SELECT status, archived_at, archive_reason FROM cases WHERE id = :id"),
                {"id": caso},
            )).one()
            assert row[0] == "arquivado"
            assert row[1] is not None
            assert row[2] == "Cliente desistiu"
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[socio], client_ids=[cli])


async def test_patch_reabertura_limpa_campos_de_desfecho():
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import atualizar

    tok = f"Reab{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}", socio, status="encerrado")
        await db.execute(
            text("""
                UPDATE cases SET
                    data_encerramento = :agora,
                    resultado = 'exito_total',
                    motivo_resultado = 'Acordo homologado',
                    provas_determinantes = 'Contrato assinado',
                    licoes_aprendidas = 'Documentar cedo'
                WHERE id = :id
            """),
            {"id": caso, "agora": datetime.now(timezone.utc)},
        )
        await db.commit()
        try:
            cu = await _carregar_user(db, socio)
            await atualizar(
                caso, CaseUpdate(status="aberto"), BackgroundTasks(), db, cu,
            )
            row = (await db.execute(
                text(
                    "SELECT status, data_encerramento, resultado, motivo_resultado, "
                    "provas_determinantes, licoes_aprendidas FROM cases WHERE id = :id"
                ),
                {"id": caso},
            )).one()
            assert row[0] == "aberto"
            assert row[1] is None
            assert row[2] is None
            assert row[3] is None
            assert row[4] is None
            assert row[5] is None
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[socio], client_ids=[cli])
