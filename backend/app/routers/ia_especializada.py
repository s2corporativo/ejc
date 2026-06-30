"""IAs especializadas — 5 perfis sobre a MESMA base (gateway + RAG).
   Comercial · Atendimento · Jurídica · Financeira · Societária.
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services import ai_gateway

router = APIRouter(prefix="/ia-especializada", tags=["IAs Especializadas"])

PERFIS = {
    "comercial": {
        "label": "IA Comercial",
        "sys": ("Você é a IA Comercial de um escritório de advocacia. Foco: captação de clientes, "
                "elaboração de propostas, argumentos de valor e conversão de leads. Linguagem persuasiva, "
                "ética e sem prometer resultado jurídico. Nunca invente dados."),
        "task": "analise_juridica",
    },
    "atendimento": {
        "label": "IA Atendimento",
        "sys": ("Você é a IA de Atendimento/Triagem. Foco: entender a demanda do cliente, classificar a área "
                "jurídica, listar documentos necessários e próximos passos. Linguagem clara e acolhedora para leigos."),
        "task": "analise_juridica",
    },
    "juridica": {
        "label": "IA Jurídica",
        "sys": ("Você é a IA Jurídica. Foco: análise técnica, teses, fundamentação legal e estratégia processual. "
                "Sempre cite base normativa (artigo + lei). Nunca invente jurisprudência. Respostas analíticas, "
                "nunca promessa de resultado."),
        "task": "redacao_peca",
    },
    "financeira": {
        "label": "IA Financeira",
        "sys": ("Você é a IA Financeira do escritório. Foco: honorários, fluxo de caixa, cobrança, indicadores "
                "(margem, inadimplência, ticket médio) e organização de receitas/despesas. Apresente memória de cálculo."),
        "task": "analise_juridica",
    },
    "societaria": {
        "label": "IA Societária",
        "sys": ("Você é a IA Societária. Foco: distribuição de lucros, participação de sócios, pró-labore, "
                "rateio de êxito (50% titular / 50% escritório após despesas) e desempenho. Seja preciso com percentuais."),
        "task": "analise_juridica",
    },
}


@router.get("/perfis")
async def listar_perfis(cu: User = Depends(get_current_user)):
    return {"perfis": [{"id": k, "label": v["label"]} for k, v in PERFIS.items()]}


@router.post("/{perfil}")
async def consultar(
    perfil: str,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    cfg = PERFIS.get(perfil)
    if not cfg:
        raise HTTPException(404, f"Perfil inválido. Use: {', '.join(PERFIS)}")
    pergunta = (body.get("pergunta") or "").strip()
    if len(pergunta) < 3:
        raise HTTPException(422, "Pergunta muito curta")

    # LGPD (laudo IA-02): sanitiza a pergunta ANTES do RAG e do LLM, com 2ª barreira.
    from app.services.sanitizer import sanitizar_pii, validar_sem_pii
    pergunta_limpa, _ = sanitizar_pii(pergunta)
    residual = validar_sem_pii(pergunta_limpa)
    if residual:
        raise HTTPException(
            422, f"Dados pessoais detectados ({', '.join(residual)}). "
                 "Remova CPF/CNPJ/nº de processo da pergunta.")

    # contexto RAG (mesma base de conhecimento)
    contexto = ""
    try:
        from app.services.ai_service import buscar_contexto_rag
        contexto = await buscar_contexto_rag(db, pergunta_limpa) or ""
    except Exception:
        contexto = ""

    sys = cfg["sys"]
    if contexto:
        sys += "\n\nContexto da base de conhecimento do escritório:\n" + contexto[:4000]

    resp = await ai_gateway.chat(
        messages=[{"role": "system", "content": sys},
                  {"role": "user", "content": pergunta_limpa}],
        task_type=cfg["task"], temperature=0.3, max_tokens=1500,
    )

    # Rastreabilidade (laudo IA-02): registra o uso de IA (auditoria LGPD / HITL).
    try:
        from uuid import uuid4
        from app.models.ai_log import AILog, AITipoUso, AIStatusHITL
        db.add(AILog(
            id=str(uuid4()), user_id=cu.id, tipo_uso=AITipoUso.consulta_rag,
            modelo=f"{resp.provedor}/{resp.modelo}"[:50],
            prompt_sanitizado=f"[ia-especializada:{perfil}] {pergunta_limpa[:500]}",
            resposta=(resp.texto or "")[:8000],
            status_hitl=AIStatusHITL.gerado, pii_removida=True,
        ))
        await db.commit()
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning("AILog (ia-especializada) nao salvo: %s", _e)

    return {"perfil": perfil, "label": cfg["label"], "resposta": resp.texto,
            "modelo": resp.modelo, "provedor": resp.provedor}
