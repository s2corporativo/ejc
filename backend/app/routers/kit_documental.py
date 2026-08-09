# ── app/routers/kit_documental.py ────────────────────────────────────────────
# P0.3 — Kit documental inicial do caso: POST /cases/{case_id}/kit-documental.
# Também abriga as portas HTTP de vínculo de documento existente ao caso; a
# regra fica em service dedicado, preservando o router já registrado em /cases.
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, requer_advogado
from app.models.client import Client
from app.models.user import User
from app.services.document_case_link_service import (
    buscar_documentos_vinculaveis,
    vincular_documento_existente,
)
from app.services.geracao_documental import gerar_kit_inicial

router = APIRouter(prefix="/cases", tags=["Kit Documental"])

_PODERES_VALIDOS = {"ad_judicia", "ad_judicia_et_extra", "especiais"}


def _req_advogado(cu: User = Depends(get_current_user)) -> User:
    # Emissão de procuração/contrato é ato jurídico: advogado+ (nível >= 6).
    requer_advogado(cu)
    return cu


class KitDocumentalIn(BaseModel):
    # Defaults CONSERVADORES: poderes especiais do art. 105 do CPC só entram
    # quando explicitamente marcados pelo advogado.
    tipo_poderes: str = "ad_judicia"
    permite_substabelecimento: bool = True
    poderes_especiais: Optional[str] = Field(None, max_length=2000)
    # Idempotência (follow-up PR #283): submissão repetida devolve os rascunhos
    # já existentes do kit (ja_existia=true). Regeneração explícita só com
    # forcar_novo=true.
    forcar_novo: bool = False

    @field_validator("tipo_poderes")
    @classmethod
    def _tipo_valido(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in _PODERES_VALIDOS:
            raise ValueError(f"tipo_poderes deve ser um de {sorted(_PODERES_VALIDOS)}")
        return v


@router.post(
    "/{case_id}/kit-documental",
    status_code=201,
    dependencies=[Depends(rate_limit("kit-documental", 5))],
)
async def gerar_kit_documental(
    case_id: str,
    payload: Optional[KitDocumentalIn] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_advogado),
):
    """Gera o kit documental inicial do caso (procuração + contrato + checklist).

    Documentos nascem SEMPRE como rascunho sujeito a revisão do advogado; o
    valor de honorários vem da Tabela OAB/MG vigente ou fica "a definir" —
    nunca inventado.
    """
    case = await verificar_acesso_caso(db, cu, case_id)
    cli = await db.get(Client, case.client_id) if case.client_id else None
    if cli is None or getattr(cli, "deleted_at", None) is not None:
        raise HTTPException(status_code=404, detail="Cliente do caso não encontrado")

    p = payload or KitDocumentalIn()
    return await gerar_kit_inicial(
        db,
        case,
        cli,
        cu,
        tipo_poderes=p.tipo_poderes,
        permite_substabelecimento=p.permite_substabelecimento,
        poderes_especiais=p.poderes_especiais,
        forcar_novo=p.forcar_novo,
    )


@router.get(
    "/{case_id}/documentos/candidatos",
    tags=["Documentos do Caso"],
    dependencies=[Depends(rate_limit("case-document-candidates", 30))],
)
async def listar_documentos_candidatos(
    case_id: str,
    search: str = Query("", max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Lista somente documentos visíveis e ainda não vinculados ao caso."""
    return await buscar_documentos_vinculaveis(
        db,
        cu,
        case_id,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/{case_id}/documentos/{document_id}/vincular",
    tags=["Documentos do Caso"],
    dependencies=[Depends(rate_limit("case-document-link", 30))],
)
async def vincular_documento_ao_caso(
    case_id: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Vincula/move documento existente, preservando gates e workflow do caso."""
    return await vincular_documento_existente(db, cu, case_id, document_id)
