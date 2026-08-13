"""Testes LEGADOS do router diplomacia_v3.py (arquivado em _dead_code na consolidação de 12/08/2026). Não coletados pelo pytest (prefixo
`legacy_`) — mantidos como documentação da semântica removida (calcular-acordo com Selic BCB) e para eventual restauração."""

async def test_calcular_acordo_router_usa_selic_do_bcb(monkeypatch):
    """Regressão: o endpoint usava DiplomaciaDigital() com o default fixo
    (10,75%) e nunca consultava o BCB. Agora deve usar selic_anualizada()."""
    from app.routers import diplomacia_v3

    async def fake_selic():
        return {"selic_anual": 0.20, "fonte": "bcb", "meses_compostos": 12}

    monkeypatch.setattr(diplomacia_v3.bcb_service, "selic_anualizada", fake_selic)

    payload = {"valor_causa": 100_000.0, "prob_exito": 0.7, "tempo_anos": 2.0}
    r = await diplomacia_v3.calcular_acordo(payload, cu=None)

    assert r["selic_anual"] == 0.20
    vpl = 70_000.0 / (1.20 ** 2)
    assert r["valor_presente_liquido"] == pytest.approx(vpl, abs=0.01)


async def test_calcular_acordo_router_respeita_selic_informada(monkeypatch):
    """Se o cliente informar selic_anual explicitamente, não deve bater no BCB."""
    from app.routers import diplomacia_v3

    async def bcb_nao_deveria_ser_chamado():
        raise AssertionError("BCB não deveria ser consultado com selic informada")

    monkeypatch.setattr(diplomacia_v3.bcb_service, "selic_anualizada",
                         bcb_nao_deveria_ser_chamado)

    payload = {"valor_causa": 100_000.0, "prob_exito": 0.7, "tempo_anos": 2.0,
               "selic_anual": 0.05}
    r = await diplomacia_v3.calcular_acordo(payload, cu=None)
    assert r["selic_anual"] == 0.05
