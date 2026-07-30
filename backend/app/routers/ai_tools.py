"""
Endpoints do MÓDULO IA PROFISSIONAL do EJC (agente por tarefa).
Tudo passa pelo ai_gateway; resultado é minuta profissional sujeita à conferência
responsável antes de assinatura, protocolo ou envio externo. JWT obrigatório.
Rotas: /api/ai/executar e /api/ai/status.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.user import User
from app.services.ai_gateway import executar_tarefa_ia
from app.services.ai_guard import sanitizar_ou_abortar
from app.services.system_prompts import TarefaIA

router = APIRouter(prefix="/ai", tags=["IA Jurídica Pro"])


class AiRequest(BaseModel):
    tarefa: TarefaIA = Field(..., description="Tipo de tarefa de IA")
    mensagem: str = Field(..., min_length=5, max_length=12000)
    case_id: Optional[str] = Field(None, description="Caso para contexto")
    usar_rag: bool = Field(False, description="Buscar na base de conhecimento (RAG)")
    nivel_inteligencia: str = Field(
        "alto", description="padrao, alto, maximo ou executivo"
    )


class AiResponse(BaseModel):
    conteudo: str
    modelo: str
    provider: str
    tarefa: str
    # Campos mantidos por compatibilidade com consumidores existentes. O sentido
    # operacional é: minuta pronta para conferência, não documento juridicamente
    # assinado nem protocolado.
    is_rascunho: bool = True
    requer_revisao: bool = True
    tokens_usados: int
    custo_estimado_brl: float
    aviso: str = (
        "MINUTA GERADA POR IA — confira e assine antes de protocolar, enviar ao "
        "cliente ou usar oficialmente."
    )


def _ai_enabled() -> bool:
    # Fonte única: Settings recebe .env e o overlay do cofre de credenciais.
    return bool(get_settings().AI_ENABLED)


def _bloquear_cliente_externo(cu: User) -> None:
    """IA interna não é exposta ao portal do cliente (mesma regra do núcleo)."""
    if str(getattr(cu, "role", "")) == "cliente_externo":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Funções de IA internas não estão disponíveis no portal do cliente.",
        )


def _modelos_por_tarefa(settings) -> dict[str, dict[str, str | None]]:
    """Espelho público e auditável da resolução configurada no ai_gateway.

    Não afirma qual provider responderá uma chamada futura: isso depende de chave,
    kill-switch, soberania, prioridade e disponibilidade no instante da execução.
    Expõe corretamente o modelo configurado para cada candidato elegível.
    """
    rapido = settings.ANTHROPIC_MODEL_RAPIDO
    complexo = settings.ANTHROPIC_MODEL_COMPLEXO
    ollama_analise = getattr(settings, "OLLAMA_MODEL_ANALISE", None)
    ollama_peca = getattr(settings, "OLLAMA_MODEL_PETICAO", None)
    ollama_resumo = getattr(settings, "OLLAMA_MODEL_RESUMO", None)
    ollama_chat = getattr(settings, "OLLAMA_MODEL_CHAT", None)
    ollama_contrato = getattr(settings, "OLLAMA_MODEL_CONTRATO", None)

    return {
        "analise_juridica": {
            "ollama": ollama_analise,
            "anthropic": complexo,
            "maritaca": settings.MARITACA_MODEL,
            "groq": settings.GROQ_MODEL,
        },
        "elaboracao_peca": {
            "ollama": ollama_peca,
            "anthropic": complexo,
            "maritaca": settings.MARITACA_MODEL,
            "groq": settings.GROQ_MODEL,
        },
        "analise_contrato": {
            "ollama": ollama_contrato,
            "anthropic": complexo,
            "maritaca": settings.MARITACA_MODEL,
            "groq": settings.GROQ_MODEL,
        },
        "estrategia": {
            "ollama": ollama_analise,
            "anthropic": complexo,
            "maritaca": settings.MARITACA_MODEL,
            "groq": settings.GROQ_MODEL,
        },
        "auditoria_peca": {
            "ollama": ollama_peca,
            "anthropic": complexo,
            "maritaca": settings.MARITACA_MODEL,
            "groq": settings.GROQ_MODEL,
        },
        "jurimetria": {
            "ollama": ollama_analise,
            "anthropic": complexo,
            "maritaca": settings.MARITACA_MODEL,
            "groq": settings.GROQ_MODEL,
        },
        "critica_adversarial": {
            "ollama": ollama_analise,
            "anthropic": complexo,
            "maritaca": settings.MARITACA_MODEL,
            "groq": settings.GROQ_MODEL,
        },
        "resumo": {
            "ollama": ollama_resumo,
            "anthropic": rapido,
            "maritaca": settings.MARITACA_MODEL_RAPIDO,
            "groq": settings.GROQ_MODEL,
        },
        "chat_rapido": {
            "ollama": ollama_chat,
            "anthropic": rapido,
            "maritaca": settings.MARITACA_MODEL_RAPIDO,
            "groq": settings.GROQ_MODEL,
        },
    }


@router.get("/status")
async def status_ia(cu: User = Depends(get_current_user)):
    _bloquear_cliente_externo(cu)
    settings = get_settings()
    return {
        "ai_enabled": bool(settings.AI_ENABLED),
        "provedores": {
            "anthropic": {
                "habilitado": bool(settings.ANTHROPIC_ENABLED),
                "configurado": bool(settings.ANTHROPIC_API_KEY),
                "modelo_rapido": settings.ANTHROPIC_MODEL_RAPIDO,
                "modelo_complexo": settings.ANTHROPIC_MODEL_COMPLEXO,
            },
            "groq": {
                "habilitado": bool(settings.AI_EXTERNAL_PROVIDERS_ALLOWED),
                "configurado": bool(settings.GROQ_API_KEY),
                "modelo": settings.GROQ_MODEL,
            },
            "maritaca": {
                "habilitado": bool(settings.MARITACA_ENABLED),
                "configurado": bool(settings.MARITACA_API_KEY),
                "modelo": settings.MARITACA_MODEL,
                "modelo_rapido": settings.MARITACA_MODEL_RAPIDO,
            },
            "ollama": {
                "habilitado": True,
                "configurado": None,
                "observacao": (
                    "Disponibilidade efetiva é verificada em runtime pelo gateway/saúde; "
                    "este endpoint não presume que o serviço local esteja respondendo."
                ),
            },
        },
        # Compatibilidade com o painel antigo, agora usando a fonte tipada real.
        "anthropic_configurado": bool(settings.ANTHROPIC_API_KEY),
        "groq_configurado": bool(settings.GROQ_API_KEY),
        "modelo_rapido": settings.ANTHROPIC_MODEL_RAPIDO,
        "modelo_complexo": settings.ANTHROPIC_MODEL_COMPLEXO,
        "modelos_por_tarefa": _modelos_por_tarefa(settings),
        "tarefas": [t.value for t in TarefaIA],
        "niveis_inteligencia": ["padrao", "alto", "maximo", "executivo"],
        "roteamento": (
            "O provider efetivo é escolhido pelo ai_gateway conforme elegibilidade, "
            "prioridade, soberania, kill-switch e disponibilidade."
        ),
        "aviso": (
            "As saídas são minutas profissionais. Conferência e assinatura do "
            "advogado responsável são exigidas antes do uso externo."
        ),
    }


@router.post(
    "/executar",
    response_model=AiResponse,
    dependencies=[Depends(rate_limit("ai-executar", 15))],
)
async def executar_ia(
    req: AiRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _bloquear_cliente_externo(cu)
    if not _ai_enabled():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Módulo de IA não habilitado. Defina AI_ENABLED=true no ambiente.",
        )
    # Bloco 5 (continuação): case_id existia mas sem checagem de ownership.
    escopo_cli = None
    entidades = None
    if req.case_id:
        from app.core.ownership import verificar_acesso_caso
        from app.services.ai.entidades_caso import entidades_do_caso
        from app.services.ai_service import _escopo_cliente_do_caso

        await verificar_acesso_caso(db, cu, req.case_id)
        escopo_cli = await _escopo_cliente_do_caso(db, req.case_id)
        # Nomes do caso → marcadores reversíveis quando a tarefa vai a provider
        # externo em modo pseudonimizado (executar_tarefa_ia decide o modo pelo
        # `tarefa`); em MASCARAMENTO o gateway ignora `entidades` (sem efeito).
        entidades = await entidades_do_caso(db, req.case_id)

    # Guarda LGPD: mensagem livre não segue a provider externo com PII residual.
    mensagem_limpa, _pii = sanitizar_ou_abortar(req.mensagem)

    contexto_rag = None
    if req.usar_rag:
        try:
            from app.services.ai_service import buscar_contexto_rag

            ctx = await buscar_contexto_rag(
                db, mensagem_limpa, limite=5, scope_client_id=escopo_cli
            )
            contexto_rag = [
                str(c.get("conteudo") or "")
                for c in (ctx or [])
                if c.get("conteudo")
            ]
        except Exception:
            contexto_rag = None
    try:
        resultado = await executar_tarefa_ia(
            tarefa=req.tarefa,
            mensagem=mensagem_limpa,
            case_id=req.case_id,
            contexto_rag=contexto_rag,
            user_id=cu.id,
            db=db,
            nivel_inteligencia=req.nivel_inteligencia,
            entidades=entidades or None,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except RuntimeError as exc:
        # Camada de borda: detalhe técnico → log; usuário → mensagem operacional.
        from app.core.ai_errors import http_erro_ia

        raise http_erro_ia(
            exc,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            contexto="executar_tarefa_ia",
        )
    return AiResponse(**resultado)
