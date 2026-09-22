# ── app/services/ai/core/capacidades.py ──────────────────────────────────────
# UMA PORTA DE IA POR CAPACIDADE (item I1 da análise E2E de 03/09/2026).
#
# O sistema tinha ~25 endpoints de IA com pipelines próprios: a qualidade da
# resposta dependia da PORTA usada, não do problema jurídico. Aqui existem
# CINCO capacidades — e só elas:
#
#   analisar · redigir · resumir · conversar · extrair
#
# Todas resolvem no MESMO orquestrador (`SingleAICoreOrchestrator.run`), que já
# aplica sigilo do caso, escopo cliente+caso, RAG, nível por tarefa, gate de
# citações, HITL e AILog. Este módulo NÃO reimplementa nada disso: traduz
# capacidade → `task_type` do classificador de intenção e normaliza a resposta.
#
# Regras:
#   • `nivel_inteligencia` sai como None por padrão → quem decide é o PISO por
#     tarefa do gateway (`_nivel_piso`). Forçar "alto" em toda chamada era gasto
#     sem critério e escondia o roteamento real.
#   • `hitl_policy.aplicar()` é o carimbo canônico de rascunho — inclusive no
#     envelope de resultado legado (`canonizar`).
#   • cliente_externo nunca entra (o orquestrador revalida; aqui é a 1ª barreira).
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.services.ai.core import hitl_policy
from app.services.ai.core.orchestrator import orchestrator
from app.services.system_prompts import TarefaIA

# As cinco capacidades. Porta nova de IA nasce mapeada em uma delas — não como
# um sexto pipeline.
CAPACIDADES: tuple[str, ...] = ("analisar", "redigir", "resumir", "conversar", "extrair")

# Capacidade → task_type entendido por `intent_classifier.classify_intent`
# (que resolve agente interno + TarefaIA + exige_fonte).
_TASK_TYPE_POR_CAPACIDADE: dict[str, str] = {
    "analisar": "analise_caso",        # → CaseAgent
    "redigir": "legal_draft",          # → LegalWritingAgent
    "resumir": "resumo",               # → DocumentAgent
    "conversar": "chat",               # → CaseAgent (Q&A com contexto/RAG)
    "extrair": "document_extraction",  # → DocumentExtractionAgent (JSON)
}

# Perfis das "IAs especializadas" → domínio do classificador. Perfil sem
# agente dedicado (comercial/atendimento) fica sem domínio: cai no agente
# padrão da capacidade, que é o comportamento correto — e não inventa rota.
_DOMINIO_POR_PERFIL: dict[str, str] = {
    "financeira": "financeiro",
    "societaria": "societario",
    "juridica": "analise_caso",
}

# TarefaIA (contrato antigo de `/ai/executar`) → capacidade canônica.
# Serve ao adaptador e a quem precisa dizer "esta tarefa é qual porta".
TAREFA_PARA_CAPACIDADE: dict[TarefaIA, str] = {
    TarefaIA.TRIAGEM: "analisar",
    TarefaIA.ANALISE_CASO: "analisar",
    TarefaIA.DOSSIE: "analisar",
    TarefaIA.AMBIENTAL: "analisar",
    TarefaIA.TRABALHISTA: "analisar",
    TarefaIA.CRIMINAL: "analisar",
    TarefaIA.FAMILIA: "analisar",
    TarefaIA.ADMINISTRATIVO: "analisar",
    TarefaIA.SUCESSOES: "analisar",
    TarefaIA.IMOBILIARIO: "analisar",
    TarefaIA.CONSTITUCIONAL: "analisar",
    TarefaIA.JUIZADOS: "analisar",
    TarefaIA.CIVEL: "analisar",
    TarefaIA.HONORARIOS: "analisar",
    TarefaIA.AUDIENCIA: "analisar",
    TarefaIA.MINUTAS: "redigir",
    TarefaIA.RESUMO: "resumir",
    TarefaIA.PRAZOS: "extrair",
    TarefaIA.PESQUISA_JURIDICA: "conversar",
    TarefaIA.RAG_QUERY: "conversar",
    TarefaIA.DEFAULT: "conversar",
}


def capacidade_da_tarefa(tarefa: TarefaIA | str) -> str:
    """TarefaIA → capacidade canônica (fallback conservador: `conversar`)."""
    if isinstance(tarefa, TarefaIA):
        return TAREFA_PARA_CAPACIDADE.get(tarefa, "conversar")
    for t, cap in TAREFA_PARA_CAPACIDADE.items():
        if t.value == str(tarefa):
            return cap
    return "conversar"


def _bloquear_cliente_externo(user: Any) -> None:
    """IA interna não é exposta ao portal do cliente.

    `UserRole` é `(str, Enum)` sem `__str__`: `str(role)` devolve
    "UserRole.cliente_externo" e o gate NUNCA dispara. Compara pelo valor —
    funciona para enum e para string.
    """
    if user is None:
        return
    role = getattr(user, "role", "")
    if getattr(role, "value", role) == "cliente_externo":
        raise HTTPException(
            403, "Funções de IA internas não estão disponíveis no portal do cliente."
        )


def _tokens(bruto: dict) -> dict[str, int | None]:
    entrada = bruto.get("tokens_input")
    saida = bruto.get("tokens_output")
    total = bruto.get("tokens_usados")
    if total is None and (entrada is not None or saida is not None):
        total = int(entrada or 0) + int(saida or 0)
    return {"input": entrada, "output": saida, "total": total}


def canonizar(capacidade: str, bruto: dict, *, tarefa: str | None = None) -> dict:
    """Resultado (do orquestrador OU de porta legada) → envelope canônico.

    Aceita as duas grafias históricas de cada campo (`resposta`/`conteudo`,
    `ai_log_id`/`log_id`, `provedor`/`provider`, `fontes`/`fontes_rag`) para que
    o adaptador de uma porta antiga devolva o contrato novo sem que o chamador
    precise saber por qual pipeline passou.
    """
    envelope = {
        "conteudo": bruto.get("conteudo") or bruto.get("resposta") or "",
        "capacidade": capacidade,
        "tarefa": bruto.get("tarefa") or tarefa,
        "modelo": bruto.get("modelo"),
        "provider": bruto.get("provider") or bruto.get("provedor"),
        "fallback_ativado": bool(bruto.get("fallback_ativado", False)),
        "fallback_motivo": bruto.get("fallback_motivo"),
        "log_id": bruto.get("log_id") or bruto.get("ai_log_id"),
        "fontes_rag": list(bruto.get("fontes") or bruto.get("fontes_rag") or []),
        "citacoes": list(bruto.get("citacoes") or []),
        # `alertas` carrega o gate de citações e o aviso de crítica adversarial
        # indisponível: é informação de SEGURANÇA da revisão humana, não enfeite.
        "alertas": list(bruto.get("alertas") or []),
        "custo_estimado_brl": float(bruto.get("custo_estimado_brl") or 0.0),
        "tokens": _tokens(bruto),
        "revisao_obrigatoria": bool(bruto.get("revisao_obrigatoria", False)),
        "critica_adversarial": bruto.get("critica_adversarial"),
    }
    # Carimbo canônico (is_rascunho / requer_revisao / status_hitl / aviso_hitl).
    envelope = hitl_policy.aplicar(envelope)
    envelope.pop("revisao_obrigatoria", None)
    if envelope.get("critica_adversarial") is None:
        envelope.pop("critica_adversarial", None)
    return envelope


async def _executar(
    capacidade: str,
    db,
    user,
    *,
    case_id: str | None,
    texto: str | None,
    mensagem: str | None,
    area: str | None,
    perfil: str | None,
    opcoes: dict | None,
) -> dict:
    if capacidade not in _TASK_TYPE_POR_CAPACIDADE:
        raise HTTPException(400, f"Capacidade desconhecida: {capacidade}")
    _bloquear_cliente_externo(user)

    conteudo = (mensagem or texto or "").strip()
    if not conteudo:
        raise HTTPException(422, "Informe o texto/mensagem da solicitação.")

    op = dict(opcoes or {})
    params = dict(op.pop("params", None) or {})
    for chave in ("module_key", "surface", "nomes_proteger", "prompt_extra"):
        valor = op.pop(chave, None)
        if valor:
            params[chave] = valor
    if perfil:
        params["perfil"] = perfil
    # Sobras de `opcoes` viram parâmetros do plano de skills (tipo_peca, fatos,
    # formato de extração…). Ficam no dossiê de auditoria do próprio pipeline.
    for chave, valor in op.items():
        if chave not in ("usar_rag", "nivel_inteligencia", "document_id", "process_id"):
            params.setdefault(chave, valor)

    dominio = (area or "").strip() or _DOMINIO_POR_PERFIL.get((perfil or "").strip())

    bruto = await orchestrator.run(
        db=db,
        user=user,
        task_type=_TASK_TYPE_POR_CAPACIDADE[capacidade],
        domain=dominio or None,
        mensagem=conteudo,
        case_id=case_id,
        document_id=(opcoes or {}).get("document_id"),
        process_id=(opcoes or {}).get("process_id"),
        params=params,
        usar_rag=bool((opcoes or {}).get("usar_rag", True)),
        # None de propósito: o PISO por tarefa decide o nível.
        nivel_inteligencia=(opcoes or {}).get("nivel_inteligencia"),
    )
    return canonizar(capacidade, bruto)


async def analisar(
    db, user, *, case_id=None, texto=None, mensagem=None, area=None,
    perfil=None, opcoes: dict | None = None,
) -> dict:
    """Análise jurídica de fatos/caso (teses, riscos, estratégia)."""
    return await _executar(
        "analisar", db, user, case_id=case_id, texto=texto, mensagem=mensagem,
        area=area, perfil=perfil, opcoes=opcoes,
    )


async def redigir(
    db, user, *, case_id=None, texto=None, mensagem=None, area=None,
    perfil=None, opcoes: dict | None = None,
) -> dict:
    """Redação de peça/minuta/comunicação — sempre RASCUNHO (OAB)."""
    return await _executar(
        "redigir", db, user, case_id=case_id, texto=texto, mensagem=mensagem,
        area=area, perfil=perfil, opcoes=opcoes,
    )


async def resumir(
    db, user, *, case_id=None, texto=None, mensagem=None, area=None,
    perfil=None, opcoes: dict | None = None,
) -> dict:
    """Resumo de texto/documento em pontos objetivos, sem acrescentar fato."""
    return await _executar(
        "resumir", db, user, case_id=case_id, texto=texto, mensagem=mensagem,
        area=area, perfil=perfil, opcoes=opcoes,
    )


async def conversar(
    db, user, *, case_id=None, texto=None, mensagem=None, area=None,
    perfil=None, opcoes: dict | None = None,
) -> dict:
    """Pergunta e resposta com contexto do escritório (RAG) — pesquisa inclusa."""
    return await _executar(
        "conversar", db, user, case_id=case_id, texto=texto, mensagem=mensagem,
        area=area, perfil=perfil, opcoes=opcoes,
    )


async def extrair(
    db, user, *, case_id=None, texto=None, mensagem=None, area=None,
    perfil=None, opcoes: dict | None = None,
) -> dict:
    """Extração estruturada (prazos, partes, valores, cláusulas) de um texto."""
    return await _executar(
        "extrair", db, user, case_id=case_id, texto=texto, mensagem=mensagem,
        area=area, perfil=perfil, opcoes=opcoes,
    )


PORTAS = {
    "analisar": analisar,
    "redigir": redigir,
    "resumir": resumir,
    "conversar": conversar,
    "extrair": extrair,
}
