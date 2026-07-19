"""Agenda de eventos — reuniões, compromissos, diligências, audiências internas.
   Complementa prazos/tarefas/suspensões/intimações na Central de Atividades.
"""
from uuid import uuid4
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ownership import is_gestao, role_str, verificar_acesso_caso
from app.models.audit_log import criar_audit_log
from app.models.user import User

router = APIRouter(prefix="/agenda-eventos", tags=["Agenda de Eventos"])

TIPOS_VALIDOS = {"reuniao", "compromisso", "diligencia", "audiencia", "outro"}


class EventoIn(BaseModel):
    # B3: max_length espelha o VARCHAR do schema (titulo 255, hora 10) —
    # sem isso o INSERT estourava em DataError 500 em vez de 422 claro.
    titulo: str = Field(max_length=255)
    tipo: str = "compromisso"
    data_evento: date
    hora: Optional[str] = Field(None, max_length=10)
    local: Optional[str] = None
    descricao: Optional[str] = None
    case_id: Optional[str] = None
    responsavel_id: Optional[str] = None


class EventoPatch(BaseModel):
    titulo: Optional[str] = Field(None, max_length=255)
    tipo: Optional[str] = None
    data_evento: Optional[date] = None
    hora: Optional[str] = Field(None, max_length=10)
    local: Optional[str] = None
    descricao: Optional[str] = None
    concluido: Optional[bool] = None
    responsavel_id: Optional[str] = None


async def _validar_responsavel(db: AsyncSession, responsavel_id: str) -> None:
    """B3: responsavel_id informado deve apontar p/ usuário REAL — antes
    qualquer string virava responsável (evento órfão, invisível p/ todos)."""
    row = (await db.execute(
        text("SELECT 1 FROM users WHERE id = :rid"), {"rid": responsavel_id}
    )).first()
    if row is None:
        raise HTTPException(422, "responsavel_id inválido: usuário não encontrado")


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
          AND (CAST(:exc AS text) IS NULL OR e.id <> CAST(:exc AS text))
        ORDER BY e.hora
    """), {"resp": responsavel_id, "d": data_evento,
           "h": hora.strip(), "exc": exclude_id})).mappings().all()
    return [dict(r) for r in rows]


def _censurar_conflitos(
    conflitos: list[dict], cu: User, responsavel_id: Optional[str],
) -> list[dict]:
    """N2: o aviso de conflito não pode virar ORÁCULO da agenda alheia — quando
    o responsável dos eventos colidentes NÃO é o chamador (e ele não é gestão),
    mantém as chaves do contrato (`ConflitoEvento` no frontend) mas censura
    titulo/local: só a existência e o horário do compromisso são revelados."""
    if not conflitos or responsavel_id == cu.id or is_gestao(cu):
        return conflitos
    return [dict(c, titulo="Compromisso de outro usuário", local=None)
            for c in conflitos]


@router.get("/")
async def listar(
    page_size: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    # N1 (leitura) + M1: evento SEM caso é PESSOAL e só aparece p/ criador,
    # responsável ou gestão; evento COM caso segue o MESMO padrão EXISTS de
    # atividades.py — responsável pelo evento OU advogado (responsável/auxiliar)
    # do caso OU gestão. Antes, todo evento com case_id vazava titulo/descricao/
    # local/caso_titulo p/ qualquer interno, contradizendo a Central de
    # Atividades, que esconde a mesma atividade.
    filtro_pessoal = ""
    params: dict = {"ps": page_size}
    if not is_gestao(cu):
        filtro_pessoal = """ AND (
            (e.case_id IS NULL AND (e.created_by = :uid OR e.responsavel_id = :uid))
            OR (e.case_id IS NOT NULL AND (e.responsavel_id = :uid OR EXISTS (
                SELECT 1 FROM cases cc WHERE cc.id = e.case_id
                  AND (cc.advogado_responsavel_id = :uid OR cc.advogado_auxiliar_id = :uid)
            )))
        )"""
        params["uid"] = cu.id
    rows = (await db.execute(text(f"""
        SELECT e.id, e.titulo, e.tipo, e.data_evento, e.hora, e.local, e.descricao,
               e.case_id, e.responsavel_id, e.concluido,
               c.titulo AS caso_titulo
        FROM agenda_eventos e
        LEFT JOIN cases c ON c.id = e.case_id
        WHERE e.deleted_at IS NULL{filtro_pessoal}
        ORDER BY e.data_evento ASC, e.hora ASC NULLS LAST
        LIMIT :ps
    """), params)).mappings().all()
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
    # N2a: criar evento na agenda de OUTRO usuário é ato de gestão — sem esse
    # gate, qualquer interno populava (e sondava, via conflito) agenda alheia.
    if resp != cu.id and not is_gestao(cu):
        raise HTTPException(403, "Só a gestão pode criar evento para outro responsável")
    # B3: valida a existência do responsável DEPOIS do gate de gestão — não vira
    # oráculo de ids de usuário p/ quem nem poderia transferir.
    if resp != cu.id:
        await _validar_responsavel(db, resp)
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
    return {"id": eid, "ok": True,
            "conflito_agenda": _censurar_conflitos(conflitos, cu, resp)}


@router.patch("/{evento_id}")
async def atualizar(
    evento_id: str,
    body: EventoPatch,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    row = (await db.execute(text(
        "SELECT case_id, responsavel_id, data_evento, hora, concluido, created_by "
        "FROM agenda_eventos WHERE id = :eid AND deleted_at IS NULL"
    ), {"eid": evento_id})).mappings().first()
    if row is None:
        raise HTTPException(404, "Evento não encontrado")
    if row["case_id"]:
        await verificar_acesso_caso(db, cu, row["case_id"])
    elif not (is_gestao(cu) or cu.id in (row["created_by"], row["responsavel_id"])):
        # Evento pessoal (sem caso — M-S2): só o criador, o responsável ou a
        # gestão podem editar; antes qualquer usuário autenticado alterava.
        raise HTTPException(403, "Sem permissão para este evento")
    if body.tipo is not None and body.tipo not in TIPOS_VALIDOS:
        raise HTTPException(422, f"Tipo inválido. Use: {', '.join(sorted(TIPOS_VALIDOS))}")
    # N2a: TRANSFERIR o evento p/ um terceiro é ato de gestão (mesma regra do
    # criar). Manter o responsável atual (no-op) ou assumir p/ si continua livre.
    if (body.responsavel_id is not None
            and body.responsavel_id not in (cu.id, row["responsavel_id"])
            and not is_gestao(cu)):
        raise HTTPException(403, "Só a gestão pode transferir o evento para outro responsável")
    # B3: novo responsável precisa existir (mesma regra do criar).
    if (body.responsavel_id is not None
            and body.responsavel_id not in (cu.id, row["responsavel_id"])):
        await _validar_responsavel(db, body.responsavel_id)
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        return {"ok": True}
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["eid"] = evento_id
    await db.execute(text(f"UPDATE agenda_eventos SET {set_clause}, updated_at = now() WHERE id = :eid"), updates)
    # B1: transferência de responsável é operação sensível — trilha de auditoria
    # (mesmo padrão de legal_docs: criar_audit_log + commit na mesma transação).
    if (body.responsavel_id is not None
            and body.responsavel_id != row["responsavel_id"]):
        await criar_audit_log(
            db, cu.id, role_str(cu), "UPDATE", "agenda_eventos", evento_id,
            detalhes=f"responsavel: {row['responsavel_id']} → {body.responsavel_id}",
        )
    await db.commit()
    # Double-booking na edição: mesma política do criar (avisa, não bloqueia).
    # Valores efetivos = patch quando presente, senão o valor atual. Evento que
    # passou a concluído não conflita. Exclui a si mesmo via exclude_id.
    concluido_eff = body.concluido if body.concluido is not None else row["concluido"]
    conflitos: list[dict] = []
    if not concluido_eff:
        data_eff = body.data_evento or row["data_evento"]
        hora_eff = body.hora if body.hora is not None else row["hora"]
        # B1: usa o responsável EFETIVO pós-update — se o patch trocou o
        # responsavel_id, checar contra o antigo apontava a agenda errada.
        resp_eff = (body.responsavel_id if body.responsavel_id is not None
                    else row["responsavel_id"])
        conflitos = _censurar_conflitos(await _buscar_conflitos(
            db, responsavel_id=resp_eff,
            data_evento=data_eff, hora=hora_eff, exclude_id=evento_id,
        ), cu, resp_eff)
    return {"ok": True, "conflito_agenda": conflitos}


@router.delete("/{evento_id}")
async def remover(
    evento_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    row = (await db.execute(text(
        "SELECT case_id, responsavel_id, created_by "
        "FROM agenda_eventos WHERE id = :eid AND deleted_at IS NULL"
    ), {"eid": evento_id})).mappings().first()
    if row is None:
        raise HTTPException(404, "Evento não encontrado")
    if row["case_id"]:
        await verificar_acesso_caso(db, cu, row["case_id"])
    elif not (is_gestao(cu) or cu.id in (row["created_by"], row["responsavel_id"])):
        # Evento pessoal (sem caso — M-S2): mesma regra do PATCH.
        raise HTTPException(403, "Sem permissão para este evento")
    await db.execute(text("UPDATE agenda_eventos SET deleted_at = now() WHERE id = :eid"), {"eid": evento_id})
    # B1: soft-delete audita quem removeu o quê (padrão legal_docs.remover).
    await criar_audit_log(db, cu.id, role_str(cu), "DELETE", "agenda_eventos", evento_id)
    await db.commit()
    return {"ok": True}
