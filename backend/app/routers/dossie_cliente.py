"""Dossiê consolidado do cliente — GET /clients/{client_id}/dossie
   Alimenta a página DossieCliente.tsx (cliente, resumo, casos, prazos, documentos)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
# Reusa o MESMO gate de PII/financeiro do cliente já aplicado ao relatório
# financeiro (gestão/financeiro/advogado) — o dossiê expõe a mesma classe de
# dado (CPF/CNPJ + casos + honorários) e antes não tinha gate forte (laudo Fase 4).
from app.routers.relatorio_cliente import _req_fin_adv

router = APIRouter(
    prefix="/clients/{client_id}/dossie",
    tags=["Dossiê do Cliente"],
    dependencies=[Depends(_req_fin_adv)],
)


@router.get("")
async def dossie_cliente(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    cli = (await db.execute(text("""
        SELECT id, nome, email, telefone, whatsapp, tipo, created_at,
               COALESCE(cpf, cnpj) AS cpf_cnpj
        FROM clients WHERE id = :cid AND deleted_at IS NULL
    """), {"cid": client_id})).mappings().first()
    if not cli:
        raise HTTPException(404, "Cliente não encontrado")

    # Casos
    casos_rows = (await db.execute(text("""
        SELECT id, numero_interno, titulo, area, status, fase, created_at, updated_at
        FROM cases WHERE client_id = :cid AND deleted_at IS NULL
        ORDER BY created_at DESC
    """), {"cid": client_id})).mappings().all()
    casos = [dict(c) for c in casos_rows]

    status_breakdown: dict = {}
    area_breakdown: dict = {}
    for c in casos:
        status_breakdown[c["status"]] = status_breakdown.get(c["status"], 0) + 1
        area_breakdown[c["area"]] = area_breakdown.get(c["area"], 0) + 1
    ativos = sum(1 for c in casos if c["status"] in ("ativo", "triagem"))
    encerrados = sum(1 for c in casos if c["status"] in ("encerrado", "arquivado"))

    # Prazos próximos (60 dias) dos casos do cliente
    prazos_rows = (await db.execute(text("""
        SELECT d.id, d.case_id, d.titulo AS descricao, d.data_prazo AS due_date,
               (d.data_prazo::date - CURRENT_DATE) AS dias_restantes, d.tipo
        FROM deadlines d JOIN cases c ON c.id = d.case_id
        WHERE c.client_id = :cid AND d.deleted_at IS NULL
          AND d.status NOT IN ('concluido','cancelado')
          AND d.data_prazo::date <= CURRENT_DATE + 60
        ORDER BY d.data_prazo ASC
    """), {"cid": client_id})).mappings().all()
    prazos = []
    for p in prazos_rows:
        pd = dict(p)
        dr = pd.get("dias_restantes")
        pd["dias_restantes"] = int(dr) if dr is not None else None
        pd["urgente"] = (dr is not None and dr <= 3)
        prazos.append(pd)

    # Documentos recentes
    docs_rows = (await db.execute(text("""
        SELECT doc.id, doc.case_id, doc.titulo AS nome, doc.tipo, doc.created_at
        FROM documents doc JOIN cases c ON c.id = doc.case_id
        WHERE c.client_id = :cid AND doc.deleted_at IS NULL
        ORDER BY doc.created_at DESC LIMIT 10
    """), {"cid": client_id})).mappings().all()
    documentos_recentes = [dict(d) for d in docs_rows]
    docs_total = (await db.execute(text("""
        SELECT COUNT(*) FROM documents doc JOIN cases c ON c.id = doc.case_id
        WHERE c.client_id = :cid AND doc.deleted_at IS NULL
    """), {"cid": client_id})).scalar() or 0

    # Honorários
    hon = (await db.execute(text("""
        SELECT COALESCE(SUM(valor),0) AS total,
               COALESCE(SUM(valor) FILTER (WHERE status='pago'),0) AS recebido,
               COALESCE(SUM(valor) FILTER (WHERE status NOT IN ('pago','cancelado')),0) AS pendente
        FROM fees WHERE client_id = :cid AND deleted_at IS NULL
    """), {"cid": client_id})).mappings().first()

    return {
        "cliente": dict(cli),
        "resumo": {
            "total_casos": len(casos),
            "casos_ativos": ativos,
            "casos_encerrados": encerrados,
            "prazos_proximos": len(prazos),
            "docs_total": int(docs_total),
            "honorarios_total": float(hon["total"]),
            "honorarios_recebido": float(hon["recebido"]),
            "honorarios_pendente": float(hon["pendente"]),
            "status_breakdown": status_breakdown,
            "area_breakdown": area_breakdown,
        },
        "casos": casos,
        "prazos": prazos,
        "documentos_recentes": documentos_recentes,
    }
