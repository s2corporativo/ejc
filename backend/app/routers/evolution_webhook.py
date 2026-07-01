"""Recebe webhooks da Evolution API (WhatsApp) e processa mensagens.

Rota PÚBLICA (Evolution chama de fora) — protegida por secret.
Mesmo padrão do webhook Z-API: valida um token e recusa se não configurado.
O secret é enviado pela Evolution como header `apikey`/`X-Webhook-Token`
ou via query `?token=` na URL do webhook configurada no painel.
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
        or request.query_params.get("token")
        or ""
    )
    return bool(recebido) and hmac.compare_digest(recebido, WEBHOOK_SECRET)


async def _processar_mensagem(data: dict):
    """Processa mensagem recebida do WhatsApp — adaptar conforme necessidade."""
    try:
        evento = data.get("event", "")
        instancia = data.get("instance", "")
        logger.info(f"WhatsApp [{instancia}] evento: {evento}")

        if evento == "messages.upsert":
            msgs = data.get("data", {})
            if isinstance(msgs, list):
                msgs = msgs[0] if msgs else {}
            numero = msgs.get("key", {}).get("remoteJid", "").replace("@s.whatsapp.net", "")
            texto = msgs.get("message", {}).get("conversation", "") or \
                    msgs.get("message", {}).get("extendedTextMessage", {}).get("text", "")
            if numero and texto and not msgs.get("key", {}).get("fromMe"):
                logger.info(f"Mensagem de {numero}: {texto[:100]}")
                # TODO: integrar com fluxo de CRM/casos se necessário

        elif evento == "connection.update":
            status = data.get("data", {}).get("state", "")
            logger.info(f"WhatsApp conexão: {status}")

    except Exception as e:
        logger.error(f"Erro ao processar webhook WhatsApp: {e}")


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
        logger.error(f"Webhook parse error: {e}")
        return {"status": "error"}
