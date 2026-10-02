# ── app/routers/intimacoes.py ────────────────────────────────────────────────
# Intimações capturadas do DJEN — tratamento humano obrigatório.
# O job do scheduler captura; aqui o advogado revisa e decide.
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func as sqlfunc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import hoje_operacional
from app.core.database import get_db
from app.core.ownership import is_gestao, verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.case import Case, CaseMovimento
from app.models.deadline import Deadline
from app.models.djen import DjenComunicacao
from app.models.user import User
from app.services.djen_service import (
    capturar_para_advogado,
    enviar_emails_pendentes,
    normalizar_processo,
    oab_para_captura,
)

router = APIRouter(prefix="/intimacoes", tags=["Intimações DJEN"])

PRAZO_DJEN_MOTIVO_BLOQUEIO = "calculo_automatico_bloqueado_ate_motor_auditavel_por_regime"

# Escopo da fonte: o DJEN só publica comunicações vinculadas à OAB monitorada.
# Ausência de item aqui NÃO prova ausência de intimação/prazo (Lei 11.419/2006,
# art. 5º — intimação eletrônica por portal; processos/tribunais fora do DJEN).
AVISO_ESCOPO_DJEN = (
    "Esta lista reúne apenas comunicações publicadas no DJEN para as OABs "
    "monitoradas. Intimações eletrônicas por portal/Domicílio Judicial e "
    "processos fora do DJEN não aparecem aqui: não trate a ausência de "
    "itens como ausência de prazo."
)

# Captura manual: uma por usuário por vez (premissa de worker único).
_capturas_manuais_em_curso: set[str] = set()


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
    *,
    for_update: bool = False,
) -> DjenComunicacao:
    stmt = select(DjenComunicacao).where(DjenComunicacao.id == com_id)
    if for_update:
        stmt = stmt.with_for_update()
    c = (await db.execute(stmt)).scalar_one_or_none()
    if not c or (not is_gestao(cu) and c.advogado_id != cu.id):
        raise HTTPException(status_code=404, detail="Comunicação não encontrada")
    return c


class VincularCasoRequest(BaseModel):
    case_id: str = Field(min_length=1, max_length=36)
    # Exigido quando o nº do processo da comunicação difere do cadastrado no caso.
    confirmar_divergencia: bool = False


async def _validar_responsavel_prazo(
    db: AsyncSession,
    responsavel_id: str,
    caso: Case,
) -> User:
    """Responsável precisa existir, estar ativo e poder atuar no caso."""
    resp = (
        await db.execute(
            select(User).where(User.id == responsavel_id, User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if resp is None or not resp.is_active:
        raise HTTPException(status_code=422, detail="Responsável inválido ou inativo")
    if not is_gestao(resp) and resp.id not in (
        caso.advogado_responsavel_id,
        caso.advogado_auxiliar_id,
    ):
        raise HTTPException(
            status_code=422,
            detail="Responsável sem vínculo com o caso da intimação",
        )
    return resp


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
    # Onda 4 (§10): contexto de caso no workspace — a aba "Intimações" do
    # CasoDetalhe lista as comunicações DJEN vinculadas ao caso. A carteira
    # aqui é do CASO (responsável/auxiliar, padrão canônico de atividades.py),
    # não da OAB capturante — por isso o predicado advogado_id NÃO se aplica
    # nesta visão escopada. Sem case_id, comportamento anterior preservado.
    if case_id:
        if not is_gestao(cu):
            await verificar_acesso_caso(db, cu, case_id)
        q = q.where(DjenComunicacao.case_id == case_id)
    elif not is_gestao(cu):
        q = q.where(DjenComunicacao.advogado_id == cu.id)
    if apenas_pendentes:
        q = q.where(DjenComunicacao.processada == False)  # noqa: E712
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
                "vinculo_pendente": comunicacao.case_id is None,
                "orgao": comunicacao.orgao,
                "link_oficial": comunicacao.link_oficial,
            }
            for comunicacao in rows
        ],
        "total": total,
        "aviso_escopo": AVISO_ESCOPO_DJEN,
    }


# Capturas longas (muitas páginas) terminam bem depois de começar; a janela de
# contagem precisa cobri-las — antes eram 5 minutos e subcontava.
_JANELA_CONTAGEM_MIN = 60


async def _contar_recentes(db: AsyncSession, cu: User, inicio: datetime) -> int:
    q = select(sqlfunc.count()).select_from(DjenComunicacao).where(
        DjenComunicacao.created_at >= inicio
    )
    if not is_gestao(cu):
        q = q.where(DjenComunicacao.advogado_id == cu.id)
    return (await db.execute(q)).scalar() or 0


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
        encontradas = await _contar_recentes(
            db, cu, ultima_execucao - timedelta(minutes=_JANELA_CONTAGEM_MIN)
        )
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
            "aviso_escopo": AVISO_ESCOPO_DJEN,
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
    encontradas = await _contar_recentes(
        db, cu, ultimo - timedelta(minutes=_JANELA_CONTAGEM_MIN)
    )
    return {
        "executado_em": ultimo,
        "sucesso": True,
        "intimacoes_encontradas": encontradas,
        "erro": None,
        "defasado": False,
        "ultima_execucao": None,
        "aviso_escopo": AVISO_ESCOPO_DJEN,
    }


@router.get("/{com_id}")
async def detalhe(
    com_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Evidência oficial da comunicação (texto íntegro em texto puro + link)."""
    c = await _carregar_comunicacao(com_id, db, cu)
    if c.case_id and not is_gestao(cu):
        await verificar_acesso_caso(db, cu, c.case_id)
    return {
        "id": c.id,
        "numero_processo": c.numero_processo,
        "tribunal": c.tribunal,
        "orgao": c.orgao,
        "tipo": c.tipo_comunicacao,
        "data": c.data_disponibilizacao,
        "texto": c.texto_integral or c.texto_resumo or "",
        "texto_completo": c.texto_integral is not None,
        "link_oficial": c.link_oficial,
        "case_id": c.case_id,
        "processada": c.processada,
        "prazo_sugerido_status": c.prazo_sugerido_status or "nenhum",
        "prazo_deadline_id": c.prazo_deadline_id,
        "aviso_escopo": AVISO_ESCOPO_DJEN,
    }


@router.post("/{com_id}/vincular-caso")
async def vincular_caso(
    com_id: str,
    payload: VincularCasoRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Vínculo manual comunicação → caso (inclusive caso encerrado/arquivado).

    O auto-vínculo só cobre caso ativo com número único; sem este endpoint a
    comunicação de processo não cadastrado/reaberto não conseguia gerar prazo.
    """
    from app.models.audit_log import criar_audit_log

    c = await _carregar_comunicacao(com_id, db, cu, for_update=True)
    if c.prazo_sugerido_status == "aceito" and c.prazo_deadline_id:
        raise HTTPException(
            status_code=409,
            detail="Prazo já aceito para esta intimação; o vínculo não pode ser alterado.",
        )
    if c.case_id and c.case_id != payload.case_id:
        await verificar_acesso_caso(db, cu, c.case_id)
    caso = await verificar_acesso_caso(db, cu, payload.case_id)

    divergente = bool(c.numero_processo) and bool(caso.numero_processo) and (
        normalizar_processo(c.numero_processo) != normalizar_processo(caso.numero_processo)
    )
    if divergente and not payload.confirmar_divergencia:
        raise HTTPException(
            status_code=422,
            detail=(
                "O número do processo da comunicação difere do cadastrado no "
                "caso. Confirme a divergência para vincular mesmo assim."
            ),
        )
    if c.case_id == caso.id:
        return {"detail": "Intimação já estava vinculada a este caso", "case_id": caso.id}

    anterior = c.case_id
    c.case_id = caso.id
    db.add(
        CaseMovimento(
            id=str(uuid4()),
            case_id=caso.id,
            tipo="intimacao",
            descricao=(
                f"📨 Intimação DJEN ({c.tribunal or 'tribunal'}): "
                f"{c.tipo_comunicacao or 'comunicação'} — vinculada manualmente "
                "pelo usuário; tratar na tela Intimações"
            ),
            created_by=cu.id,
        )
    )
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "UPDATE",
        "djen_comunicacoes",
        c.id,
        dados_antes={"case_id": anterior},
        dados_depois={"case_id": caso.id, "divergencia_confirmada": divergente},
    )
    await db.commit()
    return {"detail": "Intimação vinculada ao caso", "case_id": caso.id}


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
    # FOR UPDATE: dois aceites concorrentes não criam dois prazos.
    comunicacao = await _carregar_comunicacao(com_id, db, cu, for_update=True)

    if not comunicacao.case_id:
        raise HTTPException(
            status_code=422,
            detail=("Intimação não vinculada a um caso — vincule um caso antes de gerar o prazo."),
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
    if data_prazo < hoje_operacional():
        raise HTTPException(
            status_code=422,
            detail="data_prazo no passado: confira a publicação e o termo inicial.",
        )
    responsavel_id = payload.responsavel_id or comunicacao.advogado_id or cu.id
    if payload.responsavel_id:
        await _validar_responsavel_prazo(db, payload.responsavel_id, caso)
    aviso_dia_nao_util = (
        "data_prazo cai em fim de semana: confira a prorrogação para o primeiro "
        "dia útil (CPC, art. 224, § 1º) e o calendário forense."
        if data_prazo.weekday() >= 5
        else None
    )
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
        responsavel_id=responsavel_id,
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
        "aviso": aviso_dia_nao_util,
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


@router.post(
    "/capturar-agora",
    dependencies=[Depends(rate_limit("intimacoes-capturar-agora", 3))],
)
async def capturar_agora(
    dias: int = Query(7, ge=1, le=90, description="Janela de disponibilização (dias)"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Captura manual sem contaminar o heartbeat do job agendado."""
    # Mesma resolução do job (campo dedicado OU OAB de perfil com UF): antes a
    # tela recusava quem o job capturava normalmente.
    numero, uf = oab_para_captura(cu)
    if not numero or not uf:
        raise HTTPException(
            status_code=422,
            detail="Configure sua OAB (número e UF) no seu perfil de usuário",
        )
    if cu.id in _capturas_manuais_em_curso:
        raise HTTPException(
            status_code=409,
            detail="Já existe uma captura manual em andamento para este usuário.",
        )

    _capturas_manuais_em_curso.add(cu.id)
    try:
        resultado = await capturar_para_advogado(db, cu, dias=dias)
        if not resultado.fonte_ok:
            await db.rollback()
            raise HTTPException(
                status_code=503,
                detail=(f"Captura DJEN indisponível no momento (código: {resultado.erro or 'erro_interno'})."),
            )

        await db.commit()
    finally:
        _capturas_manuais_em_curso.discard(cu.id)
    await enviar_emails_pendentes(resultado)
    return {
        "novas": resultado.novas,
        "recebidas": resultado.recebidas,
        "duplicadas": resultado.duplicadas,
        "ignoradas": resultado.ignoradas,
        "paginas": resultado.paginas,
        "janela_dias": resultado.janela_dias,
        "detail": f"{resultado.novas} intimação(ões) nova(s)",
        "aviso_escopo": AVISO_ESCOPO_DJEN,
    }
