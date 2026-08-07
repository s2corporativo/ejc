# ── app/services/relatorio_dono_service.py ───────────────────────────────────
# Relatório SEMANAL do dono — segunda-feira, e-mail + sino aos sócios/admins.
#
# 5 indicadores da semana (coletar_numeros_semana — função testável com fakes):
#   (a) prazos_vencendo_7d       — deadlines pendentes vencendo em até 7 dias
#   (b) leads_convertidos_semana — leads que viraram clientes com caso na semana
#   (c) recebiveis_atraso_reais  — honorários vencidos em aberto (R$, líquido
#                                  de pagamentos parciais)
#   (d) custo_ia_semana          — custo estimado de IA (R$) + top casos
#   (e) casos_parados_30d        — casos ativos sem movimentação há 30+ dias
#
# Gate interno RELATORIO_DONO_ENABLED (default False — opt-in). Template do
# e-mail DETERMINÍSTICO (sem IA), sóbrio, tabela única com os 5 indicadores.
# Canais: e-mail + sino APENAS (WhatsApp fora de escopo).
from __future__ import annotations

import html
import logging
from datetime import date, timedelta

from sqlalchemy import text as sqltext
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

logger = logging.getLogger("ejc.relatorio_dono")
settings = get_settings()

ASSINATURA_AUTOMATICA = (
    "De Paula Teixeira Advogados — mensagem automática, "
    "não responda este e-mail."
)

# Guard de processo (padrão backup_service): um relatório por vez.
_em_execucao = False


# ── Coleta (testável com FakeDB — cada query nomeia a tabela-alvo) ────────────

async def coletar_numeros_semana(db: AsyncSession, hoje: date) -> dict:
    """Coleta os 5 números da semana (janela: últimos 7 dias p/ retrospectivos;
    próximos 7 p/ prazos). Retorna dict pronto para o template.

    Critérios documentados:
      (b) leads_convertidos_semana — o funil do EJC deriva conversão do STATUS
          ATUAL do cliente (lead → ativo, ver services/funil.py); NÃO existe
          timestamp de conversão nem marcador lead→caso persistido. Critério
          mais fiel disponível: clientes ATIVOS (não deletados) cujo PRIMEIRO
          caso foi criado nos últimos 7 dias — captura o momento em que o
          contato virou cliente com caso aberto.
      (c) recebiveis_atraso_reais — SUM(fees.valor) de parcelas pendente/
          atrasado vencidas, LÍQUIDO de fee_payments (pagamentos parciais
          descontados por subquery; nunca negativo por parcela).
      (d) custo_ia_semana — ai_logs.custo_estimado (R$; 0/NULL quando não
          apurado) somado na semana + nº de chamadas + top 5 casos por custo.
      (e) casos_parados_30d — mesma regra da auditoria semanal
          (scheduler._auditoria_processos): casos ativos cuja última
          case_movimentos.data_evento (fallback created_at do caso) < hoje-30.
    """
    d7 = hoje + timedelta(days=7)
    corte_semana = hoje - timedelta(days=7)
    corte_30 = hoje - timedelta(days=30)

    # (a) prazos pendentes vencendo nos próximos 7 dias
    prazos_7d = (await db.execute(sqltext("""
        SELECT COUNT(*) FROM deadlines
        WHERE status = 'pendente' AND deleted_at IS NULL
          AND data_prazo BETWEEN :hoje AND :d7
    """), {"hoje": hoje, "d7": d7})).scalar() or 0

    # (b) leads convertidos na semana (ver docstring)
    leads_convertidos = (await db.execute(sqltext("""
        SELECT COUNT(*) FROM clients cl
        WHERE cl.deleted_at IS NULL AND cl.status = 'ativo'
          AND (
            SELECT MIN(c.created_at)::date FROM cases c
            WHERE c.client_id = cl.id AND c.deleted_at IS NULL
          ) >= :corte
    """), {"corte": corte_semana})).scalar() or 0

    # (c) recebíveis em atraso (R$, líquido de pagamentos parciais)
    recebiveis_atraso = (await db.execute(sqltext("""
        SELECT COALESCE(SUM(GREATEST(f.valor - COALESCE(p.pago, 0), 0)), 0)
        FROM fees f
        LEFT JOIN (
            SELECT fee_id, SUM(valor) AS pago
            FROM fee_payments GROUP BY fee_id
        ) p ON p.fee_id = f.id
        WHERE f.status IN ('pendente', 'atrasado')
          AND f.deleted_at IS NULL
          AND f.valor IS NOT NULL
          AND f.data_vencimento IS NOT NULL
          AND f.data_vencimento < :hoje
    """), {"hoje": hoje})).scalar() or 0

    # (d) custo de IA na semana (R$) + chamadas + top 5 casos por custo
    row_ia = (await db.execute(sqltext("""
        SELECT COALESCE(SUM(custo_estimado), 0) AS custo, COUNT(*) AS chamadas
        FROM ai_logs
        WHERE created_at >= :corte
    """), {"corte": corte_semana})).first()
    custo_ia = float(row_ia.custo if row_ia else 0) or 0.0
    chamadas_ia = int(row_ia.chamadas if row_ia else 0) or 0

    top_ia = (await db.execute(sqltext("""
        SELECT c.numero_interno, c.titulo,
               COALESCE(SUM(l.custo_estimado), 0) AS custo,
               COUNT(*) AS chamadas
        FROM ai_logs l
        JOIN cases c ON c.id = l.case_id
        WHERE l.created_at >= :corte AND l.case_id IS NOT NULL
        GROUP BY c.numero_interno, c.titulo
        ORDER BY custo DESC, chamadas DESC
        LIMIT 5
    """), {"corte": corte_semana})).all()

    # (e) casos ativos parados há 30+ dias (regra da _auditoria_processos)
    casos_parados = (await db.execute(sqltext("""
        SELECT COUNT(*) FROM cases c
        WHERE c.deleted_at IS NULL
          AND c.status NOT IN ('encerrado', 'arquivado')
          AND COALESCE(
                (SELECT MAX(m.data_evento)::date FROM case_movimentos m
                 WHERE m.case_id = c.id),
                c.created_at::date
              ) < :corte
    """), {"corte": corte_30})).scalar() or 0

    return {
        "prazos_vencendo_7d": int(prazos_7d),
        "leads_convertidos_semana": int(leads_convertidos),
        "recebiveis_atraso_reais": float(recebiveis_atraso),
        "custo_ia_semana": custo_ia,
        "chamadas_ia_semana": chamadas_ia,
        "top_casos_ia": [
            {
                "caso": r.numero_interno or (r.titulo or "")[:60],
                "custo": float(r.custo or 0),
                "chamadas": int(r.chamadas or 0),
            }
            for r in top_ia
        ],
        "casos_parados_30d": int(casos_parados),
    }


# ── Template determinístico ───────────────────────────────────────────────────

def _brl(valor: float) -> str:
    """Formata R$ no padrão brasileiro (1.234,56)."""
    txt = f"{valor:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return f"R$ {txt}"


def montar_email_relatorio(
    numeros: dict, inicio: date, fim: date,
) -> tuple[str, str]:
    """Template DETERMINÍSTICO (sem IA) do relatório semanal do dono.

    Retorna (assunto, corpo_html): tabela única com os 5 indicadores +
    detalhe dos top casos por custo de IA (quando houver). Sem emojis;
    assinatura de comunicação automática."""
    periodo = f"{inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}"
    assunto = f"Relatório semanal — De Paula Teixeira Advogados ({periodo})"

    linhas = [
        ("Prazos vencendo nos próximos 7 dias",
         str(numeros.get("prazos_vencendo_7d", 0))),
        ("Leads convertidos na semana",
         str(numeros.get("leads_convertidos_semana", 0))),
        ("Recebíveis em atraso",
         _brl(float(numeros.get("recebiveis_atraso_reais", 0)))),
        ("Custo de IA na semana",
         f"{_brl(float(numeros.get('custo_ia_semana', 0)))} "
         f"({numeros.get('chamadas_ia_semana', 0)} chamada(s))"),
        ("Casos ativos sem movimentação há 30+ dias",
         str(numeros.get("casos_parados_30d", 0))),
    ]
    tabela = "".join(
        f"<tr><td style='padding:6px 12px;border:1px solid #ddd;'>{rotulo}</td>"
        f"<td style='padding:6px 12px;border:1px solid #ddd;text-align:right;'>"
        f"<b>{valor}</b></td></tr>"
        for rotulo, valor in linhas
    )

    top = numeros.get("top_casos_ia") or []
    bloco_top = ""
    if top:
        # t['caso'] carrega numero_interno/título (texto livre): escape.
        itens = "".join(
            f"<li>{html.escape(str(t['caso']))}: {_brl(t['custo'])} "
            f"({t['chamadas']} chamada(s))</li>"
            for t in top
        )
        bloco_top = (
            "<p><b>Casos com maior custo de IA na semana:</b></p>"
            f"<ul>{itens}</ul>"
        )

    corpo = (
        "<h3>Relatório semanal — De Paula Teixeira Advogados</h3>"
        f"<p>Período: {periodo}</p>"
        "<table style='border-collapse:collapse;'>"
        f"<tbody>{tabela}</tbody></table>"
        f"{bloco_top}"
        f"<p>{ASSINATURA_AUTOMATICA}</p>"
    )
    return assunto, corpo


# ── Job ───────────────────────────────────────────────────────────────────────

async def job_relatorio_dono() -> None:
    """Job semanal do APScheduler (segunda ~07h20 America/Sao_Paulo). Gate
    interno RELATORIO_DONO_ENABLED (default False — opt-in). Envia e-mail +
    sino a cada sócio/admin ativo via dispatch unificado `notificar`."""
    global _em_execucao
    if not settings.RELATORIO_DONO_ENABLED:
        logger.debug("[RelatorioDono] RELATORIO_DONO_ENABLED=false — job pulado")
        return
    if _em_execucao:
        logger.warning("[RelatorioDono] execução anterior em andamento — pulado")
        return
    _em_execucao = True  # set SÍNCRONO após o teste — sem janela de TOCTOU
    try:
        from app.core.database import AsyncSessionLocal
        from app.services.notification_service import notificar

        hoje = date.today()
        inicio, fim = hoje - timedelta(days=7), hoje

        async with AsyncSessionLocal() as db:
            numeros = await coletar_numeros_semana(db, hoje)
            assunto, corpo = montar_email_relatorio(numeros, inicio, fim)

            socios = (await db.execute(sqltext("""
                SELECT id, email FROM users
                WHERE role IN ('superadmin', 'admin', 'socio')
                  AND is_active = true AND deleted_at IS NULL
            """))).all()

            enviados = 0
            for s in socios:
                try:
                    await notificar(
                        db, s.id,
                        f"Relatório semanal — {hoje.strftime('%d/%m/%Y')}",
                        "Relatório semanal do escritório disponível: "
                        f"{numeros['prazos_vencendo_7d']} prazo(s) em 7d, "
                        f"{_brl(numeros['recebiveis_atraso_reais'])} em atraso, "
                        f"{numeros['casos_parados_30d']} caso(s) parado(s).",
                        tipo="relatorio", link="/",
                        email=(s.email or None),
                        email_assunto=assunto,
                        email_corpo=corpo,
                        forcar_sino=True,
                    )
                    enviados += 1
                except Exception as e:
                    logger.warning(
                        "[RelatorioDono] envio falhou p/ %s: %s", s.id, e
                    )
            logger.info("[RelatorioDono] %d destinatário(s) notificado(s)", enviados)
    except Exception as e:  # nunca derrubar o scheduler
        logger.error("[RelatorioDono] falha: %s", e, exc_info=True)
    finally:
        _em_execucao = False
