"""WhatsApp via Evolution API — proxy endpoints"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from app.core.security import get_current_user
from app.core.ownership import is_gestao
from app.models.user import User
import httpx
import logging
import os

logger = logging.getLogger(__name__)

# Envio ativo de WhatsApp do escritório = ação sensível: só equipe que fala com
# cliente (gestão/advogados/secretaria); nunca qualquer autenticado.
# Checagem EXPLÍCITA por conjunto (não hierárquica): `require_roles` usa o piso do
# menor nível da lista (secretaria=2), o que deixaria estagiário/financeiro passar.
_PODE_ENVIAR = frozenset(
    {"superadmin", "admin", "socio", "advogado", "advogado_auxiliar", "secretaria"}
)


def _exigir_envio(cu: User = Depends(get_current_user)) -> User:
    if cu.role.value not in _PODE_ENVIAR:
        raise HTTPException(403, "Sem permissão para enviar WhatsApp do escritório")
    return cu


def _exigir_gestao(cu: User = Depends(get_current_user)) -> User:
    # [A7] QR de pareamento controla a SESSÃO do WhatsApp do escritório (quem
    # escaneia assume a conta) → restrito a gestão (socio+), não a qualquer staff.
    if not is_gestao(cu):
        raise HTTPException(403, "Pareamento do WhatsApp restrito à gestão")
    return cu

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

# Lê os nomes oficiais do .env (EVOLUTION_API_URL / EVOLUTION_API_KEY); mantém
# fallback para nomes legados. Sem key por instância, usa a apikey global.
EVOLUTION_URL = os.getenv("EVOLUTION_API_URL") or os.getenv("EVOLUTION_URL", "http://evolution_api:8080")
EVOLUTION_KEY = os.getenv("EVOLUTION_API_KEY") or os.getenv("EVOLUTION_KEY", "")
INSTANCE      = os.getenv("EVOLUTION_INSTANCE", "ejc-escritorio")
INSTANCE_KEY  = os.getenv("EVOLUTION_INSTANCE_KEY") or EVOLUTION_KEY

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
async def get_status(current_user=Depends(_exigir_envio)):
    """Retorna status da instância WhatsApp"""
    try:
        status_code, data = await _evo_get(f"/instance/connectionState/{INSTANCE}", use_instance_key=True)
        return data
    except Exception:
        logger.warning("Falha ao consultar status da instância WhatsApp", exc_info=True)
        return {"state": "error", "detail": "Falha ao consultar o serviço de WhatsApp"}


@router.get("/qrcode")
async def get_qrcode(current_user=Depends(_exigir_gestao)):
    """Retorna QR Code para conectar o WhatsApp"""
    try:
        status_code, data = await _evo_get(f"/instance/connect/{INSTANCE}", use_instance_key=True)
        return data
    except Exception:
        logger.warning("Falha ao obter QR Code do WhatsApp", exc_info=True)
        raise HTTPException(502, "Falha ao comunicar com o serviço de WhatsApp")


@router.post("/send")
async def send_message(
    body: dict = Body(...),
    current_user=Depends(_exigir_envio),
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
    except Exception:
        logger.warning("Falha ao enviar mensagem de WhatsApp", exc_info=True)
        raise HTTPException(502, "Falha ao comunicar com o serviço de WhatsApp")


@router.get("/chats")
async def list_chats(
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(_exigir_envio),
):
    """Lista conversas recentes"""
    try:
        status_code, data = await _evo_post(
            f"/chat/findChats/{INSTANCE}",
            {"limit": limit},
            use_instance_key=True
        )
        return data if isinstance(data, list) else data
    except Exception:
        return []


@router.post("/messages")
async def get_messages(
    body: dict = Body(...),
    current_user=Depends(_exigir_envio),
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
    except Exception:
        return []
