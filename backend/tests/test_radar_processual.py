from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.case import CaseFase, CaseStatus
from app.routers import compliance


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _Db:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, _query):
        return _ScalarResult(self.rows)


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
        updated_at=datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(compliance, "_acessa_caso", lambda _u, _c: True)

    itens = await compliance._itens_processual(
        _Db([caso]),
        SimpleNamespace(),
        desde=None,
        limit=10,
    )

    assert len(itens) == 1
    assert itens[0]["fonte"] == "processual"
    assert itens[0]["nivel_risco"] == "alto"
    assert itens[0]["case_id"] == "case-1"
    assert "1234567-89.2026.8.13.0027" in itens[0]["resumo"]
    assert "fase ainda pré-processual" in itens[0]["resumo"]
