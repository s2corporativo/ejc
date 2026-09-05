# ── app/services/ai/agent/loop.py ────────────────────────────────────────────
# LOOP AGÊNTICO (tool-use, igual ao Claude Code): o modelo decide → chama
# ferramenta → lê o resultado → decide de novo, em N passos, até concluir.
#
# GUARDRAILS REUSADOS (nada é reescrito):
#   • RBAC/ownership: verificar_acesso_caso no início E dentro de cada tool.
#   • Barreira LGPD: chat_agentico pseudonimiza cada turno (marcadores
#     consistentes por `entidades`) e reidrata a saída — o histórico do loop
#     vive em ESPAÇO REAL (PII real), nunca vai ao provider em claro. O MODO de
#     sanitização vem da ÁREA/sigilo REAL do caso (achado S1), não do rótulo de
#     tarefa: caso LOCAL_COMPLETO → fail-closed (nunca vai ao externo).
#   • AILog por turno (ai_guard.registrar_ai_log) com texto PSEUDONIMIZADO —
#     nunca PII reidratada; erro de gravação PROPAGA.
#   • Gate de citações (response_validator) no texto FINAL (anti-alucinação).
#   • Orçamento (AgentBudget): teto de passos + tokens + CUSTO R$ (nunca infinito).
#   • HITL RETOMÁVEL: tools de ESCRITA pausam e exigem aprovação vinculada aos
#     ARGS exatos (achado H1) — estado persistido em Redis (token) e VINCULADO a
#     usuário/caso/papel (auditoria 2026-07-26, AI-031). Sem Redis, FALHA FECHADO
#     (AI-030): não existe fallback client-side; nenhuma escrita executa sem
#     aprovação registrada servidor-side.
#
# Tudo atrás de AI_AGENT_ENABLED (checado no router): com a flag OFF, este
# módulo nunca é acionado e o sistema é idêntico ao atual.
from __future__ import annotations

import json
import logging

from app.core.config import get_settings
from app.core.ownership import verificar_acesso_caso
from app.services.ai.agent.budget import AgentBudget
from app.services.ai.agent import hitl_state
from app.services.ai.agent.tools.context import AgentContext
from app.services.ai.agent.tools.registry import REGISTRY
# Import dos módulos de tools REGISTRA as ferramentas no REGISTRY (decoradores).
from app.services.ai.agent.tools import escrita as _escrita  # noqa: F401
from app.services.ai.agent.tools import leitura as _leitura  # noqa: F401
from app.services.ai.agent.tools import motores as _motores  # noqa: F401

logger = logging.getLogger("ejc.ai.agent.loop")

# Placeholder de degradação segura (achado M5): quando o conteúdo interno de um
# tool_result traz PII residual estrutural que a barreira não pseudonimizou, o
# trecho é redigido (não vaza) e o agente CONTINUA — em vez de abortar.
_REDIGIDO = "[conteúdo interno redigido: dado pessoal residual não pseudonimizável]"


_SYSTEM_AGENTE = (
    "Você é o AGENTE JURÍDICO do escritório operando em modo de tool-use. "
    "Você decide, chama ferramentas, lê os resultados e decide de novo, em passos, "
    "até concluir a tarefa do advogado.\n\n"
    "FERRAMENTAS: use `buscar_precedentes` e `ler_dossie` para se informar antes de "
    "concluir. LEIA OS AUTOS: `listar_documentos` → `ler_documento` (texto integral) "
    "e `buscar_nos_autos` (localizar cláusula/fato/valor) — fundamente em prova real, "
    "não em resumo; `consultar_movimentacao` dá a fase e a última decisão; "
    "`verificar_citacoes` confere cada súmula/artigo/precedente do seu texto ANTES "
    "de concluir. Os MOTORES DETERMINÍSTICOS do escritório estão disponíveis como "
    "ferramentas de leitura: `montar_cronologia` (linha do tempo real do caso), "
    "`identificar_rito_e_fase`, `detectar_providencias` (peças cabíveis com base "
    "legal e prazo do catálogo), `calcular_prazo` (projeção de prazo — NUNCA cria "
    "prazo; termo inicial sempre pendente de confirmação humana), "
    "`consultar_tabela_oab`, `ler_checklist_peca` e `classificar_area`. Repita "
    "bases legais, prazos e valores VERBATIM como as ferramentas devolverem — é "
    "PROIBIDO reformulá-los ou recalculá-los.\n"
    "ESCRITA (o sistema PAUSA e exige CONFIRMAÇÃO HUMANA antes de executar): "
    "`gerar_minuta_peca` (rascunho de peça), `registrar_nota_caso` (nota na "
    "timeline), `criar_prazo_confirmado` (cria o prazo fatal SÓ após a aprovação "
    "do advogado, que é a confirmação do termo inicial) e `gerar_kit_documental` "
    "(procuração + contrato + checklist, rascunhos).\n\n"
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
    import inspect
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


def _tem_tool_result(messages: list[dict]) -> bool:
    """True se a transcrição já contém algum tool_result (conteúdo interno lido)."""
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            for bloco in content:
                if isinstance(bloco, dict) and bloco.get("type") == "tool_result":
                    return True
    return False


def _redigir_tool_results(messages: list[dict]) -> int:
    """M5 — degradação segura: substitui o conteúdo dos tool_results por um
    placeholder (o conteúdo interno com PII residual NÃO vai ao provider). Retorna
    quantos foram redigidos."""
    n = 0
    for m in messages:
        content = m.get("content")
        if not isinstance(content, list):
            continue
        for bloco in content:
            if not (isinstance(bloco, dict) and bloco.get("type") == "tool_result"):
                continue
            rc = bloco.get("content")
            if isinstance(rc, str) and rc and rc != _REDIGIDO:
                bloco["content"] = _REDIGIDO
                n += 1
            elif isinstance(rc, list):
                for sub in rc:
                    if (isinstance(sub, dict) and sub.get("type") == "text"
                            and sub.get("text") not in (None, "", _REDIGIDO)):
                        sub["text"] = _REDIGIDO
                        n += 1
    return n


async def _processar_tool_calls(tool_calls, *, ctx, messages,
                                on_event, apenas_leitura: bool = False) -> dict | None:
    """Executa `tool_calls` em ordem, anexando cada tool_result a `messages`.
      • LEITURA (requer_confirmacao=False) → executa sempre.
      • ESCRITA (requer_confirmacao=True) → NUNCA executa aqui: PAUSA sempre,
        devolvendo {"pending": <write>, "restantes": <após o write>}. A execução
        aprovada acontece EXCLUSIVAMENTE na retomada por token (rodar_agente),
        contra o estado servidor-side — o antigo atalho por `aprovacoes_hash`
        vindo do cliente foi eliminado (auditoria 2026-07-26, AI-030: hash de
        dados públicos prova integridade, não autorização).
      • `apenas_leitura=True` (defense-in-depth): a write-tool nem foi exposta ao
        modelo por `schemas(role, apenas_leitura=True)`; se ainda assim for pedida,
        NÃO pausa em HITL — devolve erro como tool_result e SEGUE (fluxo de
        raciocínio puro nunca aguarda confirmação humana).
    Retorna None quando processou tudo."""
    for i, tc in enumerate(tool_calls):
        nome = tc.get("name", "")
        args = tc.get("input", {}) or {}
        if REGISTRY.requer_confirmacao(nome):
            if apenas_leitura:
                await _emitir(on_event, "ferramenta_bloqueada", {"ferramenta": nome})
                messages.append(_tool_result_turn(
                    tc.get("id", ""),
                    {"erro": "ferramenta_de_escrita_indisponivel_em_modo_leitura"}))
                continue
            # HITL: write-tool SEMPRE pausa o loop para aprovação humana.
            return {"pending": tc, "restantes": list(tool_calls[i + 1:])}
        await _emitir(on_event, "ferramenta", {"ferramenta": nome, "args": args})
        try:
            resultado = await REGISTRY.executar(nome, args, ctx)
        except Exception as e:
            logger.warning("tool '%s' falhou: %s", nome, str(e)[:200])
            resultado = {"erro": type(e).__name__}
        messages.append(_tool_result_turn(tc.get("id", ""), resultado))
        await _emitir(on_event, "resultado", {"ferramenta": nome, "resultado": resultado})
    return None


async def _persistir_e_pausar(*, pending, restantes, messages, passos, budget,
                              custo_total, prompt_log_base, pii_removida,
                              user, case_id, role, on_event) -> dict:
    """HITL: persiste o estado RETOMÁVEL (Redis, PII em espaço real — nunca logado)
    e devolve o status pendente. Sem Redis, FALHA FECHADO (AI-030): a operação de
    escrita NÃO executa e o chamador recebe erro — não existe fallback
    client-side. O estado carrega usuário/caso/papel (AI-031) para a retomada
    validar que o contexto é o MESMO da pausa."""
    nome = pending.get("name", "")
    args = pending.get("input", {}) or {}
    args_hash = hitl_state.hash_tool_call(nome, args)
    estado = {
        # Vínculo de contexto (AI-031): a retomada só vale para o MESMO usuário,
        # caso e papel que pausaram — comparados em rodar_agente.
        "user_id": str(getattr(user, "id", "") or ""),
        "case_id": str(case_id),
        "role": role,
        "messages": messages,
        "passos": passos,
        "custo_total": custo_total,
        "num_passos": budget.passos,
        "tokens_usados": budget.tokens_usados,
        "prompt_log_base": prompt_log_base,
        "pii_removida": pii_removida,
        "pending": pending,
        "restantes": restantes,
    }
    token = await hitl_state.salvar(estado)
    if token is None:
        # AI-030 (fail-closed): sem estado servidor-side não há como registrar
        # uma aprovação genuína — a escrita não executa.
        await _emitir(on_event, "erro", {
            "detalhe": "Aprovação humana indisponível no momento (estado HITL não "
                       "pôde ser persistido); a operação de escrita NÃO foi "
                       "executada. Tente novamente em instantes."})
        return {"status": "erro", "detalhe": "hitl_indisponivel"}
    dados = {
        "token": token, "args_hash": args_hash,
        "ferramenta": nome, "args": args, "tool_use_id": pending.get("id"),
    }
    await _emitir(on_event, "confirmacao_requerida", dados)
    return {
        "status": "pendente_confirmacao",
        "token": token,
        "args_hash": args_hash,
        "ferramenta": nome,
        "args": args,
        "transcricao_parcial": passos,
    }


async def rodar_agente(
    *,
    db,
    user,
    case_id: str,
    mensagem: str | None = None,
    historico: list[dict] | None = None,
    retomar_token: str | None = None,
    decisao: str | None = None,
    apenas_leitura: bool = False,
    on_event=None,
) -> dict:
    """Executa (ou RETOMA) o loop agêntico para `mensagem` no `case_id`.

    Início (sem `retomar_token`): roda desde a instrução do advogado.
    Retomada (`retomar_token` + `decisao`): carrega o estado do Redis (consumo
    atômico one-shot), VALIDA que usuário/caso/papel são os MESMOS que pausaram
    (AI-031) e, se `decisao=="aprovar"`, executa EXATAMENTE o tool_call pendente
    (mesmos args) e CONTINUA de onde parou; `decisao=="recusar"` registra a
    recusa e segue. Este é o ÚNICO caminho de aprovação de write-tools: sem
    estado servidor-side (Redis indisponível), a escrita falha fechada (AI-030).

    `apenas_leitura`: quando True, expõe ao modelo SOMENTE tools de leitura
    (`schemas(role, apenas_leitura=True)`) e nunca pausa em HITL — para fluxos de
    raciocínio puro (ex.: análise "advogado sênior" do Raio-X). Default False
    preserva integralmente o caminho SSE com escrita/HITL.

    Retorna um dos:
      • {"status":"ok", "resposta", "is_rascunho":True, "passos":[...],
         "custo_estimado_brl", "alertas", "revisao_obrigatoria"}
      • {"status":"pendente_confirmacao", "token", "args_hash", "ferramenta",
         "args", "transcricao_parcial"} — write-tool aguardando aprovação humana.
      • {"status":"erro", "detalhe"} — falha segura (sem vazar PII/detalhe cru).
    """
    settings = get_settings()

    from app.services.ai.sanitization_policy import (
        ModoSanitizacao, modo_para_task, modo_sigilo_do_caso,
    )
    from app.services.ai.entidades_caso import entidades_do_caso
    from app.services.ai_gateway import chat_agentico, _ProviderPulado
    from app.services.ai_guard import registrar_ai_log
    from app.models.ai_log import AITipoUso
    from app.services.observability import langfuse_client as _lf

    # 1) Gate de ownership (fail-closed) — SEMPRE, inclusive na retomada.
    caso = await verificar_acesso_caso(db, user, case_id)
    role = getattr(getattr(user, "role", None), "value", None) or str(getattr(user, "role", ""))
    area_label = (getattr(getattr(caso, "area", None), "value", None)
                  or str(getattr(caso, "area", "") or ""))

    # S1: MODO de sanitização derivado da ÁREA/sigilo REAL do caso (não do rótulo
    # de roteamento). Um caso de sigilo reforçado (LOCAL_COMPLETO) NUNCA pode ir a
    # provider externo. `caso.sigilo_reforcado` tem prioridade sobre `area_label`
    # (ver docstring de `modo_sigilo_do_caso`).
    modo_sanitizacao = modo_sigilo_do_caso(caso) or modo_para_task(area_label)

    # S1 fail-closed: o caminho agêntico só tem provider EXTERNO (Anthropic); caso
    # sigiloso → aborta ANTES de qualquer envio (nunca vai ao externo).
    if modo_sanitizacao == ModoSanitizacao.LOCAL_COMPLETO:
        await _emitir(on_event, "erro", {
            "detalhe": "Caso de sigilo reforçado exige IA local; o agente não pode "
                       "usar provedor externo. Habilite o Ollama on-prem."
        })
        return {"status": "erro", "detalhe": "caso_sigiloso_exige_ia_local"}

    entidades = await entidades_do_caso(db, case_id)
    ctx = AgentContext(
        db=db, user=user, case_id=case_id,
        client_id=getattr(caso, "client_id", None), role=role, area=area_label,
    )

    # Sugestão 3 — trace da sessão do agente (NO-OP quando Langfuse desligado).
    _trace = _lf.novo_trace(name="agente", metadata={
        "case_area": area_label, "role": role, "retomada": bool(retomar_token),
    })

    budget = AgentBudget(
        max_steps=int(getattr(settings, "AI_AGENT_MAX_STEPS", 8)),
        max_tokens_total=int(getattr(settings, "AI_AGENT_MAX_TOKENS", 120000)),
        max_custo_brl=float(getattr(settings, "AI_AGENT_MAX_CUSTO_BRL", 2.0)),
    )

    passos: list[dict] = []
    custo_total = 0.0
    final: str | None = None
    aviso_parada: str | None = None
    alertas_extra: list[str] = []

    # 2) Estado inicial — RETOMADA (Redis) ou início limpo.
    if retomar_token:
        estado = await hitl_state.carregar(retomar_token)
        if estado is None:
            await _emitir(on_event, "erro", {
                "detalhe": "Sessão do agente expirada; reenvie a solicitação."})
            return {"status": "erro", "detalhe": "sessao_expirada"}
        # Estado de versão antiga (sem chaves de vínculo) não é retomável —
        # trata como sessão expirada (diagnóstico correto), nunca executa.
        if not (estado.get("user_id") and estado.get("case_id") and estado.get("role")):
            await _emitir(on_event, "erro", {
                "detalhe": "Sessão do agente expirada; reenvie a solicitação."})
            return {"status": "erro", "detalhe": "sessao_expirada"}
        # AI-031: o token só vale para o MESMO usuário, caso e papel que pausaram.
        # O estado já foi consumido atomicamente (one-shot) — uma tentativa com
        # contexto divergente DESTRÓI o token (fail-closed; o fluxo legítimo
        # recomeça do zero), nunca executa a escrita pendente.
        if (str(estado.get("user_id")) != str(getattr(user, "id", "") or "")
                or str(estado.get("case_id")) != str(case_id)
                or str(estado.get("role")) != role):
            logger.warning("[hitl] retomada com contexto divergente do estado — recusada")
            await _emitir(on_event, "erro", {
                "detalhe": "Sessão de aprovação não corresponde a este usuário/caso; "
                           "reenvie a solicitação."})
            return {"status": "erro", "detalhe": "sessao_nao_corresponde"}
        messages = estado.get("messages") or []
        passos = estado.get("passos") or []
        custo_total = float(estado.get("custo_total") or 0.0)
        budget.passos = int(estado.get("num_passos") or 0)
        budget.tokens_usados = int(estado.get("tokens_usados") or 0)
        budget.custo_acumulado = custo_total
        prompt_log_base = estado.get("prompt_log_base") or ""
        pii_removida = bool(estado.get("pii_removida"))
        pending = estado.get("pending")
        restantes = estado.get("restantes") or []
        aprovado = (decisao or "").strip().lower() == "aprovar"
        if aprovado and pending:
            # H1: executa EXATAMENTE o tool_call aprovado (mesmos args), SEM re-run
            # das leituras anteriores.
            nome = pending.get("name", "")
            args = pending.get("input", {}) or {}
            await _emitir(on_event, "ferramenta", {"ferramenta": nome, "args": args})
            try:
                resultado = await REGISTRY.executar(nome, args, ctx)
            except Exception as e:
                logger.warning("tool '%s' (retomada) falhou: %s", nome, str(e)[:200])
                resultado = {"erro": type(e).__name__}
            messages.append(_tool_result_turn(pending.get("id", ""), resultado))
            await _emitir(on_event, "resultado", {"ferramenta": nome, "resultado": resultado})
        elif pending:
            # Recusa humana: registra a decisão como tool_result e segue.
            messages.append(_tool_result_turn(
                pending.get("id", ""),
                {"recusado": True, "motivo": "operação não aprovada pelo revisor humano (HITL)"}))
            await _emitir(on_event, "recusado", {"ferramenta": pending.get("name")})
        # Resolve tool_calls remanescentes do MESMO turno (se houver).
        if restantes:
            pausa = await _processar_tool_calls(
                restantes, ctx=ctx, messages=messages, on_event=on_event,
                apenas_leitura=apenas_leitura)
            if pausa is not None:
                return await _persistir_e_pausar(
                    pending=pausa["pending"], restantes=pausa["restantes"],
                    messages=messages, passos=passos, budget=budget,
                    custo_total=custo_total, prompt_log_base=prompt_log_base,
                    pii_removida=pii_removida, user=user, case_id=case_id,
                    role=role, on_event=on_event)
    else:
        messages = [{"role": "system", "content": _SYSTEM_AGENTE}]
        if historico:
            messages.extend(historico)
        messages.append({"role": "user", "content": mensagem or ""})
        # Log LGPD: prompt SANITIZADO (irreversível) — nunca PII real no AILog.
        from app.services.sanitizer import sanitizar_pii
        prompt_log_base, pii_removida = sanitizar_pii(mensagem or "")

    # 3) Laço de passos — a condição ÚNICA de parada é budget.deve_parar() (L6).
    while not budget.deve_parar():
        try:
            resp = await chat_agentico(
                messages, REGISTRY.schemas(role, apenas_leitura=apenas_leitura),
                task_type="estrategia", max_tokens=4096,
                entidades=entidades, modo_sanitizacao=modo_sanitizacao,
            )
        except _ProviderPulado:
            # M5: PII residual. Se há tool_results (conteúdo interno lido), degrada
            # redigindo o(s) trecho(s) e tenta UMA vez — não aborta uma leitura
            # interna bem-sucedida. Sem tool_results (só a instrução humana) → erro
            # seguro (não há o que redigir sem alterar o pedido do advogado).
            if _tem_tool_result(messages) and _redigir_tool_results(messages):
                alertas_extra.append(
                    "Um trecho interno com dado pessoal residual foi redigido para "
                    "preservar o sigilo; a análise seguiu sem ele.")
                await _emitir(on_event, "degradacao", {"motivo": "pii_residual_redigida"})
                try:
                    resp = await chat_agentico(
                        messages, REGISTRY.schemas(role, apenas_leitura=apenas_leitura),
                        task_type="estrategia", max_tokens=4096,
                        entidades=entidades, modo_sanitizacao=modo_sanitizacao,
                    )
                except _ProviderPulado:
                    await _emitir(on_event, "erro", {
                        "detalhe": "Conteúdo com dados pessoais não pôde ir a "
                                   "provider externo — revise o texto ou habilite IA local."})
                    return {"status": "erro", "detalhe": "bloqueado_por_pii_lgpd"}
            else:
                await _emitir(on_event, "erro", {
                    "detalhe": "Conteúdo com dados pessoais não pôde ir a provider "
                               "externo — revise o texto ou habilite IA local."})
                return {"status": "erro", "detalhe": "bloqueado_por_pii_lgpd"}
        except Exception as e:
            logger.warning("chat_agentico falhou no passo %d: %s", budget.passos + 1, str(e)[:200])
            await _emitir(on_event, "erro", {"detalhe": type(e).__name__})
            return {"status": "erro", "detalhe": type(e).__name__}

        usage = resp.get("usage", {}) or {}
        budget.registrar_turno(usage)
        custo_passo = _custo_turno(resp)
        custo_total += custo_passo
        budget.registrar_custo(custo_passo)

        # AILog por turno — texto PSEUDONIMIZADO (sem PII real). Erro PROPAGA.
        # I5/B4: fontes RAG acumuladas pelas tools de leitura até este turno
        # entram na trilha (IDs/ordem — sem conteúdo, ver _fontes_str).
        from app.services.ai.core.audit_logger import _fontes_str
        await registrar_ai_log(
            db, user_id=user.id, tipo_uso=AITipoUso.analise_caso, case_id=case_id,
            prompt_sanitizado=f"[AGENTE passo {budget.passos}]\n{prompt_log_base}",
            pii_removida=pii_removida,
            resposta=(resp.get("text_para_log") or "")[:8000],
            modelo=f"{resp.get('provider')}/{resp.get('model')}",
            fontes_rag=_fontes_str(ctx.fontes_rag),
            tokens_input=usage.get("input_tokens"),
            tokens_output=usage.get("output_tokens"),
            custo_estimado=custo_passo,
        )

        passo_info = {
            "passo": budget.passos,
            "provider": resp.get("provider"),
            "model": resp.get("model"),
            "stop_reason": resp.get("stop_reason"),
            "tokens": (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0),
            "ferramentas": [tc.get("name") for tc in (resp.get("tool_calls") or [])],
        }
        passos.append(passo_info)
        await _emitir(on_event, "passo", passo_info)
        # Sugestão 3 — evento por passo (SEM PII: só text_para_log pseudonimizado +
        # NOMES das tools; nunca `args`/mapa/PII real).
        _lf.registrar_evento(_trace, name=f"passo:{budget.passos}", metadata={
            "provider": resp.get("provider"), "model": resp.get("model"),
            "stop_reason": resp.get("stop_reason"),
            "ferramentas": passo_info["ferramentas"],
            "decisao_modelo": (resp.get("text_para_log") or "")[:500],
            "tokens": passo_info["tokens"],
            "custo_estimado_brl": round(custo_passo, 4),
        })

        tool_calls = resp.get("tool_calls") or []
        stop = resp.get("stop_reason")

        # L7: truncou por max_tokens no meio → NÃO conclui vazio nem executa uma
        # tool possivelmente incompleta; conclui com aviso.
        if stop == "max_tokens":
            final = (resp.get("text", "") or
                     "(resposta truncada por limite de tokens do turno; refine a solicitação)")
            aviso_parada = ("Turno truncado por max_tokens do provider — "
                            "resultado possivelmente parcial.")
            break
        # L7: pause_turn → o turno foi PAUSADO pelo provider (thinking longo);
        # reanexa o parcial e CONTINUA (não conclui).
        if stop == "pause_turn":
            messages.append(_assistant_turn(resp.get("text", "") or "", tool_calls))
            continue
        # Sem tool_use → conclusão natural do agente.
        if not tool_calls:
            final = resp.get("text", "") or ""
            break

        # Anexa o turno assistant (text + tool_use) e processa as tool_calls.
        messages.append(_assistant_turn(resp.get("text", "") or "", tool_calls))
        pausa = await _processar_tool_calls(
            tool_calls, ctx=ctx, messages=messages, on_event=on_event,
            apenas_leitura=apenas_leitura)
        if pausa is not None:
            return await _persistir_e_pausar(
                pending=pausa["pending"], restantes=pausa["restantes"],
                messages=messages, passos=passos, budget=budget,
                custo_total=custo_total, prompt_log_base=prompt_log_base,
                pii_removida=pii_removida, user=user, case_id=case_id,
                role=role, on_event=on_event)

    if final is None:
        # Laço encerrado por ORÇAMENTO (passos/tokens/custo) sem resposta natural.
        aviso_parada = aviso_parada or budget.motivo_parada()
        final = (
            "Não foi possível concluir dentro do orçamento do agente. "
            "Resultado parcial acima; revise e refine a solicitação."
        )

    # 4) Gate de citações (anti-alucinação) sobre o texto FINAL.
    alertas: list[str] = []
    revisao_obrigatoria = False
    try:
        from app.services.ai.core.response_validator import validar
        # I5/B4: fontes REAIS consultadas pelas tools (antes `fontes=None` →
        # toda resposta saía "SEM BASE VERIFICÁVEL" mesmo com RAG usado).
        validado = await validar(db, final, exige_fonte=True,
                                 fontes=ctx.fontes_rag or None)
        final = validado.get("conteudo", final)
        alertas = validado.get("alertas", []) or []
        revisao_obrigatoria = bool(validado.get("revisao_obrigatoria"))
    except Exception as e:
        logger.warning("response_validator falhou (seguindo com aviso): %s", str(e)[:200])
        alertas = ["Validação de citações indisponível — confira as fontes manualmente."]
        revisao_obrigatoria = True

    if aviso_parada:
        alertas = [aviso_parada, *alertas]
    if alertas_extra:
        alertas = [*alertas_extra, *alertas]

    _lf.flush()
    resultado_final = {
        "status": "ok",
        "resposta": final,
        "is_rascunho": True,
        "passos": passos,
        "custo_estimado_brl": round(custo_total, 4),
        "alertas": alertas,
        "revisao_obrigatoria": revisao_obrigatoria,
        # I5: fontes consultadas (metadados, sem conteúdo) — mesmo formato do
        # orchestrator, para a UI exibir a base da resposta.
        "fontes": [
            {"titulo": f.get("titulo"), "categoria": f.get("categoria"),
             "fonte": f.get("fonte")} for f in ctx.fontes_rag
        ],
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
