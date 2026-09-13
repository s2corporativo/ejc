# ── app/routers/atendimentos.py ────────────────────────────────────────────────
# Histórico de atendimentos ao cliente — CRM básico jurídico.
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import is_gestao, verificar_acesso_caso
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.atendimento import Atendimento, AtendimentoTipo
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.client import Client
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.modules.auditoria.middleware import registrar_acao
from app.services.notification_service import notificar

router = APIRouter(prefix="/atendimentos", tags=["Atendimentos"])
logger = logging.getLogger(__name__)

# O módulo Clientes usa esta mesma matriz. A lista explícita evita que perfis
# internos sem atribuição de CRM recebam acesso apenas pelo nível numérico.
_ATENDIMENTO_ROLES = {"superadmin", "admin", "socio", "advogado", "secretaria"}
_SOLICITACAO_PRIORIDADES = {"baixa", "normal", "alta", "urgente"}
_CONTATO_STATUS = {"iniciado", "confirmado", "nao_concluido"}
_TASK_PRIORIDADE = {
    "baixa": "baixa",
    "normal": "media",
    "alta": "alta",
    "urgente": "urgente",
}


# ── Schemas ───────────────────────────────────────────────────────────────────

class AtendimentoIn(BaseModel):
    client_id:                      str
    case_id:                        Optional[str]   = None
    tipo:                           AtendimentoTipo
    data_atendimento:               datetime
    duracao_min:                    Optional[str]   = Field(None, max_length=10)
    resumo:                         str = Field(min_length=10, max_length=4000)
    proximo_passo:                  Optional[str]   = Field(None, max_length=4000)
    solicitacao:                    Optional[str]   = Field(None, max_length=4000)
    solicitacao_atendida:           bool            = False
    solicitacao_prazo:              Optional[datetime] = None
    solicitacao_prioridade:         str             = Field("normal", max_length=10)
    solicitacao_responsavel_id:     Optional[str]   = None
    criar_tarefa:                   bool            = False
    contato_status:                 str             = Field("confirmado", max_length=20)
    observacoes_privadas:           Optional[str]   = Field(None, max_length=4000)
    advogado_responsavel_id:        Optional[str]   = None
    duracao_horas:                  Optional[float] = Field(None, ge=0, le=24)
    satisfacao_cliente:             Optional[int]   = Field(None, ge=1, le=5)


class AtendimentoPatch(BaseModel):
    tipo:                           Optional[AtendimentoTipo] = None
    data_atendimento:               Optional[datetime]        = None
    duracao_min:                    Optional[str]             = Field(None, max_length=10)
    resumo:                         Optional[str]             = Field(None, min_length=10, max_length=4000)
    proximo_passo:                  Optional[str]             = Field(None, max_length=4000)
    solicitacao:                    Optional[str]             = Field(None, max_length=4000)
    solicitacao_atendida:           Optional[bool]            = None
    solicitacao_prazo:              Optional[datetime]        = None
    solicitacao_prioridade:         Optional[str]             = Field(None, max_length=10)
    solicitacao_responsavel_id:     Optional[str]             = None
    contato_status:                 Optional[str]             = Field(None, max_length=20)
    observacoes_privadas:           Optional[str]             = Field(None, max_length=4000)
    advogado_responsavel_id:        Optional[str]             = None
    duracao_horas:                  Optional[float]           = Field(None, ge=0, le=24)
    satisfacao_cliente:             Optional[int]             = Field(None, ge=1, le=5)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _role_str(user: User) -> str:
    role = getattr(user, "role", None)
    return role.value if hasattr(role, "value") else str(role)


def _is_staff(user: User) -> bool:
    return _role_str(user) in _ATENDIMENTO_ROLES


def _pode_ver_privado(user: User) -> bool:
    return ROLE_LEVEL.get(_role_str(user), 0) >= ROLE_LEVEL["advogado"]


# Papéis de recepção/atendimento que precisam da carteira INTEIRA (triagem de
# leads/funil). Espelha clients._CLIENTES_VISAO_TOTAL — a segregação de sigilo
# (advogado lendo atendimentos de clientes de OUTRAS carteiras) incide só sobre
# advogado/advogado_auxiliar; gestão e recepção veem tudo por necessidade
# operacional. estagiario/financeiro nem chegam aqui (fora de _ATENDIMENTO_ROLES).
_ATENDIMENTO_VISAO_TOTAL = {"secretaria"}


def _filtro_visibilidade_atendimento(q, cu: User):
    """Segregação de titularidade (sigilo interno — LGPD/EOAB) na LISTAGEM.
    Espelha clients._filtro_visibilidade_cliente: gestão e recepção veem tudo;
    advogado/advogado_auxiliar só veem atendimentos de clientes da própria
    carteira — cujo cliente é responsavel_id do usuário OU tem caso NÃO excluído
    em que ele é advogado responsável/auxiliar."""
    if is_gestao(cu) or _role_str(cu) in _ATENDIMENTO_VISAO_TOTAL:
        return q
    clientes_do_advogado = (
        select(Client.id).where(
            or_(
                Client.responsavel_id == cu.id,
                Client.id.in_(
                    select(Case.client_id).where(
                        Case.client_id.is_not(None),
                        Case.deleted_at.is_(None),
                        or_(
                            Case.advogado_responsavel_id == cu.id,
                            Case.advogado_auxiliar_id == cu.id,
                        ),
                    )
                ),
            )
        )
    )
    # Inclui atendimentos SEM cliente vinculado (avulsos) — coerente com o gate
    # row-level _pode_ver_atendimento, que libera registro sem client_id.
    return q.where(
        or_(
            Atendimento.client_id.is_(None),
            Atendimento.client_id.in_(clientes_do_advogado),
        )
    )


async def _pode_ver_atendimento(db: AsyncSession, cu: User, a: Atendimento) -> bool:
    """Versão row-level de _filtro_visibilidade_atendimento (detalhe/histórico).
    Gestão/recepção veem tudo; demais só o próprio registro (criador/responsável)
    ou atendimentos de clientes da própria carteira."""
    if is_gestao(cu) or _role_str(cu) in _ATENDIMENTO_VISAO_TOTAL:
        return True
    if cu.id in {a.created_by, a.advogado_responsavel_id, a.solicitacao_responsavel_id}:
        return True
    if not a.client_id:
        return True  # atendimento sem cliente vinculado não pertence a carteira alheia
    cli = (await db.execute(
        select(Client).where(Client.id == a.client_id)
    )).scalar_one_or_none()
    if cli is not None and cli.responsavel_id == cu.id:
        return True
    vinculo = (await db.execute(
        select(Case.id).where(
            Case.client_id == a.client_id,
            Case.deleted_at.is_(None),
            or_(
                Case.advogado_responsavel_id == cu.id,
                Case.advogado_auxiliar_id == cu.id,
            ),
        ).limit(1)
    )).first()
    return vinculo is not None


def _pode_editar_atendimento(a: Atendimento, user: User) -> bool:
    if not _is_staff(user):
        return False
    if ROLE_LEVEL.get(_role_str(user), 0) >= ROLE_LEVEL["socio"]:
        return True
    return user.id in {
        a.created_by,
        a.advogado_responsavel_id,
        a.solicitacao_responsavel_id,
    }


def _utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalizar_texto(value: Optional[str]) -> Optional[str]:
    texto = (value or "").strip()
    return texto or None


def _validar_prioridade(value: str) -> str:
    prioridade = (value or "").strip().lower()
    if prioridade not in _SOLICITACAO_PRIORIDADES:
        raise HTTPException(
            status_code=422,
            detail="Prioridade inválida. Use baixa, normal, alta ou urgente",
        )
    return prioridade


def _validar_contato_status(value: str) -> str:
    status = (value or "").strip().lower()
    if status not in _CONTATO_STATUS:
        raise HTTPException(
            status_code=422,
            detail="Status do contato inválido",
        )
    return status


def _solicitacao_atrasada(a: Atendimento) -> bool:
    prazo = _utc(a.solicitacao_prazo)
    return bool(
        _normalizar_texto(a.solicitacao)
        and not a.solicitacao_atendida
        and prazo
        and prazo < datetime.now(timezone.utc)
    )


def _out(a: Atendimento, user: User, com_privado: bool = True) -> dict:
    return {
        "id":                          a.id,
        "client_id":                   a.client_id,
        "case_id":                     a.case_id,
        "tipo":                        a.tipo.value if hasattr(a.tipo, "value") else a.tipo,
        "data_atendimento":            a.data_atendimento.isoformat() if a.data_atendimento else None,
        "duracao_min":                 a.duracao_min,
        "duracao_horas":               float(a.duracao_horas) if a.duracao_horas is not None else None,
        "resumo":                      a.resumo,
        "proximo_passo":               a.proximo_passo,
        "solicitacao":                 a.solicitacao,
        "solicitacao_atendida":        bool(a.solicitacao_atendida),
        "solicitacao_atrasada":        _solicitacao_atrasada(a),
        "solicitacao_prazo":           a.solicitacao_prazo.isoformat() if a.solicitacao_prazo else None,
        "solicitacao_prioridade":      a.solicitacao_prioridade or "normal",
        "solicitacao_responsavel_id":  a.solicitacao_responsavel_id,
        "atendida_em":                 a.atendida_em.isoformat() if a.atendida_em else None,
        "atendida_por_id":             a.atendida_por_id,
        "task_id":                     a.task_id,
        "contato_status":              a.contato_status or "confirmado",
        "observacoes_privadas":        a.observacoes_privadas if com_privado else None,
        "advogado_responsavel_id":     a.advogado_responsavel_id,
        "satisfacao_cliente":          a.satisfacao_cliente,
        "created_by":                  a.created_by,
        "created_at":                  a.created_at.isoformat() if a.created_at else None,
        "updated_at":                  a.updated_at.isoformat() if a.updated_at else None,
        "pode_editar":                 _pode_editar_atendimento(a, user),
    }


async def _obter_atendimento(atendimento_id: str, db: AsyncSession) -> Atendimento:
    atendimento = (
        await db.execute(select(Atendimento).where(Atendimento.id == atendimento_id))
    ).scalar_one_or_none()
    if atendimento is None:
        raise HTTPException(status_code=404, detail="Atendimento não encontrado")
    return atendimento


async def _validar_cliente(db: AsyncSession, client_id: str) -> Client:
    cliente = (
        await db.execute(
            select(Client).where(
                Client.id == client_id,
                Client.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return cliente


async def _validar_responsavel(
    db: AsyncSession,
    user_id: Optional[str],
) -> Optional[User]:
    if not user_id:
        return None
    responsavel = (
        await db.execute(
            select(User).where(
                User.id == user_id,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if responsavel is None or _role_str(responsavel) not in _ATENDIMENTO_ROLES:
        raise HTTPException(status_code=422, detail="Responsável inválido")
    return responsavel


async def _validar_responsavel_tarefa_no_caso(
    db: AsyncSession,
    responsavel: Optional[User],
    case_id: Optional[str],
) -> None:
    """Impede atribuir Task de atendimento a usuário fora da carteira do caso.

    Reusa o gate canônico de ownership do próprio caso. A resposta ao caller é
    422 genérica para não expor detalhes do caso ao usuário-alvo inválido.
    Atendimento sem caso, sem responsável ou sem Task mantém o comportamento
    existente.
    """
    if responsavel is None or not case_id:
        return
    try:
        await verificar_acesso_caso(db, responsavel, case_id)
    except HTTPException as exc:
        if exc.status_code in (403, 404):
            raise HTTPException(
                status_code=422,
                detail="Responsável da solicitação sem acesso ao caso",
            ) from None
        raise


def _aplicar_status_solicitacao(
    atendimento: Atendimento,
    atendida: bool,
    user_id: str,
) -> None:
    if atendida and not _normalizar_texto(atendimento.solicitacao):
        raise HTTPException(
            status_code=422,
            detail="Informe o que foi solicitado antes de marcar como atendido",
        )
    atendimento.solicitacao_atendida = atendida
    atendimento.atendida_em = datetime.now(timezone.utc) if atendida else None
    atendimento.atendida_por_id = user_id if atendida else None
    atendimento.solicitacao_alerta_nivel = None if not atendida else "concluido"


def _titulo_tarefa(_solicitacao: str) -> str:
    # Tarefas sem caso podem ter alcance mais amplo que o CRM. O conteúdo do
    # pedido permanece somente na timeline do cliente, protegida pelo RBAC.
    return "Solicitação de cliente"


async def _obter_tarefa_vinculada(
    atendimento: Atendimento,
    db: AsyncSession,
) -> Optional[Task]:
    if not atendimento.task_id:
        return None
    return (
        await db.execute(
            select(Task).where(
                Task.id == atendimento.task_id,
                Task.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def _sincronizar_tarefa(
    atendimento: Atendimento,
    db: AsyncSession,
) -> None:
    tarefa = await _obter_tarefa_vinculada(atendimento, db)
    if tarefa is None:
        return
    responsavel = await _validar_responsavel(
        db, atendimento.solicitacao_responsavel_id
    )
    await _validar_responsavel_tarefa_no_caso(
        db, responsavel, atendimento.case_id
    )
    tarefa.titulo = _titulo_tarefa(atendimento.solicitacao or "Solicitação")
    tarefa.descricao = (
        "Tarefa originada na linha do tempo de atendimento. "
        "Consulte o dossiê do cliente para ver o pedido completo."
    )
    tarefa.prioridade = _TASK_PRIORIDADE.get(
        atendimento.solicitacao_prioridade or "normal",
        "media",
    )
    tarefa.data_limite = (
        atendimento.solicitacao_prazo.date()
        if atendimento.solicitacao_prazo
        else None
    )
    tarefa.case_id = atendimento.case_id
    tarefa.responsavel_id = atendimento.solicitacao_responsavel_id
    if atendimento.solicitacao_atendida:
        tarefa.status = TaskStatus.concluida
        tarefa.concluida_em = atendimento.atendida_em or datetime.now(timezone.utc)
    elif tarefa.status == TaskStatus.concluida:
        tarefa.status = TaskStatus.a_fazer
        tarefa.concluida_em = None


async def _notificar_nova_solicitacao(
    atendimento: Atendimento,
    responsavel: Optional[User],
    db: AsyncSession,
) -> None:
    if responsavel is None or atendimento.solicitacao_atendida:
        return
    try:
        await notificar(
            db,
            responsavel.id,
            "Solicitação de cliente atribuída",
            "Há uma solicitação pendente na linha do tempo de atendimento.",
            tipo="tarefa",
            link=f"/clientes/{atendimento.client_id}?tab=atendimentos",
            forcar_sino=True,
        )
    except Exception:
        await db.rollback()
        logger.exception(
            "Falha ao notificar responsável da solicitação %s",
            atendimento.id,
        )


# ── Endpoints base ─────────────────────────────────────────────────────────────

@router.get("")
async def listar_atendimentos(
    client_id: Optional[str] = Query(None),
    case_id: Optional[str] = Query(None),
    tipo: Optional[AtendimentoTipo] = Query(None),
    advogado_id: Optional[str] = Query(None),
    solicitacao_atendida: Optional[bool] = Query(None),
    solicitacao_prioridade: Optional[str] = Query(None),
    solicitacao_atrasada: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(status_code=403, detail="Sem permissão para atendimentos")
    if client_id:
        await _validar_cliente(db, client_id)

    q = select(Atendimento)
    # Sigilo interno (LGPD/EOAB): advogado/advogado_auxiliar só enxergam
    # atendimentos da própria carteira; gestão e recepção veem tudo.
    q = _filtro_visibilidade_atendimento(q, cu)
    if client_id:
        q = q.where(Atendimento.client_id == client_id)
    if case_id:
        q = q.where(Atendimento.case_id == case_id)
    if tipo:
        q = q.where(Atendimento.tipo == tipo)
    if advogado_id:
        q = q.where(Atendimento.advogado_responsavel_id == advogado_id)
    if solicitacao_atendida is not None:
        q = q.where(Atendimento.solicitacao_atendida == solicitacao_atendida)
    if solicitacao_prioridade:
        q = q.where(
            Atendimento.solicitacao_prioridade
            == _validar_prioridade(solicitacao_prioridade)
        )
    if solicitacao_atrasada is not None:
        condicao = (
            Atendimento.solicitacao.is_not(None)
            & Atendimento.solicitacao_atendida.is_(False)
            & Atendimento.solicitacao_prazo.is_not(None)
            & (Atendimento.solicitacao_prazo < datetime.now(timezone.utc))
        )
        q = q.where(condicao if solicitacao_atrasada else ~condicao)

    resumo_base = q.subquery()
    agora = datetime.now(timezone.utc)
    resumo = (
        await db.execute(
            select(
                func.count().filter(
                    resumo_base.c.solicitacao.is_not(None),
                    func.length(func.trim(resumo_base.c.solicitacao)) > 0,
                    resumo_base.c.solicitacao_atendida.is_(False),
                ).label("pendentes"),
                func.count().filter(
                    resumo_base.c.solicitacao.is_not(None),
                    func.length(func.trim(resumo_base.c.solicitacao)) > 0,
                    resumo_base.c.solicitacao_atendida.is_(False),
                    resumo_base.c.solicitacao_prazo.is_not(None),
                    resumo_base.c.solicitacao_prazo < agora,
                ).label("atrasadas"),
                func.count().filter(
                    resumo_base.c.solicitacao.is_not(None),
                    func.length(func.trim(resumo_base.c.solicitacao)) > 0,
                    resumo_base.c.solicitacao_atendida.is_(True),
                ).label("atendidas"),
            ).select_from(resumo_base)
        )
    ).one()

    q = q.order_by(Atendimento.data_atendimento.desc())
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    items = (
        await db.execute(q.offset((page - 1) * per_page).limit(per_page))
    ).scalars().all()
    privado = _pode_ver_privado(cu)
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "resumo_solicitacoes": {
            "pendentes": resumo.pendentes or 0,
            "atrasadas": resumo.atrasadas or 0,
            "atendidas": resumo.atendidas or 0,
        },
        "items": [_out(a, cu, com_privado=privado) for a in items],
    }


@router.post("", status_code=201)
async def criar_atendimento(
    req: AtendimentoIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(status_code=403, detail="Sem permissão para atendimentos")

    await _validar_cliente(db, req.client_id)
    if req.case_id:
        caso = await verificar_acesso_caso(db, cu, req.case_id)
        if caso.client_id != req.client_id:
            raise HTTPException(
                status_code=422,
                detail="O caso informado não pertence ao cliente",
            )

    data = req.model_dump(exclude={"solicitacao_atendida", "criar_tarefa"})
    data["solicitacao"] = _normalizar_texto(data.get("solicitacao"))
    data["solicitacao_prioridade"] = _validar_prioridade(
        data.get("solicitacao_prioridade", "normal")
    )
    data["contato_status"] = _validar_contato_status(
        data.get("contato_status", "confirmado")
    )
    data["data_atendimento"] = _utc(data["data_atendimento"])
    data["solicitacao_prazo"] = _utc(data.get("solicitacao_prazo"))

    if not data.get("advogado_responsavel_id"):
        data["advogado_responsavel_id"] = cu.id
    await _validar_responsavel(db, data["advogado_responsavel_id"])

    if not data["solicitacao"]:
        # Metadados de SLA sem uma solicitação gerariam pendências órfãs.
        data["solicitacao_prazo"] = None
        data["solicitacao_responsavel_id"] = None
        data["solicitacao_prioridade"] = "normal"
    elif not data.get("solicitacao_responsavel_id"):
        data["solicitacao_responsavel_id"] = data["advogado_responsavel_id"]
    responsavel_solicitacao = await _validar_responsavel(
        db,
        data.get("solicitacao_responsavel_id"),
    )

    if req.criar_tarefa and not data["solicitacao"]:
        raise HTTPException(
            status_code=422,
            detail="Informe a solicitação antes de criar uma tarefa",
        )

    atendimento = Atendimento(id=str(uuid4()), created_by=cu.id, **data)
    _aplicar_status_solicitacao(atendimento, req.solicitacao_atendida, cu.id)

    if req.criar_tarefa:
        await _validar_responsavel_tarefa_no_caso(
            db, responsavel_solicitacao, req.case_id
        )
        tarefa = Task(
            id=str(uuid4()),
            titulo=_titulo_tarefa(data["solicitacao"]),
            descricao=(
                "Tarefa originada na linha do tempo de atendimento. "
                "Consulte o dossiê do cliente para ver o pedido completo."
            ),
            status=(
                TaskStatus.concluida
                if req.solicitacao_atendida
                else TaskStatus.a_fazer
            ),
            prioridade=_TASK_PRIORIDADE[data["solicitacao_prioridade"]],
            data_limite=(
                data["solicitacao_prazo"].date()
                if data["solicitacao_prazo"]
                else None
            ),
            case_id=req.case_id,
            responsavel_id=data.get("solicitacao_responsavel_id"),
            criado_por=cu.id,
            concluida_em=atendimento.atendida_em,
        )
        db.add(tarefa)
        atendimento.task_id = tarefa.id

    db.add(atendimento)
    await db.commit()
    await db.refresh(atendimento)

    await _notificar_nova_solicitacao(
        atendimento,
        responsavel_solicitacao,
        db,
    )
    await registrar_acao(
        db,
        cu.id,
        "criar",
        "atendimentos",
        atendimento.id,
        f"Atendimento {atendimento.tipo} registrado para cliente {atendimento.client_id}",
        user_role=_role_str(cu),
        dados_depois={
            "tem_solicitacao": bool(atendimento.solicitacao),
            "tarefa_vinculada": bool(atendimento.task_id),
            "contato_status": atendimento.contato_status,
        },
    )
    return _out(atendimento, cu, com_privado=_pode_ver_privado(cu))


@router.get("/responsaveis")
async def listar_responsaveis(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(status_code=403, detail="Sem permissão para atendimentos")
    usuarios = (
        await db.execute(
            select(User)
            .where(
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
            .order_by(User.full_name)
        )
    ).scalars().all()
    return [
        {
            "id": usuario.id,
            "nome": usuario.full_name,
            "role": _role_str(usuario),
        }
        for usuario in usuarios
        if _role_str(usuario) in _ATENDIMENTO_ROLES
    ]


@router.get("/solicitacoes-resumo")
async def resumo_solicitacoes(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(status_code=403, detail="Sem permissão para atendimentos")

    agora = datetime.now(timezone.utc)
    inicio_local = datetime.now(ZoneInfo("America/Sao_Paulo")).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    fim_local = inicio_local + timedelta(days=1)
    inicio_utc = inicio_local.astimezone(timezone.utc)
    fim_utc = fim_local.astimezone(timezone.utc)

    tem_solicitacao = (
        Atendimento.solicitacao.is_not(None)
        & (func.length(func.trim(Atendimento.solicitacao)) > 0)
    )
    pendente = tem_solicitacao & Atendimento.solicitacao_atendida.is_(False)
    atrasada = (
        pendente
        & Atendimento.solicitacao_prazo.is_not(None)
        & (Atendimento.solicitacao_prazo < agora)
    )
    proxima = (
        pendente
        & Atendimento.solicitacao_prazo.is_not(None)
        & (Atendimento.solicitacao_prazo >= agora)
        & (Atendimento.solicitacao_prazo <= agora + timedelta(hours=24))
    )

    async def contar(condicao) -> int:
        return (
            await db.execute(
                select(func.count(Atendimento.id)).where(condicao)
            )
        ).scalar() or 0

    total_pendentes = await contar(pendente)
    total_atrasadas = await contar(atrasada)
    total_proximas = await contar(proxima)
    concluidas_hoje = await contar(
        Atendimento.solicitacao_atendida.is_(True)
        & (Atendimento.atendida_em >= inicio_utc)
        & (Atendimento.atendida_em < fim_utc)
    )

    destaque = (
        await db.execute(
            select(Atendimento)
            .where(pendente)
            .order_by(
                Atendimento.solicitacao_prazo.asc().nulls_last(),
                Atendimento.data_atendimento.asc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()

    destaque_out = None
    if destaque is not None:
        cliente = (
            await db.execute(
                select(Client).where(Client.id == destaque.client_id)
            )
        ).scalar_one_or_none()
        nome_cliente = None
        if cliente is not None:
            nome_cliente = (
                cliente.nome
                or cliente.razao_social
                or cliente.nome_fantasia
                or "Cliente"
            )
        destaque_out = {
            "atendimento_id": destaque.id,
            "client_id": destaque.client_id,
            "cliente_nome": nome_cliente or "Cliente",
            "prioridade": destaque.solicitacao_prioridade or "normal",
            "prazo": (
                destaque.solicitacao_prazo.isoformat()
                if destaque.solicitacao_prazo
                else None
            ),
            "atrasada": _solicitacao_atrasada(destaque),
        }

    return {
        "pendentes": total_pendentes,
        "atrasadas": total_atrasadas,
        "proximas_24h": total_proximas,
        "concluidas_hoje": concluidas_hoje,
        "destaque": destaque_out,
    }


@router.get("/meus")
async def meus_atendimentos(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Atendimentos em que o usuário autenticado é o responsável."""
    if not _is_staff(cu):
        raise HTTPException(status_code=403, detail="Sem permissão para atendimentos")
    q = (
        select(Atendimento)
        .where(Atendimento.advogado_responsavel_id == cu.id)
        .order_by(Atendimento.data_atendimento.desc())
    )
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    items = (
        await db.execute(q.offset((page - 1) * per_page).limit(per_page))
    ).scalars().all()
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [_out(a, cu, com_privado=_pode_ver_privado(cu)) for a in items],
    }


@router.get("/por-advogado/{advogado_id}")
async def por_advogado(
    advogado_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Lista atendimentos de um responsável específico."""
    if not _is_staff(cu):
        raise HTTPException(status_code=403, detail="Sem permissão para atendimentos")
    nivel = ROLE_LEVEL.get(_role_str(cu), 0)
    if advogado_id != cu.id and nivel < ROLE_LEVEL["socio"]:
        raise HTTPException(
            status_code=403,
            detail="Somente a gestão pode ver atendimentos de outros responsáveis",
        )

    q = (
        select(Atendimento)
        .where(Atendimento.advogado_responsavel_id == advogado_id)
        .order_by(Atendimento.data_atendimento.desc())
    )
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    items = (
        await db.execute(q.offset((page - 1) * per_page).limit(per_page))
    ).scalars().all()
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [_out(a, cu, com_privado=_pode_ver_privado(cu)) for a in items],
    }


@router.get("/dashboard")
async def dashboard_atendimentos(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Estatísticas agregadas por responsável."""
    if not _is_staff(cu):
        raise HTTPException(status_code=403, detail="Sem permissão para atendimentos")

    nivel = ROLE_LEVEL.get(_role_str(cu), 0)
    q_base = select(
        Atendimento.advogado_responsavel_id,
        func.count(Atendimento.id).label("total"),
        func.coalesce(func.sum(Atendimento.duracao_horas), 0).label("total_horas"),
        func.coalesce(func.avg(Atendimento.satisfacao_cliente), 0).label("satisfacao_media"),
    ).group_by(Atendimento.advogado_responsavel_id)

    if nivel < ROLE_LEVEL["socio"]:
        q_base = q_base.where(Atendimento.advogado_responsavel_id == cu.id)

    rows = (await db.execute(q_base)).all()
    return [
        {
            "advogado_id": r.advogado_responsavel_id,
            "total_atendimentos": r.total,
            "total_horas": round(float(r.total_horas), 2),
            "satisfacao_media": round(float(r.satisfacao_media), 2),
        }
        for r in rows
    ]


@router.get("/stats")
async def stats_mensais(
    ano: int = Query(default=2026),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Breakdown mensal de atendimentos — quantidade e horas por mês."""
    if not _is_staff(cu):
        raise HTTPException(status_code=403, detail="Sem permissão para atendimentos")

    from sqlalchemy import extract

    nivel = ROLE_LEVEL.get(_role_str(cu), 0)
    q = (
        select(
            extract("month", Atendimento.data_atendimento).label("mes"),
            func.count(Atendimento.id).label("total"),
            func.coalesce(func.sum(Atendimento.duracao_horas), 0).label("total_horas"),
            func.coalesce(func.avg(Atendimento.satisfacao_cliente), 0).label("satisfacao_media"),
        )
        .where(extract("year", Atendimento.data_atendimento) == ano)
        .group_by(extract("month", Atendimento.data_atendimento))
        .order_by(extract("month", Atendimento.data_atendimento))
    )

    if nivel < ROLE_LEVEL["socio"]:
        q = q.where(Atendimento.advogado_responsavel_id == cu.id)

    rows = (await db.execute(q)).all()
    meses = [
        "Jan",
        "Fev",
        "Mar",
        "Abr",
        "Mai",
        "Jun",
        "Jul",
        "Ago",
        "Set",
        "Out",
        "Nov",
        "Dez",
    ]
    return [
        {
            "mes": int(r.mes),
            "mes_nome": meses[int(r.mes) - 1],
            "total": r.total,
            "total_horas": round(float(r.total_horas), 2),
            "satisfacao_media": round(float(r.satisfacao_media), 2),
        }
        for r in rows
    ]


# ── Endpoints individuais ──────────────────────────────────────────────────────

@router.get("/{atendimento_id}/historico")
async def historico_atendimento(
    atendimento_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(status_code=403, detail="Sem permissão para atendimentos")
    atendimento = await _obter_atendimento(atendimento_id, db)
    if not await _pode_ver_atendimento(db, cu, atendimento):
        # 404 (não 403) para não confirmar existência de registro de outra carteira.
        raise HTTPException(status_code=404, detail="Atendimento não encontrado")

    rows = (
        await db.execute(
            select(AuditLog, User.full_name)
            .outerjoin(User, User.id == AuditLog.user_id)
            .where(
                AuditLog.entidade == "atendimentos",
                AuditLog.registro_id == atendimento_id,
            )
            .order_by(AuditLog.created_at.asc())
        )
    ).all()
    return [
        {
            "id": log.id,
            "acao": log.acao,
            "detalhes": log.detalhes,
            "usuario_id": log.user_id,
            "usuario_nome": nome or "Sistema",
            "usuario_role": log.user_role,
            "data": log.created_at.isoformat() if log.created_at else None,
        }
        for log, nome in rows
    ]


@router.get("/{atendimento_id}")
async def obter_atendimento(
    atendimento_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(status_code=403, detail="Sem permissão para atendimentos")
    atendimento = await _obter_atendimento(atendimento_id, db)
    if not await _pode_ver_atendimento(db, cu, atendimento):
        # 404 (não 403) para não confirmar existência de registro de outra carteira.
        raise HTTPException(status_code=404, detail="Atendimento não encontrado")
    return _out(atendimento, cu, com_privado=_pode_ver_privado(cu))


@router.patch("/{atendimento_id}")
async def atualizar_atendimento(
    atendimento_id: str,
    req: AtendimentoPatch,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(status_code=403, detail="Sem permissão para atendimentos")
    atendimento = await _obter_atendimento(atendimento_id, db)
    if not _pode_editar_atendimento(atendimento, cu):
        raise HTTPException(status_code=403, detail="Sem permissão para editar este atendimento")

    data = req.model_dump(exclude_unset=True)
    for obrigatorio in ("tipo", "data_atendimento", "resumo"):
        if obrigatorio in data and data[obrigatorio] is None:
            raise HTTPException(status_code=422, detail=f"{obrigatorio} não pode ser nulo")

    responsavel_anterior = atendimento.solicitacao_responsavel_id
    status_solicitacao = data.pop("solicitacao_atendida", None)

    if "advogado_responsavel_id" in data:
        await _validar_responsavel(db, data["advogado_responsavel_id"])
    if "solicitacao_responsavel_id" in data:
        await _validar_responsavel(db, data["solicitacao_responsavel_id"])
    if "solicitacao_prioridade" in data:
        if data["solicitacao_prioridade"] is None:
            raise HTTPException(status_code=422, detail="Prioridade não pode ser nula")
        data["solicitacao_prioridade"] = _validar_prioridade(
            data["solicitacao_prioridade"]
        )
    if "contato_status" in data:
        if data["contato_status"] is None:
            raise HTTPException(status_code=422, detail="Status do contato não pode ser nulo")
        data["contato_status"] = _validar_contato_status(data["contato_status"])
    if "solicitacao" in data:
        data["solicitacao"] = _normalizar_texto(data["solicitacao"])
        if data["solicitacao"] is None and atendimento.task_id:
            raise HTTPException(
                status_code=422,
                detail="A solicitação vinculada a uma tarefa não pode ser removida",
            )
    if "data_atendimento" in data:
        data["data_atendimento"] = _utc(data["data_atendimento"])
    if "solicitacao_prazo" in data:
        data["solicitacao_prazo"] = _utc(data["solicitacao_prazo"])

    if {
        "solicitacao",
        "solicitacao_prazo",
        "solicitacao_prioridade",
        "solicitacao_responsavel_id",
    }.intersection(data):
        atendimento.solicitacao_alerta_nivel = None

    for campo, valor in data.items():
        setattr(atendimento, campo, valor)

    if "solicitacao" in data and data["solicitacao"] is None:
        atendimento.solicitacao_prazo = None
        atendimento.solicitacao_prioridade = "normal"
        atendimento.solicitacao_responsavel_id = None
        atendimento.solicitacao_alerta_nivel = None

    if status_solicitacao is not None:
        _aplicar_status_solicitacao(atendimento, status_solicitacao, cu.id)
    elif not _normalizar_texto(atendimento.solicitacao):
        _aplicar_status_solicitacao(atendimento, False, cu.id)

    await _sincronizar_tarefa(atendimento, db)
    atendimento.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(atendimento)

    novo_responsavel = None
    if (
        atendimento.solicitacao_responsavel_id
        and atendimento.solicitacao_responsavel_id != responsavel_anterior
    ):
        novo_responsavel = await _validar_responsavel(
            db,
            atendimento.solicitacao_responsavel_id,
        )
    await _notificar_nova_solicitacao(atendimento, novo_responsavel, db)

    await registrar_acao(
        db,
        cu.id,
        "atualizar",
        "atendimentos",
        atendimento.id,
        "Atendimento atualizado; campos: " + ", ".join(sorted(req.model_fields_set)),
        user_role=_role_str(cu),
        dados_depois={
            "campos": sorted(req.model_fields_set),
            "solicitacao_atendida": bool(atendimento.solicitacao_atendida),
            "contato_status": atendimento.contato_status,
        },
    )
    return _out(atendimento, cu, com_privado=_pode_ver_privado(cu))


@router.delete("/{atendimento_id}", status_code=204)
async def remover_atendimento(
    atendimento_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu) or ROLE_LEVEL.get(_role_str(cu), 0) < ROLE_LEVEL["advogado"]:
        raise HTTPException(status_code=403, detail="Sem permissão para excluir atendimentos")
    atendimento = await _obter_atendimento(atendimento_id, db)
    if not _pode_editar_atendimento(atendimento, cu):
        raise HTTPException(status_code=403, detail="Sem permissão para excluir este atendimento")

    tarefa = await _obter_tarefa_vinculada(atendimento, db)
    if tarefa is not None:
        tarefa.deleted_at = datetime.now(timezone.utc)

    atendimento_id_audit = atendimento.id
    cliente_id_audit = atendimento.client_id
    await db.delete(atendimento)
    await db.commit()
    await registrar_acao(
        db,
        cu.id,
        "excluir",
        "atendimentos",
        atendimento_id_audit,
        f"Atendimento removido do cliente {cliente_id_audit}",
        user_role=_role_str(cu),
        dados_antes={"tarefa_vinculada": bool(tarefa)},
    )
