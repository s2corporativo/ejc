"""Sala Jurídica Conversacional — endpoints (V1).

Prefixo /sala-juridica. Toda IA passa pelo núcleo único (orchestrator →
ai_gateway): sanitização LGPD, RAG, AILog, HITL e crítica adversarial não
são contornados por esta superfície.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, requer_advogado, requer_equipe_juridica
from app.models.audit_log import criar_audit_log
from app.models.legal_chat import LegalChatAttachment, LegalChatSession, SESSION_STATUS
from app.models.user import User
from app.schemas.legal_chat import (
    ConverterRequest,
    EstadoUpdate,
    ProximaAcaoConfirmarRequest,
    MensagemCreate,
    SaidaAlternativaRequest,
    SessaoCreate,
    SessaoUpdate,
    VincularCasoRequest,
)
from app.services import documento_service
from app.services import legal_chat_service as svc
from app.services.upload_lote_service import processar_lote

router = APIRouter(prefix="/sala-juridica", tags=["Sala Jurídica Conversacional"])
settings = get_settings()
logger = logging.getLogger("ejc.sala_juridica")


async def exigir_equipe_juridica(user: User = Depends(get_current_user)) -> User:
    """Adapter FastAPI do gate compartilhado; sem matriz RBAC duplicada."""
    requer_equipe_juridica(user, "A Sala Jurídica é restrita à equipe jurídica")
    return user


MAX_ARQUIVOS = 10
# Markdown entra como texto plano — aceito nos anexos da Sala Jurídica
# (auditoria 12/08/2026: .md era rejeitado como formato não suportado).
EXTENSOES = {
    ".pdf", ".docx", ".doc", ".txt", ".md", ".xml", ".xlsx", ".csv",
    ".png", ".jpg", ".jpeg", ".tiff", ".webp",
}


@router.post("", dependencies=[Depends(rate_limit("sala-juridica-criar", 20))])
async def criar_sessao(
    payload: SessaoCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(exigir_equipe_juridica),
):
    sessao = LegalChatSession(
        id=str(uuid4()),
        titulo=payload.titulo,
        cliente_potencial=payload.cliente_potencial,
        area_sugerida=payload.area_sugerida,
        workspace_texto=payload.workspace_texto,
        advogado_responsavel_id=user.id,
        created_by=user.id,
    )
    db.add(sessao)
    await db.commit()
    await db.refresh(sessao)
    return svc.serializar_sessao(sessao)


@router.get("")
async def listar_sessoes(
    status: str | None = Query(default=None),
    favorita: bool | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(exigir_equipe_juridica),
):
    if status is not None and status not in SESSION_STATUS:
        raise HTTPException(422, f"status inválido; use um de: {sorted(SESSION_STATUS)}")
    stmt = select(LegalChatSession).where(LegalChatSession.deleted_at.is_(None))
    if svc._role(user) not in svc._GESTAO:
        stmt = stmt.where(
            (LegalChatSession.created_by == user.id)
            | (LegalChatSession.advogado_responsavel_id == user.id)
        )
    if status:
        stmt = stmt.where(LegalChatSession.status == status)
    if favorita is not None:
        stmt = stmt.where(LegalChatSession.favorita.is_(favorita))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            LegalChatSession.titulo.ilike(like)
            | LegalChatSession.cliente_potencial.ilike(like)
        )
    stmt = stmt.order_by(LegalChatSession.updated_at.desc()).limit(limit)
    res = await db.execute(stmt)
    return [svc.serializar_sessao(s) for s in res.scalars().all()]


@router.get("/{session_id}")
async def detalhar_sessao(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(exigir_equipe_juridica),
):
    sessao = await svc.obter_sessao(db, session_id, user)
    res = await db.execute(
        select(LegalChatSession)
        .options(
            selectinload(LegalChatSession.mensagens),
            selectinload(LegalChatSession.anexos),
        )
        .where(LegalChatSession.id == sessao.id)
    )
    sessao = res.scalar_one()
    estado = await svc.ultima_versao_estado(db, sessao.id)
    return svc.serializar_sessao(sessao, incluir_relacionados=True, estado=estado)


@router.patch("/{session_id}")
async def atualizar_sessao(
    session_id: str,
    payload: SessaoUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(exigir_equipe_juridica),
):
    sessao = await svc.obter_sessao(db, session_id, user)
    svc.exigir_nao_congelada(sessao)
    dados = payload.model_dump(exclude_unset=True)
    if "workspace_texto" in dados:
        sessao.workspace_versao = (sessao.workspace_versao or 0) + 1
    for campo, valor in dados.items():
        setattr(sessao, campo, valor)
    await db.commit()
    await db.refresh(sessao)
    return svc.serializar_sessao(sessao)


@router.post(
    "/{session_id}/mensagens",
    dependencies=[Depends(rate_limit("sala-juridica-mensagem", 15))],
)
async def enviar_mensagem(
    session_id: str,
    payload: MensagemCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(exigir_equipe_juridica),
):
    requer_advogado(user, "Somente advogados podem usar a análise jurídica de IA")
    sessao = await svc.obter_sessao(db, session_id, user)
    resultado = await svc.enviar_mensagem(db, sessao, payload, user)
    await db.commit()
    return resultado


@router.patch("/{session_id}/estado")
async def atualizar_estado(
    session_id: str,
    payload: EstadoUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(exigir_equipe_juridica),
):
    requer_advogado(user, "A curadoria do estado jurídico é ato privativo de advogado")
    sessao = await svc.obter_sessao(db, session_id, user)
    svc.exigir_nao_congelada(sessao)
    versao = await svc.gravar_versao_estado(
        db, sessao,
        estado=payload.estado,
        resumo=payload.resumo,
        origem="advogado",
        created_by=user.id,
    )
    await db.commit()
    return {"versao": versao.versao}


@router.get("/{session_id}/estado")
async def obter_estado(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(exigir_equipe_juridica),
):
    sessao = await svc.obter_sessao(db, session_id, user)
    estado = await svc.ultima_versao_estado(db, sessao.id)
    if estado is None:
        return {"versao": 0, "resumo": None, "estado": {}, "origem": None}
    return {
        "versao": estado.versao,
        "resumo": estado.resumo,
        "estado": estado.estado,
        "origem": estado.origem,
        "created_at": estado.created_at.isoformat() if estado.created_at else None,
    }


@router.post("/{session_id}/proxima-acao/confirmar")
async def confirmar_proxima_acao(
    session_id: str,
    payload: ProximaAcaoConfirmarRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(exigir_equipe_juridica),
):
    sessao = await svc.obter_sessao(db, session_id, user)
    resultado = await svc.confirmar_proxima_acao(
        db, sessao, acao=payload.acao, user=user
    )
    await criar_audit_log(
        db, user_id=user.id, user_role=svc._role(user),
        acao="UPDATE", entidade="legal_chat_next_action", registro_id=sessao.id,
        dados_depois={"estado": "confirmada", "versao": resultado["versao"]},
    )
    await db.commit()
    return resultado


@router.post(
    "/{session_id}/anexos",
    dependencies=[Depends(rate_limit("sala-juridica-upload", 10))],
)
async def anexar_documentos(
    session_id: str,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(exigir_equipe_juridica),
):
    sessao = await svc.obter_sessao(db, session_id, user)
    svc.exigir_nao_congelada(sessao)
    res = await db.execute(
        select(LegalChatAttachment.sha256).where(
            LegalChatAttachment.session_id == sessao.id
        )
    )
    existentes = {row[0] for row in res.all()}
    validos, duplicados, erros = await processar_lote(
        files,
        max_arquivos=MAX_ARQUIVOS,
        extensoes_permitidas=EXTENSOES,
        existing_hashes=existentes,
        storage_subdir="sala-juridica",
        entidade_id=sessao.id,
    )

    novos: list[LegalChatAttachment] = []
    for arquivo in validos:
        full = Path(settings.UPLOAD_DIR) / arquivo.filepath
        resultado: dict = {}
        try:
            extraido = await documento_service.extrair_e_analisar(
                str(full),
                arquivo.mimetype,
                db=db,
                enriquecer_rag=False,
                user_id=user.id,
            )
            # Texto SANITIZADO retido (truncado): é o que permite ao Document
            # transferido na conversão nascer pesquisável no GED (ocr_text) em
            # vez de "sem texto extraído".
            texto_sana = extraido.pop("_texto_sanitizado", None)
            resultado = jsonable_encoder(extraido)
            if isinstance(texto_sana, str) and texto_sana.strip():
                resultado["_texto_sanitizado"] = texto_sana[:200_000]
        except Exception as exc:  # extração nunca bloqueia o anexo em si
            # Não persistir nem devolver str(exc): mensagens de parser/provider
            # podem conter caminho físico, nome de arquivo ou detalhe interno.
            # O tipo da exceção é suficiente para observabilidade sem PII.
            logger.warning(
                "Falha de extração de anexo da Sala Jurídica; "
                "session_id=%s user_id=%s exception_type=%s",
                sessao.id,
                user.id,
                type(exc).__name__,
            )
            resultado = {
                "ok": False,
                "erro": (
                    "Não foi possível extrair o conteúdo deste anexo. "
                    "O arquivo foi preservado para revisão manual."
                ),
            }
        anexo = LegalChatAttachment(
            id=str(uuid4()),
            session_id=sessao.id,
            nome_original=arquivo.nome_original,
            filepath=arquivo.filepath,
            mimetype=arquivo.mimetype,
            size_bytes=arquivo.size_bytes,
            sha256=arquivo.sha256,
            ocr_utilizado=arquivo.ocr_utilizado,
            resultado_analise=resultado,
            uploaded_by=user.id,
        )
        db.add(anexo)
        novos.append(anexo)

    await criar_audit_log(
        db, user_id=user.id, user_role=svc._role(user),
        acao="UPLOAD", entidade="legal_chat_sessions",
        registro_id=sessao.id,
        detalhes=(
            f"{len(novos)} anexo(s) enviado(s); {len(duplicados)} duplicado(s); "
            f"{len(erros)} erro(s) de validação"
        ),
        dados_depois={
            "anexos": [a.id for a in novos],
            "duplicados": duplicados,
            "erros": erros,
        },
    )
    await db.commit()
    return {
        "anexados": [svc.serializar_anexo(a) for a in novos],
        "duplicados": duplicados,
        "erros": erros,
    }


@router.get(
    "/{session_id}/conversao/preview",
    dependencies=[Depends(rate_limit("sala-juridica-preview", 30))],
)
async def conversao_preview(
    session_id: str,
    nome_cliente: str | None = Query(default=None, max_length=255),
    client_id: str | None = Query(default=None, max_length=36),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(exigir_equipe_juridica),
):
    """Conferência PRÉVIA da conversão: alertas de conflito (EOAB), clientes
    possivelmente duplicados e casos ativos do cliente — sem expor carteira
    não autorizada (achado protegido vira alerta genérico)."""
    sessao = await svc.obter_sessao(db, session_id, user)
    return await svc.preview_conversao(
        db, sessao, user, nome_cliente=nome_cliente, client_id=client_id
    )


@router.post(
    "/{session_id}/converter",
    dependencies=[Depends(rate_limit("sala-juridica-converter", 5))],
)
async def converter(
    session_id: str,
    payload: ConverterRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(exigir_equipe_juridica),
):
    requer_advogado(user, "A criação de caso oficial é ato privativo de advogado")
    sessao = await svc.obter_sessao(db, session_id, user)
    resultado = await svc.converter_em_caso(db, sessao, payload, user)
    await criar_audit_log(
        db, user_id=user.id, user_role=svc._role(user),
        acao="sala_juridica_converter", entidade="legal_chat_sessions",
        registro_id=sessao.id,
        detalhes=f"case_id={resultado.get('case_id')}",
    )
    await db.commit()
    return resultado


@router.post(
    "/{session_id}/vincular-caso",
    dependencies=[Depends(rate_limit("sala-juridica-vincular", 5))],
)
async def vincular_caso(
    session_id: str,
    payload: VincularCasoRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(exigir_equipe_juridica),
):
    """Vincula a análise a um caso já existente (alternativa a criar caso novo)."""
    requer_advogado(user, "O vínculo a caso oficial é ato privativo de advogado")
    sessao = await svc.obter_sessao(db, session_id, user)
    resultado = await svc.vincular_caso_existente(
        db, sessao, payload.case_id, user,
        transferir_anexos=payload.transferir_anexos,
        aplicar_dossie_estruturado=payload.aplicar_dossie_estruturado,
    )
    await criar_audit_log(
        db, user_id=user.id, user_role=svc._role(user),
        acao="sala_juridica_vincular_caso", entidade="legal_chat_sessions",
        registro_id=sessao.id,
        detalhes=f"case_id={resultado.get('case_id')}",
    )
    await db.commit()
    return resultado


@router.get("/{session_id}/exportar")
async def exportar(
    session_id: str,
    formato: str = Query(default="pdf", pattern="^(pdf|docx)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(exigir_equipe_juridica),
):
    """Exporta a análise (workspace + estado + conversa) em PDF ou DOCX."""
    from fastapi.responses import Response

    sessao = await svc.obter_sessao(db, session_id, user)
    res = await db.execute(
        select(LegalChatSession)
        .options(selectinload(LegalChatSession.mensagens))
        .where(LegalChatSession.id == sessao.id)
    )
    sessao = res.scalar_one()
    estado = await svc.ultima_versao_estado(db, sessao.id)
    if formato == "docx":
        conteudo = svc.exportar_docx(sessao, list(sessao.mensagens), estado)
        media = ("application/vnd.openxmlformats-officedocument"
                 ".wordprocessingml.document")
    else:
        conteudo = svc.exportar_pdf(sessao, list(sessao.mensagens), estado)
        media = "application/pdf"
    await criar_audit_log(
        db, user_id=user.id, user_role=svc._role(user),
        acao="sala_juridica_exportar", entidade="legal_chat_sessions",
        registro_id=sessao.id, detalhes=f"formato={formato}",
    )
    await db.commit()
    nome = f"sala-juridica-{sessao.id[:8]}.{formato}"
    return Response(
        content=conteudo,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.post("/{session_id}/saida")
async def saida_alternativa(
    session_id: str,
    payload: SaidaAlternativaRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(exigir_equipe_juridica),
):
    """Saídas que não geram processo: consulta, arquivamento ou descarte."""
    sessao = await svc.obter_sessao(db, session_id, user)
    svc.exigir_nao_congelada(sessao)
    if payload.acao == "descartar":
        sessao.deleted_at = datetime.now(timezone.utc)
        sessao.status = "arquivada"
    else:
        sessao.status = "arquivada"
    await criar_audit_log(
        db, user_id=user.id, user_role=svc._role(user),
        acao=f"sala_juridica_{payload.acao}", entidade="legal_chat_sessions",
        registro_id=sessao.id,
        detalhes=(payload.justificativa or "")[:500] or None,
    )
    await db.commit()
    return {"ok": True, "status": sessao.status}
