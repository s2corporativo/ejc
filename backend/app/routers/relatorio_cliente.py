"""Relatório financeiro consolidado do cliente — GET /clients/{client_id}/relatorio-financeiro"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User

_FIN_ADV = {"superadmin", "admin", "socio", "financeiro", "advogado"}


def _req_fin_adv(cu: User = Depends(get_current_user)) -> User:
    # Relatório financeiro + PII (CPF/CNPJ) do cliente: só gestão/financeiro/advogado.
    if cu.role.value not in _FIN_ADV:
        raise HTTPException(status_code=403, detail="Acesso restrito a gestão/financeiro/advogado")
    return cu


router = APIRouter(prefix="/clients/{client_id}/relatorio-financeiro", tags=["Relatório Financeiro Cliente"], dependencies=[Depends(_req_fin_adv)])


@router.get("")
async def relatorio_financeiro_cliente(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    cli = (await db.execute(text("""
        SELECT id, nome, email, telefone, whatsapp, COALESCE(cpf, cnpj) AS cpf_cnpj FROM clients
        WHERE id = :cid AND deleted_at IS NULL
    """), {"cid": client_id})).mappings().first()
    if not cli:
        raise HTTPException(404, "Cliente não encontrado")

    # Honorários por tipo/status
    fees = (await db.execute(text("""
        SELECT f.id, f.tipo, f.status, f.descricao, f.valor, f.percentual_exito,
               f.data_vencimento, f.data_pagamento, f.case_id,
               c.titulo AS caso_titulo, c.numero_interno
        FROM fees f
        LEFT JOIN cases c ON c.id = f.case_id
        WHERE f.client_id = :cid AND f.deleted_at IS NULL
        ORDER BY f.created_at DESC
    """), {"cid": client_id})).mappings().all()
    fees = [dict(f) for f in fees]
    for f in fees:
        f["valor"] = float(f["valor"] or 0)
        if f.get("percentual_exito") is not None:
            f["percentual_exito"] = float(f["percentual_exito"])

    def soma(pred):
        return round(sum(f["valor"] for f in fees if pred(f)), 2)

    total          = soma(lambda f: True)
    recebido       = soma(lambda f: f["status"] == "pago")
    pendente       = soma(lambda f: f["status"] not in ("pago", "cancelado"))
    atrasado       = soma(lambda f: f["status"] == "atrasado")
    contratual     = soma(lambda f: f["tipo"] in ("fixo", "misto", "por_hora"))
    exito          = soma(lambda f: f["tipo"] == "exito")
    custas         = soma(lambda f: f["tipo"] == "custas_despesas")
    exito_recebido = soma(lambda f: f["tipo"] == "exito" and f["status"] == "pago")

    # Despesas vinculadas aos casos do cliente (centro de custos)
    despesas = (await db.execute(text("""
        SELECT cc.id, cc.tipo, cc.categoria, cc.valor, cc.descricao,
               cc.data_lancamento, cc.pago, cc.case_id, c.titulo AS caso_titulo
        FROM centro_custos cc
        JOIN cases c ON c.id = cc.case_id
        WHERE c.client_id = :cid AND cc.deleted_at IS NULL
        ORDER BY cc.data_lancamento DESC
    """), {"cid": client_id})).mappings().all()
    despesas = [dict(d) for d in despesas]
    for d in despesas:
        d["valor"] = float(d["valor"] or 0)
    total_despesas    = round(sum(d["valor"] for d in despesas), 2)
    despesas_pagas    = round(sum(d["valor"] for d in despesas if d["pago"]), 2)
    reembolsos        = round(sum(d["valor"] for d in despesas if (d.get("tipo") or "") == "reembolsavel"), 2)

    # Extrato unificado (honorários pagos + despesas) ordenado por data
    extrato = []
    for f in fees:
        if f["status"] == "pago" and f.get("data_pagamento"):
            extrato.append({
                "data": str(f["data_pagamento"]), "tipo": "credito",
                "categoria": f["tipo"], "descricao": f["descricao"] or "Honorário",
                "valor": f["valor"], "caso": f.get("caso_titulo"),
            })
    for d in despesas:
        if d["pago"] and d.get("data_lancamento"):
            extrato.append({
                "data": str(d["data_lancamento"]), "tipo": "debito",
                "categoria": d.get("categoria") or "despesa",
                "descricao": d["descricao"] or "Despesa", "valor": d["valor"],
                "caso": d.get("caso_titulo"),
            })
    extrato.sort(key=lambda x: x["data"], reverse=True)

    # Contratos (casos com honorário contratual)
    contratos = []
    seen_casos: set = set()
    for f in fees:
        if f["case_id"] and f["case_id"] not in seen_casos and f["tipo"] in ("fixo", "misto", "por_hora"):
            seen_casos.add(f["case_id"])
            contratos.append({
                "case_id": f["case_id"], "caso": f.get("caso_titulo"),
                "numero_interno": f.get("numero_interno"),
                "valor": soma(lambda x, cid=f["case_id"]: x["case_id"] == cid and x["tipo"] in ("fixo", "misto", "por_hora")),
            })

    return {
        "cliente": dict(cli),
        "resumo": {
            "total": total, "recebido": recebido, "pendente": pendente, "atrasado": atrasado,
            "honorarios_contratuais": contratual, "honorarios_exito": exito,
            "exito_recebido": exito_recebido, "custas_despesas": custas,
            "total_despesas": total_despesas, "despesas_pagas": despesas_pagas,
            "reembolsos": reembolsos,
            "resultado_liquido": round(recebido - despesas_pagas, 2),
            "taxa_recebimento": round(recebido / total * 100, 1) if total else 0,
        },
        "contratos": contratos,
        "honorarios": fees,
        "despesas": despesas,
        "extrato": extrato,
    }
