# ── app/routers/data_room.py ──────────────────────────────────────────────────
# Data Room — salas seguras de documentos com links de acesso externo.
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import is_gestao, verificar_acesso_caso
from app.core.rate_limit import consumir
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.case import Case
from app.models.client import Client
from app.models.data_room import (
    DataRoom,
    DataRoomAcessoLog,
    DataRoomArquivo,
    DataRoomLink,
)
from app.models.document import Document
from app.models.user import User
from app.services.security_service import obter_ip_real

router = APIRouter(prefix="/data-rooms", tags=["Data Room"])


class DataRoomIn(BaseModel):
    nome: str = Field(min_length=3, max_length=200)
    descricao: Optional[str] = Field(default=None, max_length=4000)
    case_id: Optional[str] = None
    client_id: Optional[str] = None


class AdicionarArquivoReq(BaseModel):
    document_id: str
    nome_exibicao: Optional[str] = Field(default=None, max_length=255)


class GerarLinkReq(BaseModel):
    descricao: Optional[str] = Field(default=None, max_length=200)
    expira_horas: int = Field(72, ge=1, le=8760)
    max_acessos: Optional[int] = Field(default=None, ge=1, le=10000)


def _pode_editar(u: User) -> bool:
    return ROLE_LEVEL.get(u.role.value, 0) >= ROLE_LEVEL["advogado"]


def _ids_casos_visiveis(cu: User):
    return (
        select(Case.id)
        .where(
            Case.deleted_at.is_(None),
            or_(
                Case.advogado_responsavel_id == cu.id,
                Case.advogado_auxiliar_id == cu.id,
            ),
        )
        .scalar_subquery()
    )


def _ids_clientes_visiveis(cu: User):
    casos_com_cliente = select(Case.client_id).where(
        Case.client_id.is_not(None),
        Case.deleted_at.is_(None),
        or_(
            Case.advogado_responsavel_id == cu.id,
            Case.advogado_auxiliar_id == cu.id,
        ),
    )
    return (
        select(Client.id)
        .where(
            Client.deleted_at.is_(None),
            or_(
                Client.responsavel_id == cu.id,
                Client.id.in_(casos_com_cliente),
            ),
        )
        .scalar_subquery()
    )


def _filtro_escopo_rooms(q, cu: User):
    """Segrega vínculos de caso/cliente e preserva salas institucionais.

    Salas sem caso e sem cliente são espaços compartilhados de triagem/uso
    institucional, conforme o contrato legado já coberto por testes. Quando há
    vínculo, o usuário precisa enxergar todos os vínculos informados.
    """
    if is_gestao(cu):
        return q

    casos = _ids_casos_visiveis(cu)
    clientes = _ids_clientes_visiveis(cu)
    return q.where(
        and_(
            or_(DataRoom.case_id.is_(None), DataRoom.case_id.in_(casos)),
            or_(
                DataRoom.client_id.is_(None),
                DataRoom.client_id.in_(clientes),
            ),
        )
    )


async def _cliente_visivel(
    db: AsyncSession,
    cu: User,
    client_id: str,
) -> Client:
    from app.routers.clients import _pode_ver_cliente

    cli = (
        await db.execute(
            select(Client).where(
                Client.id == client_id,
                Client.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if cli is None or not await _pode_ver_cliente(cu, cli, db):
        raise HTTPException(404, "Cliente não encontrado")
    return cli


async def _validar_vinculos_room(
    db: AsyncSession,
    cu: User,
    *,
    case_id: str | None,
    client_id: str | None,
) -> tuple[Case | None, Client | None]:
    case: Case | None = None
    cli: Client | None = None

    if case_id:
        case = (
            await db.execute(
                select(Case).where(
                    Case.id == case_id,
                    Case.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if case is None:
            raise HTTPException(404, "Caso não encontrado")
        await verificar_acesso_caso(db, cu, case_id)

    if client_id:
        cli = await _cliente_visivel(db, cu, client_id)

    if case is not None and client_id and case.client_id:
        if str(case.client_id) != str(client_id):
            raise HTTPException(
                422,
                "O cliente informado não corresponde ao cliente vinculado ao caso",
            )

    return case, cli


async def _gate_room(
    db: AsyncSession,
    cu: User,
    room: DataRoom,
) -> DataRoom:
    """Gate row-level da sala, com 404 para não revelar recurso alheio."""
    if is_gestao(cu):
        return room

    if room.case_id:
        try:
            await verificar_acesso_caso(db, cu, room.case_id)
        except HTTPException:
            raise HTTPException(404)

    if room.client_id:
        try:
            await _cliente_visivel(db, cu, room.client_id)
        except HTTPException:
            raise HTTPException(404)

    # Sem vínculos = sala institucional/triagem compartilhada pela equipe
    # jurídica. Esta compatibilidade é intencional e coberta por regressão.
    return room


async def _usuario_ve_documento(
    db: AsyncSession,
    cu: User,
    doc: Document,
) -> bool:
    from app.routers.documents import _pode_acessar_confidencial

    if not _pode_acessar_confidencial(cu, doc.confidencialidade.value):
        return False
    if doc.case_id:
        try:
            await verificar_acesso_caso(db, cu, doc.case_id)
        except HTTPException:
            return False
    return True


def _out_room(r: DataRoom) -> dict:
    return {
        "id": r.id,
        "nome": r.nome,
        "descricao": r.descricao,
        "case_id": r.case_id,
        "client_id": r.client_id,
        "created_by": r.created_by,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _out_link(lk: DataRoomLink) -> dict:
    # SEGURANÇA: o token NÃO é relistado — segredo de acesso público exposto
    # uma única vez, na criação do link (ver gerar_link). Para recuperar acesso,
    # revogue e gere um novo link.
    return {
        "id": lk.id,
        "descricao": lk.descricao,
        "expira_em": lk.expira_em.isoformat() if lk.expira_em else None,
        "max_acessos": lk.max_acessos,
        "acessos_realizados": lk.acessos_realizados,
        "ativo": lk.ativo,
        "created_at": lk.created_at.isoformat() if lk.created_at else None,
    }


async def _rl_acesso_publico(request: Request) -> None:
    await consumir(
        "data_room_public_access",
        f"ip:{obter_ip_real(request)}",
        60,
    )


def _user_agent_seguro(request: Request) -> str | None:
    ua = (request.headers.get("user-agent") or "").strip()
    return ua[:500] if ua else None


@router.get("")
async def listar_data_rooms(
    case_id: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)

    q = select(DataRoom).where(DataRoom.deleted_at.is_(None))
    q = _filtro_escopo_rooms(q, cu)
    if case_id:
        q = q.where(DataRoom.case_id == case_id)
    if client_id:
        q = q.where(DataRoom.client_id == client_id)
    q = q.order_by(DataRoom.created_at.desc())

    total = (
        await db.execute(select(func.count()).select_from(q.subquery()))
    ).scalar() or 0
    items = (
        await db.execute(q.offset((page - 1) * per_page).limit(per_page))
    ).scalars().all()
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [_out_room(r) for r in items],
    }


@router.post("", status_code=201)
async def criar_data_room(
    req: DataRoomIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)

    await _validar_vinculos_room(
        db,
        cu,
        case_id=req.case_id,
        client_id=req.client_id,
    )
    room = DataRoom(id=str(uuid4()), created_by=cu.id, **req.model_dump())
    db.add(room)
    await db.commit()
    await db.refresh(room)
    return _out_room(room)


@router.get("/{room_id}")
async def obter_data_room(
    room_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    room = (
        await db.execute(
            select(DataRoom).where(
                DataRoom.id == room_id,
                DataRoom.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not room:
        raise HTTPException(404)
    await _gate_room(db, cu, room)

    arquivos = (
        await db.execute(
            select(DataRoomArquivo).where(
                DataRoomArquivo.data_room_id == room_id
            )
        )
    ).scalars().all()

    docs: dict[str, Document] = {}
    if arquivos:
        rows = (
            await db.execute(
                select(Document).where(
                    Document.id.in_([a.document_id for a in arquivos]),
                    Document.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        docs = {d.id: d for d in rows}
    arquivos_visiveis = [
        a
        for a in arquivos
        if (d := docs.get(a.document_id)) is not None
        and await _usuario_ve_documento(db, cu, d)
    ]

    links = (
        await db.execute(
            select(DataRoomLink).where(
                DataRoomLink.data_room_id == room_id,
                DataRoomLink.ativo.is_(True),
            )
        )
    ).scalars().all()

    return {
        **_out_room(room),
        "arquivos": [
            {
                "id": a.id,
                "document_id": a.document_id,
                "nome_exibicao": a.nome_exibicao,
                "added_at": a.added_at.isoformat() if a.added_at else None,
            }
            for a in arquivos_visiveis
        ],
        "links": [_out_link(lk) for lk in links],
    }


@router.post("/{room_id}/arquivos", status_code=201)
async def adicionar_arquivo(
    room_id: str,
    req: AdicionarArquivoReq,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    room = (
        await db.execute(
            select(DataRoom).where(
                DataRoom.id == room_id,
                DataRoom.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not room:
        raise HTTPException(404)
    await _gate_room(db, cu, room)

    doc = (
        await db.execute(
            select(Document).where(
                Document.id == req.document_id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Documento não encontrado")
    from app.routers.documents import _pode_acessar_confidencial

    if not _pode_acessar_confidencial(cu, doc.confidencialidade.value):
        raise HTTPException(
            403,
            "Sem permissão para este documento (cofre)",
        )
    if doc.case_id:
        await verificar_acesso_caso(db, cu, doc.case_id)

    arq = DataRoomArquivo(
        id=str(uuid4()),
        data_room_id=room_id,
        document_id=req.document_id,
        nome_exibicao=req.nome_exibicao,
        adicionado_por=cu.id,
    )
    db.add(arq)
    await db.commit()
    return {"id": arq.id, "document_id": arq.document_id}


@router.delete("/{room_id}/arquivos/{arquivo_id}", status_code=204)
async def remover_arquivo(
    room_id: str,
    arquivo_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    room = (
        await db.execute(
            select(DataRoom).where(
                DataRoom.id == room_id,
                DataRoom.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not room:
        raise HTTPException(404)
    await _gate_room(db, cu, room)

    arq = (
        await db.execute(
            select(DataRoomArquivo).where(
                DataRoomArquivo.id == arquivo_id,
                DataRoomArquivo.data_room_id == room_id,
            )
        )
    ).scalar_one_or_none()
    if not arq:
        raise HTTPException(404)
    await db.delete(arq)
    await db.commit()


@router.post("/{room_id}/links", status_code=201)
async def gerar_link(
    room_id: str,
    req: GerarLinkReq,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    room = (
        await db.execute(
            select(DataRoom).where(
                DataRoom.id == room_id,
                DataRoom.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not room:
        raise HTTPException(404)
    await _gate_room(db, cu, room)

    token = secrets.token_urlsafe(48)
    expira = datetime.now(timezone.utc) + timedelta(hours=req.expira_horas)
    lk = DataRoomLink(
        id=str(uuid4()),
        data_room_id=room_id,
        token=token,
        descricao=req.descricao,
        expira_em=expira,
        max_acessos=req.max_acessos,
        criado_por=cu.id,
    )
    db.add(lk)
    await db.commit()
    # Única exibição do segredo: na resposta de criação (não é relistado).
    return {
        **_out_link(lk),
        "token": token,
        "url_acesso": f"/api/data-rooms/acesso/{token}",
    }


@router.delete("/{room_id}/links/{link_id}", status_code=204)
async def revogar_link(
    room_id: str,
    link_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    room = (
        await db.execute(
            select(DataRoom).where(
                DataRoom.id == room_id,
                DataRoom.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not room:
        raise HTTPException(404)
    await _gate_room(db, cu, room)

    lk = (
        await db.execute(
            select(DataRoomLink).where(
                DataRoomLink.id == link_id,
                DataRoomLink.data_room_id == room_id,
            )
        )
    ).scalar_one_or_none()
    if not lk:
        raise HTTPException(404)
    lk.ativo = False
    await db.commit()


@router.get(
    "/acesso/{token}",
    include_in_schema=False,
    dependencies=[Depends(_rl_acesso_publico)],
)
async def acessar_link_publico(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    lk = (
        await db.execute(
            select(DataRoomLink).where(
                DataRoomLink.token == token,
                DataRoomLink.ativo.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not lk:
        raise HTTPException(404, "Link inválido ou revogado")

    agora = datetime.now(timezone.utc)
    if lk.expira_em and lk.expira_em < agora:
        raise HTTPException(410, "Link expirado")
    if lk.max_acessos and lk.acessos_realizados >= lk.max_acessos:
        raise HTTPException(403, "Limite de acessos atingido")

    room = (
        await db.execute(
            select(DataRoom).where(
                DataRoom.id == lk.data_room_id,
                DataRoom.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if room is None:
        raise HTTPException(410, "Sala indisponível")

    lk.acessos_realizados = (lk.acessos_realizados or 0) + 1
    log = DataRoomAcessoLog(
        id=str(uuid4()),
        link_id=lk.id,
        ip=obter_ip_real(request),
        user_agent=_user_agent_seguro(request),
    )
    db.add(log)
    await db.flush()

    arquivos = (
        await db.execute(
            select(DataRoomArquivo).where(
                DataRoomArquivo.data_room_id == lk.data_room_id
            )
        )
    ).scalars().all()

    ativos: set[str] = set()
    if arquivos:
        ativos = set(
            (
                await db.execute(
                    select(Document.id).where(
                        Document.id.in_([a.document_id for a in arquivos]),
                        Document.deleted_at.is_(None),
                    )
                )
            ).scalars().all()
        )
    await db.commit()

    return {
        "data_room_id": lk.data_room_id,
        "arquivos": [
            {
                "document_id": a.document_id,
                "nome": a.nome_exibicao,
            }
            for a in arquivos
            if a.document_id in ativos
        ],
        "acesso_numero": lk.acessos_realizados,
        "expira_em": lk.expira_em.isoformat() if lk.expira_em else None,
    }


@router.delete("/{room_id}", status_code=204)
async def remover_data_room(
    room_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        raise HTTPException(403)
    room = (
        await db.execute(
            select(DataRoom).where(
                DataRoom.id == room_id,
                DataRoom.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not room:
        raise HTTPException(404)
    room.deleted_at = datetime.now(timezone.utc)
    await db.commit()
