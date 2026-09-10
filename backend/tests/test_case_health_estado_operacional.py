"""Regressões do estado operacional do Case Health.

O estado operacional deve ser factual e estável mesmo se os pesos numéricos do
score legado forem recalibrados no futuro.
"""
from app.services.case_health import _estado_operacional


def test_estado_normal_sem_fatores():
    assert _estado_operacional([]) == "normal"


def test_estado_atencao_com_pendencia_nao_bloqueante():
    assert _estado_operacional(
        [{"fator": "prazo_critico_sem_ciencia", "impacto": -10}]
    ) == "atencao"


def test_estado_critico_com_prazo_vencido_independe_do_score():
    fatores = [
        {"fator": "sem_movimentacao", "impacto": -15},
        {"fator": "prazo_vencido", "impacto": -20},
    ]
    assert _estado_operacional(fatores) == "critico"


def test_fator_desconhecido_degrada_para_atencao_sem_inventar_criticidade():
    assert _estado_operacional([{"fator": "futuro_fator", "impacto": -99}]) == "atencao"
