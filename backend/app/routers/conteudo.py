"""
conteudo.py — Geração de conteúdo jurídico (#44 FAQ por área · #45 glossário).
Para portal do cliente / equipe. IA via ai_gateway (Groq). FAQ é ancorado no RAG
(usa súmulas/legislação reais como contexto). Conteúdo genérico (sem PII de cliente).
Saída é rascunho — revisão humana antes de publicar.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services import ai_gateway

router = APIRouter(prefix="/conteudo", tags=["Conteúdo Jurídico"])

_AVISO = "Rascunho gerado por IA — revisar antes de publicar (pode conter imprecisões)."

_SYS_FAQ = (
    "Você redige FAQ jurídico para o PORTAL DO CLIENTE de um escritório de advocacia. "
    "Gere perguntas frequentes e respostas em linguagem SIMPLES (cliente leigo), sobre a "
    "área indicada. Use o CONTEXTO (súmulas/legislação) quando útil, mas NÃO invente lei, "
    "súmula ou número; se não tiver certeza, fale de forma geral. NUNCA prometa resultado. "
    "Responda em JSON: {\"faq\":[{\"pergunta\":\"...\",\"resposta\":\"...\"}]}"
)
_SYS_GLOSSARIO = (
    "Você cria um GLOSSÁRIO jurídico para clientes leigos. Para cada termo, dê uma definição "
    "curta e clara em português simples (1-2 frases), sem juridiquês desnecessário. NÃO invente. "
    "Responda em JSON: {\"glossario\":[{\"termo\":\"...\",\"definicao\":\"...\"}]}"
)


class FaqReq(BaseModel):
    area: str = Field(..., min_length=2, max_length=60, description="Área (ex: consumidor, trabalhista)")
    quantidade: int = Field(8, ge=3, le=20)


class GlossarioReq(BaseModel):
    termos: list[str] | None = Field(None, description="Termos específicos (opcional)")
    area: str | None = Field(None, description="Área para extrair termos comuns (opcional)")
    quantidade: int = Field(12, ge=3, le=30)


@router.post("/faq")
async def gerar_faq(req: FaqReq, db: AsyncSession = Depends(get_db),
                    cu: User = Depends(get_current_user)):
    """Gera FAQ por área, ancorado no RAG (súmulas/legislação)."""
    from app.services.ai_service import buscar_contexto_rag
    ctx = await buscar_contexto_rag(db, f"{req.area} direitos prazos dúvidas comuns", limite=5)
    ctx_txt = "\n".join(f"- {(c.get('conteudo') or '')[:300]}" for c in (ctx or []))
    user = (f"Área: {req.area}. Gere {req.quantidade} perguntas e respostas.\n\n"
            f"CONTEXTO (base do escritório):\n{ctx_txt or '(sem contexto específico)'}")
    resp = await ai_gateway.chat(
        messages=[{"role": "system", "content": _SYS_FAQ}, {"role": "user", "content": user}],
        task_type="resumo", temperature=0.3, max_tokens=2000,
    )
    return {"area": req.area, "conteudo": resp.texto,
            "modelo": f"{resp.provedor}/{resp.modelo}", "is_draft": True, "aviso": _AVISO}


@router.post("/glossario")
async def gerar_glossario(req: GlossarioReq, db: AsyncSession = Depends(get_db),
                          cu: User = Depends(get_current_user)):
    """Gera glossário jurídico (termos informados ou comuns de uma área)."""
    if req.termos:
        alvo = "Explique os termos: " + ", ".join(req.termos[:30])
    else:
        alvo = f"Liste e explique os {req.quantidade} termos jurídicos mais comuns" + \
               (f" em {req.area}." if req.area else " que clientes leigos encontram.")
    resp = await ai_gateway.chat(
        messages=[{"role": "system", "content": _SYS_GLOSSARIO}, {"role": "user", "content": alvo}],
        task_type="resumo", temperature=0.3, max_tokens=2000,
    )
    return {"conteudo": resp.texto, "modelo": f"{resp.provedor}/{resp.modelo}",
            "is_draft": True, "aviso": _AVISO}
