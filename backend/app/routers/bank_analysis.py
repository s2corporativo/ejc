# ── app/routers/bank_analysis.py ─────────────────────────────────────────────
# Módulo de Análise Bancária (extratos) — upload → parse → detecta cobranças
# abusivas → Excel + documentos jurídicos. Determinístico (sem IA).
from __future__ import annotations
import os
from uuid import uuid4
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Body
from fastapi.responses import Response
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import get_settings
from app.core.security import get_current_user
from app.models.user import User
from app.models.bank_analysis import BankAnalysis, BankTransaction, BankAbusiveCharge
from app.services.bank_statement import parse_extrato, detectar_abusivas
from app.services import bank_report

router = APIRouter(prefix="/bank-analysis", tags=["Análise Bancária (Extratos)"])
settings = get_settings()


def _fmt_de_nome(nome: str) -> str:
    ext = os.path.splitext(nome or "")[1].lower().lstrip(".")
    return {"ofx": "ofx", "csv": "csv", "txt": "csv", "pdf": "pdf"}.get(ext, "")


@router.post("/upload", status_code=201)
async def upload(
    file: UploadFile = File(...),
    banco: str = Form(""),
    formato: str = Form(""),
    case_id: str = Form(""),
    client_id: str = Form(""),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    fmt = (formato or _fmt_de_nome(file.filename or "")).lower()
    if fmt not in ("ofx", "csv", "pdf"):
        raise HTTPException(422, "Formato não suportado (use PDF, OFX ou CSV)")
    conteudo = await file.read()
    if len(conteudo) > 25 * 1024 * 1024:
        raise HTTPException(413, "Arquivo excede 25MB")

    aid = str(uuid4())
    try:
        if fmt == "pdf":
            os.makedirs(f"{settings.UPLOAD_DIR}/bank", exist_ok=True)
            caminho = f"{settings.UPLOAD_DIR}/bank/{aid}.pdf"
            with open(caminho, "wb") as f:
                f.write(conteudo)
            transacoes = parse_extrato("pdf", caminho)
        else:
            try:
                texto = conteudo.decode("utf-8")
            except UnicodeDecodeError:
                texto = conteudo.decode("latin-1", errors="ignore")
            transacoes = parse_extrato(fmt, texto)
    except Exception as e:
        raise HTTPException(422, f"Falha ao ler o extrato: {e}")

    if not transacoes:
        raise HTTPException(422, "Nenhuma transação reconhecida no arquivo. "
                                 "Para PDF, tente exportar em OFX/CSV do app do banco.")

    # ids p/ ligar cobranças às transações
    for t in transacoes:
        t["_id"] = str(uuid4())
    cobrancas = detectar_abusivas(transacoes)

    datas = [t["data"] for t in transacoes if t.get("data")]
    creditos = sum(t["valor"] for t in transacoes if t["tipo"] == "credito" and t["valor"])
    debitos = sum(t["valor"] for t in transacoes if t["tipo"] == "debito" and t["valor"])
    total_abusivo = sum(c["valor"] for c in cobrancas if c.get("valor"))

    db.add(BankAnalysis(
        id=aid, case_id=case_id or None, client_id=client_id or None,
        banco=banco or None, formato=fmt, arquivo_nome=(file.filename or "")[:255],
        periodo_inicio=min(datas) if datas else None,
        periodo_fim=max(datas) if datas else None,
        total_transacoes=len(transacoes),
        total_creditos=round(creditos, 2), total_debitos=round(debitos, 2),
        total_abusivo=round(total_abusivo, 2), qtd_abusivas=len(cobrancas),
        status="concluido", created_by=cu.id,
    ))
    for t in transacoes:
        db.add(BankTransaction(
            id=t["_id"], analysis_id=aid, data=t.get("data"),
            descricao=t.get("descricao"), valor=t.get("valor"),
            tipo=t.get("tipo"), saldo=t.get("saldo"),
        ))
    for c in cobrancas:
        db.add(BankAbusiveCharge(
            id=str(uuid4()), analysis_id=aid,
            transaction_id=(c.get("transaction") or {}).get("_id"),
            regra=c.get("regra"), titulo=c.get("titulo"),
            descricao=c.get("descricao"), base_legal=c.get("base_legal"),
            prioridade=c.get("prioridade"), valor=c.get("valor"),
        ))
    await db.commit()
    return await detalhe(aid, db, cu)


@router.get("/")
async def listar(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user),
):
    total = (await db.execute(text(
        "SELECT count(*) FROM bank_analyses WHERE deleted_at IS NULL"))).scalar()
    rows = (await db.execute(text("""
        SELECT id, banco, formato, arquivo_nome, periodo_inicio, periodo_fim,
               total_transacoes, total_abusivo, qtd_abusivas, status, created_at
        FROM bank_analyses WHERE deleted_at IS NULL
        ORDER BY created_at DESC LIMIT :l OFFSET :o
    """), {"l": page_size, "o": (page - 1) * page_size})).mappings().all()
    return {"total": total, "page": page, "data": [dict(r) for r in rows]}


@router.get("/{analysis_id}")
async def detalhe(analysis_id: str, db: AsyncSession = Depends(get_db),
                  cu: User = Depends(get_current_user)):
    a = (await db.execute(select(BankAnalysis).where(
        BankAnalysis.id == analysis_id, BankAnalysis.deleted_at.is_(None)))).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "Análise não encontrada")
    txs = (await db.execute(select(BankTransaction).where(
        BankTransaction.analysis_id == analysis_id).order_by(BankTransaction.data))).scalars().all()
    chs = (await db.execute(select(BankAbusiveCharge).where(
        BankAbusiveCharge.analysis_id == analysis_id))).scalars().all()
    return {
        "analise": {c.name: getattr(a, c.name) for c in a.__table__.columns},
        "transacoes": [{c.name: getattr(t, c.name) for c in t.__table__.columns} for t in txs],
        "cobrancas": [{c.name: getattr(x, c.name) for c in x.__table__.columns} for x in chs],
    }


def _carregar(analysis_id, db):  # helper sync wrapper não usado; mantido p/ clareza
    raise NotImplementedError


@router.get("/{analysis_id}/excel")
async def excel(analysis_id: str, db: AsyncSession = Depends(get_db),
                cu: User = Depends(get_current_user)):
    d = await detalhe(analysis_id, db, cu)
    transacoes = [{"data": t["data"], "descricao": t["descricao"], "valor": float(t["valor"] or 0),
                   "tipo": t["tipo"], "saldo": (float(t["saldo"]) if t["saldo"] is not None else None)}
                  for t in d["transacoes"]]
    cobrancas = [{"regra": c["regra"], "titulo": c["titulo"], "base_legal": c["base_legal"],
                  "prioridade": c["prioridade"], "valor": float(c["valor"] or 0),
                  "transaction": {"data": c.get("data")}} for c in d["cobrancas"]]
    xls = bank_report.gerar_excel(d["analise"], transacoes, cobrancas)
    nome = f"analise_bancaria_{analysis_id[:8]}.xlsx"
    return Response(content=xls,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@router.post("/{analysis_id}/documento")
async def documento(analysis_id: str, payload: dict = Body(default={}),
                    db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    tipo = (payload.get("tipo") or "notificacao").lower()
    if tipo not in ("notificacao", "peticao", "bacen"):
        raise HTTPException(422, "tipo deve ser notificacao|peticao|bacen")
    d = await detalhe(analysis_id, db, cu)
    cobrancas = [{"titulo": c["titulo"], "base_legal": c["base_legal"], "valor": float(c["valor"] or 0),
                  "transaction": {"data": c.get("data")}} for c in d["cobrancas"]]
    html_doc = bank_report.gerar_documento(tipo, d["analise"], cobrancas, payload.get("dados") or {})
    return {"tipo": tipo, "html": html_doc}


@router.delete("/{analysis_id}")
async def remover(analysis_id: str, db: AsyncSession = Depends(get_db),
                  cu: User = Depends(get_current_user)):
    await db.execute(text("UPDATE bank_analyses SET deleted_at = :n WHERE id = :i"),
                     {"n": datetime.now(timezone.utc), "i": analysis_id})
    await db.commit()
    return {"ok": True}
