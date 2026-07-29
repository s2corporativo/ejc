# ── app/routers/intimacoes.py ────────────────────────────────────────────────
# Intimações capturadas do DJEN — tratamento humano obrigatório.
# O job do scheduler captura; aqui o advogado processa.
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

_HEURISTICAS_PRAZO: list[tuple[tuple[str, ...], int, str, str]] = [
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
        ("apelação", "apelacao", "recurso"),
        15,
        "apelação/recurso",
        "CPC, art. 1.003, §5º — 15 dias úteis",
    ),
    (
        ("manifestação", "manifestacao", "despacho"),
        5,
        "manifestação/despacho",
        "CPC, art. 218, §3º — 5 dias úteis (prazo supletivo, na ausência de "
        "prazo legal ou judicial específico)",
    ),
]


def _calcular_sugestao(c: DjenComunicacao) -> dict:
    """Calcula sugestão de prazo sem persistir ou substituir conferência humana."""
    from app.services.deadline_calculator import prazo_dias_uteis

    texto = f"{c.tipo_comunicacao or ''} {c.texto_resumo or ''}".lower()

    tipo_detectado = None
    dias = 15
    fundamentacao = None
    casou = False
    for termos, prazo, rotulo, artigo in _HEURISTICAS_PRAZO:
        if any(termo in texto for termo in termos):
            tipo_detectado = rotulo
            dias = prazo
            fundamentacao = artigo
            casou = True
            break

    if not casou:
        tipo_detectado = "não identificado"
        dias = 15
        fundamentacao = None

    base = c.data_disponibilizacao
    if isinstance(base, datetime):
        base = base.date()
    if base is None:
        return {
            "disponivel": False,
            "com_id": c.id,
            "numero_processo": c.numero_processo,
            "case_id": c.case_id,
            "tipo_detectado": tipo_detectado,
            "dias": dias,
            "data_base": None,
            "data_sugerida": None,
            "fundamentacao": fundamentacao,
            "casou": casou,
            "aviso": (
                "Intimação sem data de disponibilização — não é possível sugerir "
                "prazo automaticamente. Informe o termo inicial manualmente."
            ),
        }

    data_sugerida = prazo_dias_uteis(base, dias, tribunal=c.tribunal)

    aviso = (
        "Sugestão automática — confirme o tipo, o termo inicial e o prazo na "
        "publicação original antes de cadastrar. Não substitui a conferência "
        "do advogado responsável."
    )
    if not casou:
        aviso = (
            "Tipo de intimação não identificado automaticamente. Prazo padrão "
            "de 15 dias úteis apresentado apenas como referência — defina o "
            "prazo correto conforme a publicação. "
            + aviso
        )

    return {
        "disponivel": True,
        "com_id": c.id,
        "numero_processo": c.numero_processo,
        "case_id": c.case_id,
        "tipo_detectado": tipo_detectado,
        "dias": dias,
        "data_base": base,
        "data_sugerida": data_sugerida,
        "fundamentacao": fundamentacao,
        "casou": casou,
        "aviso": aviso,
    }


async def _carregar_comunicacao(
    com_id: str,
    db: AsyncSession,
    cu: User,
) -> DjenComunicacao:
    c = (
        await db.execute(
            select(DjenComunicacao).where(DjenComunicacao.id == com_id)
        )
    ).scalar_one_or_none()
    if not c or (not is_gestao(cu) and c.advogado_id != cu.id):
        raise HTTPException(status_code=404, detail="Comunicação não encontrada")
    return c


class AceitarPrazoRequest(BaseModel):
    dias: Optional[int] = None
    data_prazo: Optional[date] = None
    titulo: Optional[str] = None
    responsavel_id: Optional[str] = None
    prioridade: Optional[str] = None


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
                "id": comunicacao.id,
                "numero_processo": comunicacao.numero_processo,
                "tribunal": comunicacao.tribunal,
                "tipo": comunicacao.tipo_comunicacao,
                "data": comunicacao.data_disponibilizacao,
                "texto": (comunicacao.texto_resumo or "")[:500],
                "case_id": comunicacao.case_id,
                "processada": comunicacao.processada,
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
            erro = (
                heartbeat.detail or "Última execução do job DJEN falhou."
            )[:300]
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

    ultimo = (
        await db.execute(
            _t("SELECT max(created_at) FROM djen_comunicacoes")
        )
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
    comunicacao = (
        await db.execute(
            select(DjenComunicacao).where(DjenComunicacao.id == com_id)
        )
    ).scalar_one_or_none()
    if not comunicacao or (
        not is_gestao(cu) and comunicacao.advogado_id != cu.id
    ):
        raise HTTPException(status_code=404, detail="Comunicação não encontrada")
    comunicacao.processada = True
    comunicacao.processada_por = cu.id
    comunicacao.processada_em = datetime.now(timezone.utc)
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
    sugestao["prazo_sugerido_status"] = (
        comunicacao.prazo_sugerido_status or "nenhum"
    )
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
    from app.services.deadline_calculator import prazo_dias_uteis

    payload = payload or AceitarPrazoRequest()
    comunicacao = await _carregar_comunicacao(com_id, db, cu)

    if not comunicacao.case_id:
        raise HTTPException(
            status_code=422,
            detail=(
                "Intimação não vinculada a um caso — vincule um caso antes "
                "de gerar o prazo."
            ),
        )

    await verificar_acesso_caso(db, cu, comunicacao.case_id)

    if (
        comunicacao.prazo_sugerido_status == "aceito"
        and comunicacao.prazo_deadline_id
    ):
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
    base = comunicacao.data_disponibilizacao
    if isinstance(base, datetime):
        base = base.date()

    if payload.data_prazo is not None:
        data_prazo = payload.data_prazo
        base_legal = (
            sugestao.get("fundamentacao") or "Prazo informado manualmente"
        )
    elif payload.dias is not None:
        if base is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Intimação sem data de disponibilização — informe "
                    "data_prazo diretamente."
                ),
            )
        data_prazo = prazo_dias_uteis(
            base,
            payload.dias,
            tribunal=comunicacao.tribunal,
        )
        base_legal = (
            sugestao.get("fundamentacao") or f"{payload.dias} dias úteis"
        )
    else:
        if not sugestao.get("disponivel"):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Não há sugestão de prazo disponível — informe dias ou "
                    "data_prazo."
                ),
            )
        data_prazo = sugestao["data_sugerida"]
        base_legal = sugestao.get("fundamentacao") or (
            f"{sugestao['dias']} dias úteis (sugestão automática)"
        )

    titulo = payload.titulo or (
        f"{sugestao.get('tipo_detectado') or 'Prazo'} — "
        f"proc. {comunicacao.numero_processo or 's/ número'}"
    )[:255]

    prazo = Deadline(
        id=str(uuid4()),
        titulo=titulo,
        tipo="processual",
        prioridade=payload.prioridade or "alta",
        descricao=(
            "Prazo gerado a partir de intimação DJEN "
            f"({comunicacao.tribunal or 'tribunal n/d'}). "
            f"{sugestao.get('aviso') or ''}"
        ).strip(),
        data_prazo=data_prazo,
        data_intimacao=base,
        base_legal=base_legal[:255] if base_legal else None,
        case_id=comunicacao.case_id,
        responsavel_id=(
            payload.responsavel_id
            or comunicacao.advogado_id
            or cu.id
        ),
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
        dados_depois={"origem": "djen", "com_id": comunicacao.id},
    )
    await db.commit()
    await db.refresh(prazo)
    return {
        "detail": "Prazo aceito e cadastrado",
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
    comunicacao = await _carregar_comunicacao(com_id, db, cu)
    if comunicacao.case_id:
        await verificar_acesso_caso(db, cu, comunicacao.case_id)
    comunicacao.prazo_sugerido_status = "recusado"
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
    if not (cu.djen_oab_numero or "").strip() or not (
        cu.djen_oab_uf or ""
    ).strip():
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
