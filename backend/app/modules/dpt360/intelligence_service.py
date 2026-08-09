from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.modules.dpt360.company_service import get_company_profile
from app.modules.dpt360.schemas import DptActionRequest, DptActionResponse
from app.services.ai.core.dpt360_protocol import build_dpt_instruction, parse_structured_content
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


def _minimal_company_context(profile) -> dict:
    """Contexto empresarial suficiente para análise sem duplicar PII no prompt."""
    return {
        "empresa_ref": profile.id,
        "localidade": {
            "cidade": profile.cidade,
            "estado": profile.estado,
        },
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

    requested_domain = (request.area or "empresarial").strip().lower()
    domain = requested_domain if requested_domain in _ALLOWED_DOMAINS else "empresarial"
    instruction = build_dpt_instruction(
        action=request.action,
        company_context=_minimal_company_context(profile),
        question=request.question,
        area=domain,
    )

    result = await orchestrator.run(
        db=db,
        user=user,
        task_type=domain,
        domain=domain,
        mensagem=instruction,
        usar_rag=True,
        nivel_inteligencia="alto",
        params={"module_key": "dpt360", "surface": "dpt360"},
    )

    structured = parse_structured_content(str(result.get("conteudo") or ""))
    alerts = [str(item) for item in (result.get("alertas") or [])]
    if structured is None:
        alerts.append(
            "A IA não devolveu JSON estruturado válido; o conteúdo permanece rascunho e exige revisão humana antes de qualquer reaproveitamento."
        )

    citations = result.get("citacoes") or []
    if not isinstance(citations, list):
        citations = [citations]

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
