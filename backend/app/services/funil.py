# ── app/services/funil.py ────────────────────────────────────────────────────
# Funil de leads (Bloco D) — usa o ClientStatus já existente (lead → ativo →
# inativo/arquivado). Sem campo novo: a conversão é derivada do status atual.
# Quebra por canal de origem (ClientOrigem) quando disponível.
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ROLE_LEVEL
from app.models.user import User
from app.models.client import Client

ESTAGIOS = ["lead", "ativo", "inativo", "arquivado"]


def pode_ver_todos(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["admin"]


async def funil(db: AsyncSession, user: User) -> dict:
    """Distribuição por estágio + taxa de conversão + quebra por origem.

    Conversão = clientes 'ativo' / total de cadastros (lead+ativo+inativo+arquiv.).
    Admin+ vê toda a base; demais, apenas seus clientes (responsavel_id).
    """
    q = select(Client.status, Client.origem).where(Client.deleted_at.is_(None))
    if not pode_ver_todos(user):
        q = q.where(Client.responsavel_id == user.id)
    linhas = (await db.execute(q)).all()

    por_estagio = {e: 0 for e in ESTAGIOS}
    por_origem: dict[str, dict] = {}
    for status, origem in linhas:
        sv = status.value if status else "lead"
        if sv in por_estagio:
            por_estagio[sv] += 1
        canal = origem.value if origem else "(não informado)"
        o = por_origem.setdefault(canal, {"total": 0, "convertidos": 0})
        o["total"] += 1
        if sv == "ativo":
            o["convertidos"] += 1

    total = sum(por_estagio.values())
    convertidos = por_estagio["ativo"]

    # BUG-07: taxas SEMPRE na escala 0–100 (já em %), e None quando não há base
    # (divisão por zero). O frontend consome o valor direto, sem multiplicar por
    # 100 — antes a dupla multiplicação produzia "10000%".

    canais = []
    for canal, o in por_origem.items():
        canais.append({
            "origem": canal, "total": o["total"], "convertidos": o["convertidos"],
            "taxa_conversao": round(o["convertidos"] / o["total"] * 100, 1) if o["total"] else None,
        })
    canais.sort(key=lambda c: c["total"], reverse=True)

    return {
        "escopo": "toda a base" if pode_ver_todos(user) else "clientes do usuário",
        "total_cadastros": total,
        "por_estagio": por_estagio,
        "taxa_conversao_geral": round(convertidos / total * 100, 1) if total else None,
        "por_origem": canais,
        "nota": "Conversão derivada do status atual do cliente (lead → ativo).",
    }
