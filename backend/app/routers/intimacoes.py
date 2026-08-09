# ── app/routers/intimacoes.py ────────────────────────────────────────────────
# Intimações capturadas do DJEN — tratamento humano obrigatório.
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func as sqlfunc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import is_gestao, verificar_acesso_caso
from app.core.security import get_current_user
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.deadline import Deadline
from app.models.djen import DjenComunicacao
from app.models.user import User
from app.services.deadline_calculator import (
    calcular_prazo_djen,
    data_publicacao_djen,
    regime_processual_por_area,
    termo_inicial_djen,
)
from app.services.djen_service import capturar_para_advogado, enviar_emails_pendentes

router = APIRouter(prefix="/intimacoes", tags=["Intimações DJEN"])
Regime = Literal["civel", "trabalhista", "penal"]

# Heurística SUBSTANTIVA somente para regime cível. Não usar para trabalhista,
# penal ou rito especial: o mesmo termo (ex.: "recurso") pode ter prazo diverso.
_HEURISTICAS_CIVEIS: list[tuple[tuple[str, ...], int, str, str]] = [
    (
        ("embargos de declaração", "embargos de declaracao"),
        5,
        "embargos de declaração",
        "CPC, art. 1.023 — 5 dias úteis",
    ),
    (
        ("contestação", "contestacao", "contestar"),
        15,
        "contestação",
        "CPC, art. 335 — 15 dias úteis",
    ),
    (
        ("apelação", "apelacao"),
        15,
        "apelação",
        "CPC, art. 1.003, §5º — 15 dias úteis",
    ),
    (
        ("manifestação", "manifestacao"),
        5,
        "manifestação",
        "CPC, art. 218, §3º — prazo supletivo de 5 dias quando inexistir prazo legal/judicial específico",
    ),
]


async def _carregar_comunicacao(
    com_id: str, db: AsyncSession, cu: User
) -> DjenComunicacao:
    comunicacao = (
        await db.execute(select(DjenComunicacao).where(DjenComunicacao.id == com_id))
    ).scalar_one_or_none()
    if not comunicacao or (
        not is_gestao(cu) and comunicacao.advogado_id != cu.id
    ):
        raise HTTPException(status_code=404, detail="Comunicação não encontrada")
    return comunicacao


async def _resolver_regime(
    comunicacao: DjenComunicacao,
    db: AsyncSession,
    override: Regime | None = None,
) -> tuple[Regime | None, str]:
    """Deriva pelo caso; override só entra quando a área não resolve o regime."""
    if comunicacao.case_id:
        area = (
            await db.execute(
                select(Case.area).where(
                    Case.id == comunicacao.case_id, Case.deleted_at.is_(None)
                )
            )
        ).scalar_one_or_none()
        derivado = regime_processual_por_area(area)
        if derivado:
            return derivado, "area_do_caso"
    if override:
        return override, "informado_pelo_advogado"
    return None, "indeterminado"


def _detectar_civel(comunicacao: DjenComunicacao):
    texto = (
        f"{comunicacao.tipo_comunicacao or ''} {comunicacao.texto_resumo or ''}"
    ).lower()
    for termos, dias, rotulo, fundamento in _HEURISTICAS_CIVEIS:
        if any(termo in texto for termo in termos):
            return dias, rotulo, fundamento
    return None


async def _calcular_sugestao(
    comunicacao: DjenComunicacao, db: AsyncSession
) -> dict:
    base = comunicacao.data_disponibilizacao
    if isinstance(base, datetime):
        base = base.date()

    regime, origem_regime = await _resolver_regime(comunicacao, db)
    comum = {
        "com_id": comunicacao.id,
        "numero_processo": comunicacao.numero_processo,
        "case_id": comunicacao.case_id,
        "regime_processual": regime,
        "origem_regime": origem_regime,
        "data_base": base,  # compatibilidade: agora explicitamente disponibilização
        "data_disponibilizacao": base,
        "data_publicacao": None,
        "termo_inicial": None,
        "data_sugerida": None,
        "fundamentacao": None,
        "casou": False,
    }
    if base is None:
        return {
            **comum,
            "disponivel": False,
            "tipo_detectado": "não identificado",
            "dias": None,
            "aviso": (
                "Intimação sem data de disponibilização. Informe a data fatal "
                "manualmente após conferir a publicação original."
            ),
        }

    publicacao = data_publicacao_djen(base, comunicacao.tribunal)
    termo = termo_inicial_djen(publicacao, comunicacao.tribunal, aplicar_recesso=True)
    comum.update({"data_publicacao": publicacao, "termo_inicial": termo})

    if regime is None:
        return {
            **comum,
            "disponivel": False,
            "tipo_detectado": "rito não determinado",
            "dias": None,
            "aviso": (
                "O caso não permite determinar com segurança o regime de contagem. "
                "Informe os dias/regime ou a data fatal após conferência humana."
            ),
        }

    if regime != "civel":
        return {
            **comum,
            "disponivel": False,
            "tipo_detectado": "revisão humana obrigatória",
            "dias": None,
            "aviso": (
                f"Regime {regime}: o EJC não infere automaticamente o número de "
                "dias pelo texto da intimação. Informe os dias ou a data fatal; "
                "o motor aplicará a regra de contagem do regime."
            ),
        }

    detectado = _detectar_civel(comunicacao)
    if detectado is None:
        return {
            **comum,
            "disponivel": False,
            "tipo_detectado": "não identificado",
            "dias": None,
            "aviso": (
                "A intimação cível não casou com uma hipótese legal segura. "
                "Nenhum prazo-padrão foi presumido. Informe os dias ou a data fatal."
            ),
        }

    dias, tipo_detectado, fundamentacao = detectado
    calculo = calcular_prazo_djen(
        base,
        dias,
        "civel",
        comunicacao.tribunal,
    )
    return {
        **comum,
        "disponivel": True,
        "tipo_detectado": tipo_detectado,
        "dias": dias,
        "data_publicacao": calculo["data_publicacao"],
        "termo_inicial": calculo["termo_inicial"],
        "data_sugerida": calculo["data_vencimento"],
        "fundamentacao": fundamentacao,
        "modo_calculo": calculo["modo"],
        "casou": True,
        "aviso": (
            "Sugestão automática assistiva. Confirme tipo de ato, marco inicial, "
            "rito, feriados/suspensões e prazo na publicação original antes de aceitar."
        ),
    }


class AceitarPrazoRequest(BaseModel):
    dias: Optional[int] = Field(default=None, ge=1, le=3650)
    data_prazo: Optional[date] = None
    titulo: Optional[str] = None
    responsavel_id: Optional[str] = None
    prioridade: Optional[str] = None
    regime_processual: Optional[Regime] = None
    excecao_recesso_penal: bool = False


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
        q = q.where(DjenComunicacao.processada.is_(False))
    q = q.order_by(DjenComunicacao.data_disponibilizacao.desc())

    total = (
        await db.execute(select(sqlfunc.count()).select_from(q.subquery()))
    ).scalar()
    rows = (
        await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()

    data = []
    for comunicacao in rows:
        disponibilidade = comunicacao.data_disponibilizacao
        publicacao = (
            data_publicacao_djen(disponibilidade, comunicacao.tribunal)
            if disponibilidade
            else None
        )
        data.append(
            {
                "id": comunicacao.id,
                "numero_processo": comunicacao.numero_processo,
                "tribunal": comunicacao.tribunal,
                "tipo": comunicacao.tipo_comunicacao,
                "data": disponibilidade,
                "data_disponibilizacao": disponibilidade,
                "data_publicacao_calculada": publicacao,
                "texto": (comunicacao.texto_resumo or "")[:500],
                "case_id": comunicacao.case_id,
                "processada": comunicacao.processada,
            }
        )
    return {"data": data, "total": total}


@router.get("/status-captura")
async def status_captura(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
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
                "SELECT count(*) FROM djen_comunicacoes WHERE created_at >= :inicio"
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
    comunicacao = await _carregar_comunicacao(com_id, db, cu)
    if not comunicacao.processada:
        comunicacao.processada = True
        comunicacao.processada_por = cu.id
        comunicacao.processada_em = datetime.now(timezone.utc)
        await criar_audit_log(
            db,
            cu.id,
            cu.role.value,
            "INTIMACAO_TRATADA",
            "djen_comunicacoes",
            comunicacao.id,
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
    return await _calcular_sugestao(comunicacao, db)


@router.get("/{com_id}/prazo-sugerido")
async def prazo_sugerido(
    com_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    comunicacao = await _carregar_comunicacao(com_id, db, cu)
    sugestao = await _calcular_sugestao(comunicacao, db)
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
    payload = payload or AceitarPrazoRequest()
    comunicacao = await _carregar_comunicacao(com_id, db, cu)
    if not comunicacao.case_id:
        raise HTTPException(
            status_code=422,
            detail="Intimação não vinculada a um caso — vincule um caso antes de gerar o prazo.",
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

    sugestao = await _calcular_sugestao(comunicacao, db)
    base = comunicacao.data_disponibilizacao
    if isinstance(base, datetime):
        base = base.date()

    regime, origem_regime = await _resolver_regime(
        comunicacao, db, payload.regime_processual
    )
    if payload.data_prazo is None and regime is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Regime processual indeterminado. Informe regime_processual "
                "junto com os dias ou informe data_prazo diretamente."
            ),
        )

    data_publicacao = None
    termo_inicial = None
    calculo_automatico = False

    if payload.data_prazo is not None:
        data_prazo = payload.data_prazo
        base_legal = sugestao.get("fundamentacao") or "Prazo fatal informado pelo advogado"
        if base and regime:
            data_publicacao = data_publicacao_djen(base, comunicacao.tribunal)
            termo_inicial = termo_inicial_djen(
                data_publicacao,
                comunicacao.tribunal,
                aplicar_recesso=not (
                    regime == "penal" and payload.excecao_recesso_penal
                ),
            )
    elif payload.dias is not None:
        if base is None:
            raise HTTPException(
                status_code=422,
                detail="Intimação sem data de disponibilização — informe data_prazo diretamente.",
            )
        calculo = calcular_prazo_djen(
            base,
            payload.dias,
            regime,  # type: ignore[arg-type]
            comunicacao.tribunal,
            excecao_recesso_penal=payload.excecao_recesso_penal,
        )
        data_prazo = calculo["data_vencimento"]
        data_publicacao = calculo["data_publicacao"]
        termo_inicial = calculo["termo_inicial"]
        calculo_automatico = True
        base_legal = (
            f"{payload.dias} dia(s) informado(s) pelo advogado · {calculo['modo']}"
        )
    else:
        if not sugestao.get("disponivel"):
            raise HTTPException(
                status_code=422,
                detail="Não há sugestão automática segura — informe dias ou data_prazo.",
            )
        data_prazo = sugestao["data_sugerida"]
        data_publicacao = sugestao["data_publicacao"]
        termo_inicial = sugestao["termo_inicial"]
        calculo_automatico = True
        base_legal = sugestao.get("fundamentacao") or "Sugestão automática revisável"
        regime = sugestao.get("regime_processual")
        origem_regime = sugestao.get("origem_regime") or origem_regime

    titulo = payload.titulo or (
        f"{sugestao.get('tipo_detectado') or 'Prazo'} — proc. "
        f"{comunicacao.numero_processo or 's/ número'}"
    )[:255]

    prazo = Deadline(
        id=str(uuid4()),
        titulo=titulo,
        tipo="processual",
        prioridade=payload.prioridade or "alta",
        descricao=(
            "Prazo gerado a partir de intimação DJEN. Revisão humana obrigatória. "
            f"Regime: {regime or 'não informado'} ({origem_regime})."
        ),
        data_prazo=data_prazo,
        data_intimacao=base,
        data_publicacao=data_publicacao,
        termo_inicial=termo_inicial,
        regime_calculo=regime,
        calculo_automatico=calculo_automatico,
        base_legal=base_legal[:255] if base_legal else None,
        case_id=comunicacao.case_id,
        responsavel_id=payload.responsavel_id or comunicacao.advogado_id or cu.id,
        origem="djen",
    )
    db.add(prazo)
    comunicacao.prazo_sugerido_status = "aceito"
    comunicacao.prazo_deadline_id = prazo.id

    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "PRAZO_DJEN_ACEITO",
        "deadlines",
        prazo.id,
        dados_depois={
            "com_id": comunicacao.id,
            "data_disponibilizacao": str(base) if base else None,
            "data_publicacao": str(data_publicacao) if data_publicacao else None,
            "termo_inicial": str(termo_inicial) if termo_inicial else None,
            "data_prazo": str(data_prazo),
            "regime_calculo": regime,
            "calculo_automatico": calculo_automatico,
        },
    )
    await db.commit()
    await db.refresh(prazo)
    return {
        "detail": "Prazo aceito e cadastrado",
        "criado": True,
        "deadline_id": prazo.id,
        "data_disponibilizacao": base,
        "data_publicacao": prazo.data_publicacao,
        "termo_inicial": prazo.termo_inicial,
        "data_prazo": prazo.data_prazo,
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
    comunicacao = await _carregar_comunicacao(com_id, db, cu)
    if comunicacao.case_id:
        await verificar_acesso_caso(db, cu, comunicacao.case_id)
    comunicacao.prazo_sugerido_status = "recusado"
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "PRAZO_DJEN_RECUSADO",
        "djen_comunicacoes",
        comunicacao.id,
    )
    await db.commit()
    return {
        "detail": "Prazo recusado — nenhum prazo foi gerado para esta intimação",
        "prazo_sugerido_status": comunicacao.prazo_sugerido_status,
    }


@router.post("/capturar-agora")
async def capturar_agora(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
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
        "detail": f"{resultado.novas} intimação(ões) nova(s)",
    }
