"""AI Skills — catálogo e execução do núcleo único de inteligência.

GET  /api/ai/skills/list
POST /api/ai/skills/execute             (texto)
POST /api/ai/skills/execute-doc         (PDF/DOCX/imagem → OCR → skill)
POST /api/ai/skills/transcribe-media    (áudio/vídeo → transcrição → skill)
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.ai_skill import (
    ContextualActionsResponse,
    SkillExecuteRequest,
    SkillExecuteResponse,
    SkillListItem,
)
from app.services import ai_gateway, ai_skill_service
from app.services.ai_contextual import (
    classificar_documento,
    proximas_skills,
    ranquear_skills_contextuais,
)

router = APIRouter(prefix="/ai/skills", tags=["AI Skills"])
logger = logging.getLogger("ejc.ai.skills.router")
settings = get_settings()

_MAX_DOC_BYTES = 25 * 1024 * 1024
_DIRECT_DOC_CHARS = 18_000
_DOC_EXTENSIONS = {
    ".pdf", ".docx", ".png", ".jpg", ".jpeg", ".tiff", ".webp", ".txt"
}
_MEDIA_EXTENSIONS = {
    ".flac", ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".ogg", ".wav", ".webm"
}
_BASES_LEGAIS_MIDIA = {
    "exercicio_regular_direitos",
    "execucao_contrato",
    "obrigacao_legal_regulatoria",
    "consentimento",
    "outra_documentada",
}


def _safe_filename(filename: str | None, fallback: str) -> str:
    return Path(filename or fallback).name[:180] or fallback


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    if isinstance(exc, RuntimeError):
        # Camada de borda (P0 §3.2): RuntimeError do gateway carrega detalhe
        # técnico (provider/chave/task=) — vai ao log; o usuário recebe leigo.
        from app.core.ai_errors import http_erro_ia
        return http_erro_ia(exc, status.HTTP_503_SERVICE_UNAVAILABLE,
                            contexto="ai_skills")
    if isinstance(exc, ValueError):
        code = (
            status.HTTP_404_NOT_FOUND
            if "não encontrada" in str(exc).lower()
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        return HTTPException(code, str(exc))
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Falha interna na execução da IA.")


async def _preparar_caso(
    db: AsyncSession,
    cu: User,
    case_id: str | None,
) -> tuple[str | None, dict[str, list[str]] | None]:
    """Valida ownership e deriva escopo RAG + entidades pseudonimizáveis."""
    if not case_id:
        return None, None
    from app.core.ownership import verificar_acesso_caso
    from app.services.ai.entidades_caso import entidades_do_caso
    from app.services.ai_service import _escopo_cliente_do_caso

    await verificar_acesso_caso(db, cu, case_id)
    escopo_cliente = await _escopo_cliente_do_caso(db, case_id)
    entidades = await entidades_do_caso(db, case_id) or None
    return escopo_cliente, entidades


async def _buscar_contexto(
    db: AsyncSession,
    consulta: str,
    *,
    usar_rag: bool,
    escopo_cliente: str | None,
    escopo_caso: str | None,
) -> list[str] | None:
    if not usar_rag:
        return None
    try:
        from app.services.ai_service import buscar_contexto_rag

        itens = await buscar_contexto_rag(
            db,
            consulta[:4_000],
            limite=5,
            scope_client_id=escopo_cliente,
            scope_case_id=escopo_caso,
        )
        return [
            str(item.get("conteudo") or "")
            for item in (itens or [])
            if item.get("conteudo")
        ] or None
    except Exception as exc:  # RAG é enriquecimento; a skill continua sem ele.
        logger.warning("RAG indisponível em AI Skill: %s", type(exc).__name__)
        return None


async def _metadados_caso(
    db: AsyncSession,
    case_id: str | None,
    area: str | None,
    phase: str | None,
) -> tuple[str | None, str | None]:
    """Usa área/fase do caso como fonte canônica quando houver vínculo."""
    if not case_id:
        return area, phase
    from app.models.case import Case

    row = (
        await db.execute(
            select(Case.area, Case.fase).where(Case.id == case_id)
        )
    ).one_or_none()
    if row is None:
        raise ValueError("Caso não encontrado.")
    return row.area or area, row.fase or phase


def _acao_contextual(item: dict) -> dict:
    skill = item["skill"]
    return {
        "id": skill.id,
        "name": skill.name,
        "display_name": skill.display_name,
        "description": skill.description,
        "area": skill.area,
        "requires_case": skill.requires_case,
        "requires_human_review": skill.requires_human_review,
        "oab_restricted": skill.oab_restricted,
        "reason": item["reason"],
        "score": item["score"],
    }


async def _proximas_acoes_disponiveis(
    db: AsyncSession,
    skill_name: str | None,
) -> list[dict]:
    desejadas = proximas_skills(skill_name)
    catalogo = await ai_skill_service.listar_skills(db)
    por_nome = {skill.name: skill for skill in catalogo}
    return [
        {
            "name": por_nome[nome].name,
            "display_name": por_nome[nome].display_name,
            "description": por_nome[nome].description,
        }
        for nome in desejadas
        if nome in por_nome
    ][:3]


async def _enriquecer_resultado(
    db: AsyncSession,
    resultado: dict,
    *,
    case_id: str | None,
    surface: str | None,
    area: str | None,
    phase: str | None,
    usar_rag: bool,
    input_type: str,
    classificacao: dict | None = None,
) -> dict:
    resultado["classificacao"] = classificacao
    resultado["proximas_acoes"] = await _proximas_acoes_disponiveis(
        db, resultado.get("skill_name")
    )
    resultado["auditoria"] = {
        "case_id": case_id,
        "surface": surface or "geral",
        "area": area,
        "phase": phase,
        "input_type": input_type,
        "rag_habilitado": usar_rag,
        "classificacao_local": bool(classificacao),
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "revisao_humana_obrigatoria": bool(resultado.get("requer_revisao", True)),
    }
    return resultado


@router.get("/contextual", response_model=ContextualActionsResponse)
async def listar_acoes_contextuais(
    surface: str = Query("resumo", max_length=60),
    case_id: Optional[str] = Query(None),
    area: Optional[str] = Query(None, max_length=80),
    phase: Optional[str] = Query(None, max_length=80),
    document_type: Optional[str] = Query(None, max_length=80),
    limit: int = Query(5, ge=1, le=8),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Recomenda poucas skills dentro do módulo que o usuário já está usando."""
    if case_id:
        await _preparar_caso(db, cu, case_id)
    area, phase = await _metadados_caso(db, case_id, area, phase)
    catalogo = await ai_skill_service.listar_skills(db)
    ranqueadas = ranquear_skills_contextuais(
        catalogo,
        surface=surface,
        area=area,
        phase=phase,
        document_type=document_type,
        has_case=bool(case_id),
        limit=limit,
    )
    return {
        "surface": surface,
        "area": area,
        "phase": phase,
        "document_type": document_type,
        "case_id": case_id,
        "actions": [_acao_contextual(item) for item in ranqueadas],
        "total_catalog": len(catalogo),
        "selection_method": "contextual_rules_v1",
    }


@router.get("/list", response_model=List[SkillListItem])
async def listar_skills(
    area: Optional[str] = Query(None, description="Área do catálogo"),
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
    escopo, entidades = await _preparar_caso(db, cu, req.case_id)
    area, phase = await _metadados_caso(db, req.case_id, req.area, req.phase)
    contexto_rag = await _buscar_contexto(
        db,
        req.query,
        usar_rag=req.usar_rag,
        escopo_cliente=escopo,
        escopo_caso=req.case_id,
    )
    try:
        resultado = await ai_skill_service.executar_skill(
            db=db,
            skill_name=req.skill_name,
            query=req.query,
            user_id=cu.id,
            case_id=req.case_id,
            contexto_rag=contexto_rag,
            user_role=getattr(cu.role, "value", cu.role),
            entidades=entidades,
        )
    except (ValueError, PermissionError, RuntimeError) as exc:
        raise _http_error(exc) from exc
    resultado = await _enriquecer_resultado(
        db,
        resultado,
        case_id=req.case_id,
        surface=req.surface,
        area=area,
        phase=phase,
        usar_rag=req.usar_rag,
        input_type="texto",
    )
    return SkillExecuteResponse(**resultado)


@router.post("/execute-doc", response_model=SkillExecuteResponse)
async def executar_skill_documento(
    skill_name: Optional[str] = Form(None),
    file: UploadFile = File(...),
    case_id: Optional[str] = Form(None),
    instrucoes: Optional[str] = Form(None),
    usar_rag: bool = Form(True),
    surface: str = Form("documentos"),
    area: Optional[str] = Form(None),
    phase: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Extrai documento e executa a skill sem truncar silenciosamente.

    Até ``_DIRECT_DOC_CHARS`` usa uma chamada. Acima disso aplica leitura em
    blocos + síntese; acima do teto configurado responde erro explícito e orienta
    o Data Room, em vez de produzir conclusão sobre somente o começo do arquivo.
    """
    nome_arquivo = _safe_filename(file.filename, "documento")
    extensao = Path(nome_arquivo).suffix.lower()
    if extensao not in _DOC_EXTENSIONS:
        if extensao in _MEDIA_EXTENSIONS:
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                "Para áudio ou vídeo, use a transcrição de mídia.",
            )
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Formato de documento não suportado.",
        )

    conteudo = await file.read(_MAX_DOC_BYTES + 1)
    if not conteudo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Arquivo vazio.")
    if len(conteudo) > _MAX_DOC_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "Arquivo excede 25 MB.",
        )

    escopo, entidades = await _preparar_caso(db, cu, case_id)
    from app.services import ocr_service

    if extensao == ".txt":
        texto = conteudo.decode("utf-8", errors="replace")
    else:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=extensao)
        try:
            tmp.write(conteudo)
            tmp.flush()
            tmp.close()
            texto = await asyncio.to_thread(
                ocr_service.extrair_texto,
                tmp.name,
                file.content_type,
            )
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    texto = (texto or "").strip()
    if len(texto) < 20:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Não foi possível extrair texto útil do documento.",
        )

    area, phase = await _metadados_caso(db, case_id, area, phase)
    classificacao = classificar_documento(nome_arquivo, texto)
    if not skill_name or skill_name == "auto":
        catalogo = await ai_skill_service.listar_skills(db)
        ranqueadas = ranquear_skills_contextuais(
            catalogo,
            surface=surface or classificacao["surface_sugerida"],
            area=area,
            phase=phase,
            document_type=classificacao["tipo"],
            document_skills=classificacao["skills_sugeridas"],
            has_case=bool(case_id),
            limit=1,
        )
        if not ranqueadas:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Nenhuma ação contextual disponível para o documento.",
            )
        skill_name = ranqueadas[0]["skill"].name

    consulta_rag = "\n".join(
        parte for parte in (skill_name, instrucoes or "", texto[:1_500]) if parte
    )
    contexto_rag = await _buscar_contexto(
        db,
        consulta_rag,
        usar_rag=usar_rag,
        escopo_cliente=escopo,
        escopo_caso=case_id,
    )

    try:
        if len(texto) > _DIRECT_DOC_CHARS:
            resultado = await ai_skill_service.executar_skill_documento_longo(
                db=db,
                skill_name=skill_name,
                texto_documento=texto,
                instrucoes=instrucoes or "",
                user_id=cu.id,
                case_id=case_id,
                contexto_rag=contexto_rag,
                user_role=getattr(cu.role, "value", cu.role),
                entidades=entidades,
            )
        else:
            query = (
                (f"{instrucoes.strip()}\n\n" if instrucoes and instrucoes.strip() else "")
                + f"DOCUMENTO ENVIADO ({extensao or 'sem extensão'}):\n\n{texto}"
            )
            resultado = await ai_skill_service.executar_skill(
                db=db,
                skill_name=skill_name,
                query=query,
                user_id=cu.id,
                case_id=case_id,
                contexto_rag=contexto_rag,
                user_role=getattr(cu.role, "value", cu.role),
                entidades=entidades,
            )
            resultado["processamento"] = {
                "modo": "direto",
                "caracteres": len(texto),
                "blocos": 1,
                "truncado": False,
            }
    except (ValueError, PermissionError, RuntimeError) as exc:
        raise _http_error(exc) from exc
    resultado = await _enriquecer_resultado(
        db,
        resultado,
        case_id=case_id,
        surface=surface,
        area=area,
        phase=phase,
        usar_rag=usar_rag,
        input_type="documento",
        classificacao=classificacao,
    )
    return SkillExecuteResponse(**resultado)


@router.post("/transcribe-media", response_model=SkillExecuteResponse)
async def transcrever_midia(
    file: UploadFile = File(...),
    skill_name: str = Form("transcritor-midias-audiencia"),
    instrucoes: Optional[str] = Form(None),
    case_id: Optional[str] = Form(None),
    usar_rag: bool = Form(True),
    idioma: str = Form("pt"),
    base_legal_registrada: str = Form(...),
    confirmar_envio_externo: bool = Form(False),
    surface: str = Form("audiencias"),
    area: Optional[str] = Form(None),
    phase: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Transcreve mídia autorizada e aplica uma skill à transcrição.

    O áudio/vídeo bruto não é armazenado pelo EJC. Como ele não pode ser
    pseudonimizado antes do reconhecimento, cada requisição exige confirmação
    de envio temporário ao Groq e o recurso respeita os kill-switches globais.
    """
    if not confirmar_envio_externo:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "É necessário confirmar o envio temporário da mídia ao provedor externo.",
        )
    base_legal_registrada = (base_legal_registrada or "").strip().lower()
    if base_legal_registrada not in _BASES_LEGAIS_MIDIA:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Registre uma base legal válida para o tratamento da mídia.",
        )

    nome_arquivo = _safe_filename(file.filename, "midia")
    extensao = Path(nome_arquivo).suffix.lower()
    if extensao not in _MEDIA_EXTENSIONS:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Formato de mídia não suportado.",
        )

    # Ownership é verificado antes de incorrer em chamada externa/custo.
    escopo, entidades = await _preparar_caso(db, cu, case_id)
    area, phase = await _metadados_caso(db, case_id, area, phase)
    limite = settings.AUDIO_TRANSCRIPTION_MAX_MB * 1024 * 1024
    conteudo = await file.read(limite + 1)
    if not conteudo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mídia vazia.")
    if len(conteudo) > limite:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Mídia excede {settings.AUDIO_TRANSCRIPTION_MAX_MB} MB.",
        )

    try:
        transcricao_resultado = await ai_gateway.transcrever_audio(
            file_bytes=conteudo,
            filename=nome_arquivo,
            language=idioma,
            confirmacao_envio_externo=True,
        )
        transcricao = transcricao_resultado["texto"]
        # Registro durável da OPERAÇÃO, sem nome do arquivo, áudio ou texto
        # transcrito. A análise jurídica abaixo terá seu AILog separado.
        from app.models.ai_log import AITipoUso
        from app.services.ai_guard import registrar_ai_log

        await registrar_ai_log(
            db,
            user_id=cu.id,
            tipo_uso=AITipoUso.resumo_documento,
            case_id=case_id,
            prompt_sanitizado=(
                "[TRANSCRICAO_MIDIA; "
                f"extensao={extensao}; bytes={len(conteudo)}; idioma={idioma}; "
                f"base_legal={base_legal_registrada}; conteudo_nao_persistido=true]"
            ),
            pii_removida=False,
            resposta="[MÍDIA E TRANSCRIÇÃO BRUTA NÃO PERSISTIDAS PELO EJC]",
            modelo=f"groq/{transcricao_resultado['model']}",
            tokens_input=None,
            tokens_output=None,
            custo_estimado=0,
        )
        contexto_rag = await _buscar_contexto(
            db,
            "\n".join(
                parte
                for parte in (skill_name, instrucoes or "", transcricao[:1_500])
                if parte
            ),
            usar_rag=usar_rag,
            escopo_cliente=escopo,
        )

        if len(transcricao) > _DIRECT_DOC_CHARS:
            resultado = await ai_skill_service.executar_skill_documento_longo(
                db=db,
                skill_name=skill_name,
                texto_documento=transcricao,
                instrucoes=instrucoes or "Analise a transcrição preservando incertezas.",
                user_id=cu.id,
                case_id=case_id,
                contexto_rag=contexto_rag,
                user_role=getattr(cu.role, "value", cu.role),
                entidades=entidades,
            )
        else:
            query = (
                (f"{instrucoes.strip()}\n\n" if instrucoes and instrucoes.strip() else "")
                + f"TRANSCRIÇÃO TÉCNICA DA MÍDIA ({extensao}):\n\n{transcricao}"
            )
            resultado = await ai_skill_service.executar_skill(
                db=db,
                skill_name=skill_name,
                query=query,
                user_id=cu.id,
                case_id=case_id,
                contexto_rag=contexto_rag,
                user_role=getattr(cu.role, "value", cu.role),
                entidades=entidades,
            )
            resultado["processamento"] = {
                "modo": "transcricao_direta",
                "caracteres": len(transcricao),
                "blocos": 1,
                "truncado": False,
            }
    except (ValueError, PermissionError, RuntimeError) as exc:
        raise _http_error(exc) from exc

    resultado["transcricao"] = transcricao
    resultado["aviso_privacidade"] = (
        "A mídia foi enviada ao Groq após os gates internos de ZDR e DPA. O EJC não "
        "persistiu o arquivo nem a transcrição bruta; registrou apenas metadados "
        "da operação. Esses gates registram a validação do responsável; não substituem "
        "a avaliação da base legal, do sigilo e da transferência internacional."
    )
    resultado = await _enriquecer_resultado(
        db,
        resultado,
        case_id=case_id,
        surface=surface,
        area=area,
        phase=phase,
        usar_rag=usar_rag,
        input_type="midia",
    )
    return SkillExecuteResponse(**resultado)
