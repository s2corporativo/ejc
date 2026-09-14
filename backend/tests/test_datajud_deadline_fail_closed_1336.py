"""Regressões P0 do contrato DataJud → prazos (#1336).

DataJud pode atualizar movimentações/contexto processual, mas não materializa
Deadline a partir da data genérica de movimento. Prazo operacional exige motor
canônico, termo inicial/regime verificáveis e revisão humana.
"""
from __future__ import annotations

import inspect
from unittest.mock import ANY, AsyncMock

import pytest
from fastapi import HTTPException

from app.models.case import Case
from app.routers import datajud as router_datajud
from app.services import datajud_cognitive_patch, datajud_service


class _Resultado:
    """Resultado mínimo para os handlers testados sem banco real."""

    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _DB:
    """Sessão mínima com commit/rollback observáveis."""

    def __init__(self, value):
        self._value = value
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def execute(self, _query):
        return _Resultado(self._value)


@pytest.mark.asyncio
async def test_sync_case_nao_dispara_pipeline_de_prazo(monkeypatch):
    """O sync normal importa contexto e devolve bloqueio explícito de prazo."""
    case = Case(id="case-1", numero_processo="0000000-00.2026.8.13.0000")
    db = _DB(case)

    acesso = AsyncMock(return_value=case)
    sync_movimentos = AsyncMock(return_value=2)
    sync_prazos = AsyncMock(
        side_effect=AssertionError("pipeline de prazo não pode ser chamado")
    )
    monkeypatch.setattr(router_datajud, "verificar_acesso_caso", acesso)
    monkeypatch.setattr(
        router_datajud.datajud_service,
        "sincronizar_caso",
        sync_movimentos,
    )
    monkeypatch.setattr(
        router_datajud.datajud_service,
        "sincronizar_prazos_datajud",
        sync_prazos,
    )

    resposta = await router_datajud.sync_case(
        "case-1", db=db, current_user=object()
    )

    assert resposta["synced"] == 2
    assert resposta["prazos"] == {
        "criados": 0,
        "ignorados": 0,
        "bloqueado": True,
        "motivo": "prazo_datajud_requer_motor_canonico_e_hitl",
    }
    sync_prazos.assert_not_awaited()
    acesso.assert_awaited_once_with(db, ANY, "case-1")
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_prazos_preserva_ownership_e_falha_com_409(monkeypatch):
    """A rota legada existe por compatibilidade, mas nunca grava prazo."""
    case = Case(id="case-1", numero_processo="0000000-00.2026.8.13.0000")
    db = _DB(case)

    acesso = AsyncMock(return_value=case)
    sync_prazos = AsyncMock(
        side_effect=AssertionError("pipeline legado não pode ser chamado")
    )
    monkeypatch.setattr(router_datajud, "verificar_acesso_caso", acesso)
    monkeypatch.setattr(
        router_datajud.datajud_service,
        "sincronizar_prazos_datajud",
        sync_prazos,
    )

    with pytest.raises(HTTPException) as excinfo:
        await router_datajud.sync_prazos(
            "case-1", db=db, current_user=object()
        )

    assert excinfo.value.status_code == 409
    assert "motor canônico" in excinfo.value.detail
    acesso.assert_awaited_once_with(db, ANY, "case-1")
    sync_prazos.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_detector_na_fonte_e_fail_closed_sem_startup():
    """Import isolado do serviço não calcula prazos a partir do movimento."""
    assert datajud_service._detectar_prazos_criticos(
        "Sentença publicada", object()
    ) == []


@pytest.mark.asyncio
async def test_writer_na_fonte_e_noop_sem_startup_ou_db(caplog):
    """Writer original permanece inerte mesmo sem instalar o patch cognitivo."""
    marcador = "NUMERO-PROCESSO-NAO-DEVE-APARECER"

    with caplog.at_level("WARNING", logger="ejc.datajud"):
        resultado = await datajud_service._criar_deadline_automatico(
            object(),
            object(),
            {"titulo": "prazo sintético"},
            marcador,
        )

    assert resultado is None
    assert marcador not in caplog.text
    assert "revisão humana" in caplog.text


@pytest.mark.asyncio
async def test_writer_legado_direto_e_noop_sem_db_ou_pii(caplog):
    """Defesa em profundidade: o escritor neutralizado não toca banco."""
    marcador = "NUMERO-PROCESSO-NAO-DEVE-APARECER"

    with caplog.at_level("WARNING", logger="ejc.datajud.cognitive_patch"):
        resultado = await datajud_cognitive_patch._nao_criar_deadline_datajud(
            object(),
            object(),
            {"titulo": "prazo sintético"},
            marcador,
        )

    assert resultado is None
    assert marcador not in caplog.text
    assert "revisão humana" in caplog.text


def test_instalador_neutraliza_detector_writer_e_sync_de_prazos():
    """Os três caminhos legados de materialização ficam atrás da barreira."""
    fonte = inspect.getsource(datajud_cognitive_patch._instalar_wrappers)

    assert "dj._criar_deadline_automatico = _nao_criar_deadline_datajud" in fonte
    assert "dj._detectar_prazos_criticos = detectar_sem_criar_prazo" in fonte
    assert "dj.sincronizar_prazos_datajud = sincronizar_prazos_bloqueado" in fonte
