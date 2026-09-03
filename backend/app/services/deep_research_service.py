"""
Deep Research Jurídica v1.

Pesquisa multi-etapa síncrona, sem migration e sem job persistente. A versão v1
combina RAG interno, precedentes multi-fonte e síntese pelo AI Gateway central.
Tudo é marcado como rascunho sujeito a revisão humana.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_log import AILog, AITipoUso, AIStatusHITL
from app.services.ai.entidades_caso import entidades_do_caso
from app.services.ai_cost import estimar_custo_brl
from app.services.ai_gateway import chat as gw_chat
from app.services.ai_service import buscar_contexto_rag
from app.services.crawler_precedentes import buscar_precedentes
from app.services.sanitizer import sanitizar_pii


@dataclass
class DeepResearchInput:
    tese: str
    fatos: str
    area: str | None = None
    case_id: str | None = None
    scope_client_id: str | None = None
    numero_cnj: str | None = None
    fontes_externas: list[str] | None = None
    max_subquestoes: int = 5


def _cortar(texto: str, limite: int) -> str:
    texto = (texto or "").strip()
    return texto[:limite]


def _formatar_rag(fontes: list[dict[str, Any]]) -> str:
    if not fontes:
        return "Nenhuma fonte interna localizada."
    linhas = []
    for i, f in enumerate(fontes, 1):
        linhas.append(
            f"[RAG {i}] {f.get('titulo') or 'Sem titulo'} | {f.get('categoria') or ''} | {f.get('fonte') or ''}\n"
            f"{_cortar(f.get('conteudo') or '', 900)}"
        )
    return "\n\n".join(linhas)


def _formatar_precedentes(precedentes: list[dict[str, Any]]) -> str:
    if not precedentes:
        return "Nenhum precedente externo confirmado localizado."
    linhas = []
    for i, p in enumerate(precedentes[:8], 1):
        linhas.append(
            f"[PRECEDENTE {i}] {p.get('tribunal') or ''} {p.get('numero_acordao') or ''} | {p.get('fonte') or ''}\n"
            f"Titulo: {p.get('titulo') or ''}\n"
            f"Ementa: {_cortar(p.get('ementa') or '', 900)}\n"
            f"Link: {p.get('link_original') or ''}"
        )
    return "\n\n".join(linhas)


def _subquestoes_deterministicas(tese: str, fatos: str, area: str | None, max_subquestoes: int) -> list[str]:
    base = [
        f"Cabimento jurídico da tese: {tese}",
        "Fundamentos legais e requisitos materiais aplicáveis",
        "Precedentes e entendimentos jurisprudenciais verificáveis",
        "Riscos processuais, ônus probatório e teses adversas",
        "Documentos, provas e providências recomendadas",
    ]
    if area:
        base.insert(1, f"Enquadramento específico na área {area}")
    if "prazo" in fatos.lower() or "prescri" in fatos.lower():
        base.append("Prescrição, decadência, tempestividade e marcos temporais")
    return base[: max(1, min(max_subquestoes, 8))]


async def decompor_tese(
    tese: str, fatos: str, area: str | None, max_subquestoes: int = 5,
    *, uso: list | None = None, entidades: dict[str, list[str]] | None = None,
) -> list[str]:
    """Decompõe a tese em subquestões. `uso` (opcional) acumula a resposta do
    gateway para que o chamador some tokens/custo das DUAS chamadas no AILog
    (B7); `entidades` pseudonimiza os nomes do caso de forma reversível."""
    fallback = _subquestoes_deterministicas(tese, fatos, area, max_subquestoes)
    try:
        resp = await gw_chat(
            messages=[
                {"role": "system", "content": "Você decompõe pesquisas jurídicas em subquestões objetivas. Não responda o mérito."},
                {"role": "user", "content": (
                    f"Tese: {_cortar(tese, 500)}\nÁrea: {area or 'não informada'}\n"
                    f"Fatos: {_cortar(fatos, 1200)}\n\n"
                    f"Liste até {max_subquestoes} subquestões de pesquisa, uma por linha, sem comentários."
                )},
            ],
            task_type="analise_juridica",
            temperature=0.1,
            max_tokens=500,
            entidades=entidades,
        )
        if uso is not None:
            uso.append(resp)
        linhas = [l.strip("-• 0123456789.\t") for l in resp.texto.splitlines() if l.strip()]
        linhas = [l for l in linhas if len(l) >= 12]
        return (linhas or fallback)[:max_subquestoes]
    except Exception:
        return fallback


def _somar_uso(respostas: list) -> tuple[int | None, int | None, Decimal | None]:
    """Soma tokens e custo estimado (R$) das respostas do gateway. Tokens
    ausentes em TODAS as respostas → None (não inventa zero); custo pela
    tabela de preços de `ai_cost` (provedor/modelo de cada chamada)."""
    tokens_in = tokens_out = 0
    tem_tokens = False
    custo = Decimal("0")
    for r in respostas:
        ti = getattr(r, "input_tokens", None)
        to = getattr(r, "output_tokens", None)
        if ti is not None or to is not None:
            tem_tokens = True
        tokens_in += int(ti or 0)
        tokens_out += int(to or 0)
        custo += estimar_custo_brl(
            getattr(r, "provedor", "") or "", ti, to, getattr(r, "modelo", None)
        )
    if not tem_tokens:
        return None, None, None
    return tokens_in, tokens_out, custo


async def executar_deep_research(db: AsyncSession, entrada: DeepResearchInput, *, user_id: str) -> dict[str, Any]:
    tese_limpa, _ = sanitizar_pii(_cortar(entrada.tese, 1000))
    fatos_limpos, _ = sanitizar_pii(_cortar(entrada.fatos, 6000))
    area = _cortar(entrada.area or "", 80) or None

    # Pseudonimização REVERSÍVEL dos nomes do caso (mesmo padrão de
    # ai_service.detectar_teses_ocultas): com case_id, o gateway troca os
    # nomes por placeholders antes do provedor e reidrata na volta.
    entidades = None
    if entidade_case := entrada.case_id:
        entidades = await entidades_do_caso(db, entidade_case) or None

    usos: list = []   # respostas do gateway (decomposição + síntese) p/ custo
    subquestoes = await decompor_tese(
        tese_limpa, fatos_limpos, area, entrada.max_subquestoes,
        uso=usos, entidades=entidades,
    )
    consultas = [f"{area or ''} {tese_limpa} {q}".strip() for q in subquestoes]

    fontes_rag: list[dict[str, Any]] = []
    for consulta in consultas[:6]:
        fontes_rag.extend(await buscar_contexto_rag(
            db, consulta, limite=4,
            scope_client_id=entrada.scope_client_id,
            # C4: comunicação processual de OUTRO caso do mesmo cliente fica fora.
            scope_case_id=entrada.case_id,
        ))

    vistos = set()
    rag_unico = []
    for f in fontes_rag:
        chave = f.get("chunk_id") or f.get("fonte") or (f.get("conteudo") or "")[:120]
        if chave in vistos:
            continue
        vistos.add(chave)
        rag_unico.append(f)

    precedentes = await buscar_precedentes(
        termo=f"{area or ''} {tese_limpa}".strip(),
        fontes=entrada.fontes_externas or ["lexml", "tjmg"],
        numero_cnj=entrada.numero_cnj,
        por_pagina=8,
    )
    lista_precedentes = precedentes.get("precedentes") or []

    sistema = (
        "Você é pesquisador jurídico sênior de um escritório brasileiro. "
        "Faça deep research com rigor, sem inventar fontes, julgados, artigos, links ou números. "
        "Use apenas as fontes RAG e precedentes fornecidos. Se faltar base, declare a lacuna. "
        "A resposta é rascunho para revisão humana obrigatória."
    )
    usuario = (
        f"TESE:\n{tese_limpa}\n\nÁREA:\n{area or 'não informada'}\n\nFATOS:\n{fatos_limpos}\n\n"
        f"SUBQUESTÕES:\n" + "\n".join(f"- {q}" for q in subquestoes) + "\n\n"
        f"FONTES INTERNAS RAG:\n{_formatar_rag(rag_unico[:12])}\n\n"
        f"PRECEDENTES EXTERNOS:\n{_formatar_precedentes(lista_precedentes)}\n\n"
        "Entregue em seções: conclusão executiva, fundamentos, precedentes aplicáveis, pontos fracos, provas necessárias, estratégia recomendada e lacunas de fonte."
    )

    resp = await gw_chat(
        messages=[{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
        task_type="analise_juridica",
        temperature=0.15,
        max_tokens=3500,
        entidades=entidades,
    )
    usos.append(resp)
    tokens_in, tokens_out, custo = _somar_uso(usos)

    resultado = {
        "status": "ok",
        "modo": "deep_research_v1_sincrono",
        "tese": tese_limpa,
        "area": area,
        "subquestoes": subquestoes,
        "fontes_rag_total": len(rag_unico),
        "precedentes_total": len(lista_precedentes),
        "fontes_externas": precedentes.get("fontes", {}),
        "resposta": resp.texto,
        "aviso": "Rascunho gerado por IA. Revisão humana obrigatória antes de uso jurídico.",
    }

    log = AILog(
        id=str(uuid4()),
        user_id=user_id,
        case_id=entrada.case_id,
        tipo_uso=AITipoUso.analise_caso,
        modelo=getattr(resp, "modelo", None) or "deep-research-v1",
        prompt_sanitizado=f"DEEP_RESEARCH_V1\nTese: {tese_limpa[:500]}\nSubquestoes: {json.dumps(subquestoes, ensure_ascii=False)[:1000]}",
        resposta=json.dumps(resultado, ensure_ascii=False)[:8000],
        fontes_rag=json.dumps({"rag": rag_unico[:8], "precedentes": lista_precedentes[:8]}, ensure_ascii=False)[:4000],
        # B7: custo verdadeiro — soma das DUAS chamadas (decomposição + síntese).
        tokens_input=tokens_in,
        tokens_output=tokens_out,
        custo_estimado=custo,
        status_hitl=AIStatusHITL.gerado,
    )
    db.add(log)
    await db.commit()
    resultado["ai_log_id"] = log.id
    return resultado
