"""Dossiê consolidado do cliente — GET /clients/{client_id}/dossie
   Alimenta a página DossieCliente.tsx (cliente, resumo, casos, prazos, documentos).

Degradação POR SEÇÃO (Onda 1 da refatoração): as agregações são independentes e
rodam isoladas. Uma que falhe devolve o valor neutro, entra em
`secoes_indisponiveis` e vai para o log/Sentry — a ficha do cliente ABRE com o
resto. Antes, qualquer erro numa das consultas derrubava o endpoint inteiro em
500 e a tela não abria (achado reproduzido pela auditoria de julho/2026).

O CLIENTE é a única seção não degradável: sem ele não há dossiê, e a resposta
segue 404/403 como antes.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.degradacao import ColetorDeSecoes, executar_secao
from app.core.security import get_current_user
from app.core.ownership import is_gestao
from app.models.user import User

router = APIRouter(prefix="/clients/{client_id}/dossie", tags=["Dossiê do Cliente"])

_HONORARIOS_ZERADOS = {"total": 0.0, "recebido": 0.0, "pendente": 0.0}


async def _carregar_casos(db: AsyncSession, client_id: str) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT id, numero_interno, titulo, area, status, fase, created_at, updated_at
        FROM cases WHERE client_id = :cid AND deleted_at IS NULL
        ORDER BY created_at DESC
    """), {"cid": client_id})).mappings().all()
    return [dict(c) for c in rows]


async def _carregar_prazos(db: AsyncSession, client_id: str) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT d.id, d.case_id, d.titulo AS descricao, d.data_prazo AS due_date,
               (d.data_prazo::date - CURRENT_DATE) AS dias_restantes, d.tipo
        FROM deadlines d JOIN cases c ON c.id = d.case_id
        WHERE c.client_id = :cid AND d.deleted_at IS NULL
          AND d.status NOT IN ('concluido','cancelado')
          AND d.data_prazo::date <= CURRENT_DATE + 60
        ORDER BY d.data_prazo ASC
    """), {"cid": client_id})).mappings().all()
    prazos = []
    for p in rows:
        pd = dict(p)
        dr = pd.get("dias_restantes")
        pd["dias_restantes"] = int(dr) if dr is not None else None
        pd["urgente"] = (dr is not None and dr <= 3)
        prazos.append(pd)
    return prazos


async def _carregar_documentos(db: AsyncSession, client_id: str) -> dict:
    rows = (await db.execute(text("""
        SELECT doc.id, doc.case_id, doc.titulo AS nome, doc.tipo, doc.created_at
        FROM documents doc JOIN cases c ON c.id = doc.case_id
        WHERE c.client_id = :cid AND doc.deleted_at IS NULL
        ORDER BY doc.created_at DESC LIMIT 10
    """), {"cid": client_id})).mappings().all()
    total = (await db.execute(text("""
        SELECT COUNT(*) FROM documents doc JOIN cases c ON c.id = doc.case_id
        WHERE c.client_id = :cid AND doc.deleted_at IS NULL
    """), {"cid": client_id})).scalar() or 0
    return {"recentes": [dict(d) for d in rows], "total": int(total)}


async def _carregar_honorarios(db: AsyncSession, client_id: str) -> dict:
    hon = (await db.execute(text("""
        SELECT COALESCE(SUM(valor),0) AS total,
               COALESCE(SUM(valor) FILTER (WHERE status='pago'),0) AS recebido,
               COALESCE(SUM(valor) FILTER (WHERE status NOT IN ('pago','cancelado')),0) AS pendente
        FROM fees WHERE client_id = :cid AND deleted_at IS NULL
    """), {"cid": client_id})).mappings().first()
    return {
        "total": float(hon["total"]),
        "recebido": float(hon["recebido"]),
        "pendente": float(hon["pendente"]),
    }


@router.get("")
async def dossie_cliente(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    # IDOR: este dossiê agrega TODOS os casos/prazos/documentos/honorários do
    # cliente. Como é uma visão consolidada por cliente (não por caso), filtrar
    # caso a caso não impede o vazamento dos demais casos do mesmo cliente.
    # Escolha: restringir à gestão (sócio+), que já enxerga todos os casos.
    if not is_gestao(cu):
        raise HTTPException(403, "Acesso restrito à gestão (sócio+)")
    cli = (await db.execute(text("""
        SELECT id, nome, email, telefone, whatsapp, tipo, created_at,
               COALESCE(cpf, cnpj) AS cpf_cnpj
        FROM clients WHERE id = :cid AND deleted_at IS NULL
    """), {"cid": client_id})).mappings().first()
    if not cli:
        raise HTTPException(404, "Cliente não encontrado")

    secoes = ColetorDeSecoes("dossie_cliente", db)
    casos = await secoes.tentar("casos", _carregar_casos(db, client_id), padrao=[])
    prazos = await secoes.tentar("prazos", _carregar_prazos(db, client_id), padrao=[])
    docs = await secoes.tentar(
        "documentos", _carregar_documentos(db, client_id), padrao={"recentes": [], "total": 0}
    )
    hon = await secoes.tentar(
        "honorarios", _carregar_honorarios(db, client_id), padrao=dict(_HONORARIOS_ZERADOS)
    )

    def _resumo_casos() -> dict:
        status_breakdown: dict = {}
        area_breakdown: dict = {}
        for c in casos:
            status_breakdown[c["status"]] = status_breakdown.get(c["status"], 0) + 1
            area_breakdown[c["area"]] = area_breakdown.get(c["area"], 0) + 1
        return {
            "casos_ativos": sum(1 for c in casos if c["status"] in ("ativo", "triagem")),
            "casos_encerrados": sum(1 for c in casos if c["status"] in ("encerrado", "arquivado")),
            "status_breakdown": status_breakdown,
            "area_breakdown": area_breakdown,
        }

    resumo_casos = executar_secao(
        secoes, "resumo_casos", _resumo_casos,
        padrao={"casos_ativos": 0, "casos_encerrados": 0, "status_breakdown": {}, "area_breakdown": {}},
    )

    return {
        "cliente": dict(cli),
        "resumo": {
            "total_casos": len(casos),
            "prazos_proximos": len(prazos),
            "docs_total": docs["total"],
            "honorarios_total": hon["total"],
            "honorarios_recebido": hon["recebido"],
            "honorarios_pendente": hon["pendente"],
            **resumo_casos,
        },
        "casos": casos,
        "prazos": prazos,
        "documentos_recentes": docs["recentes"],
        **secoes.rodape(),
    }
