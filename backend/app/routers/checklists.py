# ── app/routers/checklists.py ─────────────────────────────────────────────────
# Checklists Jurídicos — templates reutilizáveis + instâncias por caso.
# Fluxo: criar template → instanciar no caso → marcar itens como concluídos.
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.core.ownership import verificar_acesso_caso
from app.models.user import User
from app.models.checklist import (
    ChecklistTemplate, ChecklistTemplateItem, CaseChecklist, CaseChecklistItem,
    ChecklistStatus, ChecklistItemCategoria,
)
from app.modules.auditoria.middleware import registrar_acao

router = APIRouter(prefix="/checklists", tags=["Checklists Jurídicos"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class TemplateItemIn(BaseModel):
    texto:      str = Field(min_length=3, max_length=500)
    dica:       Optional[str] = None
    categoria:  ChecklistItemCategoria = ChecklistItemCategoria.outros
    obrigatorio: bool = True
    ordem:      int = 0


class ChecklistTemplateIn(BaseModel):
    nome:            str = Field(min_length=3, max_length=200)
    descricao:       Optional[str] = None
    area_juridica:   Optional[str] = None
    fase_processual: Optional[str] = None
    tags:            Optional[str] = None
    is_default:      bool = False
    itens:           list[TemplateItemIn] = []


class InstanciarReq(BaseModel):
    case_id:     str
    template_id: str
    nome:        Optional[str] = None   # se None, usa o nome do template
    itens_extras: list[TemplateItemIn] = []   # itens adicionados na instância


class MarcarItemReq(BaseModel):
    concluido:  bool
    observacao: Optional[str] = None


class AddItemReq(BaseModel):
    texto:      str = Field(min_length=3, max_length=500)
    dica:       Optional[str] = None
    categoria:  ChecklistItemCategoria = ChecklistItemCategoria.outros
    obrigatorio: bool = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pode_editar(u: User) -> bool:
    return ROLE_LEVEL.get(u.role.value, 0) >= ROLE_LEVEL["estagiario"]

def _pode_gerenciar(u: User) -> bool:
    return ROLE_LEVEL.get(u.role.value, 0) >= ROLE_LEVEL["advogado"]

def _out_template(t: ChecklistTemplate, itens: list = []) -> dict:
    return {
        "id": t.id, "nome": t.nome, "descricao": t.descricao,
        "area_juridica": t.area_juridica, "fase_processual": t.fase_processual,
        "tags": t.tags, "is_default": t.is_default,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "itens": itens,
    }

def _out_item_template(i: ChecklistTemplateItem) -> dict:
    return {
        "id": i.id, "texto": i.texto, "dica": i.dica,
        "categoria": i.categoria.value if hasattr(i.categoria, "value") else i.categoria,
        "obrigatorio": i.obrigatorio, "ordem": i.ordem,
    }

def _progresso(ck: CaseChecklist) -> float:
    if not ck.total_itens:
        return 0.0
    return round(ck.itens_ok / ck.total_itens * 100, 1)

def _out_checklist(ck: CaseChecklist, itens: list = []) -> dict:
    return {
        "id": ck.id, "case_id": ck.case_id, "template_id": ck.template_id,
        "nome": ck.nome,
        "status": ck.status.value if hasattr(ck.status, "value") else ck.status,
        "total_itens": ck.total_itens, "itens_ok": ck.itens_ok,
        "progresso_pct": _progresso(ck),
        "created_at": ck.created_at.isoformat() if ck.created_at else None,
        "itens": itens,
    }

def _out_case_item(i: CaseChecklistItem) -> dict:
    return {
        "id": i.id, "texto": i.texto, "dica": i.dica,
        "categoria": i.categoria.value if hasattr(i.categoria, "value") else i.categoria,
        "obrigatorio": i.obrigatorio, "ordem": i.ordem,
        "concluido": i.concluido,
        "concluido_em": i.concluido_em.isoformat() if i.concluido_em else None,
        "observacao": i.observacao,
    }


# ── Templates ─────────────────────────────────────────────────────────────────

@router.get("/templates")
async def listar_templates(
    area:       Optional[str]  = Query(None),
    is_default: Optional[bool] = Query(None),
    busca:      Optional[str]  = Query(None),
    db:         AsyncSession = Depends(get_db),
    cu:         User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    q = select(ChecklistTemplate).where(ChecklistTemplate.deleted_at.is_(None))
    if area:
        q = q.where(ChecklistTemplate.area_juridica.ilike(f"%{area}%"))
    if is_default is not None:
        q = q.where(ChecklistTemplate.is_default.is_(is_default))
    if busca:
        q = q.where(ChecklistTemplate.nome.ilike(f"%{busca}%"))
    q = q.options(selectinload(ChecklistTemplate.itens))
    q = q.order_by(ChecklistTemplate.is_default.desc(), ChecklistTemplate.nome)
    templates = (await db.execute(q)).scalars().all()

    # selectinload elimina o N+1: uma query para os itens de todos os templates.
    result = [
        _out_template(t, [_out_item_template(i) for i in t.itens])
        for t in templates
    ]
    return result


@router.post("/templates", status_code=201)
async def criar_template(
    req: ChecklistTemplateIn,
    db:  AsyncSession = Depends(get_db),
    cu:  User = Depends(get_current_user),
):
    if not _pode_gerenciar(cu):
        raise HTTPException(403)
    t = ChecklistTemplate(
        id=str(uuid4()), created_by=cu.id,
        nome=req.nome, descricao=req.descricao,
        area_juridica=req.area_juridica, fase_processual=req.fase_processual,
        tags=req.tags, is_default=req.is_default,
    )
    db.add(t)
    await db.flush()

    itens_criados = []
    for idx, it in enumerate(req.itens):
        item = ChecklistTemplateItem(
            id=str(uuid4()), template_id=t.id,
            ordem=it.ordem if it.ordem else idx + 1,
            **{k: v for k, v in it.model_dump().items() if k != "ordem"},
        )
        item.ordem = it.ordem if it.ordem else idx + 1
        db.add(item)
        itens_criados.append(item)

    await db.commit()
    return _out_template(t, [_out_item_template(i) for i in itens_criados])


@router.delete("/templates/{template_id}", status_code=204)
async def remover_template(
    template_id: str,
    db:  AsyncSession = Depends(get_db),
    cu:  User = Depends(get_current_user),
):
    # Issue #578: autor (advogado+) remove o PRÓPRIO template; sócio+ remove
    # qualquer um. Estagiário/perfis abaixo continuam bloqueados de vez —
    # nunca chegam a "é o autor?" porque não têm _pode_gerenciar (piso
    # advogado; `_pode_editar` deste arquivo é o piso ESTAGIÁRIO — nomes
    # trocados em relação a prompts_juridicos.py, cuidado ao portar padrão).
    if not _pode_gerenciar(cu):
        raise HTTPException(403, "Perfil sem autorização para remover template")
    t = (await db.execute(
        select(ChecklistTemplate).where(
            ChecklistTemplate.id == template_id,
            ChecklistTemplate.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(404)
    e_autor = t.created_by == cu.id
    e_socio = ROLE_LEVEL.get(cu.role.value, 0) >= ROLE_LEVEL["socio"]
    if not (e_autor or e_socio):
        raise HTTPException(403, "Apenas o autor ou sócio+ podem remover este template")
    t.deleted_at = datetime.now(timezone.utc)
    await db.commit()


# ── Instâncias por Caso ───────────────────────────────────────────────────────

@router.post("/instanciar", status_code=201)
async def instanciar_checklist(
    req: InstanciarReq,
    db:  AsyncSession = Depends(get_db),
    cu:  User = Depends(get_current_user),
):
    """
    Cria uma instância de checklist para um caso a partir de um template.
    Todos os itens do template são copiados para a instância.
    """
    if not _pode_editar(cu):
        raise HTTPException(403)
    # IDOR: só quem atua no caso (ou gestão) instancia checklist nele.
    await verificar_acesso_caso(db, cu, req.case_id)

    template = (await db.execute(
        select(ChecklistTemplate).where(
            ChecklistTemplate.id == req.template_id,
            ChecklistTemplate.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not template:
        raise HTTPException(404, "Template não encontrado")

    itens_template = (await db.execute(
        select(ChecklistTemplateItem)
        .where(ChecklistTemplateItem.template_id == template.id)
        .order_by(ChecklistTemplateItem.ordem)
    )).scalars().all()

    total = len(itens_template) + len(req.itens_extras)
    ck = CaseChecklist(
        id=str(uuid4()), case_id=req.case_id,
        template_id=req.template_id,
        nome=req.nome or template.nome,
        total_itens=total,
        created_by=cu.id,
    )
    db.add(ck)
    await db.flush()

    # Copia itens do template
    itens_criados = []
    for it in itens_template:
        ci = CaseChecklistItem(
            id=str(uuid4()), case_checklist_id=ck.id,
            template_item_id=it.id,
            texto=it.texto, dica=it.dica,
            categoria=it.categoria, obrigatorio=it.obrigatorio, ordem=it.ordem,
        )
        db.add(ci)
        itens_criados.append(ci)

    # Itens extras personalizados
    for idx, ex in enumerate(req.itens_extras):
        ci = CaseChecklistItem(
            id=str(uuid4()), case_checklist_id=ck.id,
            texto=ex.texto, dica=ex.dica,
            categoria=ex.categoria, obrigatorio=ex.obrigatorio,
            ordem=1000 + idx,
        )
        db.add(ci)
        itens_criados.append(ci)

    await db.commit()
    await registrar_acao(db, cu.id, "criar", "checklists", ck.id,
                         f"Checklist '{ck.nome}' criado no caso {req.case_id}")
    return _out_checklist(ck, [_out_case_item(i) for i in itens_criados])


# ── #CHK: Geração automática por área + legislação (RAG + IA, HITL) ───────────
# Lógica no serviço único app/services/checklist_ia.py (reusado pelo gatilho
# automático em conversao_caso). Aqui apenas o endpoint manual.

class GerarIAReq(BaseModel):
    gatilho: str = Field("geral", description="pre_processo | pre_protocolo | geral")
    fase:    Optional[str] = None


@router.post("/caso/{case_id}/gerar-ia", status_code=201)
async def gerar_checklist_ia_endpoint(
    case_id: str,
    req:     GerarIAReq,
    db:      AsyncSession = Depends(get_db),
    cu:      User = Depends(get_current_user),
):
    """Gera um checklist RASCUNHO por área + legislação pertinente (RAG + IA).
    HITL/OAB: itens entram como pendentes para revisão humana e NUNCA criam prazos."""
    if not _pode_gerenciar(cu):
        raise HTTPException(403, "Apenas advogado+ pode gerar checklist por IA")
    # Bloco 5 (continuação): só existência era checada — advogado+ de QUALQUER
    # caso podia gerar checklist para caso alheio. verificar_acesso_caso já
    # cobre existência (404) + ownership (403 se não for gestão/responsável).
    await verificar_acesso_caso(db, cu, case_id)

    from app.services.checklist_ia import gerar_checklist_ia
    res = await gerar_checklist_ia(db, case_id, req.gatilho, cu.id)
    if not res:
        raise HTTPException(502, "IA não retornou itens válidos. Tente novamente.")

    await registrar_acao(db, cu.id, "gerar_ia", "checklists", res["id"],
                         f"Checklist IA ({req.gatilho}) — {res['total_itens']} itens (rascunho) no caso {case_id}")
    return {
        **_out_checklist(res["ck"], [_out_case_item(i) for i in res["itens"]]),
        "is_draft": True,
        "modelo": res["modelo"],
        "aviso": "Rascunho gerado por IA com base na legislação — revisão humana obrigatória (OAB). Não cria prazos automaticamente.",
    }


@router.get("/casos/{case_id}")
async def checklists_do_caso(
    case_id: str,
    status:  Optional[str] = Query(None),
    db:      AsyncSession = Depends(get_db),
    cu:      User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    # IDOR: só quem atua no caso (ou gestão) lê os checklists dele.
    await verificar_acesso_caso(db, cu, case_id)
    q = select(CaseChecklist).where(CaseChecklist.case_id == case_id)
    if status:
        q = q.where(CaseChecklist.status == status)
    q = q.options(selectinload(CaseChecklist.itens))
    q = q.order_by(CaseChecklist.created_at.desc())
    checklists = (await db.execute(q)).scalars().all()

    # selectinload elimina o N+1: uma query para os itens de todos os checklists.
    result = [
        _out_checklist(ck, [_out_case_item(i) for i in ck.itens])
        for ck in checklists
    ]
    return result


@router.get("/{checklist_id}")
async def obter_checklist(
    checklist_id: str,
    db:  AsyncSession = Depends(get_db),
    cu:  User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    ck = (await db.execute(
        select(CaseChecklist).where(CaseChecklist.id == checklist_id)
    )).scalar_one_or_none()
    if not ck:
        raise HTTPException(404)
    # IDOR: só quem atua no caso (ou gestão) vê o checklist dele.
    await verificar_acesso_caso(db, cu, ck.case_id)
    itens = (await db.execute(
        select(CaseChecklistItem)
        .where(CaseChecklistItem.case_checklist_id == checklist_id)
        .order_by(CaseChecklistItem.ordem)
    )).scalars().all()
    return _out_checklist(ck, [_out_case_item(i) for i in itens])


@router.patch("/{checklist_id}/itens/{item_id}/marcar")
async def marcar_item(
    checklist_id: str,
    item_id:      str,
    req:          MarcarItemReq,
    db:           AsyncSession = Depends(get_db),
    cu:           User = Depends(get_current_user),
):
    """Marca ou desmarca um item do checklist. Atualiza o progresso automaticamente."""
    if not _pode_editar(cu):
        raise HTTPException(403)

    ck = (await db.execute(
        select(CaseChecklist).where(CaseChecklist.id == checklist_id)
    )).scalar_one_or_none()
    if not ck:
        raise HTTPException(404, "Checklist não encontrado")
    # IDOR: só quem atua no caso (ou gestão) marca itens do checklist dele.
    await verificar_acesso_caso(db, cu, ck.case_id)

    item = (await db.execute(
        select(CaseChecklistItem).where(
            CaseChecklistItem.id == item_id,
            CaseChecklistItem.case_checklist_id == checklist_id,
        )
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Item não encontrado")

    era_concluido = item.concluido
    item.concluido = req.concluido
    item.observacao = req.observacao or item.observacao

    if req.concluido and not era_concluido:
        item.concluido_por = cu.id
        item.concluido_em  = datetime.now(timezone.utc)
        ck.itens_ok = (ck.itens_ok or 0) + 1
    elif not req.concluido and era_concluido:
        item.concluido_por = None
        item.concluido_em  = None
        ck.itens_ok = max(0, (ck.itens_ok or 0) - 1)

    # Auto-conclui checklist quando todos os obrigatórios estiverem ok
    obrigatorios = (await db.execute(
        select(func.count(CaseChecklistItem.id)).where(
            CaseChecklistItem.case_checklist_id == checklist_id,
            CaseChecklistItem.obrigatorio.is_(True),
            CaseChecklistItem.concluido.is_(False),
        )
    )).scalar() or 0
    if obrigatorios == 0 and ck.status == ChecklistStatus.em_andamento:
        ck.status = ChecklistStatus.concluido

    ck.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {
        "item_id":       item_id,
        "concluido":     item.concluido,
        "itens_ok":      ck.itens_ok,
        "progresso_pct": _progresso(ck),
        "status_checklist": ck.status.value if hasattr(ck.status, "value") else ck.status,
    }


@router.post("/{checklist_id}/itens", status_code=201)
async def adicionar_item(
    checklist_id: str,
    req:          AddItemReq,
    db:           AsyncSession = Depends(get_db),
    cu:           User = Depends(get_current_user),
):
    """Adiciona item avulso a uma instância de checklist (não altera o template)."""
    if not _pode_editar(cu):
        raise HTTPException(403)
    ck = (await db.execute(
        select(CaseChecklist).where(CaseChecklist.id == checklist_id)
    )).scalar_one_or_none()
    if not ck:
        raise HTTPException(404)
    # IDOR: só quem atua no caso (ou gestão) adiciona item ao checklist dele.
    await verificar_acesso_caso(db, cu, ck.case_id)

    max_ordem = (await db.execute(
        select(func.max(CaseChecklistItem.ordem))
        .where(CaseChecklistItem.case_checklist_id == checklist_id)
    )).scalar() or 0

    item = CaseChecklistItem(
        id=str(uuid4()), case_checklist_id=checklist_id,
        ordem=max_ordem + 10, **req.model_dump(),
    )
    db.add(item)
    ck.total_itens = (ck.total_itens or 0) + 1
    ck.updated_at  = datetime.now(timezone.utc)
    await db.commit()
    return _out_case_item(item)


@router.delete("/{checklist_id}", status_code=204)
async def cancelar_checklist(
    checklist_id: str,
    db:  AsyncSession = Depends(get_db),
    cu:  User = Depends(get_current_user),
):
    if not _pode_gerenciar(cu):
        raise HTTPException(403)
    ck = (await db.execute(
        select(CaseChecklist).where(CaseChecklist.id == checklist_id)
    )).scalar_one_or_none()
    if not ck:
        raise HTTPException(404)
    # IDOR: só quem atua no caso (ou gestão) cancela o checklist dele.
    await verificar_acesso_caso(db, cu, ck.case_id)
    ck.status = ChecklistStatus.cancelado
    ck.updated_at = datetime.now(timezone.utc)
    await db.commit()
