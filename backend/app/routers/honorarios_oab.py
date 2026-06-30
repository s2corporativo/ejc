"""
honorarios_oab.py — Estimador de honorários ESTRUTURADO (P2.1).
POST /api/honorarios-oab/estimar  → mínimo / recomendado / estratégico + contrato
sugerido + memória de cálculo, ANCORADO na tabela OAB/MG (RAG, filtrada contra
placeholder). GET /api/honorarios-oab/tabela → itens relevantes (transparência).

REGRAS (CLAUDE.md): nunca inventa item da tabela; nunca promete resultado; tudo
é referência — o advogado define o valor final.
"""
import json
import re
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services import ai_gateway
from app.services.ai_service import buscar_contexto_rag

router = APIRouter(prefix="/honorarios-oab", tags=["Honorários OAB"])

REGRAS = (
    "REGRAS: (1) Cite SOMENTE itens que aparecem textualmente no contexto da tabela; "
    "se não houver item específico, diga 'critério usual' — NUNCA invente número de item. "
    "(2) NUNCA prometa resultado. (3) Tudo é referência; o advogado define o valor final."
)


class EstimativaIn(BaseModel):
    area: str
    tipo_acao: str = Field(min_length=2, max_length=200)
    valor_causa: Optional[float] = None
    complexidade: str = "media"           # baixa | media | alta
    tempo_meses: Optional[int] = None
    num_atos: Optional[int] = None
    instancia: Optional[str] = None        # 1grau | 2grau | superior
    observacoes: Optional[str] = None


def _parse_json(txt: str) -> Optional[dict]:
    if not txt:
        return None
    try:
        return json.loads(txt)
    except Exception:
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


async def _contexto_oab(db, area: str, tipo_acao: str) -> tuple[str, bool]:
    """Busca itens da tabela OAB no RAG, descartando placeholders (lorem ipsum)."""
    consulta = f"honorários {area} {tipo_acao} tabela OAB Minas Gerais"
    ctx = await buscar_contexto_rag(db, consulta, limite=8, categorias=["tabela_honorarios_oab"])
    reais = [c for c in ctx
             if len((c.get("conteudo") or "").strip()) > 40
             and "lorem ipsum" not in (c.get("conteudo") or "").lower()]
    txt = "\n".join(f"- {(c.get('conteudo') or '')[:400]}" for c in reais[:6])
    return txt, len(reais) > 0


@router.get("/tabela")
async def itens_tabela(area: str = "", tipo: str = "",
                       db: AsyncSession = Depends(get_db),
                       cu: User = Depends(get_current_user)):
    """Itens relevantes da tabela OAB/MG (transparência da fonte)."""
    txt, ok = await _contexto_oab(db, area, tipo)
    return {"disponivel": ok, "itens": txt or "Tabela oficial OAB/MG não disponível na base."}


@router.post("/estimar")
async def estimar(body: EstimativaIn,
                  db: AsyncSession = Depends(get_db),
                  cu: User = Depends(get_current_user)):
    ctx_txt, tabela_ok = await _contexto_oab(db, body.area, body.tipo_acao)

    if tabela_ok:
        sys = "Você estima honorários ancorado na TABELA OAB/MG do contexto. " + REGRAS
        ctx_bloco = f"TABELA OAB/MG (itens reais):\n{ctx_txt}"
        fund = '"fundamento": "<item EXATO do contexto que embasa, ou \'critério usual\' se não houver>"'
    else:
        sys = ("A tabela oficial OAB/MG NÃO está na base. Dê referência genérica por percentuais "
               "usuais de mercado. PROIBIDO citar número de item da tabela. " + REGRAS)
        ctx_bloco = "TABELA OAB/MG: indisponível — não invente itens."
        fund = '"fundamento": "Referência de mercado — consultar tabela oficial OAB/MG (indisponível na base)"'

    fatores = (
        f"Área: {body.area} | Tipo de ação: {body.tipo_acao} | "
        f"Valor da causa: {body.valor_causa} | Complexidade: {body.complexidade} | "
        f"Tempo estimado: {body.tempo_meses} meses | Nº de atos: {body.num_atos} | "
        f"Instância: {body.instancia or 'não informada'}"
        + (f" | Obs: {body.observacoes}" if body.observacoes else "")
    )
    user = (
        f"{ctx_bloco}\n\nFATORES DO CASO:\n{fatores}\n\n"
        "Calcule três cenários considerando complexidade, tempo e nº de atos. "
        "Responda APENAS JSON: {"
        '"minimo": "<valor ou regra>", '
        '"recomendado": "<valor ou faixa>", '
        '"estrategico": "<valor ou faixa>", '
        + fund + ", "
        '"memoria_calculo": "<como chegou aos valores, em 1-2 frases>", '
        '"contrato_sugerido": "<ex: 30% de êxito + R$ X de entrada parcelado>", '
        f'"tabela_oficial_disponivel": {str(tabela_ok).lower()}}}'
    )

    resp = await ai_gateway.chat(
        messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
        task_type="analise_juridica", temperature=0.2, max_tokens=800,
    )
    data = _parse_json(resp.texto) or {"_bruto": resp.texto[:800], "tabela_oficial_disponivel": tabela_ok}
    data["_aviso"] = ("Estimativa de referência (IA) — não vincula. Confira a tabela oficial OAB/MG "
                      "e ajuste conforme o caso. O advogado define o valor final.")
    return data
