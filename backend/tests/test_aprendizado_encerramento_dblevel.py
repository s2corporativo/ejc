"""Aprendizado institucional no encerramento do caso — EXECUTADO, não inspecionado.

`case_intel.aprendizado_encerramento` é o que faz o encerramento de um caso
virar ativo institucional: grava `memoria_institucional` e semeia o Banco de
Teses. Até aqui a única cobertura era um guard ESTÁTICO
(`test_migracao_gateway_fase1b.py` lê o fonte com `inspect.getsource` e
procura a string `task_type="estrategia"`). Ninguém nunca rodou a função
contra um banco.

Isso importa porque a função **engole toda exceção**:

    except Exception as e:
        logger.warning(f"[case_intel] Falha no aprendizado de encerramento ...")

É a mesma forma do defeito que o `CLAUDE.md` registra na captura DJEN —
"reporta ok há meses sem nunca ter capturado nada". Um SQL errado, uma coluna
renomeada ou um enum divergente deixariam o encerramento silenciosamente sem
memória, e nenhum teste acusaria.

Estes testes rodam a função de verdade, com `AI_ENABLED=False` para exercitar
o caminho DETERMINÍSTICO (fallback sem IA) — o único que dá para afirmar sem
depender de provedor externo.

Postgres é OBRIGATÓRIO. Sem RUN_DB_TESTS=1, pula.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_advogado(db) -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Dra. Encerramento', 'advogado', true)"),
        {"id": uid, "email": f"enc-{uid[:8]}@teste.local"},
    )
    return uid


async def _criar_cliente(db) -> str:
    cid = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, email, status) "
             "VALUES (:id, 'PF', :nome, :email, 'ativo')"),
        {"id": cid, "nome": f"Cliente Enc {cid[:8]}",
         "email": f"enc{cid[:8]}@teste.local"},
    )
    return cid


async def _criar_caso_encerrado(db, client_id: str, advogado_id: str, *,
                                resultado: str = "exito_total") -> str:
    """Caso no estado em que `encerrar_caso` o deixa antes de disparar a task."""
    case_id = str(uuid4())
    await db.execute(
        text("INSERT INTO cases (id, titulo, area, status, client_id, "
             " advogado_responsavel_id, resultado, tese_principal, "
             " motivo_resultado, provas_determinantes, licoes_aprendidas, "
             " data_encerramento) "
             "VALUES (:id, :tit, 'civil', 'encerrado', :cli, :adv, :res, "
             " :tese, :motivo, :provas, :licoes, now())"),
        {"id": case_id, "tit": f"Busca e apreensão {case_id[:6]}",
         "cli": client_id, "adv": advogado_id, "res": resultado,
         "tese": "Purgação da mora afasta a consolidação da propriedade",
         "motivo": "Depósito integral no prazo legal.",
         "provas": "Comprovante de depósito e planilha do credor.",
         "licoes": "Conferir a planilha do credor antes de depositar."},
    )
    return case_id


async def _memorias_do_caso(db, case_id: str) -> list[dict]:
    rows = (await db.execute(text(
        "SELECT tipo, titulo, conteudo, resultado, area_direito, metadados "
        "FROM memoria_institucional WHERE case_id = :i AND deleted_at IS NULL"),
        {"i": case_id})).mappings().all()
    return [dict(r) for r in rows]


async def _limpar(db, *, case_id: str, client_id: str, user_id: str):
    await db.execute(text("DELETE FROM memoria_institucional WHERE case_id = :i"),
                     {"i": case_id})
    await db.execute(text("DELETE FROM teses WHERE created_by = :u"), {"u": user_id})
    await db.execute(text("DELETE FROM case_movimentos WHERE case_id = :i"), {"i": case_id})
    await db.execute(text("DELETE FROM ai_logs WHERE case_id = :i"), {"i": case_id})
    await db.execute(text("DELETE FROM cases WHERE id = :i"), {"i": case_id})
    await db.execute(text("DELETE FROM clients WHERE id = :i"), {"i": client_id})
    await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
    await db.execute(text("DELETE FROM audit_logs WHERE user_id = :u"), {"u": user_id})
    await db.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


@pytest.fixture
def sem_ia(monkeypatch):
    """Força o caminho determinístico (fallback sem IA).

    `aprendizado_encerramento` lê `settings.AI_ENABLED` do módulo; com IA
    ligada o conteúdo vem de provedor externo e o teste deixaria de ser
    determinístico.
    """
    import app.services.case_intel as ci
    monkeypatch.setattr(ci.settings, "AI_ENABLED", False, raising=False)
    return ci


async def test_encerramento_grava_memoria_institucional(sem_ia):
    """O caminho que ninguém tinha exercitado: a linha existe mesmo?"""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        adv = await _criar_advogado(db)
        cli = await _criar_cliente(db)
        caso = await _criar_caso_encerrado(db, cli, adv)
        await db.commit()

    try:
        await sem_ia.aprendizado_encerramento(caso)

        async with AsyncSessionLocal() as db:
            memorias = await _memorias_do_caso(db, caso)
            assert len(memorias) == 1, "encerramento não gerou memória institucional"
            m = memorias[0]
            # Êxito vira tese_vencedora; derrota/parcial vira estrategia.
            assert m["tipo"] == "tese_vencedora"
            assert m["resultado"] == "exito_total"
            assert m["area_direito"] == "civil"
            # Sem IA, o conteúdo é o pós-mortem do próprio caso.
            assert "Purgação da mora" in m["conteudo"]
            assert "planilha do credor" in m["conteudo"]
            # A marca de origem é o que sustenta a idempotência.
            assert m["metadados"]["fonte"] == "auto_encerramento"
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_id=caso, client_id=cli, user_id=adv)


async def test_reexecucao_nao_duplica_memoria(sem_ia):
    """Idempotência: a task é disparada em background e pode repetir."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        adv = await _criar_advogado(db)
        cli = await _criar_cliente(db)
        caso = await _criar_caso_encerrado(db, cli, adv)
        await db.commit()

    try:
        await sem_ia.aprendizado_encerramento(caso)
        await sem_ia.aprendizado_encerramento(caso)
        await sem_ia.aprendizado_encerramento(caso)

        async with AsyncSessionLocal() as db:
            assert len(await _memorias_do_caso(db, caso)) == 1
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_id=caso, client_id=cli, user_id=adv)


async def test_tese_nasce_como_rascunho_sugerida_ia(sem_ia):
    """HITL: a tese semeada pelo encerramento não entra ativa no Banco de
    Teses — precisa de aprovação humana antes de ser reaproveitada."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        adv = await _criar_advogado(db)
        cli = await _criar_cliente(db)
        caso = await _criar_caso_encerrado(db, cli, adv)
        await db.commit()

    try:
        await sem_ia.aprendizado_encerramento(caso)

        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT titulo, tipo::text AS tipo, status::text AS status, "
                "       vezes_usada, vezes_venceu, area_juridica "
                "FROM teses WHERE created_by = :u"), {"u": adv})).mappings().first()
            assert row is not None, "encerramento não semeou o Banco de Teses"
            assert row["status"] == "rascunho"
            assert row["tipo"] == "sugerida_ia"
            assert row["vezes_usada"] == 1
            assert row["vezes_venceu"] == 1      # exito_total
            assert row["area_juridica"] == "civil"
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_id=caso, client_id=cli, user_id=adv)


async def test_derrota_vira_estrategia_e_conta_como_perda(sem_ia):
    """Caso perdido também é conhecimento — e não pode virar tese vencedora."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        adv = await _criar_advogado(db)
        cli = await _criar_cliente(db)
        caso = await _criar_caso_encerrado(db, cli, adv, resultado="improcedente")
        await db.commit()

    try:
        await sem_ia.aprendizado_encerramento(caso)

        async with AsyncSessionLocal() as db:
            memorias = await _memorias_do_caso(db, caso)
            assert memorias[0]["tipo"] == "estrategia"

            row = (await db.execute(text(
                "SELECT vezes_venceu, vezes_perdeu, taxa_sucesso "
                "FROM teses WHERE created_by = :u"), {"u": adv})).mappings().first()
            assert row["vezes_venceu"] == 0
            assert row["vezes_perdeu"] == 1
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_id=caso, client_id=cli, user_id=adv)


async def test_caso_inexistente_nao_estoura(sem_ia):
    """A task roda em background do encerramento: falhar alto derrubaria o
    processo do request. Sair em silêncio aqui é o comportamento correto."""
    await sem_ia.aprendizado_encerramento(str(uuid4()))
