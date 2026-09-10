from datetime import date

from app.services import deadline_calculator as dc


def _set_calendario_validado() -> None:
    dc._CALENDARIO_RUNTIME["feriados_ok"] = True
    dc._CALENDARIO_RUNTIME["suspensoes_ok"] = True
    dc._CALENDARIO_RUNTIME["feriados_erro_tipo"] = None
    dc._CALENDARIO_RUNTIME["suspensoes_erro_tipo"] = None


def test_processual_sem_tribunal_e_preliminar_mesmo_com_calendario_validado():
    _set_calendario_validado()

    resultado = dc.calcular_prazo_processual(
        date(2026, 9, 10),
        5,
        "civel",
        tribunal=None,
    )

    assert resultado["resultado_preliminar"] is True
    assert resultado["revisao_obrigatoria"] is True
    assert "Tribunal não informado" in (resultado["aviso"] or "")


def test_processual_com_tribunal_e_calendario_validado_pode_ser_definitivo():
    _set_calendario_validado()

    resultado = dc.calcular_prazo_processual(
        date(2026, 9, 10),
        5,
        "civel",
        tribunal="TJMG",
    )

    assert resultado["resultado_preliminar"] is False
    assert resultado["revisao_obrigatoria"] is False
    assert resultado["aviso"] is None


def test_estado_degradacao_generico_preserva_uso_sem_tribunal():
    _set_calendario_validado()

    assert dc.estado_degradacao(None) == (False, None)


def test_estado_degradacao_processual_exige_tribunal_quando_solicitado():
    _set_calendario_validado()

    degradado, aviso = dc.estado_degradacao(None, exigir_tribunal=True)

    assert degradado is True
    assert "Tribunal não informado" in (aviso or "")

def test_sem_tribunal_combina_falha_de_suspensoes_no_aviso():
    _set_calendario_validado()
    dc._CALENDARIO_RUNTIME["suspensoes_ok"] = False
    dc._CALENDARIO_RUNTIME["suspensoes_erro_tipo"] = "RuntimeError"

    degradado, aviso = dc.estado_degradacao(None, exigir_tribunal=True)

    assert degradado is True
    assert "Tribunal não informado" in (aviso or "")
    assert "Calendário local/suspensões indisponível" in (aviso or "")

    _set_calendario_validado()
