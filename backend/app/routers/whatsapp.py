"""WhatsApp via Evolution API — proxy endpoints"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user
import httpx
import os

router = APIRouter(prefix="/api/v1/whatsapp", tags=["whatsapp"])

EVOLUTION_URL = os.getenv("EVOLUTION_URL", "http://localhost:8080")
EVOLUTION_KEY = os.getenv("EVOLUTION_KEY", "")
INSTANCE      = os.getenv("EVOLUTION_INSTANCE", "ejc-escritorio")
INSTANCE_KEY  = os.getenv("EVOLUTION_INSTANCE_KEY", "")

def _headers_global():
    return {"apikey": EVOLUTION_KEY, "Content-Type": "application/json"}

def _headers_instance():
    return {"apikey": INSTANCE_KEY, "Content-Type": "application/json"}


async def _evo_get(path: str, use_instance_key=False):
    h = _headers_instance() if use_instance_key else _headers_global()
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{EVOLUTION_URL}{path}", headers=h)
        return r.status_code, r.json() if r.headers.get("content-type","").startswith("application/json") else r.text


async def _evo_post(path: str, body: dict, use_instance_key=False):
    h = _headers_instance() if use_instance_key else _headers_global()
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{EVOLUTION_URL}{path}", headers=h, json=body)
        return r.status_code, r.json() if r.headers.get("content-type","").startswith("application/json") else r.text


@router.get("/status")
async def get_status(current_user=Depends(get_current_user)):
    """Retorna status da instância WhatsApp"""
    try:
        status_code, data = await _evo_get(f"/instance/connectionState/{INSTANCE}", use_instance_key=True)
        return data
    except Exception as e:
        return {"state": "error", "detail": str(e)}


@router.get("/qrcode")
async def get_qrcode(current_user=Depends(get_current_user)):
    """Retorna QR Code para conectar o WhatsApp"""
    try:
        status_code, data = await _evo_get(f"/instance/connect/{INSTANCE}", use_instance_key=True)
        return data
    except Exception as e:
        raise HTTPException(502, f"Evolution API error: {e}")


@router.post("/send")
async def send_message(
    body: dict = Body(...),
    current_user=Depends(get_current_user),
):
    """Envia mensagem de texto para um número"""
    phone = body.get("phone", "").replace("+", "").replace("-", "").replace(" ", "")
    if not phone.startswith("55"):
        phone = "55" + phone
    message = body.get("message", "")
    if not phone or not message:
        raise HTTPException(422, "phone e message obrigatórios")

    try:
        status_code, data = await _evo_post(
            f"/message/sendText/{INSTANCE}",
            {"number": phone, "text": message},
            use_instance_key=True
        )
        if status_code >= 400:
            raise HTTPException(status_code, detail=str(data))
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Evolution API error: {e}")


@router.get("/chats")
async def list_chats(
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    """Lista conversas recentes"""
    try:
        status_code, data = await _evo_post(
            f"/chat/findChats/{INSTANCE}",
            {"limit": limit},
            use_instance_key=True
        )
        return data if isinstance(data, list) else data
    except Exception as e:
        return []


@router.post("/messages")
async def get_messages(
    body: dict = Body(...),
    current_user=Depends(get_current_user),
):
    """Busca mensagens de uma conversa"""
    phone = body.get("phone", "").replace("+", "").replace(" ", "").replace("-", "")
    if not phone.startswith("55"):
        phone = "55" + phone
    jid = phone + "@s.whatsapp.net"
    limit = body.get("limit", 30)

    try:
        status_code, data = await _evo_post(
            f"/chat/findMessages/{INSTANCE}",
            {"where": {"key": {"remoteJid": jid}}, "limit": limit},
            use_instance_key=True
        )
        return data if isinstance(data, (list, dict)) else []
    except Exception as e:
        return []
