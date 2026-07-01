"""
Motor de Honorários EJC v4.0 - Tabela OAB/MG (Etapa 4).
Cálculo automático e sugestões baseadas na complexidade e valor da causa.
"""
from typing import Dict, Any

# Aviso REFERENCIAL — esta tabela é uma simplificação interna para estimativa
# rápida e NÃO substitui a Tabela de Honorários OAB/MG oficial vigente, que deve
# sempre prevalecer. Conferir os valores na tabela oficial antes de qualquer uso.
AVISO_REFERENCIAL = (
    "Valores REFERENCIAIS — estimativa interna simplificada. NÃO substitui a "
    "Tabela de Honorários OAB/MG oficial vigente, que prevalece. Confirme na "
    "tabela oficial antes de propor honorários."
)


class MotorHonorariosOAB:
    def __init__(self):
        # Valores base simplificados — REFERENCIAIS (ver AVISO_REFERENCIAL).
        # NÃO substituem a Tabela OAB/MG oficial vigente.
        self.tabela = {
            "trabalhista": {"base": 3500.0, "percentual": 0.30},
            "civel": {"base": 4500.0, "percentual": 0.20},
            "tributario": {"base": 10000.0, "percentual": 0.15},
            "empresarial": {"base": 8000.0, "percentual": 0.20}
        }

    def calcular_sugestao(self, area: str, valor_causa: float) -> Dict[str, Any]:
        config = self.tabela.get(area.lower(), {"base": 3000.0, "percentual": 0.20})
        valor_percentual = valor_causa * config["percentual"]
        sugestao = max(config["base"], valor_percentual)

        return {
            "valor_sugerido": sugestao,
            "valor_base_tabela": config["base"],
            "percentual_exito": config["percentual"],
            "is_referencial": True,
            "aviso": AVISO_REFERENCIAL,
        }

motor_honorarios = MotorHonorariosOAB()
