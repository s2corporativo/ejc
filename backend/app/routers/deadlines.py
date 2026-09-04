# ── app/routers/deadlines.py ─────────────────────────────────────────────────
# Prazos: CRUD + cálculo automático por regime + confirmação de ciência.
from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func as sqlfunc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import is_gestao, verificar_acesso_caso
from app.core.security import get_current_user, requer_advogado
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.deadline import Deadline, DeadlineStatus
from app.models.user import User, UserRole
from app.schemas.common import MsgResponse
from app.schemas.deadline import (
    CalcularPrazoRequest,
    DeadlineCreate,
    DeadlineResponse,
    DeadlineUpdate,
)
from app.services.deadline_audit_service import (
    DuplaValidacaoError,
    ProvaIncompletaError,
    adicionar_notificacao_reconferencia,
    construir_prova_calculo,
    invalidar_conferencia,
    prazo_critico,
    preparar_estado_inicial,
    registrar_conferencia,
    validar_marcos_prazo,
)
from app.services.deadline_calculator import (
    calcular_prazo_processual,
    dias_uteis_restantes,
    estado_degradacao,
    prazo_dias_corridos,
    prazo_dias_uteis,
)

router = APIRouter(prefix="/deadlines", tags=["Prazos"])
logger = logging.getLogger("ejc.deadlines")

_MAX_EXPORT = 5000
_ROLES_RESPONSAVEIS = {
    UserRole.superadmin,
    UserRole.admin,
    UserRole.socio,
    UserRole.advogado,
    UserRole.advogado_auxiliar,
    UserRole.estagiario,
    UserRole.secretaria,
}
_MATERIAL_CALCULO = {
    "data_prazo",
    "data_publicacao",
    "termo_inicial",
    "regime_calculo",
    "base_legal",
    "prioridade",
}


def _ids_casos_do_usuario(user: User):
    return (
        select(Case.id)
        .where(
            Case.deleted_at.is_(None),
            or_(
                Case.advogado_responsavel_id == user.id,
                Case.advogado_auxiliar_id == user.id,
            ),
        )
        .scalar_subquery()
    )


def _filtro_escopo_prazos(q, cu: User):
    """Escopo de leitura: prazo avulso é pessoal; prazo de caso herda o caso."""
    if is_gestao(cu):
        return q
    return q.where(
        or_(
            Deadline.case_id.in_(_ids_casos_do_usuario(cu)),
            Deadline.responsavel_id == cu.id,
        )
    )


def _normalizar_status_filtro(status_f: str | None) -> str | None:
    """`all`, vazio ou ausência significam sem filtro; desconhecido => 422."""
    valor = (status_f or "").strip().lower()
    if not valor or valor == "all":
        return None
    validos = {status.value for status in DeadlineStatus}
    if valor not in validos:
        raise HTTPException(
            status_code=422,
            detail=f"status inválido: use um de {sorted(validos)} ou all",
        )
    return valor


async def _verificar_acesso_prazo(
    db: AsyncSession,
    cu: User,
    prazo: Deadline,
) -> None:
    if prazo.case_id:
        await verificar_acesso_caso(db, cu, prazo.case_id)
        return
    if is_gestao(cu) or prazo.responsavel_id == cu.id:
        return
    raise HTTPException(status_code=404, detail="Prazo não encontrado")


async def _validar_responsavel_prazo(
    db: AsyncSession,
    cu: User,
    responsavel_id: str,
    *,
    case_id: str | None,
) -> User:
    if responsavel_id == cu.id:
        if (
            cu.role not in _ROLES_RESPONSAVEIS
            or getattr(cu, "deleted_at", None) is not None
            or getattr(cu, "is_active", True) is False
        ):
            raise HTTPException(
                status_code=422,
                detail="responsavel_id inválido: usuário atual não é elegível",
            )
        return cu

    alvo = (
        await db.execute(
            select(User).where(
                User.id == responsavel_id,
                User.deleted_at.is_(None),
                User.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if alvo is None or alvo.role not in _ROLES_RESPONSAVEIS:
        raise HTTPException(
            status_code=422,
            detail="responsavel_id inválido: informe usuário interno ativo e elegível",
        )

    if is_gestao(cu):
        return alvo

    if not case_id:
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para atribuir prazo avulso a outro usuário",
        )

    caso = await verificar_acesso_caso(db, cu, case_id)
    if alvo.id not in (
        caso.advogado_responsavel_id,
        caso.advogado_auxiliar_id,
    ):
        raise HTTPException(
            status_code=403,
            detail="Responsável informado não pertence à equipe jurídica do caso",
        )
    return alvo


def _resolver_regime_processual(
    regime: str | None,
    dias_uteis: bool,
) -> tuple[str, bool]:
    """Prazo processual exige regime explícito; nunca presume CPC."""
    del dias_uteis
    if regime:
        return regime, False
    raise HTTPException(
        status_code=422,
        detail=(
            "Prazo processual exige regime_calculo explícito. "
            "Use civel, trabalhista ou penal."
        ),
    )


def _base_processual(
    regime: str,
    dias: int,
    dobro: bool,
    *,
    legado: bool,
    excecao_recesso_penal: bool,
) -> str:
    if regime == "penal":
        base = f"{dias} dias — CPP art. 798 c/c art. 798-A"
        if excecao_recesso_penal:
            base += " (exceção ao recesso declarada pelo operador)"
    elif regime == "trabalhista":
        base = f"{dias} dias úteis — CLT arts. 775 e 775-A"
    else:
        base = (
            f"{dias} dias úteis em dobro (CPC arts. 180/183/186/229)"
            if dobro
            else f"{dias} dias úteis (CPC art. 219)"
        )
        base += " + recesso forense integral (CPC art. 220)"
    if legado:
        base += " · regime assumido por compatibilidade; conferir"
    return base


def _validar_criticidade_estruturada(
    *,
    tipo: str,
    prioridade: str,
    regime_calculo: str | None,
    termo_inicial: date | None,
) -> None:
    if prioridade != "critica" or tipo != "processual":
        return
    if not regime_calculo:
        raise HTTPException(
            status_code=422,
            detail="Prazo processual crítico exige regime_calculo explícito",
        )
    if not termo_inicial:
        raise HTTPException(
            status_code=422,
            detail="Prazo processual crítico exige termo_inicial explícito",
        )


@router.post("/calcular")
async def calcular(
    req: CalcularPrazoRequest,
    cu: User = Depends(get_current_user),
):
    """Calculadora rápida, sem persistir, com regime processual explícito."""
    del cu
    if req.dias < 1:
        raise HTTPException(status_code=422, detail="dias deve ser maior que zero")

    if req.tipo == "processual":
        regime, legado = _resolver_regime_processual(
            req.regime_calculo,
            req.dias_uteis,
        )
        if req.excecao_recesso_penal and regime != "penal":
            raise HTTPException(
                status_code=422,
                detail="excecao_recesso_penal só é válida para regime penal",
            )
        try:
            resultado = calcular_prazo_processual(
                req.data_inicio,
                req.dias,
                regime,  # type: ignore[arg-type]
                tribunal=req.tribunal,
                em_dobro=req.dobro,
                excecao_recesso_penal=req.excecao_recesso_penal,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        resultado["regime_assumido_por_compatibilidade"] = legado
        resultado["dias_uteis_restantes"] = dias_uteis_restantes(
            resultado["data_vencimento"]
        )
        return resultado

    if req.excecao_recesso_penal or req.regime_calculo == "penal":
        raise HTTPException(
            status_code=422,
            detail="Regime penal só pode ser usado em prazo tipo=processual",
        )

    if req.dias_uteis:
        vencimento = prazo_dias_uteis(
            req.data_inicio,
            req.dias,
            tribunal=req.tribunal,
            em_dobro=req.dobro,
            aplicar_recesso=False,
            forense=False,
        )
        modo = "dias úteis sem recesso processual"
    else:
        vencimento = prazo_dias_corridos(
            req.data_inicio,
            req.dias,
            tribunal=req.tribunal,
        )
        modo = "dias corridos c/ prorrogação do termo final (Lei 9.784 art. 66 §1º)"
    # O prazo administrativo usa as MESMAS funções de dia útil e os MESMOS
    # feriados do banco que o processual — então degrada pelos mesmos motivos.
    # Antes estes três campos eram fixos (`False`/`False`/`None`): com a carga
    # de feriados falha, o prazo saía carimbado como DEFINITIVO sem os feriados
    # municipais, e ninguém era avisado. Mesma classe de defeito que este PR já
    # corrigiu em calcular_prazo_processual; agora ambos leem a fonte única.
    degradado, aviso = estado_degradacao(req.tribunal)
    return {
        "data_vencimento": vencimento,
        "modo": modo,
        "regime_calculo": "administrativo" if req.tipo == "administrativo" else None,
        "resultado_preliminar": degradado,
        "revisao_obrigatoria": degradado,
        "aviso": aviso,
        "dias_uteis_restantes": dias_uteis_restantes(vencimento),
    }


@router.get("/")
async def listar(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status_f: Optional[str] = Query("pendente", alias="status"),
    case_id: Optional[str] = None,
    tipo: Optional[str] = None,
    apenas_meus: bool = False,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(Deadline).where(Deadline.deleted_at.is_(None))
    status_normalizado = _normalizar_status_filtro(status_f)
    if status_normalizado:
        q = q.where(Deadline.status == status_normalizado)
    if case_id:
        q = q.where(Deadline.case_id == case_id)
    if tipo:
        q = q.where(Deadline.tipo == tipo)
    q = _filtro_escopo_prazos(q, cu)
    if apenas_meus:
        q = q.where(Deadline.responsavel_id == cu.id)
    q = q.order_by(Deadline.data_prazo.asc())

    total = (
        await db.execute(select(sqlfunc.count()).select_from(q.subquery()))
    ).scalar()
    rows = (
        await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()

    hoje = date.today()
    data = []
    for d in rows:
        item = DeadlineResponse.model_validate(d).model_dump()
        dias = (d.data_prazo - hoje).days
        item["dias_restantes"] = dias
        item["urgencia"] = (
            "vencido"
            if dias < 0
            else "critico"
            if dias <= 3
            else "atencao"
            if dias <= 7
            else "normal"
        )
        data.append(item)
    return {
        "data": data,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/export.csv")
async def exportar_csv(
    status_f: Optional[str] = Query("pendente", alias="status"),
    case_id: Optional[str] = None,
    tipo: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(Deadline).where(Deadline.deleted_at.is_(None))
    status_normalizado = _normalizar_status_filtro(status_f)
    if status_normalizado:
        q = q.where(Deadline.status == status_normalizado)
    if case_id:
        q = q.where(Deadline.case_id == case_id)
    if tipo:
        q = q.where(Deadline.tipo == tipo)
    q = _filtro_escopo_prazos(q, cu)
    q = q.order_by(Deadline.data_prazo.asc()).limit(_MAX_EXPORT + 1)
    rows = (await db.execute(q)).scalars().all()
    if len(rows) > _MAX_EXPORT:
        rows = rows[:_MAX_EXPORT]
        logger.warning("[export.csv] resultado truncado em %d linhas", _MAX_EXPORT)

    return Response(
        content=_prazos_para_csv(rows, date.today()),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="prazos.csv"'},
    )


def _prazos_para_csv(rows, hoje: date) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(
        [
            "Titulo",
            "Tipo",
            "Prioridade",
            "Status",
            "Data do prazo",
            "Data da intimacao",
            "Dias restantes",
            "Base legal",
        ]
    )
    for d in rows:
        dias = (d.data_prazo - hoje).days if d.data_prazo else ""
        w.writerow(
            [
                d.titulo or "",
                d.tipo or "",
                d.prioridade or "",
                d.status or "",
                d.data_prazo.isoformat() if d.data_prazo else "",
                (
                    d.data_intimacao.isoformat()
                    if getattr(d, "data_intimacao", None)
                    else ""
                ),
                dias,
                getattr(d, "base_legal", "") or "",
            ]
        )
    return "﻿" + buf.getvalue()


@router.post("/", status_code=201)
async def criar(
    payload: DeadlineCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    data_prazo = payload.data_prazo
    base = payload.base_legal
    confirmado_motor = True
    calculo_audit: dict | None = None
    base_calculo = payload.termo_inicial or payload.data_intimacao

    _validar_criticidade_estruturada(
        tipo=payload.tipo,
        prioridade=payload.prioridade,
        regime_calculo=payload.regime_calculo,
        termo_inicial=payload.termo_inicial,
    )

    if not data_prazo and payload.dias_prazo and base_calculo:
        if payload.tipo == "processual":
            regime, legado = _resolver_regime_processual(
                payload.regime_calculo,
                payload.dias_uteis,
            )
            if payload.excecao_recesso_penal and regime != "penal":
                raise HTTPException(
                    status_code=422,
                    detail="excecao_recesso_penal só é válida para regime penal",
                )
            try:
                calculo_audit = calcular_prazo_processual(
                    base_calculo,
                    payload.dias_prazo,
                    regime,  # type: ignore[arg-type]
                    tribunal=payload.tribunal,
                    em_dobro=payload.dobro,
                    excecao_recesso_penal=payload.excecao_recesso_penal,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            data_prazo = calculo_audit["data_vencimento"]
            base = base or _base_processual(
                regime,
                payload.dias_prazo,
                payload.dobro,
                legado=legado,
                excecao_recesso_penal=payload.excecao_recesso_penal,
            )
            if calculo_audit["resultado_preliminar"]:
                confirmado_motor = False
                base += " · CALENDÁRIO DEGRADADO: conferência humana obrigatória"
        elif payload.dias_uteis:
            data_prazo = prazo_dias_uteis(
                base_calculo,
                payload.dias_prazo,
                tribunal=payload.tribunal,
                em_dobro=payload.dobro,
                aplicar_recesso=False,
                forense=False,
            )
            base = base or (
                f"{payload.dias_prazo} dias úteis (sem recesso processual)"
            )
        else:
            data_prazo = prazo_dias_corridos(
                base_calculo,
                payload.dias_prazo,
                tribunal=payload.tribunal,
            )
            base = base or f"{payload.dias_prazo} dias corridos (Lei 9.784)"

    if not data_prazo:
        raise HTTPException(
            status_code=422,
            detail=(
                "Informe data_prazo OU "
                "((termo_inicial ou data_intimacao) + dias_prazo)"
            ),
        )

    try:
        validar_marcos_prazo(
            data_publicacao=payload.data_publicacao,
            termo_inicial=payload.termo_inicial,
            termo_final=data_prazo,
        )
    except ProvaIncompletaError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    caso = None
    if payload.case_id:
        caso = await verificar_acesso_caso(db, cu, payload.case_id)

    responsavel_id = payload.responsavel_id or cu.id
    await _validar_responsavel_prazo(
        db,
        cu,
        responsavel_id,
        case_id=payload.case_id,
    )
    if caso is not None and not is_gestao(cu) and responsavel_id not in (
        caso.advogado_responsavel_id,
        caso.advogado_auxiliar_id,
    ):
        raise HTTPException(
            status_code=403,
            detail="Responsável informado não pertence à equipe jurídica do caso",
        )

    confirmado, calculado_por = preparar_estado_inicial(
        prioridade=payload.prioridade,
        actor_id=cu.id,
        confirmado_motor=confirmado_motor,
    )
    prova = construir_prova_calculo(
        actor_id=cu.id,
        data_ciencia=payload.data_intimacao,
        data_publicacao=payload.data_publicacao,
        termo_inicial=payload.termo_inicial,
        termo_final=data_prazo,
        regime=payload.regime_calculo if payload.tipo == "processual" else None,
        tribunal=payload.tribunal,
        dias=payload.dias_prazo,
        dobro=payload.dobro,
        excecao_recesso_penal=payload.excecao_recesso_penal,
        base_legal=base,
        resultado=calculo_audit,
        modo_origem="motor_canonico" if calculo_audit else "vencimento_manual",
    )

    d = Deadline(
        id=str(uuid4()),
        titulo=payload.titulo,
        tipo=payload.tipo,
        prioridade=payload.prioridade,
        descricao=payload.descricao,
        data_prazo=data_prazo,
        data_intimacao=payload.data_intimacao,
        data_publicacao=payload.data_publicacao,
        termo_inicial=payload.termo_inicial,
        regime_calculo=(
            payload.regime_calculo if payload.tipo == "processual" else None
        ),
        calculo_metadata=prova,
        calculado_por=calculado_por,
        conferido_por=None,
        conferido_em=None,
        base_legal=base,
        case_id=payload.case_id,
        responsavel_id=responsavel_id,
        confirmado=confirmado,
    )
    db.add(d)
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "CREATE",
        "deadlines",
        d.id,
        dados_depois={
            "calculo_automatico": calculo_audit is not None,
            "regime_calculo": d.regime_calculo,
            "calendario_status": prova.get("calendario_status"),
            "resultado_preliminar": prova.get("resultado_preliminar"),
            "estado_validacao": prova.get("estado_validacao"),
            "prioridade": payload.prioridade,
        },
    )
    await db.commit()
    await db.refresh(d)
    return DeadlineResponse.model_validate(d)


@router.patch("/{deadline_id}")
async def atualizar(
    deadline_id: str,
    payload: DeadlineUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    d = (
        await db.execute(
            select(Deadline).where(
                Deadline.id == deadline_id,
                Deadline.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")
    await _verificar_acesso_prazo(db, cu, d)

    mudancas = payload.model_dump(exclude_unset=True)
    status_antes = getattr(d.status, "value", d.status)
    data_antes = d.data_prazo
    responsavel_antes = d.responsavel_id

    if "data_prazo" in mudancas and mudancas["data_prazo"] is None:
        raise HTTPException(status_code=422, detail="data_prazo não pode ser vazio")

    if "responsavel_id" in mudancas:
        novo_responsavel = mudancas["responsavel_id"]
        if not novo_responsavel:
            raise HTTPException(
                status_code=422,
                detail="responsavel_id não pode ser vazio",
            )
        await _validar_responsavel_prazo(
            db,
            cu,
            novo_responsavel,
            case_id=d.case_id,
        )

    candidato_prazo = mudancas.get("data_prazo", d.data_prazo)
    candidato_publicacao = mudancas.get("data_publicacao", d.data_publicacao)
    candidato_termo = mudancas.get("termo_inicial", d.termo_inicial)
    candidato_regime = mudancas.get("regime_calculo", d.regime_calculo)
    candidato_prioridade = mudancas.get(
        "prioridade",
        getattr(d.prioridade, "value", d.prioridade),
    )
    candidato_tipo = getattr(d.tipo, "value", d.tipo)

    try:
        validar_marcos_prazo(
            data_publicacao=candidato_publicacao,
            termo_inicial=candidato_termo,
            termo_final=candidato_prazo,
        )
    except ProvaIncompletaError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _validar_criticidade_estruturada(
        tipo=candidato_tipo,
        prioridade=candidato_prioridade,
        regime_calculo=candidato_regime,
        termo_inicial=candidato_termo,
    )

    material_antes = {
        campo: getattr(d, campo)
        for campo in _MATERIAL_CALCULO
        if campo in mudancas
    }

    if "data_prazo" in mudancas and mudancas["data_prazo"] != d.data_prazo:
        await criar_audit_log(
            db,
            cu.id,
            cu.role.value,
            "PRAZO_ALTERADO",
            "deadlines",
            deadline_id,
            dados_antes={"data_prazo": str(d.data_prazo)},
            dados_depois={"data_prazo": str(mudancas["data_prazo"])},
        )

    for k, v in mudancas.items():
        setattr(d, k, v)

    material_depois = {
        campo: getattr(d, campo)
        for campo in material_antes
    }
    campos_materiais_alterados = [
        campo
        for campo in material_antes
        if material_antes[campo] != material_depois[campo]
    ]
    if campos_materiais_alterados:
        havia_conferencia = invalidar_conferencia(
            d,
            actor_id=cu.id,
            motivo="alteracao_material",
            antes=material_antes,
            depois=material_depois,
        )
        await criar_audit_log(
            db,
            cu.id,
            cu.role.value,
            "PRAZO_PROVA_REABERTA",
            "deadlines",
            deadline_id,
            dados_depois={
                "campos_alterados": sorted(campos_materiais_alterados),
                "havia_conferencia": havia_conferencia,
                "novo_calculista": cu.id,
            },
        )
        if havia_conferencia:
            adicionar_notificacao_reconferencia(db, d.responsavel_id)

    mudou_data = d.data_prazo != data_antes
    mudou_responsavel = d.responsavel_id != responsavel_antes
    if mudou_data or mudou_responsavel:
        d.alerta_7d_enviado = False
        d.alerta_3d_enviado = False
        d.alerta_1d_enviado = False
        await criar_audit_log(
            db,
            cu.id,
            cu.role.value,
            "PRAZO_ALERTAS_REINICIADOS",
            "deadlines",
            deadline_id,
            dados_depois={
                "motivo": (
                    "data_e_responsavel"
                    if mudou_data and mudou_responsavel
                    else "data_prazo"
                    if mudou_data
                    else "responsavel"
                )
            },
        )

    if (
        "data_prazo" in mudancas
        and "status" not in mudancas
        and getattr(d.status, "value", d.status) == "vencido"
        and d.data_prazo >= date.today()
    ):
        d.status = "pendente"
        await criar_audit_log(
            db,
            cu.id,
            cu.role.value,
            "PRAZO_REABERTO",
            "deadlines",
            deadline_id,
            dados_antes={"status": "vencido"},
            dados_depois={
                "status": "pendente",
                "motivo": "reagendado para data futura",
            },
        )

    if mudancas.get("status") == "concluido" and status_antes != "concluido":
        d.data_conclusao = datetime.now(timezone.utc)
        d.concluido_por = cu.id
        await criar_audit_log(
            db,
            cu.id,
            cu.role.value,
            "PRAZO_CONCLUIDO",
            "deadlines",
            deadline_id,
            dados_antes={"status": status_antes},
            dados_depois={
                "status": "concluido",
                "concluido_por": cu.id,
                "data_conclusao": d.data_conclusao.isoformat(),
            },
        )
    await db.commit()
    await db.refresh(d)
    return DeadlineResponse.model_validate(d)


@router.patch("/{deadline_id}/confirmar", response_model=DeadlineResponse)
async def confirmar(
    deadline_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    d = (
        await db.execute(
            select(Deadline).where(
                Deadline.id == deadline_id,
                Deadline.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")
    await _verificar_acesso_prazo(db, cu, d)

    if d.confirmado and not prazo_critico(d):
        return DeadlineResponse.model_validate(d)
    if (
        d.confirmado
        and prazo_critico(d)
        and d.conferido_por
        and d.conferido_por != d.calculado_por
    ):
        return DeadlineResponse.model_validate(d)

    try:
        registrar_conferencia(d, cu.id)
    except DuplaValidacaoError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProvaIncompletaError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "PRAZO_CONFERIDO",
        "deadlines",
        deadline_id,
        dados_depois={
            "calculado_por": d.calculado_por,
            "conferido_por": d.conferido_por,
            "dupla_validacao": prazo_critico(d),
        },
    )
    await db.commit()
    await db.refresh(d)
    return DeadlineResponse.model_validate(d)


@router.post("/{deadline_id}/ciencia", response_model=MsgResponse)
async def confirmar_ciencia(
    deadline_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    d = (
        await db.execute(
            select(Deadline).where(
                Deadline.id == deadline_id,
                Deadline.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")
    await _verificar_acesso_prazo(db, cu, d)

    d.ciencia_confirmada = True
    d.ciencia_confirmada_em = datetime.now(timezone.utc)
    d.ciencia_confirmada_por = cu.id
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "CIENCIA_PRAZO",
        "deadlines",
        deadline_id,
    )
    await db.commit()
    return MsgResponse(detail="Ciência confirmada")


@router.delete("/{deadline_id}", response_model=MsgResponse)
async def cancelar(
    deadline_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    requer_advogado(cu, detail="Sem permissão para cancelar prazos")
    d = (
        await db.execute(
            select(Deadline).where(
                Deadline.id == deadline_id,
                Deadline.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")
    await _verificar_acesso_prazo(db, cu, d)
    d.deleted_at = datetime.now(timezone.utc)
    d.status = "cancelado"
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "DELETE",
        "deadlines",
        deadline_id,
    )
    await db.commit()
    return MsgResponse(detail="Prazo cancelado")
