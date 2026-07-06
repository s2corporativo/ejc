# ── app/routers/data_room.py ──────────────────────────────────────────────────
# Data Room — salas seguras de documentos com links de acesso externo.
from __future__ import annotations
import secrets
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.core.ownership import verificar_acesso_caso
from app.models.user import User
from app.models.document import Document
from app.models.data_room import DataRoom, DataRoomArquivo, DataRoomLink, DataRoomAcessoLog

router = APIRouter(prefix="/data-rooms", tags=["Data Room"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class DataRoomIn(BaseModel):
    nome:      str = Field(min_length=3, max_length=200)
    descricao: Optional[str] = None
    case_id:   Optional[str] = None
    client_id: Optional[str] = None


class AdicionarArquivoReq(BaseModel):
    document_id:   str
    nome_exibicao: Optional[str] = None


class GerarLinkReq(BaseModel):
    descricao:   Optional[str] = None
    expira_horas: int = Field(72, ge=1, le=8760)   # 72h padrão, máx 1 ano
    max_acessos:  Optional[int] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pode_editar(u: User) -> bool:
    return ROLE_LEVEL.get(u.role.value, 0) >= ROLE_LEVEL["advogado"]

async def _usuario_ve_documento(db: AsyncSession, cu: User, doc: Document) -> bool:
    """Reaplica o gate do GED — cofre (confidencialidade) + ownership do caso —
    para FILTRAR listagens do Data Room. Não levanta: retorna bool. Reusa os
    helpers canônicos (documents._pode_acessar_confidencial + ownership) para
    não divergir da regra do GED."""
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
        "id": r.id, "nome": r.nome, "descricao": r.descricao,
        "case_id": r.case_id, "client_id": r.client_id,
        "created_by": r.created_by,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }

def _out_link(lk: DataRoomLink) -> dict:
    return {
        "id": lk.id, "token": lk.token, "descricao": lk.descricao,
        "expira_em": lk.expira_em.isoformat() if lk.expira_em else None,
        "max_acessos": lk.max_acessos,
        "acessos_realizados": lk.acessos_realizados,
        "ativo": lk.ativo,
        "created_at": lk.created_at.isoformat() if lk.created_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def listar_data_rooms(
    case_id:   Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    page:      int = Query(1, ge=1),
    per_page:  int = Query(20, ge=1, le=50),
    db:        AsyncSession = Depends(get_db),
    cu:        User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    q = select(DataRoom).where(DataRoom.deleted_at.is_(None))
    if case_id:
        q = q.where(DataRoom.case_id == case_id)
    if client_id:
        q = q.where(DataRoom.client_id == client_id)
    q = q.order_by(DataRoom.created_at.desc())
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    items = (await db.execute(q.offset((page-1)*per_page).limit(per_page))).scalars().all()
    return {"total": total, "page": page, "per_page": per_page, "items": [_out_room(r) for r in items]}


@router.post("", status_code=201)
async def criar_data_room(
    req: DataRoomIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    room = DataRoom(id=str(uuid4()), created_by=cu.id, **req.model_dump())
    db.add(room)
    await db.commit()
    return _out_room(room)


@router.get("/{room_id}")
async def obter_data_room(
    room_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    room = (await db.execute(
        select(DataRoom).where(DataRoom.id == room_id, DataRoom.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not room:
        raise HTTPException(404)

    arquivos = (await db.execute(
        select(DataRoomArquivo).where(DataRoomArquivo.data_room_id == room_id)
    )).scalars().all()

    # Filtra por acesso do usuário a CADA documento (cofre + ownership do caso).
    # Sem isto, a listagem expõe metadados de docs de casos alheios a um
    # advogado que não é dono do caso.
    docs: dict = {}
    if arquivos:
        rows = (await db.execute(
            select(Document).where(
                Document.id.in_([a.document_id for a in arquivos]),
                Document.deleted_at.is_(None),
            )
        )).scalars().all()
        docs = {d.id: d for d in rows}
    arquivos_visiveis = [
        a for a in arquivos
        if (d := docs.get(a.document_id)) is not None
        and await _usuario_ve_documento(db, cu, d)
    ]

    links = (await db.execute(
        select(DataRoomLink).where(DataRoomLink.data_room_id == room_id, DataRoomLink.ativo.is_(True))
    )).scalars().all()

    return {
        **_out_room(room),
        "arquivos": [
            {"id": a.id, "document_id": a.document_id, "nome_exibicao": a.nome_exibicao,
             "added_at": a.added_at.isoformat() if a.added_at else None}
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
    room = (await db.execute(
        select(DataRoom).where(DataRoom.id == room_id, DataRoom.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not room:
        raise HTTPException(404)
    # Vincular um documento à sala não pode furar o cofre nem o ownership do
    # caso do documento — senão a sala (e o link externo) vazam metadados
    # (título/nome) de documentos de casos alheios. Valida ANTES de gravar.
    doc = (await db.execute(
        select(Document).where(Document.id == req.document_id, Document.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Documento não encontrado")
    from app.routers.documents import _pode_acessar_confidencial
    if not _pode_acessar_confidencial(cu, doc.confidencialidade.value):
        raise HTTPException(403, "Sem permissão para este documento (cofre)")
    if doc.case_id:
        await verificar_acesso_caso(db, cu, doc.case_id)  # 403/404
    arq = DataRoomArquivo(
        id=str(uuid4()), data_room_id=room_id,
        document_id=req.document_id, nome_exibicao=req.nome_exibicao,
        adicionado_por=cu.id,
    )
    db.add(arq)
    await db.commit()
    return {"id": arq.id, "document_id": arq.document_id}


@router.delete("/{room_id}/arquivos/{arquivo_id}", status_code=204)
async def remover_arquivo(
    room_id: str, arquivo_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    arq = (await db.execute(
        select(DataRoomArquivo).where(
            DataRoomArquivo.id == arquivo_id,
            DataRoomArquivo.data_room_id == room_id,
        )
    )).scalar_one_or_none()
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
    """Gera link de acesso externo com expiração configurável."""
    if not _pode_editar(cu):
        raise HTTPException(403)
    room = (await db.execute(
        select(DataRoom).where(DataRoom.id == room_id, DataRoom.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not room:
        raise HTTPException(404)

    token = secrets.token_urlsafe(48)
    expira = datetime.now(timezone.utc) + timedelta(hours=req.expira_horas)
    lk = DataRoomLink(
        id=str(uuid4()), data_room_id=room_id, token=token,
        descricao=req.descricao, expira_em=expira,
        max_acessos=req.max_acessos, criado_por=cu.id,
    )
    db.add(lk)
    await db.commit()
    return {**_out_link(lk), "url_acesso": f"/data-room/acesso/{token}"}


@router.delete("/{room_id}/links/{link_id}", status_code=204)
async def revogar_link(
    room_id: str, link_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Desativa (revoga) um link de acesso antes da expiração."""
    if not _pode_editar(cu):
        raise HTTPException(403)
    lk = (await db.execute(
        select(DataRoomLink).where(DataRoomLink.id == link_id,
                                   DataRoomLink.data_room_id == room_id)
    )).scalar_one_or_none()
    if not lk:
        raise HTTPException(404)
    lk.ativo = False
    await db.commit()


@router.get("/acesso/{token}", include_in_schema=False)
async def acessar_link_publico(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Endpoint público — acesso externo via token.
    Registra o acesso, valida expiração e retorna os arquivos disponíveis.
    """
    lk = (await db.execute(
        select(DataRoomLink).where(DataRoomLink.token == token, DataRoomLink.ativo.is_(True))
    )).scalar_one_or_none()
    if not lk:
        raise HTTPException(404, "Link inválido ou revogado")

    agora = datetime.now(timezone.utc)
    if lk.expira_em and lk.expira_em < agora:
        raise HTTPException(410, "Link expirado")
    if lk.max_acessos and lk.acessos_realizados >= lk.max_acessos:
        raise HTTPException(403, "Limite de acessos atingido")

    # Registra acesso
    lk.acessos_realizados = (lk.acessos_realizados or 0) + 1
    log = DataRoomAcessoLog(
        id=str(uuid4()), link_id=lk.id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(log)
    await db.flush()

    arquivos = (await db.execute(
        select(DataRoomArquivo).where(DataRoomArquivo.data_room_id == lk.data_room_id)
    )).scalars().all()
    await db.commit()

    return {
        "data_room_id": lk.data_room_id,
        "arquivos": [
            {"document_id": a.document_id, "nome": a.nome_exibicao}
            for a in arquivos
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
    room = (await db.execute(
        select(DataRoom).where(DataRoom.id == room_id, DataRoom.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not room:
        raise HTTPException(404)
    room.deleted_at = datetime.now(timezone.utc)
    await db.commit()
