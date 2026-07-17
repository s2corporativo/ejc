# ── app/services/ai/agent/tools/escrita.py ───────────────────────────────────
# Ferramentas de ESCRITA do agente (requer_confirmacao=True → o loop PAUSA e
# exige aprovação humana / HITL antes de executar). CADA uma re-verifica
# RBAC/ownership (verificar_acesso_caso). Ambas EMBRULHAM operações que já
# existem no núcleo — nada de modelo novo:
#   • gerar_minuta_peca   → executar_tarefa_ia (rascunho; NÃO persiste peça).
#   • registrar_nota_caso → grava um CaseMovimento (tipo="nota") na timeline
#                            do caso (efeito colateral REAL e persistente).
from __future__ import annotations

import logging
from uuid import uuid4

from app.core.ownership import verificar_acesso_caso
from app.services.ai.agent.tools.context import AgentContext
from app.services.ai.agent.tools.registry import registrar_tool

logger = logging.getLogger("ejc.ai.agent.escrita")


@registrar_tool(
    name="gerar_minuta_peca",
    description=(
        "Gera uma MINUTA (rascunho) de peça jurídica do tipo indicado a partir "
        "das instruções/fatos, usando o núcleo de IA por tarefa (TarefaIA.MINUTAS). "
        "O resultado é SEMPRE rascunho (is_rascunho=True), sujeito a revisão humana "
        "(HITL/OAB) — NÃO é protocolado nem persistido. Nunca prometa resultado."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "tipo": {"type": "string",
                     "description": "Tipo da peça (ex.: contestação, recurso, petição inicial)."},
            "instrucoes": {"type": "string",
                           "description": "Instruções, fatos e teses para orientar a minuta."},
        },
        "required": ["tipo", "instrucoes"],
    },
    requer_confirmacao=True,
)
async def gerar_minuta_peca(args: dict, ctx: AgentContext) -> dict:
    await verificar_acesso_caso(ctx.db, ctx.user, ctx.case_id)
    from app.services.ai.entidades_caso import entidades_do_caso
    from app.services.ai_gateway import executar_tarefa_ia
    from app.services.system_prompts.router import TarefaIA

    tipo = (args.get("tipo") or "peça").strip()
    instrucoes = (args.get("instrucoes") or "").strip()
    mensagem = f"TIPO DE PEÇA: {tipo}\n\nINSTRUÇÕES/FATOS:\n{instrucoes}"
    # Entidades do caso → pseudonimização REVERSÍVEL consistente no gateway.
    entidades = await entidades_do_caso(ctx.db, ctx.case_id)
    resultado = await executar_tarefa_ia(
        TarefaIA.MINUTAS, mensagem, case_id=ctx.case_id,
        user_id=ctx.user.id, db=ctx.db, nivel_inteligencia="alto",
        entidades=entidades,
    )
    return {
        "tipo": tipo,
        "conteudo": resultado.get("conteudo", ""),
        "is_rascunho": True,
        "modelo": resultado.get("modelo"),
        "custo_estimado_brl": resultado.get("custo_estimado_brl"),
    }


@registrar_tool(
    name="registrar_nota_caso",
    description=(
        "Registra uma NOTA na timeline (andamentos) do caso em contexto. Tem "
        "EFEITO COLATERAL REAL e persistente — por isso exige confirmação humana "
        "(HITL) antes de executar. Use para consolidar uma decisão/observação já "
        "revisada pelo advogado."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "descricao": {"type": "string",
                          "description": "Texto da nota a registrar na timeline do caso."},
        },
        "required": ["descricao"],
    },
    requer_confirmacao=True,
)
async def registrar_nota_caso(args: dict, ctx: AgentContext) -> dict:
    await verificar_acesso_caso(ctx.db, ctx.user, ctx.case_id)
    from app.models.case import CaseMovimento

    descricao = (args.get("descricao") or "").strip()
    if not descricao:
        return {"erro": "descrição vazia; nada foi registrado"}
    mov = CaseMovimento(
        id=str(uuid4()),
        case_id=ctx.case_id,
        tipo="nota",
        descricao=descricao[:8000],
        created_by=ctx.user.id,
    )
    ctx.db.add(mov)
    await ctx.db.commit()
    logger.info("[agent] nota registrada no caso %s (movimento %s)", ctx.case_id, mov.id)
    return {"registrado": True, "movimento_id": mov.id, "tipo": "nota"}
