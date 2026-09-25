"""Identidade canônica conservadora de partes processuais.

Nunca funde pessoa física apenas por nome. Reutilização automática ocorre por:
1) client_id canônico;
2) CPF/CNPJ exato via HMAC;
3) pessoa jurídica por nome empresarial exatamente normalizado, quando único.
"""
from __future__ import annotations

import re
import unicodedata
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.process_integrity import PartyEntity
from app.services.pii_crypto import hash_documento, normalizar_documento


_EMPRESA_RE = re.compile(
    r"\b(LTDA|LIMITADA|S\s*A|SA|EIRELI|EPP|ME|SERVICOS|SERVIÇOS|COMERCIO|COMÉRCIO|INDUSTRIA|INDÚSTRIA)\b",
    re.IGNORECASE,
)


def normalizar_nome_parte(nome: str | None) -> str:
    txt = unicodedata.normalize("NFKD", str(nome or ""))
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = re.sub(r"[^A-Za-z0-9]+", " ", txt).casefold()
    return re.sub(r"\s+", " ", txt).strip()


def inferir_tipo_entidade(nome: str | None, documento: str | None = None) -> str:
    doc = normalizar_documento(documento) or ""
    if len(doc) == 11:
        return "PF"
    if len(doc) == 14:
        return "PJ"
    if _EMPRESA_RE.search(str(nome or "")):
        return "PJ"
    return "desconhecido"


async def resolver_entidade_parte(
    db: AsyncSession,
    *,
    nome: str,
    client_id: str | None = None,
    cpf_cnpj: str | None = None,
) -> PartyEntity:
    """Retorna/cria identidade canônica sem fusão arriscada por homônimo."""
    nome_limpo = str(nome or "").strip()
    if not nome_limpo:
        raise ValueError("Nome da parte é obrigatório")

    if client_id:
        existente = (
            await db.execute(
                select(PartyEntity).where(
                    PartyEntity.client_id == client_id,
                    PartyEntity.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existente:
            return existente

        cliente = await db.get(Client, client_id)
        tipo = getattr(getattr(cliente, "tipo", None), "value", None) or "desconhecido"
        display = getattr(cliente, "nome_exibicao", None) or nome_limpo
        entidade = PartyEntity(
            id=str(uuid4()),
            client_id=client_id,
            entity_type=tipo if tipo in {"PF", "PJ"} else "desconhecido",
            display_name=display[:255],
            normalized_name=normalizar_nome_parte(display)[:255],
            cpf_cnpj_hash=(getattr(cliente, "cpf_hash", None) or getattr(cliente, "cnpj_hash", None)),
            aliases=[],
        )
        db.add(entidade)
        await db.flush()
        return entidade

    doc = normalizar_documento(cpf_cnpj)
    if doc:
        blind = hash_documento(doc)
        existente = (
            await db.execute(
                select(PartyEntity).where(
                    PartyEntity.cpf_cnpj_hash == blind,
                    PartyEntity.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existente:
            return existente
    else:
        blind = None

    tipo = inferir_tipo_entidade(nome_limpo, doc)
    nome_norm = normalizar_nome_parte(nome_limpo)

    # Só nome empresarial exato pode ser reutilizado automaticamente.
    if tipo == "PJ" and nome_norm:
        candidatos = (
            await db.execute(
                select(PartyEntity).where(
                    PartyEntity.entity_type == "PJ",
                    PartyEntity.normalized_name == nome_norm,
                    PartyEntity.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        if len(candidatos) == 1:
            return candidatos[0]

    entidade = PartyEntity(
        id=str(uuid4()),
        entity_type=tipo,
        display_name=nome_limpo[:255],
        normalized_name=nome_norm[:255],
        cpf_cnpj_hash=blind,
        aliases=[],
    )
    db.add(entidade)
    await db.flush()
    return entidade
