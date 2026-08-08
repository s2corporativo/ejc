"""_purgar_analises_preliminares_abandonadas (F4 / Issue #798).

Prova por negação de leitura: `retention_until` é PISO mínimo de retenção
("não excluir antes disso"), não teto de purga — o sinal de abandono é
inatividade (`updated_at` parado há muito tempo), sempre respeitando o piso
quando ele existe. Cobre:
  (a) Raio-X inativo sem piso → descartado;
  (b) Raio-X inativo COM piso no futuro → piso vence, NÃO descartado;
  (c) Raio-X convertido em caso, mesmo inativo → nunca tocado;
  (d) Sala inativa sem piso → arquivada + deleted_at;
  (e) Sala ativa (updated_at recente) → não tocada.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer PostgreSQL com migrations (defina RUN_DB_TESTS=1)",
)

async def _criar_user(db) -> str:
    uid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
            "VALUES (:id, :email, 'x', 'Purga Teste', 'advogado', true)"
        ),
        {"id": uid, "email": f"purga-{uid[:8]}@teste.local"},
    )
    return uid


async def _criar_analise_raiox(
    db, user_id: str, *, updated_at, status="novo", retention_until=None,
) -> str:
    analise_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO raio_x_analises "
            "(id, titulo, status, relatorio, revisao_humana, alertas_conflito, "
            "custo_ia, dados_extraidos, prazo_urgente, created_by, retention_until, "
            "created_at, updated_at) "
            "VALUES (:id, 'Análise Purga', :status, '{}'::jsonb, '{}'::jsonb, "
            "'[]'::jsonb, '{}'::jsonb, '{}'::jsonb, false, :uid, :ret, :ts, :ts)"
        ),
        {
            "id": analise_id, "status": status, "uid": user_id,
            "ret": retention_until, "ts": updated_at,
        },
    )
    return analise_id


async def _criar_sessao_sala(
    db, user_id: str, *, updated_at, status="em_analise", retention_until=None,
) -> str:
    sessao_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO legal_chat_sessions "
            "(id, titulo, status, workspace_versao, custo_ia_total, created_by, "
            "retention_until, created_at, updated_at) "
            "VALUES (:id, 'Sessão Purga', :status, 0, 0, :uid, :ret, :ts, :ts)"
        ),
        {
            "id": sessao_id, "status": status, "uid": user_id,
            "ret": retention_until, "ts": updated_at,
        },
    )
    return sessao_id


async def _limpar(db, *, analise_ids=(), sessao_ids=(), user_ids=()):
    # Uma asserção que falhou pode ter deixado a transação em estado abortado
    # (Postgres rejeita qualquer comando até o ROLLBACK) — sem isto, a limpeza
    # em si falharia silenciosamente e vazaria dado de teste entre execuções.
    await db.rollback()
    for analise_id in analise_ids:
        await db.execute(
            text("DELETE FROM raio_x_analises WHERE id = :id"), {"id": analise_id}
        )
    for sessao_id in sessao_ids:
        await db.execute(
            text("DELETE FROM legal_chat_sessions WHERE id = :id"), {"id": sessao_id}
        )
    for user_id in user_ids:
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": user_id})
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def test_purga_completa_respeita_piso_e_conversao():
    """Um único cenário cobre (a)-(e): mais barato que 5 conexões separadas e
    prova o comportamento relativo entre os casos na mesma varredura.

    Usa o teto default real (365 dias) — Settings é Pydantic com
    `extra="forbid"` e não aceita monkeypatch de atributo não declarado
    (mesma razão pela qual RETENCAO_CLIENTE_ANOS/RETENCAO_IA_ANOS nunca
    tiveram teste dedicado nesta base)."""
    from app.core.database import AsyncSessionLocal
    from app.services import scheduler

    agora = datetime.now(timezone.utc)
    inativo = agora - timedelta(days=400)
    ativo = agora - timedelta(days=30)
    piso_futuro = agora + timedelta(days=365)

    ids = {"analises": [], "sessoes": [], "users": []}
    async with AsyncSessionLocal() as db:
        user = await _criar_user(db)
        ids["users"].append(user)

        a_sem_piso = await _criar_analise_raiox(db, user, updated_at=inativo)
        a_com_piso_futuro = await _criar_analise_raiox(
            db, user, updated_at=inativo, retention_until=piso_futuro
        )
        a_convertida = await _criar_analise_raiox(
            db, user, updated_at=inativo, status="convertido_em_caso"
        )
        s_sem_piso = await _criar_sessao_sala(db, user, updated_at=inativo)
        s_ativa = await _criar_sessao_sala(db, user, updated_at=ativo)
        ids["analises"] = [a_sem_piso, a_com_piso_futuro, a_convertida]
        ids["sessoes"] = [s_sem_piso, s_ativa]
        await db.commit()

        try:
            await scheduler._purgar_analises_preliminares_abandonadas()

            def _raiox(obj_id):
                return db.execute(
                    text("SELECT status, discarded_at FROM raio_x_analises WHERE id = :id"),
                    {"id": obj_id},
                )

            def _sala(obj_id):
                return db.execute(
                    text("SELECT status, deleted_at FROM legal_chat_sessions WHERE id = :id"),
                    {"id": obj_id},
                )

            r = (await _raiox(a_sem_piso)).one()
            assert r.status == "descartado"
            assert r.discarded_at is not None

            r = (await _raiox(a_com_piso_futuro)).one()
            assert r.status == "novo"  # piso ainda vigente — não tocada
            assert r.discarded_at is None

            r = (await _raiox(a_convertida)).one()
            assert r.status == "convertido_em_caso"  # nunca toca convertida

            r = (await _sala(s_sem_piso)).one()
            assert r.status == "arquivada"
            assert r.deleted_at is not None

            r = (await _sala(s_ativa)).one()
            assert r.status == "em_analise"  # ativa — não tocada
            assert r.deleted_at is None
        finally:
            await _limpar(db, analise_ids=ids["analises"], sessao_ids=ids["sessoes"], user_ids=ids["users"])
