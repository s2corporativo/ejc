# ── app/routers/portal.py ────────────────────────────────────────────────────
# Portal do Cliente: superfície externa com isolamento por client_id.
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.audit_log import criar_audit_log
from app.models.case import Case, CaseMovimento
from app.models.deadline import Deadline
from app.models.document import DocConfidencialidade, Document
from app.models.fee import Fee, FeePayment
from app.models.user import User, UserRole

router = APIRouter(prefix="/portal", tags=["Portal do Cliente"])


def _exigir_cliente(cu: User) -> str:
    if cu.role != UserRole.cliente_externo or not cu.client_id:
        raise HTTPException(
            status_code=403, detail="Acesso exclusivo do Portal do Cliente"
        )
    return cu.client_id


@router.get("/meus-casos")
async def meus_casos(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    client_id = _exigir_cliente(cu)
    rows = (
        await db.execute(
            select(Case)
            .where(Case.client_id == client_id, Case.deleted_at.is_(None))
            .order_by(Case.created_at.desc())
        )
    ).scalars().all()

    ultimas: dict[str, dict] = {}
    case_ids = [c.id for c in rows]
    if case_ids:
        rn = func.row_number().over(
            partition_by=CaseMovimento.case_id,
            order_by=CaseMovimento.data_evento.desc(),
        ).label("rn")
        sub = (
            select(
                CaseMovimento.case_id,
                CaseMovimento.data_evento,
                CaseMovimento.descricao,
                rn,
            )
            .where(CaseMovimento.case_id.in_(case_ids))
            .subquery()
        )
        movs = (
            await db.execute(
                select(sub.c.case_id, sub.c.data_evento, sub.c.descricao).where(
                    sub.c.rn == 1
                )
            )
        ).all()
        ultimas = {
            cid: {
                "data": data,
                "descricao": (descricao or "").split(" [dj:")[0],
            }
            for cid, data, descricao in movs
        }

    return {
        "data": [
            {
                "id": c.id,
                "numero_interno": c.numero_interno,
                "titulo": c.titulo,
                "area": c.area.value if hasattr(c.area, "value") else str(c.area),
                "status": c.status.value
                if hasattr(c.status, "value")
                else str(c.status),
                "numero_processo": c.numero_processo,
                "comarca": c.comarca,
                "created_at": c.created_at,
                "ultima_movimentacao": ultimas.get(c.id),
            }
            for c in rows
        ]
    }


@router.get("/casos/{case_id}")
async def caso_detalhe(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    client_id = _exigir_cliente(cu)
    caso = (
        await db.execute(
            select(Case).where(
                Case.id == case_id,
                Case.client_id == client_id,
                Case.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not caso:
        raise HTTPException(status_code=404, detail="Caso não encontrado")

    movs = (
        await db.execute(
            select(CaseMovimento)
            .where(CaseMovimento.case_id == case_id)
            .order_by(CaseMovimento.data_evento.desc())
            .limit(50)
        )
    ).scalars().all()
    prazos = (
        await db.execute(
            select(Deadline)
            .where(
                Deadline.case_id == case_id,
                Deadline.deleted_at.is_(None),
                Deadline.status == "pendente",
            )
            .order_by(Deadline.data_prazo)
        )
    ).scalars().all()

    return {
        "caso": {
            "numero_interno": caso.numero_interno,
            "titulo": caso.titulo,
            "status": caso.status.value
            if hasattr(caso.status, "value")
            else str(caso.status),
            "numero_processo": caso.numero_processo,
            "comarca": caso.comarca,
            "vara": caso.vara,
        },
        "andamentos": [
            {
                "data": mov.data_evento,
                "descricao": (mov.descricao or "").split(" [dj:")[0],
            }
            for mov in movs
        ],
        "proximas_datas": [
            {"titulo": prazo.titulo, "data": prazo.data_prazo} for prazo in prazos
        ],
    }


@router.get("/documentos")
async def documentos(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Somente documentos EXPRESSAMENTE publicados para o Portal.

    Confidencialidade é classificação interna e publicação é autorização externa.
    As duas condições são reavaliadas em toda leitura: se um documento publicado
    for posteriormente movido para interno/restrito/confidencial/segredo, ele
    deixa de ser servido imediatamente, mesmo que o flag de publicação ainda
    esteja registrado para auditoria/gestão.
    """
    client_id = _exigir_cliente(cu)
    rows = (
        await db.execute(
            select(Document)
            .where(
                Document.client_id == client_id,
                Document.deleted_at.is_(None),
                Document.publicado_portal.is_(True),
                Document.confidencialidade == DocConfidencialidade.normal,
            )
            .order_by(
                Document.publicado_em.desc().nullslast(),
                Document.created_at.desc(),
            )
        )
    ).scalars().all()
    return {
        "data": [
            {
                "id": doc.id,
                "titulo": doc.titulo,
                "filename": doc.filename,
                "created_at": doc.created_at,
                "publicado_em": doc.publicado_em,
            }
            for doc in rows
        ]
    }


@router.get("/financeiro")
async def financeiro(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Honorários com valor original, baixas e saldo real.

    `valor` é mantido por compatibilidade e representa o valor ORIGINAL. A UI
    deve usar `saldo_aberto` para cobrança e `valor_pago` para baixas parciais.
    """
    client_id = _exigir_cliente(cu)
    rows = (
        await db.execute(
            select(Fee)
            .where(Fee.client_id == client_id, Fee.deleted_at.is_(None))
            .order_by(Fee.data_vencimento)
        )
    ).scalars().all()

    pagamentos_por_fee: dict[str, tuple[Decimal, object | None]] = {}
    ids = [fee.id for fee in rows]
    if ids:
        pagamentos = (
            await db.execute(
                select(
                    FeePayment.fee_id,
                    func.coalesce(func.sum(FeePayment.valor), 0),
                    func.max(FeePayment.data_pagamento),
                )
                .where(FeePayment.fee_id.in_(ids))
                .group_by(FeePayment.fee_id)
            )
        ).all()
        pagamentos_por_fee = {
            fee_id: (Decimal(str(total or 0)), ultima)
            for fee_id, total, ultima in pagamentos
        }

    data = []
    for fee in rows:
        original = Decimal(str(fee.valor or 0))
        pago, ultima_baixa = pagamentos_por_fee.get(fee.id, (Decimal("0"), None))
        saldo = max(original - pago, Decimal("0"))
        status = fee.status.value if hasattr(fee.status, "value") else str(fee.status)
        data.append(
            {
                "id": fee.id,
                "descricao": fee.descricao,
                "tipo": fee.tipo.value if hasattr(fee.tipo, "value") else str(fee.tipo),
                "valor": float(original),
                "valor_original": float(original),
                "valor_pago": float(pago),
                "saldo_aberto": float(saldo),
                "vencimento": fee.data_vencimento,
                "pago_em": fee.data_pagamento or ultima_baixa,
                "ultima_baixa": ultima_baixa,
                "status": status,
            }
        )
    return {"data": data}


class MsgIn(BaseModel):
    mensagem: str = Field(min_length=1, max_length=4000)


async def _caso_do_cliente(case_id: str, client_id: str, db: AsyncSession) -> None:
    result = await db.execute(
        text(
            "SELECT 1 FROM cases WHERE id = :cid AND client_id = :clid "
            "AND deleted_at IS NULL"
        ),
        {"cid": case_id, "clid": client_id},
    )
    if not result.first():
        raise HTTPException(status_code=404, detail="Caso não encontrado")


@router.get("/mensagens/nao-lidas")
async def mensagens_nao_lidas(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    client_id = _exigir_cliente(cu)
    res = await db.execute(
        text(
            """
            SELECT COUNT(*) FROM portal_mensagens pm
            JOIN cases c ON c.id = pm.case_id
            WHERE c.client_id = :clid AND c.deleted_at IS NULL
              AND pm.autor_tipo <> 'cliente' AND pm.lida = false
            """
        ),
        {"clid": client_id},
    )
    return {"nao_lidas": int(res.scalar() or 0)}


@router.get("/casos/{case_id}/mensagens")
async def listar_mensagens_portal(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    client_id = _exigir_cliente(cu)
    await _caso_do_cliente(case_id, client_id, db)
    res = await db.execute(
        text(
            """
            SELECT id, autor_tipo, autor_id, autor_nome, mensagem, lida, created_at
            FROM portal_mensagens WHERE case_id = :cid ORDER BY created_at ASC
            """
        ),
        {"cid": case_id},
    )
    msgs = [dict(r) for r in res.mappings().all()]
    await db.execute(
        text(
            "UPDATE portal_mensagens SET lida = true "
            "WHERE case_id = :cid AND autor_tipo <> 'cliente' AND lida = false"
        ),
        {"cid": case_id},
    )
    await db.commit()
    return msgs


@router.post("/casos/{case_id}/mensagens", status_code=201)
async def enviar_mensagem_portal(
    case_id: str,
    body: MsgIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    client_id = _exigir_cliente(cu)
    await _caso_do_cliente(case_id, client_id, db)
    nome = (
        getattr(cu, "nome", None)
        or getattr(cu, "nome_completo", None)
        or cu.full_name
        or cu.email
    )
    res = await db.execute(
        text(
            """
            INSERT INTO portal_mensagens (case_id, autor_tipo, autor_id, autor_nome, mensagem)
            VALUES (:cid, 'cliente', :aid, :nome, :msg)
            RETURNING id, created_at
            """
        ),
        {"cid": case_id, "aid": cu.id, "nome": nome, "msg": body.mensagem},
    )
    row = res.mappings().first()
    await criar_audit_log(
        db, cu.id, cu.role.value, "CREATE", "portal_mensagens", row["id"]
    )
    await db.commit()
    return {"id": row["id"], "created_at": row["created_at"]}
