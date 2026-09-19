"""WhatsApp via Evolution API — proxy endpoints"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from app.core.config import get_settings
from app.core.security import get_current_user
from app.core.ownership import is_gestao
from app.models.user import User
from app.services.notification_preferences import whatsapp_configurado
from app.services.notification_service import normalizar_telefone_br
import httpx
import logging

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

def _config_evolution():
    settings = get_settings()
    if not settings.WHATSAPP_ENABLED:
        raise HTTPException(503, "Canal WhatsApp desabilitado por configuração")
    if not whatsapp_configurado(settings):
        raise HTTPException(503, "Canal WhatsApp sem configuração completa")
    return (
        settings.EVOLUTION_API_URL.rstrip("/"),
        settings.EVOLUTION_API_KEY,
        settings.EVOLUTION_INSTANCE,
        float(settings.EVOLUTION_TIMEOUT),
    )


async def _evo_get(path: str):
    url, key, _instance_name, timeout = _config_evolution()
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            f"{url}{path}",
            headers={"apikey": key, "Content-Type": "application/json"},
        )
        if response.status_code >= 400:
            raise HTTPException(502, "Serviço de WhatsApp recusou a operação")
        if response.headers.get("content-type", "").startswith("application/json"):
            return response.json()
        return {}


async def _evo_post(path: str, body: dict):
    url, key, _instance_name, timeout = _config_evolution()
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{url}{path}",
            headers={"apikey": key, "Content-Type": "application/json"},
            json=body,
        )
        if response.status_code >= 400:
            raise HTTPException(502, "Serviço de WhatsApp recusou a operação")
        if response.headers.get("content-type", "").startswith("application/json"):
            return response.json()
        return {}


def _instance() -> str:
    return _config_evolution()[2]


@router.get("/status")
async def get_status(current_user=Depends(_exigir_envio)):
    """Retorna status da instância WhatsApp"""
    try:
        return await _evo_get(f"/instance/connectionState/{_instance()}")
    except HTTPException:
        raise
    except Exception:
        logger.warning("Falha ao consultar status da instância WhatsApp", exc_info=True)
        return {"state": "error", "detail": "Falha ao consultar o serviço de WhatsApp"}


@router.get("/qrcode")
async def get_qrcode(current_user=Depends(_exigir_gestao)):
    """Retorna QR Code para conectar o WhatsApp"""
    try:
        return await _evo_get(f"/instance/connect/{_instance()}")
    except HTTPException:
        raise
    except Exception:
        logger.warning("Falha ao obter QR Code do WhatsApp", exc_info=True)
        raise HTTPException(502, "Falha ao comunicar com o serviço de WhatsApp")


@router.post("/send")
async def send_message(
    body: dict = Body(...),
    current_user=Depends(_exigir_envio),
):
    """Envia mensagem de texto para um número"""
    phone = normalizar_telefone_br(body.get("phone"))
    message = str(body.get("message") or "").strip()
    if not phone or not message:
        raise HTTPException(422, "phone válido e message são obrigatórios")

    try:
        return await _evo_post(
            f"/message/sendText/{_instance()}",
            {"number": phone, "text": message},
        )
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
        data = await _evo_post(
            f"/chat/findChats/{_instance()}",
            {"limit": limit},
        )
        return data if isinstance(data, (list, dict)) else []
    except HTTPException:
        raise
    except Exception:
        return []


@router.post("/messages")
async def get_messages(
    body: dict = Body(...),
    current_user=Depends(_exigir_envio),
):
    """Busca mensagens de uma conversa"""
    phone = normalizar_telefone_br(body.get("phone"))
    if not phone:
        raise HTTPException(422, "phone inválido")
    jid = phone + "@s.whatsapp.net"
    try:
        limit = max(1, min(int(body.get("limit", 30)), 100))
    except (TypeError, ValueError):
        raise HTTPException(422, "limit inválido")

    try:
        data = await _evo_post(
            f"/chat/findMessages/{_instance()}",
            {"where": {"key": {"remoteJid": jid}}, "limit": limit},
        )
        return data if isinstance(data, (list, dict)) else []
    except HTTPException:
        raise
    except Exception:
        return []
