"""P1-4 — a visibilidade dos prompts jurídicos vale no ITEM, não só na lista.

Achado de review do PR #652. A primeira versão do P1-4 corrigiu o corte por
papel na LISTAGEM (`financeiro`, cujo nível é maior que o de `estagiario`, vinha
recebendo a biblioteca inteira) e deixou `GET /{id}` e `POST /{id}/executar`
selecionando só por id. Esconder na coleção não protege nada: quem tem o UUID —
de um cache da interface, de um log, de quando a listagem ainda era aberta — lia
e executava o prompt institucional assim mesmo.

É o mesmo defeito que esta auditoria batizou nas outras frentes: **o gate existe
no caminho gêmeo, não no endpoint que executa o ato**. Por isso o teste exercita
as funções de rota de verdade, contra Postgres real, em vez de conferir o SQL.

Requer Postgres com migrations (RUN_DB_TESTS=1, mesmo gate do job `db-validation`).
"""
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


async def _criar_user(db, role: str) -> str:
    uid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
            "VALUES (:id, :email, 'x', 'Teste Prompts', :role, true)"
        ),
        {"id": uid, "email": f"prompt-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _criar_prompt(db, *, publico: bool, autor: str) -> str:
    pid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO prompts_juridicos "
            "(id, titulo, categoria, conteudo, publico, created_by) "
            "VALUES (:id, :tit, 'peticao', :conteudo, :pub, :autor)"
        ),
        {
            "id": pid,
            "tit": f"Prompt {'publico' if publico else 'privado'} {pid[:6]}",
            "conteudo": "Redija a peça observando os prazos do caso {{cliente}}.",
            "pub": publico,
            "autor": autor,
        },
    )
    return pid


async def _carregar_user(db, uid: str):
    from sqlalchemy import select
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _limpar(db, prompt_ids, user_ids):
    for pid in prompt_ids:
        await db.execute(text("DELETE FROM prompts_juridicos WHERE id = :id"), {"id": pid})
    for uid in user_ids:
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": uid})
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    await db.commit()


async def test_financeiro_nao_le_prompt_privado_nem_sabendo_o_id():
    """O caso que motivou a correção: o UUID em mãos não basta."""
    from app.core.database import AsyncSessionLocal
    from app.routers.prompts_juridicos import obter_prompt

    async with AsyncSessionLocal() as db:
        advogado = await _criar_user(db, "advogado")
        financeiro = await _criar_user(db, "financeiro")
        privado = await _criar_prompt(db, publico=False, autor=advogado)
        publico = await _criar_prompt(db, publico=True, autor=advogado)
        await db.commit()
        try:
            cu_fin = await _carregar_user(db, financeiro)
            with pytest.raises(HTTPException) as exc:
                await obter_prompt(privado, db, cu_fin)
            # 404, não 403: o 403 já confirmaria que o prompt existe.
            assert exc.value.status_code == 404

            # E o público segue acessível — a restrição é de sigilo, não um
            # bloqueio do módulo inteiro para quem não é do jurídico.
            assert (await obter_prompt(publico, db, cu_fin))["id"] == publico

            # O time jurídico enxerga os dois.
            cu_adv = await _carregar_user(db, advogado)
            assert (await obter_prompt(privado, db, cu_adv))["id"] == privado
        finally:
            await _limpar(db, [privado, publico], [advogado, financeiro])


async def test_financeiro_nao_executa_prompt_privado_nem_sabendo_o_id():
    """Ler é ruim; EXECUTAR é pior — gasta IA e devolve o conteúdo elaborado.

    O gate tem de barrar antes de qualquer chamada de modelo; por isso o teste
    falha se a execução chegar ao gateway (nenhum provedor é preparado aqui).
    """
    from app.core.database import AsyncSessionLocal
    from app.routers.prompts_juridicos import ExecutarPromptReq, executar_prompt

    async with AsyncSessionLocal() as db:
        advogado = await _criar_user(db, "advogado")
        secretaria = await _criar_user(db, "secretaria")
        privado = await _criar_prompt(db, publico=False, autor=advogado)
        await db.commit()
        try:
            with pytest.raises(HTTPException) as exc:
                await executar_prompt(
                    privado,
                    ExecutarPromptReq(variaveis={"cliente": "Fulano"}),
                    db,
                    await _carregar_user(db, secretaria),
                )
            assert exc.value.status_code == 404, (
                "secretaria executou prompt institucional privado sabendo o id"
            )
        finally:
            await _limpar(db, [privado], [advogado, secretaria])
