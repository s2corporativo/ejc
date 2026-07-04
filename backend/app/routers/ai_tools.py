"""
Endpoints do MÓDULO IA PROFISSIONAL do EJC (agente por tarefa).
Tudo passa pelo ai_gateway; resultado sempre RASCUNHO (HITL/OAB). JWT obrigatório.
Rota: /api/ai/executar e /api/ai/status.
"""
from __future__ import annotations
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.system_prompts import TarefaIA
from app.services.ai_gateway import executar_tarefa_ia
from app.services.ai_guard import sanitizar_ou_abortar

router = APIRouter(prefix="/ai", tags=["IA Jurídica Pro"])


class AiRequest(BaseModel):
    tarefa: TarefaIA = Field(..., description="Tipo de tarefa de IA")
    mensagem: str = Field(..., min_length=5, max_length=12000)
    case_id: Optional[str] = Field(None, description="Caso para contexto")
    usar_rag: bool = Field(False, description="Buscar na base de conhecimento (RAG)")
    nivel_inteligencia: str = Field("alto", description="padrao, alto ou maximo")


class AiResponse(BaseModel):
    conteudo: str
    modelo: str
    provider: str
    tarefa: str
    is_rascunho: bool = True
    requer_revisao: bool = True
    tokens_usados: int
    custo_estimado_brl: float
    aviso: str = "RASCUNHO — revisão humana obrigatória antes de qualquer uso (OAB)."


def _ai_enabled() -> bool:
    # Default LIGADO: funcional já com Groq (grátis); Claude entra quando houver
    # ANTHROPIC_API_KEY (tarefas complexas). Para desligar: AI_ENABLED=false no .env.
    return os.getenv("AI_ENABLED", "true").lower() == "true"


def _bloquear_cliente_externo(cu: User) -> None:
    """IA interna não é exposta ao portal do cliente (mesma regra do núcleo)."""
    if str(getattr(cu, "role", "")) == "cliente_externo":
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Funções de IA internas não estão disponíveis no portal do cliente.")


@router.get("/status")
async def status_ia(cu: User = Depends(get_current_user)):
    _bloquear_cliente_externo(cu)
    return {
        "ai_enabled": _ai_enabled(),
        "anthropic_configurado": bool(os.getenv("ANTHROPIC_API_KEY", "")),
        "groq_configurado": bool(os.getenv("GROQ_API_KEY", "")),
        "modelo_rapido": os.getenv("ANTHROPIC_MODEL_RAPIDO", "claude-haiku-4-5-20251001"),
        "modelo_complexo": os.getenv("ANTHROPIC_MODEL_COMPLEXO", "(=rapido)"),
        "tarefas": [t.value for t in TarefaIA],
        "niveis_inteligencia": ["padrao", "alto", "maximo"],
        "aviso": "Todos os resultados são rascunhos. Revisão humana obrigatória.",
    }


@router.post("/executar", response_model=AiResponse)
async def executar_ia(
    req: AiRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _bloquear_cliente_externo(cu)
    if not _ai_enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Módulo de IA não habilitado. Defina AI_ENABLED=true no .env.")
    # Bloco 5 (continuação): case_id existia mas sem checagem de ownership.
    escopo_cli = None
    if req.case_id:
        from app.core.ownership import verificar_acesso_caso
        from app.services.ai_service import _escopo_cliente_do_caso
        await verificar_acesso_caso(db, cu, req.case_id)
        escopo_cli = await _escopo_cliente_do_caso(db, req.case_id)

    # Guarda LGPD (auditoria 2026-07-02): mensagem livre do usuário ia direto ao
    # provedor externo sem sanitização — aborta se sobrar PII estrutural.
    mensagem_limpa, _pii = sanitizar_ou_abortar(req.mensagem)

    contexto_rag = None
    if req.usar_rag:
        try:
            from app.services.ai_service import buscar_contexto_rag
            ctx = await buscar_contexto_rag(db, mensagem_limpa, limite=5, scope_client_id=escopo_cli)
            contexto_rag = [str(c.get("conteudo") or "") for c in (ctx or []) if c.get("conteudo")]
        except Exception:
            contexto_rag = None
    try:
        resultado = await executar_tarefa_ia(
            tarefa=req.tarefa, mensagem=mensagem_limpa, case_id=req.case_id,
            contexto_rag=contexto_rag, user_id=cu.id, db=db,
            nivel_inteligencia=req.nivel_inteligencia,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except RuntimeError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    return AiResponse(**resultado)
