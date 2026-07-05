# ── app/routers/ia_citacoes.py ───────────────────────────────────────────────
# Gate antialucinação de citações (Fase 4): validação SOB DEMANDA de texto
# gerado por IA contra a base RAG oficial + validação estrutural, aplicando a
# política vigente (CITACOES_POLITICA). Complementa POST /ai/citacoes/verificar
# (relatório cru do verificador) devolvendo também a DECISÃO de política
# (bloqueia_aprovacao/bloqueantes/motivos) usada pelo fluxo HITL.
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.user import User
from app.services.citation_gate import RelatorioCitacoes, validar_citacoes

router = APIRouter(prefix="/ia", tags=["IA — Gate de Citações"])


class ValidarCitacoesRequest(BaseModel):
    # 50k chars ≈ maior peça plausível; teto menor que o do verificador cru
    # (/ai/citacoes/verificar) porque este endpoint também roda a política.
    texto: str = Field(..., min_length=1, max_length=50_000)


@router.post("/validar-citacoes", response_model=RelatorioCitacoes,
             dependencies=[Depends(rate_limit("validar-citacoes", 15))])
async def validar_citacoes_endpoint(
    req: ValidarCitacoesRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Valida citações jurídicas de um texto (leis, súmulas, julgados).

    100% local e determinístico (sem LLM, sem rede externa). Retorna o
    relatório completo do verificador rigoroso + a decisão da política
    (`bloqueia_aprovacao`, `bloqueantes`, `motivos`).
    """
    return await validar_citacoes(db, req.texto)
