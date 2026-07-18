# ── app/routers/cases.py ─────────────────────────────────────────────────────
# Gestão de casos: CRUD + numeração DPT-AAAA-NNNN + prescrição automática
# + movimentos (timeline) + endpoint de análise IA integrado.
from __future__ import annotations
from datetime import datetime, timezone, date
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy import select, or_, func as sqlfunc, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, require_roles, ROLE_LEVEL
from app.models.user import User
from app.models.case import Case, CaseMovimento, CaseStatus
from app.models.client import Client
from app.models.audit_log import criar_audit_log
from app.services.deadline_calculator import calcular_prescricao
from app.services.case_intel import triagem_caso, aprendizado_encerramento
from app.services.case_automacao import automacao_caso
from app.services import event_bus
from app.services.documental import gerar_documentos_iniciais
# Mesmo vocabulário/contrato de poderes do kit documental (fonte única do
# schema de procuração conservadora).
from app.routers.kit_documental import KitDocumentalIn, _req_advogado as _req_advogado_kit
from app.models.case_parte import CaseParte
from app.models.caso_area import CasoArea
from app.models.deadline import Deadline, DeadlineTipo, DeadlineStatus
from app.services.extracao_estruturada import parse_data_br
from app.services.movimento_ia import traduzir_movimento
from app.core.ownership import verificar_acesso_caso
from app.services.ia_parser import titulo_e_json_bruto
from app.schemas.case import (
    CaseCreate, CaseUpdate, CaseResponse, CaseDetail, MovimentoCreate,
    CaseDeleteRequest,
)
from app.schemas.common import MsgResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/cases", tags=["Casos"])
_ARQUIVAMENTO_ROLES = ["superadmin", "admin", "socio", "advogado"]


async def _proximo_numero_interno(db: AsyncSession) -> str:
    """Numeração automática DPT-2026-0001 (sequencial por ano).

    Lock consultivo transacional (pg_advisory_xact_lock) serializa criações
    concorrentes no mesmo ano — evita numero_interno duplicado. Ordenação pelo
    sufixo NUMÉRICO (não lexicográfica: 'DPT-2026-10000' < 'DPT-2026-9999')."""
    ano = date.today().year
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:chave))"),
        {"chave": f"numero_interno_{ano}"},
    )
    result = await db.execute(text(r"""
        SELECT numero_interno FROM cases
        WHERE numero_interno LIKE :pref
        ORDER BY CAST(substring(numero_interno FROM '\d+$') AS INTEGER) DESC
        LIMIT 1
    """), {"pref": f"DPT-{ano}-%"})
    ultimo = result.scalar()
    seq = int(ultimo.split("-")[-1]) + 1 if ultimo else 1
    return f"DPT-{ano}-{seq:04d}"


def _filtro_visibilidade(q, user: User):
    """
    LGPD/RBAC: advogado/adv_auxiliar vê apenas seus casos.
    socio+ vê todos.
    """
    if ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["socio"]:
        return q
    return q.where(or_(
        Case.advogado_responsavel_id == user.id,
        Case.advogado_auxiliar_id == user.id,
    ))


@router.get("/")
async def listar(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=500),
    search: Optional[str] = None,
    area: Optional[str] = None,
    status_f: Optional[str] = Query(None, alias="status"),
    arquivo: str = Query("ativos", pattern="^(ativos|arquivados|todos)$"),
    advogado_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(Case).where(Case.deleted_at.is_(None))
    q = _filtro_visibilidade(q, cu)
    # Filtro por advogado: aplicado APÓS _filtro_visibilidade — para socio+
    # permite ver os processos de um advogado específico; para advogado comum
    # é inócuo (no máximo estreita o conjunto já restrito aos próprios casos).
    if advogado_id:
        q = q.where(or_(
            Case.advogado_responsavel_id == advogado_id,
            Case.advogado_auxiliar_id == advogado_id,
        ))
    if arquivo == "ativos":
        q = q.where(Case.status != CaseStatus.arquivado)
    elif arquivo == "arquivados":
        q = q.where(Case.status == CaseStatus.arquivado)
    if search:
        q = q.where(or_(
            Case.titulo.ilike(f"%{search}%"),
            Case.numero_processo.ilike(f"%{search}%"),
            Case.numero_interno.ilike(f"%{search}%"),
            Case.parte_contraria.ilike(f"%{search}%"),
        ))
    if area:
        q = q.where(Case.area == area)
    if status_f:
        q = q.where(Case.status == status_f)
    q = q.order_by(Case.created_at.desc())

    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery())
    )).scalar()
    rows = (await db.execute(
        q.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {
        "data": [CaseResponse.model_validate(c) for c in rows],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/stats")
async def stats_casos(
    advogado_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """BUG-06/BUG-10: fonte ÚNICA de contagem de casos p/ o dashboard.

    TODAS as agregações (total, ativos, encerrados e por_area) filtram
    `deleted_at IS NULL` sobre o MESMO conjunto e respeitam a visibilidade do
    usuário — elimina divergência entre header/cards e o gráfico por área.
    - ativos    = status != 'encerrado'
    - encerrados = status == 'encerrado'
    - por_area  = contagem por área sobre o MESMO conjunto (nenhuma área some).
    """
    base_q = _filtro_visibilidade(
        select(Case).where(Case.deleted_at.is_(None)), cu
    )
    # Mesmo filtro opcional do listar (após visibilidade) — mantém o dashboard
    # consistente com a listagem quando filtrado por advogado.
    if advogado_id:
        base_q = base_q.where(or_(
            Case.advogado_responsavel_id == advogado_id,
            Case.advogado_auxiliar_id == advogado_id,
        ))
    base = base_q.subquery()

    total = (await db.execute(
        select(sqlfunc.count()).select_from(base)
    )).scalar() or 0
    encerrados = (await db.execute(
        select(sqlfunc.count()).select_from(base)
        .where(base.c.status == CaseStatus.encerrado.value)
    )).scalar() or 0
    arquivados = (await db.execute(
        select(sqlfunc.count()).select_from(base)
        .where(base.c.status == CaseStatus.arquivado.value)
    )).scalar() or 0
    ativos = total - encerrados - arquivados

    rows = (await db.execute(
        select(base.c.area, sqlfunc.count())
        .select_from(base)
        .group_by(base.c.area)
    )).all()
    por_area = {(r[0].value if hasattr(r[0], "value") else r[0]): r[1] for r in rows}

    return {
        "total": total,
        "ativos": ativos,
        "encerrados": encerrados,
        "arquivados": arquivados,
        "por_area": por_area,
    }


@router.post("/", response_model=CaseDetail, status_code=201)
async def criar(
    payload: CaseCreate,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(
        ["superadmin", "admin", "socio", "advogado", "advogado_auxiliar", "secretaria"]
    )),  # M16 (auditoria 2026-06-30): criar caso = equipe jurídica/gestão/intake
):
    # BUG-03: rejeita título que é JSON/código cru de IA não parseado.
    if titulo_e_json_bruto(payload.titulo):
        raise HTTPException(
            status_code=422,
            detail="Título inválido — resposta de IA não parseada",
        )

    # Validar cliente
    client = (await db.execute(
        select(Client).where(
            Client.id == payload.client_id, Client.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=422, detail="Cliente não encontrado")

    data = payload.model_dump(exclude={"data_fato_prescricao"})
    c = Case(
        id=str(uuid4()),
        numero_interno=await _proximo_numero_interno(db),
        advogado_responsavel_id=data.pop("advogado_responsavel_id") or cu.id,
        **data,
    )

    # Prescrição automática
    if payload.tipo_acao_prescricao and payload.data_fato_prescricao:
        presc = calcular_prescricao(
            payload.tipo_acao_prescricao, payload.data_fato_prescricao
        )
        if presc:
            c.data_prescricao = datetime.combine(
                presc["data_limite"], datetime.min.time(), tzinfo=timezone.utc
            )

    db.add(c)
    db.add(CaseMovimento(
        id=str(uuid4()), case_id=c.id, tipo="nota",
        descricao=f"Caso aberto por {cu.full_name}", created_by=cu.id,
    ))
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "cases", c.id)
    await db.commit()
    await db.refresh(c)
    # NÚCLEO COGNITIVO — ETAPA 1: triagem jurídica automática (IA invisível).
    # Roda em background; preenche tese/pontos (se vazios) sem travar a resposta.
    background.add_task(automacao_caso, c.id)
    background.add_task(triagem_caso, c.id)
    background.add_task(event_bus.emitir_caso_criado, c.id, getattr(cu, 'id', None))
    return c


@router.get("/{case_id}", response_model=CaseDetail)
async def detalhe(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    q = _filtro_visibilidade(q, cu)
    c = (await db.execute(q)).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Caso não encontrado")
    # Fase 2: enriquecer com processo principal (fonte canônica)
    from app.services.processo_service import processo_principal as _get_proc
    from app.schemas.case import ProcessoPrincipalSchema, CaseDetail as _CD
    result = _CD.model_validate(c)
    proc = await _get_proc(case_id, db)
    if proc:
        result.processo_principal = ProcessoPrincipalSchema(**proc)
    return result


@router.patch("/{case_id}", response_model=CaseDetail)
async def atualizar(
    case_id: str, payload: CaseUpdate,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    q = _filtro_visibilidade(q, cu)
    c = (await db.execute(q)).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Caso não encontrado")

    mudancas = payload.model_dump(exclude_unset=True)
    for k, v in mudancas.items():
        setattr(c, k, v)
    if mudancas.get("status") == "encerrado":
        c.data_encerramento = datetime.now(timezone.utc)
    if mudancas.get("status") == "arquivado" and c.archived_at is None:
        c.archived_at = datetime.now(timezone.utc)
    elif mudancas.get("status") and mudancas.get("status") != "arquivado":
        c.archived_at = None
        c.archive_reason = None
    # Sincroniza coluna Kanban quando o status muda para um estado terminal
    _status_para_coluna = {"acordo": "Acordo", "encerrado": "Encerrado", "arquivado": "Encerrado"}
    _alvo = _status_para_coluna.get(mudancas.get("status"))
    if _alvo:
        col = (await db.execute(text("""
            SELECT name FROM kanban_columns WHERE is_active=true AND name ILIKE :nm
            ORDER BY position LIMIT 1
        """), {"nm": _alvo})).scalar()
        if col:
            c.kanban_column = col

    await criar_audit_log(
        db, cu.id, cu.role.value, "UPDATE", "cases", case_id,
        dados_depois={k: str(v) for k, v in mudancas.items()},
    )
    # Fase 3 write-through: sincroniza processes quando numero_processo muda
    if "numero_processo" in mudancas and mudancas["numero_processo"]:
        novo_cnj = (mudancas["numero_processo"] or "").strip()[:30]
        from uuid import uuid4
        await db.execute(text("""
            INSERT INTO processes (id, case_id, numero_cnj, instancia, is_principal, status, created_at, updated_at)
            VALUES (:id, :cid, :ncnj, '1', TRUE, 'ativo', now(), now())
            ON CONFLICT DO NOTHING
        """), {"id": str(uuid4()), "cid": case_id, "ncnj": novo_cnj})
        await db.execute(text("""
            UPDATE processes SET numero_cnj=:ncnj, updated_at=now()
            WHERE case_id=:cid AND is_principal=TRUE AND deleted_at IS NULL
        """), {"ncnj": novo_cnj, "cid": case_id})
    await db.commit()
    await db.refresh(c)
    # Event bus: notifica módulos interessados que o caso mudou (fail-safe).
    background.add_task(
        event_bus.emitir, "caso.atualizado", "case", case_id,
        {"mudancas": list(mudancas.keys()), "status": mudancas.get("status")}, cu.id,
    )
    # BUG-16: ao VINCULAR/alterar o CNJ do caso, sincroniza prazos do DataJud
    # em background (rascunho/HITL, dedup por referencia_datajud). Fail-safe.
    if "numero_processo" in mudancas and mudancas["numero_processo"]:
        background.add_task(_bg_sync_prazos_datajud, case_id, (mudancas["numero_processo"] or "").strip())
    # NB: o aprendizado institucional (memória+tese) é disparado pelo fluxo
    # canônico POST /cases/{id}/encerrar (com pós-mortem), não pelo PATCH.
    return c


# ── R2 — Arquivamento (reversível) e exclusão segura (soft delete) ───────────
# Nota de reconciliação (2026-07-03): esta funcionalidade foi construída em
# paralelo por duas frentes independentes. Versão canônica = a que já está em
# produção (colunas archived_at/archive_reason persistidas via migração),
# com dois adicionais do redesign incorporados: sincronização do kanban e
# evento no event_bus (arquitetura orientada a eventos, P1).

async def _sincronizar_kanban_encerrado(db: AsyncSession, c: Case) -> None:
    """Move o card para a coluna 'Encerrado' (se existir) — mesmo mapa do PATCH."""
    col = (await db.execute(text("""
        SELECT name FROM kanban_columns WHERE is_active=true AND name ILIKE :nm
        ORDER BY position LIMIT 1
    """), {"nm": "Encerrado"})).scalar()
    if col:
        c.kanban_column = col


class ArchiveCaseRequest(BaseModel):
    motivo: Optional[str] = Field(default=None, max_length=1000)


@router.post("/{case_id}/arquivar", response_model=CaseDetail)
async def arquivar_caso(
    case_id: str,
    background: BackgroundTasks,
    payload: Optional[ArchiveCaseRequest] = Body(default=None),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(_ARQUIVAMENTO_ROLES)),
):
    q = select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    q = _filtro_visibilidade(q, cu)
    c = (await db.execute(q)).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Caso não encontrado")
    if c.status == CaseStatus.arquivado:
        raise HTTPException(status_code=409, detail="Caso já arquivado")

    c.status = CaseStatus.arquivado
    c.archived_at = datetime.now(timezone.utc)
    c.archive_reason = ((payload.motivo if payload else None) or "").strip() or None
    await _sincronizar_kanban_encerrado(db, c)
    db.add(CaseMovimento(
        id=str(uuid4()), case_id=c.id, tipo="arquivamento",
        descricao=f"Caso arquivado{': ' + c.archive_reason if c.archive_reason else ''}",
        created_by=cu.id,
    ))
    await criar_audit_log(
        db, cu.id, cu.role.value, "ARCHIVE", "cases", case_id,
        dados_depois={"status": "arquivado", "motivo": c.archive_reason or ""},
    )
    await db.commit()
    await db.refresh(c)
    background.add_task(
        event_bus.emitir, "caso.atualizado", "case", case_id,
        {"mudancas": ["status"], "status": CaseStatus.arquivado.value}, cu.id,
    )
    return c


@router.post("/{case_id}/desarquivar", response_model=CaseDetail)
async def desarquivar_caso(
    case_id: str,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(_ARQUIVAMENTO_ROLES)),
):
    q = select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    q = _filtro_visibilidade(q, cu)
    c = (await db.execute(q)).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Caso não encontrado")
    if c.status != CaseStatus.arquivado:
        raise HTTPException(status_code=409, detail="Caso não está arquivado")

    motivo_anterior = c.archive_reason
    c.status = CaseStatus.ativo
    c.archived_at = None
    c.archive_reason = None
    db.add(CaseMovimento(
        id=str(uuid4()), case_id=c.id, tipo="arquivamento",
        descricao="Caso desarquivado",
        created_by=cu.id,
    ))
    await criar_audit_log(
        db, cu.id, cu.role.value, "UNARCHIVE", "cases", case_id,
        dados_depois={"status": "ativo", "motivo_anterior": motivo_anterior or ""},
    )
    await db.commit()
    await db.refresh(c)
    background.add_task(
        event_bus.emitir, "caso.atualizado", "case", case_id,
        {"mudancas": ["status"], "status": CaseStatus.ativo.value}, cu.id,
    )
    return c


async def _bg_sync_prazos_datajud(case_id: str, numero_cnj: str) -> None:
    """Background: sincroniza prazos do DataJud ao vincular um CNJ. Fail-safe."""
    from app.core.database import AsyncSessionLocal
    from app.services.datajud_service import sincronizar_prazos_datajud
    try:
        async with AsyncSessionLocal() as bgdb:
            await sincronizar_prazos_datajud(case_id, numero_cnj, bgdb)
            await bgdb.commit()
    except Exception:
        import logging
        logging.getLogger("ejc.cases").warning(
            f"[BUG-16] sync prazos DataJud falhou p/ caso {case_id}", exc_info=True
        )


@router.delete("/{case_id}", response_model=MsgResponse)
async def excluir(
    case_id: str,
    motivo: Optional[str] = Query(None, min_length=5, max_length=500,
                                  description="Motivo da exclusão (ou envie no body)"),
    payload: Optional[CaseDeleteRequest] = Body(None),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["admin", "socio"])),
):
    """
    Soft delete (lixeira/restauração via /trash). R2 endurecido:
    - motivo obrigatório (body {"motivo": ...} ou query ?motivo=), min 5 chars;
    - bloqueado (422 + lista `pendencias`) se houver prazo pendente,
      honorário pendente/atrasado ou peça protocolada — usar arquivamento.
    """
    motivo_final = ((payload.motivo if payload else None) or motivo or "").strip()
    if len(motivo_final) < 5:
        raise HTTPException(
            status_code=422,
            detail='Informe o motivo da exclusão (mínimo 5 caracteres) — '
                   'body {"motivo": "..."} ou query ?motivo=',
        )

    c = (await db.execute(
        select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Caso não encontrado")

    # ── Bloqueios condicionais (R2): pendências impedem exclusão ─────────────
    from app.models.deadline import Deadline, DeadlineStatus
    from app.models.fee import Fee, FeeStatus
    from app.models.legal_doc import LegalDoc, PecaStatus

    pendencias: list[dict] = []
    for p in (await db.execute(
        select(Deadline).where(
            Deadline.case_id == case_id,
            Deadline.deleted_at.is_(None),
            Deadline.status == DeadlineStatus.pendente,
        )
    )).scalars().all():
        pendencias.append({"tipo": "prazo", "id": p.id,
                           "descricao": f"Prazo pendente: {p.titulo} ({p.data_prazo})"})
    for f in (await db.execute(
        select(Fee).where(
            Fee.case_id == case_id,
            Fee.deleted_at.is_(None),
            Fee.status.in_([FeeStatus.pendente, FeeStatus.atrasado]),
        )
    )).scalars().all():
        _st = f.status.value if hasattr(f.status, "value") else str(f.status)
        pendencias.append({"tipo": "honorario", "id": f.id,
                           "descricao": f"Honorário {_st}: {f.descricao}"})
    for d in (await db.execute(
        select(LegalDoc).where(
            LegalDoc.case_id == case_id,
            LegalDoc.deleted_at.is_(None),
            LegalDoc.status == PecaStatus.protocolada,
        )
    )).scalars().all():
        pendencias.append({"tipo": "peca", "id": d.id,
                           "descricao": f"Peça protocolada: {d.titulo}"})

    if pendencias:
        raise HTTPException(status_code=422, detail={
            "mensagem": "Caso possui pendências — use arquivamento "
                        "(POST /cases/{id}/arquivar)",
            "pendencias": pendencias,
        })

    c.deleted_at = datetime.now(timezone.utc)
    await criar_audit_log(
        db, cu.id, cu.role.value, "DELETE", "cases", case_id,
        detalhes=f"Exclusão (soft delete). Motivo: {motivo_final}",
    )
    await db.commit()
    return MsgResponse(detail="Caso excluído (soft delete — restaurável pela lixeira)")


# ── ETAPA 5 — Geração documental automática ───────────────────────────────────
# Paridade de gates com o kit documental (POST /cases/{id}/kit-documental):
# procuração/contrato são ATO JURÍDICO → advogado+ (_req_advogado do kit) e
# mesmo rate limit "kit-documental" (5/min) — sem isso qualquer autenticado
# geraria procuração com poderes especiais por aqui.
@router.post("/{case_id}/gerar-documentos",
             dependencies=[Depends(rate_limit("kit-documental", 5))])
async def gerar_documentos(
    case_id: str,
    payload: Optional[KitDocumentalIn] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_advogado_kit),
):
    """Gera as minutas iniciais do caso (procuração, contrato de honorários,
    relatório inicial) preenchidas com os dados do cliente/caso. Rascunhos.

    Procuração com DEFAULT CONSERVADOR (ad_judicia), mesmo contrato/vocabulário
    do kit documental (POST /cases/{id}/kit-documental): poderes do art. 105 do
    CPC só com ``tipo_poderes="ad_judicia_et_extra"`` (ou ``"especiais"``)
    marcado explicitamente no corpo da requisição.
    """
    q = select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    q = _filtro_visibilidade(q, cu)
    c = (await db.execute(q)).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Caso não encontrado")
    p = payload or KitDocumentalIn()
    docs = await gerar_documentos_iniciais(
        case_id, cu.id,
        tipo_poderes=p.tipo_poderes,
        permite_substabelecimento=p.permite_substabelecimento,
        poderes_especiais=p.poderes_especiais,
    )
    await criar_audit_log(db, cu.id, cu.role.value, "GERAR_DOCS", "cases", case_id)
    await db.commit()
    return {
        "gerados": docs,
        "aviso": "Minutas geradas como RASCUNHO — revisar e preencher campos [   ] (OAB). "
                 "Disponíveis em Peças do caso.",
    }


# ── Movimentos (timeline) ─────────────────────────────────────────────────────

@router.get("/{case_id}/movimentos")
async def listar_movimentos(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    q = _filtro_visibilidade(q, cu)
    if not (await db.execute(q)).scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Caso não encontrado")

    rows = (await db.execute(
        select(CaseMovimento)
        .where(CaseMovimento.case_id == case_id)
        .order_by(CaseMovimento.created_at.desc())
        .limit(100)
    )).scalars().all()
    return [
        {"id": m.id, "tipo": m.tipo, "descricao": m.descricao,
         "data_evento": m.data_evento, "created_at": m.created_at,
         "resumo_ia": m.resumo_ia}
        for m in rows
    ]


@router.post("/{case_id}/movimentos", status_code=201)
async def criar_movimento(
    case_id: str, payload: MovimentoCreate,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    q = _filtro_visibilidade(q, cu)
    case = (await db.execute(q)).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Caso não encontrado ou sem permissão")
    m = CaseMovimento(
        id=str(uuid4()), case_id=case_id,
        tipo=payload.tipo, descricao=payload.descricao, created_by=cu.id,
    )
    db.add(m)
    await db.commit()
    # Event bus: dispara tradução IA do andamento (subscriber) — fail-safe.
    background.add_task(
        event_bus.emitir, "movimento.criado", "case_movimento", m.id,
        {"tipo": m.tipo, "case_id": case_id}, cu.id,
    )
    return {"id": m.id, "detail": "Movimento registrado"}


@router.post("/{case_id}/assistente-estrategico")
async def assistente_estrategico_caso(
    case_id: str,
    demanda: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    IA Contextual: Assistente Estratégico do Caso (Seção 1.33).
    Acesso automático a todos os dados do processo e documentos.
    """
    from app.core.ai_brain import ai_gateway
    from app.models.case_parte import CaseParte
    
    q = select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    q = _filtro_visibilidade(q, cu)
    c = (await db.execute(q)).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Caso não encontrado")
    
    partes = (await db.execute(select(CaseParte).where(CaseParte.case_id == case_id))).scalars().all()
    movs = (await db.execute(select(CaseMovimento).where(CaseMovimento.case_id == case_id).limit(10))).scalars().all()
    
    contexto = (
        f"CASO: {c.titulo}\nNÚMERO: {c.numero_processo}\nÁREA: {c.area}\n"
        f"TESE: {c.tese_principal}\n"
        f"PARTES: {', '.join([p.nome for p in partes])}\n"
        f"ÚLTIMOS MOVIMENTOS: {'; '.join([m.descricao[:100] for m in movs])}\n"
    )

    # LGPD: sanitiza PII (nomes de partes, nº do processo, CPF/CNPJ) antes de
    # enviar à IA — a análise estratégica não precisa dos dados reais.
    from app.services.sanitizer import sanitizar_pii
    contexto, pii_ctx = sanitizar_pii(contexto, [p.nome for p in partes if p.nome])
    demanda_limpa, pii_dem = sanitizar_pii(demanda)

    res = await ai_gateway.processar_demanda(demanda_limpa, contexto, tipo="juridico_profundo")

    # Auditoria obrigatória (LGPD/OAB): TODA chamada de IA precisa de rastro em
    # ai_logs. Este endpoint passa pelo shim legado (core.ai_brain →
    # ai_gateway.chat), que antes NÃO gravava AILog (furo de compliance #4a). A
    # gravação é ADITIVA: não altera a resposta nem o comportamento do modelo —
    # só registra o que já foi enviado/recebido (prompt já sanitizado acima +
    # modelo real devolvido pelo shim). Loga apenas em sucesso, mesma semântica
    # dos endpoints de IA já auditados (ai.py::assistente_estrategico e
    # diplomacia_v3::dossie_pressao só gravam quando a IA respondeu). Se a
    # gravação falhar, o erro PROPAGA (registrar_ai_log) — rastro é obrigatório;
    # não introduzimos try/except que engula a falha de auditoria.
    if res.get("status") == "sucesso":
        from app.services.ai_guard import registrar_ai_log
        from app.models.ai_log import AITipoUso
        await registrar_ai_log(
            db, user_id=cu.id, tipo_uso=AITipoUso.analise_caso, case_id=case_id,
            prompt_sanitizado=f"{contexto}\n\n[DEMANDA]\n{demanda_limpa}",
            pii_removida=bool(pii_ctx or pii_dem),
            resposta=res.get("resposta"),
            modelo=res.get("modelo_utilizado"),
        )

    return res


# ═══ DataJud: sincronização de movimentos oficiais ═══
from app.services.datajud_service import sincronizar_caso as _dj_sync


@router.post("/{case_id}/sincronizar-processo")
async def sincronizar_processo(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Busca movimentos no DataJud/CNJ e insere os novos na timeline."""
    _role = cu.role.value if hasattr(cu.role, "value") else str(cu.role)
    if _role not in ("superadmin", "admin", "socio", "advogado"):
        raise HTTPException(status_code=403, detail="Acesso negado")
    q = select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    q = _filtro_visibilidade(q, cu)
    case = (await db.execute(q)).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Caso não encontrado")
    if not case.numero_processo:
        raise HTTPException(status_code=422,
                            detail="Caso sem número de processo CNJ cadastrado")

    novos = await _dj_sync(db, case)
    await db.commit()
    return {"movimentos_novos": novos,
            "detail": f"{novos} movimento(s) oficial(is) importado(s)"
                      if novos else "Nenhum movimento novo"}


# ═══ Pós-Mortem Jurídico (ECJ): encerrar caso com aprendizado ═══
from pydantic import BaseModel as _BM2, Field as _F2


class EncerrarCasoReq(_BM2):
    resultado: str = _F2(
        # \A/\z (não ^/$): a validação por regex aceitaria "exito\n" com "$",
        # que passaria aqui mas nunca casaria o vocabulário da jurimetria.
        pattern=r"\A(exito|exito_parcial|acordo|derrota|desistencia|arquivado)\z",
        description="exito|exito_parcial|acordo|derrota|desistencia|arquivado",
    )
    motivo_resultado: str = _F2(min_length=20,
        description="Por que esse resultado? Fundamentos aceitos/rejeitados.")
    provas_determinantes: str = _F2(min_length=10)
    licoes_aprendidas: str = _F2(min_length=20)
    alimentar_rag: bool = True


@router.post("/{case_id}/encerrar")
async def encerrar_caso(
    case_id: str, payload: EncerrarCasoReq,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Encerramento com Pós-Mortem obrigatório: o conhecimento do caso
    vira ativo institucional (ingestão automática na base RAG).
    """
    _role = cu.role.value if hasattr(cu.role, "value") else str(cu.role)
    if _role not in ("superadmin", "admin", "socio", "advogado"):
        raise HTTPException(status_code=403, detail="Acesso negado")
    q = select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    q = _filtro_visibilidade(q, cu)
    case = (await db.execute(q)).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Caso não encontrado")
    if case.status in (CaseStatus.encerrado, CaseStatus.arquivado):
        raise HTTPException(status_code=409, detail="Caso já encerrado")

    case.status = CaseStatus.encerrado
    case.data_encerramento = datetime.now(timezone.utc)
    case.resultado = payload.resultado
    case.motivo_resultado = payload.motivo_resultado
    case.provas_determinantes = payload.provas_determinantes
    case.licoes_aprendidas = payload.licoes_aprendidas

    # Memória institucional: ingere o pós-mortem no RAG (sem dados pessoais).
    # Agora inclui o DOSSIÊ COMPLETO (dados especializados do ramo, prazos que
    # foram cumpridos, peças produzidas) — não só a estratégia textual. Isso faz
    # o precedente interno ser pesquisável por características concretas do caso.
    if payload.alimentar_rag:
        from app.services.case_context import montar_dossie
        from app.services.ingestion_service import upsert_documento

        area_str = case.area.value if hasattr(case.area, "value") else str(case.area)

        # Dossiê consolidado e já sanitizado (cliente, ramo, prazos, peças)
        dossie = await montar_dossie(db, case_id, incluir_pecas=True, sanitizar=True)
        bloco_dossie = dossie["texto"] if dossie else ""

        corpo = (
            f"PRECEDENTE INTERNO — CASO {case.numero_interno}\n"
            f"Área: {area_str} | Resultado: {payload.resultado}\n\n"
            f"TESE PRINCIPAL: {case.tese_principal or '—'}\n\n"
            f"MOTIVO DO RESULTADO: {payload.motivo_resultado}\n\n"
            f"PROVAS DETERMINANTES: {payload.provas_determinantes}\n\n"
            f"LIÇÕES APRENDIDAS: {payload.licoes_aprendidas}\n\n"
            f"--- CONTEXTO DO CASO (dossiê) ---\n{bloco_dossie}"
        )
        # Idempotente: chave_origem = caso:{id} evita duplicar se reencerrado.
        await upsert_documento(
            db,
            titulo=f"Precedente Interno — {case.numero_interno} ({payload.resultado})",
            categoria="precedente_interno",
            conteudo=corpo,
            chave_origem=f"caso:{case.id}",
            fonte=f"caso:{case.id}",
            extra={
                "area": area_str,
                "resultado": payload.resultado,
                "rag_status": "aprovado",
                "human_reviewed": True,
                "approved_by": str(cu.id),
            },
        )

    db.add(CaseMovimento(
        id=str(uuid4()), case_id=case.id, tipo="encerramento",
        descricao=f"Caso encerrado: {payload.resultado}",
        created_by=cu.id,
    ))
    await criar_audit_log(
        db, cu.id, cu.role.value, "UPDATE", "cases", case_id,
        detalhes=f"Encerramento ({payload.resultado}) com pós-mortem",
    )
    await db.commit()
    # NÚCLEO COGNITIVO — complementa o precedente-RAG acima com Memória
    # Institucional + Banco de Teses (ETAPA 1.3/6/7). Idempotente.
    background.add_task(aprendizado_encerramento, case_id)
    # Event bus: emite caso.encerrado (subscribers + trilha de domínio).
    background.add_task(
        event_bus.emitir, "caso.encerrado", "case", case_id,
        {"resultado": payload.resultado}, cu.id,
    )
    return {"detail": "Caso encerrado. Conhecimento registrado na base institucional."}


# ── Tradução de andamento por IA (P1) ─────────────────────────────────────────
@router.post("/{case_id}/movimentos/{mov_id}/traduzir")
async def traduzir_andamento(
    case_id: str, mov_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Gera o resumo em linguagem simples de um andamento (sob demanda).
    Útil para movimentos importados do DataJud. Resultado é RASCUNHO."""
    q = select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    q = _filtro_visibilidade(q, cu)
    if not (await db.execute(q)).scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Caso não encontrado")
    # IDOR: o movimento precisa pertencer a ESTE caso (não basta o caso existir).
    mov_ok = (await db.execute(
        select(CaseMovimento.id).where(
            CaseMovimento.id == mov_id, CaseMovimento.case_id == case_id,
        )
    )).scalar_one_or_none()
    if not mov_ok:
        raise HTTPException(status_code=404, detail="Movimento não encontrado neste caso")
    resumo = await traduzir_movimento(db, mov_id, forcar=True)
    if resumo is None:
        raise HTTPException(status_code=422, detail="Não foi possível traduzir o andamento (IA indisponível ou texto curto).")
    return {"id": mov_id, "resumo_ia": resumo,
            "aviso": "Resumo gerado por IA — rascunho, conferir com o andamento original."}


# ── Importação inteligente → Caso núcleo (P1) ─────────────────────────────────
def _map_deadline_tipo(tipo_txt: Optional[str]) -> DeadlineTipo:
    """Mapeia o `tipo` livre de um prazo extraído (ex.: 'contestação',
    'recurso', 'audiência', 'prescrição') para o enum DeadlineTipo.
    Default: processual (prazo judicial)."""
    t = (tipo_txt or "").lower()
    if "prescri" in t or "decad" in t:
        return DeadlineTipo.prescricao
    if "audi" in t:
        return DeadlineTipo.audiencia
    if "administ" in t:
        return DeadlineTipo.administrativo
    if "interno" in t or "tarefa" in t:
        return DeadlineTipo.interno
    return DeadlineTipo.processual


class AplicarExtracaoReq(_BM2):
    """JSON de /documentos-ia/analisar materializado no caso: partes
    (case_partes), área (caso_areas), campos processuais vazios e prazos
    (deadlines rascunho, #83 Gap C)."""
    identificacao_processual: Optional[dict] = None
    partes: Optional[dict] = None
    classificacao: Optional[dict] = None
    # Prazos extraídos por IA (shape de PrazoExtraido: tipo, data_base,
    # termo_final, fatal, base_legal). Cada prazo com data fatal válida vira um
    # Deadline confirmado=false (rascunho "a confirmar" — já dispara alertas).
    prazos: Optional[list[dict]] = None
    # Documento (GED) de origem dos prazos — rastreabilidade em Deadline.
    origem_documento_id: Optional[str] = None
    # Preview: quando true, computa o que SERIA aplicado sem persistir nada
    # (nem AuditLog). Pode vir no corpo ou no query param ?dry_run=true.
    dry_run: bool = False


@router.post("/{case_id}/aplicar-extracao")
async def aplicar_extracao(
    case_id: str, payload: AplicarExtracaoReq,
    background: BackgroundTasks,
    dry_run: bool = Query(False, description="Preview: não persiste nada, só devolve o que seria aplicado."),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Materializa no caso os dados extraídos de um documento pela IA.
    Aditivo: dedup de partes por (tipo, nome); campos processuais só são
    preenchidos se estiverem vazios (nunca sobrescreve o advogado).

    dry_run (corpo OU query param): roda EXATAMENTE a mesma lógica de
    materialização mas dá rollback e NÃO grava AuditLog — é só prévia."""
    is_dry_run = bool(dry_run or payload.dry_run)
    q = select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    q = _filtro_visibilidade(q, cu)
    case = (await db.execute(q)).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Caso não encontrado")

    # 1) Campos processuais (só preenche se vazio)
    ident = payload.identificacao_processual or {}
    _maxlen = {"numero_processo": 30, "tribunal": 20, "comarca": 100, "vara": 100}
    preenchidos: list[str] = []
    for campo, mx in _maxlen.items():
        raw = ident.get(campo)
        val = raw.strip() if isinstance(raw, str) else None
        if val and not getattr(case, campo, None):
            setattr(case, campo, val[:mx])
            preenchidos.append(campo)

    # 2) Partes (dedup por tipo+nome já existentes)
    existentes = {
        (p.tipo, (p.nome or "").lower())
        for p in (await db.execute(
            select(CaseParte).where(CaseParte.case_id == case_id)
        )).scalars().all()
    }
    partes = payload.partes or {}
    n_partes = 0

    def _materializar(tipo: str, valor) -> None:
        nonlocal n_partes
        nome = valor.strip() if isinstance(valor, str) else ""
        if not nome or (tipo, nome.lower()) in existentes:
            return
        db.add(CaseParte(id=str(uuid4()), case_id=case_id, tipo=tipo,
                         nome=nome[:255], created_by=cu.id))
        existentes.add((tipo, nome.lower()))
        n_partes += 1

    _materializar("autor", partes.get("autor"))
    _materializar("reu", partes.get("reu"))
    for t in (partes.get("terceiros") or []):
        _materializar("terceiro", t)
    for adv in (partes.get("advogados") or []):
        _materializar("advogado", adv)
    for proc in (partes.get("procuradores") or []):
        _materializar("procurador", proc)

    # 3) Área principal (UNIQUE case_id+area no banco evita duplicar)
    n_areas = 0
    area = ((payload.classificacao or {}).get("area") or "").strip().lower()
    if area:
        ja = (await db.execute(
            text("SELECT 1 FROM caso_areas WHERE case_id=:c AND area=:a LIMIT 1"),
            {"c": case_id, "a": area},
        )).scalar()
        if not ja:
            db.add(CasoArea(id=str(uuid4()), case_id=case_id, area=area[:40],
                            principal=True))
            n_areas += 1

    # 4) Prazos extraídos por IA → Deadline RASCUNHO (#83 Gap C).
    # Decisão de produto (imutável): o prazo nasce confirmado=false ("a
    # confirmar") mas JÁ dispara os alertas normais (não filtramos alerta por
    # confirmado). SEMPRE rascunho — nunca auto-confirma. Só materializa quando
    # há data fatal VÁLIDA; sem data clara → ignora (fica só como sugestão no
    # resultado da extração, não vira Deadline). Dedup por (data_prazo, titulo).
    n_prazos = 0
    prazos_in = payload.prazos or []
    if prazos_in:
        prazos_existentes = {
            (d.data_prazo, (d.titulo or "").strip().lower())
            for d in (await db.execute(
                select(Deadline).where(
                    Deadline.case_id == case_id, Deadline.deleted_at.is_(None)
                )
            )).scalars().all()
        }
        for pr in prazos_in:
            if not isinstance(pr, dict):
                continue
            data_fatal = parse_data_br(pr.get("termo_final") or pr.get("data_prazo"))
            if data_fatal is None:
                continue  # sem data fatal → não cria (nunca inventa prazo)
            tipo_txt = (pr.get("tipo") or "").strip()
            titulo = (pr.get("titulo") or tipo_txt or "Prazo (importação IA)")[:255]
            chave = (data_fatal, titulo.strip().lower())
            if chave in prazos_existentes:
                continue  # dedup: mesmo (data_prazo, titulo) já existe no caso
            bl = pr.get("base_legal")
            db.add(Deadline(
                id=str(uuid4()),
                titulo=titulo,
                tipo=_map_deadline_tipo(tipo_txt),
                status=DeadlineStatus.pendente,
                data_prazo=data_fatal,
                base_legal=(str(bl)[:255] if bl else None),
                case_id=case_id,
                responsavel_id=case.advogado_responsavel_id,
                confirmado=False,
                origem="importacao_ia",
                origem_documento_id=payload.origem_documento_id,
            ))
            prazos_existentes.add(chave)
            n_prazos += 1

    # Preview: desfaz tudo (partes/área/campos/prazos ficaram só pendentes na
    # sessão) e retorna o que SERIA aplicado. Nada é persistido, sem AuditLog.
    if is_dry_run:
        await db.rollback()
        return {
            "aplicado": False,
            "dry_run": True,
            "ok": False,
            "partes_criadas": n_partes,
            "areas_criadas": n_areas,
            "campos_preenchidos": preenchidos,
            "prazos_criados": n_prazos,
            "aviso": "Prévia (dry_run): nada foi persistido. Confirme para aplicar. Revisão obrigatória do advogado (OAB).",
        }

    db.add(CaseMovimento(
        id=str(uuid4()), case_id=case_id, tipo="nota", created_by=cu.id,
        descricao=(f"Importação inteligente aplicada: {n_partes} parte(s), "
                   f"{n_areas} área(s), {n_prazos} prazo(s) a confirmar, "
                   f"campos: {', '.join(preenchidos) or '—'}. Revisar (OAB)."),
    ))
    await criar_audit_log(db, cu.id, cu.role.value, "IMPORT_EXTRACAO", "cases", case_id)
    await db.commit()
    background.add_task(
        event_bus.emitir, "documento.importado", "case", case_id,
        {"partes": n_partes, "areas": n_areas, "campos": preenchidos,
         "prazos": n_prazos}, cu.id,
    )
    return {
        "aplicado": True,
        "dry_run": False,
        "ok": True,
        "partes_criadas": n_partes,
        "areas_criadas": n_areas,
        "campos_preenchidos": preenchidos,
        "prazos_criados": n_prazos,
        "aviso": "Dados extraídos por IA aplicados ao caso. Prazos criados como RASCUNHO (a confirmar) — já entram nos alertas. Revisão obrigatória do advogado (OAB).",
    }


# ── Linha do tempo do caso (#41) — determinístico, sem IA ─────────────────────
@router.get("/{case_id}/linha-do-tempo")
async def linha_do_tempo(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Cronologia unificada do caso: movimentos + prazos + documentos + honorários,
    ordenada por data (mais recente primeiro). Agrega dados reais — não inventa.
    A montagem dos eventos vive em app/services/visual_law_core.py (compartilhada
    com o módulo Visual Law); o contrato deste endpoint permanece o mesmo."""
    from app.services.visual_law_core import montar_eventos_caso

    q = select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    q = _filtro_visibilidade(q, cu)
    if not (await db.execute(q)).scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Caso não encontrado")

    eventos = await montar_eventos_caso(db, case_id)
    return {"case_id": case_id, "total": len(eventos), "eventos": eventos}


# ── Recomendação de teses relevantes ao caso (#tese-match) ────────────────────
# Sugere teses vitoriosas/relevantes do Banco de Teses semelhantes ao caso atual.
#
# ESTRATÉGIA: relevância TEXTUAL (não vetorial).
# A tabela `teses` (app/models/tese.py) NÃO possui coluna de embedding próprio —
# apenas campos textuais (titulo, descricao, fundamentacao, jurisprudencia, tags)
# e métricas de desempenho (taxa_sucesso, vezes_venceu). Como não há vetor para
# comparar com `<=>`, gerar um embedding da consulta não teria contra-parte no
# schema. Portanto usamos correspondência por área + palavras-chave (ILIKE),
# reaproveitando o mesmo padrão de busca de app/routers/teses.py, e ranqueamos
# priorizando teses vitoriosas (taxa_sucesso / vezes_venceu). Fail-safe: sem
# resultados → lista vazia (nunca erro).

_STOPWORDS_TESE = {
    "para", "com", "sem", "por", "dos", "das", "que", "uma", "uns", "umas",
    "seu", "sua", "sobre", "ante", "caso", "acao", "ação", "contra", "entre",
    "nao", "não", "the", "and", "processo", "autor", "reu", "réu", "parte",
    "juridica", "jurídica", "direito", "art", "artigo",
}


def _tokens_relevantes(*textos: Optional[str], limite: int = 12) -> list[str]:
    """Extrai palavras-chave (>3 chars, sem stopwords, únicas) do texto do caso."""
    import re
    vistos: list[str] = []
    seen: set[str] = set()
    for t in textos:
        if not t:
            continue
        for bruto in re.split(r"[^0-9a-zA-ZáàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ]+", str(t)):
            w = bruto.strip().lower()
            if len(w) <= 3 or w in _STOPWORDS_TESE or w in seen:
                continue
            seen.add(w)
            vistos.append(w)
            if len(vistos) >= limite:
                return vistos
    return vistos


@router.get("/{case_id}/teses-sugeridas", summary="Teses relevantes ao caso",
            dependencies=[Depends(rate_limit("teses-sugeridas", 15))])
async def teses_sugeridas(
    case_id: str,
    k: int = Query(5, ge=1, le=20, description="Quantidade de teses sugeridas"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Sugere teses do Banco de Teses semelhantes ao caso (vitoriosas em destaque).

    Ownership: `verificar_acesso_caso` (mesmo gate dos demais endpoints do caso).
    Busca TEXTUAL por área + palavras-chave (teses não têm embedding próprio);
    ranqueia por sobreposição de termos e desempenho histórico. Fail-safe:
    retorna `{"teses": []}` quando não há correspondências.
    """
    from app.models.tese import Tese, TeseStatus

    # 1) Ownership de leitura (IDOR): reaproveita o gate canônico do caso.
    case = await verificar_acesso_caso(db, cu, case_id)

    # 2) Texto-consulta a partir do caso (área + título + tese/fatos + partes).
    area_val = ""
    raw_area = getattr(case, "area", None)
    if raw_area:
        area_val = (raw_area.value if hasattr(raw_area, "value") else str(raw_area)).strip()

    keywords = _tokens_relevantes(
        case.titulo,
        getattr(case, "tese_principal", None),
        getattr(case, "descricao", None),
        getattr(case, "descricao_fatos", None),
        getattr(case, "parte_contraria", None),
    )

    # 3) Candidatas: teses ativas cuja área bate OU que casam alguma palavra-chave.
    stmt = select(Tese).where(
        Tese.deleted_at.is_(None),
        Tese.status == TeseStatus.ativa,
    )
    condicoes = []
    if area_val:
        condicoes.append(Tese.area_juridica.ilike(f"%{area_val}%"))
    for w in keywords:
        termo = f"%{w}%"
        condicoes.append(Tese.titulo.ilike(termo))
        condicoes.append(Tese.descricao.ilike(termo))
        condicoes.append(Tese.fundamentacao.ilike(termo))
        condicoes.append(Tese.jurisprudencia.ilike(termo))
        condicoes.append(Tese.tags.ilike(termo))
    if condicoes:
        stmt = stmt.where(or_(*condicoes))
    else:
        # Sem área nem palavras-chave úteis → cai para as mais vitoriosas.
        stmt = stmt.where(Tese.vezes_usada >= 1)

    # Pré-filtro amplo (ordenado por desempenho) e ranqueamento fino em memória.
    candidatas = (await db.execute(
        stmt.order_by(Tese.taxa_sucesso.desc().nullslast(), Tese.vezes_venceu.desc())
            .limit(100)
    )).scalars().all()

    area_lc = area_val.lower()

    def _score(t: Tese) -> float:
        blob = " ".join(filter(None, [
            t.titulo, t.descricao, t.fundamentacao, t.jurisprudencia, t.tags,
        ])).lower()
        hits = sum(1 for w in keywords if w in blob)
        area_match = bool(area_lc and t.area_juridica and area_lc in t.area_juridica.lower())
        score = float(hits) + (2.0 if area_match else 0.0)
        # Boost por desempenho (teses vitoriosas ganham prioridade no desempate).
        score += float(t.taxa_sucesso or 0.0)
        score += min(float(t.vezes_venceu or 0), 5) * 0.1
        return score

    ranqueadas = sorted(candidatas, key=_score, reverse=True)

    saida = []
    for t in ranqueadas:
        sc = _score(t)
        if sc <= 0:
            continue  # sem qualquer aderência textual — descarta
        resumo = (t.descricao or t.fundamentacao or "").strip()
        saida.append({
            "id": t.id,
            "titulo": t.titulo,
            "tema": t.area_juridica or area_val or None,
            "ramo": t.area_juridica or None,
            "resumo": (resumo[:280] + "…") if len(resumo) > 280 else resumo,
            "score": round(sc, 4),
            "distancia": round(1.0 / (1.0 + sc), 4),  # menor = mais próxima
            "taxa_sucesso": t.taxa_sucesso,
            "vezes_venceu": t.vezes_venceu,
            "vezes_usada": t.vezes_usada,
            "tribunal": t.tribunal,
        })
        if len(saida) >= k:
            break

    return {
        "case_id": case_id,
        "estrategia": "textual",  # teses não possuem embedding vetorial próprio
        "area": area_val or None,
        "palavras_chave": keywords,
        "total": len(saida),
        "teses": saida,
    }


@router.post('/{case_id}/analisar', summary='Analise estrategica com IA')
async def analisar_caso_ia(
    case_id: str,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    import json as _json
    from app.services.analise_estrategica import analisar_caso
    from app.core.ownership import verificar_acesso_caso

    # Ownership (IDOR): só quem tem o caso pode disparar a análise estratégica.
    case = await verificar_acesso_caso(db, current_user, case_id)

    parte_contraria = getattr(case, 'parte_contraria', None) or ''
    partes_str = f'Parte contraria: {parte_contraria}' if parte_contraria else ''

    # Nomes próprios a mascarar antes do LLM (LGPD): parte contrária + cliente.
    nomes_proteger = [n for n in [parte_contraria] if n]
    if getattr(case, 'client_id', None):
        _cli_nome = (await db.execute(
            text("SELECT COALESCE(nome, razao_social, nome_fantasia) FROM clients WHERE id = :id"),
            {"id": case.client_id},
        )).scalar()
        if _cli_nome:
            nomes_proteger.append(_cli_nome)

    area_val = ''
    raw_area = getattr(case, 'area', None)
    if raw_area:
        area_val = raw_area.value if hasattr(raw_area, 'value') else str(raw_area)

    analise = await analisar_caso(
        titulo=getattr(case, 'titulo', '') or '',
        objeto=getattr(case, 'descricao', '') or '',
        fatos=getattr(case, 'descricao_fatos', '') or '',
        texto_documento=(payload.get('texto_documento', '') if isinstance(payload, dict) else ''),
        partes_existentes=partes_str,
        numero_processo=getattr(case, 'numero_processo', '') or '',
        area=area_val,
        nomes_proteger=nomes_proteger,
        scope_client_id=getattr(case, 'client_id', None),  # A2: RAG restrito ao próprio cliente
        case_id=case_id,  # PR #85: pseudonimização reversível dos nomes do caso
        db=db,
    )

    try:
        from app.models.ai_log import AILog, AITipoUso, AIStatusHITL
        log = AILog(
            user_id=current_user.id,
            case_id=case_id,
            tipo_uso=AITipoUso.analise_caso,
            prompt_sanitizado='analise_estrategica_completa',
            resposta=_json.dumps(analise, ensure_ascii=False)[:10000],
            status_hitl=AIStatusHITL.gerado,
            pii_removida=True,
        )
        db.add(log)
        await db.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f'AILog nao salvo: {e}')

    return analise

