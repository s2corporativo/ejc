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
from app.core.ownership import verificar_acesso_caso
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.redesign import AreaModuloMapping
from app.models.user import User
from app.models.workflow import WorkflowTemplate, WorkflowEtapa, CaseWorkflow, WorkflowHistorico, WorkflowStatus
from app.modules.auditoria.middleware import registrar_acao

router = APIRouter(prefix="/workflow", tags=["BPM Workflow"])

# Workflow "em andamento" = ativo OU atrasado (SLA estourado, mas ainda corre).
# Sem incluir 'atrasado' aqui, um workflow marcado pelo scheduler ficaria
# travado (avancar/concluir só achavam status='ativo').
_STATUS_EM_ANDAMENTO = (WorkflowStatus.ativo, WorkflowStatus.atrasado)


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

def _bloquear_caso_fechado(case) -> None:
    """FLX-065: caso encerrado/arquivado não movimenta workflow — espelha a
    guarda do orquestrador (routers/orquestrador.py): o advogado precisa
    reabrir/desarquivar o caso antes de qualquer mutação."""
    status_caso = getattr(case.status, "value", case.status)
    if status_caso in ("encerrado", "arquivado"):
        raise HTTPException(
            409, f"Caso {status_caso} — reabra o caso para alterar o workflow."
        )

async def _etapas_visitadas(db: AsyncSession, cw: CaseWorkflow) -> set:
    """Ids de etapa que o workflow já visitou (histórico ∪ etapa atual)."""
    visitadas = set((await db.execute(
        select(WorkflowHistorico.etapa_id)
        .where(WorkflowHistorico.case_workflow_id == cw.id)
    )).scalars().all())
    if cw.etapa_atual_id:
        visitadas.add(cw.etapa_atual_id)
    return visitadas

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
    # Etapas de TODOS os templates em UMA query, agrupadas por template (evita N+1).
    template_ids = [t.id for t in templates]
    etapas_por_template: dict[str, list] = {tid: [] for tid in template_ids}
    if template_ids:
        todas_etapas = (await db.execute(
            select(WorkflowEtapa)
            .where(WorkflowEtapa.template_id.in_(template_ids))
            .order_by(WorkflowEtapa.template_id, WorkflowEtapa.ordem)
        )).scalars().all()
        for e in todas_etapas:
            etapas_por_template.setdefault(e.template_id, []).append(e)
    result = []
    for t in templates:
        etapas = etapas_por_template.get(t.id, [])
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
    """Retorna o workflow em andamento (ativo/atrasado) do caso, com etapas e histórico."""
    await verificar_acesso_caso(db, cu, case_id)  # gate ownership (sigilo EOAB/LGPD)
    cw = (await db.execute(
        select(CaseWorkflow).where(
            CaseWorkflow.case_id == case_id,
            CaseWorkflow.status.in_(_STATUS_EM_ANDAMENTO),
        ).order_by(CaseWorkflow.iniciado_em.desc())
    )).scalars().first()
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
    case = await verificar_acesso_caso(db, cu, case_id)  # gate ownership (sigilo EOAB/LGPD)
    _bloquear_caso_fechado(case)

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


@router.post("/casos/{case_id}/aplicar-padrao", status_code=201)
async def aplicar_workflow_padrao(
    case_id: str,
    db:  AsyncSession = Depends(get_db),
    cu:  User = Depends(get_current_user),
):
    """Auto-aplica o workflow padrão da ÁREA do caso (R9 / Seção 11 do redesign).

    Resolução do template, nesta ordem:
      (a) AreaModuloMapping da área do caso com workflow_template_id preenchido;
      (b) WorkflowTemplate com area_juridica == área do caso e is_default=true;
      (c) 404 com mensagem clara.
    Inicia o workflow na primeira etapa, como o /iniciar.
    """
    if not _pode_editar(cu):
        raise HTTPException(403)
    case = await verificar_acesso_caso(db, cu, case_id)
    _bloquear_caso_fechado(case)

    # Não empilha workflows: um em andamento por caso.
    existente = (await db.execute(
        select(CaseWorkflow.id).where(
            CaseWorkflow.case_id == case_id,
            CaseWorkflow.status.in_(_STATUS_EM_ANDAMENTO),
        ).limit(1)
    )).scalar_one_or_none()
    if existente:
        raise HTTPException(409, "O caso já possui um workflow em andamento")

    area = case.area.value if hasattr(case.area, "value") else str(case.area)

    # (a) matriz área → módulos com template vinculado
    template = None
    mapping = (await db.execute(
        select(AreaModuloMapping).where(
            func.lower(AreaModuloMapping.area_juridica) == area.lower(),
            AreaModuloMapping.workflow_template_id.isnot(None),
            AreaModuloMapping.habilitado.is_(True),
        ).order_by(AreaModuloMapping.ordem)
    )).scalars().first()
    if mapping:
        template = (await db.execute(
            select(WorkflowTemplate).where(
                WorkflowTemplate.id == mapping.workflow_template_id,
                WorkflowTemplate.deleted_at.is_(None),
            )
        )).scalar_one_or_none()

    # (b) template default da área
    if not template:
        template = (await db.execute(
            select(WorkflowTemplate).where(
                WorkflowTemplate.deleted_at.is_(None),
                WorkflowTemplate.is_default.is_(True),
                func.lower(WorkflowTemplate.area_juridica) == area.lower(),
            ).order_by(WorkflowTemplate.created_at)
        )).scalars().first()

    # (c) nada configurado — orienta o usuário
    if not template:
        raise HTTPException(
            404,
            f"Nenhum workflow padrão configurado para a área '{area}'. "
            "Vincule um template na matriz Área→Módulos (workflow_template_id) "
            "ou marque um template dessa área como padrão (is_default).",
        )

    primeira = (await db.execute(
        select(WorkflowEtapa).where(WorkflowEtapa.template_id == template.id)
        .order_by(WorkflowEtapa.ordem).limit(1)
    )).scalar_one_or_none()

    cw = CaseWorkflow(
        id=str(uuid4()), case_id=case_id, template_id=template.id,
        etapa_atual_id=primeira.id if primeira else None,
        created_by=cu.id,
    )
    db.add(cw)
    await db.flush()
    if primeira:
        db.add(WorkflowHistorico(
            id=str(uuid4()), case_workflow_id=cw.id,
            etapa_id=primeira.id, responsavel_id=cu.id,
        ))
    await db.commit()
    await registrar_acao(db, cu.id, "aplicar_padrao", "workflow", cw.id,
                         f"Workflow padrão '{template.nome}' (área {area}) "
                         f"aplicado ao caso {case_id}")
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
    case = await verificar_acesso_caso(db, cu, case_id)  # gate ownership (sigilo EOAB/LGPD)
    _bloquear_caso_fechado(case)

    cw = (await db.execute(
        select(CaseWorkflow).where(CaseWorkflow.case_id == case_id,
                                   CaseWorkflow.status.in_(_STATUS_EM_ANDAMENTO))
        .order_by(CaseWorkflow.iniciado_em.desc())
    )).scalars().first()
    if not cw:
        raise HTTPException(404, "Workflow ativo não encontrado para este caso")

    # FLX-062: a próxima etapa precisa pertencer ao MESMO template do workflow
    # (mesmo escopo já usado em workflow_do_caso/iniciar/aplicar-padrão) —
    # sem isso, uma etapa de template alheio corrompia instância e histórico.
    proxima = (await db.execute(
        select(WorkflowEtapa).where(
            WorkflowEtapa.id == req.proxima_etapa_id,
            WorkflowEtapa.template_id == cw.template_id,
        )
    )).scalar_one_or_none()
    if not proxima:
        existe = (await db.execute(
            select(WorkflowEtapa.id).where(WorkflowEtapa.id == req.proxima_etapa_id)
        )).scalar_one_or_none()
        if existe:
            raise HTTPException(422, "Etapa não pertence ao template deste workflow")
        raise HTTPException(404, "Etapa não encontrada")
    if proxima.id == cw.etapa_atual_id:
        raise HTTPException(422, "O workflow já está nesta etapa")

    atual = None
    if cw.etapa_atual_id:
        atual = (await db.execute(
            select(WorkflowEtapa).where(WorkflowEtapa.id == cw.etapa_atual_id)
        )).scalar_one_or_none()

    # FLX-062: avanço PARA FRENTE não pode pular etapa obrigatória jamais
    # cumprida (histórico ∪ etapa atual). Retroceder (ordem menor) é permitido.
    # Sem etapa atual válida (etapa_atual_id nulo ou órfão), tratamos como
    # início do fluxo: toda obrigatória anterior à próxima precisa ter sido
    # visitada — antes, a guarda era pulada em silêncio nesse cenário.
    if atual is None or proxima.ordem > atual.ordem:
        visitadas = await _etapas_visitadas(db, cw)
        cond = [
            WorkflowEtapa.template_id == cw.template_id,
            WorkflowEtapa.obrigatoria.is_(True),
            WorkflowEtapa.ordem < proxima.ordem,
        ]
        if atual is not None:
            cond.append(WorkflowEtapa.ordem > atual.ordem)
        intermediarias = (await db.execute(
            select(WorkflowEtapa).where(*cond).order_by(WorkflowEtapa.ordem)
        )).scalars().all()
        pendentes = [e.nome for e in intermediarias if e.id not in visitadas]
        if pendentes:
            raise HTTPException(
                422,
                "Não é possível pular etapa(s) obrigatória(s) não cumprida(s): "
                + ", ".join(pendentes),
            )

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

    cw.etapa_atual_id = proxima.id
    # Sai do estado 'atrasado' ao avançar — o SLA da nova etapa recomeça.
    if cw.status == WorkflowStatus.atrasado:
        cw.status = WorkflowStatus.ativo
    hist_nova = WorkflowHistorico(
        id=str(uuid4()), case_workflow_id=cw.id,
        etapa_id=proxima.id, responsavel_id=cu.id,
    )
    db.add(hist_nova)
    await db.commit()
    await registrar_acao(db, cu.id, "avancar", "workflow", cw.id,
                         f"Workflow do caso {case_id} avançou para etapa "
                         f"'{proxima.nome}'")
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
    case = await verificar_acesso_caso(db, cu, case_id)  # gate ownership (sigilo EOAB/LGPD)
    _bloquear_caso_fechado(case)
    cw = (await db.execute(
        select(CaseWorkflow).where(CaseWorkflow.case_id == case_id,
                                   CaseWorkflow.status.in_(_STATUS_EM_ANDAMENTO))
        .order_by(CaseWorkflow.iniciado_em.desc())
    )).scalars().first()
    if not cw:
        raise HTTPException(404)

    # FLX-065: não conclui cedo — TODA etapa obrigatória do template precisa
    # ter sido visitada (histórico ∪ etapa atual) antes do encerramento.
    visitadas = await _etapas_visitadas(db, cw)
    obrigatorias = (await db.execute(
        select(WorkflowEtapa).where(
            WorkflowEtapa.template_id == cw.template_id,
            WorkflowEtapa.obrigatoria.is_(True),
        ).order_by(WorkflowEtapa.ordem)
    )).scalars().all()
    pendentes = [e.nome for e in obrigatorias if e.id not in visitadas]
    if pendentes:
        raise HTTPException(
            422,
            "Workflow não pode ser concluído — etapa(s) obrigatória(s) não "
            "visitada(s): " + ", ".join(pendentes),
        )

    agora = datetime.now(timezone.utc)
    # Fecha no histórico a etapa que estava aberta (transição auditável).
    hist_aberto = (await db.execute(
        select(WorkflowHistorico).where(
            WorkflowHistorico.case_workflow_id == cw.id,
            WorkflowHistorico.etapa_id == cw.etapa_atual_id,
            WorkflowHistorico.concluido_em.is_(None),
        ).order_by(WorkflowHistorico.iniciado_em.desc())
    )).scalars().first()
    if hist_aberto:
        hist_aberto.concluido_em = agora

    cw.status = WorkflowStatus.concluido
    cw.concluido_em = agora
    await db.commit()
    await registrar_acao(db, cu.id, "concluir", "workflow", cw.id,
                         f"Workflow do caso {case_id} concluído")
    return {"status": "concluido"}
