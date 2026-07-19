# ── app/routers/ficha_triagem.py ─────────────────────────────────────────────
# Ficha de Triagem pré-peça — GATE de qualidade da Jornada do Caso.
#
#   POST /triagem/ficha/pre-preencher {case_id}   → rascunho dos 12 campos (IA)
#   GET  /triagem/ficha?case_id=X                  → ficha corrente do caso (ou vazia)
#   POST /triagem/ficha {case_id, ...campos, confirmar} → UPSERT (salva/confirma)
#
# Piso de role: estagiário+ (mesmo de peca_geracao.gerar_peca). Ownership por
# caso via core/ownership.verificar_acesso_caso em TODAS as rotas. Todo
# pré-preenchimento é RASCUNHO (HITL) — a peça só nasce de ficha CONFIRMADA.
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.ficha_triagem import FichaTriagem
from app.models.user import User
from app.services import ficha_triagem_service as svc

router = APIRouter(prefix="/triagem/ficha", tags=["Triagem — Ficha pré-peça"])

_PISO = ROLE_LEVEL["estagiario"]


def _role_str(cu: User) -> str:
    r = getattr(cu, "role", None)
    return r.value if hasattr(r, "value") else str(r)


def _exigir_piso(cu: User) -> None:
    if ROLE_LEVEL.get(_role_str(cu), 0) < _PISO:
        raise HTTPException(403, "Acesso negado")


# ── Schemas ───────────────────────────────────────────────────────────────────

class PrePreencherIn(BaseModel):
    case_id: str = Field(..., max_length=36)


class FichaIn(BaseModel):
    case_id: str = Field(..., max_length=36)
    competencia: Optional[str] = Field(None, max_length=8000)
    rito: Optional[str] = Field(None, max_length=8000)
    legitimidade_ativa: Optional[str] = Field(None, max_length=8000)
    legitimidade_passiva: Optional[str] = Field(None, max_length=8000)
    prescricao_decadencia: Optional[str] = Field(None, max_length=8000)
    tutela_urgencia: Optional[bool] = None
    tutela_fundamento: Optional[str] = Field(None, max_length=8000)
    provas_disponiveis: Optional[str] = Field(None, max_length=8000)
    provas_faltantes: Optional[str] = Field(None, max_length=8000)
    valor_causa: Optional[str] = Field(None, max_length=120)
    risco_processual: Optional[str] = Field(None, max_length=10)
    risco_nota: Optional[str] = Field(None, max_length=8000)
    pedidos_principais: Optional[str] = Field(None, max_length=8000)
    pedidos_subsidiarios: Optional[str] = Field(None, max_length=8000)
    confianca: Optional[dict] = None
    confirmar: bool = False


def _out_ficha(f: FichaTriagem) -> dict:
    return {
        "id": f.id,
        "case_id": f.case_id,
        "competencia": f.competencia,
        "rito": f.rito,
        "legitimidade_ativa": f.legitimidade_ativa,
        "legitimidade_passiva": f.legitimidade_passiva,
        "prescricao_decadencia": f.prescricao_decadencia,
        "tutela_urgencia": f.tutela_urgencia,
        "tutela_fundamento": f.tutela_fundamento,
        "provas_disponiveis": f.provas_disponiveis,
        "provas_faltantes": f.provas_faltantes,
        "valor_causa": f.valor_causa,
        "risco_processual": f.risco_processual,
        "risco_nota": f.risco_nota,
        "pedidos_principais": f.pedidos_principais,
        "pedidos_subsidiarios": f.pedidos_subsidiarios,
        "confianca": f.confianca,
        "status": f.status,
        "created_by": f.created_by,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/pre-preencher",
             dependencies=[Depends(rate_limit("ficha-triagem-pre", 10))])
async def pre_preencher_ficha(
    payload: PrePreencherIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Pré-preenche os 12 campos da ficha via IA (rascunho de apoio — HITL).
    Não persiste: o advogado revisa e salva/confirma via POST /triagem/ficha."""
    _exigir_piso(cu)
    await verificar_acesso_caso(db, cu, payload.case_id)
    return await svc.pre_preencher(db, payload.case_id,
                                   user_id=cu.id, user_role=_role_str(cu))


@router.get("", dependencies=[Depends(rate_limit("ficha-triagem-obter", 60))])
async def obter_ficha(
    case_id: str = Query(..., max_length=36),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Ficha corrente do caso (ou {ficha: null} se ainda não houver)."""
    _exigir_piso(cu)
    await verificar_acesso_caso(db, cu, case_id)
    ficha = await svc.obter(db, case_id)
    return {"ficha": _out_ficha(ficha) if ficha else None}


@router.post("", dependencies=[Depends(rate_limit("ficha-triagem-salvar", 30))])
async def salvar_ficha(
    payload: FichaIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """UPSERT da ficha do caso. confirmar=true → status 'confirmada' (habilita a
    geração de peça para o caso)."""
    _exigir_piso(cu)
    await verificar_acesso_caso(db, cu, payload.case_id)
    dados = payload.model_dump(exclude={"case_id", "confirmar"}, exclude_unset=True)
    ficha = await svc.salvar(db, payload.case_id, dados,
                             confirmar=payload.confirmar,
                             user_id=cu.id, user_role=_role_str(cu))
    return {"ficha": _out_ficha(ficha), "status": ficha.status}
