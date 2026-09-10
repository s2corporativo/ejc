"""Regressões AP-09/AP-10: reagendamento/reatribuição reiniciam alertas."""
from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.routers import deadlines
from app.schemas.deadline import DeadlineUpdate


def _prazo(**overrides):
    base = dict(
        id="d1",
        titulo="Prazo de teste",
        case_id=None,
        data_prazo=date.today() + timedelta(days=10),
        responsavel_id="u1",
        status="pendente",
        alerta_7d_enviado=True,
        alerta_3d_enviado=True,
        alerta_1d_enviado=True,
        data_conclusao=None,
        concluido_por=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _user(user_id="u1", role="advogado", *, email=None, phone=None):
    return SimpleNamespace(
        id=user_id,
        role=SimpleNamespace(value=role),
        email=email,
        phone=phone,
    )


class _Resultado:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDB:
    def __init__(self, resultados):
        self.resultados = list(resultados)
        self.commits = 0
        self.refreshes = 0

    async def execute(self, _query):
        if not self.resultados:
            raise AssertionError("consulta inesperada ao banco fake")
        return _Resultado(self.resultados.pop(0))

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        self.refreshes += 1


def test_mudanca_de_data_reinicia_alertas():
    prazo = _prazo()
    assert deadlines._campos_que_reiniciam_alertas(
        prazo, {"data_prazo": prazo.data_prazo + timedelta(days=1)}
    ) == ["data_prazo"]


def test_mudanca_de_responsavel_reinicia_alertas():
    assert deadlines._campos_que_reiniciam_alertas(
        _prazo(), {"responsavel_id": "u2"}
    ) == ["responsavel_id"]


def test_noop_nao_reinicia_alertas():
    prazo = _prazo()
    assert deadlines._campos_que_reiniciam_alertas(
        prazo,
        {"data_prazo": prazo.data_prazo, "responsavel_id": prazo.responsavel_id},
    ) == []


@pytest.mark.asyncio
async def test_patch_reagenda_resseta_flags_e_audita_motivo(monkeypatch):
    prazo = _prazo()
    nova_data = prazo.data_prazo + timedelta(days=5)
    db = _FakeDB([prazo])
    audits = []

    async def _audit(*args, **kwargs):
        audits.append((args, kwargs))

    monkeypatch.setattr(deadlines, "criar_audit_log", _audit)
    monkeypatch.setattr(
        deadlines.DeadlineResponse,
        "model_validate",
        staticmethod(lambda obj: obj),
    )

    out = await deadlines.atualizar(
        "d1",
        DeadlineUpdate(data_prazo=nova_data),
        db=db,
        cu=_user(),
    )

    assert out is prazo
    assert prazo.data_prazo == nova_data
    assert prazo.alerta_7d_enviado is False
    assert prazo.alerta_3d_enviado is False
    assert prazo.alerta_1d_enviado is False
    assert db.commits == 1
    assert db.refreshes == 1

    eventos = {args[3]: kwargs for args, kwargs in audits}
    assert "PRAZO_ALTERADO" in eventos
    assert "PRAZO_ALERTAS_REINICIADOS" in eventos
    reset = eventos["PRAZO_ALERTAS_REINICIADOS"]
    detalhes = reset.get("detalhes", "")
    assert "data_prazo" in detalhes
    assert reset["dados_antes"]["data_prazo"] != reset["dados_depois"]["data_prazo"]
    assert reset["dados_antes"]["responsavel_id"] == "u1"
    assert reset["dados_depois"]["responsavel_id"] == "u1"
    assert reset["dados_depois"]["motivo_campos"] == ["data_prazo"]


@pytest.mark.asyncio
async def test_reatribuicao_vencida_notifica_novo_responsavel_apos_commit(monkeypatch):
    prazo = _prazo(
        data_prazo=date.today() - timedelta(days=2),
        status="vencido",
    )
    alvo = _user("u2", "advogado")
    db = _FakeDB([prazo, alvo, alvo])
    audits = []
    notificacoes = []

    async def _audit(*args, **kwargs):
        audits.append((args, kwargs))

    async def _notificar(db_arg, user_id, titulo, mensagem, **kwargs):
        assert db_arg is db
        assert db.commits == 1, "notificação ocorreu antes do commit da reatribuição"
        notificacoes.append((user_id, titulo, mensagem, kwargs))

    from app.services import notification_service

    monkeypatch.setattr(deadlines, "criar_audit_log", _audit)
    monkeypatch.setattr(notification_service, "notificar", _notificar)
    monkeypatch.setattr(
        deadlines.DeadlineResponse,
        "model_validate",
        staticmethod(lambda obj: obj),
    )

    out = await deadlines.atualizar(
        "d1",
        DeadlineUpdate(responsavel_id="u2"),
        db=db,
        cu=_user("gestao", "socio"),
    )

    assert out.responsavel_id == "u2"
    assert out.status == "vencido"
    assert out.alerta_7d_enviado is False
    assert out.alerta_3d_enviado is False
    assert out.alerta_1d_enviado is False
    assert len(notificacoes) == 1
    user_id, titulo, _mensagem, kwargs = notificacoes[0]
    assert user_id == "u2"
    assert "vencido" in titulo.lower()
    assert kwargs["link"] == "/atividades?tipo=prazo"

    eventos = {args[3]: kwargs for args, kwargs in audits}
    assert "PRAZO_RESPONSAVEL_ALTERADO" in eventos
    assert "PRAZO_ALERTAS_REINICIADOS" in eventos
    reset = eventos["PRAZO_ALERTAS_REINICIADOS"]
    assert "responsavel_id" in reset["detalhes"]
    assert reset["dados_antes"]["responsavel_id"] == "u1"
    assert reset["dados_depois"]["responsavel_id"] == "u2"
    assert reset["dados_antes"]["data_prazo"] == reset["dados_depois"]["data_prazo"]
    assert reset["dados_depois"]["motivo_campos"] == ["responsavel_id"]


@pytest.mark.asyncio
async def test_patch_irrelevante_nao_resseta_alertas(monkeypatch):
    prazo = _prazo()
    db = _FakeDB([prazo])
    audits = []

    async def _audit(*args, **kwargs):
        audits.append((args, kwargs))

    monkeypatch.setattr(deadlines, "criar_audit_log", _audit)
    monkeypatch.setattr(
        deadlines.DeadlineResponse,
        "model_validate",
        staticmethod(lambda obj: obj),
    )

    out = await deadlines.atualizar(
        "d1",
        DeadlineUpdate(descricao="ajuste sem impacto nos alertas"),
        db=db,
        cu=_user(),
    )

    assert out is prazo
    assert prazo.alerta_7d_enviado is True
    assert prazo.alerta_3d_enviado is True
    assert prazo.alerta_1d_enviado is True
    assert db.commits == 1
    assert db.refreshes == 1
    assert all(args[3] != "PRAZO_ALERTAS_REINICIADOS" for args, _kwargs in audits)
