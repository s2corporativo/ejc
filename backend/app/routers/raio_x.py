"""Raio-X do Processo — análise preliminar autônoma e conversão confirmada."""
from __future__ import annotations

import hashlib
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import get_db
from app.core.ownership import is_gestao, verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.deadline import Deadline
from app.models.document import Document
from app.models.raio_x import RaioXAnalise, RaioXDocumento
from app.models.task import Task
from app.models.user import User
from app.schemas.raio_x import RaioXCreate, RaioXConverterRequest, RaioXUpdate
from app.services.raio_x_advogado_service import analise_advogado_caso
from app.services.raio_x_export_service import gerar_docx, gerar_pdf
from app.services.raio_x_service import (
    consolidar_relatorio,
    converter_em_caso,
    preview_conversao,
    serializar_analise,
)

settings = get_settings()
router = APIRouter(prefix="/raio-x", tags=["Raio-X do Processo"])

EXTENSOES = {".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg", ".tiff", ".webp"}
MAX_ARQUIVOS = 20


def _role(user: User) -> str:
    return user.role.value if hasattr(user.role, "value") else str(user.role)


def _permitido(user: User) -> bool:
    return _role(user) in {"superadmin", "admin", "socio", "advogado", "advogado_auxiliar", "estagiario"}


# Análise "advogado" (IA agêntica) é operação CARA (até 8 passos, ~R$2/exec):
# estagiário fica de fora (hardening de custo/governança — auditoria Fase D).
def _permitido_ia_advogado(user: User) -> bool:
    return _role(user) in {"superadmin", "admin", "socio", "advogado", "advogado_auxiliar"}


async def _obter(db: AsyncSession, analise_id: str, user: User) -> RaioXAnalise:
    analise = (
        await db.execute(
            select(RaioXAnalise)
            .options(selectinload(RaioXAnalise.documentos))
            .where(RaioXAnalise.id == analise_id, RaioXAnalise.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if not analise:
        raise HTTPException(404, "Análise Raio-X não encontrada")
    if not is_gestao(user) and analise.created_by != user.id:
        raise HTTPException(403, "Sem permissão para esta análise preliminar")
    return analise


# Teto de staleness do processamento assíncrono (Onda 1). O pipeline leva
# 71–87s em produção; muito além disso, o worker morreu sem marcar `erro`
# (kill -9, OOM, deploy no meio) e a análise ficaria presa em
# fila/em_processamento para sempre — 409 permanente nos endpoints de
# análise (achado baixo da auditoria de segurança desta branch).
PROCESSAMENTO_TIMEOUT_MINUTOS = 30


def _processamento_preso(analise: RaioXAnalise) -> bool:
    """fila/em_processamento parada além do teto = worker morreu no meio."""
    if analise.status not in {"fila", "em_processamento"}:
        return False
    ref = analise.updated_at
    if ref is None:
        return True
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - ref > timedelta(
        minutes=PROCESSAMENTO_TIMEOUT_MINUTOS
    )


def _destravar_analise_presa(analise: RaioXAnalise) -> None:
    """Registra o desfecho `erro` da execução morta antes de aceitar o novo lote.

    O caminho normal de erro é a própria task marcar o estado; este é o
    plano B para execução que morreu sem desfecho. A mensagem segue o mesmo
    contrato sanitizado de raio_x_tasks (string legível, sem detalhe interno).
    """
    relatorio = dict(analise.relatorio or {})
    relatorio["erro_processamento"] = (
        "Processamento anterior expirou sem concluir "
        f"(mais de {PROCESSAMENTO_TIMEOUT_MINUTOS} min) e foi destravado."
    )
    relatorio["erro_processamento_em"] = datetime.now(timezone.utc).isoformat()
    analise.relatorio = relatorio
    analise.status = "erro"


def _aplicar_identificacao(analise: RaioXAnalise) -> None:
    report = analise.relatorio or {}
    identification = report.get("identificacao") or {}
    analise.numero_processo = analise.numero_processo or identification.get("numero_processo")
    analise.area = analise.area or identification.get("area")
    analise.subarea = analise.subarea or identification.get("subarea")
    analise.rito = analise.rito or identification.get("rito")
    analise.fase = analise.fase or identification.get("fase") or identification.get("etapa_atual")
    analise.tribunal = analise.tribunal or identification.get("tribunal")
    analise.orgao = analise.orgao or identification.get("orgao")
    analise.unidade = analise.unidade or identification.get("unidade")
    analise.posicao_cliente = analise.posicao_cliente or identification.get("posicao_cliente")
    analise.risco_nivel = report.get("risco_nivel")
    analise.prazo_urgente = bool(report.get("prazo_urgente"))
    analise.dados_extraidos = {
        "identificacao": identification,
        "rito_jornada": report.get("rito_jornada") or {},
        "avaliacao_risco": report.get("avaliacao_risco") or {},
        "fontes": report.get("fontes") or [],
    }


@router.get("/stats")
async def stats(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if not _permitido(user):
        raise HTTPException(403, "Perfil sem acesso ao Raio-X")
    base = select(RaioXAnalise).where(RaioXAnalise.deleted_at.is_(None))
    if not is_gestao(user):
        base = base.where(RaioXAnalise.created_by == user.id)
    rows = (
        await db.execute(
            select(RaioXAnalise.status, func.count(RaioXAnalise.id))
            .where(RaioXAnalise.id.in_(base.with_only_columns(RaioXAnalise.id)))
            .group_by(RaioXAnalise.status)
        )
    ).all()
    status_counts = {status: total for status, total in rows}
    urgent = await db.scalar(
        select(func.count(RaioXAnalise.id)).where(
            RaioXAnalise.id.in_(base.with_only_columns(RaioXAnalise.id)),
            RaioXAnalise.prazo_urgente.is_(True),
        )
    )
    elevated = await db.scalar(
        select(func.count(RaioXAnalise.id)).where(
            RaioXAnalise.id.in_(base.with_only_columns(RaioXAnalise.id)),
            RaioXAnalise.risco_nivel.in_(["elevado", "critico"]),
        )
    )
    return {
        "total": sum(status_counts.values()),
        "por_status": status_counts,
        "pendentes_conferencia": status_counts.get("aguardando_conferencia", 0),
        "convertidos": status_counts.get("convertido_em_caso", 0),
        "urgentes": urgent or 0,
        "risco_elevado_ou_critico": elevated or 0,
    }


@router.get("/")
async def listar(
    search: Optional[str] = None,
    status: Optional[str] = None,
    area: Optional[str] = None,
    risco: Optional[str] = None,
    urgente: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _permitido(user):
        raise HTTPException(403, "Perfil sem acesso ao Raio-X")
    query = select(RaioXAnalise).where(RaioXAnalise.deleted_at.is_(None))
    if not is_gestao(user):
        query = query.where(RaioXAnalise.created_by == user.id)
    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                RaioXAnalise.titulo.ilike(term),
                RaioXAnalise.potencial_cliente.ilike(term),
                RaioXAnalise.numero_processo.ilike(term),
            )
        )
    if status:
        query = query.where(RaioXAnalise.status == status)
    if area:
        query = query.where(RaioXAnalise.area == area)
    if risco:
        query = query.where(RaioXAnalise.risco_nivel == risco)
    if urgente is not None:
        query = query.where(RaioXAnalise.prazo_urgente.is_(urgente))
    count = await db.scalar(select(func.count()).select_from(query.subquery()))
    items = (
        await db.execute(
            query.order_by(RaioXAnalise.prazo_urgente.desc(), RaioXAnalise.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return {
        "data": [serializar_analise(item, False) for item in items],
        "total": count or 0,
        "page": page,
        "page_size": page_size,
    }


@router.post("/", status_code=201)
async def criar(
    payload: RaioXCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _permitido(user):
        raise HTTPException(403, "Perfil sem acesso ao Raio-X")
    now = datetime.now(timezone.utc)
    analise = RaioXAnalise(
        id=str(uuid4()),
        titulo=payload.titulo,
        potencial_cliente=payload.potencial_cliente,
        status="novo",
        created_by=user.id,
        retention_until=now + timedelta(days=payload.retention_days),
    )
    db.add(analise)
    await criar_audit_log(
        db,
        user.id,
        _role(user),
        "CREATE",
        "raio_x_analises",
        analise.id,
        detalhes="Criada análise preliminar; sem cliente/caso oficial",
    )
    await db.commit()
    await db.refresh(analise)
    analise.documentos = []
    return serializar_analise(analise)


@router.get("/contextual/{case_id}")
async def contextual(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await verificar_acesso_caso(db, user, case_id)
    case = (
        await db.execute(select(Case).where(Case.id == case_id, Case.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if not case:
        raise HTTPException(404, "Caso não encontrado")
    docs = (
        await db.execute(select(Document).where(Document.case_id == case_id, Document.deleted_at.is_(None)))
    ).scalars().all()
    deadlines = (
        await db.execute(select(Deadline).where(Deadline.case_id == case_id, Deadline.deleted_at.is_(None)))
    ).scalars().all()
    tasks = (
        await db.execute(select(Task).where(Task.case_id == case_id, Task.deleted_at.is_(None)))
    ).scalars().all()
    report = {
        "modo": "contextual",
        "case_id": case.id,
        "aviso": "Relatório contextual do caso existente. Não cria ou converte cadastros.",
        "identificacao": {
            "titulo": case.titulo,
            "numero_processo": case.numero_processo,
            "area": case.area.value if hasattr(case.area, "value") else case.area,
            "fase": case.fase.value if hasattr(case.fase, "value") else case.fase,
            "tribunal": case.tribunal,
            "parte_contraria": case.parte_contraria,
            "risco": case.risco,
        },
        "sintese_executiva": case.descricao_fatos or "Síntese ainda não registrada.",
        "pontos_fortes": [case.pontos_fortes] if case.pontos_fortes else [],
        "pontos_fracos": [case.pontos_fracos] if case.pontos_fracos else [],
        "tese_principal": case.tese_principal,
        "documentos": [{"id": doc.id, "titulo": doc.titulo, "tipo": doc.tipo} for doc in docs],
        "prazos": [
            {
                "id": deadline.id,
                "titulo": deadline.titulo,
                "data": deadline.data_prazo.isoformat(),
                "confirmado": deadline.confirmado,
            }
            for deadline in deadlines
        ],
        "tarefas": [
            {
                "id": task.id,
                "titulo": task.titulo,
                "status": task.status.value if hasattr(task.status, "value") else task.status,
            }
            for task in tasks
        ],
        "proximos_passos": [
            task.titulo
            for task in tasks
            if str(getattr(task.status, "value", task.status)) != "concluida"
        ],
    }
    await criar_audit_log(
        db,
        user.id,
        _role(user),
        "VIEW",
        "raio_x_contextual",
        case.id,
        detalhes="Raio-X contextual gerado",
    )
    await db.commit()
    return report


@router.post(
    "/contextual/{case_id}/analise-advogado",
    dependencies=[Depends(rate_limit("raio-x-analise-advogado", 5))],
)
async def contextual_analise_advogado(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Análise "advogado sênior" (IA agêntica) do Raio-X contextual de um caso.

    Operação de IA deliberada e cara — POST separado do GET contextual (que
    permanece idêntico, sem IA). Atrás de AI_AGENT_ENABLED: com a flag OFF o
    serviço devolve status "indisponivel" e nada muda no sistema.
    """
    if not _permitido_ia_advogado(user):
        raise HTTPException(403, "Perfil sem acesso à análise do advogado (IA)")
    resultado = await analise_advogado_caso(db, user, case_id)
    # Audita TODO desfecho (ok/indisponivel/erro) — operação de IA cara não passa
    # sem trilha (rate-limit/custo consumidos mesmo em falha).
    await criar_audit_log(
        db, user.id, _role(user), "AI_USE", "raio_x_contextual", case_id,
        detalhes=f"Análise do advogado (IA) — Raio-X contextual [{resultado.get('status')}]",
    )
    await db.commit()
    return resultado


@router.get("/{analise_id}")
async def detalhar(
    analise_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    analise = await _obter(db, analise_id, user)
    await criar_audit_log(db, user.id, _role(user), "VIEW", "raio_x_analises", analise.id)
    await db.commit()
    return serializar_analise(analise)


@router.patch("/{analise_id}")
async def atualizar(
    analise_id: str,
    payload: RaioXUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    analise = await _obter(db, analise_id, user)
    if analise.status == "convertido_em_caso":
        raise HTTPException(409, "Relatório convertido está congelado para auditoria")
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("status") == "convertido_em_caso":
        raise HTTPException(422, "Status reservado à conversão confirmada em caso")
    before = serializar_analise(analise, False)
    for key, value in updates.items():
        setattr(analise, key, value)

    review = updates.get("revisao_humana")
    if isinstance(review, dict):
        report = dict(analise.relatorio or {})
        identification = dict(report.get("identificacao") or {})
        reviewed_identification = review.get("identificacao")
        if isinstance(reviewed_identification, dict):
            for key, value in reviewed_identification.items():
                if value not in (None, ""):
                    identification[key] = value
                    if hasattr(analise, key):
                        setattr(analise, key, value)
        if review.get("sintese_revisada"):
            report["sintese_executiva_revisada"] = review["sintese_revisada"]
        for key in (
            "partes_revisadas", "pedidos_revisados", "provas_revisadas",
            "prazos_revisados", "riscos_revisados", "contradicoes_revisadas",
        ):
            if key in review:
                report[key] = review[key]
        report["identificacao"] = identification
        report["revisao_humana_aplicada"] = True
        analise.relatorio = report

    await criar_audit_log(
        db,
        user.id,
        _role(user),
        "UPDATE",
        "raio_x_analises",
        analise.id,
        dados_antes=before,
        dados_depois=updates,
    )
    await db.commit()
    await db.refresh(analise)
    return serializar_analise(analise)


@router.post(
    "/{analise_id}/documentos/analisar",
    dependencies=[Depends(rate_limit("raio-x-upload", 10))],
)
async def analisar_documentos(
    analise_id: str,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Recebe o lote, persiste os documentos e ENFILEIRA a análise (Onda 1).

    A extração + IA (71–87s em produção) roda fora do request, em
    app/tasks/raio_x_tasks.py: aqui só validação barata, gravação em disco e
    despacho. Estados observáveis via GET: fila → em_processamento →
    aguardando_conferencia | documentos_pendentes | erro.
    """
    analise = await _obter(db, analise_id, user)
    if analise.status == "convertido_em_caso":
        raise HTTPException(409, "Análise já convertida; o relatório está congelado")
    if analise.status in {"fila", "em_processamento"}:
        if not _processamento_preso(analise):
            raise HTTPException(
                409, "Análise em processamento; aguarde a conclusão do lote atual"
            )
        _destravar_analise_presa(analise)
    if not files or len(files) > MAX_ARQUIVOS:
        raise HTTPException(422, f"Envie de 1 a {MAX_ARQUIVOS} arquivos por lote")

    existing_hashes = {doc.sha256 for doc in analise.documentos}
    novos: list[RaioXDocumento] = []
    duplicados: list[str] = []
    erros: list[dict[str, str]] = []
    from app.routers.documents import _validar_conteudo

    for upload in files:
        filename = Path(upload.filename or "documento").name[:255]
        ext = Path(filename).suffix.lower()
        if ext not in EXTENSOES:
            erros.append({"arquivo": filename, "erro": "Formato não suportado"})
            continue
        content = await upload.read()
        if not content:
            erros.append({"arquivo": filename, "erro": "Arquivo vazio"})
            continue
        if len(content) > settings.MAX_UPLOAD_MB * 1024 * 1024:
            erros.append({"arquivo": filename, "erro": f"Excede {settings.MAX_UPLOAD_MB} MB"})
            continue
        digest = hashlib.sha256(content).hexdigest()
        if digest in existing_hashes:
            duplicados.append(filename)
            continue
        try:
            mime_real = _validar_conteudo(ext, content)
        except HTTPException as exc:
            erros.append({"arquivo": filename, "erro": str(exc.detail)[:300]})
            continue
        now = datetime.now(timezone.utc)
        rel = Path("raio-x") / f"{now.year}" / f"{now.month:02d}" / analise.id / f"{uuid4()}{ext}"
        full = Path(settings.UPLOAD_DIR) / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(full, "wb") as target:
            await target.write(content)
        # Documento PENDENTE: resultado_analise vazio até a task preencher.
        doc = RaioXDocumento(
            id=str(uuid4()),
            analise_id=analise.id,
            nome_original=filename,
            filepath=str(rel),
            mimetype=mime_real,
            size_bytes=len(content),
            sha256=digest,
            ocr_utilizado=ext in {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".webp"},
            resultado_analise={},
            uploaded_by=user.id,
        )
        db.add(doc)
        novos.append(doc)
        existing_hashes.add(digest)

    if novos:
        analise.status = "fila"
    await criar_audit_log(
        db,
        user.id,
        _role(user),
        "UPLOAD",
        "raio_x_analises",
        analise.id,
        detalhes=(
            f"{len(novos)} documento(s) enfileirado(s) para análise; "
            f"{len(duplicados)} duplicado(s); {len(erros)} erro(s) de validação"
        ),
        dados_depois={
            "documentos": [doc.id for doc in novos],
            "duplicados": duplicados,
            "erros": erros,
        },
    )
    await db.commit()

    processamento = None
    if novos:
        from app.tasks.raio_x_tasks import agendar_analise

        processamento = await agendar_analise(
            analise.id,
            user.id,
            _role(user),
            documento_ids=[doc.id for doc in novos],
            reprocessar=False,
            background_tasks=background_tasks,
        )
    refreshed = await _obter(db, analise.id, user)
    return {
        "analise": serializar_analise(refreshed),
        "duplicados": duplicados,
        "erros": erros,
        "processamento": processamento,
    }


@router.post("/{analise_id}/reanalisar")
async def reanalisar(
    analise_id: str,
    background_tasks: BackgroundTasks,
    reprocessar: bool = Query(False, description="Quando true, refaz OCR/extração de todos os documentos"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    analise = await _obter(db, analise_id, user)
    if analise.status == "convertido_em_caso":
        raise HTTPException(409, "Relatório convertido está congelado")
    if analise.status in {"fila", "em_processamento"}:
        if not _processamento_preso(analise):
            raise HTTPException(
                409, "Análise em processamento; aguarde a conclusão do lote atual"
            )
        _destravar_analise_presa(analise)
    errors: list[dict[str, str]] = []
    if reprocessar and analise.documentos:
        # Reprocessamento refaz OCR + IA de todos os documentos — operação
        # longa, vai para a fila (Onda 1); o request só enfileira e responde.
        analise.status = "fila"
        await criar_audit_log(
            db,
            user.id,
            _role(user),
            "REPROCESS",
            "raio_x_analises",
            analise.id,
            dados_depois={"reprocessar": True, "modo": "assincrono"},
        )
        await db.commit()
        from app.tasks.raio_x_tasks import agendar_analise

        processamento = await agendar_analise(
            analise.id,
            user.id,
            _role(user),
            documento_ids=None,
            reprocessar=True,
            background_tasks=background_tasks,
        )
        return {
            "analise": serializar_analise(analise),
            "erros": errors,
            "reprocessado": True,
            "processamento": processamento,
        }
    # Reconsolidação síncrona (sem IA, barata): comportamento anterior mantido.
    analise.relatorio = consolidar_relatorio(list(analise.documentos))
    _aplicar_identificacao(analise)
    preview = await preview_conversao(db, analise)
    analise.alertas_conflito = preview.get("alertas_conflito") or []
    analise.status = "aguardando_conferencia" if analise.documentos else "documentos_pendentes"
    await criar_audit_log(
        db,
        user.id,
        _role(user),
        "REPROCESS" if reprocessar else "RECONSOLIDATE",
        "raio_x_analises",
        analise.id,
        dados_depois={"reprocessar": reprocessar, "erros": errors},
    )
    await db.commit()
    return {"analise": serializar_analise(analise), "erros": errors, "reprocessado": reprocessar}


@router.post(
    "/{analise_id}/analise-advogado",
    dependencies=[Depends(rate_limit("raio-x-analise-advogado", 5))],
)
async def analise_advogado_por_documentos(
    analise_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Análise "advogado sênior" (IA agêntica) sobre uma análise preliminar por
    documentos: injeta o relatório consolidado do Raio-X como contexto.

    Exige caso vinculado (a análise preliminar é isolada de casos): o agente
    precisa de um caso para RBAC/ownership e para o modo de sanitização LGPD
    derivado da área. Sem caso vinculado → 409 orientando a conversão.
    """
    if not _permitido_ia_advogado(user):
        raise HTTPException(403, "Perfil sem acesso à análise do advogado (IA)")
    analise = await _obter(db, analise_id, user)
    case_id = analise.convertido_case_id or analise.origem_contextual_case_id
    if not case_id:
        raise HTTPException(
            409,
            "Análise preliminar sem caso vinculado. Converta em caso (ou use o "
            "Raio-X contextual de um caso) para a análise do advogado (IA).",
        )
    base_relatorio = analise.relatorio or None
    resultado = await analise_advogado_caso(
        db, user, case_id, base_relatorio=base_relatorio,
    )
    # Audita TODO desfecho (ok/indisponivel/erro) — ver endpoint contextual.
    await criar_audit_log(
        db, user.id, _role(user), "AI_USE", "raio_x_analises", analise_id,
        detalhes=f"Análise do advogado (IA) — Raio-X por documentos [{resultado.get('status')}]",
    )
    await db.commit()
    return resultado


@router.get("/{analise_id}/documentos/{documento_id}/download")
async def download(
    analise_id: str,
    documento_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    analise = await _obter(db, analise_id, user)
    doc = next((item for item in analise.documentos if item.id == documento_id), None)
    if not doc:
        raise HTTPException(404, "Documento preliminar não encontrado")
    full = Path(settings.UPLOAD_DIR) / doc.filepath
    if not full.exists():
        raise HTTPException(404, "Arquivo físico indisponível")
    await criar_audit_log(
        db,
        user.id,
        _role(user),
        "DOWNLOAD",
        "raio_x_documentos",
        doc.id,
        detalhes=doc.nome_original,
    )
    await db.commit()
    return FileResponse(str(full), filename=doc.nome_original, media_type=doc.mimetype)


@router.get("/{analise_id}/exportar")
async def exportar(
    analise_id: str,
    formato: str = Query("pdf", pattern="^(pdf|docx)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    analise = await _obter(db, analise_id, user)
    report = analise.relatorio or {}
    if not report:
        raise HTTPException(409, "A análise ainda não possui relatório para exportação")
    if formato == "docx":
        content = gerar_docx(analise.titulo, report)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        content = gerar_pdf(analise.titulo, report)
        media = "application/pdf"
    filename = f"raio-x-{analise.id}.{formato}"
    await criar_audit_log(
        db,
        user.id,
        _role(user),
        "EXPORT",
        "raio_x_analises",
        analise.id,
        detalhes=f"Exportação {formato.upper()}",
    )
    await db.commit()
    return StreamingResponse(
        io.BytesIO(content),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{analise_id}/conversao/preview")
async def conversao_preview(
    analise_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    analise = await _obter(db, analise_id, user)
    return await preview_conversao(db, analise)


@router.post("/{analise_id}/converter")
async def converter(
    analise_id: str,
    payload: RaioXConverterRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    analise = await _obter(db, analise_id, user)
    if analise.status not in {"aguardando_conferencia", "em_analise", "analise_concluida", "convertido_em_caso"}:
        raise HTTPException(409, "Conclua e confira a análise antes da conversão")
    try:
        return await converter_em_caso(db, analise, payload, user)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(409, str(exc))


@router.post("/{analise_id}/arquivar")
async def arquivar(
    analise_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    analise = await _obter(db, analise_id, user)
    if analise.status == "convertido_em_caso":
        raise HTTPException(409, "Análise convertida deve ser preservada para auditoria")
    analise.status = "arquivado"
    analise.archived_at = datetime.now(timezone.utc)
    await criar_audit_log(db, user.id, _role(user), "ARCHIVE", "raio_x_analises", analise.id)
    await db.commit()
    return {"ok": True, "status": analise.status}


@router.post("/{analise_id}/descartar")
async def descartar(
    analise_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    analise = await _obter(db, analise_id, user)
    if analise.status == "convertido_em_caso":
        raise HTTPException(409, "Análise convertida não pode ser descartada")
    analise.status = "descartado"
    analise.discarded_at = datetime.now(timezone.utc)
    await criar_audit_log(db, user.id, _role(user), "DISCARD", "raio_x_analises", analise.id)
    await db.commit()
    return {"ok": True, "status": analise.status}


@router.delete("/{analise_id}")
async def excluir(
    analise_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    analise = await _obter(db, analise_id, user)
    if analise.status == "convertido_em_caso":
        raise HTTPException(409, "Análise convertida deve ser preservada para auditoria")
    if analise.retention_until and analise.retention_until > datetime.now(timezone.utc) and not is_gestao(user):
        raise HTTPException(409, "Prazo de retenção vigente; arquive ou solicite exclusão à gestão")
    analise.deleted_at = datetime.now(timezone.utc)
    await criar_audit_log(
        db,
        user.id,
        _role(user),
        "DELETE",
        "raio_x_analises",
        analise.id,
        detalhes="Soft delete controlado",
    )
    await db.commit()
    return {"ok": True}
