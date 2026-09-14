from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ownership import is_gestao
from app.models.activity_alert import ActivityAlertState
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.user import User

SOURCE_TYPES = {"prazo", "tarefa", "intimacao", "movimentacao"}
ACK_STATES = {"visualizado", "tratado"}
_FINAL_STATUSES = {"concluido", "concluida", "tratada", "cancelado", "cancelada"}
_LEVEL_RANK = {"critico": 0, "alto": 1, "atencao": 2, "info": 3, "normal": 4}


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
    """Documento de caso segue ownership; documento avulso segue o uploader."""
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
    params: dict[str, Any] = {"uid": user.id}
    scope = _activity_scope_sql(user)

    # Somente itens que podem demandar atenção imediata entram neste cockpit.
    # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    atividades = (
        await db.execute(
            text(
                f"""
                SELECT v.id, v.tipo, v.titulo, v.descricao, v.data, v.status,
                       v.case_id, v.responsavel_id, v.prioridade, v.subtipo,
                       c.titulo AS caso_titulo, u.full_name AS responsavel_nome,
                       (v.data::date - CURRENT_DATE) AS dias_restantes,
                       s.estado AS estado_alerta, s.source_fingerprint
                FROM vw_atividades v
                LEFT JOIN cases c ON c.id = v.case_id
                LEFT JOIN users u ON u.id = v.responsavel_id
                LEFT JOIN activity_alert_states s
                  ON s.user_id = :uid AND s.source_type = v.tipo AND s.source_id = v.id
                WHERE v.tipo IN ('prazo','tarefa','intimacao')
                  AND COALESCE(v.status,'') NOT IN ('concluido','concluida','tratada','cancelado','cancelada')
                  AND (
                    (v.tipo = 'prazo' AND v.data::date <= CURRENT_DATE + 3)
                    OR (v.tipo = 'tarefa' AND (
                        v.data::date <= CURRENT_DATE
                        OR COALESCE(v.prioridade,'') IN ('alta','critica')
                    ))
                    OR v.tipo = 'intimacao'
                  )
                  {scope}
                ORDER BY v.data ASC NULLS LAST
                """
            ),
            params,
        )
    ).mappings().all()

    mov_scope = _case_scope_sql(user)
    # Movimentações antigas não podem nascer como alerta retroativo infinito.
    # O cockpit considera a janela recente de sete dias; o histórico completo
    # continua disponível na timeline do caso.
    # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    movimentos = (
        await db.execute(
            text(
                f"""
                SELECT m.id, m.case_id, m.tipo AS tipo_movimento,
                       COALESCE(NULLIF(m.resumo_ia,''), m.descricao) AS descricao,
                       COALESCE(m.data_evento, m.created_at) AS data,
                       c.titulo AS caso_titulo,
                       c.advogado_responsavel_id AS responsavel_id,
                       u.full_name AS responsavel_nome,
                       s.estado AS estado_alerta, s.source_fingerprint
                FROM case_movimentos m
                JOIN cases c ON c.id = m.case_id
                LEFT JOIN users u ON u.id = c.advogado_responsavel_id
                LEFT JOIN activity_alert_states s
                  ON s.user_id = :uid AND s.source_type = 'movimentacao' AND s.source_id = m.id
                WHERE c.deleted_at IS NULL
                  AND COALESCE(m.created_at, m.data_evento) >= NOW() - INTERVAL '7 days'
                  {mov_scope}
                ORDER BY COALESCE(m.data_evento, m.created_at) DESC
                LIMIT 100
                """
            ),
            params,
        )
    ).mappings().all()

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
    params = {"uid": user.id, "sid": source_id, "tipo": source_type}
    if source_type == "movimentacao":
        scope = _case_scope_sql(user)
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        row = (
            await db.execute(
                text(
                    f"""SELECT m.id, m.case_id, m.tipo AS tipo_movimento,
                               COALESCE(NULLIF(m.resumo_ia,''), m.descricao) AS descricao,
                               COALESCE(m.data_evento, m.created_at) AS data,
                               c.titulo AS caso_titulo
                        FROM case_movimentos m
                        JOIN cases c ON c.id = m.case_id
                        WHERE m.id = :sid AND c.deleted_at IS NULL {scope}
                        LIMIT 1"""
                ),
                params,
            )
        ).mappings().first()
        if row:
            data = dict(row)
            data["titulo"] = f"Movimentação: {data.get('caso_titulo') or 'caso'}"
            data["subtipo"] = data.get("tipo_movimento")
        else:
            data = {}
    else:
        scope = _activity_scope_sql(user)
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        row = (
            await db.execute(
                text(
                    f"""SELECT v.id, v.tipo, v.titulo, v.descricao, v.data, v.status,
                               v.case_id, v.prioridade, v.subtipo
                        FROM vw_atividades v
                        WHERE v.id = :sid AND v.tipo = :tipo {scope}
                        LIMIT 1"""
                ),
                params,
            )
        ).mappings().first()
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
    params: dict[str, Any] = {"uid": user.id}
    case_scope = _case_scope_sql(user)
    # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    casos = (
        await db.execute(
            text(
                f"""
                SELECT c.id, c.titulo, c.status::text AS status, c.prioridade::text AS prioridade,
                       c.proxima_acao, c.proxima_acao_prazo
                FROM cases c
                WHERE c.deleted_at IS NULL
                  AND c.status::text NOT IN ('encerrado','arquivado')
                  AND (c.proxima_acao IS NULL OR BTRIM(c.proxima_acao) = ''
                       OR c.proxima_acao_prazo::date <= CURRENT_DATE + 3)
                  {case_scope}
                ORDER BY c.proxima_acao_prazo ASC NULLS FIRST, c.created_at DESC
                LIMIT 15
                """
            ),
            params,
        )
    ).mappings().all()

    doc_scope = _document_scope_sql(user)
    # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    docs = (
        await db.execute(
            text(
                f"""
                SELECT d.id, d.titulo, d.tipo, d.case_id, d.created_at, c.titulo AS caso_titulo
                FROM documents d
                LEFT JOIN cases c ON c.id = d.case_id
                WHERE d.deleted_at IS NULL
                  AND d.created_at >= NOW() - INTERVAL '7 days'
                  {doc_scope}
                ORDER BY d.created_at DESC
                LIMIT 10
                """
            ),
            params,
        )
    ).mappings().all()

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
