from __future__ import annotations

import asyncio

from datetime import date

import pytest
from fastapi import HTTPException

from app.services import deadline_calculator as dc


def test_penal_conta_fim_de_semana_no_meio_do_prazo():
    inicio = date(2026, 8, 14)  # sexta-feira

    penal = dc.calcular_prazo_processual(inicio, 3, "penal")
    civel = dc.calcular_prazo_processual(inicio, 3, "civel")

    assert penal["data_vencimento"] == date(2026, 8, 17)  # sáb+dom contam
    assert civel["data_vencimento"] == date(2026, 8, 19)  # só dias úteis
    assert penal["data_vencimento"] != civel["data_vencimento"]


def test_penal_suspende_recesso_quando_nao_ha_excecao():
    inicio = date(2026, 12, 18)

    resultado = dc.calcular_prazo_processual(inicio, 2, "penal")

    assert resultado["data_vencimento"] == date(2027, 1, 21)
    assert "798-A" in resultado["modo"]


def test_penal_excecao_recesso_precisa_ser_explicita():
    inicio = date(2026, 12, 18)

    resultado = dc.calcular_prazo_processual(
        inicio,
        2,
        "penal",
        excecao_recesso_penal=True,
    )

    # 19/12 conta; 20/12 seria o segundo dia, mas é domingo → prorroga 21/12.
    assert resultado["data_vencimento"] == date(2026, 12, 21)
    assert "exceção ao recesso declarada" in resultado["modo"]


def test_penal_rejeita_dobro_do_cpc():
    with pytest.raises(ValueError, match="não se aplica ao regime penal"):
        dc.calcular_prazo_processual(
            date(2026, 8, 14), 5, "penal", em_dobro=True
        )


def test_calendario_degradado_torna_resultado_preliminar_com_tribunal():
    anterior = dict(dc._CALENDARIO_RUNTIME)
    try:
        dc._CALENDARIO_RUNTIME["feriados_ok"] = True
        dc._CALENDARIO_RUNTIME["suspensoes_ok"] = False
        dc._CALENDARIO_RUNTIME["suspensoes_erro_tipo"] = "RuntimeError"

        resultado = dc.calcular_prazo_processual(
            date(2026, 8, 14), 3, "civel", tribunal="TJMG"
        )

        assert resultado["resultado_preliminar"] is True
        assert resultado["revisao_obrigatoria"] is True
        assert resultado["calendario_status"] == "degradado"
        assert resultado["aviso"]
    finally:
        dc._CALENDARIO_RUNTIME.clear()
        dc._CALENDARIO_RUNTIME.update(anterior)


def test_feriados_falhos_degradam_mesmo_sem_tribunal():
    """Feriado municipal/estadual entra na conta sem depender de tribunal.

    Regressão: o predicado exigia `tribunal` para degradar — cálculo pedido sem
    tribunal saía definitivo mesmo com a tabela `feriados` não carregada.
    """
    anterior = dict(dc._CALENDARIO_RUNTIME)
    try:
        dc._CALENDARIO_RUNTIME["feriados_ok"] = False
        dc._CALENDARIO_RUNTIME["feriados_erro_tipo"] = "OperationalError"
        dc._CALENDARIO_RUNTIME["suspensoes_ok"] = True

        resultado = dc.calcular_prazo_processual(date(2026, 8, 14), 3, "civel")

        assert resultado["resultado_preliminar"] is True
        assert resultado["revisao_obrigatoria"] is True
        assert resultado["calendario_status"] == "degradado"
        assert resultado["aviso"]
    finally:
        dc._CALENDARIO_RUNTIME.clear()
        dc._CALENDARIO_RUNTIME.update(anterior)


@pytest.mark.parametrize(
    "loader,chave",
    [
        ("carregar_feriados_db", "feriados_ok"),
        ("carregar_suspensoes_db", "suspensoes_ok"),
    ],
)
async def test_timeout_de_boot_marca_calendario_como_falho(
    monkeypatch, loader, chave,
):
    """Teto de tempo do boot (`asyncio.timeout`) precisa deixar rastro.

    Regressão do achado P1: `asyncio.timeout` cancela a corrotina injetando
    `CancelledError`, que herda de BaseException e escapava do `except
    Exception` do loader. O estado ficava `None` ("nao_inicializado") e
    `calcular_prazo_processual` devolvia prazo SEM feriados/suspensões e SEM o
    aviso obrigatório de degradação.
    """
    import app.core.database as db_mod

    class _SessaoQueTrava:
        async def __aenter__(self):
            await asyncio.sleep(3600)     # simula banco lento no boot
            return self

        async def __aexit__(self, *_):
            return False

    monkeypatch.setattr(db_mod, "AsyncSessionLocal", lambda: _SessaoQueTrava())

    anterior = dict(dc._CALENDARIO_RUNTIME)
    try:
        dc._CALENDARIO_RUNTIME.update(
            {"feriados_ok": None, "suspensoes_ok": None}
        )

        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.05):
                await getattr(dc, loader)()

        assert dc._CALENDARIO_RUNTIME[chave] is False
        assert dc._CALENDARIO_RUNTIME[chave.replace("_ok", "_erro_tipo")] == (
            "CancelledError"
        )
        assert dc.calendario_runtime_status()["status"] == "degradado"

        resultado = dc.calcular_prazo_processual(
            date(2026, 8, 14), 3, "civel", tribunal="TJMG"
        )
        assert resultado["resultado_preliminar"] is True
        assert resultado["revisao_obrigatoria"] is True
        assert resultado["aviso"]
    finally:
        dc._CALENDARIO_RUNTIME.clear()
        dc._CALENDARIO_RUNTIME.update(anterior)


@pytest.mark.anyio
async def test_calculadora_bloqueia_processual_corrido_sem_regime():
    from app.routers.deadlines import calcular
    from app.schemas.deadline import CalcularPrazoRequest

    req = CalcularPrazoRequest(
        data_inicio=date(2026, 8, 14),
        dias=3,
        tipo="processual",
        dias_uteis=False,
    )

    with pytest.raises(HTTPException) as exc:
        await calcular(req=req, cu=object())

    assert exc.value.status_code == 422
    assert "regime_calculo explícito" in str(exc.value.detail)


@pytest.mark.anyio
async def test_calculadora_penal_ignora_flag_legada_dias_uteis():
    from app.routers.deadlines import calcular
    from app.schemas.deadline import CalcularPrazoRequest

    req = CalcularPrazoRequest(
        data_inicio=date(2026, 8, 14),
        dias=3,
        tipo="processual",
        dias_uteis=True,  # legado; regime explícito prevalece
        regime_calculo="penal",
    )

    resultado = await calcular(req=req, cu=object())

    assert resultado["regime_calculo"] == "penal"
    assert resultado["data_vencimento"] == date(2026, 8, 17)
    assert resultado["regime_assumido_por_compatibilidade"] is False
