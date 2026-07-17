# ── app/services/ai/agent/tools/leitura.py ───────────────────────────────────
# Ferramentas READ-ONLY do agente (requer_confirmacao=False → execução
# automática). CADA uma re-verifica RBAC/ownership (verificar_acesso_caso) — o
# gate de entrada do router não basta (defense-in-depth). Elas apenas EMBRULHAM
# serviços existentes do núcleo (RAG isolado por cliente; dossiê estratégico).
from __future__ import annotations

import logging

from app.core.ownership import verificar_acesso_caso
from app.services.ai.agent.tools.context import AgentContext
from app.services.ai.agent.tools.registry import registrar_tool

logger = logging.getLogger("ejc.ai.agent.leitura")


@registrar_tool(
    name="buscar_precedentes",
    description=(
        "Busca precedentes/jurisprudência e conhecimento interno na base RAG, "
        "ISOLADA ao cliente do caso em contexto. Use para FUNDAMENTAR análise e "
        "estratégia. Retorna trechos com título, categoria, fonte e score. "
        "NUNCA invente fonte: use apenas o que voltar desta ferramenta."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "consulta": {"type": "string", "description": "Termos/tese a pesquisar."},
            "area": {"type": "string", "description": "Categoria/área opcional (ex.: trabalhista, civel)."},
        },
        "required": ["consulta"],
    },
    requer_confirmacao=False,
)
async def buscar_precedentes(args: dict, ctx: AgentContext) -> dict:
    # Re-checagem de ownership (fail-closed): nunca confiar só no gate do router.
    await verificar_acesso_caso(ctx.db, ctx.user, ctx.case_id)
    from app.services.ai_service import buscar_contexto_rag, _escopo_cliente_do_caso

    consulta = (args.get("consulta") or "").strip()
    if not consulta:
        return {"erro": "consulta vazia", "total": 0, "trechos": []}
    categorias = None
    area = (args.get("area") or "").strip()
    if area:
        categorias = [area]
    # Escopo de isolamento do RAG = client_id do PRÓPRIO caso (nunca de outro).
    scope = await _escopo_cliente_do_caso(ctx.db, ctx.case_id)
    trechos = await buscar_contexto_rag(
        ctx.db, consulta, limite=6, categorias=categorias,
        modo_or=True, scope_client_id=scope,
    )
    resumo = [{
        "titulo": t.get("titulo"),
        "categoria": t.get("categoria"),
        "fonte": t.get("fonte"),
        "score": t.get("score"),
        "trecho": (t.get("conteudo") or "")[:1200],
    } for t in (trechos or [])]
    return {"total": len(resumo), "trechos": resumo}


@registrar_tool(
    name="ler_dossie",
    description=(
        "Obtém o dossiê estratégico do caso em contexto (fatos, financeiro, "
        "andamentos, checklists pendentes e enriquecimento por IA). Use para uma "
        "visão geral do caso antes de decidir a estratégia."
    ),
    input_schema={"type": "object", "properties": {}},
    requer_confirmacao=False,
)
async def ler_dossie(args: dict, ctx: AgentContext) -> dict:
    await verificar_acesso_caso(ctx.db, ctx.user, ctx.case_id)
    from app.services import dossie_service

    # NOTA (scaffold): dossie_service.gerar_dossie PERSISTE um DossieEstrategico
    # (status=rascunho) + AILog — logo esta tool tem um efeito colateral de
    # GERAÇÃO, ainda que exposta como leitura (o produto trata "gerar dossiê"
    # como ação de consulta do advogado, e o resultado é sempre rascunho/HITL).
    # GANCHO fase 2: para leitura ESTRITAMENTE pura, trocar por um leitor da
    # última versão persistida (sem regenerar) — ex.: case_context.montar_dossie.
    dossie = await dossie_service.gerar_dossie(ctx.db, ctx.case_id, ctx.user.id)
    conteudo = (
        getattr(dossie, "conteudo_texto", None)
        or getattr(dossie, "conteudo_html", None)
        or ""
    )
    return {
        "versao": getattr(dossie, "versao", None),
        "titulo": getattr(dossie, "titulo", None),
        "conteudo": conteudo[:8000],
    }
