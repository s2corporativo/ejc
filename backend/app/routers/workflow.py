# ── app/routers/workflow.py ────────────────────────────────────────────────────
# BPM Workflow — templates, instâncias por caso e avanço de etapas.
from __future__ import annotations
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User
from app.models.workflow import WorkflowTemplate, WorkflowEtapa, CaseWorkflow, WorkflowHistorico, WorkflowStatus
from app.modules.auditoria.middleware import registrar_acao

router = APIRouter(prefix="/workflow", tags=["BPM Workflow"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class EtapaIn(BaseModel):
    nome:             str = Field(min_length=2, max_length=100)
    descricao:        Optional[str] = None
    ordem:            int = 0
    sla_dias_uteis:   Optional[int] = None
    cor:              Optional[str] = None
    obrigatoria:      bool = True
    acao_automatica:  Optional[str] = None  # notificar|criar_tarefa|alerta_prazo|nenhuma


class TemplateIn(BaseModel):
    nome:          str = Field(min_length=3, max_length=200)
    descricao:     Optional[str] = None
    area_juridica: Optional[str] = None
    is_default:    bool = False
    etapas:        list[EtapaIn] = []


class AvancarEtapaReq(BaseModel):
    proxima_etapa_id: str
    observacao:       Optional[str] = None
    sla_respeitado:   Optional[bool] = None


class IniciarWorkflowReq(BaseModel):
    template_id: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pode_editar(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["advogado"]

def _out_etapa(e: WorkflowEtapa) -> dict:
    return {
        "id": e.id, "template_id": e.template_id, "nome": e.nome,
        "descricao": e.descricao, "ordem": e.ordem,
        "sla_dias_uteis": e.sla_dias_uteis, "cor": e.cor,
        "obrigatoria": e.obrigatoria, "acao_automatica": e.acao_automatica,
    }

def _out_template(t: WorkflowTemplate, etapas: list = []) -> dict:
    return {
        "id": t.id, "nome": t.nome, "descricao": t.descricao,
        "area_juridica": t.area_juridica, "is_default": t.is_default,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "etapas": etapas,
    }

def _out_case_wf(cw: CaseWorkflow) -> dict:
    return {
        "id": cw.id, "case_id": cw.case_id, "template_id": cw.template_id,
        "etapa_atual_id": cw.etapa_atual_id,
        "status": cw.status.value if hasattr(cw.status, "value") else cw.status,
        "iniciado_em": cw.iniciado_em.isoformat() if cw.iniciado_em else None,
        "concluido_em": cw.concluido_em.isoformat() if cw.concluido_em else None,
    }


# ── Endpoints — Templates ─────────────────────────────────────────────────────

@router.get("/templates")
async def listar_templates(
    area: Optional[str] = Query(None),
    db:   AsyncSession = Depends(get_db),
    cu:   User = Depends(get_current_user),
):
    q = select(WorkflowTemplate).where(WorkflowTemplate.deleted_at.is_(None))
    if area:
        q = q.where(WorkflowTemplate.area_juridica.ilike(f"%{area}%"))
    templates = (await db.execute(q.order_by(WorkflowTemplate.is_default.desc(), WorkflowTemplate.nome))).scalars().all()
    result = []
    for t in templates:
        etapas = (await db.execute(
            select(WorkflowEtapa).where(WorkflowEtapa.template_id == t.id).order_by(WorkflowEtapa.ordem)
        )).scalars().all()
        result.append(_out_template(t, [_out_etapa(e) for e in etapas]))
    return result


@router.post("/templates", status_code=201)
async def criar_template(
    req: TemplateIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)

    t = WorkflowTemplate(
        id=str(uuid4()), created_by=cu.id,
        nome=req.nome, descricao=req.descricao,
        area_juridica=req.area_juridica, is_default=req.is_default,
    )
    db.add(t)
    await db.flush()

    etapas_criadas = []
    for i, ep in enumerate(req.etapas):
        e = WorkflowEtapa(id=str(uuid4()), template_id=t.id, **ep.model_dump())
        if e.ordem == 0:
            e.ordem = i + 1
        db.add(e)
        etapas_criadas.append(e)

    await db.commit()
    return _out_template(t, [_out_etapa(e) for e in etapas_criadas])


@router.delete("/templates/{template_id}", status_code=204)
async def arquivar_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        raise HTTPException(403)
    t = (await db.execute(
        select(WorkflowTemplate).where(WorkflowTemplate.id == template_id)
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(404)
    t.deleted_at = datetime.now(timezone.utc)
    await db.commit()


# ── Endpoints — Instâncias por Caso ──────────────────────────────────────────

@router.get("/casos/{case_id}")
async def workflow_do_caso(
    case_id: str,
    db:  AsyncSession = Depends(get_db),
    cu:  User = Depends(get_current_user),
):
    """Retorna o workflow ativo do caso, com etapas e histórico."""
    cw = (await db.execute(
        select(CaseWorkflow).where(
            CaseWorkflow.case_id == case_id,
            CaseWorkflow.status == WorkflowStatus.ativo,
        )
    )).scalar_one_or_none()
    if not cw:
        return {"ativo": False}

    etapas = (await db.execute(
        select(WorkflowEtapa).where(WorkflowEtapa.template_id == cw.template_id).order_by(WorkflowEtapa.ordem)
    )).scalars().all()

    historico = (await db.execute(
        select(WorkflowHistorico).where(WorkflowHistorico.case_workflow_id == cw.id)
        .order_by(WorkflowHistorico.iniciado_em)
    )).scalars().all()

    return {
        **_out_case_wf(cw),
        "etapas": [_out_etapa(e) for e in etapas],
        "historico": [
            {
                "etapa_id": h.etapa_id, "iniciado_em": h.iniciado_em.isoformat() if h.iniciado_em else None,
                "concluido_em": h.concluido_em.isoformat() if h.concluido_em else None,
                "sla_respeitado": h.sla_respeitado, "observacao": h.observacao,
            }
            for h in historico
        ],
    }


@router.post("/casos/{case_id}/iniciar", status_code=201)
async def iniciar_workflow(
    case_id: str,
    req: IniciarWorkflowReq,
    db:  AsyncSession = Depends(get_db),
    cu:  User = Depends(get_current_user),
):
    """Vincula um template de workflow a um caso e inicia na primeira etapa."""
    if not _pode_editar(cu):
        raise HTTPException(403)

    # Verifica template
    t = (await db.execute(
        select(WorkflowTemplate).where(WorkflowTemplate.id == req.template_id,
                                       WorkflowTemplate.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Template não encontrado")

    # Primeira etapa
    primeira = (await db.execute(
        select(WorkflowEtapa).where(WorkflowEtapa.template_id == t.id)
        .order_by(WorkflowEtapa.ordem).limit(1)
    )).scalar_one_or_none()

    cw = CaseWorkflow(
        id=str(uuid4()), case_id=case_id, template_id=t.id,
        etapa_atual_id=primeira.id if primeira else None,
        created_by=cu.id,
    )
    db.add(cw)
    await db.flush()

    if primeira:
        hist = WorkflowHistorico(
            id=str(uuid4()), case_workflow_id=cw.id,
            etapa_id=primeira.id, responsavel_id=cu.id,
        )
        db.add(hist)

    await db.commit()
    await registrar_acao(db, cu.id, "iniciar", "workflow", cw.id,
                         f"Workflow '{t.nome}' iniciado no caso {case_id}")
    return _out_case_wf(cw)


@router.post("/casos/{case_id}/avancar")
async def avancar_etapa(
    case_id: str,
    req: AvancarEtapaReq,
    db:  AsyncSession = Depends(get_db),
    cu:  User = Depends(get_current_user),
):
    """Avança o workflow para a próxima etapa e registra no histórico."""
    if not _pode_editar(cu):
        raise HTTPException(403)

    cw = (await db.execute(
        select(CaseWorkflow).where(CaseWorkflow.case_id == case_id,
                                   CaseWorkflow.status == WorkflowStatus.ativo)
    )).scalar_one_or_none()
    if not cw:
        raise HTTPException(404, "Workflow ativo não encontrado para este caso")

    # Conclui etapa atual no histórico
    hist_atual = (await db.execute(
        select(WorkflowHistorico).where(
            WorkflowHistorico.case_workflow_id == cw.id,
            WorkflowHistorico.etapa_id == cw.etapa_atual_id,
            WorkflowHistorico.concluido_em.is_(None),
        )
    )).scalar_one_or_none()
    if hist_atual:
        hist_atual.concluido_em = datetime.now(timezone.utc)
        hist_atual.sla_respeitado = req.sla_respeitado
        if req.observacao:
            hist_atual.observacao = req.observacao

    # Avança para próxima etapa
    proxima = (await db.execute(
        select(WorkflowEtapa).where(WorkflowEtapa.id == req.proxima_etapa_id)
    )).scalar_one_or_none()
    if not proxima:
        raise HTTPException(404, "Etapa não encontrada")

    cw.etapa_atual_id = proxima.id
    hist_nova = WorkflowHistorico(
        id=str(uuid4()), case_workflow_id=cw.id,
        etapa_id=proxima.id, responsavel_id=cu.id,
    )
    db.add(hist_nova)
    await db.commit()
    return {"etapa_atual": _out_etapa(proxima)}


@router.post("/casos/{case_id}/concluir")
async def concluir_workflow(
    case_id: str,
    db:  AsyncSession = Depends(get_db),
    cu:  User = Depends(get_current_user),
):
    """Marca o workflow do caso como concluído."""
    if not _pode_editar(cu):
        raise HTTPException(403)
    cw = (await db.execute(
        select(CaseWorkflow).where(CaseWorkflow.case_id == case_id,
                                   CaseWorkflow.status == WorkflowStatus.ativo)
    )).scalar_one_or_none()
    if not cw:
        raise HTTPException(404)
    cw.status = WorkflowStatus.concluido
    cw.concluido_em = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "concluido"}
