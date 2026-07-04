# ── app/services/scheduler.py ────────────────────────────────────────────────
# APScheduler — alertas automáticos do escritório.
# CORREÇÃO P0-3 do v2: gate ENABLE_SCHEDULER evita jobs duplicados quando
# uvicorn roda com múltiplos workers. Padrão Dockerfile: --workers 1.
#
# Jobs:
#  06:55 — Briefing matinal por advogado (personalizado)
#  07:00 — Morning Brief WhatsApp (consolidado do dia)
#  07:15 — Alertas de prazos (7d/3d/1d)
#  07:30 — SLA de etapas BPM (workflow) — vencidos + vésperas
#  08:00 — Honorários vencidos
#  08:15 — Régua de cobrança escalonada (inadimplência)
#  08:30 — Defesas ambientais ≤ 5 dias (crítico)
#  09:00 seg — Procurações vencendo em 30 dias
#  09:15 — Alertas de vencimento societário
from __future__ import annotations
import logging
from uuid import uuid4
from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text, select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)
settings = get_settings()
_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")
    return _scheduler


# ── Jobs ──────────────────────────────────────────────────────────────────────

async def _morning_brief():
    """Briefing diário 07h00 — WhatsApp para o admin."""
    from app.core.database import AsyncSessionLocal
    from app.services.notification_service import enviar_whatsapp

    try:
        async with AsyncSessionLocal() as db:
            hoje = date.today()
            d3 = hoje + timedelta(days=3)
            d7 = hoje + timedelta(days=7)

            # Prazos fatais 3 dias
            r1 = await db.execute(text("""
                SELECT COUNT(*) FROM deadlines
                WHERE status='pendente' AND deleted_at IS NULL
                  AND data_prazo BETWEEN :hoje AND :d3
            """), {"hoje": hoje, "d3": d3})
            prazos_3d = r1.scalar() or 0

            # Prazos 7 dias
            r2 = await db.execute(text("""
                SELECT COUNT(*) FROM deadlines
                WHERE status='pendente' AND deleted_at IS NULL
                  AND data_prazo BETWEEN :hoje AND :d7
            """), {"hoje": hoje, "d7": d7})
            prazos_7d = r2.scalar() or 0

            # Honorários vencidos
            r3 = await db.execute(text("""
                SELECT COUNT(*), COALESCE(SUM(valor),0) FROM fees
                WHERE status IN ('pendente','atrasado') AND deleted_at IS NULL
                  AND data_vencimento < :hoje
            """), {"hoje": hoje})
            hon_qtd, hon_valor = r3.one()

            # Defesas ambientais críticas (≤5 dias)
            r4 = await db.execute(text("""
                SELECT COUNT(*) FROM environmental_cases
                WHERE status_defesa IN ('prazo_correndo','elaborando')
                  AND deleted_at IS NULL
                  AND data_prazo_defesa <= :d5
            """), {"d5": hoje + timedelta(days=5)})
            amb_criticas = r4.scalar() or 0

            # _morning_brief_email: busca admin para e-mail + push
            r5 = await db.execute(text("""
                SELECT id, email FROM users
                WHERE role IN ('superadmin','admin') AND is_active=true
                  AND email IS NOT NULL LIMIT 1
            """))
            admin_row = r5.first()

        msg_txt = (
            f"Morning Brief {hoje.strftime('%d/%m/%Y')}\n"
            f"Prazos fatais (3d): {prazos_3d} | "
            f"Prazos 7d: {prazos_7d} | "
            f"Honor. vencidos: {hon_qtd} (R$ {hon_valor:,.2f}) | "
            f"IBAMA <=5d: {amb_criticas}"
        )
        msg_html = (
            f"<h3>EJC — Morning Brief {hoje.strftime('%d/%m/%Y')}</h3>"
            f"<ul>"
            f"<li><b>Prazos fatais (3 dias):</b> {prazos_3d}</li>"
            f"<li><b>Prazos 7 dias:</b> {prazos_7d}</li>"
            f"<li><b>Honorários vencidos:</b> {hon_qtd} (R$ {hon_valor:,.2f})</li>"
            f"<li><b>Defesas IBAMA ≤5 dias:</b> {amb_criticas}</li>"
            f"</ul><p><a href='https://ejc.depaulateixeira.adv.br'>Acessar EJC</a></p>"
        )
        async with AsyncSessionLocal() as db2:
            from app.services.notification_service import enviar_email, enviar_push, criar_notificacao_interna
            if admin_row:
                # E-mail
                try:
                    await enviar_email(
                        admin_row.email,
                        f"[EJC] Morning Brief {hoje.strftime('%d/%m')}",
                        msg_html,
                    )
                except Exception as _e:
                    logger.warning(f"[Brief] email falhou: {_e}")
                # Push interno
                try:
                    await criar_notificacao_interna(
                        db2, admin_row.id,
                        f"Morning Brief {hoje.strftime('%d/%m/%Y')}",
                        msg_txt, tipo="sistema", link="/",
                    )
                    await db2.commit()
                except Exception as _e:
                    logger.warning(f"[Brief] notif falhou: {_e}")
        logger.info(f"[Brief] {prazos_3d} prazos 3d, {amb_criticas} amb críticas")
    except Exception as e:
        logger.error(f"[Scheduler] morning_brief: {e}")


async def _alertar_prazos():
    """Alerta prazos 7/3/1 dias por TRÊS canais: notificação interna (sino),
    e-mail e WhatsApp ao responsável. E-mail/WhatsApp só disparam se habilitados
    no .env (EMAIL_ENABLED / WHATSAPP_ENABLED) — caso contrário, no-op seguro."""
    from app.core.database import AsyncSessionLocal
    from app.services.notification_service import (
        criar_notificacao_interna, enviar_email, enviar_whatsapp, enviar_push,
    )

    try:
        async with AsyncSessionLocal() as db:
            hoje = date.today()
            for dias, flag in [(7, "alerta_7d_enviado"),
                               (3, "alerta_3d_enviado"),
                               (1, "alerta_1d_enviado")]:
                alvo = hoje + timedelta(days=dias)
                rows = await db.execute(text(f"""
                    SELECT d.id, d.titulo, d.data_prazo, d.responsavel_id, u.email, u.phone
                    FROM deadlines d
                    LEFT JOIN users u ON u.id = d.responsavel_id
                    WHERE d.status='pendente' AND d.deleted_at IS NULL
                      AND d.data_prazo <= :alvo AND d.data_prazo >= :hoje AND d.{flag} = false
                      AND d.responsavel_id IS NOT NULL
                """), {"alvo": alvo, "hoje": hoje})
                for r in rows:
                    venc = r.data_prazo.strftime('%d/%m/%Y')
                    dias_reais = (r.data_prazo - hoje).days
                    await criar_notificacao_interna(
                        db, r.responsavel_id,
                        f"⏰ Prazo em {dias_reais} dia(s)",
                        f"{r.titulo} vence em {venc}",
                        tipo="prazo", link=f"/prazos",
                    )
                    await enviar_push(
                        db, r.responsavel_id,
                        f"⏰ Prazo em {dias_reais} dia(s)",
                        f"{r.titulo} vence em {venc}",
                        link="/prazos",
                    )
                    if r.email:
                        await enviar_email(
                            r.email,
                            f"[EJC] Prazo em {dias_reais} dia(s): {r.titulo}",
                            f"<p>O prazo <b>{r.titulo}</b> vence em "
                            f"<b>{venc}</b> ({dias_reais} dia(s)).</p>"
                            f"<p>Acesse o EJC para os detalhes do caso.</p>",
                        )
                    if r.phone:
                        await enviar_whatsapp(
                            r.phone,
                            f"⏰ *EJC* — o prazo \"{r.titulo}\" vence em "
                            f"{venc} ({dias_reais} dia(s)).",
                        )
                    await db.execute(text(
                        f"UPDATE deadlines SET {flag}=true WHERE id=:id"
                    ), {"id": r.id})
                await db.commit()
    except Exception as e:
        logger.error(f"[Scheduler] alertar_prazos: {e}")


async def _alertar_ambiental():
    """Defesas ambientais ≤5 dias → notificação crítica + WhatsApp."""
    from app.core.database import AsyncSessionLocal
    from app.services.notification_service import (
        criar_notificacao_interna, enviar_whatsapp,
    )
    try:
        async with AsyncSessionLocal() as db:
            limite = date.today() + timedelta(days=5)
            rows = await db.execute(text("""
                SELECT ec.numero_auto, ec.data_prazo_defesa,
                       c.advogado_responsavel_id, u.phone
                FROM environmental_cases ec
                JOIN cases c ON c.id = ec.case_id
                LEFT JOIN users u ON u.id = c.advogado_responsavel_id
                WHERE ec.status_defesa IN ('prazo_correndo','elaborando')
                  AND ec.deleted_at IS NULL
                  AND ec.data_prazo_defesa <= :lim
            """), {"lim": limite})
            for r in rows:
                if r.advogado_responsavel_id:
                    await criar_notificacao_interna(
                        db, r.advogado_responsavel_id,
                        "🌿 DEFESA AMBIENTAL URGENTE",
                        f"Auto {r.numero_auto} — prazo: "
                        f"{r.data_prazo_defesa.strftime('%d/%m/%Y')}",
                        tipo="ambiental", link="/ambiental",
                    )
                if r.phone:
                    await enviar_whatsapp(
                        r.phone,
                        f"🌿 *URGENTE EJC*: Defesa IBAMA auto {r.numero_auto} "
                        f"vence {r.data_prazo_defesa.strftime('%d/%m')}!",
                    )
    except Exception as e:
        logger.error(f"[Scheduler] alertar_ambiental: {e}")


async def _alertar_prescricao():
    """Casos com prescrição ≤90 dias → alerta semanal ao responsável."""
    from app.core.database import AsyncSessionLocal
    from app.services.notification_service import criar_notificacao_interna
    try:
        async with AsyncSessionLocal() as db:
            limite = date.today() + timedelta(days=90)
            rows = await db.execute(text("""
                SELECT c.id, c.titulo, c.tipo_acao_prescricao,
                       c.data_prescricao, c.advogado_responsavel_id
                FROM cases c
                WHERE c.deleted_at IS NULL
                  AND c.data_prescricao IS NOT NULL
                  AND c.data_prescricao::date <= :lim
                  AND c.data_prescricao::date >= CURRENT_DATE
                  AND c.status NOT IN ('encerrado','arquivado')
            """), {"lim": limite})
            for r in rows:
                if not r.advogado_responsavel_id:
                    continue
                dias = (r.data_prescricao.date() - date.today()).days
                await criar_notificacao_interna(
                    db, r.advogado_responsavel_id,
                    "\u23f3 PRESCRIÇÃO SE APROXIMANDO",
                    f"Caso \"{r.titulo}\" — prescrição em {dias} dia(s) "
                    f"({r.data_prescricao.strftime('%d/%m/%Y')})"
                    + (f" · {r.tipo_acao_prescricao}" if r.tipo_acao_prescricao else ""),
                    tipo="prescricao", link=f"/casos/{r.id}",
                )
    except Exception as e:
        logger.error(f"[Scheduler] alertar_prescricao: {e}")


async def _verificar_sla_workflows():
    """07h30 — SLA das etapas de workflow BPM, em DIAS ÚTEIS (R9/Seção 11).

    Para cada CaseWorkflow em progresso (status='ativo'):
      vencimento = data de entrada na etapa atual (WorkflowHistorico aberto)
                   + sla_dias_uteis, via deadline_calculator.prazo_dias_uteis
                   (respeita feriados e suspensões carregados do banco).
      - VENCIDO (hoje > vencimento)  → status='atrasado' + histórico
        '[sla_vencido]' + notificação interna (e e-mail, se habilitado) ao
        responsável do caso + audit log. Idempotente: o job só varre
        status='ativo', então o workflow marcado não é re-notificado.
      - VÉSPERA (1 dia útil antes), se acao_automatica da etapa for
        'alerta_prazo' ou 'notificar' → notificação antecipada. Idempotente
        via marcador '[alerta_sla]' no WorkflowHistorico (checado antes de
        repetir; sem coluna nova). Marcadores têm concluido_em preenchido
        para não colidir com a query de "etapa aberta" do /avancar.
    """
    from datetime import datetime, timezone as _tz
    from app.core.database import AsyncSessionLocal
    from app.models.case import Case
    from app.models.workflow import (
        CaseWorkflow, WorkflowEtapa, WorkflowHistorico, WorkflowStatus,
    )
    from app.modules.auditoria.middleware import registrar_acao
    from app.services.deadline_calculator import dia_util_anterior, prazo_dias_uteis
    from app.services.notification_service import criar_notificacao_interna, enviar_email

    async def _notificar_responsavel(db, resp_id, case_id, titulo, msg):
        if not resp_id:
            return
        await criar_notificacao_interna(
            db, resp_id, titulo, msg, tipo="workflow", link=f"/casos/{case_id}",
        )
        email = (await db.execute(
            text("SELECT email FROM users WHERE id=:i AND is_active=true"),
            {"i": resp_id},
        )).scalar()
        if email:
            await enviar_email(email, f"[EJC] {titulo}", f"<p>{msg}</p>")

    try:
        async with AsyncSessionLocal() as db:
            hoje = date.today()
            agora = datetime.now(_tz.utc)
            cws = (await db.execute(select(CaseWorkflow).where(
                CaseWorkflow.status == WorkflowStatus.ativo,
                CaseWorkflow.etapa_atual_id.isnot(None),
            ))).scalars().all()

            vencidos = alertas = 0
            for cw in cws:
                etapa = (await db.execute(select(WorkflowEtapa).where(
                    WorkflowEtapa.id == cw.etapa_atual_id
                ))).scalar_one_or_none()
                if not etapa or not etapa.sla_dias_uteis:
                    continue

                # Entrada na etapa atual = histórico ABERTO mais recente
                entrada = (await db.execute(
                    select(WorkflowHistorico).where(
                        WorkflowHistorico.case_workflow_id == cw.id,
                        WorkflowHistorico.etapa_id == etapa.id,
                        WorkflowHistorico.concluido_em.is_(None),
                    ).order_by(WorkflowHistorico.iniciado_em.desc())
                )).scalars().first()
                inicio = entrada.iniciado_em if entrada else cw.iniciado_em
                if inicio is None:
                    continue
                vencimento = prazo_dias_uteis(inicio.date(), etapa.sla_dias_uteis)

                case = (await db.execute(select(Case).where(
                    Case.id == cw.case_id
                ))).scalar_one_or_none()
                resp_id = case.advogado_responsavel_id if case else None
                ref_caso = (getattr(case, "numero_interno", None)
                            or getattr(case, "titulo", None) or cw.case_id)

                if hoje > vencimento:
                    # ── SLA estourado ────────────────────────────────────
                    cw.status = WorkflowStatus.atrasado
                    db.add(WorkflowHistorico(
                        id=str(uuid4()), case_workflow_id=cw.id,
                        etapa_id=etapa.id, responsavel_id=resp_id,
                        concluido_em=agora, sla_respeitado=False,
                        observacao=(
                            f"[sla_vencido] Etapa '{etapa.nome}' venceu em "
                            f"{vencimento.strftime('%d/%m/%Y')} "
                            f"(SLA de {etapa.sla_dias_uteis} dia(s) útil(eis))."
                        ),
                    ))
                    await db.commit()
                    await _notificar_responsavel(
                        db, resp_id, cw.case_id,
                        "⚠️ Etapa de workflow ATRASADA",
                        f"Caso {ref_caso}: a etapa '{etapa.nome}' venceu em "
                        f"{vencimento.strftime('%d/%m/%Y')} "
                        f"(SLA {etapa.sla_dias_uteis} dia(s) útil(eis)).",
                    )
                    await registrar_acao(
                        db, None, "sla_vencido", "workflow", cw.id,
                        f"Workflow do caso {cw.case_id} marcado 'atrasado' — "
                        f"etapa '{etapa.nome}' venceu "
                        f"{vencimento.strftime('%d/%m/%Y')}",
                    )
                    vencidos += 1

                elif (etapa.acao_automatica or "") in ("alerta_prazo", "notificar"):
                    # ── Véspera: 1 dia útil antes do vencimento ──────────
                    alerta_em = dia_util_anterior(vencimento - timedelta(days=1))
                    if not (alerta_em <= hoje <= vencimento):
                        continue
                    ja_alertado = (await db.execute(
                        select(WorkflowHistorico.id).where(
                            WorkflowHistorico.case_workflow_id == cw.id,
                            WorkflowHistorico.etapa_id == etapa.id,
                            WorkflowHistorico.observacao.like("[alerta_sla]%"),
                            WorkflowHistorico.iniciado_em >= inicio,
                        ).limit(1)
                    )).scalar_one_or_none()
                    if ja_alertado:
                        continue
                    db.add(WorkflowHistorico(
                        id=str(uuid4()), case_workflow_id=cw.id,
                        etapa_id=etapa.id, responsavel_id=resp_id,
                        concluido_em=agora,
                        observacao=(
                            f"[alerta_sla] Véspera do SLA da etapa "
                            f"'{etapa.nome}' — vence em "
                            f"{vencimento.strftime('%d/%m/%Y')}."
                        ),
                    ))
                    await db.commit()
                    await _notificar_responsavel(
                        db, resp_id, cw.case_id,
                        "⏰ Etapa de workflow vence amanhã (dia útil)",
                        f"Caso {ref_caso}: a etapa '{etapa.nome}' vence em "
                        f"{vencimento.strftime('%d/%m/%Y')}.",
                    )
                    alertas += 1

            logger.info(
                f"[Workflow SLA] {len(cws)} workflow(s) ativos verificados — "
                f"{vencidos} atrasado(s), {alertas} alerta(s) de véspera"
            )
    except Exception as e:
        logger.error(f"[Scheduler] workflow_sla: {e}", exc_info=True)


async def _alertar_honorarios():
    """Marca como 'atrasado' honorários vencidos."""
    from app.core.database import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("""
                UPDATE fees SET status='atrasado'
                WHERE status='pendente' AND deleted_at IS NULL
                AND data_vencimento < CURRENT_DATE
            """))
            await db.commit()
    except Exception as e:
        logger.error(f"[Scheduler] honorarios: {e}")


async def _regua_cobranca():
    """08h15 — Régua de cobrança escalonada de honorários vencidos (#3).

    Reutiliza inadimplencia_service.varrer_inadimplencia() para recalcular os
    níveis (leve<30 → medio 30-59 → critico 60-89 → cobranca_formal ≥90) e
    popular/atualizar inadimplencia_alerts. Em seguida, para cada alerta NÃO
    resolvido, dispara notificação escalonada ao advogado responsável pelo
    caso do honorário:
      - leve            → apenas sino interno
      - medio           → sino + e-mail (se habilitado)
      - critico/formal  → sino + e-mail + WhatsApp (se habilitados)

    Idempotência sem coluna nova: usa inadimplencia_alerts.action_taken como
    marcador 'regua:<nivel>'. Só (re)notifica quando o nível muda ou ainda não
    houve notificação — evita spam diário no mesmo nível.
    """
    from app.core.database import AsyncSessionLocal
    from app.services.inadimplencia_service import varrer_inadimplencia
    from app.services.notification_service import (
        criar_notificacao_interna, enviar_email, enviar_whatsapp, enviar_push,
    )
    try:
        async with AsyncSessionLocal() as db:
            # 1) Recalcula níveis e sincroniza a tabela de alertas (não reimplementar).
            resumo = await varrer_inadimplencia(db)

            # 2) Alertas abertos + advogado responsável do caso.
            rows = (await db.execute(text("""
                SELECT a.id, a.fee_id, a.days_overdue, a.amount_due,
                       a.alert_level, a.action_taken,
                       cl.nome AS cliente_nome,
                       c.numero_interno AS caso_num,
                       c.advogado_responsavel_id AS adv_id,
                       u.email AS adv_email, u.phone AS adv_phone
                FROM inadimplencia_alerts a
                LEFT JOIN cases   c  ON c.id  = a.case_id
                LEFT JOIN clients cl ON cl.id = a.client_id
                LEFT JOIN users   u  ON u.id  = c.advogado_responsavel_id
                WHERE a.resolved = FALSE
                ORDER BY a.days_overdue DESC
                LIMIT 500
            """))).all()

            notificados = 0
            for r in rows:
                if not r.adv_id:
                    continue  # sem responsável a quem escalar
                marcador = f"regua:{r.alert_level}"
                if (r.action_taken or "") == marcador:
                    continue  # já notificado neste nível — evita spam diário

                nome = r.cliente_nome or "Cliente"
                caso = r.caso_num or "—"
                valor = float(r.amount_due or 0)
                dias = int(r.days_overdue or 0)
                titulo = f"💰 Honorário vencido ({dias}d) — {r.alert_level}"
                corpo = (
                    f"{nome} (caso {caso}): R$ {valor:,.2f} em atraso há "
                    f"{dias} dia(s). Nível de cobrança: {r.alert_level}."
                )

                # Sino interno — sempre (todos os níveis)
                await criar_notificacao_interna(
                    db, r.adv_id, titulo, corpo,
                    tipo="financeiro", link="/financeiro",
                )
                await enviar_push(
                    db, r.adv_id, titulo, corpo, link="/financeiro",
                )
                # E-mail — a partir de 'medio'
                if r.alert_level in ("medio", "critico", "cobranca_formal") and r.adv_email:
                    await enviar_email(
                        r.adv_email,
                        f"[EJC] Cobrança {r.alert_level}: {nome} ({dias}d)",
                        f"<p>O honorário de <b>{nome}</b> (caso {caso}) está "
                        f"<b>{dias} dia(s)</b> em atraso — R$ {valor:,.2f}.</p>"
                        f"<p>Nível de cobrança: <b>{r.alert_level}</b>. "
                        f"Acione a régua de cobrança no EJC.</p>",
                    )
                # WhatsApp — apenas níveis mais graves
                if r.alert_level in ("critico", "cobranca_formal") and r.adv_phone:
                    await enviar_whatsapp(
                        r.adv_phone,
                        f"💰 *EJC* — Honorário de {nome} (caso {caso}) "
                        f"{dias}d em atraso (R$ {valor:,.2f}). "
                        f"Nível: {r.alert_level}.",
                    )

                # Marca o nível notificado (sem coluna nova)
                await db.execute(text(
                    "UPDATE inadimplencia_alerts SET action_taken=:m, updated_at=NOW() "
                    "WHERE id=:id"
                ), {"m": marcador, "id": r.id})
                notificados += 1

            await db.commit()
            logger.info(
                f"[Régua] varridas={resumo.get('varridas')} "
                f"alertas={len(rows)} notificados={notificados}"
            )
    except Exception as e:
        logger.error(f"[Scheduler] regua_cobranca: {e}", exc_info=True)


async def _alertar_vencimento_societario():
    """09h15 — Alertas de vencimento societário (#7).

    (a) ContratoSocietario com data_fim se aproximando: notifica o criador do
        contrato (sino) em marcos discretos — 30/15/7/1 dia(s) antes do fim —
        para não repetir diariamente (não há coluna de flag/dedup no model).
        Model app/models/contrato_societario.py: campo de data usado = data_fim
        (Date); considera também renovacao_automatica na mensagem.
    (b) DistribuicaoLucro 'agendada' (status='aprovado', aguardando pagamento)
        aprovada nas últimas 24h: notifica o aprovador/criador (sino). O model
        socio.py NÃO possui data de vencimento própria — usa-se aprovado_em como
        gatilho e mes_referencia como rótulo.
    """
    from app.core.database import AsyncSessionLocal
    from app.services.notification_service import criar_notificacao_interna
    try:
        async with AsyncSessionLocal() as db:
            hoje = date.today()

            # (a) Contratos societários vencendo — marcos 30/15/7/1
            contratos = (await db.execute(text("""
                SELECT c.id, c.titulo, c.data_fim, c.renovacao_automatica,
                       c.created_by
                FROM contratos_societarios c
                WHERE c.deleted_at IS NULL
                  AND c.status IN ('vigente','assinado','aprovado')
                  AND c.data_fim IS NOT NULL
                  AND c.data_fim >= :hoje
                  AND c.data_fim <= :lim
            """), {"hoje": hoje, "lim": hoje + timedelta(days=30)})).all()

            notif_c = 0
            for c in contratos:
                dias = (c.data_fim - hoje).days
                if dias not in (30, 15, 7, 1):
                    continue  # só marcos discretos — evita repetição diária
                if not c.created_by:
                    continue
                sufixo = (" · renovação automática" if c.renovacao_automatica
                          else " · SEM renovação automática")
                await criar_notificacao_interna(
                    db, c.created_by,
                    "📄 Contrato societário vencendo",
                    f"\"{c.titulo[:80]}\" encerra em {dias} dia(s) "
                    f"({c.data_fim.strftime('%d/%m/%Y')}){sufixo}.",
                    tipo="societario", link="/sociedade",
                )
                notif_c += 1

            # (b) Distribuições de lucro agendadas (aprovadas nas últimas 24h)
            distros = (await db.execute(text("""
                SELECT d.id, d.mes_referencia, d.valor_total,
                       d.aprovado_por, d.created_by, d.aprovado_em
                FROM distribuicoes_lucro d
                WHERE d.status = 'aprovado'
                  AND d.aprovado_em IS NOT NULL
                  AND d.aprovado_em >= NOW() - INTERVAL '1 day'
            """))).all()

            notif_d = 0
            for d in distros:
                destino = d.aprovado_por or d.created_by
                if not destino:
                    continue
                valor = float(d.valor_total or 0)
                await criar_notificacao_interna(
                    db, destino,
                    "💵 Distribuição de lucros agendada",
                    f"Distribuição {d.mes_referencia} aprovada — "
                    f"R$ {valor:,.2f} aguardando pagamento.",
                    tipo="societario", link="/sociedade",
                )
                notif_d += 1

            await db.commit()
            logger.info(
                f"[Societário] contratos_notif={notif_c} distribuicoes_notif={notif_d}"
            )
    except Exception as e:
        logger.error(f"[Scheduler] vencimento_societario: {e}", exc_info=True)


async def _briefing_matinal_advogado():
    """06h55 — Briefing matinal PERSONALIZADO por advogado (#11), antes do
    Morning Brief genérico (07h00).

    Para cada usuário de equipe/gestão (superadmin, admin, socio, advogado,
    advogado_auxiliar), monta um resumo dos SEUS casos (advogado_responsavel_id):
      - prazos pendentes nos próximos 7 dias (deadlines dos seus casos);
      - pendências: tarefas em aberto (status a_fazer/fazendo) sob sua
        responsabilidade, com destaque de atrasadas;
      - índice de risco: nº de casos ativos classificados como 'alto'
        (Case.risco). Entrega via sino interno + e-mail (se habilitado).
    Só notifica quem tiver algum item — evita briefing vazio.
    """
    from app.core.database import AsyncSessionLocal
    from app.services.notification_service import (
        criar_notificacao_interna, enviar_email,
    )
    try:
        async with AsyncSessionLocal() as db:
            hoje = date.today()
            d7 = hoje + timedelta(days=7)

            advs = (await db.execute(text("""
                SELECT id, full_name, email FROM users
                WHERE is_active = true AND deleted_at IS NULL
                  AND role IN ('superadmin','admin','socio','advogado','advogado_auxiliar')
            """))).all()

            enviados = 0
            for adv in advs:
                # Prazos próximos (7d) dos casos do advogado
                prazos = (await db.execute(text("""
                    SELECT COUNT(*)
                    FROM deadlines dl
                    JOIN cases c ON c.id = dl.case_id
                    WHERE dl.status = 'pendente' AND dl.deleted_at IS NULL
                      AND c.deleted_at IS NULL
                      AND c.advogado_responsavel_id = :uid
                      AND dl.data_prazo BETWEEN :hoje AND :d7
                """), {"uid": adv.id, "hoje": hoje, "d7": d7})).scalar() or 0

                # Pendências: tarefas em aberto (total + atrasadas)
                tarefas = (await db.execute(text("""
                    SELECT
                      COUNT(*) FILTER (WHERE status IN ('a_fazer','fazendo')) AS pendentes,
                      COUNT(*) FILTER (
                        WHERE status IN ('a_fazer','fazendo')
                          AND data_limite IS NOT NULL AND data_limite < :hoje
                      ) AS atrasadas
                    FROM tasks
                    WHERE deleted_at IS NULL AND responsavel_id = :uid
                """), {"uid": adv.id, "hoje": hoje})).one()
                pendentes = tarefas.pendentes or 0
                atrasadas = tarefas.atrasadas or 0

                # Índice de risco: casos ativos de risco alto
                risco_alto = (await db.execute(text("""
                    SELECT COUNT(*) FROM cases
                    WHERE deleted_at IS NULL
                      AND advogado_responsavel_id = :uid
                      AND status NOT IN ('encerrado','arquivado')
                      AND risco = 'alto'
                """), {"uid": adv.id})).scalar() or 0

                if not (prazos or pendentes or risco_alto):
                    continue  # nada a reportar

                nome = (adv.full_name or "advogado").split()[0]
                resumo_txt = (
                    f"Bom dia, {nome}! Prazos (7d): {prazos} | "
                    f"Tarefas em aberto: {pendentes} (atrasadas: {atrasadas}) | "
                    f"Casos de risco alto: {risco_alto}"
                )
                await criar_notificacao_interna(
                    db, adv.id,
                    f"☀️ Seu briefing — {hoje.strftime('%d/%m/%Y')}",
                    resumo_txt, tipo="sistema", link="/",
                )
                if adv.email:
                    await enviar_email(
                        adv.email,
                        f"[EJC] Seu briefing de {hoje.strftime('%d/%m')}",
                        f"<h3>Bom dia, {nome}!</h3>"
                        f"<ul>"
                        f"<li><b>Prazos próximos (7 dias):</b> {prazos}</li>"
                        f"<li><b>Tarefas em aberto:</b> {pendentes} "
                        f"(atrasadas: {atrasadas})</li>"
                        f"<li><b>Casos de risco alto:</b> {risco_alto}</li>"
                        f"</ul>"
                        f"<p><a href='https://ejc.depaulateixeira.adv.br'>Acessar EJC</a></p>",
                    )
                enviados += 1

            await db.commit()
            logger.info(f"[Briefing/advogado] {enviados} briefing(s) personalizado(s)")
    except Exception as e:
        logger.error(f"[Scheduler] briefing_matinal_advogado: {e}", exc_info=True)


async def _backup_diario():
    """Backup automatizado do banco de dados (pg_dump) — Auditoria Item 80."""
    import os
    import subprocess
    from datetime import datetime
    try:
        hoje = datetime.now().strftime("%Y-%m-%d")
        # P1-3: usa BACKUP_DIR do config (antes /home/ubuntu/backups, inexistente
        # no container → backup silenciosamente perdido). pg_dump exige URL SÍNCRONA
        # (DATABASE_URL é +asyncpg e quebra o pg_dump).
        os.makedirs(settings.BACKUP_DIR, exist_ok=True)
        path = f"{settings.BACKUP_DIR}/ejc_db_{hoje}.sql"
        cmd = f"pg_dump {settings.DATABASE_URL_SYNC} > {path}"
        subprocess.run(cmd, shell=True, check=True)
        logger.info(f"[Backup] Diário concluído com sucesso: {path}")
    except Exception as e:
        logger.error(f"[Backup] Falha no backup diário: {e}")


async def _verificar_sincronia_datajud():
    """Alerta se processos estão há mais de 3 dias sem sincronizar — Auditoria Item 32."""
    from app.core.database import AsyncSessionLocal
    from app.services.notification_service import criar_notificacao_interna
    try:
        async with AsyncSessionLocal() as db:
            limite = datetime.now() - timedelta(days=3)
            rows = await db.execute(text("""
                SELECT id, numero_processo, advogado_responsavel_id FROM cases
                WHERE deleted_at IS NULL AND status NOT IN ('encerrado','arquivado')
                  AND (last_synced_at IS NULL OR last_synced_at < :lim)
                  AND numero_processo IS NOT NULL
            """), {"lim": limite})
            for r in rows:
                if r.advogado_responsavel_id:
                    await criar_notificacao_interna(
                        db, r.advogado_responsavel_id,
                        "⚠️ Sincronização Pendente",
                        f"O processo {r.numero_processo} está há mais de 3 dias sem atualização oficial.",
                        tipo="sistema", link=f"/casos/{r.id}"
                    )
            await db.commit()
    except Exception as e:
        logger.error(f"[Scheduler] Sincronia DataJud: {e}")



async def _alertar_procuracoes():
    """Procurações vencendo em 30 dias (semanal)."""
    from app.core.database import AsyncSessionLocal
    from app.services.notification_service import criar_notificacao_interna
    try:
        async with AsyncSessionLocal() as db:
            limite = date.today() + timedelta(days=30)
            rows = await db.execute(text("""
                SELECT p.id, cl.nome, cl.razao_social, cl.responsavel_id,
                       p.data_validade
                FROM procuracoes p
                JOIN clients cl ON cl.id = p.client_id
                WHERE p.revogada=false AND p.deleted_at IS NULL
                  AND p.alerta_30d_enviado=false
                  AND p.data_validade IS NOT NULL
                  AND p.data_validade <= :lim
            """), {"lim": limite})
            for r in rows:
                nome = r.nome or r.razao_social or "Cliente"
                if r.responsavel_id:
                    await criar_notificacao_interna(
                        db, r.responsavel_id,
                        "📜 Procuração vencendo",
                        f"{nome}: válida até "
                        f"{r.data_validade.strftime('%d/%m/%Y')}",
                        tipo="sistema", link="/clientes",
                    )
                await db.execute(text(
                    "UPDATE procuracoes SET alerta_30d_enviado=true WHERE id=:id"
                ), {"id": r.id})
            await db.commit()
    except Exception as e:
        logger.error(f"[Scheduler] procuracoes: {e}")


async def _purgar_dados_lgpd():
    """
    LGPD art. 16 — purga dados de clientes inativos sem contrato ativo
    após RETENCAO_CLIENTE_ANOS anos (default 5). Mantém casos e financeiro por
    obrigação fiscal (art. 195 CTN — 5 anos). Logueia tudo para auditoria.
    """
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import text as _t
    from app.core.database import AsyncSessionLocal
    anos = getattr(settings, "RETENCAO_CLIENTE_ANOS", 5)
    corte = datetime.now(timezone.utc) - timedelta(days=365 * anos)
    try:
        async with AsyncSessionLocal() as db:
            # Soft-delete de clientes sem casos ativos há mais de N anos
            r = await db.execute(_t("""
                UPDATE clients SET deleted_at = NOW()
                WHERE deleted_at IS NULL
                AND updated_at < :corte
                AND id NOT IN (
                    SELECT DISTINCT client_id FROM cases
                    WHERE deleted_at IS NULL AND status NOT IN ('encerrado','arquivado')
                )
            """), {"corte": corte})
            await db.commit()
            logger.info(f"[LGPD] {r.rowcount or 0} clientes inativos soft-deleted (>{anos} anos sem caso ativo)")
    except Exception as e:
        logger.error(f"[LGPD] purga falhou: {e}")


# ── Retenção de dados de IA (#90) — purga logs antigos (LGPD) ─────────────────
async def _purgar_logs_ia():
    """Remove ai_logs com mais de RETENCAO_IA_ANOS anos (default 2). Auditável via log."""
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import text as _t
    from app.core.database import AsyncSessionLocal
    anos = getattr(settings, "RETENCAO_IA_ANOS", 2)
    limite = datetime.now(timezone.utc) - timedelta(days=365 * anos)
    try:
        async with AsyncSessionLocal() as db:
            r = await db.execute(_t("DELETE FROM ai_logs WHERE created_at < :lim"),
                                 {"lim": limite})
            await db.commit()
            logger.info(f"[Retenção IA] {r.rowcount or 0} ai_logs > {anos} anos purgados")
    except Exception as e:
        logger.error(f"[Retenção IA] falha: {e}")


# ── Start/Stop ────────────────────────────────────────────────────────────────

def start_scheduler():
    """Inicia jobs APENAS se ENABLE_SCHEDULER=true (evita duplicação)."""
    if not settings.ENABLE_SCHEDULER:
        logger.info("[Scheduler] Desabilitado via ENABLE_SCHEDULER=false")
        return
    s = get_scheduler()
    if s.running:
        return

    s.add_job(_morning_brief,       CronTrigger(hour=7,  minute=0),  id="brief",       replace_existing=True)
    s.add_job(_alertar_prazos,      CronTrigger(hour=7,  minute=15), id="prazos",      replace_existing=True)
    s.add_job(_verificar_sla_workflows, CronTrigger(hour=7, minute=30), id="workflow_sla", replace_existing=True)
    s.add_job(_briefing_matinal_advogado, CronTrigger(hour=6, minute=55), id="briefing_adv", replace_existing=True)
    s.add_job(_alertar_honorarios,  CronTrigger(hour=8,  minute=0),  id="honorarios",  replace_existing=True)
    s.add_job(_regua_cobranca,      CronTrigger(hour=8,  minute=15), id="regua_cobranca", replace_existing=True)
    s.add_job(_alertar_ambiental,   CronTrigger(hour=8,  minute=30), id="ambiental",   replace_existing=True)
    s.add_job(_alertar_procuracoes, CronTrigger(day_of_week="mon", hour=9), id="procuracoes", replace_existing=True)
    s.add_job(_alertar_vencimento_societario, CronTrigger(hour=9, minute=15), id="societario", replace_existing=True)
    s.add_job(_alertar_prescricao,  CronTrigger(day_of_week="mon", hour=9, minute=5), id="prescricao", replace_existing=True)

    # Jobs v3.x — integrações oficiais (guardas internas pulam se não configurado)
    s.add_job(job_djen_intimacoes,  CronTrigger(hour=6,  minute=30), id="djen",        replace_existing=True)
    s.add_job(job_datajud_sync,     CronTrigger(hour="8,16", minute=45), id="datajud",  replace_existing=True)
    s.add_job(job_relatorio_mensal, CronTrigger(day=1,  hour=7, minute=30), id="relatorio_mensal", replace_existing=True)

    # Jobs de ingestão no RAG (Bloco B)
    s.add_job(job_ingestao_planalto, CronTrigger(day_of_week="sun", hour=3), id="ing_planalto", replace_existing=True)
    s.add_job(job_ingestao_stj,      CronTrigger(day_of_week="sat", hour=3), id="ing_stj",      replace_existing=True)
    s.add_job(_purgar_logs_ia,    CronTrigger(day_of_week="sun", hour=2),  id="purga_ia",   replace_existing=True)
    s.add_job(_purgar_dados_lgpd, CronTrigger(day_of_week="sun", hour=2, minute=30), id="purga_lgpd", replace_existing=True)
    s.add_job(job_ingestao_camara,   CronTrigger(hour=4, minute=0),          id="ing_camara",   replace_existing=True)
    s.add_job(job_ingestao_senado,   CronTrigger(hour=4, minute=20),         id="ing_senado",   replace_existing=True)

    # Recarrega feriados municipais/estaduais (00h05) — pega novas inserções
    # na tabela `feriados` sem precisar reiniciar o backend.
    s.add_job(_recarregar_feriados,   CronTrigger(hour=0, minute=5),  id="feriados",  replace_existing=True)
    s.add_job(_backup_banco,          CronTrigger(hour=2, minute=0),  id="backup",    replace_existing=True)
    s.add_job(_auditoria_processos,   CronTrigger(day_of_week="mon", hour=8, minute=15),  id="auditoria",  replace_existing=True)
    s.add_job(_monitor_diario_oficial, CronTrigger(hour=6, minute=0),                      id="dou_monitor", replace_existing=True)
    s.add_job(_alertar_contratos,     CronTrigger(day_of_week="mon", hour=9, minute=30),  id="contratos",  replace_existing=True)
    s.add_job(_purgar_logs_ia,        CronTrigger(day=1, hour=3, minute=30), id="retencao_ia", replace_existing=True)

    s.start()
    logger.info("[Scheduler] Iniciado — 24 jobs (+ briefing por advogado, régua de cobrança e alertas societários)")


async def _backup_banco():
    """
    02h00 — dump pg_dump do banco e upload offsite via rclone (se configurado).
    Roda dentro do container postgres (docker compose exec) via subprocess no HOST.
    Aqui, registramos o evento no log e verificamos se o dump do dia já existe.
    O backup efetivo é executado pelo script scripts/backup.sh no HOST via cron.
    """
    import os, glob as _glob
    from datetime import date as _date

    backup_dir = settings.BACKUP_DIR
    hoje = _date.today().strftime("%Y-%m-%d")
    padrao = os.path.join(backup_dir, f"ejc_backup_{hoje}*.sql.gz")
    arquivos = _glob.glob(padrao)

    if arquivos:
        logger.info(f"[Backup] Dump do dia {hoje} já existe: {arquivos[0]}")
        return

    # Backup do dia não encontrado — tentar pg_dump diretamente se disponível
    import subprocess, shutil
    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        logger.warning(
            "[Backup] pg_dump não encontrado no container backend. "
            "Configure cron no HOST: ver scripts/backup.sh"
        )
        return

    try:
        from urllib.parse import urlparse
        url = urlparse(settings.DATABASE_URL_SYNC)
        os.makedirs(backup_dir, exist_ok=True)
        destino = os.path.join(backup_dir, f"ejc_backup_{hoje}.sql.gz")
        env = {**os.environ, "PGPASSWORD": url.password or ""}
        cmd_dump = [
            pg_dump, "-h", url.hostname, "-p", str(url.port or 5432),
            "-U", url.username, "-d", url.path.lstrip("/"), "-Fc",
        ]
        with open(destino, "wb") as f:
            r = subprocess.run(cmd_dump, stdout=f, env=env, timeout=300)
        if r.returncode == 0:
            tamanho_mb = os.path.getsize(destino) / (1024 * 1024)
            logger.info(f"[Backup] Dump criado: {destino} ({tamanho_mb:.1f} MB)")
        else:
            logger.error(f"[Backup] pg_dump retornou código {r.returncode}")
            return

        # Upload offsite via rclone (se BACKUP_REMOTE configurado)
        if settings.BACKUP_REMOTE:
            rclone = shutil.which("rclone")
            if rclone:
                r2 = subprocess.run(
                    [rclone, "copy", destino, settings.BACKUP_REMOTE],
                    timeout=120,
                )
                if r2.returncode == 0:
                    logger.info(f"[Backup] Upload p/ {settings.BACKUP_REMOTE} OK")
                else:
                    logger.warning(f"[Backup] rclone upload falhou (código {r2.returncode})")

        # Rotação: remove dumps locais mais antigos que BACKUP_RETENTION_DAYS dias.
        try:
            import time as _time
            corte = _time.time() - (settings.BACKUP_RETENTION_DAYS * 86400)
            removidos = 0
            for caminho in _glob.glob(os.path.join(backup_dir, "ejc_backup_*.sql.gz")):
                try:
                    if os.path.getmtime(caminho) < corte:
                        os.remove(caminho)
                        removidos += 1
                except OSError:
                    continue
            if removidos:
                logger.info(
                    f"[Backup] Rotação: {removidos} dump(s) > "
                    f"{settings.BACKUP_RETENTION_DAYS}d removido(s)"
                )
        except Exception as e:
            logger.warning(f"[Backup] Rotação falhou (não-fatal): {e}")
    except Exception as e:
        logger.error(f"[Backup] Falha no backup: {e}")


async def _recarregar_feriados():
    """00h05 — recarrega o cache de feriados municipais/estaduais do banco."""
    from app.services.deadline_calculator import carregar_feriados_db, carregar_suspensoes_db
    n = await carregar_feriados_db()
    ns = await carregar_suspensoes_db()
    logger.info(f"[Scheduler] Feriados recarregados: {n} | Suspensões: {ns} dia(s)")


async def _monitor_diario_oficial():
    """06h00 — captura publicações do DOU que casam com as keywords cadastradas."""
    try:
        from app.services.diario_oficial_service import processar_alertas_dou
        async with AsyncSessionLocal() as db:
            novos = await processar_alertas_dou(db)
            logger.info(f"[DOU] Monitor concluído — {novos} novo(s) alerta(s)")
    except Exception as e:
        logger.error(f"[DOU] Falha no monitor: {e}")


async def _alertar_contratos():
    """Segunda-feira 09h30 — alerta contratos societários próximos do vencimento."""
    try:
        async with AsyncSessionLocal() as db:
            hoje = date.today()
            rows = (await db.execute(text("""
                SELECT c.id, c.titulo, c.data_fim, c.alertar_dias_antes
                FROM contratos_societarios c
                WHERE c.deleted_at IS NULL
                  AND c.status IN ('vigente', 'assinado')
                  AND c.data_fim IS NOT NULL
                  AND c.data_fim <= CURRENT_DATE + c.alertar_dias_antes * INTERVAL '1 day'
                  AND c.data_fim >= CURRENT_DATE
            """))).all()
            if rows:
                logger.warning(
                    f"[Contratos] {len(rows)} contrato(s) próximos do vencimento: "
                    + ", ".join(r.titulo[:30] for r in rows[:5])
                )
    except Exception as e:
        logger.error(f"[Contratos] Falha no alerta: {e}")


async def _auditoria_processos():
    """
    Segunda-feira 08h15 — detecta processos esquecidos e envia alertas internos.
    - Casos sem movimentação há 30+ dias
    - Casos com prazos vencidos sem tarefa associada
    - Clientes sem atendimento há 60+ dias
    - Honorários sem cobrança há 90+ dias
    """
    try:
        async with AsyncSessionLocal() as db:
            hoje = date.today()
            limite_30 = hoje - timedelta(days=30)
            limite_60 = hoje - timedelta(days=60)
            limite_90 = hoje - timedelta(days=90)

            # 1. Casos sem movimentação DataJud há 30+ dias
            rows_mov = (await db.execute(text("""
                SELECT c.id, c.titulo, c.numero_processo, u.email
                FROM cases c
                LEFT JOIN users u ON u.id = c.advogado_responsavel_id
                WHERE c.deleted_at IS NULL
                  AND c.status NOT IN ('encerrado','arquivado')
                  AND COALESCE(
                        (SELECT MAX(m.data_evento)::date FROM case_movimentos m WHERE m.case_id = c.id),
                        c.created_at::date
                      ) < :limite
                LIMIT 50
            """), {"limite": limite_30})).all()
            if rows_mov:
                logger.warning(
                    f"[Auditoria] {len(rows_mov)} caso(s) sem movimentação há 30+ dias: "
                    + ", ".join(r.numero_processo or r.id for r in rows_mov[:5])
                )

            # 2. Prazos vencidos ontem sem tarefa
            rows_prazos = (await db.execute(text("""
                SELECT d.id, d.titulo, d.case_id
                FROM deadlines d
                WHERE d.data_prazo < :hoje
                  AND d.status = 'pendente'
                  AND d.deleted_at IS NULL
                LIMIT 30
            """), {"hoje": hoje})).all()
            if rows_prazos:
                logger.warning(
                    f"[Auditoria] {len(rows_prazos)} prazo(s) VENCIDO(S) ainda 'pendente': "
                    + ", ".join(r.titulo for r in rows_prazos[:5])
                )

            # 3. Clientes sem atendimento registrado há 60+ dias
            try:
                rows_clientes = (await db.execute(text("""
                    -- _auditoria_clientes_fixed
                    SELECT cl.id, cl.nome
                    FROM clients cl
                    WHERE cl.deleted_at IS NULL
                      AND cl.status = 'ativo'
                      AND (
                          (SELECT MAX(a.data_atendimento) FROM atendimentos a WHERE a.client_id = cl.id) < :limite
                          OR (SELECT COUNT(*) FROM atendimentos a WHERE a.client_id = cl.id) = 0
                      )
                    LIMIT 30
                """), {"limite": limite_60})).all()
                if rows_clientes:
                    logger.info(
                        f"[Auditoria] {len(rows_clientes)} cliente(s) sem contato há 60+ dias"
                    )
            except Exception:
                pass  # tabela atendimentos pode não existir ainda (migration pendente)

            total_alertas = len(rows_mov) + len(rows_prazos)
            logger.info(f"[Auditoria] Concluída — {total_alertas} alerta(s) emitido(s)")
    except Exception as e:
        logger.error(f"[Auditoria] Falha: {e}")


def stop_scheduler():
    s = get_scheduler()
    if s.running:
        s.shutdown(wait=False)
        logger.info("[Scheduler] Encerrado.")


# ═══════════════════════════════════════════════════════════════════════════
# JOBS v3.x — DJEN, DataJud, Relatório Mensal
# ═══════════════════════════════════════════════════════════════════════════

async def job_djen_intimacoes():
    """06h30 — captura intimações DJEN para cada advogado com OAB configurada."""
    from app.models.user import User as _U
    from app.services.djen_service import capturar_para_advogado
    async with AsyncSessionLocal() as db:
        advs = (await db.execute(select(_U).where(
            _U.is_active == True, _U.deleted_at.is_(None),
            _U.djen_oab_numero.isnot(None),
        ))).scalars().all()
        total = 0
        for a in advs:
            try:
                total += await capturar_para_advogado(db, a)
            except Exception as e:
                logger.warning(f"DJEN {a.email}: {e}")
        await db.commit()
        logger.info(f"[DJEN] {total} intimação(ões) nova(s)")


async def job_datajud_sync():
    """08h45/16h45 — sincroniza movimentos oficiais dos casos ativos com nº CNJ."""
    from app.models.case import Case as _C
    from app.services.datajud_service import sincronizar_caso
    async with AsyncSessionLocal() as db:
        casos = (await db.execute(select(_C).where(
            _C.deleted_at.is_(None),
            _C.numero_processo.isnot(None),
            _C.status.in_(["ativo", "suspenso"]),
        ))).scalars().all()
        total = 0
        for c in casos[:80]:   # teto por execução (rate limit amigável)
            try:
                total += await sincronizar_caso(db, c)
            except Exception as e:
                logger.warning(f"DataJud {c.numero_interno}: {e}")
        await db.commit()
        logger.info(f"[DataJud] {total} movimento(s) novo(s)")


async def job_relatorio_mensal():
    """Dia 1, 07h30 — gera PDF do mês ANTERIOR e notifica sócios."""
    from datetime import date as _d
    from app.routers.dashboard import _coletar_dados_mes
    from app.services.pdf_service import relatorio_mensal_pdf
    from app.models.user import User as _U, UserRole as _R
    from app.models.notification import Notification as _N
    import os
    hoje = _d.today()
    mes = hoje.month - 1 or 12
    ano = hoje.year if hoje.month > 1 else hoje.year - 1

    async with AsyncSessionLocal() as db:
        dados = await _coletar_dados_mes(db, mes, ano)
        try:
            pdf = relatorio_mensal_pdf(mes, ano, dados)
            destino = f"{settings.UPLOAD_DIR}/relatorios"
            os.makedirs(destino, exist_ok=True)
            caminho = f"{destino}/relatorio_{ano}_{mes:02d}.pdf"
            with open(caminho, "wb") as f:
                f.write(pdf)
        except Exception as e:
            logger.error(f"Relatório mensal: {e}")
            return

        socios = (await db.execute(select(_U).where(
            _U.role.in_([_R.superadmin, _R.admin, _R.socio]),
            _U.is_active == True,
        ))).scalars().all()
        for s in socios:
            db.add(_N(
                id=str(uuid4()), user_id=s.id,
                titulo=f"📊 Relatório mensal {mes:02d}/{ano} disponível",
                mensagem="PDF gerencial gerado automaticamente.",
                tipo="relatorio", link="/",
            ))
        await db.commit()
        logger.info(f"[Relatório] {mes:02d}/{ano} gerado e notificado")


# ═══════════════════════════════════════════════════════════════════════════
# JOBS DE INGESTÃO NO RAG (Bloco B) — alimentam a base de conhecimento
# ═══════════════════════════════════════════════════════════════════════════

async def job_ingestao_planalto():
    """Domingo 03h00 — (re)ingere os códigos-núcleo federais no RAG.

    Idempotente: só re-embeda diplomas cujo texto mudou (alteração legislativa).
    """
    from app.services.ingestion_service import executar_ingestao
    from app.services.ingestors import planalto
    await executar_ingestao(
        "planalto", "Códigos-núcleo federais (Planalto)", "legislacao",
        planalto.ingerir,
    )


async def job_ingestao_stj():
    """Sábado 03h00 — ingere o lote mensal mais recente de acórdãos do STJ."""
    from app.services.ingestion_service import executar_ingestao
    from app.services.ingestors import stj
    await executar_ingestao(
        "stj", "Jurisprudência STJ (espelhos de acórdãos)", "jurisprudencia",
        stj.ingerir,
    )


async def job_ingestao_camara():
    """Diário 04h00 — monitor legislativo: ementas de proposições recentes."""
    from app.services.ingestion_service import executar_ingestao
    from app.services.ingestors import camara
    await executar_ingestao(
        "camara", "Monitor legislativo (Câmara dos Deputados)",
        "proposicao_legislativa", camara.ingerir,
    )


async def job_ingestao_senado():
    """Diário 04h20 — monitor legislativo: ementas de matérias do Senado."""
    from app.services.ingestion_service import executar_ingestao
    from app.services.ingestors import senado
    await executar_ingestao(
        "senado", "Monitor legislativo (Senado Federal)",
        "proposicao_legislativa", senado.ingerir,
    )
