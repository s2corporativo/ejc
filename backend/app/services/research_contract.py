"""Contrato de saída da pesquisa jurídica do EJC.

A camada é determinística: classifica proveniência, expõe limites e não tenta
substituir o advogado ou inferir fatos ausentes. O texto da IA continua sendo
rascunho; este envelope torna a incerteza visível para a UI e para auditoria.
"""
from __future__ import annotations

from typing import Any


_AUTHORITY_BY_CATEGORY = {
    "legislacao": "norma_vigente",
    "legislacao_federal": "norma_vigente",
    "legislacao_estadual": "norma_vigente",
    "legislacao_municipal": "norma_vigente",
    "sumula_stf": "precedente_vinculante",
    "sumula_stj": "jurisprudencia_persuasiva",
    "sumula_tst": "jurisprudencia_persuasiva",
    "jurisprudencia": "jurisprudencia_persuasiva",
    "jurisprudencia_estruturada": "precedente_vinculante",
    "referencia_legislativa": "norma_vigente",
    "referencia_interna": "material_interno",
    "modelo_documento_juridico": "material_interno",
}

_ALWAYS_LIMITS = [
    "A resposta é rascunho de IA e exige revisão de advogado antes de uso externo.",
    "A autoridade recuperada não prova, sozinha, a aplicação ao caso: conferir fatos, prova, competência, vigência e produção de efeitos.",
    "Não inferir prazo, valor, dano, probabilidade de êxito ou resultado processual sem documentos e cronologia completos.",
]


def _extra(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("extra")
    return value if isinstance(value, dict) else {}


def classificar_autoridade(item: dict[str, Any]) -> str:
    """Classifica a autoridade sem promover conteúdo interno automaticamente."""
    extra = _extra(item)
    taxonomy = extra.get("taxonomy")
    if isinstance(taxonomy, dict) and taxonomy.get("authority_type"):
        return str(taxonomy["authority_type"])
    if extra.get("ficticio") is True or extra.get("origem") in {"seed_interno_curado", "modelo"}:
        return "material_interno"
    category = str(item.get("categoria") or "").lower()
    if category in _AUTHORITY_BY_CATEGORY:
        return _AUTHORITY_BY_CATEGORY[category]
    title = str(item.get("titulo") or "").lower()
    if "súmula vinculante" in title:
        return "precedente_vinculante"
    if "tema repetitivo" in title or "repercussão geral" in title:
        return "precedente_vinculante"
    if "súmula" in title:
        return "jurisprudencia_persuasiva"
    if item.get("fonte"):
        return "fonte_oficial_nao_classificada"
    return "material_interno"


def montar_fonte(item: dict[str, Any]) -> dict[str, Any]:
    extra = _extra(item)
    autoridade = classificar_autoridade(item)
    fonte = {
        "doc_id": item.get("doc_id"),
        "titulo": item.get("titulo"),
        "categoria": item.get("categoria"),
        "autoridade": autoridade,
        "fonte_oficial": item.get("fonte"),
        "tribunal": item.get("tribunal") or extra.get("tribunal"),
        "identificador": extra.get("identificador") or extra.get("numero_processo") or item.get("chave_origem"),
        "versao": item.get("versao"),
        "atualizado_em": item.get("atualizado_em") or extra.get("last_verified_at"),
        "vigente": item.get("vigente", True),
        "revisado": item.get("revisado", True),
        "confianca": item.get("confianca") or extra.get("confidence_level"),
    }
    warnings: list[str] = []
    if autoridade == "material_interno":
        warnings.append("Material interno: não citar como lei, súmula ou decisão oficial.")
    if not fonte["fonte_oficial"]:
        warnings.append("Sem URL oficial associada; não usar como autoridade jurídica externa.")
    if fonte["vigente"] is False:
        warnings.append("Versão não vigente: usar somente para histórico, nunca como regra atual.")
    if fonte["revisado"] is False:
        warnings.append("Documento ainda não revisado manualmente no fluxo de governança.")
    if warnings:
        fonte["alertas"] = warnings
    return fonte


def montar_lacunas(pergunta: str, contexto: list[dict[str, Any]]) -> list[str]:
    lacunas: list[str] = []
    if not contexto:
        lacunas.append("A base não retornou fonte relevante; não produzir conclusão jurídica afirmativa.")
    if contexto and not any(c.get("fonte") for c in contexto):
        lacunas.append("As fontes recuperadas não têm URL oficial associada; confirmar a autoridade antes de citar.")
    if contexto and not any(classificar_autoridade(c) in {"norma_vigente", "precedente_vinculante"} for c in contexto):
        lacunas.append("A recuperação não contém norma vigente ou precedente qualificado; pesquisar fonte primária.")
    lacunas.extend([
        "Fatos, datas, documentos e competência não foram fornecidos ou validados pelo sistema.",
        "Vigência, modulação e decisões posteriores devem ser conferidas na fonte oficial na data do uso.",
        "A prova necessária para sustentar a tese ainda precisa ser identificada pelo advogado.",
    ])
    return list(dict.fromkeys(lacunas))


def montar_envelope(*, resposta: str, pergunta: str, contexto: list[dict[str, Any]],
                    pii_removida: bool, log_id: Any) -> dict[str, Any]:
    fontes = [montar_fonte(c) for c in contexto]
    return {
        "resposta": resposta,
        "modo": "pesquisa_juridica_grounded",
        "rascunho": True,
        "revisao_humana_obrigatoria": True,
        "pergunta_sanitizada": pergunta,
        "fontes": fontes,
        "fontes_relevantes": len(fontes),
        "lacunas": montar_lacunas(pergunta, contexto),
        "limites": list(_ALWAYS_LIMITS),
        "pii_removida": bool(pii_removida),
        "ai_log_id": log_id,
    }
