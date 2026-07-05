"""
AI Skills — execução de skills IA parametrizadas.
GET  /api/ai/skills/list
POST /api/ai/skills/execute        (texto)
POST /api/ai/skills/execute-doc    (upload PDF/DOCX/imagem → OCR → skill)
"""
from __future__ import annotations
import os
import asyncio
import tempfile
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.ai_skill import SkillListItem, SkillExecuteRequest, SkillExecuteResponse
from app.services import ai_skill_service

router = APIRouter(prefix="/ai/skills", tags=["AI Skills"])

_MAX_DOC_BYTES = 25 * 1024 * 1024     # 25 MB
_MAX_TEXTO_CHARS = 18000              # limite p/ caber no contexto do modelo


@router.get("/list", response_model=List[SkillListItem])
async def listar_skills(
    area: Optional[str] = Query(None, description="juridico | financeiro | operacional"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    return await ai_skill_service.listar_skills(db, area=area)


@router.post("/execute", response_model=SkillExecuteResponse)
async def executar_skill(
    req: SkillExecuteRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    # Bloco 5 (continuação): case_id existia mas sem checagem de ownership —
    # fecha a lacuna antes de derivar o escopo do RAG a partir dele (sem isso,
    # um usuário poderia passar case_id de outro cliente e puxar precedentes
    # alheios).
    escopo_cli = None
    if req.case_id:
        from app.core.ownership import verificar_acesso_caso
        from app.services.ai_service import _escopo_cliente_do_caso
        await verificar_acesso_caso(db, cu, req.case_id)
        escopo_cli = await _escopo_cliente_do_caso(db, req.case_id)

    contexto_rag = None
    if req.usar_rag:
        try:
            from app.services.ai_service import buscar_contexto_rag
            ctx = await buscar_contexto_rag(db, req.query, limite=5, scope_client_id=escopo_cli)
            contexto_rag = [str(c.get("conteudo") or "") for c in (ctx or []) if c.get("conteudo")]
        except Exception:
            contexto_rag = None

    try:
        resultado = await ai_skill_service.executar_skill(
            db=db,
            skill_name=req.skill_name,
            query=req.query,
            user_id=cu.id,
            case_id=req.case_id,
            contexto_rag=contexto_rag,
            user_role=getattr(cu.role, "value", cu.role),
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except RuntimeError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))

    return SkillExecuteResponse(**resultado)


@router.post("/execute-doc", response_model=SkillExecuteResponse)
async def executar_skill_documento(
    skill_name: str = Form(...),
    file: UploadFile = File(...),
    case_id: Optional[str] = Form(None),
    instrucoes: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Upload de PDF/DOCX/imagem → extrai texto (OCR) → executa a skill escolhida
    sobre o conteúdo. Habilita ferramentas baseadas em documento (síntese de
    processo, análise de CNIS, laudo, contrato...) reusando o engine de skills.
    Resultado é MINUTA (revisão humana obrigatória)."""
    conteudo = await file.read()
    if not conteudo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Arquivo vazio.")
    if len(conteudo) > _MAX_DOC_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Arquivo excede 25 MB.")

    from app.services import ocr_service
    sufixo = os.path.splitext(file.filename or "doc")[1] or ".bin"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=sufixo)
    try:
        tmp.write(conteudo)
        tmp.flush()
        tmp.close()
        texto = await asyncio.to_thread(
            ocr_service.extrair_texto, tmp.name, file.content_type
        )
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass

    if not texto or len(texto.strip()) < 20:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Não foi possível extrair texto do documento (PDF escaneado sem OCR, "
            "formato não suportado ou arquivo ilegível).",
        )
    texto = texto[:_MAX_TEXTO_CHARS]
    query = (f"{instrucoes.strip()}\n\n" if instrucoes else "") + \
            f"DOCUMENTO ENVIADO ({file.filename}):\n\n{texto}"

    try:
        resultado = await ai_skill_service.executar_skill(
            db=db, skill_name=skill_name, query=query, user_id=cu.id, case_id=case_id,
            user_role=getattr(cu.role, "value", cu.role),
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except RuntimeError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))

    return SkillExecuteResponse(**resultado)
