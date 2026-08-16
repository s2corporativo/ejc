# ── app/routers/cases.py ─────────────────────────────────────────────────────
# Gestão de casos: CRUD + numeração DPT-AAAA-NNNN + prescrição automática
# + movimentos (timeline) + endpoint de análise IA integrado.
from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy import select, or_, func as sqlfunc, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import (get_current_user, require_roles, ROLE_LEVEL,
                                 requer_equipe_juridica, EQUIPE_JURIDICA)
from app.models.user import User
from app.models.case import Case, CaseMovimento, CaseStatus
from app.models.audit_log import criar_audit_log
# Alocador canônico de numero_interno extraído para service compartilhado
# (fonte única com a conversão da Sala Jurídica). Alias fino preserva os
# chamadores internos deste router.
from app.services.case_numeracao import proximo_numero_interno as _proximo_numero_interno
from app.services.deadline_calculator import calcular_prescricao
from app.services.case_intel import triagem_caso, aprendizado_encerramento
from app.services.case_automacao import automacao_caso, gerar_documentos_iniciais_auto
from app.services.fee_proposal_service import seed_proposta_honorarios_cadastro
from app.services import event_bus
from app.services.documental import gerar_documentos_iniciais
# Mesmo vocabulário/contrato de poderes do kit documental (fonte única do
# schema de procuração conservadora).
from app.routers.kit_documental import KitDocumentalIn, _req_advogado as _req_advogado_kit
from app.models.case_parte import CaseParte
from app.models.caso_area import CasoArea
from app.models.deadline import Deadline, DeadlineTipo, DeadlineStatus
from app.services.extracao_estruturada import parse_data_br
from app.core.ownership import verificar_acesso_caso
from app.core.status_caso import (
    STATUS_ABERTOS,
    validar_area_caso,
    validar_status_caso,
)
from app.services.ia_parser import titulo_e_json_bruto
from app.schemas.case import (
    CaseCreate, CaseUpdate, CaseResponse, CaseDetail, MovimentoCreate,
    MovimentoUpdate,
    CaseDeleteRequest,
)
from app.schemas.common import MsgResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/cases", tags=["Casos"])
_ARQUIVAMENTO_ROLES = ["superadmin", "admin", "socio", "advogado"]

# Status que exigem proxima_acao preenchido (G1 — caso sempre tem "o que fazer agora").
# Todo caso ABERTO exige próxima ação — inclusive protocolado (ex.: "aguardar
# citação"). Deriva da lista canônica para não divergir de status_caso.py.
_STATUS_EXIGE_PROXIMA_ACAO = {s.value for s in STATUS_ABERTOS}


def _validar_proxima_acao(payload, status_atual: str | None = None):
    """G1: valida que casos ativos têm proxima_acao definido.

    Chamado no criar() e no atualizar(). Não bloqueia encerramento/arquivamento.
    """
    status = (getattr(payload, "status", None) or status_atual or "aberto")
    proxima = getattr(payload, "proxima_acao", None)
    if status in _STATUS_EXIGE_PROXIMA_ACAO and not proxima:
        raise HTTPException(
            status_code=422,
            detail="Campo 'proxima_acao' é obrigatório para casos abertos (aberto/em_instrucao/em_producao/protocolado)",
        )


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
    # M04 (homologação 2026-08-15): gate EXATO de equipe jurídica no corpo —
    # require_roles(EQUIPE_JURIDICA) deixaria financeiro passar pelo fallback
    # hierárquico (Issue #694).
    requer_equipe_juridica(cu)
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
    # `area` e `status` são ENUM NATIVO no Postgres: string fora do enum não é
    # rejeitada pelo bind do SQLAlchemy, chega crua ao banco e estoura
    # InvalidTextRepresentation -> HTTP 500 (era o caso de `?status=all`).
    # Validamos aqui e devolvemos 422 dizendo o que é aceito. "Todos" é a
    # AUSÊNCIA do parâmetro — nenhum valor sentinela vai para a query.
    if area:
        try:
            q = q.where(Case.area == validar_area_caso(area))
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from None
    if status_f:
        try:
            q = q.where(Case.status == validar_status_caso(status_f))
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from None
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
    # M04 (homologação 2026-08-15): mesmo gate exato do listador.
    requer_equipe_juridica(cu)
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
    # `ativos` conta EXPLICITAMENTE os status abertos, em vez de subtrair os
    # fechados do total. Subtração presume que os fechados são só dois: se um
    # status novo entrar no enum, a subtração o classificaria como ativo em
    # silêncio. A lista canônica vive em core/status_caso.py.
    ativos = (await db.execute(
        select(sqlfunc.count()).select_from(base)
        .where(base.c.status.in_([s.value for s in STATUS_ABERTOS]))
    )).scalar() or 0

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

    # G1: casos ativos devem ter proxima_acao
    _validar_proxima_acao(payload)

    # Validar cliente — com GATE DE CARTEIRA (404 uniforme).
    # Só existência não basta: `advogado_responsavel_id` abaixo cai em `cu.id`
    # quando omitido, então criar caso com client_id de outra carteira fabricava
    # o vínculo que faz `pode_ver_cliente` liberar aquele cliente para sempre
    # (dossiê, CPF/CNPJ, procurações, data room). É a porta da frente da mesma
    # classe já fechada no Raio-X (`_resolver_cliente`) e na Sala Jurídica.
    from app.core.client_ownership import obter_cliente_autorizado
    await obter_cliente_autorizado(db, cu, payload.client_id)

    # Idempotência concorrente: o mesmo cliente e número processual não
    # podem criar dois casos ativos. O advisory lock serializa requisições
    # simultâneas; a comparação normaliza CNJ mascarado e texto administrativo.
    if payload.numero_processo:
        from app.services.validators_service import normalizar_cnj

        numero = payload.numero_processo.strip()
        digitos_cnj = normalizar_cnj(numero)
        numero_chave = digitos_cnj if len(digitos_cnj) == 20 else numero.casefold()
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:chave))"),
            {"chave": f"case_duplicate:{payload.client_id}:{numero_chave}"},
        )
        if len(digitos_cnj) == 20:
            numero_igual = (
                sqlfunc.regexp_replace(Case.numero_processo, r"\D", "", "g")
                == digitos_cnj
            )
        else:
            numero_igual = (
                sqlfunc.lower(sqlfunc.trim(Case.numero_processo))
                == numero.casefold()
            )
        caso_existente = (
            await db.execute(
                select(Case.id).where(
                    Case.client_id == payload.client_id,
                    Case.deleted_at.is_(None),
                    numero_igual,
                ).limit(1)
            )
        ).scalar_one_or_none()
        if caso_existente:
            raise HTTPException(
                status_code=409,
                detail="Já existe caso ativo para este cliente e número processual",
            )

    # `honorarios` (FASE 2) NÃO é coluna de Case — vira proposta vigente abaixo.
    data = payload.model_dump(exclude={"data_fato_prescricao", "honorarios"})
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
    # FASE 2: honorários do cadastro → proposta de honorários já vigente, na
    # MESMA transação do caso (atômico) e ANTES do background do kit. Assim o
    # gerar_documentos_iniciais_auto (que abre nova sessão após este commit)
    # encontra a proposta aprovada e o CONTRATO do kit sai preenchido. Sem
    # honorários (ou sem dado financeiro) → nada é semeado e o contrato mantém
    # os placeholders de revisão (comportamento legado). Idempotente.
    if payload.honorarios is not None:
        await seed_proposta_honorarios_cadastro(db, c.id, cu, payload.honorarios)
    await db.commit()
    await db.refresh(c)
    # NÚCLEO COGNITIVO — ETAPA 1: triagem jurídica automática (IA invisível).
    # Roda em background; preenche tese/pontos (se vazios) sem travar a resposta.
    background.add_task(automacao_caso, c.id)
    background.add_task(triagem_caso, c.id)
    # Kit documental inicial (procuração PODERES GERAIS + contrato) gerado em
    # BACKGROUND: o titular pediu geração automática na abertura de cada caso, sem
    # bloquear a resposta do POST. É idempotente e fail-safe (reusa
    # geracao_documental.gerar_kit_inicial via case_automacao). Engate feito só
    # aqui em criar() para a v1 — a conversão de lead poderia assinar
    # "caso.criado" no event_bus, mas o gatilho central da abertura é este.
    background.add_task(gerar_documentos_iniciais_auto, c.id, getattr(cu, "id", None))
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
    status_anterior = c.status.value if c.status else None

    # G1: valida proxima_acao — se o caso é/será ativo, exige campo
    status_novo = mudancas.get("status", status_anterior)
    proxima_nova = mudancas.get("proxima_acao", c.proxima_acao)
    if status_novo in _STATUS_EXIGE_PROXIMA_ACAO and not proxima_nova:
        raise HTTPException(
            status_code=422,
            detail="Campo 'proxima_acao' é obrigatório para casos abertos (aberto/em_instrucao/em_producao/protocolado)",
        )

    # Achado da auditoria (docs/PLANO_FUSAO_CASO_UNICO.md §4.3-5): este PATCH
    # genérico não pode ser um atalho para arquivar/encerrar — os dois têm
    # endpoint dedicado com gate de papel (POST /arquivar) e pós-mortem
    # obrigatório (POST /encerrar). Entrar em qualquer um dos dois por aqui
    # contornava ambos os gates. Sempre exige o endpoint dedicado — nenhuma
    # exceção por papel, para não manter dois caminhos com regras distintas
    # para o mesmo destino. Sair deles (reabertura) continua livre por PATCH.
    if mudancas.get("status") in ("arquivado", "encerrado") and \
            mudancas["status"] != status_anterior:
        # F-12 (auditoria funcional 16/08/2026): a mensagem anterior expunha a
        # rota interna da API ("Use POST /cases/{id}/arquivar") ao usuário.
        # Texto de negócio visível; o caminho técnico permanece só neste código.
        raise HTTPException(
            status_code=422,
            detail=(
                "O arquivamento de caso possui fluxo próprio com validações "
                "adicionais. Use a ação 'Arquivar caso' na ficha do caso."
                if mudancas["status"] == "arquivado"
                else "O encerramento de caso possui fluxo próprio, com "
                     "pós-mortem obrigatório. Use a ação 'Encerrar caso' "
                     "na ficha do caso."
            ),
        )

    for k, v in mudancas.items():
        setattr(c, k, v)
    # Só sobra a saída de "arquivado" por aqui (entrada é bloqueada acima) —
    # reabertura limpa o registro de arquivamento. Achado do code-reviewer:
    # sem o `!= "arquivado"`, um PATCH que reenvia o MESMO status (payload
    # "salvar tudo" reenviando o objeto inteiro) zerava archived_at/
    # archive_reason mesmo com o caso permanecendo arquivado, perdendo quando
    # e por que foi arquivado.
    if mudancas.get("status") and mudancas["status"] != "arquivado":
        c.archived_at = None
        c.archive_reason = None
    # Reabertura (sai de encerrado/arquivado para um estado de trabalho): limpa
    # os campos de desfecho — um caso reaberto não é mais um caso encerrado,
    # e deixá-los preencher contaminava jurimetria/case_health com um desfecho
    # que deixou de existir (achado da auditoria).
    if (
        status_anterior in ("encerrado", "arquivado")
        and mudancas.get("status") not in (None, "encerrado", "arquivado")
    ):
        c.data_encerramento = None
        c.resultado = None
        c.motivo_resultado = None
        c.provas_determinantes = None
        c.licoes_aprendidas = None

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
    c.status = CaseStatus.aberto
    c.archived_at = None
    c.archive_reason = None
    db.add(CaseMovimento(
        id=str(uuid4()), case_id=c.id, tipo="arquivamento",
        descricao="Caso desarquivado",
        created_by=cu.id,
    ))
    await criar_audit_log(
        db, cu.id, cu.role.value, "UNARCHIVE", "cases", case_id,
        dados_depois={"status": "aberto", "motivo_anterior": motivo_anterior or ""},
    )
    await db.commit()
    await db.refresh(c)
    background.add_task(
        event_bus.emitir, "caso.atualizado", "case", case_id,
        {"mudancas": ["status"], "status": CaseStatus.aberto.value}, cu.id,
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
        .order_by(CaseMovimento.data_evento.desc())
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
        tipo=payload.tipo, descricao=payload.descricao,
        data_evento=payload.data_evento, created_by=cu.id,
    )
    db.add(m)
    await db.commit()
    # M12 (homologação 2026-08-16): auditoria CREATE do movimento.
    _role_c = cu.role.value if hasattr(cu.role, "value") else str(cu.role)
    await criar_audit_log(
        db, cu.id, _role_c, "CREATE", "case_movimentos", case_id,
        dados_depois={"movimento_id": m.id, "tipo": m.tipo,
                      "descricao": (m.descricao or "")[:100]},
    )
    await db.commit()
    # Event bus: dispara tradução IA do andamento (subscriber) — fail-safe.
    background.add_task(
        event_bus.emitir, "movimento.criado", "case_movimento", m.id,
        {"tipo": m.tipo, "case_id": case_id}, cu.id,
    )
    return {"id": m.id, "detail": "Movimento registrado"}


@router.patch("/{case_id}/movimentos/{movimento_id}")
async def editar_movimento(
    case_id: str,
    movimento_id: str,
    payload: MovimentoUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """M12 (homologação 2026-08-16): edição de movimento da timeline.
    Patch parcial (só campos informados); guarda de acesso do caso;
    auditoria UPDATE. created_at/created_by nunca mudam (proveniência).
    """
    q = select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    q = _filtro_visibilidade(q, cu)
    if not (await db.execute(q)).scalar_one_or_none():
        raise HTTPException(status_code=404,
                            detail="Caso não encontrado ou sem permissão")
    q = select(CaseMovimento).where(CaseMovimento.id == movimento_id,
                                    CaseMovimento.case_id == case_id)
    m = (await db.execute(q)).scalars().first()
    if not m:
        raise HTTPException(status_code=404, detail="Movimento não encontrado")
    if payload.tipo is not None:
        m.tipo = payload.tipo
    if payload.descricao is not None:
        m.descricao = payload.descricao
    if payload.data_evento is not None:
        m.data_evento = payload.data_evento
    await db.commit()
    _role = cu.role.value if hasattr(cu.role, "value") else str(cu.role)
    await criar_audit_log(
        db, cu.id, _role, "UPDATE", "case_movimentos", case_id,
        dados_depois={"movimento_id": movimento_id, "tipo": m.tipo,
                      "descricao": m.descricao[:100]},
    )
    await db.commit()
    return {"id": m.id, "detail": "Movimento atualizado"}


@router.delete("/{case_id}/movimentos/{movimento_id}")
async def excluir_movimento(
    case_id: str,
    movimento_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """M12 (homologação 2026-08-16): exclusão de movimento da timeline.
    Hard delete (movimento não tem referências externas). Endurecido:
    movimento inexistente ou fora do caso retorna 404 (nunca 200)."""
    q = select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    q = _filtro_visibilidade(q, cu)
    if not (await db.execute(q)).scalar_one_or_none():
        raise HTTPException(status_code=404,
                            detail="Caso não encontrado ou sem permissão")
    q = select(CaseMovimento).where(CaseMovimento.id == movimento_id,
                                    CaseMovimento.case_id == case_id)
    m = (await db.execute(q)).scalars().first()
    if not m:
        raise HTTPException(status_code=404, detail="Movimento não encontrado")
    await db.delete(m)
    _role = cu.role.value if hasattr(cu.role, "value") else str(cu.role)
    await criar_audit_log(
        db, cu.id, _role, "DELETE", "case_movimentos", case_id,
        dados_depois={"movimento_id": movimento_id},
    )
    await db.commit()
    return {"detail": "Movimento removido"}


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
    from app.services import datajud_service as _djs
    try:
        novos = await _dj_sync(db, case)
    except _djs.DataJudDesabilitadoError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except _djs.TribunalNaoMapeadoError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:  # M12: falha externa nunca vira stack trace; 502 claro
        import logging as _lg
        _lg.getLogger("ejc.cases").warning(
            "sincronizar-processo falhou para %s: %s", case_id,
            f"{type(e).__name__}: {str(e)[:180]}")
        raise HTTPException(
            status_code=502,
            detail="Falha ao consultar o DataJud. Verifique a conexão/chave e tente novamente.")
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
        from app.models.ai_log import AILog, AITipoUso, AIStatusHITL, classificar_risco_ia
        log = AILog(
            user_id=current_user.id,
            case_id=case_id,
            tipo_uso=AITipoUso.analise_caso,
            prompt_sanitizado='analise_estrategica_completa',
            resposta=_json.dumps(analise, ensure_ascii=False)[:10000],
            risco_ia=classificar_risco_ia("analise_juridica"),
            status_hitl=AIStatusHITL.gerado,
            pii_removida=True,
        )
        db.add(log)
        await db.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f'AILog nao salvo: {e}')

    return analise

