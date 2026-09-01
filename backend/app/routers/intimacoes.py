# ── app/routers/intimacoes.py ────────────────────────────────────────────────
# Intimações capturadas do DJEN — tratamento humano obrigatório.
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional
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
from app.models.user import User, UserRole
from app.services.djen_service import capturar_para_advogado, enviar_emails_pendentes

router = APIRouter(prefix="/intimacoes", tags=["Intimações DJEN"])

PRAZO_DJEN_MOTIVO_BLOQUEIO = "revisao_humana_obrigatoria_por_marcos_e_regime"
_REGIMES = {"civel", "trabalhista", "penal"}
_ROLES_RESPONSAVEIS = {
    UserRole.superadmin,
    UserRole.admin,
    UserRole.socio,
    UserRole.advogado,
    UserRole.advogado_auxiliar,
    UserRole.estagiario,
    UserRole.secretaria,
}


def _calcular_sugestao(c: DjenComunicacao) -> dict:
    """Expõe os quatro marcos sem fabricar publicação, início ou vencimento."""
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
        "data_publicacao": c.data_publicacao,
        "termo_inicial": c.termo_inicial,
        "regime_calculo": c.regime_calculo,
        "fundamentacao": None,
        "casou": False,
        "revisao_necessaria": True,
        "motivo": PRAZO_DJEN_MOTIVO_BLOQUEIO,
        "aviso": (
            "Informe e confira na fonte oficial: publicação, termo inicial, "
            "regime processual e vencimento. A disponibilização capturada é "
            "mantida apenas como fato da fonte e nunca é usada como termo inicial."
        ),
    }


async def _carregar_comunicacao(
    com_id: str, db: AsyncSession, cu: User
) -> DjenComunicacao:
    c = (
        await db.execute(select(DjenComunicacao).where(DjenComunicacao.id == com_id))
    ).scalar_one_or_none()
    if not c or (not is_gestao(cu) and c.advogado_id != cu.id):
        raise HTTPException(status_code=404, detail="Comunicação não encontrada")
    return c


class AceitarPrazoRequest(BaseModel):
    # `dias` é legado; DJEN não calcula automaticamente enquanto o ato não
    # trouxer base determinística suficiente. O vencimento é revisão humana.
    dias: Optional[int] = None
    data_prazo: Optional[date] = None
    data_publicacao: Optional[date] = None
    termo_inicial: Optional[date] = None
    regime_calculo: Optional[Literal["civel", "trabalhista", "penal"]] = None
    confirmacao_fonte_oficial: bool = False
    titulo: Optional[str] = None
    responsavel_id: Optional[str] = None
    prioridade: Optional[str] = None


def _validar_revisao_prazo(
    comunicacao: DjenComunicacao, payload: AceitarPrazoRequest
) -> None:
    faltantes = []
    if payload.data_publicacao is None:
        faltantes.append("data_publicacao")
    if payload.termo_inicial is None:
        faltantes.append("termo_inicial")
    if payload.regime_calculo is None:
        faltantes.append("regime_calculo")
    if payload.data_prazo is None:
        faltantes.append("data_prazo")
    if faltantes:
        raise HTTPException(
            status_code=422,
            detail=(
                "Revisão do prazo incompleta: informe " + ", ".join(faltantes) + "."
            ),
        )
    if not payload.confirmacao_fonte_oficial:
        raise HTTPException(
            status_code=422,
            detail=(
                "Confirme a conferência da comunicação/publicação oficial, "
                "termo inicial, regime e calendário antes de cadastrar o prazo."
            ),
        )
    if payload.regime_calculo not in _REGIMES:
        raise HTTPException(status_code=422, detail="Regime processual inválido")

    disponibilizacao = comunicacao.data_disponibilizacao
    if isinstance(disponibilizacao, datetime):
        disponibilizacao = disponibilizacao.date()
    assert payload.data_publicacao is not None
    assert payload.termo_inicial is not None
    assert payload.data_prazo is not None
    if disponibilizacao and payload.data_publicacao < disponibilizacao:
        raise HTTPException(
            status_code=422,
            detail="Data de publicação não pode anteceder a disponibilização capturada.",
        )
    if payload.termo_inicial < payload.data_publicacao:
        raise HTTPException(
            status_code=422,
            detail="Termo inicial não pode anteceder a publicação informada.",
        )
    if payload.data_prazo < payload.termo_inicial:
        raise HTTPException(
            status_code=422,
            detail="Vencimento não pode anteceder o termo inicial informado.",
        )


async def _validar_responsavel(
    db: AsyncSession,
    cu: User,
    case,
    responsavel_id: str,
) -> None:
    alvo = (
        await db.execute(
            select(User).where(
                User.id == responsavel_id,
                User.deleted_at.is_(None),
                User.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not alvo or alvo.role not in _ROLES_RESPONSAVEIS:
        raise HTTPException(
            status_code=422,
            detail="Responsável do prazo inválido ou inativo.",
        )
    if is_gestao(cu) or alvo.id == cu.id:
        return
    if alvo.id not in (case.advogado_responsavel_id, case.advogado_auxiliar_id):
        raise HTTPException(
            status_code=403,
            detail="Responsável informado não pertence à equipe jurídica do caso.",
        )


@router.get("/")
async def listar(
    apenas_pendentes: bool = True,
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
    q = q.order_by(DjenComunicacao.data_disponibilizacao.desc())
    total = (
        await db.execute(select(sqlfunc.count()).select_from(q.subquery()))
    ).scalar()
    rows = (
        await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()
    return {
        "data": [
            {
                "id": c.id,
                "numero_processo": c.numero_processo,
                "tribunal": c.tribunal,
                "tipo": c.tipo_comunicacao,
                "data": c.data_disponibilizacao,
                "data_publicacao": c.data_publicacao,
                "termo_inicial": c.termo_inicial,
                "regime_calculo": c.regime_calculo,
                "texto": (c.texto_resumo or "")[:500],
                "case_id": c.case_id,
                "processada": c.processada,
                "prazo_sugerido_status": c.prazo_sugerido_status or "nenhum",
                "prazo_deadline_id": c.prazo_deadline_id,
            }
            for c in rows
        ],
        "total": total,
    }


@router.get("/status-captura")
async def status_captura(
    db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)
):
    from sqlalchemy import text as _t
    from app.models.scheduler_heartbeat import SchedulerHeartbeat
    from app.services import heartbeat_service as hb

    heartbeat = (
        await db.execute(
            select(SchedulerHeartbeat).where(
                SchedulerHeartbeat.job_name == hb.JOB_DJEN
            )
        )
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
                _t(
                    "SELECT count(*) FROM djen_comunicacoes "
                    "WHERE created_at >= :inicio"
                ),
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
                f"{idade:.0f}h (limite {config['max_age_horas']}h). Verifique o scheduler."
            )
        return {
            "executado_em": ultima_execucao,
            "sucesso": sucesso,
            "intimacoes_encontradas": encontradas,
            "erro": erro,
            "defasado": defasado,
            "ultima_execucao": ultima_execucao,
        }

    ultimo = (
        await db.execute(_t("SELECT max(created_at) FROM djen_comunicacoes"))
    ).scalar()
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
            _t(
                "SELECT count(*) FROM djen_comunicacoes "
                "WHERE created_at >= :inicio"
            ),
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
        dados_depois={"processada": True, "decisao_prazo": decisao_prazo},
    )
    await db.commit()
    return {"detail": "Intimação marcada como tratada"}


@router.post("/{com_id}/sugerir-prazo")
async def sugerir_prazo(
    com_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    return _calcular_sugestao(await _carregar_comunicacao(com_id, db, cu))


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
            detail="Intimação não vinculada a um caso — vincule o caso antes do prazo.",
        )
    caso = await verificar_acesso_caso(db, cu, comunicacao.case_id)

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

    if payload.dias is not None:
        raise HTTPException(
            status_code=422,
            detail=(
                "DJEN não calcula vencimento apenas por quantidade de dias. "
                "Use o motor processual canônico para conferência e informe os "
                "quatro marcos revisados nesta comunicação."
            ),
        )
    _validar_revisao_prazo(comunicacao, payload)

    responsavel_id = payload.responsavel_id or comunicacao.advogado_id or cu.id
    await _validar_responsavel(db, cu, caso, responsavel_id)
    agora = datetime.now(timezone.utc)
    assert payload.data_prazo is not None
    assert payload.data_publicacao is not None
    assert payload.termo_inicial is not None
    assert payload.regime_calculo is not None

    metadata = {
        "fonte": "djen",
        "modo": "vencimento_manual_revisado",
        "regime_calculo": payload.regime_calculo,
        "tribunal": comunicacao.tribunal,
        "data_disponibilizacao": (
            comunicacao.data_disponibilizacao.isoformat()
            if comunicacao.data_disponibilizacao
            else None
        ),
        "data_publicacao": payload.data_publicacao.isoformat(),
        "termo_inicial": payload.termo_inicial.isoformat(),
        "data_prazo": payload.data_prazo.isoformat(),
        "resultado_preliminar": False,
        "revisao_humana": True,
    }
    titulo = payload.titulo or (
        f"Prazo DJEN — proc. {comunicacao.numero_processo or 's/ número'}"
    )[:255]
    prazo = Deadline(
        id=str(uuid4()),
        titulo=titulo,
        tipo="processual",
        prioridade=payload.prioridade or "alta",
        descricao=(
            "Prazo DJEN cadastrado após revisão humana dos marcos processuais. "
            "A disponibilização capturada não foi usada como termo inicial."
        ),
        data_prazo=payload.data_prazo,
        data_intimacao=None,
        data_publicacao=payload.data_publicacao,
        termo_inicial=payload.termo_inicial,
        regime_calculo=payload.regime_calculo,
        calculo_metadata=metadata,
        calculado_por=cu.id,
        conferido_por=cu.id,
        conferido_em=agora,
        base_legal="Vencimento informado após revisão humana da fonte oficial",
        case_id=comunicacao.case_id,
        responsavel_id=responsavel_id,
        origem="djen",
        confirmado=True,
    )
    db.add(prazo)

    comunicacao.data_publicacao = payload.data_publicacao
    comunicacao.termo_inicial = payload.termo_inicial
    comunicacao.regime_calculo = payload.regime_calculo
    comunicacao.calculo_metadata = metadata
    comunicacao.prazo_revisado_por = cu.id
    comunicacao.prazo_revisado_em = agora
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
            "regime_calculo": payload.regime_calculo,
            "data_publicacao": payload.data_publicacao.isoformat(),
            "termo_inicial": payload.termo_inicial.isoformat(),
            "data_prazo": payload.data_prazo.isoformat(),
        },
    )
    await db.commit()
    await db.refresh(prazo)
    return {
        "detail": "Prazo revisado e cadastrado com trilha dos marcos processuais",
        "criado": True,
        "deadline_id": prazo.id,
        "data_prazo": prazo.data_prazo,
        "data_publicacao": prazo.data_publicacao,
        "termo_inicial": prazo.termo_inicial,
        "regime_calculo": prazo.regime_calculo,
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
                "antes de alterar a decisão."
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
    db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)
):
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
            detail=(
                "Captura DJEN indisponível no momento "
                f"(código: {resultado.erro or 'erro_interno'})."
            ),
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
