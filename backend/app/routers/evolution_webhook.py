"""Recebe webhooks da Evolution API (WhatsApp) e processa mensagens."""
import hmac
import os
import logging

from fastapi import APIRouter, Request, BackgroundTasks, Header, HTTPException

logger = logging.getLogger("ejc.whatsapp")
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
EVOLUTION_WEBHOOK_TOKEN = os.getenv("EVOLUTION_WEBHOOK_TOKEN", "")


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
            texto = msgs.get("message", {}).get("conversation", "") or                     msgs.get("message", {}).get("extendedTextMessage", {}).get("text", "")
            if numero and texto and not msgs.get("key", {}).get("fromMe"):
                logger.info(f"Mensagem de {numero}: {texto[:100]}")
                # TODO: integrar com fluxo de CRM/casos se necessário

        elif evento == "connection.update":
            status = data.get("data", {}).get("state", "")
            logger.info(f"WhatsApp conexão: {status}")

    except Exception as e:
        logger.error(f"Erro ao processar webhook WhatsApp: {e}")


@router.post("/evolution")
async def evolution_webhook(
    request: Request,
    bg: BackgroundTasks,
    x_webhook_token: str | None = Header(None, alias="X-Webhook-Token"),
    apikey: str | None = Header(None),
):
    """Endpoint para webhooks da Evolution API."""
    token_recebido = x_webhook_token or apikey
    if not EVOLUTION_WEBHOOK_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Webhook indisponivel: EVOLUTION_WEBHOOK_TOKEN nao configurado.",
        )
    if not token_recebido or not hmac.compare_digest(token_recebido, EVOLUTION_WEBHOOK_TOKEN):
        raise HTTPException(status_code=401, detail="Token invalido")

    try:
        body = await request.json()
        bg.add_task(_processar_mensagem, body)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook parse error: {e}")
        return {"status": "error"}
