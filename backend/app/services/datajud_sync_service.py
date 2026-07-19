# ── app/services/datajud_sync_service.py ─────────────────────────────────────
# Sync DIÁRIO do DataJud com notificação de andamentos novos ao CLIENTE.
#
# Diferença para o job legado (scheduler.job_datajud_sync, 08h45/16h45): aquele
# apenas importa movimentos para a timeline; ESTE job, além de importar (mesmo
# dedup [dj:<hash16>] — os dois caminhos compartilham a chave), notifica:
#   • o advogado responsável (sino + e-mail, dispatch unificado `notificar`);
#   • o cliente: sino no Portal (usuários cliente_externo do client_id) +
#     e-mail a clients.email com template DETERMINÍSTICO (sem IA), sóbrio,
#     apenas dados públicos do processo — NUNCA estratégia interna.
#
# Canais: e-mail + sino APENAS (WhatsApp permanentemente fora de escopo).
#
# Padrões seguidos (backup_service):
#   • gate interno DATAJUD_SYNC_ENABLED (default False — opt-in no .env);
#   • horário via DATAJUD_SYNC_HORA_UTC ("HH:MM" UTC, CronTrigger timezone=UTC);
#   • flag anti-concorrência testada-e-setada sincronamente (sem TOCTOU);
#   • commit POR CASO (não perder progresso) + rate-limit educado (sleep 1s,
#     teto de casos por execução).
from __future__ import annotations

import asyncio
import html
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select, text as sqltext
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.case import Case, CaseMovimento
from app.services.datajud_service import (
    DataJudDesabilitadoError,
    TribunalNaoMapeadoError,
    _hash_mov,
    alias_do_numero,
    consultar_movimentos,
    upsert_movimentos_no_caso,
)

logger = logging.getLogger("ejc.datajud_sync")
settings = get_settings()

# Teto de casos por execução — rate-limit educado com a API pública do CNJ.
MAX_CASOS_POR_EXECUCAO = 80
# Pausa entre casos (segundos).
PAUSA_ENTRE_CASOS = 1.0
# Máximo de andamentos listados no e-mail ("e mais N" para o excedente).
MAX_ANDAMENTOS_EMAIL = 5

ASSINATURA_AUTOMATICA = (
    "De Paula Teixeira Advogados — mensagem automática, "
    "não responda este e-mail."
)

# Guard de processo: um sync por vez (padrão backup_service — flag booleana
# testada-e-setada SINCRONAMENTE, sem await entre teste e set).
_em_execucao = False


# ── Configuração ──────────────────────────────────────────────────────────────

def hora_sync_clientes_utc() -> tuple[int, int]:
    """Converte DATAJUD_SYNC_HORA_UTC ("HH:MM") em (hora, minuto). Valor
    malformado cai no default 09:30 UTC com warning — nunca derruba o boot do
    scheduler (mesmo contrato de backup_service.hora_backup_utc)."""
    raw = (settings.DATAJUD_SYNC_HORA_UTC or "").strip()
    try:
        hora_s, minuto_s = raw.split(":", 1)
        hora, minuto = int(hora_s), int(minuto_s)
        if 0 <= hora <= 23 and 0 <= minuto <= 59:
            return hora, minuto
    except (ValueError, AttributeError):
        pass
    logger.warning(
        "[DataJudSync] DATAJUD_SYNC_HORA_UTC inválida (%r) — usando 09:30 UTC",
        raw,
    )
    return 9, 30


# ── Funções puras (testáveis) ─────────────────────────────────────────────────

def limpar_descricao(descricao: str) -> str:
    """Remove o sufixo técnico de dedup "[dj:<hash>]" da descrição do
    movimento — o cliente nunca vê metadado interno."""
    return re.sub(r"\s*\[dj:[0-9a-f]{16}\]\s*$", "", descricao or "").strip()


def filtrar_movimentos_novos(
    movimentos: list[dict], descricoes_existentes: list[str],
) -> list[dict]:
    """Filtra os movimentos AINDA não importados no caso, pela MESMA chave de
    dedup do datajud_service (hash(data[:10]|descricao) embutido como sufixo
    [dj:<hash16>] nas descrições existentes). Função pura — testável sem banco.
    Dedup também dentro do próprio lote."""
    hashes_exist = {
        m.group(1)
        for d in descricoes_existentes
        if (m := re.search(r"\[dj:([0-9a-f]{16})\]", d or ""))
    }
    novos: list[dict] = []
    for mov in movimentos:
        h = _hash_mov((mov.get("data") or "")[:10], mov.get("descricao") or "")
        if h in hashes_exist:
            continue
        hashes_exist.add(h)
        novos.append(mov)
    return novos


def _fmt_data_mov(data_iso: str) -> str:
    """ISO-8601 → dd/mm/aaaa (fallback: string original truncada)."""
    try:
        return datetime.fromisoformat((data_iso or "")[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return (data_iso or "—")[:10]


def montar_email_andamentos(
    numero_processo: str, andamentos: list[dict],
) -> tuple[str, str]:
    """Template DETERMINÍSTICO (sem IA) do e-mail de movimentação ao cliente.

    Retorna (assunto, corpo_html). Linguagem sóbria de escritório; lista no
    máximo MAX_ANDAMENTOS_EMAIL andamentos ("e mais N" para o excedente);
    somente dados públicos do processo (número, data e descrição oficial) —
    nunca estratégia interna. Aviso de comunicação automática ao final.
    """
    assunto = (
        f"[De Paula Teixeira Advogados] Movimentação no processo "
        f"{numero_processo}"
    )
    visiveis = andamentos[:MAX_ANDAMENTOS_EMAIL]
    excedente = len(andamentos) - len(visiveis)

    # Descrições vêm da API pública do CNJ (texto de terceiros): escape
    # obrigatório antes de entrar no corpo HTML do e-mail do escritório.
    itens = "".join(
        f"<li><b>{html.escape(_fmt_data_mov(a.get('data') or ''))}</b> — "
        f"{html.escape(limpar_descricao(a.get('descricao') or ''))}</li>"
        for a in visiveis
    )
    mais = (
        f"<p>e mais {excedente} andamento(s) registrado(s) na mesma consulta.</p>"
        if excedente > 0 else ""
    )
    corpo = (
        "<p>Prezado(a) cliente,</p>"
        f"<p>Informamos que o processo <b>{html.escape(numero_processo)}</b> teve "
        f"nova(s) movimentação(ões) oficial(is):</p>"
        f"<ul>{itens}</ul>"
        f"{mais}"
        "<p>Em caso de dúvidas, os detalhes estão disponíveis no Portal do "
        "Cliente. Nossa equipe está acompanhando o andamento e entrará em "
        "contato caso alguma providência seja necessária.</p>"
        "<p>Atenciosamente,</p>"
        f"<p>{ASSINATURA_AUTOMATICA}</p>"
    )
    return assunto, corpo


# ── Acesso a dados ────────────────────────────────────────────────────────────

async def usuarios_portal_do_cliente(db: AsyncSession, client_id: str) -> list[str]:
    """IDs dos usuários cliente_externo ATIVOS vinculados ao client_id —
    destinatários do sino no Portal do Cliente."""
    rows = await db.execute(sqltext(
        "SELECT id FROM users WHERE client_id = :cid "
        "AND role = 'cliente_externo' AND is_active = true"
    ), {"cid": client_id})
    return [r.id for r in rows]


async def _notificar_andamentos(
    db: AsyncSession, case: Case, novos: list[dict],
) -> None:
    """(b)/(c) da entrega: notifica advogado responsável e cliente (Portal +
    e-mail com template determinístico). Falha de canal nunca propaga —
    `notificar`/`enviar_email` já são fail-safe."""
    from app.services.notification_service import enviar_email, notificar

    qtd = len(novos)
    numero = case.numero_processo or case.numero_interno or case.id

    # (b) advogado responsável — sino (+ e-mail conforme preferências)
    if case.advogado_responsavel_id:
        adv_email = (await db.execute(sqltext(
            "SELECT email FROM users WHERE id = :i AND is_active = true"
        ), {"i": case.advogado_responsavel_id})).scalar()
        await notificar(
            db, case.advogado_responsavel_id,
            f"Novo andamento oficial ({qtd})",
            f"O processo {numero} teve {qtd} andamento(s) novo(s) no DataJud.",
            tipo="andamento", link=f"/casos/{case.id}",
            email=adv_email or None,
            email_assunto=f"[EJC] Andamento novo no processo {numero}",
            email_corpo=(
                f"<p>O processo <b>{numero}</b> (caso "
                f"{case.numero_interno or case.id}) teve <b>{qtd}</b> "
                f"andamento(s) novo(s) importado(s) do DataJud.</p>"
                f"<p>Acesse o EJC para os detalhes.</p>"
            ),
        )

    # (c) cliente — sino no Portal para cada usuário externo vinculado
    assunto, corpo = montar_email_andamentos(numero, novos)
    for uid in await usuarios_portal_do_cliente(db, case.client_id):
        await notificar(
            db, uid,
            "Movimentação no seu processo",
            f"O processo {numero} teve {qtd} nova(s) movimentação(ões). "
            "Acompanhe os detalhes na área do seu caso.",
            tipo="andamento", link=f"/portal/casos/{case.id}",
            forcar_sino=True,
        )

    # (c) e-mail ao endereço cadastral do cliente (clients.email)
    cli_email = (await db.execute(sqltext(
        "SELECT email FROM clients WHERE id = :cid AND deleted_at IS NULL"
    ), {"cid": case.client_id})).scalar()
    if cli_email:
        await enviar_email(cli_email, assunto, corpo)


# ── Execução ──────────────────────────────────────────────────────────────────

async def executar_sync_clientes(db: AsyncSession) -> dict:
    """Percorre os casos ativos com número CNJ válido, importa movimentos do
    DataJud (commit POR CASO) e notifica advogado + cliente quando há
    andamento NOVO. Retorna resumo {casos, com_novos, movimentos_novos, erros}.
    """
    casos = (await db.execute(select(Case).where(
        Case.deleted_at.is_(None),
        Case.status.in_(["ativo", "suspenso"]),
        Case.numero_processo.isnot(None),
    ).order_by(Case.last_synced_at.asc().nullsfirst()))).scalars().all()

    resumo = {"casos": 0, "com_novos": 0, "movimentos_novos": 0, "erros": 0}
    for case in casos:
        # Número precisa ter 20 dígitos E tribunal mapeado — senão pular
        # silenciosamente (o alias é pré-requisito da consulta).
        n = re.sub(r"\D", "", case.numero_processo or "")
        if len(n) != 20 or not alias_do_numero(case.numero_processo):
            continue
        if resumo["casos"] >= MAX_CASOS_POR_EXECUCAO:
            logger.info(
                "[DataJudSync] teto de %d casos atingido — restantes ficam "
                "para a próxima execução", MAX_CASOS_POR_EXECUCAO,
            )
            break
        resumo["casos"] += 1

        try:
            movimentos = await consultar_movimentos(case.numero_processo)

            # Quais são NOVOS (para o conteúdo da notificação) — a mesma chave
            # de dedup do upsert garante consistência entre os dois passos.
            existentes = (await db.execute(
                select(CaseMovimento.descricao)
                .where(CaseMovimento.case_id == case.id)
            )).scalars().all()
            novos = filtrar_movimentos_novos(movimentos, list(existentes))

            # (a) timeline: upsert idempotente (dedup [dj:hash] + prazos autom.)
            await upsert_movimentos_no_caso(db, case, movimentos)

            # Marcador do último andamento NOVO visto (migration 084) — só
            # avança quando há novidade, fiel ao nome da coluna (o "último
            # sync" fica em last_synced_at, atualizado pelo upsert acima).
            if novos:
                case.datajud_ultimo_andamento_em = datetime.now(timezone.utc)
                resumo["com_novos"] += 1
                resumo["movimentos_novos"] += len(novos)
                await _notificar_andamentos(db, case, novos)

            # Commit POR CASO — falha adiante não perde o progresso já feito.
            await db.commit()
        except DataJudDesabilitadoError:
            # Integração desligada no meio do caminho — aborta o lote inteiro.
            await db.rollback()
            logger.info("[DataJudSync] DataJud desabilitado — sync abortado")
            break
        except TribunalNaoMapeadoError:
            await db.rollback()
            continue
        except Exception as e:
            await db.rollback()
            resumo["erros"] += 1
            logger.warning(
                "[DataJudSync] caso %s falhou: %s",
                case.numero_interno or case.id, e,
            )

        await asyncio.sleep(PAUSA_ENTRE_CASOS)  # rate-limit educado

    logger.info(
        "[DataJudSync] casos=%d com_novos=%d movimentos_novos=%d erros=%d",
        resumo["casos"], resumo["com_novos"],
        resumo["movimentos_novos"], resumo["erros"],
    )
    return resumo


async def job_datajud_sync_clientes() -> None:
    """Job diário do APScheduler (DATAJUD_SYNC_HORA_UTC). Gates internos:
    DATAJUD_SYNC_ENABLED (default False — opt-in) + integração DataJud
    configurada. Anti-concorrência por flag de processo."""
    global _em_execucao
    if not settings.DATAJUD_SYNC_ENABLED:
        logger.debug("[DataJudSync] DATAJUD_SYNC_ENABLED=false — job pulado")
        return
    if not settings.DATAJUD_ENABLED or not settings.DATAJUD_API_KEY:
        logger.info(
            "[DataJudSync] DATAJUD_ENABLED/DATAJUD_API_KEY ausentes — job pulado"
        )
        return
    if _em_execucao:
        logger.warning("[DataJudSync] execução anterior ainda em andamento — pulado")
        return
    _em_execucao = True  # set SÍNCRONO após o teste — sem janela de TOCTOU
    try:
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await executar_sync_clientes(db)
    except Exception as e:  # nunca deixar exceção derrubar o scheduler
        logger.error("[DataJudSync] falha na execução: %s", e, exc_info=True)
    finally:
        _em_execucao = False
