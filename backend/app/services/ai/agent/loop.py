# ── app/services/ai/agent/loop.py ────────────────────────────────────────────
# LOOP AGÊNTICO (tool-use, igual ao Claude Code): o modelo decide → chama
# ferramenta → lê o resultado → decide de novo, em N passos, até concluir.
#
# GUARDRAILS REUSADOS (nada é reescrito):
#   • RBAC/ownership: verificar_acesso_caso no início E dentro de cada tool.
#   • Barreira LGPD: chat_agentico pseudonimiza cada turno (marcadores
#     consistentes por `entidades`) e reidrata a saída — o histórico do loop
#     vive em ESPAÇO REAL (PII real), nunca vai ao provider em claro.
#   • AILog por turno (ai_guard.registrar_ai_log) com texto PSEUDONIMIZADO —
#     nunca PII reidratada; erro de gravação PROPAGA.
#   • Gate de citações (response_validator) no texto FINAL (anti-alucinação).
#   • Orçamento: teto de passos + de tokens (nunca loop infinito).
#   • HITL: tools de ESCRITA pausam e exigem aprovação humana.
#
# Tudo atrás de AI_AGENT_ENABLED (checado no router): com a flag OFF, este
# módulo nunca é acionado e o sistema é idêntico ao atual.
from __future__ import annotations

import inspect
import json
import logging

from app.core.config import get_settings
from app.core.ownership import verificar_acesso_caso
from app.services.ai.agent.budget import AgentBudget
from app.services.ai.agent.tools.context import AgentContext
from app.services.ai.agent.tools.registry import REGISTRY
# Import dos módulos de tools REGISTRA as ferramentas no REGISTRY (decoradores).
from app.services.ai.agent.tools import escrita as _escrita  # noqa: F401
from app.services.ai.agent.tools import leitura as _leitura  # noqa: F401

logger = logging.getLogger("ejc.ai.agent.loop")


_SYSTEM_AGENTE = (
    "Você é o AGENTE JURÍDICO do escritório operando em modo de tool-use. "
    "Você decide, chama ferramentas, lê os resultados e decide de novo, em passos, "
    "até concluir a tarefa do advogado.\n\n"
    "FERRAMENTAS: use `buscar_precedentes` e `ler_dossie` para se informar antes de "
    "concluir; use `gerar_minuta_peca` para produzir rascunhos de peça e "
    "`registrar_nota_caso` para gravar notas — estas DUAS últimas são de ESCRITA e "
    "só rodam após CONFIRMAÇÃO HUMANA (o sistema pausa e pede aprovação).\n\n"
    "REGRAS INEGOCIÁVEIS:\n"
    "- Todo texto que você produz é RASCUNHO sujeito a revisão humana (HITL/OAB).\n"
    "- NUNCA invente fonte (súmula/artigo/precedente/jurisprudência): cite apenas o "
    "que voltar das ferramentas; sem base, escreva 'verificar fonte'.\n"
    "- NUNCA prometa ou garanta resultado (vedação OAB).\n"
    "- Estruture o raciocínio jurídico pelo método FIRAC (fato / questão / regra com "
    "fonte / aplicação / conclusão), separando FATO, INFERÊNCIA, LACUNA e DECISÃO "
    "HUMANA PENDENTE.\n"
    "- NÃO revele sua cadeia de pensamento: entregue apenas o resultado estruturado.\n"
    "- Quando tiver informação suficiente, PARE de chamar ferramentas e responda."
)


async def _emitir(on_event, tipo: str, dados: dict) -> None:
    """Emite um evento (se houver callback). Suporta callback sync OU async."""
    if on_event is None:
        return
    try:
        res = on_event(tipo, dados)
        if inspect.isawaitable(res):
            await res
    except Exception as e:  # observabilidade nunca derruba o loop
        logger.warning("on_event('%s') falhou: %s", tipo, str(e)[:200])


def _assistant_turn(text: str, tool_calls: list[dict]) -> dict:
    """Reconstrói o turno assistant (ESPAÇO REAL) com blocos text + tool_use, no
    formato Anthropic, para reanexar ao histórico do loop."""
    blocos: list[dict] = []
    if text:
        blocos.append({"type": "text", "text": text})
    for tc in tool_calls:
        blocos.append({
            "type": "tool_use",
            "id": tc.get("id", ""),
            "name": tc.get("name", ""),
            "input": tc.get("input", {}) or {},
        })
    return {"role": "assistant", "content": blocos}


def _tool_result_turn(tool_use_id: str, resultado: dict) -> dict:
    """Turno user com um bloco tool_result (ESPAÇO REAL)."""
    return {
        "role": "user",
        "content": [{
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": json.dumps(resultado, ensure_ascii=False, default=str)[:12000],
        }],
    }


async def rodar_agente(
    *,
    db,
    user,
    case_id: str,
    mensagem: str,
    historico: list[dict] | None = None,
    ferramentas_aprovadas: set[str] | None = None,
    on_event=None,
) -> dict:
    """Executa o loop agêntico para `mensagem` no `case_id`.

    Retorna um dos:
      • {"status":"ok", "resposta", "is_rascunho":True, "passos":[...],
         "custo_estimado_brl", "alertas", "revisao_obrigatoria"}
      • {"status":"pendente_confirmacao", "ferramenta", "args",
         "transcricao_parcial"} — quando uma tool de ESCRITA precisa de aprovação
         humana. O cliente re-invoca incluindo a tool em `ferramentas_aprovadas`
         (no scaffold o loop RE-RODA do início; a fase 2 pode persistir o estado
         parcial em Redis para retomar sem reexecutar tools de leitura).
      • {"status":"erro", "detalhe"} — falha segura (sem vazar PII/detalhe cru).
    """
    settings = get_settings()
    ferramentas_aprovadas = set(ferramentas_aprovadas or [])

    # 1) Gate de ownership (fail-closed) — o mesmo das escritas em sub-recursos.
    caso = await verificar_acesso_caso(db, user, case_id)
    role = getattr(getattr(user, "role", None), "value", None) or str(getattr(user, "role", ""))

    # 2) Entidades nomeadas do caso → pseudonimização REVERSÍVEL consistente.
    from app.services.ai.entidades_caso import entidades_do_caso
    entidades = await entidades_do_caso(db, case_id)

    ctx = AgentContext(
        db=db, user=user, case_id=case_id,
        client_id=getattr(caso, "client_id", None), role=role,
    )

    # 3) Histórico em ESPAÇO REAL (PII real) — chat_agentico pseudonimiza a cada turno.
    messages: list[dict] = [{"role": "system", "content": _SYSTEM_AGENTE}]
    if historico:
        messages.extend(historico)
    messages.append({"role": "user", "content": mensagem})

    budget = AgentBudget(
        max_steps=int(getattr(settings, "AI_AGENT_MAX_STEPS", 8)),
        max_tokens_total=int(getattr(settings, "AI_AGENT_MAX_TOKENS", 16000)),
    )

    # Log LGPD: prompt SANITIZADO (irreversível) — nunca PII real no AILog.
    from app.services.sanitizer import sanitizar_pii
    prompt_log_base, pii_removida = sanitizar_pii(mensagem)

    from app.services.ai_gateway import chat_agentico, _ProviderPulado
    from app.services.ai_guard import registrar_ai_log
    from app.models.ai_log import AITipoUso

    passos: list[dict] = []
    custo_total = 0.0
    final: str | None = None
    aviso_parada: str | None = None

    for passo in range(budget.max_steps):
        try:
            resp = await chat_agentico(
                messages,
                REGISTRY.schemas(role),
                task_type="estrategia",
                max_tokens=4096,
                entidades=entidades,
            )
        except _ProviderPulado:
            # Barreira LGPD pulou o provider (PII residual) — erro SEGURO.
            await _emitir(on_event, "erro", {
                "detalhe": "Conteúdo com dados pessoais não pôde ir a provider "
                           "externo — revise o texto ou habilite IA local."
            })
            return {"status": "erro", "detalhe": "bloqueado_por_pii_lgpd"}
        except Exception as e:
            logger.warning("chat_agentico falhou no passo %d: %s", passo, str(e)[:200])
            await _emitir(on_event, "erro", {"detalhe": type(e).__name__})
            return {"status": "erro", "detalhe": type(e).__name__}

        usage = resp.get("usage", {}) or {}
        budget.registrar_turno(usage)
        custo_passo = _custo_turno(resp)
        custo_total += custo_passo

        # 4) AILog por turno — texto PSEUDONIMIZADO (sem PII real). Erro PROPAGA.
        await registrar_ai_log(
            db, user_id=user.id, tipo_uso=AITipoUso.analise_caso, case_id=case_id,
            prompt_sanitizado=f"[AGENTE passo {passo + 1}]\n{prompt_log_base}",
            pii_removida=pii_removida,
            resposta=(resp.get("text_para_log") or "")[:8000],
            modelo=f"{resp.get('provider')}/{resp.get('model')}",
            tokens_input=usage.get("input_tokens"),
            tokens_output=usage.get("output_tokens"),
            custo_estimado=custo_passo,
        )

        passos.append({
            "passo": passo + 1,
            "provider": resp.get("provider"),
            "model": resp.get("model"),
            "stop_reason": resp.get("stop_reason"),
            "tokens": (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0),
            "ferramentas": [tc.get("name") for tc in (resp.get("tool_calls") or [])],
        })
        await _emitir(on_event, "passo", passos[-1])

        tool_calls = resp.get("tool_calls") or []
        # 5) Sem tool_use → conclusão do agente.
        if resp.get("stop_reason") != "tool_use" or not tool_calls:
            final = resp.get("text", "") or ""
            break

        # Anexa o turno assistant (text + tool_use) ao histórico (espaço real).
        messages.append(_assistant_turn(resp.get("text", "") or "", tool_calls))

        for tc in tool_calls:
            nome = tc.get("name", "")
            args = tc.get("input", {}) or {}
            # HITL: tool de ESCRITA não-aprovada PAUSA o loop.
            if REGISTRY.requer_confirmacao(nome) and nome not in ferramentas_aprovadas:
                await _emitir(on_event, "confirmacao_requerida", {
                    "ferramenta": nome, "args": args, "tool_use_id": tc.get("id"),
                })
                return {
                    "status": "pendente_confirmacao",
                    "ferramenta": nome,
                    "args": args,
                    "transcricao_parcial": passos,
                }
            await _emitir(on_event, "ferramenta", {"ferramenta": nome, "args": args})
            try:
                resultado = await REGISTRY.executar(nome, args, ctx)
            except Exception as e:
                logger.warning("tool '%s' falhou: %s", nome, str(e)[:200])
                resultado = {"erro": type(e).__name__}
            messages.append(_tool_result_turn(tc.get("id", ""), resultado))
            await _emitir(on_event, "resultado", {"ferramenta": nome, "resultado": resultado})

        # 6) Orçamento de tokens — corta o loop antes do teto de passos se estourar.
        if budget.estourou_tokens():
            aviso_parada = ("Parada por teto de tokens do agente "
                            f"({budget.tokens_usados}/{budget.max_tokens_total}).")
            break
    else:
        aviso_parada = f"Parada por teto de passos do agente ({budget.max_steps})."

    if final is None:
        # Loop terminou por orçamento sem uma resposta final natural.
        final = (
            "Não foi possível concluir dentro do orçamento do agente. "
            "Resultado parcial acima; revise e refine a solicitação."
        )

    # 7) Gate de citações (anti-alucinação) sobre o texto FINAL.
    alertas: list[str] = []
    revisao_obrigatoria = False
    try:
        from app.services.ai.core.response_validator import validar
        validado = await validar(db, final, exige_fonte=True, fontes=None)
        final = validado.get("conteudo", final)
        alertas = validado.get("alertas", []) or []
        revisao_obrigatoria = bool(validado.get("revisao_obrigatoria"))
    except Exception as e:
        logger.warning("response_validator falhou (seguindo com aviso): %s", str(e)[:200])
        alertas = ["Validação de citações indisponível — confira as fontes manualmente."]
        revisao_obrigatoria = True

    if aviso_parada:
        alertas = [aviso_parada, *alertas]

    resultado_final = {
        "status": "ok",
        "resposta": final,
        "is_rascunho": True,
        "passos": passos,
        "custo_estimado_brl": round(custo_total, 4),
        "alertas": alertas,
        "revisao_obrigatoria": revisao_obrigatoria,
    }
    await _emitir(on_event, "final", resultado_final)
    return resultado_final


def _custo_turno(resp: dict) -> float:
    """Custo (R$) do turno pela fonte única (ai_cost), ciente do provider real."""
    try:
        from app.services.ai_cost import estimar_custo_brl
        usage = resp.get("usage", {}) or {}
        return float(estimar_custo_brl(
            resp.get("provider", "anthropic"),
            int(usage.get("input_tokens") or 0),
            int(usage.get("output_tokens") or 0),
            resp.get("model", "") or "",
        ))
    except Exception:
        return 0.0
