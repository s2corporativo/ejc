# ── app/routers/ia_extra.py ───────────────────────────────────────────────────
# Onda 2 — IA jurídica: tradução de andamento p/ cliente, geração de minuta com
# RAG e pesquisa jurídica. Mesma pipeline segura do ai_service: sanitiza PII
# (LGPD) → Groq → registra AILog → devolve como RASCUNHO (revisão OAB).
from __future__ import annotations
import json
from uuid import uuid4
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import get_settings
from app.core.security import get_current_user
from app.models.user import User
from app.models.ai_log import AILog, AITipoUso, AIStatusHITL
from app.services.ai_service import get_groq, buscar_contexto_rag
from app.services.sanitizer import sanitizar_pii

settings = get_settings()
router = APIRouter(prefix="/ai", tags=["IA — Assistente"])


async def _groq(system: str, user: str, temperature: float = 0.2, max_tokens: int = 1200) -> str:
    client = get_groq()
    resp = await client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=temperature, max_tokens=max_tokens, timeout=settings.GROQ_TIMEOUT,
    )
    return resp.choices[0].message.content


async def _log(db, user_id, tipo, case_id, prompt, pii, resposta):
    log = AILog(
        id=str(uuid4()), user_id=user_id, case_id=case_id, tipo_uso=tipo,
        modelo=settings.GROQ_MODEL, prompt_sanitizado=prompt[:8000],
        pii_removida=pii, resposta=resposta, status_hitl=AIStatusHITL.gerado,
    )
    db.add(log); await db.commit()
    return log.id


# ── Traduzir andamento para linguagem do cliente ──────────────────────────────
class TraduzirIn(BaseModel):
    texto: str = Field(min_length=5, max_length=8000)
    case_id: Optional[str] = None

SYS_TRADUZIR = (
    "Você é um advogado que explica o processo ao CLIENTE leigo. Reescreva o "
    "andamento processual abaixo em português claro e acolhedor, SEM jargão "
    "jurídico, em até 2 parágrafos curtos. Explique o que aconteceu e o que o "
    "cliente deve esperar. Não invente fatos nem dê garantias de resultado."
)

@router.post("/traduzir-andamento")
async def traduzir_andamento(body: TraduzirIn, db: AsyncSession = Depends(get_db),
                             cu: User = Depends(get_current_user)):
    if not settings.AI_ENABLED:
        raise HTTPException(503, "IA desabilitada")
    limpo, pii = sanitizar_pii(body.texto)
    try:
        resposta = await _groq(SYS_TRADUZIR, limpo, temperature=0.3, max_tokens=700)
    except Exception as e:
        raise HTTPException(502, f"Falha na IA: {str(e)[:160]}")
    log_id = await _log(db, cu.id, AITipoUso.outro, body.case_id, limpo, pii, resposta)
    return {"ai_log_id": log_id, "resposta": resposta,
            "aviso": "⚠️ Texto gerado por IA — revise antes de enviar ao cliente."}


# ── Resumir texto (peça/decisão/processo longo) ───────────────────────────────
class ResumirIn(BaseModel):
    texto: str = Field(min_length=20, max_length=12000)
    case_id: Optional[str] = None

SYS_RESUMIR = (
    "Você é assistente jurídico. Resuma o texto abaixo em tópicos objetivos "
    "(pontos-chave, decisão/pedido, prazos e próximos passos, se houver). "
    "Não invente nada que não esteja no texto."
)

@router.post("/resumir-texto")
async def resumir_texto(body: ResumirIn, db: AsyncSession = Depends(get_db),
                        cu: User = Depends(get_current_user)):
    if not settings.AI_ENABLED:
        raise HTTPException(503, "IA desabilitada")
    limpo, pii = sanitizar_pii(body.texto)
    try:
        resposta = await _groq(SYS_RESUMIR, limpo, temperature=0.1, max_tokens=1200)
    except Exception as e:
        raise HTTPException(502, f"Falha na IA: {str(e)[:160]}")
    log_id = await _log(db, cu.id, AITipoUso.resumo_documento, body.case_id, limpo, pii, resposta)
    return {"ai_log_id": log_id, "resposta": resposta,
            "aviso": "⚠️ Resumo gerado por IA — confira com o original."}


# ── Gerar minuta de peça com apoio do RAG ─────────────────────────────────────
class MinutaIn(BaseModel):
    tema: str = Field(min_length=5, max_length=2000)
    tipo_peca: str = "petição inicial"
    area: Optional[str] = None
    fatos: Optional[str] = None
    case_id: Optional[str] = None

SYS_MINUTA = (
    "Você é advogado redator. Produza um RASCUNHO de {tipo} na área de {area}, "
    "estruturado (endereçamento, qualificação [deixe placeholders], dos fatos, "
    "do direito, dos pedidos). Use a base de jurisprudência/teses fornecida como "
    "CONTEXTO quando pertinente, citando-a. NÃO invente jurisprudência nem números "
    "de processo. Deixe claro onde faltam dados com [COLCHETES]."
)

@router.post("/gerar-minuta")
async def gerar_minuta(body: MinutaIn, db: AsyncSession = Depends(get_db),
                       cu: User = Depends(get_current_user)):
    if not settings.AI_ENABLED:
        raise HTTPException(503, "IA desabilitada")
    contexto = await buscar_contexto_rag(db, body.tema, limite=5)
    ctx_txt = "\n\n".join(f"- {c.get('titulo','')}: {(c.get('conteudo') or '')[:500]}"
                          for c in contexto) or "(sem contexto relevante)"
    fatos_limpo, pii = sanitizar_pii(body.fatos or body.tema)
    system = SYS_MINUTA.format(tipo=body.tipo_peca, area=body.area or "geral")
    user = f"TEMA: {body.tema}\n\nFATOS: {fatos_limpo}\n\nCONTEXTO (base do escritório):\n{ctx_txt}"
    try:
        resposta = await _groq(system, user, temperature=0.3, max_tokens=2200)
    except Exception as e:
        raise HTTPException(502, f"Falha na IA: {str(e)[:160]}")
    log_id = await _log(db, cu.id, AITipoUso.redacao_peca, body.case_id, user, pii, resposta)
    return {"ai_log_id": log_id, "resposta": resposta,
            "fontes": [{"titulo": c.get("titulo"), "categoria": c.get("categoria")} for c in contexto],
            "aviso": "⚠️ RASCUNHO gerado por IA — revisão humana obrigatória (OAB)."}


# ── Pesquisa jurídica (RAG + IA) ──────────────────────────────────────────────
class PesquisaIn(BaseModel):
    pergunta: str = Field(min_length=5, max_length=2000)

SYS_PESQUISA = (
    "Você é assistente de pesquisa jurídica do escritório. Responda à pergunta "
    "usando PRINCIPALMENTE o contexto fornecido (base interna). Seja objetivo, cite "
    "as fontes do contexto e, se a base não cobrir, diga isso explicitamente em vez "
    "de inventar. Não dê garantias de resultado."
)

@router.post("/pesquisar")
async def pesquisar(body: PesquisaIn, db: AsyncSession = Depends(get_db),
                    cu: User = Depends(get_current_user)):
    if not settings.AI_ENABLED:
        raise HTTPException(503, "IA desabilitada")
    contexto = await buscar_contexto_rag(db, body.pergunta, limite=6)
    ctx_txt = "\n\n".join(f"- {c.get('titulo','')}: {(c.get('conteudo') or '')[:600]}"
                          for c in contexto) or "(base sem resultados relevantes)"
    user = f"PERGUNTA: {body.pergunta}\n\nCONTEXTO:\n{ctx_txt}"
    try:
        resposta = await _groq(SYS_PESQUISA, user, temperature=0.2, max_tokens=1400)
    except Exception as e:
        raise HTTPException(502, f"Falha na IA: {str(e)[:160]}")
    log_id = await _log(db, cu.id, AITipoUso.consulta_rag, None, body.pergunta, False, resposta)
    return {"ai_log_id": log_id, "resposta": resposta,
            "fontes": [{"titulo": c.get("titulo"), "categoria": c.get("categoria")} for c in contexto]}


# ── ETAPA 4 — Motor de honorários (tabela OAB/MG via RAG) ─────────────────────
def _pj(txt: str) -> Optional[dict]:
    if not txt:
        return None
    i, j = txt.find("{"), txt.rfind("}")
    try:
        return json.loads(txt[i:j + 1]) if i != -1 and j != -1 else None
    except Exception:
        return None


class HonorariosIn(BaseModel):
    area: str = Field(min_length=2, max_length=60)
    descricao: str = Field(min_length=3, max_length=600)   # o serviço/ato
    valor_causa: Optional[float] = None


SYS_HONORARIOS = (
    "Você é especialista em honorários advocatícios. Com base APENAS nos TRECHOS da "
    "Tabela de Honorários da OAB/MG fornecidos, sugira honorários para o serviço descrito. "
    "Responda APENAS JSON válido: "
    '{"honorario_minimo_oab": "<valor/regra da tabela, ex: R$ X ou 10% do valor da causa>",'
    ' "honorario_recomendado": "<sugestão prática, pode ser faixa>",'
    ' "percentual_exito": "<faixa, ex: 20-30%>",'
    ' "fundamento": "<qual item da tabela OAB embasa>",'
    ' "observacao": "<nota relevante>"}\n'
    "Use SOMENTE valores presentes nos trechos. Se não houver o item exato, use o mais "
    "próximo e diga isso no fundamento. NUNCA invente valores."
)


@router.post("/sugestao-honorarios")
async def sugestao_honorarios(body: HonorariosIn, db: AsyncSession = Depends(get_db),
                              cu: User = Depends(get_current_user)):
    if not settings.AI_ENABLED:
        raise HTTPException(503, "IA desabilitada")
    consulta = f"honorários {body.area} {body.descricao}"
    ctx = await buscar_contexto_rag(db, consulta, limite=6, categorias=["tabela_honorarios_oab"])
    ctx_txt = "\n\n".join(f"- {(c.get('conteudo') or '')[:600]}" for c in ctx) or "(tabela OAB não localizada na base)"
    vc = f"\nValor da causa: R$ {body.valor_causa:.2f}" if body.valor_causa else ""
    user = (f"ÁREA: {body.area}\nSERVIÇO/ATO: {body.descricao}{vc}\n\n"
            f"TRECHOS DA TABELA DE HONORÁRIOS OAB/MG:\n{ctx_txt}")
    try:
        bruto = await _groq(SYS_HONORARIOS, user, temperature=0.1, max_tokens=700)
    except Exception as e:
        raise HTTPException(502, f"Falha na IA: {str(e)[:160]}")
    log_id = await _log(db, cu.id, AITipoUso.outro, None, user, False, bruto)
    return {
        "ai_log_id": log_id,
        "sugestao": _pj(bruto) or {"texto": bruto},
        "fonte": "Tabela de Honorários OAB/MG (referencial)",
        "trechos_consultados": len(ctx),
        "aviso": "⚠️ Valores REFERENCIAIS da OAB/MG. Honorário é livremente pactuado — "
                 "o advogado define o valor final. Confira na tabela oficial.",
    }
