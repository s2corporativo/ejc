"""Agenda de eventos — reuniões, compromissos, diligências, audiências internas.
   Complementa prazos/tarefas/suspensões/intimações na Central de Atividades.
"""
from uuid import uuid4
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ownership import verificar_acesso_caso
from app.models.user import User

router = APIRouter(prefix="/agenda-eventos", tags=["Agenda de Eventos"])

TIPOS_VALIDOS = {"reuniao", "compromisso", "diligencia", "audiencia", "outro"}


class EventoIn(BaseModel):
    titulo: str
    tipo: str = "compromisso"
    data_evento: date
    hora: Optional[str] = None
    local: Optional[str] = None
    descricao: Optional[str] = None
    case_id: Optional[str] = None
    responsavel_id: Optional[str] = None


class EventoPatch(BaseModel):
    titulo: Optional[str] = None
    tipo: Optional[str] = None
    data_evento: Optional[date] = None
    hora: Optional[str] = None
    local: Optional[str] = None
    descricao: Optional[str] = None
    concluido: Optional[bool] = None


async def _buscar_conflitos(
    db: AsyncSession,
    *,
    responsavel_id: Optional[str],
    data_evento: Optional[date],
    hora: Optional[str],
    exclude_id: Optional[str] = None,
) -> list[dict]:
    """Double-booking: outros eventos NÃO concluídos do MESMO responsável na
    MESMA data e MESMA hora (horário de início exato).

    Como o schema não tem campo de duração (`hora` é VARCHAR livre), o critério
    possível é a coincidência de horário de início — mesma data + mesma string
    de hora (normalizada por trim). Evento sem hora (None/"") NÃO colide por
    horário e retorna lista vazia. `exclude_id` evita o próprio evento colidir
    consigo mesmo na edição.
    """
    if not responsavel_id or not data_evento or not hora or not hora.strip():
        return []
    rows = (await db.execute(text("""
        SELECT e.id, e.titulo, e.tipo, e.data_evento, e.hora, e.local
        FROM agenda_eventos e
        WHERE e.deleted_at IS NULL AND e.concluido = false
          AND e.responsavel_id = :resp
          AND e.data_evento = :d
          AND e.hora IS NOT NULL AND btrim(e.hora) = :h
          AND (:exc IS NULL OR e.id <> :exc)
        ORDER BY e.hora
    """), {"resp": responsavel_id, "d": data_evento,
           "h": hora.strip(), "exc": exclude_id})).mappings().all()
    return [dict(r) for r in rows]


@router.get("/")
async def listar(
    page_size: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    rows = (await db.execute(text("""
        SELECT e.id, e.titulo, e.tipo, e.data_evento, e.hora, e.local, e.descricao,
               e.case_id, e.responsavel_id, e.concluido,
               c.titulo AS caso_titulo
        FROM agenda_eventos e
        LEFT JOIN cases c ON c.id = e.case_id
        WHERE e.deleted_at IS NULL
        ORDER BY e.data_evento ASC, e.hora ASC NULLS LAST
        LIMIT :ps
    """), {"ps": page_size})).mappings().all()
    return {"data": [dict(r) for r in rows]}


@router.post("/", status_code=201)
async def criar(
    body: EventoIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if body.tipo not in TIPOS_VALIDOS:
        raise HTTPException(422, f"Tipo inválido. Use: {', '.join(sorted(TIPOS_VALIDOS))}")
    if body.case_id:
        await verificar_acesso_caso(db, cu, body.case_id)
    resp = body.responsavel_id or cu.id
    # Double-booking: AVISA, não bloqueia (decisão: o padrão menos disruptivo é
    # criar e devolver `conflito_agenda` no corpo — nunca silencia, nunca perde
    # o evento). A checagem é feita ANTES do INSERT para o novo evento não
    # aparecer como conflito de si mesmo.
    conflitos = await _buscar_conflitos(
        db, responsavel_id=resp, data_evento=body.data_evento, hora=body.hora,
    )
    eid = str(uuid4())
    await db.execute(text("""
        INSERT INTO agenda_eventos (id, titulo, tipo, data_evento, hora, local, descricao, case_id, responsavel_id, created_by)
        VALUES (:id, :t, :tp, :d, :h, :l, :desc, :cid, :resp, :cb)
    """), {"id": eid, "t": body.titulo, "tp": body.tipo, "d": body.data_evento,
           "h": body.hora, "l": body.local, "desc": body.descricao,
           "cid": body.case_id, "resp": resp, "cb": cu.id})
    await db.commit()
    return {"id": eid, "ok": True, "conflito_agenda": conflitos}


@router.patch("/{evento_id}")
async def atualizar(
    evento_id: str,
    body: EventoPatch,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    row = (await db.execute(text(
        "SELECT case_id, responsavel_id, data_evento, hora, concluido "
        "FROM agenda_eventos WHERE id = :eid AND deleted_at IS NULL"
    ), {"eid": evento_id})).mappings().first()
    if row is None:
        raise HTTPException(404, "Evento não encontrado")
    if row["case_id"]:
        await verificar_acesso_caso(db, cu, row["case_id"])
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        return {"ok": True}
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["eid"] = evento_id
    await db.execute(text(f"UPDATE agenda_eventos SET {set_clause}, updated_at = now() WHERE id = :eid"), updates)
    await db.commit()
    # Double-booking na edição: mesma política do criar (avisa, não bloqueia).
    # Valores efetivos = patch quando presente, senão o valor atual. Evento que
    # passou a concluído não conflita. Exclui a si mesmo via exclude_id.
    concluido_eff = body.concluido if body.concluido is not None else row["concluido"]
    conflitos: list[dict] = []
    if not concluido_eff:
        data_eff = body.data_evento or row["data_evento"]
        hora_eff = body.hora if body.hora is not None else row["hora"]
        conflitos = await _buscar_conflitos(
            db, responsavel_id=row["responsavel_id"],
            data_evento=data_eff, hora=hora_eff, exclude_id=evento_id,
        )
    return {"ok": True, "conflito_agenda": conflitos}


@router.delete("/{evento_id}")
async def remover(
    evento_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    row = (await db.execute(text(
        "SELECT case_id FROM agenda_eventos WHERE id = :eid AND deleted_at IS NULL"
    ), {"eid": evento_id})).first()
    if row is None:
        raise HTTPException(404, "Evento não encontrado")
    if row[0]:
        await verificar_acesso_caso(db, cu, row[0])
    await db.execute(text("UPDATE agenda_eventos SET deleted_at = now() WHERE id = :eid"), {"eid": evento_id})
    await db.commit()
    return {"ok": True}
