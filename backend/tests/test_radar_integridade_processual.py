from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.user import UserRole
from app.routers import compliance


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Db:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, _query):
        return _Rows(self.rows)


@pytest.mark.anyio
async def test_radar_alerta_pre_processual_com_cnj_respeita_ownership():
    agora = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
    visivel = SimpleNamespace(
        id="case-1",
        numero_interno="DPT-2026-0099",
        titulo="Caso visível",
        updated_at=agora,
        advogado_responsavel_id="adv-1",
        advogado_auxiliar_id=None,
    )
    oculto = SimpleNamespace(
        id="case-2",
        numero_interno="DPT-2026-0100",
        titulo="Caso de outro advogado",
        updated_at=agora,
        advogado_responsavel_id="adv-2",
        advogado_auxiliar_id=None,
    )
    proc_visivel = SimpleNamespace(
        numero_cnj="1018284-13.2026.8.13.0027",
        updated_at=agora,
    )
    proc_oculto = SimpleNamespace(
        numero_cnj="1015352-52.2026.8.13.0027",
        updated_at=agora,
    )
    user = SimpleNamespace(id="adv-1", role=UserRole.advogado)

    itens = await compliance._itens_integridade_processual(
        _Db([(visivel, proc_visivel), (oculto, proc_oculto)]),
        user,
        desde=None,
        hoje=date(2026, 9, 25),
        limit=10,
    )

    assert len(itens) == 1
    assert itens[0]["fonte"] == "integridade_processual"
    assert itens[0]["case_id"] == "case-1"
    assert itens[0]["nivel_risco"] == "alto"
    assert "1018284-13.2026.8.13.0027" in itens[0]["resumo"]


@pytest.mark.anyio
async def test_radar_integridade_respeita_filtro_desde():
    antigo = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    case = SimpleNamespace(
        id="case-1",
        numero_interno="DPT-2026-0099",
        titulo="Caso antigo",
        updated_at=antigo,
        advogado_responsavel_id=None,
        advogado_auxiliar_id=None,
    )
    process = SimpleNamespace(
        numero_cnj="1018284-13.2026.8.13.0027",
        updated_at=antigo,
    )
    socio = SimpleNamespace(id="socio-1", role=UserRole.socio)

    itens = await compliance._itens_integridade_processual(
        _Db([(case, process)]),
        socio,
        desde=date(2026, 9, 20),
        hoje=date(2026, 9, 25),
        limit=10,
    )

    assert itens == []
