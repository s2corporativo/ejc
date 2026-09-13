from __future__ import annotations

from app.services.scheduler import _hora_utc_do_job


def test_horario_valido_e_respeitado():
    assert _hora_utc_do_job("07:30", padrao=(11, 0), rotulo="TESTE") == (7, 30)
    assert _hora_utc_do_job("23:59", padrao=(11, 0), rotulo="TESTE") == (23, 59)


def test_horario_malformado_degrada_sem_derrubar_boot():
    for valor in ("11h00", "", None, "25:00", "10:99", "abc", "12"):
        assert _hora_utc_do_job(valor, padrao=(11, 0), rotulo="TESTE") == (11, 0)
