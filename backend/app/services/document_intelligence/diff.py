"""Comparação segura entre estados de inteligência do caso."""
from __future__ import annotations

from typing import Any


_TRACKED = (
    ("classificacao", "classificação"),
    ("partes", "partes"),
    ("fatos", "fatos"),
    ("cronologia", "cronologia"),
    ("questoes_juridicas", "questões jurídicas"),
    ("informacoes_faltantes", "informações faltantes"),
    ("provas_necessarias", "provas necessárias"),
    ("riscos", "riscos"),
    ("estrategias", "estratégias"),
    ("honorarios", "honorários"),
)


def _canon(value: Any) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def comparar_inteligencia(anterior: dict[str, Any] | None,
                           atual: dict[str, Any]) -> dict[str, Any]:
    """Retorna somente mudanças observáveis, sem afirmar impacto jurídico.

    O resultado é uma proposta de revisão: impacto em tese, risco ou estratégia
    nunca é promovido automaticamente. A comparação é deliberadamente
    determinística para ser auditável e independente de LLM.
    """
    antigo = anterior if isinstance(anterior, dict) else {}
    alteracoes: list[dict[str, Any]] = []
    aliases = {
        "classificacao": ("classificacao", "area"),
        "fatos": ("fatos",),
        "provas_necessarias": ("provas_necessarias", "provas"),
        "estrategias": ("estrategias", "plano_juridico"),
        "questoes_juridicas": ("questoes_juridicas", "teses"),
    }
    for chave, rotulo in _TRACKED:
        before = next((antigo.get(nome) for nome in aliases.get(chave, (chave,))
                       if nome in antigo), None)
        after = atual.get(chave)
        if _canon(before) == _canon(after):
            continue
        alteracoes.append({
            "campo": chave,
            "rotulo": rotulo,
            "anterior": before,
            "atual": after,
            "impacto_a_confirmar": chave in {
                "fatos", "cronologia", "questoes_juridicas", "provas_necessarias",
                "riscos", "estrategias", "honorarios",
            },
            "requer_revisao_humana": True,
        })
    return {
        "houve_alteracao": bool(alteracoes),
        "campos_alterados": [item["campo"] for item in alteracoes],
        "alteracoes": alteracoes,
        "aviso": "Comparação determinística; impacto jurídico exige revisão do advogado.",
    }
