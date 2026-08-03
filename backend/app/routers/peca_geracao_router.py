"""
Geração de documentos por TEMPLATE (Victory Vault / Jinja2).
Distinto de peca_geracao.py (que gera peças via IA/Groq em /pecas).

Religado e protegido na auditoria 28/06/2026: antes era órfão (não registrado),
sem auth e com engine quebrado. Agora exige JWT e usa o DocumentTemplateEngine
async corrigido. Montado em /api/document-templates.
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any, Optional

from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, requer_advogado
from app.models.user import User
from app.core.document_template_engine import DocumentTemplateEngine

router = APIRouter(prefix="/document-templates", tags=["Templates de Documentos"])

dte = DocumentTemplateEngine()


@router.get("/", response_model=List[Dict[str, str]])
async def listar_templates(area_juridica: Optional[str] = None,
                           cu: User = Depends(get_current_user)):
    return await dte.list_available_templates(area_juridica)


def _req_advogado(cu: User = Depends(get_current_user)) -> User:
    """Gerar documento jurídico é ATO JURÍDICO — piso advogado+.

    P1 da auditoria integral (docs/auditoria-ejc/08-backend.md §6.3): esta rota
    renderizava documento sem vínculo a caso e apenas com JWT, enquanto o
    caminho gêmeo (kit_documental.py:58) já exigia advogado + rate limit. A
    listagem de templates segue aberta a staff — ler o catálogo não é ato.
    """
    requer_advogado(cu)
    return cu


@router.post("/generate",
             dependencies=[Depends(rate_limit("document-templates-generate", 10))])
async def gerar_documento(payload: Dict[str, Any],
                          cu: User = Depends(_req_advogado)):
    template_id = payload.get("template_id")
    data = payload.get("data", {})
    if not template_id:
        raise HTTPException(status_code=400, detail="template_id é obrigatório.")
    try:
        documento_gerado = await dte.render_document(template_id, data)
        return {"documento": documento_gerado}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
