# ── app/routers/gestao_societaria.py ─────────────────────────────────────────
# Gestão Societária — cadastro interno, cap table e distribuição de lucros.
# Não substitui contrato social, registro perante OAB/Junta ou escrituração.
from __future__ import annotations

import json
from datetime import date as _date
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.audit_log import criar_audit_log
from app.models.socio import DistribuicaoLucro, RegimeSocio, Socio, SocioHistorico
from app.models.user import User

router = APIRouter(prefix="/sociedade", tags=["Gestão Societária"])
_CENTAVO = Decimal("0.01")
_QUATRO = Decimal("0.0001")


class SocioIn(BaseModel):
    user_id: str
    participacao_percentual: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))
    regime: RegimeSocio = RegimeSocio.misto
    pro_labore: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    oab_numero: Optional[str] = None
    oab_uf: Optional[str] = None
    data_entrada: _date
    observacoes: Optional[str] = None


class SocioPatch(BaseModel):
    participacao_percentual: Optional[Decimal] = Field(
        default=None, gt=Decimal("0"), le=Decimal("1")
    )
    regime: Optional[RegimeSocio] = None
    pro_labore: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    ativo: Optional[bool] = None
    data_saida: Optional[_date] = None
    meta_produtividade: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    observacoes: Optional[str] = None
    motivo_alteracao: Optional[str] = Field(default=None, min_length=3, max_length=1000)


class DistribuicaoIn(BaseModel):
    mes_referencia: str = Field(pattern=r"^\d{4}-\d{2}$")
    valor_total: Decimal = Field(gt=Decimal("0"))
    observacoes: Optional[str] = None


def _is_socio(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["socio"]


def _is_admin(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["admin"]


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
        "meta_produtividade": (
            float(s.meta_produtividade) if s.meta_produtividade is not None else None
        ),
        "ativo": s.ativo,
        "observacoes": s.observacoes,
    }


def _snapshot(s: Socio) -> dict:
    return _out_socio(s)


async def _validar_cap_table(
    db: AsyncSession,
    *,
    participacao: Decimal,
    ativo: bool,
    excluir_socio_id: str | None = None,
) -> Decimal:
    if not ativo:
        total_outros = await db.scalar(
            select(func.coalesce(func.sum(Socio.participacao_percentual), 0)).where(
                Socio.ativo.is_(True),
                *([Socio.id != excluir_socio_id] if excluir_socio_id else []),
            )
        )
        return Decimal(str(total_outros or 0)).quantize(_QUATRO)

    filtros = [Socio.ativo.is_(True)]
    if excluir_socio_id:
        filtros.append(Socio.id != excluir_socio_id)
    total_outros = await db.scalar(
        select(func.coalesce(func.sum(Socio.participacao_percentual), 0)).where(*filtros)
    )
    total = Decimal(str(total_outros or 0)) + Decimal(str(participacao))
    if total > Decimal("1.0001"):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Participação ativa total ficaria em {total * 100:.2f}%, acima de 100%. "
                "Revise o cap table antes de salvar."
            ),
        )
    return total.quantize(_QUATRO)


async def _registrar_historico(
    db: AsyncSession,
    socio: Socio,
    user_id: str,
    motivo: str,
    antes: dict | None,
    depois: dict,
) -> SocioHistorico:
    hist = SocioHistorico(
        id=str(uuid4()),
        socio_id=socio.id,
        alterado_por=user_id,
        motivo=motivo,
        dados_antes=json.dumps(antes, ensure_ascii=False, default=str) if antes else None,
        dados_depois=json.dumps(depois, ensure_ascii=False, default=str),
    )
    db.add(hist)
    return hist


@router.get("/socios")
async def listar_socios(
    ativo: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_socio(cu):
        raise HTTPException(status_code=403, detail="Acesso restrito a sócios")
    q = select(Socio)
    if ativo is not None:
        q = q.where(Socio.ativo.is_(ativo))
    socios = (
        await db.execute(q.order_by(Socio.participacao_percentual.desc()))
    ).scalars().all()
    total = sum(Decimal(str(s.participacao_percentual)) for s in socios if s.ativo)
    return {
        "total_participacao": float(total),
        "cap_table_completo": Decimal("0.9999") <= total <= Decimal("1.0001"),
        "cap_table_valido": total <= Decimal("1.0001"),
        "socios": [_out_socio(s) for s in socios],
        "aviso": (
            None
            if Decimal("0.9999") <= total <= Decimal("1.0001")
            else "O quadro ativo não soma 100%; distribuição de lucros permanecerá bloqueada."
        ),
    }


@router.get("/socios/{socio_id}/historico")
async def historico_socio(
    socio_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_socio(cu):
        raise HTTPException(status_code=403, detail="Acesso restrito a sócios")
    existe = await db.scalar(select(Socio.id).where(Socio.id == socio_id))
    if not existe:
        raise HTTPException(status_code=404, detail="Sócio não encontrado")
    rows = (
        await db.execute(
            select(SocioHistorico)
            .where(SocioHistorico.socio_id == socio_id)
            .order_by(SocioHistorico.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return {
        "data": [
            {
                "id": h.id,
                "motivo": h.motivo,
                "alterado_por": h.alterado_por,
                "dados_antes": json.loads(h.dados_antes) if h.dados_antes else None,
                "dados_depois": json.loads(h.dados_depois),
                "created_at": h.created_at,
            }
            for h in rows
        ]
    }


@router.post("/socios", status_code=201)
async def cadastrar_socio(
    req: SocioIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_admin(cu):
        raise HTTPException(
            status_code=403, detail="Apenas administradores podem cadastrar sócios"
        )
    existente = await db.scalar(select(Socio).where(Socio.user_id == req.user_id))
    if existente:
        raise HTTPException(status_code=409, detail="Usuário já é sócio")

    await _validar_cap_table(
        db,
        participacao=req.participacao_percentual,
        ativo=True,
    )
    socio = Socio(id=str(uuid4()), **req.model_dump())
    db.add(socio)
    await db.flush()
    depois = _snapshot(socio)
    await _registrar_historico(
        db,
        socio,
        cu.id,
        "Cadastro inicial do sócio",
        None,
        depois,
    )
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "CREATE",
        "socios",
        socio.id,
        dados_depois=depois,
    )
    await db.commit()
    return _out_socio(socio)


@router.patch("/socios/{socio_id}")
async def atualizar_socio(
    socio_id: str,
    req: SocioPatch,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_admin(cu):
        raise HTTPException(
            status_code=403,
            detail="Alterações do quadro societário são restritas a administradores",
        )
    socio = await db.scalar(select(Socio).where(Socio.id == socio_id).with_for_update())
    if not socio:
        raise HTTPException(status_code=404, detail="Sócio não encontrado")

    alteracoes = req.model_dump(exclude_none=True)
    motivo = alteracoes.pop("motivo_alteracao", None)
    if not alteracoes:
        raise HTTPException(status_code=422, detail="Nenhuma alteração informada")

    campos_sensiveis = {
        "participacao_percentual",
        "regime",
        "pro_labore",
        "ativo",
        "data_saida",
    }
    if campos_sensiveis.intersection(alteracoes) and not motivo:
        raise HTTPException(
            status_code=422,
            detail=(
                "Informe motivo_alteracao para participação, regime, pró-labore "
                "ou situação societária."
            ),
        )
    motivo = motivo or "Atualização cadastral não societária"

    antes = _snapshot(socio)
    nova_participacao = Decimal(
        str(alteracoes.get("participacao_percentual", socio.participacao_percentual))
    )
    novo_ativo = bool(alteracoes.get("ativo", socio.ativo))
    await _validar_cap_table(
        db,
        participacao=nova_participacao,
        ativo=novo_ativo,
        excluir_socio_id=socio.id,
    )

    for campo, valor in alteracoes.items():
        setattr(socio, campo, valor)
    socio.updated_at = datetime.now(timezone.utc)
    depois = _snapshot(socio)
    await _registrar_historico(db, socio, cu.id, motivo, antes, depois)
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "UPDATE",
        "socios",
        socio.id,
        dados_antes=antes,
        dados_depois=depois,
        detalhes=f"motivo={motivo}",
    )
    await db.commit()
    return _out_socio(socio)


@router.post("/distribuicao", status_code=201)
async def calcular_distribuicao(
    req: DistribuicaoIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_socio(cu):
        raise HTTPException(status_code=403, detail="Acesso restrito a sócios")

    socios = (
        await db.execute(select(Socio).where(Socio.ativo.is_(True)))
    ).scalars().all()
    if not socios:
        raise HTTPException(status_code=422, detail="Nenhum sócio ativo cadastrado")

    total_participacao = sum(Decimal(str(s.participacao_percentual)) for s in socios)
    if total_participacao > Decimal("1.0001"):
        raise HTTPException(
            status_code=422,
            detail=f"Participação total {total_participacao * 100:.2f}% excede 100%",
        )
    if total_participacao < Decimal("0.9999"):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Participação total {total_participacao * 100:.2f}% difere de 100% — "
                "ajuste o quadro societário antes de distribuir os lucros"
            ),
        )

    valor_total_dec = req.valor_total.quantize(_CENTAVO, rounding=ROUND_HALF_UP)
    socios_lista = []
    soma_cotas = Decimal("0")
    for socio in socios:
        part = Decimal(str(socio.participacao_percentual))
        valor = (valor_total_dec * part).quantize(_CENTAVO, rounding=ROUND_HALF_UP)
        soma_cotas += valor
        socios_lista.append(
            {
                "socio_id": socio.id,
                "user_id": socio.user_id,
                "participacao": float(part),
                "valor": valor,
            }
        )
    drift = valor_total_dec - soma_cotas
    if drift != Decimal("0") and socios_lista:
        maior = max(socios_lista, key=lambda item: item["valor"])
        maior["valor"] = (maior["valor"] + drift).quantize(
            _CENTAVO, rounding=ROUND_HALF_UP
        )
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
        dados_depois={
            "mes_referencia": req.mes_referencia,
            "valor_total": str(valor_total_dec),
            "socios": len(socios_lista),
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
        raise HTTPException(status_code=403, detail="Acesso restrito a sócios")
    q = select(DistribuicaoLucro).order_by(DistribuicaoLucro.mes_referencia.desc())
    total = (
        await db.execute(select(func.count()).select_from(q.subquery()))
    ).scalar() or 0
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
    if not _is_admin(cu):
        raise HTTPException(status_code=403, detail="Aprovação restrita a administradores")
    dist = await db.scalar(
        select(DistribuicaoLucro)
        .where(DistribuicaoLucro.id == dist_id)
        .with_for_update()
    )
    if not dist:
        raise HTTPException(status_code=404, detail="Distribuição não encontrada")
    if dist.status != "calculado":
        raise HTTPException(status_code=422, detail=f"Distribuição já está '{dist.status}'")
    # Segregação de funções: quem calculou/criou a própria distribuição não pode
    # ser o segundo par de olhos que a aprova, inclusive se for superadmin.
    if dist.created_by and str(dist.created_by) == str(cu.id):
        raise HTTPException(
            status_code=403,
            detail=(
                "Quem criou a distribuição não pode aprová-la — segregação de funções"
            ),
        )
    dist.status = "aprovado"
    dist.aprovado_por = cu.id
    dist.aprovado_em = datetime.now(timezone.utc)
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "APPROVE",
        "distribuicao_lucro",
        dist_id,
        dados_depois={"status": "aprovado", "aprovado_por": cu.id},
    )
    await db.commit()
    return {"id": dist_id, "status": "aprovado"}
