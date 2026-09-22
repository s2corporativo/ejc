"""Núcleo de inteligência documental e jurídica da Entrada Única.

Este pacote contém apenas contratos e normalização determinística. Os modelos de
IA continuam sendo chamados pelo gateway/orquestrador existente; nenhuma chamada
paralela a provedor é criada aqui.
"""
from .diff import comparar_inteligencia
from .schemas import CaseIntelligence, build_case_intelligence, build_document_intelligence

__all__ = [
    "CaseIntelligence",
    "build_case_intelligence",
    "build_document_intelligence",
    "comparar_inteligencia",
]
