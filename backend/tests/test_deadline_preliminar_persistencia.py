from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.routers import deadlines
from app.schemas.deadline import DeadlineCreate


class _FakeDB:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        return None

    async def refresh(self, obj):
        return None


@pytest.mark.anyio
async def test_criacao_persiste_motivo_real_do_resultado_preliminar(monkeypatch):
    aviso = (
        "Tribunal não informado: suspensões e feriados específicos da jurisdição "
        "não puderam ser aplicados; resultado preliminar e sujeito a conferência humana."
    )

    def _calculo(*args, **kwargs):
        return {
            "data_vencimento": date(2026, 9, 17),
            "regime_calculo": "civel",
            "calendario_status": "validado",
            "resultado_preliminar": True,
            "revisao_obrigatoria": True,
            "aviso": aviso,
        }

    async def _audit(*args, **kwargs):
        return None

    monkeypatch.setattr(deadlines, "calcular_prazo_processual", _calculo)
    monkeypatch.setattr(deadlines, "criar_audit_log", _audit)
    monkeypatch.setattr(
        deadlines.DeadlineResponse,
        "model_validate",
        staticmethod(lambda obj: obj),
    )

    db = _FakeDB()
    cu = SimpleNamespace(id="u-adv", role=SimpleNamespace(value="advogado"))
    payload = DeadlineCreate(
        titulo="Contestação",
        tipo="processual",
        data_intimacao=date(2026, 9, 10),
        dias_prazo=5,
        regime_calculo="civel",
        tribunal=None,
    )

    prazo = await deadlines.criar(payload=payload, db=db, cu=cu)

    assert prazo.confirmado is False
    assert "RESULTADO PRELIMINAR" in (prazo.base_legal or "")
    assert "Tribunal não informado" in (prazo.base_legal or "")
    assert "CALENDÁRIO DEGRADADO" not in (prazo.base_legal or "")
