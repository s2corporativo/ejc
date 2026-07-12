# ── app/routers/webhooks.py ──────────────────────────────────────────────────
# Webhooks externos. Z-API inbound: mensagem recebida no WhatsApp do
# escritório vira LEAD no CRM (se telefone desconhecido) + notificação.
# Rota PÚBLICA (Z-API chama de fora) — validada por Client-Token.
from __future__ import annotations
import hmac
import logging
import re
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Header, HTTPException
from sqlalchemy import func, or_, select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.rate_limit import consumir
from app.models.client import Client, ClientStatus, ClientOrigem, ClientTipo
from app.models.notification import Notification
from app.models.user import User, UserRole
from app.services.security_service import obter_ip_real

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
settings = get_settings()
logger = logging.getLogger("ejc.webhooks")


async def _rl_zapi(request: Request) -> None:
    """Rate limit do webhook público antes de parsear o payload.

    A rota não usa JWT por necessidade operacional: quem chama é a Z-API.
    O `Client-Token` continua sendo a autenticação efetiva, mas o limite por IP
    reduz brute force de token e DoS por chamadas/payloads repetidos. Usa o
    mesmo resolvedor de IP real do restante do EJC, respeitando X-Forwarded-For
    quando a aplicação está atrás do Nginx confiável.
    """
    await consumir("webhook_zapi", f"ip:{obter_ip_real(request)}", 120)


@router.post("/zapi", dependencies=[Depends(_rl_zapi)])
async def zapi_inbound(
    request: Request,
    client_token: str | None = Header(None, alias="Client-Token"),
):
    """Recebe mensagens do WhatsApp (Z-API). Cria lead se número novo."""
    # Validação do token (configurado no painel Z-API → Webhooks).
    # Sem token configurado o endpoint NÃO aceita chamadas — evita que terceiros
    # injetem mensagens forjadas num deploy ainda não configurado.
    if not settings.ZAPI_CLIENT_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Webhook indisponível: ZAPI_CLIENT_TOKEN não configurado.",
        )
    if not client_token or not hmac.compare_digest(client_token, settings.ZAPI_CLIENT_TOKEN):
        raise HTTPException(status_code=401, detail="Token inválido")

    try:
        body = await request.json()
    except Exception:
        return {"ok": True}  # payloads não-JSON: ignorar silenciosamente

    # Ignorar mensagens enviadas PELO escritório (fromMe) e grupos
    if body.get("fromMe") or body.get("isGroup"):
        return {"ok": True}

    telefone = re.sub(r"\D", "", str(body.get("phone") or ""))
    texto = (body.get("text", {}) or {}).get("message") \
            or body.get("message") or ""
    nome_push = body.get("senderName") or body.get("chatName") or "Contato WhatsApp"

    if not telefone or len(telefone) < 10:
        return {"ok": True}

    async with AsyncSessionLocal() as db:
        # Telefone já cadastrado? (whatsapp ou telefone)
        # Item 8 (auditoria pré-produção): antes carregava TODOS os clientes
        # (linhas inteiras, com PII) e casava o telefone em Python — O(n) de
        # memória/PII trafegada por mensagem recebida. telefone/whatsapp são
        # colunas em CLARO (diferente de CPF/CNPJ, que têm índice cego via
        # pii_crypto.hash_documento), então dá para filtrar direto no SQL:
        # normaliza os dígitos com regexp_replace (PG) e compara o sufixo de 8
        # dígitos — mesma semântica do match antigo, campo a campo. Se um dia
        # os telefones forem cifrados, migrar para o padrão de hash cego.
        sufixo = telefone[-8:]
        ja_existe = (await db.execute(
            select(Client.id).where(
                Client.deleted_at.is_(None),
                or_(
                    func.regexp_replace(
                        func.coalesce(Client.whatsapp, ""), r"\D", "", "g"
                    ).contains(sufixo),
                    func.regexp_replace(
                        func.coalesce(Client.telefone, ""), r"\D", "", "g"
                    ).contains(sufixo),
                ),
            ).limit(1)
        )).scalar_one_or_none() is not None

        if not ja_existe:
            lead = Client(
                id=str(uuid4()), tipo=ClientTipo.PF,
                status=ClientStatus.lead,
                nome=nome_push[:255],
                whatsapp=telefone,
                origem=ClientOrigem.whatsapp,
                observacoes=f"Lead automático via WhatsApp. "
                            f"1ª mensagem: {texto[:300]}",
            )
            db.add(lead)
            # LGPD: não gravar telefone de titular em log de aplicação
            # (agregadores/`docker logs` não têm base legal nem retenção
            # controlada). Mascara para só os 4 últimos dígitos.
            logger.info(f"Lead WhatsApp criado: ****{telefone[-4:]}")

            # Notificar admins/sócios
            staff = (await db.execute(select(User).where(
                User.role.in_([UserRole.superadmin, UserRole.admin, UserRole.socio]),
                User.is_active == True,
            ))).scalars().all()
            for u in staff:
                db.add(Notification(
                    id=str(uuid4()), user_id=u.id,
                    titulo="💬 Novo lead no WhatsApp",
                    mensagem=f"{nome_push} ({telefone}): {texto[:120]}",
                    tipo="lead", link="/clientes",
                ))
            await db.commit()

    return {"ok": True}
