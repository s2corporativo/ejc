"""
documento_ia.py — Importação inteligente de documentos.
POST /api/documentos-ia/analisar  (multipart: file)
  → OCR + extração estruturada + diagnóstico jurídico + honorários + referências.
POST /api/documentos-ia/analisar-url (JSON: url, case_id opcional)
  → importação segura de página pública + dossiê jurídico + análise opcional.
Retorna JSON que o frontend usa para pré-preencher um novo caso (sem duplicar a
criação de casos — usa o /cases existente).
"""
import os
import tempfile
import logging
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.security import get_current_user
from app.models.case import Case
from app.models.user import User
from app.services import documento_service
from app.services.document_url_import_service import importar_url_juridica

logger = logging.getLogger("ejc.documento_ia")
router = APIRouter(prefix="/documentos-ia", tags=["Importação Inteligente"])

MAX_BYTES = 25 * 1024 * 1024  # 25 MB
TIPOS_OK = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # docx
    "image/png", "image/jpeg", "image/jpg", "image/tiff", "image/webp",
}


class AnalisarUrlRequest(BaseModel):
    """Prévia de importação jurídica por URL pública."""

    url: str = Field(..., min_length=8, max_length=2048)
    titulo: Optional[str] = Field(None, max_length=255)
    case_id: Optional[str] = Field(None, description="Caso existente para análise estratégica opcional")
    executar_analise: bool = Field(
        False,
        description="Quando true e case_id informado, roda análise estratégica como rascunho.",
    )


@router.post("/analisar")
async def analisar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload de PDF/DOCX/imagem → análise jurídica estruturada (HITL)."""
    mimetype = file.content_type or ""
    if mimetype not in TIPOS_OK:
        # alguns navegadores mandam octet-stream; deixamos o OCR decidir pela extensão
        if not (file.filename or "").lower().endswith((".pdf", ".docx", ".png", ".jpg", ".jpeg", ".tiff", ".webp")):
            raise HTTPException(415, "Formato não suportado. Envie PDF, DOCX ou imagem.")

    conteudo = await file.read()
    if len(conteudo) > MAX_BYTES:
        raise HTTPException(413, "Arquivo muito grande (máx. 25 MB).")
    if not conteudo:
        raise HTTPException(400, "Arquivo vazio.")

    # Validação por magic bytes (server-side) — reusa a barreira do GED. Não
    # confiar em content_type/extensão. Extensões sem mapa (.tiff/.webp) passam
    # pelo fallback e ainda assim têm o MIME real detectado; .pdf/.docx/.png/.jpg
    # ganham verificação estrita de conteúdo.
    sufixo = os.path.splitext(file.filename or "doc")[1] or ".bin"
    from app.routers.documents import _validar_conteudo
    mime_real = _validar_conteudo(sufixo.lower(), conteudo)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=sufixo)
    try:
        tmp.write(conteudo)
        tmp.flush()
        tmp.close()
        resultado = await documento_service.extrair_e_analisar(
            tmp.name, mime_real or mimetype or None, db=db, enriquecer_rag=True,
            user_id=current_user.id,
        )
        if not resultado.get("ok"):
            raise HTTPException(422, resultado.get("erro", "Falha ao processar documento."))

        # ── Núcleo Único de IA: o diagnóstico jurídico passa OBRIGATORIAMENTE
        # pelo orchestrator (permissões, policy de provider, validação de
        # citações, HITL e AILog). Os campos antigos do payload (extração
        # estruturada, honorários, referências) são preservados; os campos do
        # núcleo são ACRESCENTADOS — o frontend antigo continua funcionando.
        texto_sanitizado = resultado.pop("_texto_sanitizado", "") or ""
        # Retorno degradado (analise_llm_indisponivel=True): TODA a cadeia de
        # IA acabou de falhar no serviço — chamar o orchestrator agora só
        # adiciona latência para falhar de novo. Pula o núcleo e mantém o
        # aviso (aviso_llm) já presente no payload.
        if resultado.get("analise_llm_indisponivel"):
            resultado["diagnostico_nucleo"] = None
        elif texto_sanitizado:
            from app.services.ai.core.orchestrator import orchestrator
            try:
                nucleo = await orchestrator.run(
                    db=db,
                    user=current_user,
                    task_type="document_analysis",
                    domain="documents",
                    mensagem=(
                        "Analise juridicamente o documento abaixo (já sanitizado) e "
                        "aponte natureza, riscos, providências e pontos de atenção "
                        "para o advogado responsável.\n\nDOCUMENTO:\n"
                        f"{texto_sanitizado}"
                    ),
                    usar_rag=True,
                )
                resultado["diagnostico_nucleo"] = nucleo.get("conteudo")
                resultado["agente"] = nucleo.get("agente")
                resultado["modelo_nucleo"] = nucleo.get("modelo")
                resultado["provider"] = nucleo.get("provider")
                resultado["fontes"] = nucleo.get("fontes", [])
                resultado["citacoes"] = nucleo.get("citacoes", [])
                resultado["log_id"] = nucleo.get("log_id")
                resultado["is_rascunho"] = nucleo.get("is_rascunho", True)
                resultado["aviso_hitl"] = nucleo.get("aviso_hitl")
            except HTTPException as e:
                # Núcleo pode abortar (422 PII residual / policy). A extração
                # estruturada permanece útil — degrada com aviso, sem stack trace.
                logger.warning(f"Núcleo IA indisponível para diagnóstico: {e.detail}")
                resultado["diagnostico_nucleo"] = None
                resultado["nucleo_aviso"] = str(e.detail)[:300]
            except Exception as e:
                logger.warning(f"Núcleo IA falhou no diagnóstico: {type(e).__name__}")
                resultado["diagnostico_nucleo"] = None
                resultado["nucleo_aviso"] = "Diagnóstico pelo núcleo de IA indisponível no momento."
        return resultado
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


@router.post("/analisar-url")
async def analisar_url(
    req: AnalisarUrlRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """URL pública → texto jurídico + dossiê + análise opcional.

    Esta rota NÃO grava automaticamente conteúdo externo no GED nem no caso. Ela
    cria uma prévia revisável para evitar reprodução indevida de conteúdo de
    terceiros e para manter revisão humana obrigatória.
    """
    caso = None
    if req.case_id:
        await verificar_acesso_caso(db, current_user, req.case_id)
        caso = (await db.execute(
            select(Case).where(Case.id == req.case_id, Case.deleted_at.is_(None))
        )).scalar_one_or_none()
        if not caso:
            raise HTTPException(status_code=404, detail="Caso não encontrado")

    resultado = await importar_url_juridica(req.url, titulo=req.titulo)
    out = resultado.model_dump() if hasattr(resultado, "model_dump") else resultado.dict()
    out["ok"] = not resultado.bloqueado
    out["origem"] = "url_publica"
    out["requer_revisao_humana"] = True
    out["pode_aplicar_ao_caso"] = bool(req.case_id and not resultado.bloqueado and resultado.dossie)
    out["diretriz_autoral"] = (
        "Use como referência jurídica revisável. Preferir resumo próprio, metadados, "
        "trechos curtos e link de origem; para jurisprudência, validar em fonte oficial."
    )

    if not req.executar_analise:
        return out

    if not caso:
        raise HTTPException(status_code=422, detail="Informe case_id para executar análise")
    if resultado.bloqueado or not resultado.dossie:
        out["analise"] = None
        out["analise_aviso"] = "Análise não executada porque a URL não gerou texto importável."
        return out

    try:
        from app.services.analise_estrategica import analisar_caso
        analise = await analisar_caso(
            titulo=caso.titulo or req.titulo or resultado.titulo or "Importação por URL",
            area=caso.area or "",
            numero_processo=caso.numero_processo or "",
            texto_documento=resultado.dossie,
            scope_client_id=caso.client_id,
            db=db,
        )
        out["analise"] = analise
        out["analise_aviso"] = "Análise gerada como rascunho. Revise antes de usar no caso."
    except Exception as exc:
        logger.warning("Análise de URL falhou: %s", type(exc).__name__)
        out["analise"] = None
        out["analise_aviso"] = f"Falha ao executar análise estratégica: {str(exc)[:180]}"

    return out
