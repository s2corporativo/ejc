# ── app/services/conflito_service.py ─────────────────────────────────────────
# Detector de conflito de interesses (EOAB arts. 34-35).
#
# NÚCLEO DE MATCHING COMPARTILHADO: as primitivas `_clientes_por_documentos`,
# `_clientes_por_nome` e `_casos_por_parte_contraria` são a ÚNICA implementação
# das regras de correspondência (hash-aware) usada por AMBAS as funções públicas
# de conflito do sistema:
#   • detectar_conflito()          (este módulo)  → schema {classificacao, achados, bloqueio}
#   • verificar_conflito()  (conflito_interesses) → schema {resultado, matches, recomendacao, ...}
# Cada função pública só FORMATA seu próprio schema de saída; a regra de casar
# (texto puro + cpf_hash/cnpj_hash, nome ILIKE, parte contrária em casos) é a
# mesma para as duas — elimina a antiga divergência entre elas.
#
# IMPORTANTE: Case.parte_contraria é TEXTO LIVRE (String 255) — sem CPF/CNPJ.
# Portanto o cruzamento por parte contrária é SEMPRE por nome (ILIKE).
from __future__ import annotations
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.case import Case, CaseStatus


def _padrao_like(nome: str) -> str:
    """Padrão ILIKE com wildcards do INPUT escapados.

    Sem isto, um nome contendo `%`/`_` vira curinga: `"____"` casa qualquer
    registro com 4+ caracteres e `"%Ab%"` transforma a checagem ética num
    oráculo de substring de 1 caractere (o piso de 4 chars é contornado).
    Usar sempre com `.ilike(padrao, escape="\\\\")`."""
    limpo = nome.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{limpo}%"


async def _clientes_por_documentos(
    db: AsyncSession,
    docs: list[Optional[str]],
    *,
    ignorar_client_id: Optional[str] = None,
    limit: int = 10,
) -> list[Client]:
    """Clientes ATIVOS cujo CPF ou CNPJ casa com algum documento informado.

    Cutover C6/LGPD: não há mais cpf/cnpj em texto puro para comparar — o
    matching é feito EXCLUSIVAMENTE pelo índice cego determinístico (HMAC do
    documento normalizado). Igualdade exata: a checagem ética (EOAB) exige o
    documento COMPLETO, então falso-negativo por documento parcial é esperado
    (o cruzamento por nome cobre o resto)."""
    from app.services.pii_crypto import normalizar_documento, hash_documento

    conds = []
    for doc in docs:
        norm = normalizar_documento(doc)
        if not norm:
            continue
        h = hash_documento(norm)
        conds.append(Client.cpf_hash == h)
        conds.append(Client.cnpj_hash == h)
    if not conds:
        return []
    q = select(Client).where(or_(*conds), Client.deleted_at.is_(None))
    if ignorar_client_id:
        q = q.where(Client.id != ignorar_client_id)
    return list((await db.execute(q.limit(limit))).scalars().all())


async def _clientes_por_nome(
    db: AsyncSession,
    nome: Optional[str],
    *,
    ignorar_client_id: Optional[str] = None,
    limit: int = 10,
) -> list[Client]:
    """Clientes ATIVOS cujo nome/razão social casa (ILIKE) com o nome informado.
    Piso de 4 caracteres para evitar correspondências espúrias."""
    if not nome or len(nome) < 4:
        return []
    padrao = _padrao_like(nome)
    q = select(Client).where(
        or_(
            Client.nome.ilike(padrao, escape="\\"),
            Client.razao_social.ilike(padrao, escape="\\"),
        ),
        Client.deleted_at.is_(None),
    )
    if ignorar_client_id:
        q = q.where(Client.id != ignorar_client_id)
    return list((await db.execute(q.limit(limit))).scalars().all())


async def _casos_por_parte_contraria(
    db: AsyncSession,
    nome: Optional[str],
    *,
    somente_ativos: bool = False,
    ignorar_case_id: Optional[str] = None,
    limit: int = 10,
) -> list[Case]:
    """Casos onde `nome` aparece como parte contrária (ILIKE, texto livre).
    `somente_ativos` exclui encerrado/arquivado. Piso de 4 caracteres."""
    if not nome or len(nome) < 4:
        return []
    q = select(Case).where(
        Case.parte_contraria.ilike(_padrao_like(nome), escape="\\"),
        Case.deleted_at.is_(None),
    )
    if somente_ativos:
        q = q.where(Case.status.notin_([CaseStatus.encerrado, CaseStatus.arquivado]))
    if ignorar_case_id:
        q = q.where(Case.id != ignorar_case_id)
    return list((await db.execute(q.limit(limit))).scalars().all())


async def detectar_conflito(
    db: AsyncSession,
    nome: Optional[str] = None,
    cpf: Optional[str] = None,
    cnpj: Optional[str] = None,
    parte_contraria: Optional[str] = None,
    ignorar_client_id: Optional[str] = None,
) -> dict:
    """
    Varre clientes e partes contrárias de casos ativos em busca de conflito.
    Retorna {classificacao, achados, bloqueio}. Nunca levanta exceção de regra
    de negócio — quem chama decide o que fazer (HITL).

    Usa o núcleo de matching compartilhado (mesmas regras de verificar_conflito).
    """
    achados: list[dict] = []

    # 1. Mesmo nome/documento já é cliente existente (doc via texto puro + hash).
    clientes = await _clientes_por_documentos(
        db, [cpf, cnpj], ignorar_client_id=ignorar_client_id
    )
    ja_vistos = {c.id for c in clientes}
    for c in await _clientes_por_nome(db, nome, ignorar_client_id=ignorar_client_id):
        if c.id not in ja_vistos:
            clientes.append(c)
            ja_vistos.add(c.id)
    for c in clientes:
        achados.append({
            "tipo": "cliente_existente",
            "id": c.id, "nome": c.nome or c.razao_social,
            "documento": c.documento_plain,
        })

    # 2. Nome do novo cliente / parte contrária aparece como parte contrária de
    #    algum caso (varre todos os casos não deletados).
    casos_vistos: set[str] = set()
    for n in [nome, parte_contraria]:
        for c in await _casos_por_parte_contraria(db, n):
            if c.id in casos_vistos:
                continue
            casos_vistos.add(c.id)
            achados.append({
                "tipo": "parte_contraria_em_caso",
                "case_id": c.id, "titulo": c.titulo,
                "parte": c.parte_contraria,
            })

    # 3. A parte contrária informada já é cliente nosso (CONFLITO grave).
    for c in await _clientes_por_nome(db, parte_contraria, limit=5):
        achados.append({
            "tipo": "CONFLITO_parte_contraria_eh_cliente",
            "id": c.id, "nome": c.nome or c.razao_social,
            "documento": c.documento_plain,
        })

    conflito_grave = any("CONFLITO" in a["tipo"] for a in achados)
    classificacao = (
        "CONFLITO_IDENTIFICADO" if conflito_grave
        else "POSSIVEL_CONFLITO" if achados
        else "SEM_CONFLITO"
    )
    return {
        "classificacao": classificacao,
        "achados": achados,
        "bloqueio": conflito_grave,
    }
