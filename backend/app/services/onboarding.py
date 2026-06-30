# ── app/services/onboarding.py ───────────────────────────────────────────────
# Onboarding de clientes (Bloco D) — status de entrada por cliente, derivado de
# dados que já existem: cadastro, contato, procuração, contrato e documentos.
# Sem campo novo. Cada item aponta o que falta, servindo de checklist acionável.
from __future__ import annotations

from datetime import date

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ROLE_LEVEL
from app.models.user import User
from app.models.client import Client, ClientTipo, ClientStatus
from app.models.procuracao import Procuracao
from app.models.document import Document
from app.models.fee import Fee


def pode_ver_todos(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["admin"]


async def _checklist(db: AsyncSession, client: Client, hoje: date) -> dict:
    """Monta o checklist de onboarding de um cliente a partir dos dados reais."""
    # 1) cadastro básico conforme tipo
    if client.tipo == ClientTipo.PJ:
        cadastro_ok = bool((client.razao_social or "").strip() and (client.cnpj or "").strip())
        cadastro_det = "Razão social e CNPJ" + ("" if cadastro_ok else " — incompletos")
    else:
        cadastro_ok = bool((client.nome or "").strip() and (client.cpf or "").strip())
        cadastro_det = "Nome e CPF" + ("" if cadastro_ok else " — incompletos")

    # 2) contato
    contato_ok = bool((client.email or "").strip() or (client.telefone or "").strip()
                      or (client.whatsapp or "").strip())

    # 3) procuração ativa
    proc = (await db.execute(
        select(func.count()).select_from(Procuracao).where(
            Procuracao.client_id == client.id, Procuracao.deleted_at.is_(None),
            Procuracao.revogada.is_(False),
            (Procuracao.data_validade.is_(None)) | (Procuracao.data_validade >= hoje),
        ))).scalar() or 0
    proc_ok = proc > 0

    # 4) contrato de honorários (documento tipo=contrato OU honorário cadastrado)
    docs_contrato = (await db.execute(
        select(func.count()).select_from(Document).where(
            Document.client_id == client.id, Document.deleted_at.is_(None),
            func.lower(Document.tipo) == "contrato",
        ))).scalar() or 0
    fees = (await db.execute(
        select(func.count()).select_from(Fee).where(
            Fee.client_id == client.id, Fee.deleted_at.is_(None)
        ))).scalar() or 0
    contrato_ok = docs_contrato > 0 or fees > 0

    # 5) ao menos um documento anexado
    docs_total = (await db.execute(
        select(func.count()).select_from(Document).where(
            Document.client_id == client.id, Document.deleted_at.is_(None)
        ))).scalar() or 0
    docs_ok = docs_total > 0

    itens = [
        {"item": "Cadastro básico", "ok": cadastro_ok, "detalhe": cadastro_det},
        {"item": "Contato (e-mail/telefone)", "ok": contato_ok,
         "detalhe": "" if contato_ok else "Sem e-mail/telefone/WhatsApp"},
        {"item": "Procuração ativa", "ok": proc_ok,
         "detalhe": "" if proc_ok else "Sem procuração vigente"},
        {"item": "Contrato de honorários", "ok": contrato_ok,
         "detalhe": "" if contrato_ok else "Sem contrato/honorário registrado"},
        {"item": "Documentos anexados", "ok": docs_ok,
         "detalhe": f"{docs_total} documento(s)" if docs_ok else "Nenhum documento no GED"},
    ]
    concluidos = sum(1 for i in itens if i["ok"])
    pendencias = [i["item"] for i in itens if not i["ok"]]
    return {
        "client_id": client.id,
        "nome": client.nome or client.razao_social or "(sem nome)",
        "tipo": client.tipo.value,
        "status": client.status.value if client.status else None,
        "itens": itens,
        "percentual_completo": round(concluidos / len(itens) * 100),
        "pendencias": pendencias,
        "onboarding_completo": not pendencias,
    }


async def status_cliente(db: AsyncSession, client: Client) -> dict:
    return await _checklist(db, client, date.today())


async def pendencias(db: AsyncSession, user: User, limit: int = 50) -> dict:
    """Clientes com onboarding incompleto (mais incompletos primeiro)."""
    hoje = date.today()
    q = select(Client).where(
        Client.deleted_at.is_(None),
        Client.status != ClientStatus.arquivado,
    )
    if not pode_ver_todos(user):
        q = q.where(Client.responsavel_id == user.id)
    clientes = (await db.execute(q.limit(500))).scalars().all()

    checklists = [await _checklist(db, c, hoje) for c in clientes]
    incompletos = [c for c in checklists if not c["onboarding_completo"]]
    incompletos.sort(key=lambda c: c["percentual_completo"])
    return {
        "escopo": "toda a base" if pode_ver_todos(user) else "clientes do usuário",
        "total_clientes": len(checklists),
        "completos": sum(1 for c in checklists if c["onboarding_completo"]),
        "incompletos": len(incompletos),
        "clientes_pendentes": incompletos[:limit],
    }
