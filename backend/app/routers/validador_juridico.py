# app/routers/validador_juridico.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.security import get_current_user, requer_advogado
from app.models.ai_log import AILog, AIStatusHITL
from app.models.audit_log import criar_audit_log
from app.models.legal_doc import LegalDoc, PecaStatus
from app.models.user import User
from app.schemas.legal_doc import LegalDocDetail
from app.services.case_intel import indexar_peca_rag
from app.services.document_format import padronizar_documento_juridico
from app.services.pdf_service import peca_para_pdf_async
from app.services.validador_juridico_service import ValidacaoInput, validar_rascunho_juridico

# Sem prefixo global: preserva as rotas históricas /validador-juridico/* e permite
# que este módulo exponha o novo fluxo consolidado em /legal-docs/* sem alterar
# app/main.py nem duplicar o router principal de peças.
router = APIRouter(tags=["Validador Juridico"])

Nivel = Literal["padrao", "alto", "maximo"]
_VALIDACAO_SCORE_MINIMO = 75
_STATUS_APROVADOS = {"aprovada", "final", "protocolada"}


class ValidacaoJuridicaRequest(BaseModel):
    rascunho: str = Field(..., min_length=100, max_length=120000)
    tipo_documento: str = Field("peca_juridica", max_length=80)
    area: str | None = Field(None, max_length=80)
    rito: str | None = Field(None, max_length=80)
    fase: str | None = Field(None, max_length=80)
    documentos: list[str] = Field(default_factory=list)
    case_id: str | None = None
    nivel_inteligencia: Nivel = "alto"


class ConferenciaAssinaturaRequest(BaseModel):
    """Manifestação afirmativa do advogado no ato único de conferência.

    As observações são opcionais: a prova mínima do ato é o usuário autenticado,
    data/hora, IP capturado pelo middleware, versão da peça e log de validação.
    """

    confirmado: bool = Field(..., description="Confirma que o advogado conferiu a peça")
    observacoes: str | None = Field(None, max_length=4000)


@router.get("/validador-juridico/status")
async def status_validador(cu: User = Depends(get_current_user)):
    return {
        "modulo": "validador_juridico",
        "status": "ativo",
        "verifica": [
            "fontes normativas",
            "jurisprudencia pendente",
            "provas e onus probatorio",
            "rito e pedidos",
            "coerencia interna",
            "score de confianca",
            "checklist de conferencia do advogado",
        ],
        "aviso": (
            "Controle interno de qualidade. A peça somente é liberada para uso "
            "após conferência afirmativa do advogado responsável."
        ),
    }


@router.post("/validador-juridico/validar")
async def validar(
    req: ValidacaoJuridicaRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    try:
        # Bloco 5 (continuação): case_id existia mas sem checagem de ownership.
        escopo_cli = None
        if req.case_id:
            await verificar_acesso_caso(db, cu, req.case_id)
            from app.services.ai_service import _escopo_cliente_do_caso

            escopo_cli = await _escopo_cliente_do_caso(db, req.case_id)
        payload = ValidacaoInput(
            rascunho=req.rascunho,
            tipo_documento=req.tipo_documento,
            area=req.area,
            rito=req.rito,
            fase=req.fase,
            documentos=req.documentos,
            case_id=req.case_id,
            nivel_inteligencia=req.nivel_inteligencia,
        )
        return await validar_rascunho_juridico(
            payload, db=db, user_id=cu.id, scope_client_id=escopo_cli
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))


async def _peca_ou_404(db: AsyncSession, doc_id: str, cu: User) -> LegalDoc:
    doc = (
        await db.execute(
            select(LegalDoc).where(
                LegalDoc.id == doc_id,
                LegalDoc.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    if doc.case_id:
        await verificar_acesso_caso(db, cu, doc.case_id)
    return doc


async def _validacao_corrente(db: AsyncSession, doc_id: str) -> AILog | None:
    return (
        await db.execute(
            select(AILog)
            .where(
                AILog.legal_doc_id == doc_id,
                AILog.legal_doc_validation_current.is_(True),
            )
            .order_by(AILog.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _gerar_validacao_corrente(
    db: AsyncSession,
    doc: LegalDoc,
    cu: User,
) -> AILog:
    escopo_cli = None
    if doc.case_id:
        from app.services.ai_service import _escopo_cliente_do_caso

        escopo_cli = await _escopo_cliente_do_caso(db, doc.case_id)

    resultado = await validar_rascunho_juridico(
        ValidacaoInput(
            rascunho=doc.conteudo,
            tipo_documento=(
                doc.tipo_peca.value if hasattr(doc.tipo_peca, "value") else str(doc.tipo_peca)
            ),
            area=doc.area,
            fase="conferencia_pre_assinatura",
            documentos=[
                f"LEGAL_DOC_ID:{doc.id}",
                f"TITULO:{doc.titulo}",
                f"STATUS_ATUAL:{doc.status.value if hasattr(doc.status, 'value') else doc.status}",
            ],
            case_id=doc.case_id,
            nivel_inteligencia="alto",
        ),
        db=db,
        user_id=cu.id,
        scope_client_id=escopo_cli,
    )
    log = (
        await db.execute(select(AILog).where(AILog.id == resultado["ai_log_id"]))
    ).scalar_one_or_none()
    if not log:
        raise HTTPException(
            status_code=500,
            detail="A validação foi executada, mas o respectivo log não foi localizado.",
        )
    return log


@router.patch("/legal-docs/{doc_id}/conferir-assinar")
async def conferir_e_assinar(
    doc_id: str,
    payload: ConferenciaAssinaturaRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Consolida validar → aplicar HITL → aprovar em um único ato afirmativo.

    O clique não elimina os controles: ele identifica o advogado, exige confirmação
    expressa, usa a validação vinculada à versão atual da peça, mantém score mínimo,
    bloqueia jurisprudência não confirmada e registra trilha de auditoria.
    """
    requer_advogado(cu, detail="Conferir e assinar peça é restrito a advogados")
    if payload.confirmado is not True:
        raise HTTPException(
            status_code=422,
            detail="A confirmação afirmativa do advogado é obrigatória.",
        )

    doc = await _peca_ou_404(db, doc_id, cu)
    log = await _validacao_corrente(db, doc.id)
    if log is None:
        try:
            log = await _gerar_validacao_corrente(db, doc, cu)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
        except RuntimeError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))

    # Reutiliza a mesma fonte de verdade do fluxo principal de peças.
    from app.routers.legal_docs import (
        _auditar_jurisprudencia_peca,
        _bg_checklist_protocolo,
        _montar_validacao,
        _ultima_validacao_peca,
    )

    validacao = _montar_validacao(log)
    score = validacao.get("score")
    veredito = (validacao.get("veredito") or "").upper()
    if score is None or score < _VALIDACAO_SCORE_MINIMO:
        raise HTTPException(
            status_code=422,
            detail=(
                "Peça não liberada: a validação da versão atual precisa atingir "
                f"{_VALIDACAO_SCORE_MINIMO}/100. Score atual: {score if score is not None else 'indisponível'}."
            ),
        )
    if veredito.startswith("BLOQUEAR"):
        raise HTTPException(
            status_code=422,
            detail="Peça não liberada: o veredito da validação exige correção prévia.",
        )

    auditoria_juris = await _auditar_jurisprudencia_peca(db, doc.conteudo or "")
    if not auditoria_juris.get("apto"):
        raise HTTPException(
            status_code=422,
            detail={
                "mensagem": (
                    "Peça não liberada: há jurisprudência citada sem validação "
                    "oficial na base."
                ),
                "auditoria_jurisprudencia": auditoria_juris,
            },
        )

    status_anterior = doc.status.value if hasattr(doc.status, "value") else str(doc.status)
    observacoes = (payload.observacoes or "").strip()
    log.status_hitl = AIStatusHITL.aplicado
    doc.human_reviewed = True
    doc.revisor_id = cu.id
    doc.revisado_em = datetime.now(timezone.utc)
    doc.notas_revisao = observacoes or doc.notas_revisao
    if status_anterior not in _STATUS_APROVADOS:
        doc.status = PecaStatus.aprovada

    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "CONFERENCIA_ASSINATURA_HITL",
        "legal_docs",
        doc.id,
        detalhes=(
            f"confirmado=true ai_log_id={log.id} score={score} "
            f"versao={doc.versao} observacoes={'sim' if observacoes else 'nao'}"
        ),
    )
    await db.commit()
    await db.refresh(doc)

    background.add_task(indexar_peca_rag, doc.id)
    if doc.case_id and status_anterior not in _STATUS_APROVADOS:
        background.add_task(_bg_checklist_protocolo, doc.case_id, cu.id)

    resposta = LegalDocDetail.model_validate(doc).model_dump(mode="json")
    resposta["validacao_juridica"] = await _ultima_validacao_peca(db, doc)
    resposta["ato_confirmado"] = {
        "tipo": "conferencia_assinatura",
        "advogado_id": cu.id,
        "confirmado_em": doc.revisado_em,
        "versao": doc.versao,
        "ai_log_id": log.id,
    }
    return resposta


@router.get("/legal-docs/{doc_id}/pdf-minuta")
async def exportar_pdf_minuta(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Disponibiliza imediatamente a minuta em PDF, sem contornar o protocolo.

    Antes da conferência, o PDF leva a marca de minuta gerada por IA. Depois do
    ato afirmativo, sai sem a marca. O endpoint /legal-docs/{id}/pdf continua
    reservado à exportação final já aprovada e validada para protocolo.
    """
    doc = await _peca_ou_404(db, doc_id, cu)
    status_atual = doc.status.value if hasattr(doc.status, "value") else str(doc.status)
    pronto_protocolo = status_atual in _STATUS_APROVADOS and bool(doc.human_reviewed)

    try:
        pdf_bytes = await peca_para_pdf_async(
            padronizar_documento_juridico(doc.titulo),
            padronizar_documento_juridico(doc.conteudo),
            pronto_protocolo=pronto_protocolo,
            codigo_peca=doc.codigo_peca,
            versao=doc.versao,
            status=doc.status,
            revisado_em=doc.revisado_em,
            minuta_ia=bool(doc.ai_generated and not doc.human_reviewed),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "DOWNLOAD",
        "legal_docs",
        doc.id,
        detalhes=(
            "Exportacao PDF minuta; "
            f"human_reviewed={bool(doc.human_reviewed)} versao={doc.versao}"
        ),
    )
    await db.commit()

    from app.routers.legal_docs import _slug_arquivo

    nome = _slug_arquivo(doc.titulo, fallback="minuta-juridica")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nome}.pdf"'},
    )
