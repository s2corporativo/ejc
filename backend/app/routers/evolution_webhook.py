"""Recebe webhooks da Evolution API (WhatsApp) e processa mensagens.

Rota PÚBLICA (Evolution chama de fora) — protegida por secret: valida um
token e recusa se não configurado.
O secret é enviado pela Evolution EXCLUSIVAMENTE via header
`apikey`/`X-Webhook-Token`. Query string (`?token=`) NÃO é aceita: URL vaza em
access log do Nginx, em proxy e no histórico do painel (LGPD/segurança).
"""
import hmac
import logging
import os

from fastapi import APIRouter, Request, BackgroundTasks, HTTPException

logger = logging.getLogger("ejc.whatsapp")
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

WEBHOOK_SECRET = os.getenv("EVOLUTION_WEBHOOK_SECRET", "")


def _autorizado(request: Request) -> bool:
    """Compara (timing-safe) o secret recebido com o configurado."""
    recebido = (
        request.headers.get("x-webhook-token")
        or request.headers.get("apikey")
        # Sem fallback por query string: segredo em URL vaza em log de acesso.
        or ""
    )
    return bool(recebido) and hmac.compare_digest(recebido, WEBHOOK_SECRET)


def _log_safe(valor) -> str:
    """Valor de payload EXTERNO seguro para log: curto e sem quebras de linha
    (evita forja de linhas de log via \\n injetado no webhook)."""
    return str(valor or "")[:60].replace("\n", " ").replace("\r", " ")


async def _processar_mensagem(data: dict):
    """Processa mensagem recebida do WhatsApp — adaptar conforme necessidade."""
    try:
        evento = _log_safe(data.get("event", ""))
        instancia = _log_safe(data.get("instance", ""))
        logger.info(f"WhatsApp [{instancia}] evento: {evento}")

        if evento == "messages.upsert":
            msgs = data.get("data", {})
            if isinstance(msgs, list):
                msgs = msgs[0] if msgs else {}
            # LGPD (auditoria 2026-07-26, AI-028): NUNCA logar telefone nem
            # conteúdo da mensagem — podem carregar segredo profissional, saúde,
            # fatos criminais ou CPF. Log registra apenas o EVENTO; o payload é
            # processado em memória quando a integração CRM existir.
            if not msgs.get("key", {}).get("fromMe"):
                logger.info(f"WhatsApp [{instancia}] mensagem recebida "
                            "(telefone/conteúdo não logados — LGPD)")
                # TODO: integrar com fluxo de CRM/casos se necessário

        elif evento == "connection.update":
            status = _log_safe(data.get("data", {}).get("state", ""))
            logger.info(f"WhatsApp conexão: {status}")

    except Exception as e:
        # Só o TIPO da exceção — a mensagem pode carregar fragmento do payload.
        logger.error(f"Erro ao processar webhook WhatsApp: {type(e).__name__}")


@router.post("/evolution")
async def evolution_webhook(request: Request, bg: BackgroundTasks):
    """Endpoint para webhooks da Evolution API."""
    # Sem secret configurado, o endpoint NÃO aceita chamadas — evita que
    # terceiros injetem eventos forjados num deploy ainda não configurado.
    if not WEBHOOK_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Webhook indisponível: EVOLUTION_WEBHOOK_SECRET não configurado.",
        )
    if not _autorizado(request):
        raise HTTPException(status_code=401, detail="Webhook não autorizado")
    try:
        body = await request.json()
        bg.add_task(_processar_mensagem, body)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook parse error: {type(e).__name__}")
        return {"status": "error"}
