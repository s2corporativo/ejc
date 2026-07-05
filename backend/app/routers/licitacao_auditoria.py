"""
Router de Auditoria de Licitacoes (consolidacao 28/06/2026).
Correcoes vs pacote v6.0: prefixo /v1 (era /api/v1 -> duplo prefixo); auth JWT;
sem dependencia de DB (auditor stateless).
Montado em /api/v1/licitacao-auditoria (main.py adiciona /api).
"""
from typing import Dict, Any
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.rate_limit import rate_limit
from app.core.licitacao_auditor import LicitacaoAuditor
from app.models.user import User

router = APIRouter(
    prefix="/v1/licitacao-auditoria",
    tags=["licitacao-auditoria"],
    dependencies=[Depends(get_current_user)],
)

_auditor = LicitacaoAuditor()


@router.post("/analyze-competitor-proposal",
             dependencies=[Depends(rate_limit("licitacao-auditoria", 15))])
async def analyze_competitor_proposal(
    file: UploadFile = File(...),
    com_ia: bool = Query(False, description="Enriquecer com IA (opt-in; texto sanitizado + AILog)"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
) -> Dict[str, Any]:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF sao aceitos.")
    pdf_content = await file.read()
    return await _auditor.analyze_competitor_proposal(
        pdf_content, db=db, user_id=cu.id, com_ia=com_ia,
    )


@router.get("/audit-report-template")
async def get_audit_report_template() -> Dict[str, str]:
    return {"template": await _auditor.get_audit_report_template()}
