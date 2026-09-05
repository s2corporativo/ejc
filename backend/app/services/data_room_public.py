"""Entrega pública do Data Room sem abrir os endpoints autenticados de Documentos.

A capability URL continua sendo o segredo primário. Uma visita bem-sucedida ao
manifesto consome ``max_acessos`` e emite grants HMAC curtos por item. O grant
permite os downloads daquela visita sem contar cada arquivo como novo acesso,
mas não sobrevive a revogação/expiração do link ou perda da condição de
publicação do documento.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlencode
from uuid import uuid4

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.publicacao_externa import confidencialidade_str
from app.models.audit_log import criar_audit_log
from app.models.data_room import DataRoom, DataRoomAcessoLog, DataRoomArquivo, DataRoomLink
from app.models.document import DocConfidencialidade, Document
from app.services import google_drive as gd
from app.services.document_format import ascii_seguro
from app.services.security_service import obter_ip_real

settings = get_settings()
_GRANT_TTL = timedelta(minutes=5)


@dataclass(frozen=True)
class EntregaPublica:
    filename: str
    media_type: str
    local_path: str | None = None
    content: bytes | None = None


def _hash_token(token: str) -> str:
    """Mesmo lookup determinístico da rota canônica de criação do link."""
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def _arquivo_publicavel(arquivo: DataRoomArquivo, doc: Document) -> bool:
    """A aprovação histórica nunca supera a classificação atual do documento."""
    if not bool(arquivo.publicado_externamente):
        return False
    return confidencialidade_str(doc) in {
        DocConfidencialidade.normal.value,
        DocConfidencialidade.restrito.value,
        DocConfidencialidade.confidencial.value,
    }


def _grant_expira_em(agora: datetime, link: DataRoomLink) -> datetime:
    limite = agora + _GRANT_TTL
    if link.expira_em and link.expira_em < limite:
        return link.expira_em
    return limite


def _grant_payload(link_id: str, arquivo_id: str, acesso_numero: int, exp: int) -> bytes:
    return f"data-room:{link_id}:{arquivo_id}:{acesso_numero}:{exp}".encode("utf-8")


def gerar_grant(link_id: str, arquivo_id: str, acesso_numero: int, exp: int) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        _grant_payload(link_id, arquivo_id, acesso_numero, exp),
        hashlib.sha256,
    ).hexdigest()


def grant_valido(
    grant: str,
    *,
    link_id: str,
    arquivo_id: str,
    acesso_numero: int,
    exp: int,
    agora: datetime,
) -> bool:
    if exp < int(agora.timestamp()):
        return False
    esperado = gerar_grant(link_id, arquivo_id, acesso_numero, exp)
    return hmac.compare_digest(grant or "", esperado)


def _remote_path_documento(document: Document) -> str | None:
    filepath = str(document.filepath or "")
    if not filepath.startswith("drive://"):
        return None
    candidato = filepath[len("drive://") :].strip()
    if not candidato or candidato == str(document.drive_file_id or ""):
        return None
    return candidato


def _local_path_seguro(document: Document) -> str:
    """Resolve somente dentro de UPLOAD_DIR, mesmo se metadado estiver corrompido."""
    root = Path(settings.UPLOAD_DIR).resolve()
    rel = PurePosixPath(str(document.filepath or "").replace("\\", "/"))
    if rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts):
        raise HTTPException(status_code=410, detail="Arquivo físico indisponível")
    path = (root / Path(*rel.parts)).resolve()
    if path != root and root not in path.parents:
        raise HTTPException(status_code=410, detail="Arquivo físico indisponível")
    if not path.is_file():
        raise HTTPException(status_code=410, detail="Arquivo físico não encontrado")
    return str(path)


def content_disposition(filename: str) -> str:
    nome = PurePosixPath((filename or "documento").replace("\\", "/")).name
    nome = "".join(ch for ch in nome if ch >= " " and ch != "\x7f").strip()
    if not nome or nome in {".", ".."}:
        nome = "documento"
    nome = nome[:255]
    ascii_nome = ascii_seguro(nome)
    for char in ('"', ";", "\\", "/", "\r", "\n"):
        ascii_nome = ascii_nome.replace(char, "")
    ascii_nome = " ".join(ascii_nome.split()) or "documento"
    return (
        f'attachment; filename="{ascii_nome}"; '
        f"filename*=UTF-8''{quote(nome, safe='')}"
    )


def headers_publicos(filename: str) -> dict[str, str]:
    return {
        "Cache-Control": "private, no-store, max-age=0",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": content_disposition(filename),
    }


async def _link_por_token(
    db: AsyncSession,
    token: str,
    *,
    lock: bool = False,
) -> DataRoomLink:
    stmt = select(DataRoomLink).where(
        DataRoomLink.token_hash == _hash_token(token),
        DataRoomLink.ativo.is_(True),
    )
    if lock:
        stmt = stmt.with_for_update()
    link = (await db.execute(stmt)).scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=404, detail="Link inválido ou revogado")
    agora = datetime.now(timezone.utc)
    if link.expira_em and link.expira_em < agora:
        raise HTTPException(status_code=410, detail="Link expirado")
    return link


async def _room_ativo(db: AsyncSession, room_id: str) -> DataRoom:
    room = (
        await db.execute(
            select(DataRoom).where(
                DataRoom.id == room_id,
                DataRoom.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if room is None:
        raise HTTPException(status_code=410, detail="Sala indisponível")
    return room


async def abrir_manifesto(
    db: AsyncSession,
    token: str,
    request: Request,
) -> dict:
    """Conta uma visita e devolve somente IDs opacos + grants curtos de download."""
    link = await _link_por_token(db, token, lock=True)
    if link.max_acessos and link.acessos_realizados >= link.max_acessos:
        raise HTTPException(status_code=403, detail="Limite de acessos atingido")
    room = await _room_ativo(db, link.data_room_id)

    link.acessos_realizados = (link.acessos_realizados or 0) + 1
    acesso_numero = int(link.acessos_realizados)
    db.add(
        DataRoomAcessoLog(
            id=str(uuid4()),
            link_id=link.id,
            ip=obter_ip_real(request),
            user_agent=(request.headers.get("user-agent") or "").strip()[:500] or None,
        )
    )

    arquivos = (
        await db.execute(
            select(DataRoomArquivo).where(
                DataRoomArquivo.data_room_id == room.id,
                DataRoomArquivo.publicado_externamente.is_(True),
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
        docs = {str(d.id): d for d in rows}

    agora = datetime.now(timezone.utc)
    expira_grant = _grant_expira_em(agora, link)
    exp = int(expira_grant.timestamp())
    itens = []
    for arquivo in arquivos:
        doc = docs.get(str(arquivo.document_id))
        if doc is None or not _arquivo_publicavel(arquivo, doc):
            continue
        grant = gerar_grant(link.id, arquivo.id, acesso_numero, exp)
        query = urlencode({"n": acesso_numero, "exp": exp, "grant": grant})
        itens.append(
            {
                "arquivo_id": arquivo.id,
                "nome": arquivo.nome_exibicao or doc.filename or doc.titulo,
                "download_url": (
                    f"/api/data-rooms/acesso/{token}/arquivos/{arquivo.id}?{query}"
                ),
            }
        )

    await db.commit()
    return {
        "data_room": {"nome": room.nome},
        "arquivos": itens,
        "acesso_numero": acesso_numero,
        "expira_em": link.expira_em.isoformat() if link.expira_em else None,
        "grant_expira_em": expira_grant.isoformat(),
    }


async def _registrar_download_publico(
    db: AsyncSession,
    *,
    arquivo_id: str,
    link_id: str,
    acesso_numero: int,
    request: Request,
) -> None:
    await criar_audit_log(
        db,
        None,
        "publico_data_room",
        "DOWNLOAD_PUBLICO",
        "data_room_arquivos",
        arquivo_id,
        ip=obter_ip_real(request),
        dados_depois={"link_id": link_id, "acesso_numero": acesso_numero},
    )
    await db.commit()


async def preparar_download(
    db: AsyncSession,
    token: str,
    arquivo_id: str,
    *,
    acesso_numero: int,
    exp: int,
    grant: str,
    request: Request,
) -> EntregaPublica:
    link = await _link_por_token(db, token)
    agora = datetime.now(timezone.utc)
    if acesso_numero < 1 or acesso_numero > int(link.acessos_realizados or 0):
        raise HTTPException(status_code=403, detail="Sessão pública inválida")
    if link.max_acessos and acesso_numero > link.max_acessos:
        raise HTTPException(status_code=403, detail="Sessão pública inválida")
    if not grant_valido(
        grant,
        link_id=link.id,
        arquivo_id=arquivo_id,
        acesso_numero=acesso_numero,
        exp=exp,
        agora=agora,
    ):
        raise HTTPException(status_code=403, detail="Grant de download inválido ou expirado")
    if link.expira_em and datetime.fromtimestamp(exp, tz=timezone.utc) > link.expira_em:
        raise HTTPException(status_code=403, detail="Grant de download inválido")

    room = await _room_ativo(db, link.data_room_id)
    arquivo = (
        await db.execute(
            select(DataRoomArquivo).where(
                DataRoomArquivo.id == arquivo_id,
                DataRoomArquivo.data_room_id == room.id,
                DataRoomArquivo.publicado_externamente.is_(True),
            )
        )
    ).scalar_one_or_none()
    if arquivo is None:
        raise HTTPException(status_code=404, detail="Arquivo compartilhado não encontrado")
    doc = (
        await db.execute(
            select(Document).where(
                Document.id == arquivo.document_id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if doc is None or not _arquivo_publicavel(arquivo, doc):
        raise HTTPException(status_code=410, detail="Documento não está mais disponível")

    filename = arquivo.nome_exibicao or doc.filename or "documento"
    media_type = doc.mimetype or "application/octet-stream"
    if doc.drive_file_id:
        try:
            content = await asyncio.to_thread(
                gd.download_file,
                doc.drive_file_id,
                remote_path=_remote_path_documento(doc),
            )
        except gd.DriveIndisponivelError as exc:
            raise HTTPException(status_code=503, detail="Storage indisponível") from exc
        except gd.DriveObjetoNaoEncontradoError as exc:
            raise HTTPException(status_code=410, detail="Arquivo remoto não encontrado") from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Falha no storage remoto") from exc
        await _registrar_download_publico(
            db,
            arquivo_id=arquivo.id,
            link_id=link.id,
            acesso_numero=acesso_numero,
            request=request,
        )
        return EntregaPublica(filename=filename, media_type=media_type, content=content)

    local_path = _local_path_seguro(doc)
    await _registrar_download_publico(
        db,
        arquivo_id=arquivo.id,
        link_id=link.id,
        acesso_numero=acesso_numero,
        request=request,
    )
    return EntregaPublica(
        filename=filename,
        media_type=media_type,
        local_path=local_path,
    )
