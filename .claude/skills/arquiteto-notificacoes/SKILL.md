---
name: arquiteto-notificacoes
description: >
  Projeta e implementa o sistema de notificações dos sistemas EJC, Verde Limp e S2: alertas de prazo por email, WhatsApp, push notification no navegador e notificações internas no sistema. Use SEMPRE que precisar implementar qualquer tipo de notificação automática, alerta de vencimento, comunicado para advogados, clientes ou equipe de campo. Cobre: serviço de email SMTP/SendGrid, integração com WhatsApp (via integrador-whatsapp-business), notificações push browser (Web Push API), sistema de notificações internas do EJC (sino no header), scheduler de alertas com APScheduler/Celery, templates de mensagem por evento. Acionado por: "sistema de notificações", "alerta de prazo email", "notificação push", "alertas automáticos EJC", "email automático", "sino notificação", "push notification", "APScheduler", "alerta vencimento email", "notificação interna EJC".
---

# Sistema de Notificações — EJC · Verde Limp · S2

## Arquitetura

```
CANAIS DISPONÍVEIS:
  1. Email (SMTP / SendGrid)
  2. WhatsApp (→ delegar para integrador-whatsapp-business)
  3. Push Browser (Web Push API — notificação mesmo com aba fechada)
  4. Notificação Interna EJC (sino no header — DB polling)

MOTOR DE AGENDAMENTO:
  Opção A: APScheduler (leve, embutido no FastAPI) — recomendado MVP
  Opção B: Celery + Redis (quando volume aumentar)

TABELA CENTRAL: notifications (todas as notificações — estado, canal, enviado, lido)
```

---

## 1. Modelo de Dados

```python
# models/notification.py
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum

class NotificationChannel(str, enum.Enum):
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    PUSH = "push"
    INTERNAL = "internal"

class NotificationStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    READ = "read"

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    channel = Column(String(20), nullable=False)  # NotificationChannel
    event_type = Column(String(50), nullable=False)  # DEADLINE_ALERT, OS_CONCLUIDA, etc.
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    reference_type = Column(String(50), nullable=True)  # cases, deadlines, etc.
    reference_id = Column(Integer, nullable=True)
    status = Column(String(20), default="pending")
    scheduled_for = Column(DateTime(timezone=True), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    extra_data = Column(Text, nullable=True)  # JSON para dados extras
```

---

## 2. Serviço de Email (SMTP)

```python
# services/email.py
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os
from typing import Optional
from jinja2 import Environment, BaseLoader
import logging

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
FROM_NAME = os.getenv("EMAIL_FROM_NAME", "EJC — Ecossistema Jurídico")
FROM_EMAIL = os.getenv("SMTP_USER")

# Templates HTML embutidos
EMAIL_TEMPLATES = {
    "deadline_alert": """
<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
<div style="background:#1e40af;padding:20px;text-align:center">
  <h2 style="color:white;margin:0">⚠️ Alerta de Prazo — EJC</h2>
</div>
<div style="padding:24px;background:#f9fafb">
  <p>Olá, <strong>{{ advogado_name }}</strong>!</p>
  <p>O seguinte prazo está se aproximando:</p>
  <table style="width:100%;border-collapse:collapse;margin:16px 0">
    <tr><td style="padding:8px;background:#e5e7eb;font-weight:bold">Caso</td><td style="padding:8px">{{ case_number }}</td></tr>
    <tr><td style="padding:8px;background:#e5e7eb;font-weight:bold">Ato</td><td style="padding:8px">{{ ato }}</td></tr>
    <tr><td style="padding:8px;background:#e5e7eb;font-weight:bold">Vencimento</td><td style="padding:8px;color:#dc2626;font-weight:bold">{{ deadline_date }}</td></tr>
    <tr><td style="padding:8px;background:#e5e7eb;font-weight:bold">Cliente</td><td style="padding:8px">{{ client_name }}</td></tr>
  </table>
  <a href="{{ ejc_url }}/casos/{{ case_id }}" style="background:#1e40af;color:white;padding:12px 24px;text-decoration:none;border-radius:6px">Abrir no EJC</a>
</div>
<div style="padding:12px;text-align:center;color:#9ca3af;font-size:12px">
  EJC — Ecossistema Jurídico | Gerado automaticamente
</div>
</body></html>
""",
    "new_lead": """
<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
<div style="background:#059669;padding:20px;text-align:center">
  <h2 style="color:white;margin:0">🔔 Novo Lead — EJC</h2>
</div>
<div style="padding:24px"><p><strong>{{ lead_name }}</strong> entrou em contato.</p>
<p><strong>Assunto:</strong> {{ subject }}</p>
<p><strong>Área:</strong> {{ area }}</p>
<a href="{{ ejc_url }}/leads" style="background:#059669;color:white;padding:12px 24px;text-decoration:none;border-radius:6px">Ver Lead</a>
</div></body></html>
"""
}

def render_template(template_name: str, context: dict) -> str:
    template_str = EMAIL_TEMPLATES.get(template_name, "<p>{{ message }}</p>")
    env = Environment(loader=BaseLoader())
    template = env.from_string(template_str)
    return template.render(**context)

async def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    attachment_path: Optional[str] = None
) -> bool:
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{FROM_NAME} <{FROM_EMAIL}>"
        msg["To"] = to_email

        msg.attach(MIMEText(html_content, "html", "utf-8"))

        if attachment_path:
            with open(attachment_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                import os
                part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(attachment_path)}")
                msg.attach(part)

        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(FROM_EMAIL, to_email, msg.as_string())
        return True
    except Exception as e:
        logger.error(f"Email send error to {to_email}: {e}")
        return False
```

---

## 3. Scheduler APScheduler (embutido no FastAPI)

```python
# scheduler/jobs.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from app.database import SessionLocal
import logging

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@scheduler.scheduled_job(CronTrigger(hour="8,12,17", day_of_week="mon-fri"))
async def check_critical_deadlines():
    """Verifica prazos críticos 3x/dia em dias úteis"""
    db = SessionLocal()
    try:
        today = date.today()
        critical_date = today + timedelta(days=2)
        deadlines = db.execute("""
            SELECT d.*, c.case_number, c.id as case_id, cl.name as client_name,
                   u.name as advogado_name, u.email as advogado_email, u.phone as advogado_phone
            FROM deadlines d
            JOIN cases c ON d.case_id = c.id
            JOIN clients cl ON c.client_id = cl.id
            LEFT JOIN users u ON c.responsible_user_id = u.id
            WHERE d.status = 'pendente'
            AND d.deadline_date <= :critical_date
            AND d.deadline_date >= :today
            AND d.deleted_at IS NULL
        """, {"critical_date": critical_date, "today": today}).fetchall()

        for deadline in deadlines:
            # Enviar email
            if deadline.advogado_email:
                from services.email import send_email, render_template
                html = render_template("deadline_alert", {
                    "advogado_name": deadline.advogado_name,
                    "case_number": deadline.case_number,
                    "ato": deadline.description,
                    "deadline_date": deadline.deadline_date.strftime("%d/%m/%Y"),
                    "client_name": deadline.client_name,
                    "case_id": deadline.case_id,
                    "ejc_url": os.getenv("EJC_URL", "http://localhost:3000")
                })
                await send_email(deadline.advogado_email, f"⚠️ Prazo Crítico — {deadline.case_number}", html)

            # Gravar notificação interna
            db.execute("""
                INSERT INTO notifications (user_id, channel, event_type, title, message, reference_type, reference_id)
                VALUES (:uid, 'internal', 'DEADLINE_ALERT', :title, :msg, 'deadlines', :did)
            """, {
                "uid": deadline.responsible_user_id,
                "title": f"Prazo crítico: {deadline.case_number}",
                "msg": f"Vence em {deadline.deadline_date}: {deadline.description}",
                "did": deadline.id
            })
        db.commit()
        logger.info(f"Deadline check: {len(deadlines)} alertas processados")
    except Exception as e:
        logger.error(f"Scheduler error: {e}")
    finally:
        db.close()

# Iniciar scheduler junto com a app
# Em app/main.py:
# @app.on_event("startup")
# async def startup():
#     from scheduler.jobs import scheduler
#     scheduler.start()
```

---

## 4. Notificações Internas EJC (sino no header)

```python
# routers/notifications.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])

@router.get("/unread-count")
async def unread_count(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    count = db.execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id=? AND status='pending' AND channel='internal'",
        (current_user.id,)
    ).scalar()
    return {"count": count}

@router.get("/")
async def list_notifications(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    items = db.execute(
        "SELECT * FROM notifications WHERE user_id=? AND channel='internal' ORDER BY created_at DESC LIMIT ?",
        (current_user.id, limit)
    ).fetchall()
    return {"data": [dict(i) for i in items]}

@router.patch("/{notification_id}/read")
async def mark_read(notification_id: int, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    db.execute(
        "UPDATE notifications SET status='read', read_at=NOW() WHERE id=? AND user_id=?",
        (notification_id, current_user.id)
    )
    db.commit()
    return {"ok": True}
```

---

## 5. Variáveis de Ambiente

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=adm@vetmg.com.br
SMTP_PASS=APP_PASSWORD_16_CHARS
EMAIL_FROM_NAME=EJC — Ecossistema Jurídico
EJC_URL=https://ejc.seudominio.com.br
```

---

## 6. Regras

- APScheduler: instanciar uma única vez na startup da app (evitar duplicação)
- Notificações internas: polling a cada 30s no frontend (evitar WebSocket no MVP)
- Email falhou: gravar status='failed' + error_message → retry máximo 2x
- Nunca enviar email com dados de processo para endereços não verificados
- LGPD: não incluir informações de terceiros nos emails automáticos
- Rate limit de email: máximo 100 emails/dia no SMTP gratuito Google
