from __future__ import annotations

from datetime import date, datetime

import pytest

from app.services import agenda_interval_service as svc


def _intervalo(
    inicio="2026-09-01T09:00:00",
    fim="2026-09-01T10:00:00",
):
    return svc.normalizar_intervalo(
        inicio_em=datetime.fromisoformat(inicio),
        fim_em=datetime.fromisoformat(fim),
        timezone="America/Sao_Paulo",
    )


def test_intervalo_exige_fim_posterior():
    with pytest.raises(svc.AgendaTemporalError, match="posterior"):
        svc.normalizar_intervalo(
            inicio_em=datetime(2026, 9, 1, 10, 0),
            fim_em=datetime(2026, 9, 1, 9, 0),
        )


def test_timezone_invalido_e_rejeitado():
    with pytest.raises(svc.AgendaTemporalError, match="timezone inválido"):
        svc.normalizar_intervalo(
            inicio_em=datetime(2026, 9, 1, 9, 0),
            fim_em=datetime(2026, 9, 1, 10, 0),
            timezone="America/Timezone-Inexistente",
        )


def test_intervalo_half_open_detecta_sobreposicao_real():
    base = _intervalo()
    parcial = _intervalo("2026-09-01T09:30:00", "2026-09-01T10:30:00")
    contido = _intervalo("2026-09-01T09:15:00", "2026-09-01T09:45:00")
    encosta = _intervalo("2026-09-01T10:00:00", "2026-09-01T11:00:00")
    separado = _intervalo("2026-09-01T11:00:00", "2026-09-01T12:00:00")

    assert svc.intervalos_sobrepoem(base, parcial) is True
    assert svc.intervalos_sobrepoem(base, contido) is True
    assert svc.intervalos_sobrepoem(base, encosta) is False
    assert svc.intervalos_sobrepoem(base, separado) is False


def test_dia_inteiro_normaliza_para_intervalo_de_um_dia():
    intervalo = svc.normalizar_intervalo(
        inicio_em=datetime(2026, 9, 1, 14, 30),
        fim_em=None,
        dia_inteiro=True,
    )
    assert intervalo.inicio.isoformat().startswith("2026-09-01T00:00:00")
    assert intervalo.fim.isoformat().startswith("2026-09-02T00:00:00")
    assert intervalo.duracao_minutos == 1440


def test_lembretes_preservam_default_de_audiencia():
    assert svc.normalizar_lembretes(None, tipo="audiencia") == (4320, 1440, 0)
    assert svc.normalizar_lembretes(None, tipo="reuniao") == ()


def test_lembretes_configuraveis_deduplicam_e_ordenam():
    assert svc.normalizar_lembretes([60, 1440, 60, 15], tipo="reuniao") == (
        1440,
        60,
        15,
    )
    assert svc.normalizar_lembretes([], tipo="audiencia") == ()


def test_lembrete_invalido_e_rejeitado():
    with pytest.raises(svc.AgendaTemporalError, match="negativo"):
        svc.normalizar_lembretes([-1], tipo="reuniao")
    with pytest.raises(svc.AgendaTemporalError, match="90 dias"):
        svc.normalizar_lembretes([svc.MAX_LEMBRETE_MINUTOS + 1], tipo="reuniao")


def test_recorrencia_semanal_preserva_horario_e_duracao():
    base = _intervalo()
    ocorrencias = svc.expandir_recorrencia(
        base,
        svc.RegraRecorrencia(frequencia="semanal", quantidade=3),
    )
    assert [o.inicio.date().isoformat() for o in ocorrencias] == [
        "2026-09-01",
        "2026-09-08",
        "2026-09-15",
    ]
    assert {o.duracao_minutos for o in ocorrencias} == {60}


def test_recorrencia_excecao_remove_ocorrencia_sem_deslocar_serie():
    base = _intervalo()
    ocorrencias = svc.expandir_recorrencia(
        base,
        svc.RegraRecorrencia(frequencia="diaria", quantidade=4),
        excecoes_inicio=[datetime(2026, 9, 2, 9, 0)],
    )
    assert [o.inicio.date().isoformat() for o in ocorrencias] == [
        "2026-09-01",
        "2026-09-03",
        "2026-09-04",
    ]


def test_recorrencia_mensal_ajusta_fim_do_mes_sem_erro():
    base = _intervalo("2026-01-31T09:00:00", "2026-01-31T10:00:00")
    ocorrencias = svc.expandir_recorrencia(
        base,
        svc.RegraRecorrencia(frequencia="mensal", quantidade=3),
    )
    assert [o.inicio.date().isoformat() for o in ocorrencias] == [
        "2026-01-31",
        "2026-02-28",
        "2026-03-28",
    ]


def test_recorrencia_sem_fim_e_rejeitada():
    with pytest.raises(svc.AgendaTemporalError, match="quantidade ou data limite"):
        svc.expandir_recorrencia(
            _intervalo(),
            svc.RegraRecorrencia(frequencia="diaria"),
        )


def test_legado_sem_hora_nao_recebe_horario_inventado():
    assert (
        svc.legado_para_intervalo(
            data_evento=date(2026, 9, 1),
            hora=None,
        )
        is None
    )


def test_legado_com_hora_tem_adapter_conservador_nao_persistente():
    intervalo = svc.legado_para_intervalo(
        data_evento=date(2026, 9, 1),
        hora="09:30",
        duracao_padrao_minutos=60,
    )
    assert intervalo is not None
    assert intervalo.inicio.hour == 9
    assert intervalo.inicio.minute == 30
    assert intervalo.fim.hour == 10
    assert intervalo.fim.minute == 30
