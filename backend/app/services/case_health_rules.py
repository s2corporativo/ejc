"""Score e indicadores determinísticos de saúde operacional do caso."""
from __future__ import annotations

from typing import Any


def _indicator(
    code: str,
    severity: str,
    message: str,
    action: str,
    *,
    count: int | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "message": message,
        "recommended_action": action,
    }
    if count is not None:
        item["count"] = count
    return item


def assess_operational_health(
    *,
    case_status: str,
    has_judicial_process: bool,
    inactive_days: int,
    stale_days: int,
    metrics: dict[str, int],
) -> dict[str, Any]:
    """Calcula score sem acesso ao banco; reutilizável pelo Dashboard."""
    indicators: list[dict[str, Any]] = []
    score = 100
    active_case = case_status not in {"encerrado", "arquivado"}

    overdue_deadlines = metrics["overdue_deadlines"]
    critical_deadlines = metrics["deadlines_next_3_days"]
    actionable_tasks = metrics["actionable_tasks"]
    active_processes = metrics["active_processes"]
    overdue_requests = metrics["overdue_client_requests"]
    unreviewed_ai_docs = metrics["unreviewed_ai_documents"]
    docs_in_review = metrics["documents_in_review"]

    if overdue_deadlines:
        indicators.append(
            _indicator(
                "OVERDUE_DEADLINES",
                "critical",
                "Há prazos vencidos sem conclusão ou cancelamento.",
                "Abrir a Central de Agenda e Prazos e regularizar imediatamente.",
                count=overdue_deadlines,
            )
        )
        score -= min(45, 20 + overdue_deadlines * 5)
    if critical_deadlines:
        indicators.append(
            _indicator(
                "DEADLINES_NEXT_3_DAYS",
                "high",
                "Há prazos com vencimento nos próximos três dias.",
                "Confirmar ciência, responsável e tarefa vinculada.",
                count=critical_deadlines,
            )
        )
        score -= min(20, 5 + critical_deadlines * 3)
    if active_case and inactive_days > stale_days:
        indicators.append(
            _indicator(
                "CASE_INACTIVE",
                "high",
                f"Caso sem atividade relevante há {inactive_days} dias.",
                "Registrar revisão estratégica e definir o próximo passo.",
            )
        )
        score -= 20
    if active_case and actionable_tasks == 0:
        indicators.append(
            _indicator(
                "NO_ACTIONABLE_TASK",
                "medium",
                "Caso ativo sem tarefa executável em aberto.",
                "Criar a próxima ação com responsável e data limite.",
            )
        )
        score -= 10
    if active_case and has_judicial_process and active_processes == 0:
        indicators.append(
            _indicator(
                "MISSING_ACTIVE_PROCESS",
                "high",
                "Caso marcado como judicial sem processo ativo na entidade canônica.",
                "Cadastrar ou desarquivar o processo principal.",
            )
        )
        score -= 20
    if overdue_requests:
        indicators.append(
            _indicator(
                "CLIENT_REQUEST_OVERDUE",
                "high",
                "Solicitações de cliente ultrapassaram o prazo de retorno.",
                "Responder o cliente e concluir ou reprogramar a solicitação.",
                count=overdue_requests,
            )
        )
        score -= min(20, 8 + overdue_requests * 3)
    if unreviewed_ai_docs:
        indicators.append(
            _indicator(
                "AI_DOCUMENTS_UNREVIEWED",
                "medium",
                "Há documentos gerados por IA sem revisão humana registrada.",
                "Revisar, corrigir e aprovar antes de uso externo ou protocolo.",
                count=unreviewed_ai_docs,
            )
        )
        score -= min(15, 5 + unreviewed_ai_docs * 2)
    if docs_in_review:
        indicators.append(
            _indicator(
                "DOCUMENTS_IN_REVIEW",
                "low",
                "Há peças em rascunho ou revisão.",
                "Conferir a fila de produção e os responsáveis.",
                count=docs_in_review,
            )
        )
        score -= min(8, docs_in_review)

    score = max(0, score)
    level = (
        "healthy"
        if score >= 85
        else "attention"
        if score >= 65
        else "risk"
        if score >= 40
        else "critical"
    )
    return {
        "score": score,
        "level": level,
        "indicators": indicators,
        "next_recommended_action": (
            indicators[0]["recommended_action"]
            if indicators
            else "Manter o acompanhamento e revisar o caso na próxima rotina."
        ),
    }
