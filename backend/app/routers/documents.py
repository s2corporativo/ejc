# ── app/routers/documents.py ─────────────────────────────────────────────────
# GED: upload/download com controle de confidencialidade (cofre).
# Acesso a docs restritos: audit log obrigatório (LGPD art. 37).
import json
import logging
import os
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional

import aiofiles
import magic  # python-magic — validação por magic bytes (server-side)
from fastapi import BackgroundTasks, APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, func as sqlfunc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import get_settings
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User
from app.models.document import Document, DocConfidencialidade
from app.models.client import Client
from app.models.case import Case
from app.models.redesign import DocumentTypeMaster
from app.models.audit_log import criar_audit_log
from app.core.ownership import verificar_acesso_caso, is_gestao
from app.schemas.common import MsgResponse
import asyncio
from app.services.ocr_service import extrair_texto, extrair_xml

settings = get_settings()
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["Documentos / GED"])

EXTENSOES_PERMITIDAS = {".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png", ".xlsx", ".xls", ".txt", ".xml"}
# Legados sem extrator de texto (sem lib p/ binário OLE): upload aceito, mas o
# response avisa que o conteúdo não é indexável (ver bloco final do upload()).
FORMATOS_SEM_INDEXACAO = {".doc", ".xls"}

# Tipos legados do campo Document.tipo — continuam aceitos no upload mesmo que
# não existam no master (compatibilidade com o frontend atual). Os que existem
# no master (procuracao/contrato/peticao/outro) são validados por lá também.
TIPOS_LEGADOS = {"procuracao", "contrato", "decisao", "peticao", "prova", "outro"}

# Magic bytes esperados por extensão. O valor é o conjunto de MIME types
# aceitáveis que `magic.from_buffer` pode retornar para aquele formato.
# .txt fica de fora da exigência estrita (texto puro tem detecção ambígua).
MIME_POR_EXTENSAO: dict[str, set[str]] = {
    ".pdf":  {"application/pdf"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
              "application/zip"},  # OOXML é um zip — magic às vezes reporta zip
    ".doc":  {"application/msword", "application/x-ole-storage"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
              "application/zip"},
    ".xls":  {"application/vnd.ms-excel", "application/x-ole-storage"},
    ".jpg":  {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png":  {"image/png"},
    # NF-e/XML: libmagic pode reportar application/xml, text/xml ou text/plain
    ".xml":  {"application/xml", "text/xml", "text/plain"},
}


def _validar_conteudo(ext: str, conteudo: bytes) -> str:
    """
    Valida magic bytes contra a extensão declarada. Retorna o MIME real
    (detectado do conteúdo) para persistir — nunca o content_type do cliente.
    Levanta HTTPException 415 se houver incompatibilidade.
    """
    mime_real = magic.from_buffer(conteudo[:2048], mime=True)
    esperados = MIME_POR_EXTENSAO.get(ext)
    if esperados is None:
        # .txt e similares: aceita, mas registra o MIME detectado
        return mime_real or "text/plain"
    if mime_real not in esperados:
        raise HTTPException(
            status_code=415,
            detail=f"Conteúdo do arquivo ({mime_real}) não corresponde à "
                   f"extensão {ext}.",
        )
    return mime_real


def _pode_acessar_confidencial(user: User, conf: str) -> bool:
    """Cofre: restrito+ exige perfil socio ou superior."""
    if conf in ("restrito", "confidencial", "segredo_justica"):
        return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["socio"]
    return True


async def _verificar_acesso_cliente_sem_caso(
    db: AsyncSession,
    user: User,
    client_id: str,
) -> None:
    """Autoriza cliente avulso por gestão, titular externo ou caso atribuído."""
    if is_gestao(user):
        return
    if user.role.value == "cliente_externo":
        if getattr(user, "client_id", None) == client_id:
            return
        raise HTTPException(status_code=403, detail="Sem permissão para este cliente")
    case_id = (
        await db.execute(
            select(Case.id)
            .where(
                Case.client_id == client_id,
                Case.deleted_at.is_(None),
                or_(
                    Case.advogado_responsavel_id == user.id,
                    Case.advogado_auxiliar_id == user.id,
                ),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if case_id is None:
        raise HTTPException(status_code=403, detail="Sem permissão para este cliente")


async def _verificar_acesso_documento(
    db: AsyncSession,
    user: User,
    document: Document,
) -> None:
    """Gate único para documento vinculado a caso, cliente ou apenas uploader."""
    if document.case_id:
        await verificar_acesso_caso(db, user, document.case_id)
        return
    if is_gestao(user) or document.uploaded_by == user.id:
        return
    if document.client_id:
        if (
            user.role.value == "cliente_externo"
            and document.confidencialidade.value != "normal"
        ):
            raise HTTPException(status_code=403, detail="Documento interno ou restrito")
        await _verificar_acesso_cliente_sem_caso(db, user, document.client_id)
        return
    raise HTTPException(status_code=403, detail="Sem permissão para este documento")



async def _analisar_doc_bg(case_id: str, ocr_text: str, doc_id: str, user_id: str) -> None:
    """Dispara análise estratégica em background após upload de documento com OCR."""
    try:
        from app.services.analise_estrategica import analisar_caso
        from app.core.database import AsyncSessionLocal
        from app.models.ai_log import AILog, AITipoUso, AIStatusHITL
        from sqlalchemy import text as _sql
        from uuid import uuid4 as _uuid4
        import json as _json

        async with AsyncSessionLocal() as db:
            row = await db.execute(
                _sql("SELECT titulo, area, numero_processo, client_id FROM cases WHERE id = :id"),
                {"id": case_id},
            )
            caso = row.fetchone()

            resultado = await analisar_caso(
                titulo=(caso.titulo if caso else "") or "",
                area=(caso.area if caso else "") or "",
                numero_processo=(caso.numero_processo if caso else "") or "",
                texto_documento=ocr_text[:4000],
                scope_client_id=(caso.client_id if caso else None),  # A2: RAG restrito ao cliente
                case_id=case_id,  # PR #85: pseudonimização reversível dos nomes do caso
                db=db,
            )

            fontes = None
            if isinstance(resultado, dict) and resultado.get("_fontes_rag"):
                fontes = _json.dumps(resultado["_fontes_rag"], ensure_ascii=False)[:2000]
            log = AILog(
                id=str(_uuid4()),
                user_id=user_id,
                case_id=case_id,
                tipo_uso=AITipoUso.analise_caso,
                modelo="auto-analise-doc",
                prompt_sanitizado=f"[auto] analise estrategica do documento {doc_id}",
                resposta=_json.dumps(resultado, ensure_ascii=False)[:8000],
                fontes_rag=fontes,
                status_hitl=AIStatusHITL.gerado,
            )
            db.add(log)
            await db.commit()
    except Exception as exc:
        import logging as _log
        _log.getLogger(__name__).warning("Hook analise doc falhou: %s", exc)

async def _tipos_master_ativos(db: AsyncSession) -> list[DocumentTypeMaster]:
    """Tipos ativos do master (document_types_master), ordenados para o seletor."""
    rows = (await db.execute(
        select(DocumentTypeMaster)
        .where(DocumentTypeMaster.ativo.is_(True))
        .order_by(DocumentTypeMaster.ordem, DocumentTypeMaster.nome)
    )).scalars().all()
    return list(rows)


# ─────────────────────────────────────────────────────────────────────────────
# TIPOS DE DOCUMENTO (master) — R3
# IMPORTANTE (ordem de rotas): /tipos e /sugerir-tipo são declarados ANTES de
# qualquer rota com path param /{doc_id}, senão o FastAPI capturaria "tipos"
# como doc_id. Não mover para baixo.
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/tipos")
async def listar_tipos(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Lista os tipos de documento ativos do master para o seletor do frontend."""
    tipos = await _tipos_master_ativos(db)
    return {
        "data": [
            {
                "tipo_key": t.tipo_key,
                "nome": t.nome,
                "categoria": t.categoria,
                "descricao": t.descricao,
                "campos_extracao": t.campos_extracao,
                "extensoes_aceitas": t.extensoes_aceitas,
            }
            for t in tipos
        ],
        "total": len(tipos),
    }


class SugerirTipoRequest(BaseModel):
    doc_id: Optional[str] = None
    texto: Optional[str] = None
    # Formato alternativo usado pelo ImportarDocumento.tsx: classifica a partir
    # do JSON da análise (extração estruturada) + nome do arquivo.
    nome_arquivo: Optional[str] = None
    analise: Optional[dict] = None


@router.post("/sugerir-tipo")
async def sugerir_tipo_documento(
    req: SugerirTipoRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Classifica o documento em UM tipo_key do master via IA (SUGESTÃO).

    NUNCA grava o tipo no Document — confirmação humana obrigatória (HITL).
    Pipeline LGPD: sanitizar_pii antes do envio + AILog (como em ai_service).
    """
    if not req.doc_id and not (req.texto and req.texto.strip()):
        raise HTTPException(status_code=422, detail="Informe doc_id ou texto")

    texto = req.texto
    case_id = None
    if req.doc_id:
        d = (await db.execute(
            select(Document).where(
                Document.id == req.doc_id, Document.deleted_at.is_(None)
            )
        )).scalar_one_or_none()
        if not d:
            raise HTTPException(status_code=404, detail="Documento não encontrado")
        # Mesmos gates do download (IDOR + cofre)
        await _verificar_acesso_documento(db, cu, d)
        if not _pode_acessar_confidencial(cu, d.confidencialidade.value):
            raise HTTPException(status_code=403, detail="Documento restrito — acesso negado")
        case_id = d.case_id
        texto = texto or d.ocr_text

    if not texto or len(texto.strip()) < 40:
        raise HTTPException(
            status_code=422,
            detail="Sem texto suficiente para classificar (OCR vazio ou muito curto).",
        )

    tipos = await _tipos_master_ativos(db)
    if not tipos:
        raise HTTPException(
            status_code=503,
            detail="Catálogo de tipos (document_types_master) não populado — rode o seed.",
        )

    from app.services.documento_service import sugerir_tipo
    try:
        return await sugerir_tipo(
            db, cu.id, texto,
            tipos=[{"tipo_key": t.tipo_key, "nome": t.nome, "descricao": t.descricao}
                   for t in tipos],
            case_id=case_id, doc_id=req.doc_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        import logging as _logging
        _logging.getLogger(__name__).error(
            "sugerir-tipo falhou (doc %s): %s", req.doc_id, e, exc_info=True
        )
        raise HTTPException(status_code=503, detail="Serviço de IA indisponível no momento")


@router.post("/upload", status_code=201)
async def upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    titulo: str = Form(...),
    tipo: Optional[str] = Form(None),
    confidencialidade: str = Form("normal"),
    case_id: Optional[str] = Form(None),
    client_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    # Bloco 2 (Etapa 4) — fecha IDOR na ESCRITA: só cria documento em caso ao
    # qual o usuário tem acesso. Antes, case_id vinha do form sem checagem (o
    # gate existia só na leitura/download). Verificado antes de qualquer I/O em
    # disco para não deixar arquivo órfão em caso de rejeição. Mesmo padrão de
    # processes.py e do download deste módulo.
    if case_id:
        caso = await verificar_acesso_caso(db, cu, case_id)
        # #8: o cliente do documento é SEMPRE derivado do caso — nunca confiar no
        # client_id do formulário. Sem isso, um usuário podia marcar o documento
        # com o client_id de OUTRO cliente e ele apareceria no Portal externo do
        # cliente errado (vazamento cross-tenant). Divergência → 422.
        if client_id and client_id != caso.client_id:
            raise HTTPException(
                status_code=422,
                detail="client_id diverge do cliente do caso informado",
            )
        client_id = caso.client_id
    elif client_id:
        # Sem caso vinculado, o client_id precisa existir — senão o documento
        # apontaria para um cliente arbitrário/inexistente (mesmo risco no portal).
        cli = (await db.execute(
            select(Client.id).where(
                Client.id == client_id, Client.deleted_at.is_(None)
            )
        )).scalar_one_or_none()
        if cli is None:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        await _verificar_acesso_cliente_sem_caso(db, cu, client_id)

    # #29: confidencialidade chega como string livre do form; validar contra o
    # enum e responder 422 (antes caía direto no SAEnum do model → 500).
    try:
        conf_enum = DocConfidencialidade(confidencialidade)
    except ValueError:
        _validos = ", ".join(c.value for c in DocConfidencialidade)
        raise HTTPException(
            status_code=422,
            detail=f"Confidencialidade inválida: {confidencialidade}. Use: {_validos}",
        )

    # Validações
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in EXTENSOES_PERMITIDAS:
        raise HTTPException(status_code=422, detail=f"Extensão não permitida: {ext}")

    # Validação do tipo contra o master (R3), mantendo os valores legados
    # aceitos (decisao/prova não existem no master, mas o frontend atual envia).
    if tipo:
        tipos_validos = set(TIPOS_LEGADOS)
        try:
            tipos_validos |= {t.tipo_key for t in await _tipos_master_ativos(db)}
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "document_types_master indisponível na validação de tipo: %s", e
            )
        if tipo not in tipos_validos:
            raise HTTPException(
                status_code=422,
                detail=f"Tipo de documento inválido: {tipo}. Use GET /documents/tipos.",
            )

    conteudo = await file.read()
    if len(conteudo) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo excede {settings.MAX_UPLOAD_MB}MB",
        )

    # Validação por magic bytes (server-side) — não confiar na extensão nem no
    # content_type do cliente. Retorna o MIME real, persistido abaixo.
    mime_real = _validar_conteudo(ext, conteudo)

    # Salvar no volume (estrutura: uploads/AAAA/MM/uuid.ext)
    agora = datetime.now(timezone.utc)
    subdir = f"{agora.year}/{agora.month:02d}"
    os.makedirs(f"{settings.UPLOAD_DIR}/{subdir}", exist_ok=True)
    doc_id = str(uuid4())
    filepath = f"{subdir}/{doc_id}{ext}"
    full_path = f"{settings.UPLOAD_DIR}/{filepath}"

    async with aiofiles.open(full_path, "wb") as f:
        await f.write(conteudo)

    # OCR em thread (não bloqueia o event loop); falha não impede upload.
    # XML (NF-e): parser seguro dedicado, que devolve também campos fiscais
    # estruturados (chave de acesso, CNPJ emitente, valor total, NCMs).
    import asyncio as _asyncio
    ocr_text = None
    nfe_info = None
    try:
        if ext == ".xml":
            res_xml = await _asyncio.to_thread(extrair_xml, full_path)
            if res_xml:
                ocr_text = res_xml.get("texto")
                nfe_info = res_xml.get("nfe")
        else:
            ocr_text = await _asyncio.to_thread(extrair_texto, full_path, mime_real)
    except Exception as e:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "OCR falhou no upload doc %s: %s", doc_id, e
        )

    d = Document(
        id=doc_id, titulo=titulo, tipo=tipo,
        filename=file.filename, filepath=filepath,
        mimetype=mime_real, size_bytes=len(conteudo),
        confidencialidade=conf_enum, ocr_text=ocr_text,
        case_id=case_id, client_id=client_id, uploaded_by=cu.id,
    )
    db.add(d)
    await criar_audit_log(
        db, cu.id, cu.role.value, "UPLOAD", "documents", doc_id,
        detalhes=f"{titulo} ({confidencialidade})",
    )
    await db.commit()
    # Hook: análise estratégica automática quando há OCR e case_id
    if case_id and ocr_text:
        background_tasks.add_task(_analisar_doc_bg, case_id, ocr_text, doc_id, cu.id)
    resposta: dict = {"id": doc_id, "detail": "Documento enviado"}
    if nfe_info:
        resposta["nfe"] = nfe_info  # campos fiscais estruturados (NF-e/XML)
    # P1 (2026-07-05): formatos legados SEM extrator de texto (.doc/.xls) —
    # decisão de menor atrito: o upload continua aceito (não quebra fluxo de
    # quem só arquiva), mas o response avisa que o conteúdo não será indexado
    # (busca por conteúdo e análise IA ficam indisponíveis para o arquivo).
    if ext in FORMATOS_SEM_INDEXACAO and not ocr_text:
        resposta["aviso"] = (
            "Conteúdo não indexável: formato legado sem extração de texto "
            f"({ext}). Converta para {'.docx' if ext == '.doc' else '.xlsx'} "
            "para habilitar busca por conteúdo e análise por IA."
        )
    return resposta


@router.get("/")
async def listar(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=500),
    case_id: Optional[str] = None,
    client_id: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(Document).where(Document.deleted_at.is_(None))
    # Cofre + ownership: documento sem case_id não é público para a equipe.
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        q = q.where(Document.confidencialidade.in_(["normal", "interno"]))
    if cu.role.value == "cliente_externo":
        if not getattr(cu, "client_id", None):
            q = q.where(Document.id.is_(None))
        else:
            q = q.where(
                Document.client_id == cu.client_id,
                Document.confidencialidade == "normal",
            )
    elif not is_gestao(cu):
        casos_visiveis = select(Case.id).where(
            Case.deleted_at.is_(None),
            or_(
                Case.advogado_responsavel_id == cu.id,
                Case.advogado_auxiliar_id == cu.id,
            ),
        )
        clientes_visiveis = select(Case.client_id).where(
            Case.deleted_at.is_(None),
            Case.client_id.is_not(None),
            or_(
                Case.advogado_responsavel_id == cu.id,
                Case.advogado_auxiliar_id == cu.id,
            ),
        )
        q = q.where(
            or_(
                Document.case_id.in_(casos_visiveis),
                (
                    Document.case_id.is_(None)
                    & Document.client_id.in_(clientes_visiveis)
                ),
                (
                    Document.case_id.is_(None)
                    & Document.client_id.is_(None)
                    & (Document.uploaded_by == cu.id)
                ),
            )
        )
    if case_id:
        q = q.where(Document.case_id == case_id)
    if client_id:
        q = q.where(Document.client_id == client_id)
    if search:
        q = q.where(
            (Document.titulo.ilike(f"%{search}%"))
            | (Document.ocr_text.ilike(f"%{search}%"))   # busca por CONTEÚDO
        )
    q = q.order_by(Document.created_at.desc())

    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery())
    )).scalar()
    rows = (await db.execute(
        q.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {
        "data": [
            {"id": d.id, "titulo": d.titulo, "tipo": d.tipo,
             "filename": d.filename, "size_bytes": d.size_bytes,
             "confidencialidade": d.confidencialidade.value,
             "case_id": d.case_id, "created_at": d.created_at}
            for d in rows
        ],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/{doc_id}/download")
async def download(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    d = (await db.execute(
        select(Document).where(
            Document.id == doc_id, Document.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    # Ownership (IDOR): documento de um caso só é acessível a quem tem o caso.
    await _verificar_acesso_documento(db, cu, d)

    if not _pode_acessar_confidencial(cu, d.confidencialidade.value):
        raise HTTPException(
            status_code=403,
            detail="Documento restrito — acesso negado",
        )

    full_path = f"{settings.UPLOAD_DIR}/{d.filepath}"
    if not os.path.exists(full_path):
        raise HTTPException(status_code=410, detail="Arquivo físico não encontrado")

    # Audit de download (obrigatório — LGPD)
    await criar_audit_log(
        db, cu.id, cu.role.value, "DOWNLOAD", "documents", doc_id,
        detalhes=d.titulo,
    )
    await db.commit()

    return FileResponse(
        full_path, filename=d.filename,
        media_type=d.mimetype or "application/octet-stream",
    )


@router.delete("/{doc_id}", response_model=MsgResponse)
async def remover(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    d = (await db.execute(
        select(Document).where(
            Document.id == doc_id, Document.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    # Ownership (IDOR): só quem tem o caso pode remover o documento dele.
    await _verificar_acesso_documento(db, cu, d)
    d.deleted_at = datetime.now(timezone.utc)
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", "documents", doc_id)
    await db.commit()
    return MsgResponse(detail="Documento removido")


@router.post("/{doc_id}/classificar",
             dependencies=[Depends(rate_limit("doc-classificar", 15))])
async def classificar_tipo_documento(
    doc_id: str,
    aplicar: bool = Query(
        False,
        description="Se true, grava o tipo sugerido em Document.tipo "
                    "(somente quando a IA sugere um tipo válido do catálogo).",
    ),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Classificação automática de tipo por IA a partir do texto extraído (OCR).

    Retorna uma SUGESTÃO (tipo_sugerido/confianca/alternativas). Por padrão NÃO
    grava nada no documento — confirmação humana obrigatória (HITL/OAB). Use
    `?aplicar=true` para persistir o tipo sugerido em Document.tipo.

    LGPD: o texto é sanitizado (sanitizar_pii) dentro de classificar_documento
    ANTES de qualquer envio à IA. Fail-safe: IA indisponível → tipo_sugerido=None.
    """
    d = (await db.execute(
        select(Document).where(
            Document.id == doc_id, Document.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    # Mesmos gates do download/sugerir-tipo (IDOR + cofre).
    await _verificar_acesso_documento(db, cu, d)
    if not _pode_acessar_confidencial(cu, d.confidencialidade.value):
        raise HTTPException(status_code=403, detail="Documento restrito — acesso negado")

    # Texto extraído do documento: campo Document.ocr_text (preenchido no upload).
    from app.services.document_classifier import classificar_documento
    resultado = await classificar_documento(db, d.ocr_text or "")

    # Persistência opcional e explícita (não sobrescreve automaticamente).
    aplicado = False
    if aplicar and resultado.get("tipo_sugerido"):
        d.tipo = resultado["tipo_sugerido"]
        await criar_audit_log(
            db, cu.id, cu.role.value, "UPDATE", "documents", doc_id,
            detalhes=f"tipo classificado por IA: {d.tipo}",
        )
        await db.commit()
        aplicado = True

    return {
        "doc_id": doc_id,
        "aplicado": aplicado,
        "tipo_atual": d.tipo,
        **resultado,
        "aviso": "⚠️ SUGESTÃO gerada por IA — confirmação humana obrigatória.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE DRIVE — upload, download e deleção de documentos
# ─────────────────────────────────────────────────────────────────────────────
from fastapi import UploadFile, File as FastFile, Form
from app.services import google_drive as gd
import os

@router.post("/drive/upload")
async def upload_para_drive(
    file: UploadFile = FastFile(...),
    case_id: str = Form(None),
    descricao: str = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload de documento direto para o Google Drive."""
    # Bloco 2 (Etapa 4) — mesmo fecho de IDOR do /upload: exige acesso ao caso
    # antes de subir para o Drive e gravar a referência.
    if case_id:
        await verificar_acesso_caso(db, current_user, case_id)

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(413, "Arquivo muito grande (máx 50 MB)")

    mime = file.content_type or "application/octet-stream"
    # Organizar em subpasta do caso se fornecido
    folder_id = None
    if case_id:
        folder_id = await _get_or_create_case_folder(case_id, db)

    result = gd.upload_file(content, file.filename or "documento", mime, folder_id)

    # Salvar referência no banco
    from sqlalchemy import text as sql_text
    import uuid
    doc_id = str(uuid.uuid4())
    # Colunas alinhadas ao schema real de `documents` (titulo/filename/filepath/
    # size_bytes/uploaded_by são NOT NULL ou canônicas; drive_* vieram na migr. 059).
    # filepath guarda um marcador drive:// (o arquivo vive no Drive, não no volume).
    nome_arq = file.filename or "documento"
    await db.execute(sql_text("""
        INSERT INTO documents
            (id, case_id, titulo, filename, filepath, mimetype, size_bytes,
             drive_file_id, drive_link, uploaded_by, created_at)
        VALUES
            (:id, :case_id, :titulo, :filename, :filepath, :mimetype, :size_bytes,
             :drive_file_id, :drive_link, :uploaded_by, NOW())
        ON CONFLICT DO NOTHING
    """), {
        "id": doc_id,
        "case_id": case_id,
        "titulo": nome_arq,
        "filename": nome_arq,
        "filepath": f"drive://{result['id']}",
        "mimetype": mime,
        "size_bytes": len(content),
        "drive_file_id": result["id"],
        "drive_link": result.get("webViewLink"),
        "uploaded_by": current_user.id,
    })
    await db.commit()

    return {
        "id": doc_id,
        "drive_file_id": result["id"],
        "nome": file.filename,
        "link": result.get("webViewLink"),
        "download": result.get("webContentLink"),
    }


async def _gate_drive_doc(db: AsyncSession, cu: User, file_id: str):
    """Gate IDOR/LGPD para documentos do Drive, inclusive sem case_id."""
    from sqlalchemy import text as sql_text

    row = (
        await db.execute(
            sql_text(
                "SELECT id, case_id, client_id, uploaded_by, confidencialidade "
                "FROM documents WHERE drive_file_id = :fid "
                "AND deleted_at IS NULL LIMIT 1"
            ),
            {"fid": file_id},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(404, "Documento não encontrado")
    if row.get("case_id"):
        await verificar_acesso_caso(db, cu, row["case_id"])
    elif is_gestao(cu) or row.get("uploaded_by") == cu.id:
        pass
    elif row.get("client_id"):
        if (
            cu.role.value == "cliente_externo"
            and row.get("confidencialidade") != "normal"
        ):
            raise HTTPException(403, "Documento interno ou restrito")
        await _verificar_acesso_cliente_sem_caso(db, cu, row["client_id"])
    else:
        raise HTTPException(403, "Sem permissão para este documento")
    if not _pode_acessar_confidencial(
        cu, row.get("confidencialidade") or "normal"
    ):
        raise HTTPException(403, "Documento restrito — acesso negado")
    return row


@router.get("/drive/{file_id}/link")
async def link_documento(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna link de visualização e download de um documento no Drive."""
    await _gate_drive_doc(db, current_user, file_id)
    try:
        info = gd.get_file_link(file_id)
        return {
            "view": info.get("webViewLink"),
            "download": info.get("webContentLink"),
            "nome": info.get("name"),
        }
    except Exception:
        logger.warning("Falha ao obter link do arquivo %s no Drive", file_id, exc_info=True)
        raise HTTPException(404, "Arquivo não encontrado no Drive")


@router.get("/drive/{file_id}/download")
async def download_documento(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Proxy de download — baixa do Drive e retorna ao cliente."""
    await _gate_drive_doc(db, current_user, file_id)
    from fastapi.responses import Response
    try:
        content, mime = gd.download_file(file_id)
        info = gd.get_file_link(file_id)
        return Response(
            content=content,
            media_type=mime,
            headers={"Content-Disposition": f'attachment; filename="{info.get("name","documento")}"'},
        )
    except Exception:
        logger.warning("Falha ao baixar arquivo %s do Drive", file_id, exc_info=True)
        raise HTTPException(404, "Erro ao baixar o arquivo")


@router.delete("/drive/{file_id}")
async def deletar_documento_drive(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove documento do Drive e do banco."""
    from sqlalchemy import text as sql_text
    import logging as _logging
    # Gate IDOR: exige acesso ao caso (ou gestão/criador) ANTES de tocar o Drive.
    row = await _gate_drive_doc(db, current_user, file_id)
    try:
        gd.delete_file(file_id)
    except Exception:
        # Pode já ter sido removido do Drive — registra para diagnóstico.
        _logging.getLogger(__name__).warning(
            "Falha ao remover arquivo %s do Drive (seguindo com remoção local)",
            file_id, exc_info=True,
        )
    # Apaga somente a linha autorizada pelo gate — drive_file_id não é unique,
    # e apagar pelo file_id removeria duplicatas de outros casos/soft-deleted.
    await db.execute(
        sql_text("DELETE FROM documents WHERE id = :id"),
        {"id": row["id"]},
    )
    await criar_audit_log(
        db, current_user.id, current_user.role.value, "DELETE", "documents",
        row["id"], detalhes=f"Exclusão de documento do Drive (drive_file_id={file_id})",
    )
    await db.commit()
    return {"ok": True}


async def _get_or_create_case_folder(case_id: str, db) -> str:
    """Cria subpasta no Drive para o caso se não existir. Retorna folder_id."""
    from sqlalchemy import text as sql_text
    row = (await db.execute(
        sql_text("SELECT drive_folder_id, titulo FROM cases WHERE id = :id"),
        {"id": case_id},
    )).mappings().first()
    if not row:
        return os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
    if row.get("drive_folder_id"):
        return row["drive_folder_id"]
    # Criar subpasta
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    import json as _json
    sa_json = os.getenv("GOOGLE_DRIVE_SA_JSON")
    if not sa_json:
        return os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
    creds = service_account.Credentials.from_service_account_info(
        _json.loads(sa_json),
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    svc = build("drive", "v3", credentials=creds, cache_discovery=False)
    parent = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    meta = {
        "name": f"{case_id[:8]} — {(row.get('titulo') or 'Caso')[:40]}",
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent] if parent else [],
    }
    folder = svc.files().create(body=meta, fields="id").execute()
    folder_id = folder["id"]
    await db.execute(
        sql_text("UPDATE cases SET drive_folder_id = :fid WHERE id = :id"),
        {"fid": folder_id, "id": case_id},
    )
    await db.commit()
    return folder_id

