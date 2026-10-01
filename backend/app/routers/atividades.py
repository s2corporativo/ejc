"""Fonte única de atividades — lê a VIEW vw_atividades (prazos+tarefas+suspensões+agenda+intimações).
   Substitui a agregação no frontend por uma chamada só.

Tarefa 3 (plano de performance, baseline §10): modo cursor opt-in
(`pagination=cursor`) com página keyset assinada + enriquecimento EM LOTE
por página (hora/local de agenda, confirmado/ciência de prazos) — elimina o
fan-out do frontend (3 chamadas + até 9 páginas de 200 prazos). O caminho
legado (feed completo) permanece inalterado para rollback.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ownership import is_gestao
from app.core.pagination_cursor import CursorInvalido, make_cursor, parse_cursor
from app.models.user import User
from app.schemas.activity_alert import ActivityAlertStateUpdate
from app.services.activity_alert_service import listar_alertas_inteligentes, marcar_estado_alerta

router = APIRouter(prefix="/atividades", tags=["Central de Atividades"])

# Ordenação canônica do modo cursor: data ASC NULLS LAST + (tipo, id) como
# desempate ABSOLUTO — o legado ordena só por data, e atividades com a mesma
# data trocam de posição entre chamadas (paginação instável, baseline §5-E).
_CURSOR_ORDER = "data.asc.nullslast|tipo.asc|id.asc"


def _where_visibilidade(cu: User, params: dict) -> str:
    """Predicado canônico da Central — IDÊNTICO no legado e no cursor.

    Visibilidade: gestão vê tudo. Equipe vê atividade vinculada a caso apenas
    quando atua naquele caso; atividades avulsas seguem o responsável direto.
    Assim, responsavel_id nunca funciona como bypass da carteira de um caso.
    """
    if is_gestao(cu):
        return ""
    params["uid"] = cu.id
    return """ AND (
        (v.case_id IS NULL AND v.responsavel_id = :uid)
        OR EXISTS (
            SELECT 1 FROM cases cc WHERE cc.id = v.case_id
              AND cc.deleted_at IS NULL
              AND (cc.advogado_responsavel_id = :uid OR cc.advogado_auxiliar_id = :uid)
        )
    )"""


def _urg(d):
    if d is None:
        return "normal"
    if d < 0:
        return "vencido"
    if d <= 3:
        return "critico"
    if d <= 7:
        return "atencao"
    return "normal"


def _dias(d):
    # Robusto: aceita int (date - date) ou timedelta (fallback de driver).
    if d is None:
        return None
    if hasattr(d, "days"):
        return d.days
    return int(d)


async def _enriquecer_pagina(db: AsyncSession, data: list[dict]) -> None:
    """Enriquecimento EM LOTE dos itens da página (padrão LIMIT n+1, baseline §10-T3).

    A view não expõe hora/local (agenda) nem confirmado/ciencia_confirmada
    (prazos) — campos dos botões "Confirmar"/"Dar ciência" que o frontend
    hoje busca com até 10 chamadas de 200 prazos + 1 de 500 eventos. Aqui são
    2 queries pontuais restritas aos IDs DA PÁGINA: custo constante e pequeno,
    botões preservados (gate da Tarefa 3).
    """
    prazos_ids = [d["id"] for d in data if d["tipo"] == "prazo"]
    agenda_ids = [d["id"] for d in data if d["tipo"] == "agenda"]
    if prazos_ids:
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        rows = (await db.execute(text(
            "SELECT id, confirmado, ciencia_confirmada FROM deadlines"
            " WHERE id = ANY(:ids)"
        ), {"ids": prazos_ids})).mappings().all()
        mapa = {r["id"]: r for r in rows}
        for d in data:
            if d["tipo"] == "prazo":
                p = mapa.get(d["id"])
                d["confirmado"] = bool(p["confirmado"]) if p else None
                d["ciencia_confirmada"] = bool(p["ciencia_confirmada"]) if p else None
    if agenda_ids:
        rows = (await db.execute(text(
            "SELECT id, hora, local FROM agenda_eventos WHERE id = ANY(:ids)"
        ), {"ids": agenda_ids})).mappings().all()
        mapa = {r["id"]: r for r in rows}
        for d in data:
            if d["tipo"] == "agenda":
                a = mapa.get(d["id"])
                d["hora"] = a["hora"] if a else None
                d["local"] = a["local"] if a else None


@router.get("")
async def listar_atividades(
    apenas_pendentes: bool = Query(True),
    # Opt-in (Tarefa 3): `pagination=cursor` pagina keyset com enriquecimento
    # em lote. Default preserva o feed completo (contrato atual/rollback).
    pagination: str = Query("offset", pattern="^(offset|cursor)$"),
    cursor: Optional[str] = Query(None),
    page_size: int = Query(50, ge=1, le=200),
    case_id: Optional[str] = Query(None, description="Escopo opcional por caso"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    where = "WHERE 1=1"
    params: dict = {}
    if apenas_pendentes:
        where += " AND COALESCE(v.status,'') NOT IN ('concluido','concluida','tratada','cancelado')"
    if case_id:
        where += " AND v.case_id = :case_id"
        params["case_id"] = case_id
    where += _where_visibilidade(cu, params)

    if pagination == "cursor":
        filtros = {
            "apenas_pendentes": apenas_pendentes,
            "case_id": case_id,
        }
        last: list | None = None
        if cursor:
            try:
                last = parse_cursor(cursor, "atividades", cu, filtros, _CURSOR_ORDER)
            except CursorInvalido as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            if len(last) != 3:
                raise HTTPException(
                    status_code=409,
                    detail="cursor incompatível com a ordenação atual",
                )
            # Coerção ISO → date: a comparação SQL exige tipos nativos
            # (asyncpg não compara coluna date com texto cru). Ruim = 409.
            try:
                last[0] = date.fromisoformat(last[0]) if last[0] else None
            except (ValueError, TypeError) as exc:
                raise HTTPException(
                    status_code=409,
                    detail="cursor com chave de continuação inválida",
                ) from exc
        ordem = "ORDER BY v.data ASC NULLS LAST, v.tipo ASC, v.id ASC"
        if last is not None:
            last_d, last_t, last_id = last
            params["ld"] = last_d
            params["lt"] = last_t
            params["lid"] = last_id
            # Keyset com NULLS LAST por ramos (NULL não compara em tupla):
            # após last com data → restam NULLs (cauda) e datas maiores;
            # após last NULL → só NULLs por (tipo, id).
            if last_d is None:
                where += """ AND v.data IS NULL
                    AND (v.tipo > :lt OR (v.tipo = :lt AND v.id > :lid))"""
            else:
                where += """ AND (v.data IS NULL OR v.data > :ld
                    OR (v.data = :ld AND (v.tipo > :lt
                        OR (v.tipo = :lt AND v.id > :lid))))"""
        # page_size+1: has_more sem count(*) sobre a UNION ALL de 5 tabelas.
        sql = f"""
        SELECT v.id, v.tipo, v.titulo, v.descricao, v.data, v.status,
               v.case_id, v.responsavel_id, v.prioridade, v.subtipo,
               c.titulo AS caso_titulo,
               (v.data::date - CURRENT_DATE) AS dias_restantes
        FROM vw_atividades v
        LEFT JOIN cases c ON c.id = v.case_id
        {where}
        {ordem}
        LIMIT :ps
        """
        params["ps"] = page_size + 1
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        rows = (await db.execute(text(sql), params)).mappings().all()
        tem_mais = len(rows) > page_size
        rows = rows[:page_size]
        data = [_item(r) for r in rows]
        await _enriquecer_pagina(db, data)
        next_cursor = None
        if tem_mais and rows:
            ultimo = rows[-1]
            next_cursor = make_cursor(
                "atividades", cu, filtros, _CURSOR_ORDER,
                [
                    ultimo["data"].isoformat() if ultimo["data"] else None,
                    ultimo["tipo"],
                    ultimo["id"],
                ],
            )
        return {
            "data": data,
            "page_size": page_size,
            "has_more": tem_mais,
            "next_cursor": next_cursor,
        }

    # ── Legado (inalterado): feed completo ordenado por data ────────────
    # (v.data::date - CURRENT_DATE) força diferença em DIAS inteiros mesmo se a
    # coluna for TIMESTAMP (senão vem interval → int() estoura 500).
    # SQL literal com bind params; a regra marca todo text(), sem olhar
    # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
    # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    rows = (await db.execute(text(f"""
        SELECT v.id, v.tipo, v.titulo, v.descricao, v.data, v.status,
               v.case_id, v.responsavel_id, v.prioridade, v.subtipo,
               c.titulo AS caso_titulo,
               (v.data::date - CURRENT_DATE) AS dias_restantes
        FROM vw_atividades v
        LEFT JOIN cases c ON c.id = v.case_id
        {where}
        ORDER BY v.data ASC NULLS LAST
    """), params)).mappings().all()

    return {"data": [_item(r) for r in rows]}


def _item(r) -> dict:
    di = _dias(r["dias_restantes"])
    return {
        "id": r["id"], "tipo": r["tipo"], "titulo": r["titulo"],
        "descricao": r["descricao"], "date": str(r["data"]) if r["data"] else None,
        "status": r["status"], "case_id": r["case_id"], "caso_titulo": r["caso_titulo"],
        "responsavel_id": r["responsavel_id"], "prioridade": r["prioridade"],
        "subtipo": r["subtipo"],
        "dias_restantes": di, "urgencia": _urg(di),
    }


@router.get("/resumo")
async def resumo_atividades(
    case_id: Optional[str] = Query(None, description="Escopo por caso (contexto da Central)"),
    apenas_pendentes: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Contadores de urgência da Central — fonte única server-side (Tarefa 3).

    Semântica anti-auto-zerar preservada (Central 1452-1478): conta TODO o
    conjunto visível (com escopo de caso quando informado) e NÃO aplica os
    filtros de tipo/urgência/situação da UI — os cards são os próprios botões
    de filtro. Mesmo predicado de visibilidade do feed: cliente_externo já é
    barrado pelo AuthMiddleware; equipe só conta a própria carteira.
    """
    where = "WHERE 1=1"
    params: dict = {}
    if apenas_pendentes:
        where += " AND COALESCE(v.status,'') NOT IN ('concluido','concluida','tratada','cancelado')"
    if case_id:
        where += " AND v.case_id = :case_id"
        params["case_id"] = case_id
    where += _where_visibilidade(cu, params)
    # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    r = (await db.execute(text(f"""
        SELECT
          COUNT(*) FILTER (WHERE dr < 0)              AS vencido,
          COUNT(*) FILTER (WHERE dr BETWEEN 0 AND 3)  AS critico,
          COUNT(*) FILTER (WHERE dr BETWEEN 4 AND 7)  AS atencao,
          COUNT(*) FILTER (WHERE dr > 7 OR dr IS NULL) AS normal,
          COUNT(*)                                    AS pendentes
        FROM (
          SELECT (v.data::date - CURRENT_DATE) AS dr
          FROM vw_atividades v
          {where}
        ) t
    """), params)).mappings().one()
    return {
        "vencido": r["vencido"],
        "critico": r["critico"],
        "atencao": r["atencao"],
        "normal": r["normal"],
        "pendentes": r["pendentes"],
    }


@router.get("/alertas-inteligentes")
async def alertas_inteligentes(
    limit_per_type: int = Query(5, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    return await listar_alertas_inteligentes(
        db, cu, limit_per_type=limit_per_type
    )


@router.patch("/alertas/{source_type}/{source_id}")
async def atualizar_estado_alerta(
    source_type: str,
    source_id: str,
    payload: ActivityAlertStateUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    return await marcar_estado_alerta(
        db, cu, source_type, source_id, payload.estado
    )
