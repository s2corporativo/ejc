"""
Cérebro do EJC — Módulo Único de Inteligência Jurídica Estratégica.
Centraliza IA, Banco de Teses, Jurisprudência, Legislação e Conhecimento Interno.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.ai_errors import http_erro_ia
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.user import User
from app.services.ai.skill_router import skill_router

router = APIRouter(prefix="/cerebro", tags=["Cérebro"])

@router.get("/status")
async def status_cerebro(cu: User = Depends(get_current_user)):
    return {"status": "online", "version": "3.0", "mode": "soberania_tecnologica"}

@router.post("/analise-estrategica", dependencies=[Depends(rate_limit("cerebro-analise-estrategica", 10))])
async def analise_estrategica(payload: dict, db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    """
    Executa análise estratégica unificada com roteamento automático de Skills.
    Consolidado no NÚCLEO ÚNICO de IA (orchestrator): permissões, sanitização
    LGPD, policy de provider, validação de citações, HITL e AILog.
    """
    from app.services.ai.core.orchestrator import orchestrator

    texto_caso = payload.get("texto", "")
    if not (texto_caso or "").strip():
        raise HTTPException(422, "Envie o campo 'texto' com o contexto do caso.")
    ramo = skill_router.identificar_ramo(texto_caso)
    instrucao_skill = skill_router.get_skill_instruction(ramo)

    contexto_completo = f"{instrucao_skill}\n\nContexto do Caso: {texto_caso}"
    try:
        res = await orchestrator.run(
            db=db,
            user=cu,
            task_type="case_analysis",
            domain="estrategia",
            mensagem=contexto_completo,
            case_id=payload.get("case_id"),
        )
    except RuntimeError as e:  # cadeia de provedores esgotada → degradação graciosa
        raise http_erro_ia(f"Serviço de IA indisponível: {str(e)[:180]}", 503)
    except HTTPException:
        raise

    # Shape legado preservado (analise.{analise_principal,analise_critica,...});
    # campos do núcleo ACRESCENTADOS (log_id, aviso_hitl, is_rascunho, modelo).
    alertas = res.get("alertas") or []
    return {
        "ramo_identificado": ramo,
        "skill_acionada": instrucao_skill,
        "analise": {
            "analise_principal": res.get("conteudo"),
            "analise_critica": "\n".join(alertas) if alertas
                               else "Validação automática do núcleo (citações/promessas) aplicada.",
            "convergencias": "Análise consolidada pelo núcleo único de IA.",
            "riscos_identificados": "Ver alertas e revisão HITL obrigatória.",
        },
        "modelo": res.get("modelo"),
        "provider": res.get("provider"),
        "fontes": res.get("fontes", []),
        "log_id": res.get("log_id"),
        "is_rascunho": res.get("is_rascunho", True),
        "aviso_hitl": res.get("aviso_hitl"),
    }

@router.get("/teses")
async def listar_teses(db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    result = await db.execute(text("SELECT * FROM teses WHERE deleted_at IS NULL ORDER BY taxa_sucesso DESC"))
    return result.mappings().all()

@router.post("/jurisprudencia/pesquisa", dependencies=[Depends(rate_limit("cerebro-juris-pesquisa", 15))])
async def pesquisar_jurisprudencia(query: str, db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    # INDISPONIBILIDADE EXPLÍCITA (auditoria 2026-07-19): este endpoint ANTES
    # devolvia sempre `resultados: []` com o comentário "Simulação de busca
    # semântica integrada" — mock enganoso que fingia base sem resultados. A
    # busca semântica real vive no RAG híbrido; enquanto este atalho não é ligado
    # ao núcleo, responde 503 honesto em vez de simular vazio.
    raise HTTPException(
        status_code=503,
        detail=(
            "Busca de jurisprudência do Cérebro não está ligada ao núcleo de busca. "
            "Use /api/search ou /api/rag (Conhecimento Jurídico) para busca semântica real."
        ),
    )
