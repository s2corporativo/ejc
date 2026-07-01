"""
Geração de documentos por TEMPLATE (Victory Vault / Jinja2).
Distinto de peca_geracao.py (que gera peças via IA/Groq em /pecas).

Religado e protegido na auditoria 28/06/2026: antes era órfão (não registrado),
sem auth e com engine quebrado. Agora exige JWT e usa o DocumentTemplateEngine
async corrigido. Montado em /api/document-templates.
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any, Optional

from app.core.security import get_current_user
from app.models.user import User
from app.core.document_template_engine import DocumentTemplateEngine

router = APIRouter(prefix="/document-templates", tags=["Templates de Documentos"])

dte = DocumentTemplateEngine()


@router.get("/", response_model=List[Dict[str, str]])
async def listar_templates(area_juridica: Optional[str] = None,
                           cu: User = Depends(get_current_user)):
    return await dte.list_available_templates(area_juridica)


@router.post("/generate")
async def gerar_documento(payload: Dict[str, Any],
                          cu: User = Depends(get_current_user)):
    template_id = payload.get("template_id")
    data = payload.get("data", {})
    if not template_id:
        raise HTTPException(status_code=400, detail="template_id é obrigatório.")
    try:
        documento_gerado = await dte.render_document(template_id, data)
        return {"documento": documento_gerado}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
