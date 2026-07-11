# ── app/services/cobranca_cliente_service.py ─────────────────────────────────
# Régua de cobrança de honorários voltada ao CLIENTE (migration 084).
#
# NÃO confundir com a régua interna do advogado (scheduler._regua_cobranca,
# 08h15, inadimplencia_alerts) — esta régua comunica o PRÓPRIO cliente, com
# tom cordial de escritório, e escala internamente ao advogado no fim.
#
# Degraus (função pura `degrau_aplicavel`):
#   d-3               → lembrete "a vencer" (vence em 1..3 dias)
#   d+1               → 1..6 dias vencida
#   d+7               → 7..14 dias vencida
#   d+15              → 15+ dias vencida
#   escalado_advogado → 16+ dias E d+15 já enviado — APENAS notificação
#                       interna ao advogado; o cliente NÃO é mais contatado.
#
# Idempotência: cada degrau enviado é registrado em fee_cobranca_envios
# (UNIQUE(fee_id, degrau)) ANTES do envio externo, com commit por parcela —
# no máximo 1 degrau por parcela por execução. Canais: e-mail + sino APENAS.
from __future__ import annotations

import html
import logging
from datetime import date
from uuid import uuid4

from sqlalchemy import text as sqltext
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

logger = logging.getLogger("ejc.cobranca_cliente")
settings = get_settings()

ASSINATURA_AUTOMATICA = (
    "De Paula Teixeira Advogados — mensagem automática, "
    "não responda este e-mail."
)

DEGRAUS_CLIENTE = ("d-3", "d+1", "d+7", "d+15")
DEGRAU_ESCALADA = "escalado_advogado"

# Guard de processo (padrão backup_service): uma régua por vez.
_em_execucao = False


# ── Função pura (testável) ────────────────────────────────────────────────────

def degrau_aplicavel(
    hoje: date, vencimento: date, degraus_enviados: set[str] | frozenset[str],
) -> str | None:
    """Degrau MAIS AVANÇADO aplicável à parcela e ainda não enviado.

    Regras (dias = hoje - vencimento; positivo = vencida):
      • dias >= 16 e "d+15" já enviado → "escalado_advogado" (uma única vez);
      • dias >= 15 → "d+15";
      • 7 <= dias <= 14 → "d+7";
      • 1 <= dias <= 6 → "d+1";
      • vence em 1..3 dias (dias em -3..-1) → "d-3";
      • nenhum degrau novo aplicável → None.

    Sempre o degrau mais avançado da janela atual (parcela que entra na régua
    já com 20 dias de atraso recebe d+15 direto — os anteriores são "pulados"
    e nunca reenviados); um degrau já registrado nunca repete.
    """
    enviados = set(degraus_enviados or ())
    dias = (hoje - vencimento).days

    if dias >= 16 and "d+15" in enviados and DEGRAU_ESCALADA not in enviados:
        return DEGRAU_ESCALADA
    if dias >= 15:
        return "d+15" if "d+15" not in enviados else None
    if 7 <= dias <= 14:
        return "d+7" if "d+7" not in enviados else None
    if 1 <= dias <= 6:
        return "d+1" if "d+1" not in enviados else None
    if -3 <= dias <= -1:  # vence em 1..3 dias
        return "d-3" if "d-3" not in enviados else None
    return None


# ── Templates determinísticos (cordiais, escalada sutil de firmeza) ───────────

def _brl(valor: float) -> str:
    txt = f"{valor:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return f"R$ {txt}"


def montar_email_cobranca(
    degrau: str, descricao: str, valor: float, vencimento: date,
) -> tuple[str, str]:
    """Template DETERMINÍSTICO (sem IA) do e-mail de cobrança ao cliente.

    Retorna (assunto, corpo_html). Tom SEMPRE cordial e respeitoso; d-3 é
    lembrete "a vencer", os demais são avisos de pendência com escalada sutil
    de firmeza. Toda mensagem identifica a parcela (descrição, valor e
    vencimento) e orienta a contatar o escritório caso o pagamento já tenha
    sido efetuado. Sem emojis; assinatura de comunicação automática.
    """
    venc = vencimento.strftime("%d/%m/%Y")
    # descricao é texto livre (financeiro): escape antes do corpo HTML.
    ident = (
        f"<p><b>Parcela:</b> {html.escape(descricao)}<br>"
        f"<b>Valor:</b> {_brl(valor)}<br>"
        f"<b>Vencimento:</b> {venc}</p>"
    )
    rodape = (
        "<p>Caso o pagamento já tenha sido efetuado, por gentileza "
        "desconsidere este aviso e, se possível, informe o escritório para "
        "atualizarmos nossos registros.</p>"
        "<p>Atenciosamente,</p>"
        f"<p>{ASSINATURA_AUTOMATICA}</p>"
    )

    if degrau == "d-3":
        assunto = "[De Paula Teixeira Advogados] Lembrete: parcela de honorários a vencer"
        corpo = (
            "<p>Prezado(a) cliente,</p>"
            "<p>Lembramos, com cordialidade, que a parcela de honorários "
            f"abaixo vence em <b>{venc}</b>:</p>"
            f"{ident}{rodape}"
        )
    elif degrau == "d+1":
        assunto = "[De Paula Teixeira Advogados] Aviso: parcela de honorários em aberto"
        corpo = (
            "<p>Prezado(a) cliente,</p>"
            "<p>Verificamos que a parcela de honorários abaixo consta em "
            "aberto em nossos registros:</p>"
            f"{ident}"
            "<p>Pedimos a gentileza de providenciar a regularização ou de "
            "entrar em contato com o escritório para qualquer esclarecimento.</p>"
            f"{rodape}"
        )
    elif degrau == "d+7":
        assunto = "[De Paula Teixeira Advogados] Reiteração: parcela de honorários pendente"
        corpo = (
            "<p>Prezado(a) cliente,</p>"
            "<p>Reiteramos que a parcela de honorários abaixo permanece "
            "pendente em nossos registros:</p>"
            f"{ident}"
            "<p>Solicitamos, respeitosamente, a regularização do pagamento. "
            "Permanecemos à disposição para conversar sobre eventuais "
            "dificuldades ou ajustes de condições.</p>"
            f"{rodape}"
        )
    else:  # d+15
        assunto = "[De Paula Teixeira Advogados] Pendência de honorários — atenção necessária"
        corpo = (
            "<p>Prezado(a) cliente,</p>"
            "<p>Apesar dos avisos anteriores, a parcela de honorários abaixo "
            "segue pendente em nossos registros:</p>"
            f"{ident}"
            "<p>Solicitamos que a regularização seja tratada com prioridade. "
            "Caso haja qualquer dificuldade, pedimos que entre em contato com "
            "o escritório para buscarmos, juntos, a melhor solução.</p>"
            f"{rodape}"
        )
    return assunto, corpo


# ── Execução ──────────────────────────────────────────────────────────────────

async def executar_regua_cliente(db: AsyncSession, hoje: date | None = None) -> dict:
    """Varre as parcelas elegíveis e envia NO MÁXIMO 1 degrau por parcela.

    Elegível: fee status pendente/atrasado, valor e data_vencimento não nulos,
    deleted_at IS NULL. O degrau é registrado em fee_cobranca_envios (com
    commit) ANTES de qualquer envio externo — reexecução nunca duplica.
    Retorna resumo {parcelas, enviados, escalados, erros}.
    """
    hoje = hoje or date.today()
    resumo = {"parcelas": 0, "enviados": 0, "escalados": 0, "erros": 0}

    rows = (await db.execute(sqltext("""
        SELECT f.id, f.descricao, f.valor, f.data_vencimento,
               f.client_id, f.case_id,
               cl.nome, cl.razao_social, cl.email AS cliente_email,
               cl.responsavel_id AS cliente_responsavel_id,
               c.advogado_responsavel_id, c.numero_interno
        FROM fees f
        JOIN clients cl ON cl.id = f.client_id
        LEFT JOIN cases c ON c.id = f.case_id
        WHERE f.status IN ('pendente', 'atrasado')
          AND f.deleted_at IS NULL
          AND f.valor IS NOT NULL
          AND f.data_vencimento IS NOT NULL
        ORDER BY f.data_vencimento
        LIMIT 500
    """))).all()

    for r in rows:
        resumo["parcelas"] += 1
        try:
            enviados = set((await db.execute(sqltext(
                "SELECT degrau FROM fee_cobranca_envios WHERE fee_id = :fid"
            ), {"fid": r.id})).scalars().all())

            degrau = degrau_aplicavel(hoje, r.data_vencimento, enviados)
            if degrau is None:
                continue

            # 1) REGISTRA o degrau (idempotência) ANTES do envio externo —
            # commit por parcela: restart/reexecução nunca duplica cobrança.
            await db.execute(sqltext(
                "INSERT INTO fee_cobranca_envios (id, fee_id, degrau) "
                "VALUES (:id, :fid, :deg) ON CONFLICT (fee_id, degrau) DO NOTHING"
            ), {"id": str(uuid4()), "fid": r.id, "deg": degrau})
            await db.commit()

            # 2) Envio
            if degrau == DEGRAU_ESCALADA:
                await _escalar_advogado(db, r, hoje)
                resumo["escalados"] += 1
            else:
                await _cobrar_cliente(db, r, degrau)
                resumo["enviados"] += 1
        except Exception as e:
            await db.rollback()
            resumo["erros"] += 1
            logger.error("[CobrancaCliente] parcela %s falhou: %s", r.id, e)

    logger.info(
        "[CobrancaCliente] parcelas=%d enviados=%d escalados=%d erros=%d",
        resumo["parcelas"], resumo["enviados"],
        resumo["escalados"], resumo["erros"],
    )
    return resumo


async def _cobrar_cliente(db: AsyncSession, r, degrau: str) -> None:
    """Degraus d-3/d+1/d+7/d+15: e-mail ao clients.email + sino no Portal
    (usuários cliente_externo do client_id). Canais fail-safe."""
    from app.services.datajud_sync_service import usuarios_portal_do_cliente
    from app.services.notification_service import enviar_email, notificar

    valor = float(r.valor or 0)
    assunto, corpo = montar_email_cobranca(
        degrau, r.descricao or "Honorários", valor, r.data_vencimento,
    )
    if r.cliente_email:
        await enviar_email(r.cliente_email, assunto, corpo)

    venc = r.data_vencimento.strftime("%d/%m/%Y")
    titulo = ("Lembrete: parcela de honorários a vencer" if degrau == "d-3"
              else "Parcela de honorários em aberto")
    for uid in await usuarios_portal_do_cliente(db, r.client_id):
        await notificar(
            db, uid, titulo,
            f"{r.descricao or 'Honorários'} — {_brl(valor)}, "
            f"vencimento {venc}. Detalhes na seção Financeiro do Portal.",
            tipo="financeiro", link="/portal/financeiro",
            forcar_sino=True,
        )


async def _escalar_advogado(db: AsyncSession, r, hoje: date) -> None:
    """Degrau escalado_advogado: APENAS notificação interna ao advogado
    responsável do caso (ou, sem caso, ao responsável do cliente). O cliente
    NÃO é mais contatado."""
    from app.services.notification_service import notificar

    destino = r.advogado_responsavel_id or r.cliente_responsavel_id
    if not destino:
        logger.warning(
            "[CobrancaCliente] parcela %s sem responsável para escalar", r.id,
        )
        return
    nome = r.nome or r.razao_social or "Cliente"
    dias = (hoje - r.data_vencimento).days
    valor = float(r.valor or 0)
    await notificar(
        db, destino,
        "Cobrança esgotou a régua automática",
        f"{nome} (caso {r.numero_interno or '—'}): parcela "
        f"'{r.descricao or 'Honorários'}' de {_brl(valor)} vencida há "
        f"{dias} dia(s). A régua automática ao cliente foi concluída — "
        "avalie tratativa direta.",
        tipo="financeiro", link="/financeiro",
        forcar_sino=True,
    )


async def job_regua_cobranca_cliente() -> None:
    """Job diário do APScheduler (~08h30 America/Sao_Paulo). Gate interno
    COBRANCA_ENABLED (default False — opt-in). Anti-concorrência por flag."""
    global _em_execucao
    if not settings.COBRANCA_ENABLED:
        logger.debug("[CobrancaCliente] COBRANCA_ENABLED=false — job pulado")
        return
    if _em_execucao:
        logger.warning("[CobrancaCliente] execução anterior em andamento — pulado")
        return
    _em_execucao = True  # set SÍNCRONO após o teste — sem janela de TOCTOU
    try:
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await executar_regua_cliente(db)
    except Exception as e:  # nunca derrubar o scheduler
        logger.error("[CobrancaCliente] falha: %s", e, exc_info=True)
    finally:
        _em_execucao = False
