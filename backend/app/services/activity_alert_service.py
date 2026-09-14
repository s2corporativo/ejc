from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import (
    Date,
    DateTime,
    String,
    and_,
    cast,
    column,
    exists,
    func,
    or_,
    select,
    table,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.ownership import is_gestao
from app.models.activity_alert import ActivityAlertState
from app.models.audit_log import criar_audit_log
from app.models.case import Case, CaseMovimento
from app.models.document import Document
from app.models.user import User

SOURCE_TYPES = {"prazo", "tarefa", "intimacao", "movimentacao"}
ACK_STATES = {"visualizado", "tratado"}
_FINAL_STATUSES = {"concluido", "concluida", "tratada", "cancelado", "cancelada"}
_LEVEL_RANK = {"critico": 0, "alto": 1, "atencao": 2, "info": 3, "normal": 4}

# VIEW sem model ORM próprio. ``table()/column()`` permite consultar a view com
# SQLAlchemy Core parametrizado, sem SQL textual/f-string.
VW_ATIVIDADES = table(
    "vw_atividades",
    column("id", String),
    column("tipo", String),
    column("titulo", String),
    column("descricao", String),
    column("data", DateTime(timezone=True)),
    column("status", String),
    column("case_id", String),
    column("responsavel_id", String),
    column("prioridade", String),
    column("subtipo", String),
)


def _role_value(user: User) -> str:
    return getattr(user.role, "value", str(user.role))


def _activity_scope_sql(user: User) -> str:
    """Escopo fail-closed: atividade de caso segue ownership; avulsa segue responsável."""
    if is_gestao(user):
        return ""
    return """ AND (
        (v.case_id IS NULL AND v.responsavel_id = :uid)
        OR EXISTS (
            SELECT 1 FROM cases cc WHERE cc.id = v.case_id
            AND cc.deleted_at IS NULL
            AND (cc.advogado_responsavel_id = :uid OR cc.advogado_auxiliar_id = :uid)
        )
    )"""


def _case_scope_sql(user: User) -> str:
    """Casos sem ownership explícito não são visíveis a usuário não gestor."""
    if is_gestao(user):
        return ""
    return """ AND (
        c.advogado_responsavel_id = :uid OR c.advogado_auxiliar_id = :uid
    )"""


def _document_scope_sql(user: User) -> str:
    """Representação legada do escopo, mantida apenas para testes de contrato."""
    if is_gestao(user):
        return ""
    return """ AND (
        (d.case_id IS NULL AND d.uploaded_by = :uid)
        OR EXISTS (
            SELECT 1 FROM cases cc WHERE cc.id = d.case_id
            AND cc.deleted_at IS NULL
            AND (cc.advogado_responsavel_id = :uid OR cc.advogado_auxiliar_id = :uid)
        )
    )"""


def _activity_scope_clause(user: User):
    if is_gestao(user):
        return None
    v = VW_ATIVIDADES.c
    cc = aliased(Case)
    return or_(
        and_(v.case_id.is_(None), v.responsavel_id == user.id),
        exists(
            select(1).select_from(cc).where(
                cc.id == v.case_id,
                cc.deleted_at.is_(None),
                or_(
                    cc.advogado_responsavel_id == user.id,
                    cc.advogado_auxiliar_id == user.id,
                ),
            )
        ),
    )


def _case_scope_clause(user: User):
    if is_gestao(user):
        return None
    return or_(
        Case.advogado_responsavel_id == user.id,
        Case.advogado_auxiliar_id == user.id,
    )


def _document_scope_clause(user: User):
    if is_gestao(user):
        return None
    cc = aliased(Case)
    return or_(
        and_(Document.case_id.is_(None), Document.uploaded_by == user.id),
        exists(
            select(1).select_from(cc).where(
                cc.id == Document.case_id,
                cc.deleted_at.is_(None),
                or_(
                    cc.advogado_responsavel_id == user.id,
                    cc.advogado_auxiliar_id == user.id,
                ),
            )
        ),
    )


def nivel_alerta(
    source_type: str,
    dias_restantes: int | None,
    prioridade: str | None = None,
    subtipo: str | None = None,
) -> str:
    """Classificação operacional determinística; não é inferência de IA."""
    prioridade = (prioridade or "").lower()
    subtipo = (subtipo or "").lower()
    if source_type == "prazo":
        if dias_restantes is not None and dias_restantes < 0:
            return "critico"
        if dias_restantes is not None and dias_restantes <= 1:
            return "alto"
        if dias_restantes is not None and dias_restantes <= 3:
            return "atencao"
        return "normal"
    if source_type == "tarefa":
        if dias_restantes is not None and dias_restantes < 0:
            return "critico"
        if dias_restantes == 0:
            return "alto"
        if prioridade in {"critica", "alta"}:
            return "atencao"
        return "normal"
    if source_type == "intimacao":
        return "alto"
    if source_type == "movimentacao":
        if any(chave in subtipo for chave in ("decis", "senten", "intim", "audien")):
            return "alto"
        return "info"
    return "normal"


def _link_alerta(source_type: str, case_id: str | None) -> str:
    if source_type == "movimentacao":
        return f"/casos/{case_id}" if case_id else "/casos"
    base = f"/atividades?tipo={source_type}"
    return f"{base}&caso={case_id}" if case_id else base


def _fingerprint(source_type: str, row: dict[str, Any]) -> str:
    payload = {
        "source_type": source_type,
        "titulo": row.get("titulo"),
        "descricao": row.get("descricao"),
        "data": str(row.get("data") or ""),
        "status": row.get("status"),
        "prioridade": row.get("prioridade"),
        "subtipo": row.get("subtipo") or row.get("tipo_movimento"),
        "case_id": row.get("case_id"),
    }
    bruto = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def _estado(row: dict[str, Any], fingerprint: str) -> str:
    if not row.get("estado_alerta"):
        return "novo"
    if str(row.get("source_fingerprint") or "") != fingerprint:
        return "novo"
    return str(row["estado_alerta"])


def _normalizar_item(row: dict[str, Any], source_type: str) -> dict[str, Any]:
    dias = row.get("dias_restantes")
    if dias is not None:
        dias = int(dias.days if hasattr(dias, "days") else dias)
    nivel = nivel_alerta(
        source_type,
        dias,
        prioridade=row.get("prioridade"),
        subtipo=row.get("subtipo") or row.get("tipo_movimento"),
    )
    fingerprint = _fingerprint(source_type, row)
    estado = _estado(row, fingerprint)
    return {
        "source_type": source_type,
        "source_id": str(row["id"]),
        "titulo": row.get("titulo") or "Atividade sem título",
        "descricao": row.get("descricao"),
        "data": str(row.get("data")) if row.get("data") else None,
        "case_id": row.get("case_id"),
        "caso_titulo": row.get("caso_titulo"),
        "responsavel_id": row.get("responsavel_id"),
        "responsavel_nome": row.get("responsavel_nome"),
        "prioridade": row.get("prioridade"),
        "dias_restantes": dias,
        "nivel_alerta": nivel,
        "estado_alerta": estado,
        "link": _link_alerta(source_type, row.get("case_id")),
    }


async def listar_alertas_inteligentes(
    db: AsyncSession,
    user: User,
    *,
    limit_per_type: int = 5,
) -> dict[str, Any]:
    """Retorna apenas alertas acionáveis da carteira permitida ao usuário."""
    v = VW_ATIVIDADES.c
    stmt_atividades = (
        select(
            v.id,
            v.tipo,
            v.titulo,
            v.descricao,
            v.data,
            v.status,
            v.case_id,
            v.responsavel_id,
            v.prioridade,
            v.subtipo,
            Case.titulo.label("caso_titulo"),
            User.full_name.label("responsavel_nome"),
            (cast(v.data, Date) - func.current_date()).label("dias_restantes"),
            ActivityAlertState.estado.label("estado_alerta"),
            ActivityAlertState.source_fingerprint,
        )
        .select_from(VW_ATIVIDADES)
        .outerjoin(Case, Case.id == v.case_id)
        .outerjoin(User, User.id == v.responsavel_id)
        .outerjoin(
            ActivityAlertState,
            and_(
                ActivityAlertState.user_id == user.id,
                ActivityAlertState.source_type == v.tipo,
                ActivityAlertState.source_id == v.id,
            ),
        )
        .where(
            v.tipo.in_(("prazo", "tarefa", "intimacao")),
            func.coalesce(v.status, "").notin_(_FINAL_STATUSES),
            or_(
                and_(v.tipo == "prazo", cast(v.data, Date) <= func.current_date() + 3),
                and_(
                    v.tipo == "tarefa",
                    or_(
                        cast(v.data, Date) <= func.current_date(),
                        func.coalesce(v.prioridade, "").in_(("alta", "critica")),
                    ),
                ),
                v.tipo == "intimacao",
            ),
        )
        .order_by(v.data.asc().nullslast())
    )
    activity_scope = _activity_scope_clause(user)
    if activity_scope is not None:
        stmt_atividades = stmt_atividades.where(activity_scope)
    atividades = (await db.execute(stmt_atividades)).mappings().all()

    stmt_movimentos = (
        select(
            CaseMovimento.id,
            CaseMovimento.case_id,
            CaseMovimento.tipo.label("tipo_movimento"),
            func.coalesce(
                func.nullif(CaseMovimento.resumo_ia, ""),
                CaseMovimento.descricao,
            ).label("descricao"),
            func.coalesce(CaseMovimento.data_evento, CaseMovimento.created_at).label("data"),
            Case.titulo.label("caso_titulo"),
            Case.advogado_responsavel_id.label("responsavel_id"),
            User.full_name.label("responsavel_nome"),
            ActivityAlertState.estado.label("estado_alerta"),
            ActivityAlertState.source_fingerprint,
        )
        .select_from(CaseMovimento)
        .join(Case, Case.id == CaseMovimento.case_id)
        .outerjoin(User, User.id == Case.advogado_responsavel_id)
        .outerjoin(
            ActivityAlertState,
            and_(
                ActivityAlertState.user_id == user.id,
                ActivityAlertState.source_type == "movimentacao",
                ActivityAlertState.source_id == CaseMovimento.id,
            ),
        )
        .where(
            Case.deleted_at.is_(None),
            func.coalesce(CaseMovimento.created_at, CaseMovimento.data_evento)
            >= func.now() - timedelta(days=7),
        )
        .order_by(
            func.coalesce(CaseMovimento.data_evento, CaseMovimento.created_at).desc()
        )
        .limit(100)
    )
    case_scope = _case_scope_clause(user)
    if case_scope is not None:
        stmt_movimentos = stmt_movimentos.where(case_scope)
    movimentos = (await db.execute(stmt_movimentos)).mappings().all()

    por_tipo: dict[str, list[dict[str, Any]]] = {tipo: [] for tipo in SOURCE_TYPES}
    for row in atividades:
        item = _normalizar_item(dict(row), str(row["tipo"]))
        por_tipo[item["source_type"]].append(item)
    for row in movimentos:
        r = dict(row)
        r["titulo"] = f"Movimentação: {r.get('caso_titulo') or 'caso'}"
        r["subtipo"] = r.get("tipo_movimento")
        r["dias_restantes"] = None
        item = _normalizar_item(r, "movimentacao")
        por_tipo["movimentacao"].append(item)

    resumo: dict[str, dict[str, int]] = {}
    saida: dict[str, list[dict[str, Any]]] = {}
    for tipo, itens in por_tipo.items():
        ativos = [i for i in itens if i["estado_alerta"] != "tratado"]
        ativos.sort(
            key=lambda i: (
                _LEVEL_RANK.get(i["nivel_alerta"], 9),
                i["dias_restantes"] if i["dias_restantes"] is not None else 9999,
                i["data"] or "9999",
            )
        )
        novos = [i for i in ativos if i["estado_alerta"] == "novo"]
        resumo[tipo] = {
            "ativos": len(ativos),
            "novos": len(novos),
            "criticos": sum(i["nivel_alerta"] == "critico" for i in ativos),
            "altos": sum(i["nivel_alerta"] == "alto" for i in ativos),
        }
        saida[tipo] = ativos[:limit_per_type]

    return {"resumo": resumo, "itens": saida}


async def _validar_fonte_acessivel(
    db: AsyncSession, user: User, source_type: str, source_id: str
) -> tuple[dict[str, Any], str]:
    if source_type == "movimentacao":
        stmt = (
            select(
                CaseMovimento.id,
                CaseMovimento.case_id,
                CaseMovimento.tipo.label("tipo_movimento"),
                func.coalesce(
                    func.nullif(CaseMovimento.resumo_ia, ""),
                    CaseMovimento.descricao,
                ).label("descricao"),
                func.coalesce(CaseMovimento.data_evento, CaseMovimento.created_at).label("data"),
                Case.titulo.label("caso_titulo"),
            )
            .select_from(CaseMovimento)
            .join(Case, Case.id == CaseMovimento.case_id)
            .where(
                CaseMovimento.id == source_id,
                Case.deleted_at.is_(None),
            )
            .limit(1)
        )
        scope = _case_scope_clause(user)
        if scope is not None:
            stmt = stmt.where(scope)
        row = (await db.execute(stmt)).mappings().first()
        if row:
            data = dict(row)
            data["titulo"] = f"Movimentação: {data.get('caso_titulo') or 'caso'}"
            data["subtipo"] = data.get("tipo_movimento")
        else:
            data = {}
    else:
        v = VW_ATIVIDADES.c
        stmt = (
            select(
                v.id,
                v.tipo,
                v.titulo,
                v.descricao,
                v.data,
                v.status,
                v.case_id,
                v.prioridade,
                v.subtipo,
            )
            .select_from(VW_ATIVIDADES)
            .where(v.id == source_id, v.tipo == source_type)
            .limit(1)
        )
        scope = _activity_scope_clause(user)
        if scope is not None:
            stmt = stmt.where(scope)
        row = (await db.execute(stmt)).mappings().first()
        data = dict(row) if row else {}
    if not data:
        raise HTTPException(status_code=404, detail="Alerta não encontrado")
    return data, _fingerprint(source_type, data)


async def marcar_estado_alerta(
    db: AsyncSession,
    user: User,
    source_type: str,
    source_id: str,
    estado: str,
) -> dict[str, Any]:
    if source_type not in SOURCE_TYPES or estado not in ACK_STATES:
        raise HTTPException(status_code=422, detail="Estado ou origem de alerta inválidos")
    _, source_fingerprint = await _validar_fonte_acessivel(
        db, user, source_type, source_id
    )

    atual = (
        await db.execute(
            select(ActivityAlertState)
            .where(
                ActivityAlertState.user_id == user.id,
                ActivityAlertState.source_type == source_type,
                ActivityAlertState.source_id == source_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    mesma_versao = bool(
        atual and atual.source_fingerprint == source_fingerprint
    )
    antes = atual.estado if atual and mesma_versao else "novo"
    # Estado é monotônico dentro da MESMA versão da origem. Uma alteração
    # material gera novo fingerprint e reabre o alerta como "novo".
    destino = "tratado" if antes == "tratado" or estado == "tratado" else "visualizado"
    agora = datetime.now(timezone.utc)
    if atual is None:
        atual = ActivityAlertState(
            id=str(uuid4()),
            user_id=user.id,
            source_type=source_type,
            source_id=source_id,
            estado=destino,
            source_fingerprint=source_fingerprint,
            visualizado_em=agora,
            tratado_em=agora if destino == "tratado" else None,
        )
        db.add(atual)
    else:
        if not mesma_versao:
            atual.visualizado_em = agora
            atual.tratado_em = agora if destino == "tratado" else None
        atual.estado = destino
        atual.source_fingerprint = source_fingerprint
        atual.visualizado_em = atual.visualizado_em or agora
        if destino == "tratado":
            atual.tratado_em = atual.tratado_em or agora

    if antes != destino:
        await criar_audit_log(
            db,
            user_id=user.id,
            user_role=_role_value(user),
            acao="UPDATE",
            entidade="activity_alert_state",
            registro_id=source_id,
            dados_antes={"source_type": source_type, "estado": antes},
            dados_depois={"source_type": source_type, "estado": destino},
        )
    await db.commit()
    await db.refresh(atual)
    return {
        "source_type": source_type,
        "source_id": source_id,
        "estado": atual.estado,
        "visualizado_em": atual.visualizado_em,
        "tratado_em": atual.tratado_em,
    }


async def montar_contexto_operacional_ejc(db: AsyncSession, user: User) -> str:
    """Contexto mínimo, autorizado e bounded para o modo Contexto EJC."""
    alertas = await listar_alertas_inteligentes(db, user, limit_per_type=5)
    stmt_casos = (
        select(
            Case.id,
            Case.titulo,
            cast(Case.status, String).label("status"),
            cast(Case.prioridade, String).label("prioridade"),
            Case.proxima_acao,
            Case.proxima_acao_prazo,
        )
        .where(
            Case.deleted_at.is_(None),
            cast(Case.status, String).notin_(("encerrado", "arquivado")),
            or_(
                Case.proxima_acao.is_(None),
                func.btrim(Case.proxima_acao) == "",
                cast(Case.proxima_acao_prazo, Date) <= func.current_date() + 3,
            ),
        )
        .order_by(Case.proxima_acao_prazo.asc().nullsfirst(), Case.created_at.desc())
        .limit(15)
    )
    case_scope = _case_scope_clause(user)
    if case_scope is not None:
        stmt_casos = stmt_casos.where(case_scope)
    casos = (await db.execute(stmt_casos)).mappings().all()

    stmt_docs = (
        select(
            Document.id,
            Document.titulo,
            Document.tipo,
            Document.case_id,
            Document.created_at,
            Case.titulo.label("caso_titulo"),
        )
        .select_from(Document)
        .outerjoin(Case, Case.id == Document.case_id)
        .where(
            Document.deleted_at.is_(None),
            Document.created_at >= func.now() - timedelta(days=7),
        )
        .order_by(Document.created_at.desc())
        .limit(10)
    )
    doc_scope = _document_scope_clause(user)
    if doc_scope is not None:
        stmt_docs = stmt_docs.where(doc_scope)
    docs = (await db.execute(stmt_docs)).mappings().all()

    casos_lista = [dict(r) for r in casos]
    docs_lista = [dict(r) for r in docs]
    case_ids = {
        str(item.get("case_id"))
        for grupo in (alertas.get("itens") or {}).values()
        for item in grupo
        if item.get("case_id")
    }
    case_ids.update(str(item["id"]) for item in casos_lista if item.get("id"))
    case_ids.update(str(item["case_id"]) for item in docs_lista if item.get("case_id"))
    sigilosos: set[str] = set()
    if case_ids:
        sigilosos = {
            str(row[0])
            for row in (
                await db.execute(
                    select(Case.id).where(
                        Case.id.in_(case_ids), Case.sigilo_reforcado.is_(True)
                    )
                )
            ).all()
        }

    alertas_minimos: dict[str, list[dict[str, Any]]] = {}
    for tipo, grupo in (alertas.get("itens") or {}).items():
        itens: list[dict[str, Any]] = []
        for item in grupo:
            sigilo = str(item.get("case_id") or "") in sigilosos
            itens.append({
                "tipo": tipo,
                "titulo": "Alerta em caso com sigilo reforçado" if sigilo else item.get("titulo"),
                "caso": "Caso com sigilo reforçado" if sigilo else item.get("caso_titulo"),
                "data": item.get("data"),
                "nivel": item.get("nivel_alerta"),
                "estado": item.get("estado_alerta"),
            })
        alertas_minimos[tipo] = itens

    for item in casos_lista:
        if str(item.get("id") or "") in sigilosos:
            item["titulo"] = "Caso com sigilo reforçado"
            item["proxima_acao"] = None
    for item in docs_lista:
        if str(item.get("case_id") or "") in sigilosos:
            item["titulo"] = "Documento de caso com sigilo reforçado"
            item["caso_titulo"] = "Caso com sigilo reforçado"

    payload = {
        "resumo_alertas": alertas.get("resumo") or {},
        "alertas": alertas_minimos,
        "casos_que_exigem_proxima_acao": casos_lista,
        "documentos_recentes": docs_lista,
        "nota_sigilo": (
            "Casos com sigilo reforçado foram redigidos; detalhes exigem abertura "
            "do caso no EJC e não são enviados neste contexto."
        ),
    }
    return json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))[:45_000]
