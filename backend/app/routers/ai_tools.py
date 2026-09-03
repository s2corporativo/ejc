"""
Endpoints do MÓDULO IA PROFISSIONAL do EJC (agente por tarefa).
Tudo passa pelo ai_gateway; resultado sempre RASCUNHO (HITL/OAB). JWT obrigatório.
Rota: /api/ai/executar e /api/ai/status.
"""
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.system_prompts import TarefaIA
from app.services.ai.provider_registry import (
    PROVIDERS_SUPORTADOS, motivo_inelegivel, provider_elegivel,
)
from app.services.ai_gateway import executar_tarefa_ia
from app.services.ai_guard import sanitizar_ou_abortar
from app.core.rate_limit import rate_limit

router = APIRouter(prefix="/ai", tags=["IA Jurídica Pro"])


class AiRequest(BaseModel):
    tarefa: TarefaIA = Field(..., description="Tipo de tarefa de IA")
    mensagem: str = Field(..., min_length=5, max_length=12000)
    case_id: Optional[str] = Field(None, description="Caso para contexto")
    usar_rag: bool = Field(False, description="Buscar na base de conhecimento (RAG)")
    # I2: vazio = o PISO por tarefa decide (AI_NIVEL_INTELIGENCIA_MERITO nas
    # tarefas de mérito, econômico nas demais). O default fixo "alto" fazia esta
    # porta ignorar o piso — mesmo defeito já corrigido em /ai/core/*.
    nivel_inteligencia: Optional[str] = Field(
        None, description="padrao, alto, maximo ou executivo (vazio = piso por tarefa)"
    )


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
    # ── Chaves canônicas (I1, 03/09/2026) ────────────────────────────────────
    # A porta canônica é `/ia/{capacidade}` (routers/ia_capacidades.py). Esta
    # rota continua atendendo pelo contrato antigo e passa a devolver TAMBÉM o
    # envelope único das cinco capacidades — `capacidade` diz em qual porta
    # aquela TarefaIA cai (`capacidades.capacidade_da_tarefa`).
    capacidade: str = ""
    log_id: Optional[str] = None
    status_hitl: str = "gerado"
    aviso_hitl: str = ""
    fontes_rag: list[dict] = []
    citacoes: list[dict] = []
    alertas: list[str] = []
    tokens: dict = {}


def _ai_enabled() -> bool:
    # Kill-switch global lido de Settings — a MESMA fonte do gateway e do
    # provider_registry. Antes lia os.getenv("AI_ENABLED") e ignorava Settings.
    return bool(get_settings().AI_ENABLED)


def _bloquear_cliente_externo(cu: User) -> None:
    """IA interna não é exposta ao portal do cliente (mesma regra do núcleo)."""
    # `UserRole` é `(str, Enum)` sem `__str__`: em Python 3.11 `str(role)` vira
    # "UserRole.cliente_externo" e o gate nunca disparava (só o middleware
    # segurava). Compara pelo valor — funciona para enum e para string.
    role = getattr(cu, "role", "")
    if getattr(role, "value", role) == "cliente_externo":
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Funções de IA internas não estão disponíveis no portal do cliente.")


@router.get("/status")
async def status_ia(cu: User = Depends(get_current_user)):
    _bloquear_cliente_externo(cu)
    # Elegibilidade pela fonte única (provider_registry: AI_ENABLED, *_ENABLED,
    # chave via Settings/Cofre, AI_EXTERNAL_PROVIDERS_ALLOWED). O painel lia
    # os.getenv: ignorava o Cofre e os kill-switches por provedor e afirmava
    # modelo_complexo="(=rapido)" fora do container (o default real é Opus).
    s = get_settings()
    return {
        "ai_enabled": _ai_enabled(),
        "anthropic_configurado": provider_elegivel("anthropic"),
        "groq_configurado": provider_elegivel("groq"),
        "maritaca_configurado": provider_elegivel("maritaca"),
        "ollama_configurado": provider_elegivel("ollama"),
        "motivos_inelegiveis": {
            p: motivo_inelegivel(p) for p in PROVIDERS_SUPORTADOS if not provider_elegivel(p)
        },
        "modelo_rapido": s.ANTHROPIC_MODEL_RAPIDO,
        "modelo_complexo": s.ANTHROPIC_MODEL_COMPLEXO,
        "tarefas": [t.value for t in TarefaIA],
        "niveis_inteligencia": ["padrao", "alto", "maximo", "executivo"],
        "aviso": "Todos os resultados são rascunhos. Revisão humana obrigatória.",
    }


@router.post("/executar", response_model=AiResponse, dependencies=[Depends(rate_limit("ai-executar", 15))])
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
    entidades = None
    modo_sigilo = None
    if req.case_id:
        from app.core.ownership import verificar_acesso_caso
        from app.services.ai_service import _escopo_cliente_do_caso
        from app.services.ai.entidades_caso import entidades_do_caso
        from app.services.ai.sanitization_policy import modo_sigilo_do_caso
        caso = await verificar_acesso_caso(db, cu, req.case_id)
        escopo_cli = await _escopo_cliente_do_caso(db, req.case_id)
        # Nomes do caso → marcadores reversíveis quando a tarefa vai a provider
        # externo em modo pseudonimizado (executar_tarefa_ia decide o modo pelo
        # `tarefa`); em MASCARAMENTO o gateway ignora `entidades` (sem efeito).
        entidades = await entidades_do_caso(db, req.case_id)
        # Achado do security-auditor (Issue #1194): esta rota chamava
        # executar_tarefa_ia sem `modo_sanitizacao` — mesma classe de bug que a
        # migration 146 fechou em orchestrator.py/agent/loop.py, reproduzida
        # aqui porque `verificar_acesso_caso` já busca o Case e o retorno era
        # descartado.
        modo_sigilo = modo_sigilo_do_caso(caso)

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
            entidades=entidades or None,
            modo_sanitizacao=modo_sigilo,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except RuntimeError as e:
        # Camada de borda (P0 §3.2): detalhe técnico → log; usuário → leigo.
        from app.core.ai_errors import http_erro_ia
        raise http_erro_ia(e, status.HTTP_503_SERVICE_UNAVAILABLE,
                           contexto="executar_tarefa_ia")
    # Envelope canônico por cima do contrato antigo: `TarefaIA` → capacidade
    # (/ia/analisar, /ia/redigir, /ia/resumir, /ia/conversar, /ia/extrair).
    from app.services.ai.core import capacidades
    capacidade = capacidades.capacidade_da_tarefa(req.tarefa)
    canonico = capacidades.canonizar(capacidade, resultado)
    return AiResponse(**{**resultado, **canonico})
