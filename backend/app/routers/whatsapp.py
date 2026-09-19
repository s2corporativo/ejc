"""WhatsApp via Evolution API — proxy endpoints"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from app.core.config import get_settings
from app.core.security import get_current_user
from app.core.ownership import is_gestao
from app.models.user import User
from app.services.notification_service import normalizar_telefone_br
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

def _exigir_whatsapp_habilitado() -> None:
    """Kill switch único: flag desligada bloqueia também as rotas manuais."""
    if not get_settings().WHATSAPP_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="WhatsApp desabilitado por configuração.",
        )


router = APIRouter(
    prefix="/whatsapp",
    tags=["whatsapp"],
    dependencies=[Depends(_exigir_whatsapp_habilitado)],
)


def _evolution_config() -> tuple[str, str, str, str, float]:
    """Resolve a configuração vigente a cada chamada.

    Usa o singleton de Settings (incluindo overlay do Cofre) em vez de
    capturar segredo/URL no import do módulo. Nomes legados ficam apenas como
    fallback de compatibilidade.
    """
    settings = get_settings()
    base = (settings.EVOLUTION_API_URL or os.getenv("EVOLUTION_URL") or "").strip().rstrip("/")
    key = (settings.EVOLUTION_API_KEY or os.getenv("EVOLUTION_KEY") or "").strip()
    instance = (settings.EVOLUTION_INSTANCE or "ejc-escritorio").strip()
    instance_key = (os.getenv("EVOLUTION_INSTANCE_KEY") or key).strip()
    timeout = float(settings.EVOLUTION_TIMEOUT or 20)
    if not (base and key and instance):
        raise HTTPException(
            status_code=503,
            detail="Evolution API não configurada para o WhatsApp.",
        )
    return base, key, instance, instance_key, timeout


def _headers(key: str):
    return {"apikey": key, "Content-Type": "application/json"}


async def _evo_get(path: str, use_instance_key=False):
    base, key, _instance, instance_key, timeout = _evolution_config()
    h = _headers(instance_key if use_instance_key else key)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(f"{base}{path}", headers=h)
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else None
        return r.status_code, data


async def _evo_post(path: str, body: dict, use_instance_key=False):
    base, key, _instance, instance_key, timeout = _evolution_config()
    h = _headers(instance_key if use_instance_key else key)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(f"{base}{path}", headers=h, json=body)
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else None
        return r.status_code, data


@router.get("/status")
async def get_status(current_user=Depends(_exigir_envio)):
    """Retorna status da instância WhatsApp"""
    try:
        _base, _key, instance, _instance_key, _timeout = _evolution_config()
        status_code, data = await _evo_get(
            f"/instance/connectionState/{instance}", use_instance_key=True
        )
        if status_code >= 400:
            return {"state": "error", "detail": f"Evolution API respondeu HTTP {status_code}."}
        return data
    except Exception:
        logger.warning("Falha ao consultar status da instância WhatsApp", exc_info=True)
        return {"state": "error", "detail": "Falha ao consultar o serviço de WhatsApp"}


@router.get("/qrcode")
async def get_qrcode(current_user=Depends(_exigir_gestao)):
    """Retorna QR Code para conectar o WhatsApp"""
    try:
        _base, _key, instance, _instance_key, _timeout = _evolution_config()
        status_code, data = await _evo_get(
            f"/instance/connect/{instance}", use_instance_key=True
        )
        if status_code >= 400:
            raise HTTPException(status_code, "Evolution API recusou o pareamento.")
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
    phone = normalizar_telefone_br(body.get("phone"))
    message = str(body.get("message") or "").strip()
    if not phone or not message:
        raise HTTPException(422, "phone válido e message são obrigatórios")

    try:
        _base, _key, instance, _instance_key, _timeout = _evolution_config()
        status_code, data = await _evo_post(
            f"/message/sendText/{instance}",
            {"number": phone, "text": message},
            use_instance_key=True,
        )
        if status_code >= 400:
            raise HTTPException(
                status_code,
                detail="Evolution API recusou o envio.",
            )
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
        _base, _key, instance, _instance_key, _timeout = _evolution_config()
        status_code, data = await _evo_post(
            f"/chat/findChats/{instance}",
            {"limit": limit},
            use_instance_key=True,
        )
        if status_code >= 400:
            return []
        return data if isinstance(data, (list, dict)) else []
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
    limit = body.get("limit", 30)

    try:
        _base, _key, instance, _instance_key, _timeout = _evolution_config()
        status_code, data = await _evo_post(
            f"/chat/findMessages/{instance}",
            {"where": {"key": {"remoteJid": jid}}, "limit": limit},
            use_instance_key=True,
        )
        if status_code >= 400:
            return []
        return data if isinstance(data, (list, dict)) else []
    except Exception:
        return []
