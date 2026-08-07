# ── app/routers/ai_core.py ───────────────────────────────────────────────────
# ENDPOINTS CENTRAIS do Núcleo Único de IA ("Cérebro EJC") — Etapa 8.
#
# frontend → backend → ai_gateway → Núcleo Único → agente interno → skill →
# RAG/contexto → provider seguro → validação → AILog → HITL → resposta.
#
# O frontend envia APENAS intenção/domínio/IDs/pergunta/parâmetros mínimos;
# o contexto real é montado no backend sob RBAC/ownership. Endpoints antigos
# de IA permanecem como wrappers deste núcleo (matriz de migração em
# docs/ai/EJC_AI_ENDPOINT_MIGRATION_MATRIX.md).
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.ai.core.orchestrator import orchestrator
from app.services.ai.core.agent_registry import AGENT_REGISTRY
from app.services.ai.core.skill_registry import listar_skills
from app.services.ai.core.ejc_skill_catalog import native_skill_coverage
from app.core.rate_limit import rate_limit

router = APIRouter(prefix="/ai/core", tags=["IA — Núcleo Único"])


def _staff_only(cu: User) -> None:
    """cliente_externo NUNCA acessa o núcleo (o orchestrator revalida)."""
    if str(getattr(cu, "role", "")) == "cliente_externo":
        raise HTTPException(403, "Funções de IA internas não estão disponíveis no portal do cliente.")


# ── Schemas ───────────────────────────────────────────────────────────────────

class CoreChatRequest(BaseModel):
    mensagem: str = Field(..., min_length=3, max_length=12000)
    domain: Optional[str] = Field(None, max_length=60)
    module_key: Optional[str] = Field(None, max_length=60)
    surface: Optional[str] = Field(None, max_length=80)
    case_id: Optional[str] = None
    nivel_inteligencia: str = Field("alto", description="padrao | alto | maximo | executivo")


class CoreTaskRequest(BaseModel):
    task_type: str = Field(..., min_length=2, max_length=60)
    domain: Optional[str] = Field(None, max_length=60)
    mensagem: str = Field(..., min_length=3, max_length=12000)
    case_id: Optional[str] = None
    document_id: Optional[str] = None
    process_id: Optional[str] = None
    params: Optional[dict] = None
    module_key: Optional[str] = Field(None, max_length=60)
    surface: Optional[str] = Field(None, max_length=80)
    usar_rag: bool = True
    nivel_inteligencia: str = "alto"


class CoreAnalyzeRequest(BaseModel):
    domain: str = Field(..., min_length=2, max_length=60)
    mensagem: str = Field(..., min_length=3, max_length=12000)
    case_id: Optional[str] = None
    document_id: Optional[str] = None
    process_id: Optional[str] = None
    params: Optional[dict] = None
    module_key: Optional[str] = Field(None, max_length=60)
    surface: Optional[str] = Field(None, max_length=80)
    usar_rag: bool = True
    nivel_inteligencia: str = "alto"


class CoreGenerateRequest(BaseModel):
    tipo: str = Field(..., description="minuta | peca | mensagem_cliente | relatorio")
    mensagem: str = Field(..., min_length=3, max_length=12000)
    case_id: Optional[str] = None
    params: Optional[dict] = None
    module_key: Optional[str] = Field(None, max_length=60)
    surface: Optional[str] = Field(None, max_length=80)
    nivel_inteligencia: str = "alto"


class CoreReportRequest(BaseModel):
    domain: str = Field(..., min_length=2, max_length=60)
    mensagem: Optional[str] = Field(None, max_length=12000)
    case_id: Optional[str] = None
    params: Optional[dict] = None
    module_key: Optional[str] = Field(None, max_length=60)
    surface: Optional[str] = Field(None, max_length=80)


def _native_params(
    params: Optional[dict],
    module_key: Optional[str],
    surface: Optional[str],
) -> dict:
    merged = dict(params or {})
    if module_key:
        merged["module_key"] = module_key
    if surface:
        merged["surface"] = surface
    return merged


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/chat", dependencies=[Depends(rate_limit("ai-core-chat", 20))])
async def core_chat(
    body: CoreChatRequest,
    cu: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _staff_only(cu)
    return await orchestrator.run(
        db=db, user=cu, task_type="chat", domain=body.domain,
        mensagem=body.mensagem, case_id=body.case_id,
        params=_native_params(None, body.module_key, body.surface),
        nivel_inteligencia=body.nivel_inteligencia,
    )


@router.post("/task", dependencies=[Depends(rate_limit("ai-core-task", 15))])
async def core_task(
    body: CoreTaskRequest,
    cu: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _staff_only(cu)
    return await orchestrator.run(
        db=db, user=cu, task_type=body.task_type, domain=body.domain,
        mensagem=body.mensagem, case_id=body.case_id,
        document_id=body.document_id, process_id=body.process_id,
        params=_native_params(body.params, body.module_key, body.surface),
        usar_rag=body.usar_rag,
        nivel_inteligencia=body.nivel_inteligencia,
    )


@router.post("/analyze", dependencies=[Depends(rate_limit("ai-core-analyze", 15))])
async def core_analyze(
    body: CoreAnalyzeRequest,
    cu: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _staff_only(cu)
    return await orchestrator.run(
        db=db, user=cu, task_type=f"{body.domain}_analysis", domain=body.domain,
        mensagem=body.mensagem, case_id=body.case_id,
        document_id=body.document_id, process_id=body.process_id,
        params=_native_params(body.params, body.module_key, body.surface),
        usar_rag=body.usar_rag,
        nivel_inteligencia=body.nivel_inteligencia,
    )


@router.post("/generate", dependencies=[Depends(rate_limit("ai-core-generate", 15))])
async def core_generate(
    body: CoreGenerateRequest,
    cu: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _staff_only(cu)
    task = "legal_draft" if body.tipo in ("minuta", "peca") else body.tipo
    return await orchestrator.run(
        db=db, user=cu, task_type=task, mensagem=body.mensagem,
        case_id=body.case_id,
        params=_native_params(body.params, body.module_key, body.surface),
        nivel_inteligencia=body.nivel_inteligencia,
    )


@router.post("/report", dependencies=[Depends(rate_limit("ai-core-report", 10))])
async def core_report(
    body: CoreReportRequest,
    cu: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _staff_only(cu)
    return await orchestrator.run(
        db=db, user=cu, task_type="report", domain=body.domain,
        mensagem=body.mensagem or f"Gere o relatório executivo do domínio {body.domain}.",
        case_id=body.case_id,
        params=_native_params(body.params, body.module_key, body.surface),
    )


# ── Introspecção (staff) — metadados apenas; nunca prompts/handlers internos ──

@router.get("/agents")
async def core_agents(cu: User = Depends(get_current_user)):
    _staff_only(cu)
    return [
        {
            "nome": a.nome, "descricao": a.descricao, "dominios": a.dominios,
            "tarefa_padrao": a.tarefa_padrao.value, "exige_fonte": a.exige_fonte,
            "roles_permitidos": a.roles_permitidos, "skills": a.skills,
        }
        for a in AGENT_REGISTRY.values()
    ]


@router.get("/skills")
async def core_skills(cu: User = Depends(get_current_user)):
    _staff_only(cu)
    return listar_skills()


@router.get("/native-skills/coverage")
async def core_native_skills_coverage(cu: User = Depends(get_current_user)):
    _staff_only(cu)
    return native_skill_coverage()


@router.get("/status")
async def core_status(cu: User = Depends(get_current_user)):
    """Estado do núcleo. Só booleans/nomes — NUNCA valores de chave."""
    _staff_only(cu)
    from app.core.config import get_settings
    s = get_settings()
    return {
        "nucleo": "SingleAICoreOrchestrator",
        "agente_coordenador": "EJCCoordinatorAgent",
        "agentes": len(AGENT_REGISTRY),
        "skills": len(listar_skills()),
        "skills_nativas": native_skill_coverage(),
        "providers": {
            "anthropic": bool(s.ANTHROPIC_ENABLED and s.ANTHROPIC_API_KEY),
            "groq": bool(s.GROQ_API_KEY),
            "maritaca": bool(s.MARITACA_ENABLED and s.MARITACA_API_KEY),
        },
        "policy": {
            "externos_permitidos": bool(s.AI_EXTERNAL_PROVIDERS_ALLOWED),
            "sanitizacao_para_externo": bool(s.AI_REQUIRE_SANITIZATION_FOR_EXTERNAL),
            "hitl_obrigatorio": bool(s.AI_REQUIRE_HITL),
            "prioridade": s.AI_PROVIDER_PRIORITY,
        },
        "aviso": "Toda resposta jurídica é rascunho sujeito à revisão humana (HITL — OAB).",
    }
