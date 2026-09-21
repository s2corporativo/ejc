# ── app/routers/intimacoes.py ────────────────────────────────────────────────
# Intimações capturadas do DJEN — tratamento humano obrigatório.
# O job do scheduler captura; aqui o advogado revisa e decide.
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func as sqlfunc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import is_gestao, verificar_acesso_caso
from app.core.security import get_current_user
from app.models.deadline import Deadline
from app.models.djen import DjenComunicacao
from app.models.user import User
from app.services.djen_service import (
    capturar_para_advogado,
    enviar_emails_pendentes,
)

router = APIRouter(prefix="/intimacoes", tags=["Intimações DJEN"])

PRAZO_DJEN_MOTIVO_BLOQUEIO = "calculo_automatico_bloqueado_ate_motor_auditavel_por_regime"


def _calcular_sugestao(c: DjenComunicacao) -> dict:
    """Expõe a pendência de revisão sem fabricar termo inicial ou vencimento.

    A comunicação capturada ainda não possui, no schema atual, os marcos
    separados de publicação e termo inicial nem o regime processual auditável.
    A data de disponibilização é preservada somente como fato da fonte e nunca
    é reutilizada como ``data_base`` de cálculo.
    """
    disponibilizacao = c.data_disponibilizacao
    if isinstance(disponibilizacao, datetime):
        disponibilizacao = disponibilizacao.date()

    return {
        "disponivel": False,
        "com_id": c.id,
        "numero_processo": c.numero_processo,
        "case_id": c.case_id,
        "tipo_detectado": "revisão necessária",
        "dias": None,
        "data_base": None,
        "data_sugerida": None,
        "data_disponibilizacao": disponibilizacao,
        "fundamentacao": None,
        "casou": False,
        "revisao_necessaria": True,
        "motivo": PRAZO_DJEN_MOTIVO_BLOQUEIO,
        "aviso": (
            "Cálculo automático temporariamente bloqueado: disponibilização, "
            "publicação, termo inicial e regime processual precisam ser "
            "conferidos na comunicação oficial. Informe o vencimento final "
            "manualmente somente após essa conferência."
        ),
    }


async def _carregar_comunicacao(
    com_id: str,
    db: AsyncSession,
    cu: User,
) -> DjenComunicacao:
    c = (await db.execute(select(DjenComunicacao).where(DjenComunicacao.id == com_id))).scalar_one_or_none()
    if not c or (not is_gestao(cu) and c.advogado_id != cu.id):
        raise HTTPException(status_code=404, detail="Comunicação não encontrada")
    return c


class AceitarPrazoRequest(BaseModel):
    # ``dias`` é preservado apenas por compatibilidade de contrato; sem termo
    # inicial/regime auditáveis o backend rejeita seu uso para cálculo.
    dias: Optional[int] = None
    data_prazo: Optional[date] = None
    titulo: Optional[str] = None
    responsavel_id: Optional[str] = None
    prioridade: Optional[str] = None


@router.get("/")
async def listar(
    apenas_pendentes: bool = True,
    case_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(DjenComunicacao)
    if not is_gestao(cu):
        q = q.where(DjenComunicacao.advogado_id == cu.id)
    if apenas_pendentes:
        q = q.where(DjenComunicacao.processada == False)  # noqa: E712
    # Onda 4 (§10): contexto de caso no workspace — a aba "Intimações" do
    # CasoDetalhe lista as comunicações DJEN vinculadas ao caso (aditivo;
    # sem case_id o comportamento é exatamente o anterior).
    if case_id:
        q = q.where(DjenComunicacao.case_id == case_id)
    q = q.order_by(DjenComunicacao.data_disponibilizacao.desc())

    total = (await db.execute(select(sqlfunc.count()).select_from(q.subquery()))).scalar()
    rows = (await db.execute(q.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {
        "data": [
            {
                "id": comunicacao.id,
                "numero_processo": comunicacao.numero_processo,
                "tribunal": comunicacao.tribunal,
                "tipo": comunicacao.tipo_comunicacao,
                "data": comunicacao.data_disponibilizacao,
                "texto": (comunicacao.texto_resumo or "")[:500],
                "case_id": comunicacao.case_id,
                "processada": comunicacao.processada,
                "prazo_sugerido_status": (comunicacao.prazo_sugerido_status or "nenhum"),
                "prazo_deadline_id": comunicacao.prazo_deadline_id,
            }
            for comunicacao in rows
        ],
        "total": total,
    }


@router.get("/status-captura")
async def status_captura(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Estado da última execução real do job DJEN."""
    from sqlalchemy import text as _t

    from app.models.scheduler_heartbeat import SchedulerHeartbeat
    from app.services import heartbeat_service as hb

    heartbeat = (
        await db.execute(select(SchedulerHeartbeat).where(SchedulerHeartbeat.job_name == hb.JOB_DJEN))
    ).scalar_one_or_none()

    if heartbeat is not None:
        config = hb.JOBS_MONITORADOS[hb.JOB_DJEN]
        avaliacao = hb.avaliar_job(
            heartbeat.last_run_at,
            heartbeat.last_status,
            max_age_horas=config["max_age_horas"],
        )
        ultima_execucao = heartbeat.last_run_at
        defasado = avaliacao["status"] in ("defasado", "nunca_executou")
        falhou = avaliacao["status"] == "erro"
        sucesso = avaliacao["status"] == "ok"
        encontradas = (
            await db.execute(
                _t("SELECT count(*) FROM djen_comunicacoes WHERE created_at >= :inicio"),
                {"inicio": ultima_execucao - timedelta(minutes=5)},
            )
        ).scalar() or 0
        erro = None
        if falhou:
            erro = (heartbeat.detail or "Última execução do job DJEN falhou.")[:300]
        elif defasado:
            idade = avaliacao["idade_horas"] or 0
            erro = (
                "Captura possivelmente parada: última execução do job DJEN há "
                f"{idade:.0f}h (limite {config['max_age_horas']}h). Verifique o "
                "scheduler."
            )
        return {
            "executado_em": ultima_execucao,
            "sucesso": sucesso,
            "intimacoes_encontradas": encontradas,
            "erro": erro,
            "defasado": defasado,
            "ultima_execucao": ultima_execucao,
        }

    ultimo = (await db.execute(_t("SELECT max(created_at) FROM djen_comunicacoes"))).scalar()
    if ultimo is None:
        return {
            "executado_em": None,
            "sucesso": False,
            "intimacoes_encontradas": 0,
            "erro": "Nenhuma captura de intimações registrada até o momento.",
            "defasado": False,
            "ultima_execucao": None,
        }
    encontradas = (
        await db.execute(
            _t("SELECT count(*) FROM djen_comunicacoes WHERE created_at >= :inicio"),
            {"inicio": ultimo - timedelta(minutes=5)},
        )
    ).scalar() or 0
    return {
        "executado_em": ultimo,
        "sucesso": True,
        "intimacoes_encontradas": encontradas,
        "erro": None,
        "defasado": False,
        "ultima_execucao": None,
    }


@router.post("/{com_id}/processar")
async def processar(
    com_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    from app.models.audit_log import criar_audit_log

    comunicacao = await _carregar_comunicacao(com_id, db, cu)
    if comunicacao.case_id:
        await verificar_acesso_caso(db, cu, comunicacao.case_id)

    decisao_prazo = comunicacao.prazo_sugerido_status or "nenhum"
    if decisao_prazo not in {"aceito", "recusado"}:
        raise HTTPException(
            status_code=422,
            detail=(
                "Revise a necessidade de prazo antes de marcar a intimação como "
                "tratada: aceite um vencimento conferido ou registre a recusa."
            ),
        )

    if comunicacao.processada:
        return {"detail": "Intimação já estava marcada como tratada"}

    comunicacao.processada = True
    comunicacao.processada_por = cu.id
    comunicacao.processada_em = datetime.now(timezone.utc)
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "UPDATE",
        "djen_comunicacoes",
        comunicacao.id,
        dados_depois={
            "processada": True,
            "decisao_prazo": decisao_prazo,
        },
    )
    await db.commit()
    return {"detail": "Intimação marcada como tratada"}


@router.post("/{com_id}/sugerir-prazo")
async def sugerir_prazo(
    com_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    comunicacao = await _carregar_comunicacao(com_id, db, cu)
    return _calcular_sugestao(comunicacao)


@router.get("/{com_id}/prazo-sugerido")
async def prazo_sugerido(
    com_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    comunicacao = await _carregar_comunicacao(com_id, db, cu)
    sugestao = _calcular_sugestao(comunicacao)
    sugestao["prazo_sugerido_status"] = comunicacao.prazo_sugerido_status or "nenhum"
    sugestao["prazo_deadline_id"] = comunicacao.prazo_deadline_id
    return sugestao


@router.post("/{com_id}/aceitar-prazo")
async def aceitar_prazo(
    com_id: str,
    payload: Optional[AceitarPrazoRequest] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    from app.models.audit_log import criar_audit_log

    payload = payload or AceitarPrazoRequest()
    comunicacao = await _carregar_comunicacao(com_id, db, cu)

    if not comunicacao.case_id:
        raise HTTPException(
            status_code=422,
            detail=("Intimação não vinculada a um caso — vincule um caso antes de gerar o prazo."),
        )

    await verificar_acesso_caso(db, cu, comunicacao.case_id)

    if comunicacao.prazo_sugerido_status == "aceito" and comunicacao.prazo_deadline_id:
        existente = (
            await db.execute(
                select(Deadline).where(
                    Deadline.id == comunicacao.prazo_deadline_id,
                    Deadline.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existente is not None:
            return {
                "detail": "Prazo já havia sido aceito para esta intimação",
                "criado": False,
                "deadline_id": existente.id,
                "data_prazo": existente.data_prazo,
            }

    sugestao = _calcular_sugestao(comunicacao)

    if payload.data_prazo is None:
        if payload.dias is not None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Cálculo por quantidade de dias está bloqueado até a "
                    "implantação do motor auditável por regime e termo inicial. "
                    "Informe data_prazo após conferência da publicação oficial."
                ),
            )
        raise HTTPException(
            status_code=422,
            detail=(
                "Não há vencimento automático disponível. Informe data_prazo "
                "após conferir publicação, termo inicial, regime e calendário."
            ),
        )

    data_prazo = payload.data_prazo
    base_legal = "Vencimento informado manualmente após revisão humana"
    titulo = payload.titulo or (f"Prazo DJEN — proc. {comunicacao.numero_processo or 's/ número'}")[:255]

    disponibilizacao = comunicacao.data_disponibilizacao
    if isinstance(disponibilizacao, datetime):
        disponibilizacao = disponibilizacao.date()
    metadado_disponibilizacao = (
        f" Disponibilização capturada: {disponibilizacao.isoformat()}."
        if disponibilizacao
        else " Disponibilização não disponível/validada na fonte capturada."
    )

    prazo = Deadline(
        id=str(uuid4()),
        titulo=titulo,
        tipo="processual",
        prioridade=payload.prioridade or "alta",
        descricao=(
            "Prazo vinculado a intimação DJEN após informação manual do "
            f"vencimento pelo usuário.{metadado_disponibilizacao} "
            f"{sugestao['aviso']}"
        ).strip(),
        data_prazo=data_prazo,
        # Disponibilização não é tratada como intimação/termo inicial.
        data_intimacao=None,
        base_legal=base_legal,
        case_id=comunicacao.case_id,
        responsavel_id=(payload.responsavel_id or comunicacao.advogado_id or cu.id),
        origem="djen",
    )
    db.add(prazo)

    comunicacao.prazo_sugerido_status = "aceito"
    comunicacao.prazo_deadline_id = prazo.id

    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "CREATE",
        "deadlines",
        prazo.id,
        dados_depois={
            "origem": "djen",
            "com_id": comunicacao.id,
            "modo": "vencimento_manual_revisado",
        },
    )
    await db.commit()
    await db.refresh(prazo)
    return {
        "detail": "Prazo manual conferido e cadastrado",
        "criado": True,
        "deadline_id": prazo.id,
        "data_prazo": prazo.data_prazo,
        "titulo": prazo.titulo,
        "base_legal": prazo.base_legal,
    }


@router.post("/{com_id}/recusar-prazo")
async def recusar_prazo(
    com_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    from app.models.audit_log import criar_audit_log

    comunicacao = await _carregar_comunicacao(com_id, db, cu)
    if comunicacao.case_id:
        await verificar_acesso_caso(db, cu, comunicacao.case_id)

    if comunicacao.prazo_sugerido_status == "aceito" and comunicacao.prazo_deadline_id:
        raise HTTPException(
            status_code=409,
            detail=(
                "Esta intimação já possui prazo aceito. Revise o prazo cadastrado "
                "antes de alterar a decisão sobre a comunicação."
            ),
        )

    comunicacao.prazo_sugerido_status = "recusado"
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "UPDATE",
        "djen_comunicacoes",
        comunicacao.id,
        dados_depois={"prazo_sugerido_status": "recusado"},
    )
    await db.commit()
    return {
        "detail": "Prazo recusado — nenhum prazo será gerado para esta intimação",
        "prazo_sugerido_status": comunicacao.prazo_sugerido_status,
    }


@router.post("/capturar-agora")
async def capturar_agora(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Captura manual sem contaminar o heartbeat do job agendado."""
    if not (cu.djen_oab_numero or "").strip() or not (cu.djen_oab_uf or "").strip():
        raise HTTPException(
            status_code=422,
            detail="Configure sua OAB (número e UF) no seu perfil de usuário",
        )

    resultado = await capturar_para_advogado(db, cu)
    if not resultado.fonte_ok:
        await db.rollback()
        raise HTTPException(
            status_code=503,
            detail=(f"Captura DJEN indisponível no momento (código: {resultado.erro or 'erro_interno'})."),
        )

    await db.commit()
    await enviar_emails_pendentes(resultado)
    return {
        "novas": resultado.novas,
        "recebidas": resultado.recebidas,
        "duplicadas": resultado.duplicadas,
        "ignoradas": resultado.ignoradas,
        "paginas": resultado.paginas,
        "janela_dias": resultado.janela_dias,
        "detail": f"{resultado.novas} intimação(ões) nova(s)",
    }
