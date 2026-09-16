# ── app/services/onboarding.py ───────────────────────────────────────────────
# Onboarding de clientes (Bloco D) — status de entrada por cliente, derivado de
# dados que já existem: cadastro, contato, procuração, contrato e documentos.
# Sem campo novo. Cada item aponta o que falta, servindo de checklist acionável.
from __future__ import annotations

from datetime import date
from typing import TypedDict

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_ownership import ids_clientes_visiveis, visao_total_clientes
from app.models.client import Client, ClientStatus, ClientTipo
from app.models.document import Document
from app.models.fee import Fee
from app.models.procuracao import Procuracao
from app.models.user import User


class _FatosOnboarding(TypedDict):
    procuracoes_ativas: int
    documentos_total: int
    contratos_documento: int
    honorarios: int


def _fatos_vazios() -> _FatosOnboarding:
    return {
        "procuracoes_ativas": 0,
        "documentos_total": 0,
        "contratos_documento": 0,
        "honorarios": 0,
    }


def pode_ver_todos(user: User) -> bool:
    """Compatibilidade: delega à fonte canônica de visibilidade de Clientes."""
    return visao_total_clientes(user)


async def _carregar_fatos_em_lote(
    db: AsyncSession,
    client_ids: list[str],
    hoje: date,
) -> dict[str, _FatosOnboarding]:
    """Carrega fatos objetivos do onboarding em três consultas agregadas.

    A implementação anterior executava quatro consultas por cliente dentro de
    ``pendencias``. Com até 500 clientes, isso permitia milhares de round-trips
    ao PostgreSQL. Aqui o custo passa a ser constante: procurações, documentos
    e honorários são agregados por ``client_id`` e combinados em memória.
    """
    if not client_ids:
        return {}

    fatos: dict[str, _FatosOnboarding] = {
        client_id: _fatos_vazios() for client_id in client_ids
    }

    procuracoes = (
        await db.execute(
            select(Procuracao.client_id, func.count(Procuracao.id))
            .where(
                Procuracao.client_id.in_(client_ids),
                Procuracao.deleted_at.is_(None),
                Procuracao.revogada.is_(False),
                (Procuracao.data_validade.is_(None))
                | (Procuracao.data_validade >= hoje),
            )
            .group_by(Procuracao.client_id)
        )
    ).all()
    for client_id, total in procuracoes:
        fatos[client_id]["procuracoes_ativas"] = int(total or 0)

    documentos = (
        await db.execute(
            select(
                Document.client_id,
                func.count(Document.id),
                func.sum(
                    case(
                        (func.lower(Document.tipo) == "contrato", 1),
                        else_=0,
                    )
                ),
            )
            .where(
                Document.client_id.in_(client_ids),
                Document.deleted_at.is_(None),
            )
            .group_by(Document.client_id)
        )
    ).all()
    for client_id, total, contratos in documentos:
        fatos[client_id]["documentos_total"] = int(total or 0)
        fatos[client_id]["contratos_documento"] = int(contratos or 0)

    honorarios = (
        await db.execute(
            select(Fee.client_id, func.count(Fee.id))
            .where(
                Fee.client_id.in_(client_ids),
                Fee.deleted_at.is_(None),
            )
            .group_by(Fee.client_id)
        )
    ).all()
    for client_id, total in honorarios:
        fatos[client_id]["honorarios"] = int(total or 0)

    return fatos


def _montar_checklist(client: Client, fatos: _FatosOnboarding) -> dict:
    """Monta o checklist sem I/O a partir de fatos previamente agregados."""
    # 1) cadastro básico conforme tipo
    # Cutover C6/LGPD: presença do documento verificada pelo campo cifrado
    # (cpf_enc/cnpj_enc) — não há mais coluna em texto puro.
    if client.tipo == ClientTipo.PJ:
        cadastro_ok = bool((client.razao_social or "").strip() and client.cnpj_enc)
        cadastro_det = "Razão social e CNPJ" + ("" if cadastro_ok else " — incompletos")
    else:
        cadastro_ok = bool((client.nome or "").strip() and client.cpf_enc)
        cadastro_det = "Nome e CPF" + ("" if cadastro_ok else " — incompletos")

    # 2) contato
    contato_ok = bool(
        (client.email or "").strip()
        or (client.telefone or "").strip()
        or (client.whatsapp or "").strip()
    )

    # 3) procuração ativa
    proc_ok = fatos["procuracoes_ativas"] > 0

    # 4) contrato de honorários (documento tipo=contrato OU honorário cadastrado)
    contrato_ok = fatos["contratos_documento"] > 0 or fatos["honorarios"] > 0

    # 5) ao menos um documento anexado
    docs_total = fatos["documentos_total"]
    docs_ok = docs_total > 0

    itens = [
        {"item": "Cadastro básico", "ok": cadastro_ok, "detalhe": cadastro_det},
        {
            "item": "Contato (e-mail/telefone)",
            "ok": contato_ok,
            "detalhe": "" if contato_ok else "Sem e-mail/telefone/WhatsApp",
        },
        {
            "item": "Procuração ativa",
            "ok": proc_ok,
            "detalhe": "" if proc_ok else "Sem procuração vigente",
        },
        {
            "item": "Contrato de honorários",
            "ok": contrato_ok,
            "detalhe": "" if contrato_ok else "Sem contrato/honorário registrado",
        },
        {
            "item": "Documentos anexados",
            "ok": docs_ok,
            "detalhe": f"{docs_total} documento(s)" if docs_ok else "Nenhum documento no GED",
        },
    ]
    concluidos = sum(1 for item in itens if item["ok"])
    pendencias = [item["item"] for item in itens if not item["ok"]]
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
    fatos = await _carregar_fatos_em_lote(db, [client.id], date.today())
    return _montar_checklist(client, fatos.get(client.id, _fatos_vazios()))


async def pendencias(db: AsyncSession, user: User, limit: int = 50) -> dict:
    """Clientes visíveis com onboarding incompleto (mais incompletos primeiro)."""
    hoje = date.today()
    q = select(Client).where(
        Client.deleted_at.is_(None),
        Client.status != ClientStatus.arquivado,
    )
    if not visao_total_clientes(user):
        # Fonte única com Clientes/Dossiê/Pendências: responsável direto OU
        # advogado responsável/auxiliar em caso não excluído. A implementação
        # anterior usava só `responsavel_id`, ocultando cliente legitimamente
        # visível por vínculo em caso e divergindo do restante do CRM.
        q = q.where(Client.id.in_(ids_clientes_visiveis(user)))
    clientes = (await db.execute(q.limit(500))).scalars().all()

    fatos = await _carregar_fatos_em_lote(
        db,
        [cliente.id for cliente in clientes],
        hoje,
    )
    checklists = [
        _montar_checklist(cliente, fatos.get(cliente.id, _fatos_vazios()))
        for cliente in clientes
    ]
    incompletos = [c for c in checklists if not c["onboarding_completo"]]
    incompletos.sort(key=lambda c: c["percentual_completo"])
    return {
        "escopo": "toda a base" if visao_total_clientes(user) else "clientes visíveis do usuário",
        "total_clientes": len(checklists),
        "completos": sum(1 for c in checklists if c["onboarding_completo"]),
        "incompletos": len(incompletos),
        "clientes_pendentes": incompletos[:limit],
    }
