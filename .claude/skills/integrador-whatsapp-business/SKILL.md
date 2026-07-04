---
name: integrador-whatsapp-business
description: >
  Implementa integração WhatsApp Business API nos sistemas EJC, Verde Limp e S2/Licitação. Use SEMPRE que precisar enviar mensagens automáticas, notificações, alertas ou configurar atendimento via WhatsApp em qualquer um dos três sistemas. Cobre: Z-API (integração nacional), Meta WhatsApp Business API (oficial), Twilio, configuração de webhooks de entrada, chatbot básico, templates de mensagem, notificações de prazo EJC, alertas de licitação S2, check-in de equipe Verde Limp. WhatsApp é o canal principal dos três sistemas — esta skill é transversal. Acionado por: "WhatsApp API", "notificação WhatsApp", "mensagem automática WhatsApp", "bot WhatsApp", "integrar WhatsApp", "enviar WhatsApp sistema", "WhatsApp EJC", "WhatsApp Verde Limp", "WhatsApp S2", "alerta WhatsApp", "Z-API", "Meta WhatsApp Business".
---

# Integrador WhatsApp Business — EJC · Verde Limp · S2

## Contexto

```
USO POR SISTEMA:
  EJC:        alertas de prazo para advogados + comunicação com clientes
  Verde Limp: check-in de equipe em campo + notificações de OS para cliente
  S2:         alertas de novos editais + status de propostas para Dr. Clovis

OPÇÕES DE INTEGRAÇÃO:
  A) Z-API       — nacional, simples, ~R$89/mês, sem aprovação Meta
  B) Meta Official API — gratuito até 1.000 convs/mês, requer conta Business
  C) Twilio      — internacional, mais caro, confiável para volume alto

RECOMENDAÇÃO: Z-API para início (velocidade); migrar para Meta Oficial conforme escala
```

---

## 1. Z-API — Integração Simples (Recomendada)

### Configuração Básica

```python
# whatsapp/zapi.py
import httpx
import os
from typing import Optional

ZAPI_INSTANCE = os.getenv("ZAPI_INSTANCE")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")
ZAPI_BASE = f"https://api.z-api.io/instances/{ZAPI_INSTANCE}/token/{ZAPI_TOKEN}"

async def send_text(phone: str, message: str) -> dict:
    """Envia mensagem de texto simples"""
    phone_clean = phone.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
    if not phone_clean.startswith("55"):
        phone_clean = "55" + phone_clean
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{ZAPI_BASE}/send-text",
            json={"phone": phone_clean, "message": message},
            headers={"Client-Token": ZAPI_CLIENT_TOKEN},
            timeout=15
        )
        response.raise_for_status()
        return response.json()

async def send_document(phone: str, document_url: str, filename: str, caption: str = "") -> dict:
    """Envia documento (PDF)"""
    phone_clean = "55" + phone.replace("+55", "").replace("-", "").replace(" ", "")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{ZAPI_BASE}/send-document/url",
            json={"phone": phone_clean, "document": document_url, "fileName": filename, "caption": caption},
            headers={"Client-Token": ZAPI_CLIENT_TOKEN},
            timeout=30
        )
        return response.json()

async def send_button_list(phone: str, message: str, buttons: list[dict]) -> dict:
    """Envia mensagem com botões de ação"""
    phone_clean = "55" + phone.replace("+55", "").replace("-", "").replace(" ", "")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{ZAPI_BASE}/send-button-list",
            json={
                "phone": phone_clean,
                "message": message,
                "buttonList": {"buttons": buttons}
            },
            headers={"Client-Token": ZAPI_CLIENT_TOKEN},
            timeout=15
        )
        return response.json()
```

---

## 2. Meta WhatsApp Business API (Oficial)

### Configuração

```python
# whatsapp/meta.py
import httpx
import os

META_TOKEN = os.getenv("META_WHATSAPP_TOKEN")
META_PHONE_ID = os.getenv("META_PHONE_NUMBER_ID")
META_BASE = f"https://graph.facebook.com/v18.0/{META_PHONE_ID}"

async def send_template(phone: str, template_name: str, language: str = "pt_BR", components: list = None) -> dict:
    """Envia template aprovado pela Meta"""
    async with httpx.AsyncClient() as client:
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                "components": components or []
            }
        }
        response = await client.post(
            f"{META_BASE}/messages",
            json=payload,
            headers={"Authorization": f"Bearer {META_TOKEN}"},
            timeout=15
        )
        return response.json()

async def send_text_meta(phone: str, message: str) -> dict:
    """Envia texto livre (apenas dentro de janela de 24h)"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{META_BASE}/messages",
            json={
                "messaging_product": "whatsapp",
                "to": phone,
                "type": "text",
                "text": {"body": message}
            },
            headers={"Authorization": f"Bearer {META_TOKEN}"},
            timeout=15
        )
        return response.json()
```

---

## 3. Templates por Sistema

### EJC — Alertas Jurídicos

```python
# templates/ejc.py

def prazo_critico(case_number: str, ato: str, deadline: str, client_name: str) -> str:
    return f"""⚠️ *PRAZO CRÍTICO — EJC*

📁 Caso: {case_number}
📋 Ato: {ato}
📅 Vence: {deadline}
👤 Cliente: {client_name}

Acesse o EJC para providências."""

def novo_lead(lead_name: str, subject: str, area: str) -> str:
    return f"""🔔 *NOVO LEAD — EJC*

👤 Nome: {lead_name}
📋 Assunto: {subject}
⚖️ Área: {area}

Verifique no EJC para triagem."""

def cliente_notificacao(client_name: str, message: str) -> str:
    return f"""Olá, *{client_name}*!

{message}

Dúvidas? Responda esta mensagem.
— Dr. Clovis José Soares | OAB/MG"""
```

### Verde Limp — Operações

```python
# templates/verde_limp.py

def os_concluida(client_name: str, os_number: str, service: str, area: str) -> str:
    return f"""✅ *SERVIÇO CONCLUÍDO — Verde Limp*

Prezado(a) {client_name},

Informamos que o serviço foi realizado com sucesso:
📋 OS: {os_number}
🔧 Serviço: {service}
📐 Área: {area} m²

O relatório fotográfico será enviado em seguida.
Verde Limp — (31) 99907-4546"""

def checkin_equipe(leader: str, client: str, os_number: str) -> str:
    return f"""📍 *CHECK-IN — Verde Limp*

Líder: {leader}
Cliente: {client}
OS: {os_number}
⏰ Início: {__import__('datetime').datetime.now().strftime('%d/%m/%Y %H:%M')}

Execução iniciada."""

def alerta_vencimento_doc(doc_type: str, days_left: int) -> str:
    emoji = "🔴" if days_left <= 7 else "🟡"
    return f"""{emoji} *DOCUMENTO VENCENDO — Verde Limp*

📄 Documento: {doc_type}
⏳ Vence em: {days_left} dias

Acione o contador para renovação urgente."""
```

### S2 — Licitações

```python
# templates/s2.py

def novo_edital(orgao: str, objeto: str, valor: float, abertura: str, link: str, segmento: str) -> str:
    valor_fmt = f"R$ {valor:,.2f}" if valor else "Não informado"
    return f"""🔔 *RADAR S2 — Novo Edital*

🏛️ Órgão: {orgao}
📋 Objeto: {objeto[:100]}...
💰 Valor: {valor_fmt}
📅 Abertura: {abertura}
🏷️ Segmento: {segmento.upper()}

🔗 {link}

Status: NOVO — aguarda análise."""

def status_proposta(edital_id: str, status: str, notes: str = "") -> str:
    emoji_map = {"enviada": "📤", "vencedora": "🏆", "perdida": "❌", "cancelada": "⚪"}
    emoji = emoji_map.get(status.lower(), "📋")
    return f"""{emoji} *STATUS PROPOSTA — S2*

Edital: {edital_id}
Status: {status.upper()}
{f'Observação: {notes}' if notes else ''}"""
```

---

## 4. Webhook de Entrada (Receber mensagens)

```python
# whatsapp/webhook.py — FastAPI endpoint
from fastapi import APIRouter, Request, HTTPException
import hmac, hashlib, os

router = APIRouter(prefix="/webhook/whatsapp")

@router.get("/")
async def verify_webhook(hub_mode: str, hub_challenge: str, hub_verify_token: str):
    """Verificação Meta Webhook"""
    if hub_mode == "subscribe" and hub_verify_token == os.getenv("META_VERIFY_TOKEN"):
        return int(hub_challenge)
    raise HTTPException(status_code=403)

@router.post("/")
async def receive_message(request: Request):
    """Recebe mensagens de entrada"""
    payload = await request.json()
    # Meta format
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            messages = change.get("value", {}).get("messages", [])
            for msg in messages:
                phone = msg.get("from")
                text = msg.get("text", {}).get("body", "")
                await process_incoming_message(phone, text)
    return {"status": "ok"}

async def process_incoming_message(phone: str, text: str):
    """Roteamento básico por palavra-chave"""
    text_lower = text.lower().strip()
    if any(w in text_lower for w in ["prazo", "urgente", "caso"]):
        await send_text(phone, "Mensagem recebida. Encaminhando para o advogado responsável. 📋")
    elif any(w in text_lower for w in ["orçamento", "proposta", "serviço"]):
        await send_text(phone, "Obrigado pelo contato Verde Limp! Retornaremos em breve com o orçamento. 🌿")
    else:
        await send_text(phone, "Mensagem recebida! Entraremos em contato em breve. ✅")
```

---

## 5. Variáveis de Ambiente

```env
# Z-API
ZAPI_INSTANCE=SUA_INSTANCIA
ZAPI_TOKEN=SEU_TOKEN
ZAPI_CLIENT_TOKEN=SEU_CLIENT_TOKEN

# Meta WhatsApp Business (alternativa)
META_WHATSAPP_TOKEN=TOKEN_META
META_PHONE_NUMBER_ID=ID_NUMERO
META_VERIFY_TOKEN=TOKEN_VERIFICACAO_WEBHOOK

# Contatos fixos
WHATSAPP_CLOVIS=5531999074546
WHATSAPP_ADM=5531XXXXXXXXX
```

---

## 6. Boas Práticas

- Nunca enviar mensagens em massa sem consentimento (LGPD)
- Respeitar janela de 24h da Meta para mensagens livres
- Usar templates aprovados para notificações fora da janela
- Rate limiting: máximo 30 mensagens/minuto por instância Z-API
- Log de todas as mensagens enviadas (tabela whatsapp_logs)
- Fallback: se WhatsApp falhar, tentar email
- Nunca enviar dados sensíveis (CPF, números de processo) via WhatsApp sem criptografia
