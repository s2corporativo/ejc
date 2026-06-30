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
from app.models.case_parte import CaseParte
from app.models.caso_area import CasoArea
from app.services.movimento_ia import traduzir_movimento
from app.schemas.case import (
    CaseCreate, CaseUpdate, CaseResponse, CaseDetail, MovimentoCreate,
)
from app.schemas.common import MsgResponse

router = APIRouter(prefix="/cases", tags=["Casos"])


async def _proximo_numero_interno(db: AsyncSession) -> str:
    """Numeração automática DPT-2026-0001 (sequencial por ano)."""
    ano = date.today().year
    result = await db.execute(text("""
        SELECT numero_interno FROM cases
        WHERE numero_interno LIKE :pref
        ORDER BY numero_interno DESC LIMIT 1
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
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(Case).where(Case.deleted_at.is_(None))
    q = _filtro_visibilidade(q, cu)
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


@router.post("/", response_model=CaseDetail, status_code=201)
async def criar(
    payload: CaseCreate,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
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
    # NB: o aprendizado institucional (memória+tese) é disparado pelo fluxo
    # canônico POST /cases/{id}/encerrar (com pós-mortem), não pelo PATCH.
    return c


@router.delete("/{case_id}", response_model=MsgResponse)
async def arquivar(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["admin", "socio"])),
):
    c = (await db.execute(
        select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Caso não encontrado")
    c.deleted_at = datetime.now(timezone.utc)
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", "cases", case_id)
    await db.commit()
    return MsgResponse(detail="Caso arquivado")


# ── ETAPA 5 — Geração documental automática ───────────────────────────────────
@router.post("/{case_id}/gerar-documentos")
async def gerar_documentos(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Gera as minutas iniciais do caso (procuração, contrato de honorários,
    relatório inicial) preenchidas com os dados do cliente/caso. Rascunhos."""
    c = (await db.execute(
        select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Caso não encontrado")
    docs = await gerar_documentos_iniciais(case_id, cu.id)
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
    from app.models.document import Document
    
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
    
    return await ai_gateway.processar_demanda(demanda, contexto, tipo="juridico_profundo")


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
    resultado: str = _F2(description="exito|exito_parcial|acordo|derrota|desistencia|arquivado")
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
            extra={"area": area_str, "resultado": payload.resultado},
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
    resumo = await traduzir_movimento(db, mov_id, forcar=True)
    if resumo is None:
        raise HTTPException(status_code=422, detail="Não foi possível traduzir o andamento (IA indisponível ou texto curto).")
    return {"id": mov_id, "resumo_ia": resumo,
            "aviso": "Resumo gerado por IA — rascunho, conferir com o andamento original."}


# ── Importação inteligente → Caso núcleo (P1) ─────────────────────────────────
class AplicarExtracaoReq(_BM2):
    """JSON de /documentos-ia/analisar materializado no caso: partes
    (case_partes), área (caso_areas) e campos processuais vazios."""
    identificacao_processual: Optional[dict] = None
    partes: Optional[dict] = None
    classificacao: Optional[dict] = None


@router.post("/{case_id}/aplicar-extracao")
async def aplicar_extracao(
    case_id: str, payload: AplicarExtracaoReq,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Materializa no caso os dados extraídos de um documento pela IA.
    Aditivo: dedup de partes por (tipo, nome); campos processuais só são
    preenchidos se estiverem vazios (nunca sobrescreve o advogado)."""
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

    db.add(CaseMovimento(
        id=str(uuid4()), case_id=case_id, tipo="nota", created_by=cu.id,
        descricao=(f"Importação inteligente aplicada: {n_partes} parte(s), "
                   f"{n_areas} área(s), campos: {', '.join(preenchidos) or '—'}. "
                   f"Revisar (OAB)."),
    ))
    await criar_audit_log(db, cu.id, cu.role.value, "IMPORT_EXTRACAO", "cases", case_id)
    await db.commit()
    background.add_task(
        event_bus.emitir, "documento.importado", "case", case_id,
        {"partes": n_partes, "areas": n_areas, "campos": preenchidos}, cu.id,
    )
    return {
        "ok": True,
        "partes_criadas": n_partes,
        "areas_criadas": n_areas,
        "campos_preenchidos": preenchidos,
        "aviso": "Dados extraídos por IA aplicados ao caso. Revisão obrigatória do advogado (OAB).",
    }


# ── Linha do tempo do caso (#41) — determinístico, sem IA ─────────────────────
@router.get("/{case_id}/linha-do-tempo")
async def linha_do_tempo(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Cronologia unificada do caso: movimentos + prazos + documentos + honorários,
    ordenada por data (mais recente primeiro). Agrega dados reais — não inventa."""
    from app.models.deadline import Deadline
    from app.models.document import Document
    from app.models.fee import Fee

    q = select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    q = _filtro_visibilidade(q, cu)
    if not (await db.execute(q)).scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Caso não encontrado")

    def _val(x):
        return x.value if hasattr(x, "value") else x

    eventos: list[dict] = []
    for m in (await db.execute(
        select(CaseMovimento).where(CaseMovimento.case_id == case_id)
        .order_by(CaseMovimento.data_evento.desc()).limit(300)
    )).scalars().all():
        eventos.append({"data": m.data_evento, "categoria": "movimento",
                        "tipo": m.tipo, "descricao": (m.descricao or "")[:240]})
    for p in (await db.execute(
        select(Deadline).where(Deadline.case_id == case_id, Deadline.deleted_at.is_(None))
    )).scalars().all():
        eventos.append({"data": p.data_prazo, "categoria": "prazo", "tipo": _val(p.tipo),
                        "descricao": f"{p.titulo} [{_val(p.status)}]"})
    for d in (await db.execute(
        select(Document).where(Document.case_id == case_id, Document.deleted_at.is_(None))
    )).scalars().all():
        eventos.append({"data": d.created_at, "categoria": "documento",
                        "tipo": d.tipo or "doc", "descricao": d.titulo})
    for f in (await db.execute(
        select(Fee).where(Fee.case_id == case_id, Fee.deleted_at.is_(None))
    )).scalars().all():
        dt = f.data_pagamento or f.data_vencimento
        if dt:
            eventos.append({"data": dt, "categoria": "honorario", "tipo": _val(f.tipo),
                            "descricao": f"{f.descricao} [{_val(f.status)}]"})

    eventos.sort(key=lambda e: (e["data"].isoformat() if hasattr(e["data"], "isoformat")
                                else str(e["data"])), reverse=True)
    return {"case_id": case_id, "total": len(eventos), "eventos": eventos}


@router.post('/{case_id}/analisar', summary='Analise estrategica com IA')
async def analisar_caso_ia(
    case_id: str,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    import json as _json
    from app.services.analise_estrategica import analisar_caso

    result = await db.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail='Caso nao encontrado')

    partes_str = getattr(case, 'parte_contraria', None) or ''
    if partes_str:
        partes_str = f'Parte contraria: {partes_str}'

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

