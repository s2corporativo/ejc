"""Endpoint GET /cases/{case_id}/sala-de-guerra e PATCH /notas"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ownership import verificar_acesso_caso
from app.models.user import User
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/cases/{case_id}/sala-de-guerra", tags=["Sala de Guerra"])

_ADV = {"superadmin", "admin", "socio", "advogado", "advogado_auxiliar"}


def _req_adv(cu: User = Depends(get_current_user)) -> User:
    # Estratégia confidencial do caso (pontos fortes/fracos): escrita só pela equipe jurídica.
    if cu.role.value not in _ADV:
        raise HTTPException(403, "Acesso restrito à equipe jurídica")
    return cu


class NotasPayload(BaseModel):
    tese_principal:   Optional[str] = None
    pontos_fortes:    Optional[str] = None
    pontos_fracos:    Optional[str] = None
    observacoes:      Optional[str] = None


@router.get("")
async def sala_de_guerra(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    caso_q = await db.execute(text("""
        SELECT id, numero_interno, titulo, area, status, fase,
               prioridade, numero_processo, tribunal, comarca, vara,
               parte_contraria, valor_causa, tese_principal, pontos_fortes,
               pontos_fracos, observacoes, resultado, licoes_aprendidas,
               created_at, advogado_responsavel_id AS responsavel_id,
               risco_nivel AS nivel_risco, risco_fatores AS fatores_risco,
               indice_risco
        FROM cases WHERE id = :cid AND deleted_at IS NULL
    """), {"cid": case_id})
    caso_row = caso_q.mappings().first()
    if not caso_row:
        raise HTTPException(404, "Caso não encontrado")
    caso = dict(caso_row)

    # Time
    time_q = await db.execute(text("""
        SELECT u.id, u.full_name AS nome, u.role,
               (u.id = c.advogado_responsavel_id) AS responsavel
        FROM cases c
        JOIN users u ON u.id IN (c.advogado_responsavel_id, c.advogado_auxiliar_id)
        WHERE c.id = :cid AND u.deleted_at IS NULL
    """), {"cid": case_id})
    time_rows = [dict(r) for r in time_q.mappings().all()]
    seen: set = set()
    time_dedup = []
    for t in time_rows:
        if t["id"] not in seen:
            seen.add(t["id"])
            time_dedup.append(t)

    # Prazos
    prazos_q = await db.execute(text("""
        SELECT id, titulo AS descricao, data_prazo AS due_date,
               (data_prazo::date - CURRENT_DATE) AS dias_restantes, tipo,
               ((data_prazo::date - CURRENT_DATE) <= 7) AS urgente
        FROM deadlines
        WHERE case_id = :cid AND deleted_at IS NULL
          AND status NOT IN ('concluido','cancelado')
        ORDER BY data_prazo ASC LIMIT 20
    """), {"cid": case_id})
    prazos = []
    for r in prazos_q.mappings().all():
        p = dict(r)
        if p.get("dias_restantes") is not None:
            p["dias_restantes"] = int(p["dias_restantes"])
        p["urgente"] = bool(p.get("urgente"))
        prazos.append(p)

    # Horas (time_entries — minutos)
    horas_q = await db.execute(text("""
        SELECT u.full_name AS usuario,
               COALESCE(SUM(t.minutos), 0) / 60.0 AS horas,
               COALESCE(SUM(t.minutos) FILTER (WHERE t.faturavel), 0) / 60.0 AS horas_faturavel,
               COUNT(*) AS lancamentos
        FROM time_entries t LEFT JOIN users u ON u.id = t.user_id
        WHERE t.case_id = :cid AND t.deleted_at IS NULL
        GROUP BY u.full_name ORDER BY horas DESC
    """), {"cid": case_id})
    horas_rows = []
    for r in horas_q.mappings().all():
        horas_rows.append({
            "usuario": r["usuario"],
            "horas": float(r["horas"] or 0),
            "horas_faturavel": float(r["horas_faturavel"] or 0),
            "lancamentos": int(r["lancamentos"] or 0),
        })
    total_horas = sum(h["horas"] for h in horas_rows)

    # Checklists (case_checklists já agrega total_itens / itens_ok)
    cl_q = await db.execute(text("""
        SELECT cl.id, COALESCE(ct.nome, cl.nome) AS nome,
               cl.total_itens, cl.itens_ok
        FROM case_checklists cl
        LEFT JOIN checklist_templates ct ON ct.id = cl.template_id
        WHERE cl.case_id = :cid
    """), {"cid": case_id})
    checklists = []
    for r in cl_q.mappings().all():
        total = int(r["total_itens"] or 0)
        ok = int(r["itens_ok"] or 0)
        checklists.append({
            "id": r["id"], "nome": r["nome"],
            "total_itens": total, "itens_ok": ok,
            "progresso": round(ok / total * 100) if total else 0,
        })

    # Documentos recentes
    docs_q = await db.execute(text("""
        SELECT id, titulo AS nome, tipo, created_at FROM documents
        WHERE case_id = :cid AND deleted_at IS NULL
        ORDER BY created_at DESC LIMIT 5
    """), {"cid": case_id})
    documentos_recentes = [dict(r) for r in docs_q.mappings().all()]

    # Movimentos recentes (case_movimentos.data_evento)
    movs_q = await db.execute(text("""
        SELECT id, tipo, descricao, data_evento AS data_movimento FROM case_movimentos
        WHERE case_id = :cid ORDER BY data_evento DESC NULLS LAST, created_at DESC LIMIT 10
    """), {"cid": case_id})
    movimentos_recentes = [dict(r) for r in movs_q.mappings().all()]

    # Teses vinculadas (tese_caso_links — tolera ausência de colunas)
    teses_vinculadas = []
    try:
        teses_q = await db.execute(text("""
            SELECT t.id, t.titulo
            FROM teses t JOIN tese_caso_links ct2 ON ct2.tese_id = t.id
            WHERE ct2.case_id = :cid LIMIT 10
        """), {"cid": case_id})
        teses_vinculadas = [dict(r) for r in teses_q.mappings().all()]
    except Exception:
        await db.rollback()

    return {
        "caso": caso,
        "time": time_dedup,
        "prazos": prazos,
        "horas": {"por_pessoa": horas_rows, "total": total_horas},
        "checklists": checklists,
        "documentos_recentes": documentos_recentes,
        "movimentos_recentes": movimentos_recentes,
        "teses_vinculadas": teses_vinculadas,
        "risco": {
            "indice": caso.get("indice_risco"),
            "nivel": caso.get("nivel_risco"),
            "fatores": caso.get("fatores_risco"),
        },
    }


@router.patch("/notas")
async def atualizar_notas(
    case_id: str,
    body: NotasPayload,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_adv),
):
    await verificar_acesso_caso(db, cu, case_id)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        return {"ok": True}
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["cid"] = case_id
    await db.execute(text(f"UPDATE cases SET {set_clause} WHERE id = :cid"), updates)
    await db.commit()
    return {"ok": True}
