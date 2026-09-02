from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException

from app.models.deadline import Deadline, DeadlineStatus
from app.models.notification import Notification
from app.models.user import User, UserRole
from app.schemas.deadline import DeadlineUpdate


class _Res:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _DB:
    def __init__(self, deadline: Deadline):
        self.deadline = deadline
        self.added: list[object] = []
        self.commits = 0

    async def execute(self, *args, **kwargs):
        return _Res(self.deadline)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        return None


def _user(uid: str, role: UserRole) -> User:
    user = User(
        id=uid,
        email=f"{uid}@ejc.adv.br",
        full_name=uid,
        role=role,
    )
    user.is_active = True
    return user


def _deadline(**kwargs) -> Deadline:
    base = dict(
        id="dl-717",
        titulo="Prazo crítico de teste",
        tipo="processual",
        prioridade="critica",
        status=DeadlineStatus.pendente,
        data_prazo=date(2026, 9, 22),
        data_publicacao=date(2026, 9, 1),
        termo_inicial=date(2026, 9, 2),
        regime_calculo="civel",
        responsavel_id="calc-1",
        confirmado=False,
        calculado_por="calc-1",
        calculo_metadata={
            "termo_final": "2026-09-22",
            "termo_inicial": "2026-09-02",
            "regime_calculo": "civel",
            "historico_recalculo": [],
            "estado_validacao": "aguardando_conferencia",
        },
        ciencia_confirmada=False,
        created_at=datetime.now(timezone.utc),
    )
    estado_historico = {
        chave: kwargs.pop(chave)
        for chave in ("confirmado", "conferido_por", "conferido_em")
        if chave in kwargs
    }
    base.update(kwargs)
    prazo = Deadline(**base)
    for chave, valor in estado_historico.items():
        setattr(prazo, chave, valor)
    return prazo


def _audit_noop(monkeypatch):
    from app.routers import deadlines

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(deadlines, "criar_audit_log", _noop)


@pytest.mark.anyio
async def test_calculista_nao_confirma_o_proprio_prazo_critico(monkeypatch):
    from app.routers import deadlines

    _audit_noop(monkeypatch)
    prazo = _deadline()
    db = _DB(prazo)

    with pytest.raises(HTTPException) as exc:
        await deadlines.confirmar(
            deadline_id=prazo.id,
            db=db,
            cu=_user("calc-1", UserRole.advogado),
        )

    assert exc.value.status_code == 409
    assert "diferente do calculista" in str(exc.value.detail)
    assert prazo.confirmado is False
    assert db.commits == 0


@pytest.mark.anyio
async def test_segundo_usuario_de_gestao_confirma_sem_burlar_ownership(monkeypatch):
    from app.routers import deadlines

    _audit_noop(monkeypatch)
    prazo = _deadline()
    db = _DB(prazo)

    resposta = await deadlines.confirmar(
        deadline_id=prazo.id,
        db=db,
        cu=_user("socio-2", UserRole.socio),
    )

    assert resposta.confirmado is True
    assert resposta.calculado_por == "calc-1"
    assert resposta.conferido_por == "socio-2"
    assert prazo.calculo_metadata["estado_validacao"] == "conferido"
    assert db.commits == 1


@pytest.mark.anyio
async def test_segundo_advogado_sem_ownership_nao_ganha_acesso_por_quatro_olhos(monkeypatch):
    from app.routers import deadlines

    _audit_noop(monkeypatch)
    prazo = _deadline()
    db = _DB(prazo)

    with pytest.raises(HTTPException) as exc:
        await deadlines.confirmar(
            deadline_id=prazo.id,
            db=db,
            cu=_user("adv-sem-acesso", UserRole.advogado),
        )

    assert exc.value.status_code == 404
    assert prazo.confirmado is False


@pytest.mark.anyio
async def test_alteracao_material_reabre_conferencia_e_notifica(monkeypatch):
    from app.routers import deadlines

    _audit_noop(monkeypatch)
    prazo = _deadline(
        confirmado=True,
        calculado_por="calc-1",
        conferido_por="socio-2",
        conferido_em=datetime.now(timezone.utc),
        calculo_metadata={
            "termo_final": "2026-09-22",
            "termo_inicial": "2026-09-02",
            "regime_calculo": "civel",
            "historico_recalculo": [],
            "ultima_conferencia": {"por": "socio-2"},
            "estado_validacao": "conferido",
        },
    )
    db = _DB(prazo)

    resposta = await deadlines.atualizar(
        deadline_id=prazo.id,
        payload=DeadlineUpdate(data_prazo=date(2026, 9, 25)),
        db=db,
        cu=_user("calc-1", UserRole.advogado),
    )

    assert resposta.data_prazo == date(2026, 9, 25)
    assert resposta.confirmado is False
    assert resposta.calculado_por == "calc-1"
    assert resposta.conferido_por is None
    assert prazo.calculo_metadata["termo_final"] == "2026-09-25"
    assert prazo.calculo_metadata["estado_validacao"] == "aguardando_conferencia"
    assert any(isinstance(item, Notification) for item in db.added)
    assert db.commits == 1


@pytest.mark.anyio
async def test_promover_para_critico_exige_termo_e_regime(monkeypatch):
    from app.routers import deadlines

    _audit_noop(monkeypatch)
    prazo = _deadline(
        prioridade="alta",
        termo_inicial=None,
        regime_calculo=None,
        confirmado=True,
    )
    db = _DB(prazo)

    with pytest.raises(HTTPException) as exc:
        await deadlines.atualizar(
            deadline_id=prazo.id,
            payload=DeadlineUpdate(prioridade="critica"),
            db=db,
            cu=_user("calc-1", UserRole.advogado),
        )

    assert exc.value.status_code == 422
    assert db.commits == 0
