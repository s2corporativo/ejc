# ── app/services/retencao_lgpd_service.py ────────────────────────────────────
# Retenção LGPD de clientes/casos — IDENTIFICA e REPORTA, nunca apaga.
#
# Achado DB-14 da auditoria de camadas de 06/09/2026: o scheduler só expurga
# telemetria de rotas e rascunhos da Entrada Única; nenhum job olha para
# `clients`/`cases` frente a `docs/DPT360_POLITICA_RETENCAO_LGPD.md`.
#
# O que a política define e o que ela NÃO define — lido antes de escrever:
#   - Define, com prazos, o ciclo de vida das OPORTUNIDADES DPT360
#     (`document_intake_batches`, modalidade `dpt360_oportunidade`): 30 dias
#     para expirar triagem pendente, 90 dias após triagem concluída, 30 dias
#     de descartada até anonimizar, 30 dias de anonimizada até expurgar. Esses
#     prazos já são aplicados por `app/modules/dpt360/lifecycle_service.py`.
#   - NÃO define prazo de retenção para cliente ou caso. Diz apenas que dado
#     vinculado a Cliente/Caso é PROTEGIDO ("nunca expurgar se convertido").
#
# Por isso este serviço:
#   1. Para oportunidades DPT360, reaproveita as constantes da política e só
#      CONTA o que está além do prazo (o lifecycle_service é quem age).
#   2. Para clientes e casos, usa prazos PROVISÓRIOS declarados abaixo, com a
#      base legal que os justifica como piso, e produz um RELATÓRIO (contagens
#      + amostra de ids, sem PII). A decisão de anonimizar/expurgar é do
#      titular e passa pelo fluxo existente (`client_anonimizacao.py`, com
#      bloqueios e auditoria) — nunca por este job.
#   3. Bate ponto no heartbeat com o RESULTADO (contagens serializadas), não
#      com um "ok" mudo — mesma regra do expurgo da Entrada Única.
#
# Prazos provisórios (candidatos a settings; ver relatório do PR):
#   PRAZO_CASO_ENCERRADO_DIAS = 1825 (5 anos) — piso: prescrição da pretensão
#     de honorários (CC art. 206, §5º, II) e guarda fiscal; a Lei 8.906/94 e o
#     Provimento OAB não fixam prazo de guarda do dossiê, e o CPC (art. 425,
#     §2º-A) permite descarte de autos físicos só após trânsito em julgado.
#   PRAZO_CLIENTE_INATIVO_DIAS = 1825 — cliente inativo/arquivado sem caso
#     aberto há 5 anos.
#   PRAZO_LEAD_SEM_CONVERSAO_DIAS = 90 — lead (`clients.status = 'lead'`) sem
#     caso, espelhando o prazo de `triagem_concluida` da política DPT360, o
#     único análogo documentado para "contato sem conversão".
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case, CaseStatus
from app.models.client import Client, ClientStatus
from app.models.document_intake import DocumentIntakeBatch

logger = logging.getLogger(__name__)

PRAZO_CASO_ENCERRADO_DIAS = 1825
PRAZO_CLIENTE_INATIVO_DIAS = 1825
PRAZO_LEAD_SEM_CONVERSAO_DIAS = 90

#: Estados de caso que representam representação em curso — um cliente com
#: caso nestes estados nunca entra no relatório (política: dado vinculado a
#: caso vivo é protegido). Espelha `core/status_caso.STATUS_ABERTOS`; copiado
#: aqui para o serviço não depender de um módulo em edição paralela.
_STATUS_CASO_ABERTOS = (
    CaseStatus.aberto,
    CaseStatus.em_instrucao,
    CaseStatus.em_producao,
    CaseStatus.protocolado,
)
_STATUS_CASO_FECHADOS = (CaseStatus.encerrado, CaseStatus.arquivado)
_STATUS_CLIENTE_INATIVOS = (ClientStatus.inativo, ClientStatus.arquivado)

_MODALIDADE_DPT360 = "dpt360_oportunidade"
_AMOSTRA_PADRAO = 20

ACAO = "somente_relatorio"


def _prazos_dpt360() -> tuple[int, int]:
    """(dias até anonimizar descartada/expirada, dias até expurgar anonimizada)
    — lidos da política em código; fallback aos valores do documento."""
    try:
        from app.modules.dpt360 import lifecycle_service as lc
        return int(lc.PRAZO_DESCARTADA), int(lc.PRAZO_ANONIMIZADA)
    except Exception:  # noqa: BLE001 — módulo opcional
        return 30, 30


async def _contar_e_amostrar(db: AsyncSession, id_col, cond, amostra: int) -> dict:
    total = int((await db.execute(select(func.count()).where(cond))).scalar() or 0)
    ids: list[str] = []
    if total and amostra > 0:
        ids = [
            str(v) for v in
            (await db.execute(select(id_col).where(cond).order_by(id_col).limit(amostra))).scalars().all()
        ]
    return {"total": total, "amostra_ids": ids}


async def identificar_alem_do_prazo(
    db: AsyncSession,
    *,
    agora: datetime | None = None,
    prazo_caso_dias: int = PRAZO_CASO_ENCERRADO_DIAS,
    prazo_cliente_dias: int = PRAZO_CLIENTE_INATIVO_DIAS,
    prazo_lead_dias: int = PRAZO_LEAD_SEM_CONVERSAO_DIAS,
    amostra: int = _AMOSTRA_PADRAO,
) -> dict:
    """Relatório de retenção: o que está além do prazo, por categoria.

    Não altera nada. Devolve contagens e uma amostra de ids (nunca nome,
    documento ou contato) para o operador localizar os registros.
    """
    agora = agora or datetime.now(timezone.utc)
    corte_caso = agora - timedelta(days=prazo_caso_dias)
    corte_cliente = agora - timedelta(days=prazo_cliente_dias)
    corte_lead = agora - timedelta(days=prazo_lead_dias)
    dias_anonimizar, dias_expurgar = _prazos_dpt360()
    corte_dpt_anon = agora - timedelta(days=dias_anonimizar)
    corte_dpt_expurgo = agora - timedelta(days=dias_expurgar)

    # 1. Casos encerrados/arquivados há mais de N dias (vivos — soft-deleted
    #    já saíram da operação e têm fluxo próprio de lixeira).
    cond_casos = and_(
        Case.deleted_at.is_(None),
        Case.status.in_(_STATUS_CASO_FECHADOS),
        func.coalesce(Case.data_encerramento, Case.updated_at, Case.created_at) < corte_caso,
    )
    casos = await _contar_e_amostrar(db, Case.id, cond_casos, amostra)

    # Cliente com QUALQUER caso aberto é protegido (representação em curso).
    tem_caso_aberto = exists().where(
        and_(
            Case.client_id == Client.id,
            Case.deleted_at.is_(None),
            Case.status.in_(_STATUS_CASO_ABERTOS),
        )
    )
    tem_algum_caso = exists().where(Case.client_id == Client.id)

    # 2. Clientes inativos/arquivados, não anonimizados, sem caso aberto,
    #    sem atualização há mais de N dias.
    cond_clientes = and_(
        Client.deleted_at.is_(None),
        Client.anonimizado_em.is_(None),
        Client.status.in_(_STATUS_CLIENTE_INATIVOS),
        func.coalesce(Client.updated_at, Client.created_at) < corte_cliente,
        ~tem_caso_aberto,
    )
    clientes = await _contar_e_amostrar(db, Client.id, cond_clientes, amostra)

    # 3. Leads sem conversão (nenhum caso) há mais de N dias.
    cond_leads = and_(
        Client.deleted_at.is_(None),
        Client.anonimizado_em.is_(None),
        Client.status == ClientStatus.lead,
        func.coalesce(Client.updated_at, Client.created_at) < corte_lead,
        ~tem_algum_caso,
    )
    leads = await _contar_e_amostrar(db, Client.id, cond_leads, amostra)

    # 4. Oportunidades DPT360 além do prazo da política (o lifecycle_service
    #    age sobre elas; aqui só se mede se ele está dando conta).
    cond_dpt_anon = and_(
        DocumentIntakeBatch.modalidade == _MODALIDADE_DPT360,
        DocumentIntakeBatch.ciclo_vida_estado.in_(("descartada", "expirada")),
        DocumentIntakeBatch.anonimizada_em.is_(None),
        DocumentIntakeBatch.case_id.is_(None),
        DocumentIntakeBatch.ciclo_vida_updated_at < corte_dpt_anon,
    )
    cond_dpt_expurgo = and_(
        DocumentIntakeBatch.modalidade == _MODALIDADE_DPT360,
        DocumentIntakeBatch.ciclo_vida_estado == "anonimizada",
        DocumentIntakeBatch.anonimizada_em.is_not(None),
        DocumentIntakeBatch.case_id.is_(None),
        DocumentIntakeBatch.anonimizada_em < corte_dpt_expurgo,
    )
    dpt_anon = await _contar_e_amostrar(db, DocumentIntakeBatch.id, cond_dpt_anon, amostra)
    dpt_expurgo = await _contar_e_amostrar(db, DocumentIntakeBatch.id, cond_dpt_expurgo, amostra)

    total = casos["total"] + clientes["total"] + leads["total"] + dpt_anon["total"] + dpt_expurgo["total"]
    return {
        "acao": ACAO,
        "gerado_em": agora.isoformat(),
        "casos_encerrados_alem_prazo": {"prazo_dias": prazo_caso_dias, **casos},
        "clientes_inativos_alem_prazo": {"prazo_dias": prazo_cliente_dias, **clientes},
        "leads_sem_conversao_alem_prazo": {"prazo_dias": prazo_lead_dias, **leads},
        "dpt360_a_anonimizar": {"prazo_dias": dias_anonimizar, **dpt_anon},
        "dpt360_a_expurgar": {"prazo_dias": dias_expurgar, **dpt_expurgo},
        "total_alem_prazo": total,
    }


def resumo_heartbeat(relatorio: dict) -> str:
    """Só contagens (cabe nos 500 chars do heartbeat; sem ids, sem PII)."""
    chaves = (
        "casos_encerrados_alem_prazo", "clientes_inativos_alem_prazo",
        "leads_sem_conversao_alem_prazo", "dpt360_a_anonimizar", "dpt360_a_expurgar",
    )
    compacto = {k: relatorio.get(k, {}).get("total", 0) for k in chaves}
    compacto["total"] = relatorio.get("total_alem_prazo", 0)
    compacto["acao"] = relatorio.get("acao", ACAO)
    if "erro" in relatorio:
        compacto["erro"] = relatorio["erro"]
    return json.dumps(compacto, ensure_ascii=False)


async def job_retencao_lgpd() -> dict:
    """Job agendado: gera o relatório e bate ponto por RESULTADO.

    Registro no scheduler (services/scheduler.py, ao lado de `purga_lgpd`):
        from app.services.retencao_lgpd_service import job_retencao_lgpd
        s.add_job(job_retencao_lgpd, CronTrigger(day_of_week="sun", hour=2, minute=45),
                  id="retencao_lgpd", replace_existing=True)
    """
    from app.core.database import AsyncSessionLocal
    from app.services.heartbeat_service import JOB_RETENCAO_LGPD, registrar_heartbeat

    status = "ok"
    relatorio: dict
    try:
        async with AsyncSessionLocal() as db:
            relatorio = await identificar_alem_do_prazo(db)
    except Exception as exc:  # noqa: BLE001 — job nunca derruba o scheduler
        status = "erro"
        relatorio = {"acao": ACAO, "erro": type(exc).__name__, "total_alem_prazo": 0}
        logger.error("[retencao_lgpd] falha ao gerar relatório: %s", exc)
    else:
        if relatorio["total_alem_prazo"]:
            logger.warning(
                "[retencao_lgpd] %s registro(s) além do prazo de retenção — "
                "somente relatório, nada foi alterado: %s",
                relatorio["total_alem_prazo"], resumo_heartbeat(relatorio),
            )
        else:
            logger.info("[retencao_lgpd] nenhum registro além do prazo.")

    try:
        async with AsyncSessionLocal() as db:
            await registrar_heartbeat(db, JOB_RETENCAO_LGPD, status, resumo_heartbeat(relatorio))
    except Exception as exc:  # noqa: BLE001 — heartbeat é best-effort
        logger.warning("[retencao_lgpd] heartbeat não registrado: %s", exc)
    return relatorio
