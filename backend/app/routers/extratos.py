"""Extratos consolidados — caso, advogado e sócio.
   Agrega fees + centro_custos + partner_withdrawals + distribuicoes_lucro.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.core.ownership import verificar_acesso_caso
from app.models.user import User

router = APIRouter(prefix="/extratos", tags=["Extratos"])


def _gestor(u: User) -> bool:
    return ROLE_LEVEL.get(u.role.value, 0) >= ROLE_LEVEL["socio"]


@router.get("/detalhado/{case_id}")
async def extrato_caso(case_id: str, db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    # Gate de ownership (IDOR): 404 se não existe, 403 se sem acesso ao caso.
    await verificar_acesso_caso(db, cu, case_id)
    caso = (await db.execute(text("SELECT titulo, numero_interno FROM cases WHERE id=:id AND deleted_at IS NULL"), {"id": case_id})).mappings().first()
    if not caso:
        raise HTTPException(404, "Caso não encontrado")
    fees = (await db.execute(text("""
        SELECT tipo, status, descricao, valor, data_pagamento, data_vencimento
        FROM fees WHERE case_id=:id AND deleted_at IS NULL ORDER BY created_at
    """), {"id": case_id})).mappings().all()
    custos = (await db.execute(text("""
        SELECT tipo, categoria, descricao, valor, data_lancamento, pago
        FROM centro_custos WHERE case_id=:id AND deleted_at IS NULL ORDER BY data_lancamento
    """), {"id": case_id})).mappings().all()
    entradas = round(sum(float(f["valor"] or 0) for f in fees if f["status"] == "pago"), 2)
    a_receber = round(sum(float(f["valor"] or 0) for f in fees if f["status"] not in ("pago", "cancelado")), 2)
    saidas = round(sum(float(c["valor"] or 0) for c in custos if c["tipo"] == "despesa"), 2)
    return {
        "caso": dict(caso),
        "resumo": {"entradas": entradas, "a_receber": a_receber, "saidas": saidas,
                   "saldo": round(entradas - saidas, 2)},
        "honorarios": [dict(f) | {"valor": float(f["valor"] or 0)} for f in fees],
        "custos": [dict(c) | {"valor": float(c["valor"] or 0)} for c in custos],
    }


@router.get("/advogado/{user_id}")
async def extrato_advogado(user_id: str, db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    if not _gestor(cu) and cu.id != user_id:
        raise HTTPException(403, "Sem permissão")
    adv = (await db.execute(text("SELECT full_name FROM users WHERE id=:id"), {"id": user_id})).scalar()
    if adv is None:
        raise HTTPException(404, "Usuário não encontrado")
    # honorários dos casos sob responsabilidade do advogado
    fees = (await db.execute(text("""
        SELECT f.tipo, f.status, f.valor, c.titulo AS caso, f.data_pagamento
        FROM fees f JOIN cases c ON c.id = f.case_id
        WHERE c.advogado_responsavel_id = :uid AND f.deleted_at IS NULL
        ORDER BY f.created_at
    """), {"uid": user_id})).mappings().all()
    # saques do advogado (se for sócio)
    saques = (await db.execute(text("""
        SELECT gross_value, net_value, partner_share, description, status, created_at
        FROM partner_withdrawals WHERE partner_id = :uid AND deleted_at IS NULL ORDER BY created_at
    """), {"uid": user_id})).mappings().all()
    recebido = round(sum(float(f["valor"] or 0) for f in fees if f["status"] == "pago"), 2)
    saques_total = round(sum(float(s["partner_share"] or 0) for s in saques), 2)
    return {
        "advogado": adv,
        "resumo": {"honorarios_recebidos": recebido, "saques_exito": saques_total},
        "honorarios": [dict(f) | {"valor": float(f["valor"] or 0)} for f in fees],
        "saques": [dict(s) | {"partner_share": float(s["partner_share"] or 0)} for s in saques],
    }


@router.get("/socio/{user_id}")
async def extrato_socio(user_id: str, db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    if not _gestor(cu):
        raise HTTPException(403, "Apenas sócios/gestores")
    socio = (await db.execute(text("""
        SELECT u.full_name, s.participacao_percentual, s.pro_labore, s.observacoes
        FROM socios s JOIN users u ON u.id = s.user_id WHERE s.user_id = :uid
    """), {"uid": user_id})).mappings().first()
    if not socio:
        raise HTTPException(404, "Sócio não encontrado")
    saques = (await db.execute(text("""
        SELECT partner_share, description, status, created_at, paid_at
        FROM partner_withdrawals WHERE partner_id = :uid AND deleted_at IS NULL ORDER BY created_at
    """), {"uid": user_id})).mappings().all()
    # distribuições de lucro (socios_json contém o rateio)
    dist = (await db.execute(text("""
        SELECT mes_referencia, valor_total, socios_json, status, created_at
        FROM distribuicoes_lucro ORDER BY created_at DESC LIMIT 24
    """))).mappings().all()
    saques_total = round(sum(float(s["partner_share"] or 0) for s in saques), 2)
    return {
        "socio": dict(socio) | {"participacao_percentual": float(socio["participacao_percentual"] or 0),
                                "pro_labore": float(socio["pro_labore"]) if socio["pro_labore"] else None},
        "resumo": {"saques_exito": saques_total},
        "saques": [dict(s) | {"partner_share": float(s["partner_share"] or 0)} for s in saques],
        "distribuicoes": [dict(d) | {"valor_total": float(d["valor_total"] or 0)} for d in dist],
    }
