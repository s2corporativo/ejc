"""IAs especializadas — 5 perfis sobre a MESMA base (gateway + RAG).
   Comercial · Atendimento · Jurídica · Financeira · Societária.
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services import ai_gateway
from app.core.rate_limit import rate_limit

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
        "task": "elaboracao_peca",
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


@router.post("/{perfil}", dependencies=[Depends(rate_limit("ia-especializada", 15))])
async def consultar(
    perfil: str,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    from app.services.ai_guard import sanitizar_ou_abortar, registrar_ai_log
    from app.models.ai_log import AITipoUso

    cfg = PERFIS.get(perfil)
    if not cfg:
        raise HTTPException(404, f"Perfil inválido. Use: {', '.join(PERFIS)}")
    pergunta = (body.get("pergunta") or "").strip()
    nivel = (body.get("nivel_inteligencia") or "alto").strip()
    if len(pergunta) < 3:
        raise HTTPException(422, "Pergunta muito curta")

    # Sanitização LGPD com abort real em PII residual (segunda barreira).
    pergunta_limpa, pii = sanitizar_ou_abortar(pergunta)

    # contexto RAG (mesma base de conhecimento) — fontes estruturadas
    fontes: list[dict] = []
    try:
        from app.services.ai_service import buscar_contexto_rag
        fontes = await buscar_contexto_rag(db, pergunta_limpa) or []
    except Exception:
        fontes = []

    sys = cfg["sys"]
    if fontes:
        ctx_txt = "\n".join(
            f"- {f.get('titulo') or ''}: {(f.get('conteudo') or '')[:300]}" for f in fontes
        )
        sys += "\n\nContexto da base de conhecimento do escritório:\n" + ctx_txt[:4000]

    resp = await ai_gateway.chat(
        messages=[{"role": "system", "content": sys},
                  {"role": "user", "content": pergunta_limpa}],
        task_type=cfg["task"], temperature=0.18 if nivel in ("alto", "maximo") else 0.3, max_tokens=2600 if nivel == "maximo" else 1900,
        nivel_inteligencia=nivel,
    )

    # Auditoria: rastro obrigatório em ai_logs (HITL/LGPD).
    log_id = await registrar_ai_log(
        db, user_id=cu.id, tipo_uso=AITipoUso.consulta_rag, case_id=None,
        prompt_sanitizado=pergunta_limpa, pii_removida=pii,
        resposta=resp.texto, modelo=f"{resp.provedor}/{resp.modelo}",
        fontes_rag="; ".join(f.get("titulo") or "" for f in fontes) or None,
        tokens_input=resp.input_tokens, tokens_output=resp.output_tokens,
    )
    return {"perfil": perfil, "label": cfg["label"], "resposta": resp.texto,
            "modelo": resp.modelo, "provedor": resp.provedor, "nivel_inteligencia": nivel,
            "fontes": [{"titulo": f.get("titulo"), "categoria": f.get("categoria"),
                        "fonte": f.get("fonte")} for f in fontes],
            "log_id": log_id, "is_rascunho": False,
            "padrao_saida": "juridico_profissional",
            "requer_conferencia": True,
            "aviso_hitl": "Resposta gerada em padrão jurídico-profissional. Conferir fatos, fontes, documentos, valores e estratégia antes do uso externo."}
