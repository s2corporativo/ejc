from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dpt_diagnostico import DptDiagnosticEstado
from app.models.user import User
from app.modules.dpt360.company_service import get_company_profile
from app.modules.dpt360.diagnostic_service import build_diagnostic_readiness
from app.modules.dpt360.schemas import DptActionRequest, DptActionResponse
from app.services.ai.core.dpt360_protocol import build_dpt_instruction, parse_structured_content
from app.services.ai.core.dpt360_registry import ensure_dpt360_registered
from app.services.ai.core.orchestrator import orchestrator

_ALLOWED_DOMAINS = {
    "empresarial",
    "tributario",
    "ambiental",
    "administrativo",
    "trabalhista",
    "contratual",
    "societario",
    "digital_lgpd",
    "lgpd",
}

_ACTION_TASK = {
    "conselho": "conselho_empresarial",
    "preflight": "preflight_empresarial",
    "diagnostico": "diagnostico_empresarial",
}


def _minimal_company_context(profile) -> dict:
    """Contexto empresarial suficiente para análise sem duplicar PII no prompt."""
    return {
        "empresa_ref": profile.id,
        "localidade": {"cidade": profile.cidade, "estado": profile.estado},
        "areas_com_casos": profile.areas_com_casos,
        "casos_abertos": profile.casos_abertos,
        "prazos_pendentes": profile.prazos_pendentes,
        "documentos_vinculados": profile.documentos,
        "sociedades_registradas": profile.sociedades,
        "operacoes_lgpd": profile.operacoes_lgpd,
        "operacoes_lgpd_alto_risco": profile.operacoes_lgpd_alto_risco,
        "autos_ambientais": profile.autos_ambientais,
        "saude_juridica": [
            {
                "area": item.area,
                "classificacao": item.classificacao,
                # É apenas contagem quantitativa do Legal Twin, nunca conteúdo
                # documental ou evidência textual enviada ao provider.
                "evidencias": item.evidencias,
            }
            for item in profile.health
        ],
        "regra": "sem_dados ou Não avaliado não significam regularidade",
    }


async def run_dpt_action(
    db: AsyncSession,
    user: User,
    request: DptActionRequest,
) -> DptActionResponse | None:
    profile = await get_company_profile(db, user, request.client_id)
    if profile is None:
        return None

    ensure_dpt360_registered()

    requested_domain = (request.area or "empresarial").strip().lower()
    domain = requested_domain if requested_domain in _ALLOWED_DOMAINS else "empresarial"
    instruction = build_dpt_instruction(
        action=request.action,
        company_context=_minimal_company_context(profile),
        question=request.question,
        area=domain,
    )

    # O orquestrador central chama obrigatoriamente `ai_gateway` e sua barreira
    # final de PII. O nome empresarial é fornecido como entidade adicional para
    # pseudonimização reversível caso o usuário o repita na pergunta livre.
    result = await orchestrator.run(
        db=db,
        user=user,
        task_type=_ACTION_TASK[request.action],
        domain=domain,
        mensagem=instruction,
        usar_rag=True,
        nivel_inteligencia="alto",
        params={
            "module_key": "dpt360",
            "surface": "dpt360",
            "nomes_proteger": [profile.nome] if profile.nome else [],
        },
    )

    structured = parse_structured_content(str(result.get("conteudo") or ""))
    alerts = [str(item) for item in (result.get("alertas") or [])]
    if structured is None:
        alerts.append(
            "A IA não devolveu JSON estruturado válido; o conteúdo permanece rascunho e exige revisão humana antes de qualquer reaproveitamento."
        )
    if result.get("critica_adversarial") is None:
        alerts.append(
            "Crítica adversarial especializada do DPT ainda não foi executada por esta tarefa; revisão humana permanece obrigatória."
        )

    citations = result.get("citacoes") or []
    if not isinstance(citations, list):
        citations = [citations]

    # Persistência do diagnóstico (migração 141): ao executar a action
    # `diagnostico`, grava-se o run em estado `rascunho` para o histórico e
    # para o contador "diagnósticos pendentes" do dashboard. HITL mantido:
    # `requer_revisao=True` e nenhum run nasce revisado.
    if request.action == "diagnostico":
        readiness = await build_diagnostic_readiness(
            db, user, request.client_id, "completo", persistir=True
        )
        if readiness is not None:
            # Marca o run criado como coberto pela análise de IA desta action.
            await db.flush()
            from sqlalchemy import select  # noqa: E402

            from app.models.dpt_diagnostico import DptDiagnosticRun  # noqa: E402

            stmt = (
                select(DptDiagnosticRun)
                .where(
                    DptDiagnosticRun.client_id == request.client_id,
                    DptDiagnosticRun.tipo == "completo",
                    DptDiagnosticRun.estado == DptDiagnosticEstado.rascunho.value,
                )
                .order_by(DptDiagnosticRun.created_at.desc())
                .limit(1)
            )
            ultimo_run = (await db.execute(stmt)).scalar_one_or_none()
            if ultimo_run is not None:
                ultimo_run.estado = DptDiagnosticEstado.em_revisao.value

    return DptActionResponse(
        action=request.action,
        client_id=request.client_id,
        conteudo=str(result.get("conteudo") or ""),
        estruturado=structured,
        fontes=list(result.get("fontes") or []),
        citacoes=citations,
        alertas=alerts,
        critica_adversarial=result.get("critica_adversarial"),
        is_rascunho=bool(result.get("is_rascunho", True)),
        requer_revisao=bool(result.get("requer_revisao", True)),
        status_hitl=str(result.get("status_hitl") or "gerado"),
        aviso_hitl=str(result.get("aviso_hitl") or "Revisão humana obrigatória."),
        log_id=str(result.get("log_id")) if result.get("log_id") else None,
    )
