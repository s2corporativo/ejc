"""A crítica adversarial nunca pode falhar silenciosamente para o HITL."""
from app.services.ai.core.hitl_policy import _propagar_alertas_critica


def test_falha_da_segunda_ia_propaga_aviso_e_alertas_sem_duplicar():
    resultado = {
        "alertas": ["Alerta já existente"],
        "critica_adversarial": {
            "disponivel": False,
            "aviso": "Crítica adversarial indisponível; reforce a revisão humana.",
            "alertas": ["Falha na IA Crítica: timeout", "Alerta já existente"],
        },
    }

    _propagar_alertas_critica(resultado)

    assert resultado["alertas"] == [
        "Alerta já existente",
        "Falha na IA Crítica: timeout",
        "Crítica adversarial indisponível; reforce a revisão humana.",
    ]


def test_critica_disponivel_propaga_alertas_de_provider_e_citacao_sem_aviso_generico():
    resultado = {
        "alertas": [],
        "critica_adversarial": {
            "disponivel": True,
            "aviso": "Relatório de IA sujeito a revisão humana.",
            "alertas": [
                "Crítica executada no mesmo provider.",
                "Gate de citações indisponível; verifique manualmente.",
            ],
        },
    }

    _propagar_alertas_critica(resultado)

    assert resultado["alertas"] == [
        "Crítica executada no mesmo provider.",
        "Gate de citações indisponível; verifique manualmente.",
    ]
    assert "Relatório de IA sujeito a revisão humana." not in resultado["alertas"]


def test_sem_critica_nao_altera_alertas():
    resultado = {"alertas": ["x"], "critica_adversarial": None}
    _propagar_alertas_critica(resultado)
    assert resultado["alertas"] == ["x"]
