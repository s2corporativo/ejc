"""
Router de Auditoria de Licitacoes (consolidacao 28/06/2026).
Correcoes vs pacote v6.0: prefixo interno sem /v1 (o middleware global expõe
/api/v1), RBAC jurídico + rate limit; sem dependencia de DB (auditor stateless).
Montado internamente em /api/licitacao-auditoria; o contrato canônico externo
é /api/v1/licitacao-auditoria.
"""
from typing import Dict, Any
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException

from app.core.licitacao_auditor import LicitacaoAuditor
from app.core.rate_limit import rate_limit
from app.core.security import EQUIPE_JURIDICA, require_roles_exact

router = APIRouter(
    prefix="/licitacao-auditoria",
    tags=["licitacao-auditoria"],
    dependencies=[Depends(require_roles_exact(EQUIPE_JURIDICA))],
)

_auditor = LicitacaoAuditor()
_MAX_PDF_BYTES = 15 * 1024 * 1024


@router.post(
    "/analyze-competitor-proposal",
    dependencies=[Depends(rate_limit("licitacao-auditoria-pdf", 10))],
)
async def analyze_competitor_proposal(file: UploadFile = File(...)) -> Dict[str, Any]:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF sao aceitos.")
    pdf_content = await file.read(_MAX_PDF_BYTES + 1)
    if len(pdf_content) > _MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF excede o limite de 15 MB.")
    return await _auditor.analyze_competitor_proposal(pdf_content)


@router.get("/audit-report-template")
async def get_audit_report_template() -> Dict[str, str]:
    return {"template": await _auditor.get_audit_report_template()}
