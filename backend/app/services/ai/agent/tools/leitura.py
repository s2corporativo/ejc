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
        # C4: conteúdo privado restrito ao CASO em contexto (não só ao cliente).
        scope_case_id=ctx.case_id,
    )
    # I5/B4: as fontes ficam no contexto do agente para o gate de citações
    # final e para a trilha do AILog (fontes_rag).
    ctx.registrar_fontes(trechos)
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
        "Lê o dossiê estratégico JÁ EXISTENTE do caso em contexto (fatos, "
        "financeiro, andamentos, checklists e enriquecimento por IA da última "
        "versão salva). Use para uma visão geral antes de decidir a estratégia. "
        "Se ainda não houver dossiê salvo, informa isso (não gera um novo)."
    ),
    input_schema={"type": "object", "properties": {}},
    requer_confirmacao=False,
)
async def ler_dossie(args: dict, ctx: AgentContext) -> dict:
    await verificar_acesso_caso(ctx.db, ctx.user, ctx.case_id)
    from app.services import dossie_service

    # S3/M2: LEITURA PURA — lê a ÚLTIMA versão persistida SEM regenerar. Antes esta
    # tool chamava gerar_dossie, que PERSISTE um DossieEstrategico + AILog (escrita
    # sob rótulo de leitura). Agora nenhuma escrita/IA/AILog ocorre numa tool de
    # leitura (efeito colateral zero, coerente com requer_confirmacao=False).
    dossie = await dossie_service.ler_ultimo_dossie(ctx.db, ctx.case_id)
    if dossie is None:
        return {
            "existe": False,
            "conteudo": "",
            "nota": "Nenhum dossiê estratégico salvo para este caso. "
                    "Gere um dossiê pela tela do caso antes de consultá-lo aqui.",
        }
    conteudo = (
        getattr(dossie, "conteudo_texto", None)
        or getattr(dossie, "conteudo_html", None)
        or ""
    )
    return {
        "existe": True,
        "versao": getattr(dossie, "versao", None),
        "titulo": getattr(dossie, "titulo", None),
        "conteudo": conteudo[:8000],
    }
