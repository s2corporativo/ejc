# ── app/routers/api_keys.py ──────────────────────────────────────────────────
# Administração de chaves de API de serviço (Fase 2 IA/RAG).
# Protegido pelo auth JWT existente e restrito a admin/superadmin.
# A chave em claro é retornada UMA única vez, na criação.
# NÃO confundir com routers/credential_vault.py: api_keys emite chaves QUE O
# EJC FORNECE a integradores consumirem nossa API; o cofre (/cofre-credenciais)
# guarda segredos QUE O EJC USA em serviços externos (DataJud, Groq, SMTP…).
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_key_auth import gerar_chave
from app.core.database import get_db
from app.core.security import require_admin
from app.models.api_key import ApiKey
from app.models.audit_log import criar_audit_log

router = APIRouter(prefix="/api-keys", tags=["API Keys de Serviço"])

_ESCOPOS_VALIDOS = {"knowledge:write"}


class ApiKeyCreate(BaseModel):
    nome: str = Field(..., min_length=3, max_length=120,
                      description="Identificação humana da chave (ex.: 'n8n produção')")
    escopo: str = Field("knowledge:write",
                        description="Escopos separados por vírgula. Suportado: knowledge:write")
    client_id: Optional[str] = Field(
        None, description="Isolamento LGPD: restringe TODO conteúdo ingerido por esta chave a um cliente"
    )


def _serializar(ak: ApiKey) -> dict:
    return {
        "id": ak.id, "nome": ak.nome, "prefixo": ak.prefixo,
        "escopo": ak.escopo, "client_id": ak.client_id, "ativo": ak.ativo,
        "created_at": ak.created_at, "last_used_at": ak.last_used_at,
        "revoked_at": ak.revoked_at,
    }


@router.post("", status_code=201, summary="Cria uma chave de API de serviço")
async def criar_api_key(
    req: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    cu=Depends(require_admin),
):
    """Cria uma chave de serviço para integradores externos (n8n, automações).

    A chave em claro (`chave`) é exibida APENAS nesta resposta — guarde-a com
    segurança. O sistema armazena somente o hash SHA-256.
    """
    escopos = {s.strip() for s in req.escopo.split(",") if s.strip()}
    invalidos = escopos - _ESCOPOS_VALIDOS
    if not escopos or invalidos:
        raise HTTPException(
            422, f"Escopo(s) inválido(s): {sorted(invalidos) or 'vazio'}. "
                 f"Suportados: {sorted(_ESCOPOS_VALIDOS)}"
        )
    chave, h, prefixo = gerar_chave()
    ak = ApiKey(
        id=str(uuid4()), nome=req.nome, chave_hash=h, prefixo=prefixo,
        escopo=",".join(sorted(escopos)), client_id=req.client_id, ativo=True,
    )
    db.add(ak)
    await criar_audit_log(
        db, cu.id, cu.role, "CREATE", "api_keys", ak.id,
        detalhes=f"API key '{req.nome}' criada (escopo {ak.escopo})",
    )
    await db.commit()
    return {**_serializar(ak), "chave": chave,
            "aviso": "Guarde esta chave agora — ela não será exibida novamente."}


@router.get("", summary="Lista as chaves de API de serviço")
async def listar_api_keys(
    db: AsyncSession = Depends(get_db),
    cu=Depends(require_admin),
):
    """Lista todas as chaves (sem o segredo — apenas prefixo e metadados)."""
    rows = (await db.execute(
        select(ApiKey).order_by(ApiKey.created_at.desc())
    )).scalars().all()
    return {"data": [_serializar(a) for a in rows], "total": len(rows)}


@router.post("/{key_id}/revogar", summary="Revoga uma chave de API de serviço")
async def revogar_api_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    cu=Depends(require_admin),
):
    """Revogação imediata e irreversível: requisições com esta chave passam a
    receber 401. A linha é mantida para auditoria (nunca apagada)."""
    ak = (await db.execute(
        select(ApiKey).where(ApiKey.id == key_id)
    )).scalar_one_or_none()
    if not ak:
        raise HTTPException(404, "API key não encontrada")
    if ak.revoked_at is not None:
        return {"detail": "API key já estava revogada", **_serializar(ak)}
    ak.ativo = False
    ak.revoked_at = datetime.now(timezone.utc)
    await criar_audit_log(
        db, cu.id, cu.role, "UPDATE", "api_keys", ak.id,
        detalhes=f"API key '{ak.nome}' revogada",
    )
    await db.commit()
    return {"detail": "API key revogada", **_serializar(ak)}
