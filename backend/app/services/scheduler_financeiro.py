"""Estabilização dos jobs financeiros do scheduler.

Este módulo substitui SOMENTE os callbacks financeiros legados antes de o
APScheduler iniciar. Mantém horários/IDs já existentes em scheduler.py e evita
uma refatoração ampla do scheduler central durante a auditoria do Financeiro.

Objetivos:
- Morning Brief usa saldo residual (FeePayment), não valor contratado bruto;
- honorário só vira atrasado se ainda houver obrigação aberta;
- transição automática pendente -> atrasado deixa trilha de auditoria;
- nenhuma PII financeira adicional é registrada em log/auditoria.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import text

from app.core.database import AsyncSessionLocal

logger = logging.getLogger("ejc.scheduler_financeiro")


def instalar() -> None:
    """Instala os callbacks estabilizados antes de ``start_scheduler()``.

    ``main.py`` importa ``event_subscribers`` antes do lifespan. O
    ``start_scheduler`` já importado continua consultando os globais do módulo
    ``scheduler`` no momento em que registra os jobs, portanto esta substituição
    é determinística e não altera IDs/horários do APScheduler.
    """
    from app.services import scheduler

    scheduler._morning_brief = _morning_brief_financeiro
    scheduler._alertar_honorarios = _marcar_honorarios_atrasados
    logger.info("Jobs financeiros do scheduler estabilizados")


async def _saldo_vencido(db, hoje: date) -> tuple[int, float, int]:
    """Retorna quantidade, saldo monetário vencido e percentuais sem base."""
    row = (
        await db.execute(
            text(
                """
                WITH pagos AS (
                    SELECT fee_id, COALESCE(SUM(valor), 0) AS total_pago
                    FROM fee_payments
                    GROUP BY fee_id
                ), abertos AS (
                    SELECT
                        f.id,
                        f.valor,
                        f.percentual_exito,
                        GREATEST(
                            COALESCE(f.valor, 0) - COALESCE(p.total_pago, 0),
                            0
                        ) AS saldo
                    FROM fees f
                    LEFT JOIN pagos p ON p.fee_id = f.id
                    WHERE f.deleted_at IS NULL
                      AND CAST(f.status AS text) IN ('pendente','atrasado')
                      AND f.data_vencimento < :hoje
                )
                SELECT
                    COUNT(*) FILTER (WHERE valor IS NOT NULL AND saldo > 0) AS qtd,
                    COALESCE(SUM(saldo) FILTER (
                        WHERE valor IS NOT NULL AND saldo > 0
                    ), 0) AS total,
                    COUNT(*) FILTER (
                        WHERE valor IS NULL AND percentual_exito IS NOT NULL
                    ) AS percentuais_sem_base
                FROM abertos
                """
            ),
            {"hoje": hoje},
        )
    ).one()
    return int(row.qtd or 0), float(row.total or 0), int(row.percentuais_sem_base or 0)


async def _morning_brief_financeiro() -> None:
    """Briefing diário preservando o fluxo legado, com ledger financeiro real."""
    try:
        async with AsyncSessionLocal() as db:
            hoje = date.today()
            d3 = hoje + timedelta(days=3)
            d7 = hoje + timedelta(days=7)

            prazos_3d = (
                await db.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM deadlines
                        WHERE status='pendente' AND deleted_at IS NULL
                          AND data_prazo BETWEEN :hoje AND :d3
                        """
                    ),
                    {"hoje": hoje, "d3": d3},
                )
            ).scalar() or 0

            prazos_7d = (
                await db.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM deadlines
                        WHERE status='pendente' AND deleted_at IS NULL
                          AND data_prazo BETWEEN :hoje AND :d7
                        """
                    ),
                    {"hoje": hoje, "d7": d7},
                )
            ).scalar() or 0

            hon_qtd, hon_valor, percentuais_sem_base = await _saldo_vencido(db, hoje)

            amb_criticas = (
                await db.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM environmental_cases
                        WHERE status_defesa IN ('prazo_correndo','elaborando')
                          AND deleted_at IS NULL
                          AND data_prazo_defesa <= :d5
                        """
                    ),
                    {"d5": hoje + timedelta(days=5)},
                )
            ).scalar() or 0

            admin_row = (
                await db.execute(
                    text(
                        """
                        SELECT id, email FROM users
                        WHERE role IN ('superadmin','admin') AND is_active=true
                          AND email IS NOT NULL LIMIT 1
                        """
                    )
                )
            ).first()

        percentual_txt = (
            f" | Percentuais sem base: {percentuais_sem_base}"
            if percentuais_sem_base
            else ""
        )
        msg_txt = (
            f"Morning Brief {hoje.strftime('%d/%m/%Y')}\n"
            f"Prazos fatais (3d): {prazos_3d} | "
            f"Prazos 7d: {prazos_7d} | "
            f"Honor. vencidos: {hon_qtd} (saldo R$ {hon_valor:,.2f})"
            f"{percentual_txt} | IBAMA <=5d: {amb_criticas}"
        )
        msg_html = (
            f"<h3>EJC — Morning Brief {hoje.strftime('%d/%m/%Y')}</h3>"
            f"<ul>"
            f"<li><b>Prazos fatais (3 dias):</b> {prazos_3d}</li>"
            f"<li><b>Prazos 7 dias:</b> {prazos_7d}</li>"
            f"<li><b>Honorários vencidos:</b> {hon_qtd} "
            f"(saldo R$ {hon_valor:,.2f})</li>"
            + (
                f"<li><b>Honorários percentuais sem base monetária:</b> "
                f"{percentuais_sem_base}</li>"
                if percentuais_sem_base
                else ""
            )
            + f"<li><b>Defesas IBAMA ≤5 dias:</b> {amb_criticas}</li>"
            f"</ul><p><a href='https://ejc.depaulateixeira.adv.br'>Acessar EJC</a></p>"
        )

        if admin_row:
            from app.services.notification_service import notificar

            async with AsyncSessionLocal() as db2:
                try:
                    await notificar(
                        db2,
                        admin_row.id,
                        f"Morning Brief {hoje.strftime('%d/%m/%Y')}",
                        msg_txt,
                        tipo="sistema",
                        link="/",
                        email=admin_row.email or None,
                        email_assunto=f"[EJC] Morning Brief {hoje.strftime('%d/%m')}",
                        email_corpo=msg_html,
                    )
                except Exception as exc:
                    logger.warning("Morning Brief: notificação falhou: %s", exc)

        logger.info(
            "Morning Brief financeiro: prazos_3d=%s honorarios_vencidos=%s "
            "percentuais_sem_base=%s",
            prazos_3d,
            hon_qtd,
            percentuais_sem_base,
        )
    except Exception as exc:
        logger.error("Morning Brief financeiro falhou: %s", exc, exc_info=True)


async def _marcar_honorarios_atrasados() -> None:
    """Transição automática auditada de honorários ainda efetivamente abertos."""
    from app.modules.auditoria.middleware import registrar_acao

    try:
        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    text(
                        """
                        WITH pagos AS (
                            SELECT fee_id, COALESCE(SUM(valor), 0) AS total_pago
                            FROM fee_payments
                            GROUP BY fee_id
                        )
                        SELECT f.id, f.data_vencimento
                        FROM fees f
                        LEFT JOIN pagos p ON p.fee_id = f.id
                        WHERE f.deleted_at IS NULL
                          AND CAST(f.status AS text) = 'pendente'
                          AND f.data_vencimento < CURRENT_DATE
                          AND (
                              f.valor IS NULL
                              OR GREATEST(
                                  f.valor - COALESCE(p.total_pago, 0), 0
                              ) > 0
                          )
                        ORDER BY f.data_vencimento, f.id
                        LIMIT 2000
                        """
                    )
                )
            ).all()

            alterados = 0
            for row in rows:
                try:
                    result = await db.execute(
                        text(
                            """
                            UPDATE fees
                               SET status='atrasado', updated_at=NOW()
                             WHERE id=:id
                               AND CAST(status AS text)='pendente'
                               AND deleted_at IS NULL
                            """
                        ),
                        {"id": row.id},
                    )
                    if not (result.rowcount or 0):
                        await db.rollback()
                        continue
                    await db.commit()
                    await registrar_acao(
                        db,
                        None,
                        "status_atrasado_automatico",
                        "fees",
                        row.id,
                        "Honorário marcado automaticamente como atrasado após vencimento; saldo ainda aberto.",
                        dados_antes={"status": "pendente"},
                        dados_depois={"status": "atrasado"},
                    )
                    alterados += 1
                except Exception as exc:
                    await db.rollback()
                    logger.error(
                        "Falha ao marcar honorário %s como atrasado: %s",
                        getattr(row, "id", "?"),
                        exc,
                    )

            logger.info("Honorários marcados como atrasados: %s", alterados)
    except Exception as exc:
        logger.error("Job de atraso de honorários falhou: %s", exc, exc_info=True)
