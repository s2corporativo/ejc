# ── app/routers/portal.py ────────────────────────────────────────────────────
# Portal do Cliente: acesso EXTERNO read-only.
# Segurança em camadas:
#   1. Middleware confina cliente_externo a /api/portal/*
#   2. Cada endpoint filtra por cu.client_id (nunca expõe dados de terceiros)
#   3. Documentos: apenas confidencialidade=normal
#   4. Estratégia do caso (tese, pontos fortes/fracos) NUNCA é exposta
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, UserRole
from app.models.case import Case, CaseMovimento
from app.models.deadline import Deadline
from app.models.fee import Fee
from app.models.document import Document, DocConfidencialidade
from app.models.audit_log import criar_audit_log
from app.services.fee_ledger_compat import LEDGER_COMPAT_CTES

router = APIRouter(prefix="/portal", tags=["Portal do Cliente"])

TIPOS_MOVIMENTOS_PORTAL = (
    "peticao", "decisao", "audiencia", "intimacao", "andamento_oficial"
)


def _exigir_cliente(cu: User) -> str:
    if cu.role != UserRole.cliente_externo or not cu.client_id:
        raise HTTPException(status_code=403, detail="Acesso exclusivo do Portal do Cliente")
    return cu.client_id


@router.get("/meus-casos")
async def meus_casos(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    client_id = _exigir_cliente(cu)
    rows = (await db.execute(
        select(Case).where(
            Case.client_id == client_id, Case.deleted_at.is_(None)
        ).order_by(Case.created_at.desc())
    )).scalars().all()

    ultimas: dict[str, dict] = {}
    case_ids = [c.id for c in rows]
    if case_ids:
        rn = func.row_number().over(
            partition_by=CaseMovimento.case_id,
            order_by=CaseMovimento.data_evento.desc(),
        ).label("rn")
        sub = select(
            CaseMovimento.case_id, CaseMovimento.data_evento,
            CaseMovimento.descricao, rn,
        ).where(
            CaseMovimento.case_id.in_(case_ids),
            CaseMovimento.tipo.in_(TIPOS_MOVIMENTOS_PORTAL),
        ).subquery()
        movs = (await db.execute(
            select(sub.c.case_id, sub.c.data_evento, sub.c.descricao)
            .where(sub.c.rn == 1)
        )).all()
        ultimas = {
            cid: {"data": data, "descricao": descricao.split(" [dj:")[0]}
            for cid, data, descricao in movs
        }

    return {"data": [
        {"id": c.id, "numero_interno": c.numero_interno, "titulo": c.titulo,
         "area": c.area.value if hasattr(c.area, "value") else str(c.area),
         "status": c.status.value if hasattr(c.status, "value") else str(c.status),
         "numero_processo": c.numero_processo, "comarca": c.comarca,
         "created_at": c.created_at,
         "ultima_movimentacao": ultimas.get(c.id)}
        for c in rows
    ]}


@router.get("/casos/{case_id}")
async def caso_detalhe(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    client_id = _exigir_cliente(cu)
    c = (await db.execute(select(Case).where(
        Case.id == case_id, Case.client_id == client_id,
        Case.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Caso não encontrado")

    movs = (await db.execute(
        select(CaseMovimento).where(
            CaseMovimento.case_id == case_id,
            CaseMovimento.tipo.in_(TIPOS_MOVIMENTOS_PORTAL),
        ).order_by(CaseMovimento.data_evento.desc()).limit(50)
    )).scalars().all()

    prazos = (await db.execute(
        select(Deadline).where(
            Deadline.case_id == case_id, Deadline.deleted_at.is_(None),
            Deadline.status == "pendente",
        ).order_by(Deadline.data_prazo)
    )).scalars().all()

    return {
        "caso": {
            "numero_interno": c.numero_interno, "titulo": c.titulo,
            "status": c.status.value if hasattr(c.status, "value") else str(c.status),
            "numero_processo": c.numero_processo,
            "comarca": c.comarca, "vara": c.vara,
        },
        "andamentos": [
            {"data": m.data_evento, "descricao": m.descricao.split(" [dj:")[0]}
            for m in movs
        ],
        "proximas_datas": [
            {"titulo": d.titulo, "data": d.data_prazo} for d in prazos
        ],
    }


@router.get("/documentos")
async def documentos(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    client_id = _exigir_cliente(cu)
    rows = (await db.execute(
        select(Document).where(
            Document.client_id == client_id,
            Document.deleted_at.is_(None),
            Document.confidencialidade == DocConfidencialidade.normal,
            or_(
                Document.publicado_portal.is_(True),
                Document.uploaded_by == cu.id,
            ),
        ).order_by(Document.created_at.desc())
    )).scalars().all()
    return {"data": [
        {"id": d.id, "titulo": d.titulo, "filename": d.filename,
         "created_at": d.created_at}
        for d in rows
    ]}


@router.get("/financeiro")
async def financeiro(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Financeiro do próprio cliente com ledger real + fallback legado seguro.

    `fee_payments` é soberano. Apenas fees antigos já quitados, com valor e
    data_pagamento, entram como pagamento legado quando NÃO existe nenhuma linha
    no subledger. Nenhum pagamento sintético é persistido por esta leitura.
    """
    client_id = _exigir_cliente(cu)

    ledger = await db.execute(
        # SQL literal com bind params; a regra marca todo text(), sem olhar
        # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        text(
            f"""
            WITH {LEDGER_COMPAT_CTES}
            SELECT pe.fee_id, pe.total_pago, pe.legado_sem_subledger
            FROM pagamentos_efetivos pe
            JOIN fees f ON f.id = pe.fee_id
            WHERE f.client_id = :client_id
              AND f.deleted_at IS NULL
            """
        ),
        {"client_id": client_id},
    )
    por_fee = {
        r["fee_id"]: {
            "total_pago": float(r["total_pago"] or 0),
            "legado_sem_subledger": bool(r["legado_sem_subledger"]),
        }
        for r in ledger.mappings().all()
    }

    rows = (await db.execute(
        select(Fee)
        .where(Fee.client_id == client_id, Fee.deleted_at.is_(None))
        .order_by(Fee.data_vencimento)
    )).scalars().all()

    data = []
    for fee in rows:
        valor_contratado = float(fee.valor) if fee.valor is not None else None
        compat = por_fee.get(fee.id, {"total_pago": 0.0, "legado_sem_subledger": False})
        total_pago = float(compat["total_pago"])
        saldo = (
            max(valor_contratado - total_pago, 0.0)
            if valor_contratado is not None
            else None
        )
        data.append({
            "descricao": fee.descricao,
            "valor": valor_contratado,
            "valor_contratado": valor_contratado,
            "total_pago": total_pago,
            "saldo": saldo,
            "pagamento_legado_sem_subledger": bool(compat["legado_sem_subledger"]),
            "percentual_exito": (
                float(fee.percentual_exito)
                if fee.percentual_exito is not None
                else None
            ),
            "tipo": fee.tipo.value if hasattr(fee.tipo, "value") else str(fee.tipo),
            "vencimento": fee.data_vencimento,
            "pago_em": fee.data_pagamento,
            "status": fee.status.value if hasattr(fee.status, "value") else str(fee.status),
        })
    return {"data": data}


class MsgIn(BaseModel):
    mensagem: str = Field(min_length=1, max_length=4000)


async def _caso_do_cliente(case_id: str, client_id: str, db: AsyncSession) -> None:
    r = await db.execute(
        text("SELECT 1 FROM cases WHERE id = :cid AND client_id = :clid "
             "AND deleted_at IS NULL"),
        {"cid": case_id, "clid": client_id},
    )
    if not r.first():
        raise HTTPException(status_code=404, detail="Caso não encontrado")


@router.get("/mensagens/nao-lidas")
async def mensagens_nao_lidas(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    client_id = _exigir_cliente(cu)
    res = await db.execute(
        text("""
            SELECT COUNT(*) FROM portal_mensagens pm
            JOIN cases c ON c.id = pm.case_id
            WHERE c.client_id = :clid AND c.deleted_at IS NULL
              AND pm.autor_tipo <> 'cliente' AND pm.lida = false
        """),
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
        text("""
            SELECT id, autor_tipo, autor_id, autor_nome, mensagem, lida, created_at
            FROM portal_mensagens WHERE case_id = :cid ORDER BY created_at ASC
        """),
        {"cid": case_id},
    )
    msgs = [dict(r) for r in res.mappings().all()]
    await db.execute(
        text("UPDATE portal_mensagens SET lida = true "
             "WHERE case_id = :cid AND autor_tipo <> 'cliente' AND lida = false"),
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
    nome = getattr(cu, "nome", None) or getattr(cu, "nome_completo", None) or cu.email
    res = await db.execute(
        text("""
            INSERT INTO portal_mensagens (case_id, autor_tipo, autor_id, autor_nome, mensagem)
            VALUES (:cid, 'cliente', :aid, :nome, :msg)
            RETURNING id, created_at
        """),
        {"cid": case_id, "aid": cu.id, "nome": nome, "msg": body.mensagem},
    )
    row = res.mappings().first()
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "portal_mensagens", row["id"])
    await db.commit()
    return {"id": row["id"], "created_at": row["created_at"]}
