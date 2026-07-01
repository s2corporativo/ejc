"""Rateio de honorários de êxito 50/50 (titular x escritório) após despesas do caso.
   Regra EJC: 50% advogado titular do caso, 50% escritório, após dedução das despesas.
   GET  /api/v1/honorarios-exito/{fee_id}/rateio  → preview não-destrutivo
   POST /api/v1/honorarios-exito/{fee_id}/rateio  → gera saque (partner_withdrawal) do titular
"""
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User

router = APIRouter(prefix="/honorarios-exito", tags=["Rateio de Êxito"])


def _is_gestor(u: User) -> bool:
    return ROLE_LEVEL.get(u.role.value, 0) >= ROLE_LEVEL["socio"]


async def _calcular(fee_id: str, db: AsyncSession) -> dict:
    fee = (await db.execute(text("""
        SELECT f.id, f.valor, f.tipo, f.status, f.descricao, f.case_id,
               c.titulo AS caso_titulo, c.numero_interno,
               c.advogado_responsavel_id, u.full_name AS titular_nome
        FROM fees f
        LEFT JOIN cases c ON c.id = f.case_id
        LEFT JOIN users u ON u.id = c.advogado_responsavel_id
        WHERE f.id = :fid AND f.deleted_at IS NULL
    """), {"fid": fee_id})).mappings().first()
    if not fee:
        raise HTTPException(404, "Honorário não encontrado")
    if fee["tipo"] != "exito":
        raise HTTPException(422, "Rateio aplicável apenas a honorários de êxito")

    bruto = float(fee["valor"] or 0)

    # Custo do caso UNIFICADO: despesas pagas do centro de custos + custas/despesas lançadas em fees.
    # (corrige: antes somava receitas+despesas; agora só tipo despesa, e inclui fees custas_despesas)
    desp = (await db.execute(text("""
        SELECT
          (SELECT COALESCE(SUM(valor),0) FROM centro_custos
             WHERE case_id = :cid AND deleted_at IS NULL AND tipo = 'despesa' AND pago = true)
          +
          (SELECT COALESCE(SUM(valor),0) FROM fees
             WHERE case_id = :cid AND deleted_at IS NULL AND tipo = 'custas_despesas' AND status = 'pago')
        AS total
    """), {"cid": fee["case_id"]})).scalar()
    despesas = float(desp or 0)

    liquido = round(max(bruto - despesas, 0), 2)
    titular_share = round(liquido * 0.5, 2)
    escritorio_share = round(liquido - titular_share, 2)

    # Titular é sócio?
    partner = None
    if fee["advogado_responsavel_id"]:
        partner = (await db.execute(text("""
            SELECT id FROM socios WHERE user_id = :uid AND ativo = true
        """), {"uid": fee["advogado_responsavel_id"]})).scalar()

    return {
        "fee": dict(fee) | {"valor": bruto},
        "bruto": bruto,
        "despesas_caso": despesas,
        "liquido": liquido,
        "titular": {
            "nome": fee["titular_nome"],
            "user_id": fee["advogado_responsavel_id"],
            "partner_id": partner,
            "valor": titular_share,
            "percentual": 50,
        },
        "escritorio": {"valor": escritorio_share, "percentual": 50},
        "pago": fee["status"] == "pago",
    }


@router.get("/{fee_id}/rateio")
async def preview_rateio(
    fee_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_gestor(cu):
        raise HTTPException(403, "Apenas sócios/gestores")
    return await _calcular(fee_id, db)


@router.post("/{fee_id}/rateio", status_code=201)
async def gerar_rateio(
    fee_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_gestor(cu):
        raise HTTPException(403, "Apenas sócios/gestores")
    calc = await _calcular(fee_id, db)
    if not calc["pago"]:
        raise HTTPException(422, "Honorário de êxito ainda não foi pago")
    socio_id = calc["titular"]["partner_id"]  # socios.id — prova de que o titular é sócio
    if not socio_id:
        raise HTTPException(422, "Advogado titular do caso não é sócio cadastrado — rateio manual necessário")
    # A13 (auditoria 2026-06-30): partner_withdrawals.partner_id é, por convenção
    # unificada, o users.id (igual ao create_withdrawal e ao filtro "minhas
    # retiradas"). Antes gravava socios.id -> o rateio de êxito sumia da lista do
    # próprio sócio. Passa a gravar o user_id do titular.
    partner_id = calc["titular"]["user_id"]

    # Evita duplicar: já existe saque com esta referência?
    ref = f"exito:{fee_id}"
    dup = (await db.execute(text("""
        SELECT id FROM partner_withdrawals
        WHERE period_reference = :ref AND deleted_at IS NULL
    """), {"ref": ref})).scalar()
    if dup:
        raise HTTPException(409, "Rateio já gerado para este honorário")

    wid = str(uuid4())
    await db.execute(text("""
        INSERT INTO partner_withdrawals
            (id, partner_id, gross_value, case_expenses, net_value, partner_share,
             description, period_reference, status, created_at, updated_at)
        VALUES (:id, :pid, :gross, :exp, :net, :share, :desc, :ref, 'pendente', now(), now())
    """), {
        "id": wid, "pid": partner_id, "gross": calc["bruto"],
        "exp": calc["despesas_caso"], "net": calc["liquido"], "share": calc["titular"]["valor"],
        "desc": f"Êxito 50% — {calc['fee'].get('caso_titulo') or 'caso'} ({calc['fee'].get('numero_interno') or ''})",
        "ref": ref,
    })
    await db.commit()
    return {"ok": True, "withdrawal_id": wid, "rateio": calc}
