# ── app/routers/gestao_societaria.py ─────────────────────────────────────────
# Gestão Societária — sócios, participação e distribuição de lucros.
# Acesso restrito a sócios e administradores.
from __future__ import annotations
import json
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from datetime import datetime, timezone, date as _date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User
from app.models.socio import Socio, DistribuicaoLucro, RegimeSocio
from app.modules.auditoria.middleware import registrar_acao

router = APIRouter(prefix="/sociedade", tags=["Gestão Societária"])


class SocioIn(BaseModel):
    user_id:                 str
    participacao_percentual: float = Field(gt=0, le=1)   # 0.0001 a 1.0
    regime:                  RegimeSocio = RegimeSocio.misto
    pro_labore:              Optional[float] = None
    oab_numero:              Optional[str]  = None
    oab_uf:                  Optional[str]  = None
    data_entrada:            _date
    observacoes:             Optional[str]  = None


class SocioPatch(BaseModel):
    participacao_percentual: Optional[float] = Field(None, gt=0, le=1)
    regime:                  Optional[RegimeSocio] = None
    pro_labore:              Optional[float] = None
    ativo:                   Optional[bool]  = None
    data_saida:              Optional[_date] = None
    meta_produtividade:      Optional[float] = None # Seção 8.270
    observacoes:             Optional[str]   = None


class DistribuicaoIn(BaseModel):
    mes_referencia: str = Field(pattern=r"^\d{4}-\d{2}$")  # YYYY-MM
    valor_total:    float = Field(gt=0)
    observacoes:    Optional[str] = None


def _is_socio(u: User) -> bool:
    return ROLE_LEVEL.get(u.role.value, 0) >= ROLE_LEVEL["socio"]

def _out_socio(s: Socio) -> dict:
    return {
        "id": s.id, "user_id": s.user_id,
        "participacao_percentual": float(s.participacao_percentual),
        "regime": s.regime.value if hasattr(s.regime, "value") else s.regime,
        "pro_labore": float(s.pro_labore) if s.pro_labore else None,
        "oab_numero": s.oab_numero, "oab_uf": s.oab_uf,
        "data_entrada": s.data_entrada.isoformat() if s.data_entrada else None,
        "data_saida": s.data_saida.isoformat() if s.data_saida else None,
        "meta_produtividade": float(s.meta_produtividade) if hasattr(s, 'meta_produtividade') and s.meta_produtividade else 0.0,
        "ativo": s.ativo, "observacoes": s.observacoes,
    }


# ── Sócios ────────────────────────────────────────────────────────────────────

@router.get("/socios")
async def listar_socios(
    ativo: Optional[bool] = Query(None),
    db:    AsyncSession = Depends(get_db),
    cu:    User = Depends(get_current_user),
):
    if not _is_socio(cu):
        raise HTTPException(403, "Acesso restrito a sócios")
    q = select(Socio)
    if ativo is not None:
        q = q.where(Socio.ativo.is_(ativo))
    socios = (await db.execute(q.order_by(Socio.participacao_percentual.desc()))).scalars().all()
    total_participacao = sum(float(s.participacao_percentual) for s in socios if s.ativo)
    return {
        "total_participacao": round(total_participacao, 4),
        "socios": [_out_socio(s) for s in socios],
    }


@router.post("/socios", status_code=201)
async def cadastrar_socio(
    req: SocioIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["admin"]:
        raise HTTPException(403, "Apenas administradores podem cadastrar sócios")
    existente = (await db.execute(
        select(Socio).where(Socio.user_id == req.user_id)
    )).scalar_one_or_none()
    if existente:
        raise HTTPException(409, "Usuário já é sócio")
    s = Socio(id=str(uuid4()), **req.model_dump())
    db.add(s)
    await db.commit()
    await registrar_acao(db, cu.id, "criar", "socios", s.id, f"Sócio {s.user_id} cadastrado")
    return _out_socio(s)


@router.patch("/socios/{socio_id}")
async def atualizar_socio(
    socio_id: str,
    req: SocioPatch,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_socio(cu):
        raise HTTPException(403)
    s = (await db.execute(select(Socio).where(Socio.id == socio_id))).scalar_one_or_none()
    if not s:
        raise HTTPException(404)
    for campo, valor in req.model_dump(exclude_none=True).items():
        setattr(s, campo, valor)
    s.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _out_socio(s)


# ── Distribuição de Lucros ────────────────────────────────────────────────────

@router.post("/distribuicao", status_code=201)
async def calcular_distribuicao(
    req: DistribuicaoIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Calcula a distribuição de lucros para o mês de referência
    com base nas participações percentuais dos sócios ativos.
    """
    if not _is_socio(cu):
        raise HTTPException(403)

    socios = (await db.execute(
        select(Socio).where(Socio.ativo.is_(True))
    )).scalars().all()
    if not socios:
        raise HTTPException(422, "Nenhum sócio ativo cadastrado")

    total_participacao = sum(float(s.participacao_percentual) for s in socios)
    if round(total_participacao, 4) > 1.0001:
        raise HTTPException(422, f"Participação total {total_participacao * 100:.2f}% excede 100%")
    # Antes, uma soma < 100% distribuía silenciosamente o restante a ninguém
    # (ex.: sócios somando 80% => 20% do lucro não era atribuído). Agora exige
    # que o quadro societário some 100% antes de distribuir.
    if round(total_participacao, 4) < 0.9999:
        raise HTTPException(
            422,
            f"Participação total {total_participacao * 100:.2f}% difere de 100% — "
            f"ajuste o quadro societário antes de distribuir os lucros",
        )

    # Cálculo em Decimal (dinheiro nunca em float) com correção do drift de
    # centavos: a soma das cotas arredondadas fecha exatamente o valor total.
    _CENTAVO = Decimal("0.01")
    valor_total_dec = Decimal(str(req.valor_total)).quantize(_CENTAVO, rounding=ROUND_HALF_UP)
    socios_lista = []
    soma_cotas = Decimal("0")
    for s in socios:
        part = Decimal(str(s.participacao_percentual))
        valor = (valor_total_dec * part).quantize(_CENTAVO, rounding=ROUND_HALF_UP)
        soma_cotas += valor
        socios_lista.append({
            "socio_id": s.id,
            "user_id":  s.user_id,
            "participacao": float(part),
            "valor":    valor,
        })
    drift = valor_total_dec - soma_cotas
    if drift != Decimal("0") and socios_lista:
        maior = max(socios_lista, key=lambda item: item["valor"])
        maior["valor"] = (maior["valor"] + drift).quantize(_CENTAVO, rounding=ROUND_HALF_UP)
    for item in socios_lista:
        item["valor"] = float(item["valor"])

    dist = DistribuicaoLucro(
        id=str(uuid4()),
        mes_referencia=req.mes_referencia,
        valor_total=valor_total_dec,
        socios_json=json.dumps(socios_lista, ensure_ascii=False),
        observacoes=req.observacoes,
        created_by=cu.id,
    )
    db.add(dist)
    await db.commit()

    return {
        "id": dist.id,
        "mes_referencia": dist.mes_referencia,
        "valor_total": req.valor_total,
        "status": "calculado",
        "distribuicao": socios_lista,
    }


@router.get("/distribuicao")
async def listar_distribuicoes(
    page:     int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=60),
    db:       AsyncSession = Depends(get_db),
    cu:       User = Depends(get_current_user),
):
    if not _is_socio(cu):
        raise HTTPException(403)
    q = select(DistribuicaoLucro).order_by(DistribuicaoLucro.mes_referencia.desc())
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    items = (await db.execute(q.offset((page-1)*per_page).limit(per_page))).scalars().all()
    return {
        "total": total, "page": page, "per_page": per_page,
        "items": [
            {
                "id": d.id,
                "mes_referencia": d.mes_referencia,
                "valor_total": float(d.valor_total),
                "status": d.status,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "distribuicao": json.loads(d.socios_json) if d.socios_json else [],
            }
            for d in items
        ],
    }


@router.post("/distribuicao/{dist_id}/aprovar")
async def aprovar_distribuicao(
    dist_id: str,
    db:  AsyncSession = Depends(get_db),
    cu:  User = Depends(get_current_user),
):
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["admin"]:
        raise HTTPException(403)
    d = (await db.execute(select(DistribuicaoLucro).where(DistribuicaoLucro.id == dist_id))).scalar_one_or_none()
    if not d:
        raise HTTPException(404)
    if d.status != "calculado":
        raise HTTPException(422, f"Distribuição já está '{d.status}'")
    d.status = "aprovado"
    d.aprovado_por = cu.id
    d.aprovado_em  = datetime.now(timezone.utc)
    await db.commit()
    await registrar_acao(db, cu.id, "aprovar", "distribuicao_lucro", dist_id,
                         f"Distribuição {d.mes_referencia} aprovada")
    return {"id": dist_id, "status": "aprovado"}
