# ── app/routers/gestao_societaria.py ─────────────────────────────────────────
# Gestão Societária — sócios, participação e distribuição de lucros.
# Acesso restrito a sócios e administradores.
from __future__ import annotations

import json
from datetime import date as _date
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.audit_log import criar_audit_log
from app.models.socio import DistribuicaoLucro, RegimeSocio, Socio
from app.models.user import User

router = APIRouter(prefix="/sociedade", tags=["Gestão Societária"])


class SocioIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    participacao_percentual: float = Field(gt=0, le=1)
    regime: RegimeSocio = RegimeSocio.misto
    pro_labore: Optional[float] = Field(None, ge=0)
    oab_numero: Optional[str] = Field(None, max_length=20)
    oab_uf: Optional[str] = Field(None, min_length=2, max_length=2)
    data_entrada: _date
    observacoes: Optional[str] = None


class SocioPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participacao_percentual: Optional[float] = Field(None, gt=0, le=1)
    regime: Optional[RegimeSocio] = None
    pro_labore: Optional[float] = Field(None, ge=0)
    ativo: Optional[bool] = None
    data_saida: Optional[_date] = None
    observacoes: Optional[str] = None


_SOCIO_PATCH_CAMPOS = {
    "participacao_percentual",
    "regime",
    "pro_labore",
    "ativo",
    "data_saida",
    "observacoes",
}


class DistribuicaoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mes_referencia: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    valor_total: Decimal = Field(gt=0)
    observacoes: Optional[str] = None


def _is_socio(u: User) -> bool:
    return ROLE_LEVEL.get(u.role.value, 0) >= ROLE_LEVEL["socio"]


def _serializar_campo_socio(valor):
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, _date):
        return valor.isoformat()
    if hasattr(valor, "value"):
        return valor.value
    return valor


def _out_socio(s: Socio) -> dict:
    return {
        "id": s.id,
        "user_id": s.user_id,
        "participacao_percentual": float(s.participacao_percentual),
        "regime": s.regime.value if hasattr(s.regime, "value") else s.regime,
        "pro_labore": float(s.pro_labore) if s.pro_labore is not None else None,
        "oab_numero": s.oab_numero,
        "oab_uf": s.oab_uf,
        "data_entrada": s.data_entrada.isoformat() if s.data_entrada else None,
        "data_saida": s.data_saida.isoformat() if s.data_saida else None,
        "ativo": s.ativo,
        "observacoes": s.observacoes,
    }


async def _travar_cap_table(db: AsyncSession) -> None:
    """Serializa mutações de participação dentro da transação corrente.

    A checagem de soma sem lock sofre TOCTOU: dois requests podem ler 80% e,
    simultaneamente, inserir 15% cada. O advisory xact lock é local ao Postgres,
    não requer migration e é liberado automaticamente no commit/rollback.
    """
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext('ejc:sociedade:cap-table'))"))


async def _validar_cap_table(
    db: AsyncSession,
    participacao: Decimal,
    *,
    excluir_socio_id: Optional[str] = None,
    ativo: bool = True,
) -> None:
    if not ativo:
        return
    q = select(func.coalesce(func.sum(Socio.participacao_percentual), 0)).where(
        Socio.ativo.is_(True)
    )
    if excluir_socio_id:
        q = q.where(Socio.id != excluir_socio_id)
    total_outros = Decimal(str((await db.execute(q)).scalar() or 0))
    total = total_outros + participacao
    if total > Decimal("1.0000"):
        raise HTTPException(
            422,
            f"Participação ativa total ficaria em {(total * 100):.2f}%, acima de 100%",
        )


# ── Sócios ────────────────────────────────────────────────────────────────────

@router.get("/socios")
async def listar_socios(
    ativo: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
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

    usuario = (await db.execute(select(User.id).where(User.id == req.user_id))).scalar_one_or_none()
    if not usuario:
        raise HTTPException(404, "Usuário informado não existe")

    await _travar_cap_table(db)
    existente = (
        await db.execute(select(Socio).where(Socio.user_id == req.user_id))
    ).scalar_one_or_none()
    if existente:
        raise HTTPException(409, "Usuário já é sócio")
    await _validar_cap_table(db, Decimal(str(req.participacao_percentual)))

    s = Socio(id=str(uuid4()), **req.model_dump())
    db.add(s)
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "CREATE",
        "socios",
        s.id,
        detalhes=f"Sócio {s.user_id} cadastrado",
        dados_antes={},
        dados_depois=_out_socio(s),
    )
    await db.commit()
    return _out_socio(s)


@router.patch("/socios/{socio_id}")
async def atualizar_socio(
    socio_id: str,
    req: SocioPatch,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["admin"]:
        raise HTTPException(403, "Apenas administradores podem alterar sócios")

    await _travar_cap_table(db)
    s = (
        await db.execute(select(Socio).where(Socio.id == socio_id))
    ).scalar_one_or_none()
    if not s:
        raise HTTPException(404)

    dados = req.model_dump(exclude_none=True)
    campos_invalidos = set(dados) - _SOCIO_PATCH_CAMPOS
    if campos_invalidos:
        raise HTTPException(422, f"Campos não permitidos no PATCH: {sorted(campos_invalidos)}")
    if not dados:
        raise HTTPException(422, "Nenhum campo informado para atualizar")

    participacao_nova = Decimal(
        str(dados.get("participacao_percentual", s.participacao_percentual))
    )
    ativo_novo = bool(dados.get("ativo", s.ativo))
    await _validar_cap_table(
        db,
        participacao_nova,
        excluir_socio_id=socio_id,
        ativo=ativo_novo,
    )

    dados_antes = {
        campo: _serializar_campo_socio(getattr(s, campo, None)) for campo in dados
    }
    for campo, valor in dados.items():
        setattr(s, campo, valor)
    s.updated_at = datetime.now(timezone.utc)
    dados_depois = {
        campo: _serializar_campo_socio(getattr(s, campo, None)) for campo in dados
    }
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "UPDATE",
        "socios",
        socio_id,
        detalhes=f"campos alterados: {sorted(dados)}",
        dados_antes=dados_antes,
        dados_depois=dados_depois,
    )
    await db.commit()
    return _out_socio(s)


# ── Distribuição de Lucros ────────────────────────────────────────────────────

@router.post("/distribuicao", status_code=201)
async def calcular_distribuicao(
    req: DistribuicaoIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_socio(cu):
        raise HTTPException(403)

    await _travar_cap_table(db)
    socios = (
        await db.execute(select(Socio).where(Socio.ativo.is_(True)))
    ).scalars().all()
    if not socios:
        raise HTTPException(422, "Nenhum sócio ativo cadastrado")

    total_participacao = sum(Decimal(str(s.participacao_percentual)) for s in socios)
    if total_participacao > Decimal("1.0001"):
        raise HTTPException(
            422,
            f"Participação total {total_participacao * 100:.2f}% excede 100%",
        )
    if total_participacao < Decimal("0.9999"):
        raise HTTPException(
            422,
            f"Participação total {total_participacao * 100:.2f}% difere de 100% — "
            "ajuste o quadro societário antes de distribuir os lucros",
        )

    centavo = Decimal("0.01")
    valor_total_dec = Decimal(str(req.valor_total)).quantize(centavo, rounding=ROUND_HALF_UP)
    socios_lista = []
    soma_cotas = Decimal("0")
    for s in socios:
        part = Decimal(str(s.participacao_percentual))
        valor = (valor_total_dec * part).quantize(centavo, rounding=ROUND_HALF_UP)
        soma_cotas += valor
        socios_lista.append(
            {
                "socio_id": s.id,
                "user_id": s.user_id,
                "participacao": float(part),
                "valor": valor,
            }
        )
    drift = valor_total_dec - soma_cotas
    if drift != Decimal("0") and socios_lista:
        maior = max(socios_lista, key=lambda item: item["valor"])
        maior["valor"] = (maior["valor"] + drift).quantize(centavo, rounding=ROUND_HALF_UP)
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
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "CREATE",
        "distribuicao_lucro",
        dist.id,
        detalhes=f"Distribuição {dist.mes_referencia} calculada",
        dados_depois={
            "mes_referencia": dist.mes_referencia,
            "valor_total": str(valor_total_dec),
            "status": "calculado",
            "socios_qtd": len(socios_lista),
        },
    )
    await db.commit()

    return {
        "id": dist.id,
        "mes_referencia": dist.mes_referencia,
        "valor_total": float(valor_total_dec),
        "status": "calculado",
        "distribuicao": socios_lista,
    }


@router.get("/distribuicao")
async def listar_distribuicoes(
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_socio(cu):
        raise HTTPException(403)
    q = select(DistribuicaoLucro).order_by(DistribuicaoLucro.mes_referencia.desc())
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    items = (
        await db.execute(q.offset((page - 1) * per_page).limit(per_page))
    ).scalars().all()
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
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
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["admin"]:
        raise HTTPException(403)
    d = (
        await db.execute(
            select(DistribuicaoLucro).where(DistribuicaoLucro.id == dist_id)
        )
    ).scalar_one_or_none()
    if not d:
        raise HTTPException(404)
    if d.status != "calculado":
        raise HTTPException(422, f"Distribuição já está '{d.status}'")

    status_antes = d.status
    d.status = "aprovado"
    d.aprovado_por = cu.id
    d.aprovado_em = datetime.now(timezone.utc)
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "UPDATE",
        "distribuicao_lucro",
        dist_id,
        detalhes=f"Distribuição {d.mes_referencia} aprovada",
        dados_antes={"status": status_antes},
        dados_depois={"status": d.status},
    )
    await db.commit()
    return {"id": dist_id, "status": "aprovado"}
