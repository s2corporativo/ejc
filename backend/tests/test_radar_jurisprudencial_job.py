"""Radar Jurisprudencial — job do scheduler (PR 4, Commit 6).

`job_radar_jurisprudencial` é o wrapper fino de gate+heartbeat, mesmo molde
de `job_expurgo_entrada_unica` — aqui cobrimos só a plumbing (early-return
com a flag desligada; heartbeat reflete o resumo/erro), não a lógica do
radar em si (já coberta em test_radar_jurisprudencial_orquestrador.py).
Sessão e orquestrador são mockados: o corpo real de `executar_radar` precisa
de Postgres (knowledge_docs.extra é JSONB).
"""
from __future__ import annotations

import json

import app.services.radar_jurisprudencial_orquestrador as orquestrador_mod
from app.services import scheduler


class _SessaoFalsa:
    async def __aenter__(self):
        return "sessao-falsa"

    async def __aexit__(self, *args):
        return False


async def test_flag_desligada_nao_chama_orquestrador_nem_heartbeat(monkeypatch):
    monkeypatch.setattr(scheduler.settings, "RADAR_JURISPRUDENCIAL_ENABLED", False)
    chamou = {"orquestrador": 0, "heartbeat": 0}

    async def _fake_executar_radar(db):
        chamou["orquestrador"] += 1
        return {}

    async def _fake_bater_ponto(*a, **kw):
        chamou["heartbeat"] += 1

    monkeypatch.setattr(orquestrador_mod, "executar_radar", _fake_executar_radar)
    monkeypatch.setattr(scheduler, "_bater_ponto", _fake_bater_ponto)

    await scheduler.job_radar_jurisprudencial()

    assert chamou == {"orquestrador": 0, "heartbeat": 0}


async def test_flag_ligada_chama_orquestrador_e_heartbeat_ok(monkeypatch):
    monkeypatch.setattr(scheduler.settings, "RADAR_JURISPRUDENCIAL_ENABLED", True)
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _SessaoFalsa)
    resumo = {"decisoes_varridas": 3, "alertas_criados": 1, "alertas_duplicados": 0, "erros": 0}
    chamadas = []

    async def _fake_executar_radar(db):
        assert db == "sessao-falsa"
        return resumo

    async def _fake_bater_ponto(job_name, status, detail=None):
        chamadas.append((job_name, status, detail))

    monkeypatch.setattr(orquestrador_mod, "executar_radar", _fake_executar_radar)
    monkeypatch.setattr(scheduler, "_bater_ponto", _fake_bater_ponto)

    await scheduler.job_radar_jurisprudencial()

    assert len(chamadas) == 1
    job_name, status, detail = chamadas[0]
    assert job_name == "radar_jurisprudencial"
    assert status == "ok"
    assert json.loads(detail) == resumo


async def test_resultado_com_erros_marca_heartbeat_como_erro(monkeypatch):
    monkeypatch.setattr(scheduler.settings, "RADAR_JURISPRUDENCIAL_ENABLED", True)
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _SessaoFalsa)
    resumo = {"decisoes_varridas": 2, "alertas_criados": 0, "alertas_duplicados": 0, "erros": 2}
    chamadas = []

    async def _fake_executar_radar(db):
        return resumo

    async def _fake_bater_ponto(job_name, status, detail=None):
        chamadas.append((job_name, status, detail))

    monkeypatch.setattr(orquestrador_mod, "executar_radar", _fake_executar_radar)
    monkeypatch.setattr(scheduler, "_bater_ponto", _fake_bater_ponto)

    await scheduler.job_radar_jurisprudencial()

    assert chamadas[0][1] == "erro"


async def test_excecao_no_orquestrador_vira_heartbeat_de_erro_sem_propagar(monkeypatch):
    monkeypatch.setattr(scheduler.settings, "RADAR_JURISPRUDENCIAL_ENABLED", True)
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _SessaoFalsa)
    chamadas = []

    async def _fake_executar_radar(db):
        raise RuntimeError("banco fora do ar")

    async def _fake_bater_ponto(job_name, status, detail=None):
        chamadas.append((job_name, status, detail))

    monkeypatch.setattr(orquestrador_mod, "executar_radar", _fake_executar_radar)
    monkeypatch.setattr(scheduler, "_bater_ponto", _fake_bater_ponto)

    await scheduler.job_radar_jurisprudencial()  # não deve levantar

    assert chamadas[0][1] == "erro"
    assert json.loads(chamadas[0][2]) == {"erro": "RuntimeError"}
