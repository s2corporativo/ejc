"""Radar Jurisprudencial — notificação (PR 4, Commit 8).

Só severidade "critica"/"alta" notifica; destinatário é `Tese.validada_por`
das teses afetadas ou, na ausência, todos os usuários ativos advogado+
(mesmo piso de `_pode_editar`). `notification_service.notificar` é
monkeypatchado — cobrimos só a lógica de seleção de destinatário e o gate de
severidade, não os canais de entrega em si.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.tese import Tese, TeseStatus, TeseTipo
from app.models.user import User, UserRole
from app.services import radar_jurisprudencial_notificacao as mod
from app.services.radar_jurisprudencial_notificacao import notificar_alerta

_TABELAS = [Tese.__table__, User.__table__]


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABELAS))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def _alerta(**overrides):
    base = dict(id=str(uuid4()), titulo="REsp 1.111.111/SP", tribunal="STJ", severidade="alta")
    base.update(overrides)
    return SimpleNamespace(**base)


async def _tese(db, *, validada_por=None) -> Tese:
    t = Tese(
        id=str(uuid4()), titulo="Tese", descricao="Descrição de teste com mais de dez caracteres",
        tipo=TeseTipo.escritorio, status=TeseStatus.ativa, validada_por=validada_por,
    )
    db.add(t)
    await db.commit()
    return t


async def _usuario(db, *, role=UserRole.advogado, ativo=True) -> User:
    u = User(id=str(uuid4()), email=f"{uuid4()}@x.com", full_name="Fulano",
              role=role, is_active=ativo, hashed_password="x")
    db.add(u)
    await db.commit()
    return u


# ── gate de severidade ───────────────────────────────────────────────────────

async def test_severidade_baixa_nao_notifica(db, monkeypatch):
    chamou = {"n": 0}

    async def _fake_notificar(*a, **kw):
        chamou["n"] += 1

    monkeypatch.setattr(mod, "notificar", _fake_notificar)
    n = await notificar_alerta(db, _alerta(severidade="baixa"), [])
    assert n == 0
    assert chamou["n"] == 0


async def test_severidade_media_nao_notifica(db, monkeypatch):
    async def _fake_notificar(*a, **kw):
        raise AssertionError("não deveria ser chamado")

    monkeypatch.setattr(mod, "notificar", _fake_notificar)
    n = await notificar_alerta(db, _alerta(severidade="media"), [])
    assert n == 0


# ── destinatário: Tese.validada_por ──────────────────────────────────────────

async def test_notifica_validador_da_tese_afetada(db, monkeypatch):
    validador = await _usuario(db)
    tese = await _tese(db, validada_por=validador.id)
    notificados = []

    async def _fake_notificar(db_, user_id, titulo, mensagem, **kw):
        notificados.append(user_id)

    monkeypatch.setattr(mod, "notificar", _fake_notificar)
    n = await notificar_alerta(
        db, _alerta(severidade="critica"), [{"tese_id": tese.id}],
    )
    assert n == 1
    assert notificados == [validador.id]


async def test_deduplica_validador_repetido_em_teses_diferentes(db, monkeypatch):
    validador = await _usuario(db)
    t1 = await _tese(db, validada_por=validador.id)
    t2 = await _tese(db, validada_por=validador.id)
    notificados = []

    async def _fake_notificar(db_, user_id, titulo, mensagem, **kw):
        notificados.append(user_id)

    monkeypatch.setattr(mod, "notificar", _fake_notificar)
    n = await notificar_alerta(
        db, _alerta(severidade="alta"), [{"tese_id": t1.id}, {"tese_id": t2.id}],
    )
    assert n == 1
    assert notificados == [validador.id]


# ── fallback: equipe advogado+ ativa ─────────────────────────────────────────

async def test_sem_validador_cai_para_equipe_advogado_mais(db, monkeypatch):
    tese = await _tese(db, validada_por=None)
    advogado = await _usuario(db, role=UserRole.advogado)
    socio = await _usuario(db, role=UserRole.socio)
    await _usuario(db, role=UserRole.estagiario)  # abaixo do piso — não notifica
    await _usuario(db, role=UserRole.advogado, ativo=False)  # inativo — não notifica
    notificados = []

    async def _fake_notificar(db_, user_id, titulo, mensagem, **kw):
        notificados.append(user_id)

    monkeypatch.setattr(mod, "notificar", _fake_notificar)
    n = await notificar_alerta(
        db, _alerta(severidade="critica"), [{"tese_id": tese.id}],
    )
    assert n == 2
    assert set(notificados) == {advogado.id, socio.id}


# ── fail-open ────────────────────────────────────────────────────────────────

async def test_falha_ao_notificar_nao_propaga(db, monkeypatch):
    validador = await _usuario(db)
    tese = await _tese(db, validada_por=validador.id)

    async def _fake_notificar(*a, **kw):
        raise RuntimeError("canal indisponível")

    monkeypatch.setattr(mod, "notificar", _fake_notificar)
    n = await notificar_alerta(db, _alerta(severidade="alta"), [{"tese_id": tese.id}])
    assert n == 0
