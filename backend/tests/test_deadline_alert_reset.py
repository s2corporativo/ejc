"""Regressões AP-09/AP-10: reagendamento/reatribuição reiniciam alertas."""
from __future__ import annotations

import inspect
from datetime import date
from types import SimpleNamespace

from app.routers import deadlines


def _prazo():
    return SimpleNamespace(
        data_prazo=date(2026, 9, 20),
        responsavel_id="u1",
    )


def test_mudanca_de_data_reinicia_alertas():
    assert deadlines._campos_que_reiniciam_alertas(
        _prazo(), {"data_prazo": date(2026, 9, 21)}
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


def test_update_resseta_tres_flags_e_audita():
    fonte = inspect.getsource(deadlines.atualizar)
    for flag in (
        "alerta_7d_enviado",
        "alerta_3d_enviado",
        "alerta_1d_enviado",
    ):
        assert f"d.{flag} = False" in fonte
    assert "PRAZO_ALERTAS_REINICIADOS" in fonte
    assert "PRAZO_RESPONSAVEL_ALTERADO" in fonte
