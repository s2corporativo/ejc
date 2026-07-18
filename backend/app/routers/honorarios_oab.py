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
from datetime import date
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.audit_log import criar_audit_log
from app.models.redesign import TabelaOABHonorario
from app.models.user import User
from app.services import ai_gateway
from app.services.ai_service import buscar_contexto_rag
from app.core.rate_limit import rate_limit

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


@router.post("/estimar", dependencies=[Depends(rate_limit("honorarios-estimar", 15))])
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


# ── Gestão da tabela estruturada (P0.4) ───────────────────────────────────────
# tabela_oab_honorarios é versionada por vigência (models/redesign.py):
# nova vigência = NOVOS registros (fechar vigencia_fim dos antigos), nunca
# sobrescrever. Entrada manual dos itens que o seed não importou (layout de
# 2 colunas do PDF) — `fonte` OBRIGATÓRIA (nunca inventar valor/vigência).
# Restrito a sócio+, com auditoria.

def _req_socio(cu: User = Depends(get_current_user)) -> User:
    role = cu.role.value if hasattr(cu.role, "value") else str(cu.role)
    if ROLE_LEVEL.get(role, 0) < ROLE_LEVEL["socio"]:
        raise HTTPException(status_code=403, detail="Acesso restrito a sócios/administração")
    return cu


def _item_out(i: TabelaOABHonorario) -> dict:
    return {
        "id": i.id,
        "item_codigo": i.item_codigo,
        "descricao": i.descricao,
        "area_juridica": i.area_juridica,
        "valor_minimo": float(i.valor_minimo) if i.valor_minimo is not None else None,
        "percentual": float(i.percentual) if i.percentual is not None else None,
        "unidade": i.unidade,
        "vigencia_inicio": i.vigencia_inicio.isoformat() if i.vigencia_inicio else None,
        "vigencia_fim": i.vigencia_fim.isoformat() if i.vigencia_fim else None,
        "fonte": i.fonte,
        "observacoes": i.observacoes,
        "ativo": bool(i.ativo),
    }


class ItemOABIn(BaseModel):
    """Entrada manual de item da tabela — valores VERBATIM da fonte oficial."""
    item_codigo: str = Field(min_length=1, max_length=30)
    descricao: str = Field(min_length=3, max_length=300)
    area_juridica: Optional[str] = Field(None, max_length=50)
    valor_minimo: Optional[float] = Field(None, ge=0)
    percentual: Optional[float] = Field(None, ge=0, le=100)
    unidade: Optional[str] = Field(None, max_length=30)
    # Só preenchida quando INFORMADA pelo usuário (edição/vigência conhecida);
    # nunca deduzida pelo sistema.
    vigencia_inicio: Optional[date] = None
    observacoes: Optional[str] = Field(None, max_length=2000)
    fonte: str = Field(min_length=5, max_length=300)  # documento/URL oficial OAB/MG

    @field_validator("fonte")
    @classmethod
    def _fonte_identificavel(cls, v: str) -> str:
        # Barreira mínima contra fonte nominal ("aaaaa"): precisa referenciar a
        # OAB ou ser um endereço/documento identificável (URL).
        v = v.strip()
        if "oab" not in v.lower() and not v.lower().startswith(("http://", "https://")):
            raise ValueError(
                "fonte deve identificar o documento oficial (mencionar OAB ou ser URL)"
            )
        return v


class EncerrarVigenciaIn(BaseModel):
    # Data informada pelo usuário — o sistema não presume o fim da vigência.
    vigencia_fim: date
    motivo: Optional[str] = Field(None, max_length=300)


@router.get("/itens")
async def listar_itens(
    area: str = "",
    incluir_encerrados: bool = False,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Itens estruturados da tabela OAB/MG (transparência/gestão)."""
    q = select(TabelaOABHonorario)
    if not incluir_encerrados:
        q = q.where(TabelaOABHonorario.ativo.is_(True))
    if area:
        q = q.where(TabelaOABHonorario.area_juridica.ilike(f"%{area}%"))
    q = q.order_by(TabelaOABHonorario.item_codigo,
                   TabelaOABHonorario.vigencia_inicio.desc().nullslast()).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return {"total": len(rows), "itens": [_item_out(i) for i in rows]}


@router.post("/itens", status_code=201,
             dependencies=[Depends(rate_limit("oab-itens", 30))])
async def criar_item(
    body: ItemOABIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_socio),
):
    """Cadastra manualmente um item da tabela (fonte obrigatória, auditado).

    Versionamento: se já existe item ATIVO com mesmo código e vigência aberta
    (QUALQUER fonte), é preciso encerrar a vigência anterior antes — nunca
    sobrescrever nem criar item paralelo que "sombreie" o vigente.
    """
    dup = (await db.execute(
        select(TabelaOABHonorario).where(
            TabelaOABHonorario.item_codigo == body.item_codigo,
            TabelaOABHonorario.ativo.is_(True),
            TabelaOABHonorario.vigencia_fim.is_(None),
        ).limit(1)
    )).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(
            status_code=409,
            detail=("Já existe item ativo com este código em vigência aberta "
                    f"(fonte: {dup.fonte}). Encerre a vigência anterior antes de "
                    "registrar a nova (versionamento)."),
        )

    item = TabelaOABHonorario(
        id=str(uuid4()),
        item_codigo=body.item_codigo,
        descricao=body.descricao,
        area_juridica=body.area_juridica,
        valor_minimo=body.valor_minimo,
        percentual=body.percentual,
        # VERBATIM da fonte: sem default — item só-percentual não ganha "R$".
        unidade=body.unidade,
        vigencia_inicio=body.vigencia_inicio,
        vigencia_fim=None,
        fonte=body.fonte,
        observacoes=body.observacoes,
        ativo=True,
    )
    db.add(item)
    await criar_audit_log(
        db, cu.id, cu.role.value if hasattr(cu.role, "value") else str(cu.role),
        "CREATE", "tabela_oab_honorarios", item.id,
        detalhes=f"Entrada manual item {body.item_codigo} (fonte: {body.fonte})",
        dados_depois=_item_out(item),
    )
    await db.commit()
    return _item_out(item)


@router.post("/itens/{item_id}/encerrar-vigencia",
             dependencies=[Depends(rate_limit("oab-itens", 30))])
async def encerrar_vigencia(
    item_id: str,
    body: EncerrarVigenciaIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_socio),
):
    """Encerra a vigência de um item (versionamento): fecha vigencia_fim e
    desativa — os valores históricos NUNCA são alterados/sobrescritos."""
    item = (await db.execute(
        select(TabelaOABHonorario).where(TabelaOABHonorario.id == item_id)
    )).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item da tabela não encontrado")
    if item.vigencia_fim is not None:
        raise HTTPException(status_code=409, detail="Vigência deste item já está encerrada")
    if item.vigencia_inicio and body.vigencia_fim < item.vigencia_inicio:
        raise HTTPException(status_code=422,
                            detail="vigencia_fim anterior à vigencia_inicio do item")

    antes = _item_out(item)
    item.vigencia_fim = body.vigencia_fim
    item.ativo = False
    await criar_audit_log(
        db, cu.id, cu.role.value if hasattr(cu.role, "value") else str(cu.role),
        "UPDATE", "tabela_oab_honorarios", item.id,
        detalhes=("Encerramento de vigência"
                  + (f" — motivo: {body.motivo}" if body.motivo else "")),
        dados_antes=antes, dados_depois=_item_out(item),
    )
    await db.commit()
    return _item_out(item)
