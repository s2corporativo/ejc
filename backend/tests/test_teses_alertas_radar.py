"""Radar Jurisprudencial — router de consulta e tratamento de alertas
(PR 4 da série de consolidação do Banco de Teses, Commit 7).

`criar_audit_log` é monkeypatchado (mesmo padrão de
`test_teses_extensoes_validacao.py`): a coluna real usa `JSONB`,
Postgres-only, incompatível com SQLite — aqui cobrimos só a lógica do
router (RBAC, filtro, transição de status), não a trilha de auditoria.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.tese_extensoes import TeseAlertaJurisprudencial
from app.models.user import User, UserRole
from app.routers import teses_alertas_radar as router_mod
from app.routers.teses_alertas_radar import (
    TratarAlertaIn,
    listar_alertas,
    listar_alertas_da_tese,
    tratar_alerta,
)

_TABELAS = [TeseAlertaJurisprudencial.__table__]


@pytest.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABELAS))
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _audit_log_fake(*a, **kw):
        return None

    monkeypatch.setattr(router_mod, "criar_audit_log", _audit_log_fake)

    async with maker() as session:
        yield session
    await engine.dispose()


def _usuario(role: UserRole = UserRole.advogado, uid: str = "u1") -> User:
    return User(id=uid, role=role)


async def _novo_alerta(db, *, severidade="alta", status="novo",
                        teses_afetadas=None, fonte="lexml") -> TeseAlertaJurisprudencial:
    a = TeseAlertaJurisprudencial(
        id=str(uuid4()), fonte=fonte, chave_dedup=f"radar:{uuid4()}",
        titulo="REsp 1.111.111/SP", severidade=severidade, status=status,
        teses_afetadas=teses_afetadas or [{"tese_id": "t1", "titulo": "Tese X"}],
    )
    db.add(a)
    await db.commit()
    return a


# ── GET /teses/alertas ───────────────────────────────────────────────────────

async def test_listar_alertas_exige_staff(db):
    outro = _usuario(role=UserRole.financeiro)
    with pytest.raises(HTTPException) as exc:
        await listar_alertas(status=None, severidade=None, fonte=None,
                              limite=50, db=db, cu=outro)
    assert exc.value.status_code == 403


async def test_listar_alertas_devolve_todos_para_staff(db):
    await _novo_alerta(db)
    await _novo_alerta(db)
    saida = await listar_alertas(status=None, severidade=None, fonte=None,
                                  limite=50, db=db, cu=_usuario(role=UserRole.socio))
    assert len(saida) == 2


async def test_listar_alertas_filtra_por_status_severidade_fonte(db):
    await _novo_alerta(db, severidade="alta", status="novo", fonte="lexml")
    await _novo_alerta(db, severidade="baixa", status="tratado", fonte="stj")

    saida = await listar_alertas(status="tratado", severidade=None, fonte=None,
                                  limite=50, db=db, cu=_usuario())
    assert len(saida) == 1
    assert saida[0]["status"] == "tratado"

    saida = await listar_alertas(status=None, severidade="alta", fonte=None,
                                  limite=50, db=db, cu=_usuario())
    assert len(saida) == 1
    assert saida[0]["severidade"] == "alta"

    saida = await listar_alertas(status=None, severidade=None, fonte="stj",
                                  limite=50, db=db, cu=_usuario())
    assert len(saida) == 1
    assert saida[0]["fonte"] == "stj"


# ── GET /teses/{tese_id}/alertas ─────────────────────────────────────────────

async def test_listar_alertas_da_tese_filtra_pelo_json(db):
    await _novo_alerta(db, teses_afetadas=[{"tese_id": "t1", "titulo": "A"}])
    await _novo_alerta(db, teses_afetadas=[{"tese_id": "t2", "titulo": "B"}])
    await _novo_alerta(db, teses_afetadas=[{"tese_id": "t1", "titulo": "A"}, {"tese_id": "t3", "titulo": "C"}])

    saida = await listar_alertas_da_tese("t1", limite=50, db=db, cu=_usuario())
    assert len(saida) == 2

    saida = await listar_alertas_da_tese("t2", limite=50, db=db, cu=_usuario())
    assert len(saida) == 1

    saida = await listar_alertas_da_tese("inexistente", limite=50, db=db, cu=_usuario())
    assert saida == []


async def test_listar_alertas_da_tese_exige_staff(db):
    outro = _usuario(role=UserRole.financeiro)
    with pytest.raises(HTTPException) as exc:
        await listar_alertas_da_tese("t1", limite=50, db=db, cu=outro)
    assert exc.value.status_code == 403


# ── POST /teses/alertas/{alerta_id}/tratar ───────────────────────────────────

async def test_tratar_alerta_exige_permissao_de_edicao(db):
    alerta = await _novo_alerta(db)
    estagiario = _usuario(role=UserRole.estagiario)
    with pytest.raises(HTTPException) as exc:
        await tratar_alerta(alerta.id, TratarAlertaIn(novo_status="tratado"), db=db, cu=estagiario)
    assert exc.value.status_code == 403


async def test_tratar_alerta_inexistente_404(db):
    with pytest.raises(HTTPException) as exc:
        await tratar_alerta(str(uuid4()), TratarAlertaIn(novo_status="tratado"), db=db, cu=_usuario())
    assert exc.value.status_code == 404


async def test_tratar_alerta_rejeita_status_novo(db):
    alerta = await _novo_alerta(db)
    with pytest.raises(HTTPException) as exc:
        await tratar_alerta(alerta.id, TratarAlertaIn(novo_status="novo"), db=db, cu=_usuario())
    assert exc.value.status_code == 422


async def test_tratar_alerta_rejeita_status_desconhecido(db):
    alerta = await _novo_alerta(db)
    with pytest.raises(HTTPException) as exc:
        await tratar_alerta(alerta.id, TratarAlertaIn(novo_status="qualquer-coisa"), db=db, cu=_usuario())
    assert exc.value.status_code == 422


async def test_tratar_alerta_transicao_valida_atualiza_campos(db):
    alerta = await _novo_alerta(db)
    antes = datetime.now(timezone.utc)
    usuario = _usuario(uid="advogado-1")

    saida = await tratar_alerta(
        alerta.id, TratarAlertaIn(novo_status="em_analise", observacao="Verificando impacto."),
        db=db, cu=usuario,
    )

    assert saida["status"] == "em_analise"
    assert saida["tratado_por"] == "advogado-1"
    assert saida["observacao"] == "Verificando impacto."
    assert saida["tratado_em"] >= antes


async def test_tratar_alerta_sem_observacao_preserva_a_anterior(db):
    alerta = await _novo_alerta(db)
    alerta.observacao = "Observação original."
    await db.commit()

    saida = await tratar_alerta(
        alerta.id, TratarAlertaIn(novo_status="descartado"), db=db, cu=_usuario(),
    )
    assert saida["observacao"] == "Observação original."
