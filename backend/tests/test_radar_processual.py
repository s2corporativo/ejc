from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.case import CaseFase, CaseStatus
from app.routers import compliance


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Db:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, _query):
        return _Result(self.rows)


@pytest.mark.anyio
async def test_radar_processual_sinaliza_cnj_com_estado_incompativel(monkeypatch):
    caso = SimpleNamespace(
        id="case-1",
        numero_interno="DPT-2026-0001",
        titulo="Caso de teste",
        numero_processo="1234567-89.2026.8.13.0027",
        has_judicial_process=False,
        case_type="extrajudicial",
        status=CaseStatus.aberto,
        fase=CaseFase.pre_processual,
        advogado_responsavel_id="adv-1",
        updated_at=datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(compliance, "_acessa_caso", lambda _u, _c: True)

    itens = await compliance._itens_processual(
        _Db([(caso, False)]),
        SimpleNamespace(),
        desde=None,
        limit=10,
    )

    assert len(itens) == 1
    assert itens[0]["fonte"] == "processual"
    assert itens[0]["nivel_risco"] == "alto"
    assert itens[0]["case_id"] == "case-1"
    assert "processo principal canônico" in itens[0]["resumo"]


@pytest.mark.anyio
async def test_radar_processual_sinaliza_caso_ativo_sem_advogado(monkeypatch):
    caso = SimpleNamespace(
        id="case-2",
        numero_interno="DPT-2026-0002",
        titulo="Sem responsável",
        numero_processo=None,
        has_judicial_process=False,
        case_type="judicial",
        status=CaseStatus.em_instrucao,
        fase=CaseFase.pre_processual,
        advogado_responsavel_id=None,
        updated_at=datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(compliance, "_acessa_caso", lambda _u, _c: True)

    itens = await compliance._itens_processual(
        _Db([(caso, False)]),
        SimpleNamespace(),
        desde=None,
        limit=10,
    )

    assert len(itens) == 1
    assert "sem advogado responsável" in itens[0]["resumo"]
    assert itens[0]["nivel_risco"] == "alto"


@pytest.mark.anyio
async def test_radar_financeiro_sinaliza_recebimento_sem_rateio(monkeypatch):
    pagamento = SimpleNamespace(
        id="pay-1",
        data_pagamento=datetime(2026, 9, 25, tzinfo=timezone.utc).date(),
    )
    fee = SimpleNamespace(case_id="case-3")
    caso = SimpleNamespace(
        id="case-3",
        numero_interno="DPT-2026-0073",
        titulo="Ednaldo x Affare",
        advogado_responsavel_id=None,
    )
    monkeypatch.setattr(compliance, "is_gestao", lambda _u: True)
    monkeypatch.setattr(compliance, "_acessa_caso", lambda _u, _c: True)

    itens = await compliance._itens_financeiro_integridade(
        _Db([(pagamento, fee, caso)]),
        SimpleNamespace(),
        desde=None,
        limit=10,
    )

    assert len(itens) == 1
    assert itens[0]["fonte"] == "financeiro"
    assert "sem rateio econômico" in itens[0]["resumo"]
    assert "sem advogado responsável" in itens[0]["resumo"]


def test_radar_nao_expoe_caso_orfao_para_advogado():
    caso = SimpleNamespace(
        advogado_responsavel_id=None,
        advogado_auxiliar_id=None,
    )
    advogado = SimpleNamespace(
        id="adv-sem-vinculo",
        role=SimpleNamespace(value="advogado"),
    )
    socio = SimpleNamespace(
        id="socio-1",
        role=SimpleNamespace(value="socio"),
    )

    assert compliance._acessa_caso(advogado, caso) is False
    assert compliance._acessa_caso(socio, caso) is True
