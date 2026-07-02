# ── app/services/conflito_service.py ─────────────────────────────────────────
# Detector de conflito de interesses (EOAB arts. 34-35).
# Reutilizável: usado pelo endpoint /clients/verificar-conflito E pelo cadastro.
# IMPORTANTE: Case.parte_contraria é TEXTO LIVRE (String 255) — sem CPF/CNPJ.
# Portanto o cruzamento por parte contrária é SEMPRE por nome (ILIKE).
from __future__ import annotations
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.case import Case


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
    """
    achados: list[dict] = []

    # 1. Mesmo nome/documento já é cliente existente.
    # Bloco 6a (LGPD): casa tanto pelo texto puro (clientes ainda não
    # migrados) quanto pelo hash determinístico (clientes já com PII
    # cifrada) — nenhum dos dois lados sozinho cobre os dois estados de
    # transição. Verificação ética (EOAB) não pode ter falso-negativo aqui.
    from app.services.pii_crypto import normalizar_documento, hash_documento
    cpf_norm = normalizar_documento(cpf)
    cnpj_norm = normalizar_documento(cnpj)
    cpf_hash = hash_documento(cpf_norm) if cpf_norm else None
    cnpj_hash = hash_documento(cnpj_norm) if cnpj_norm else None
    conds = []
    if cpf:
        conds.append(Client.cpf == cpf)
    if cpf_hash:
        conds.append(Client.cpf_hash == cpf_hash)
    if cnpj:
        conds.append(Client.cnpj == cnpj)
    if cnpj_hash:
        conds.append(Client.cnpj_hash == cnpj_hash)
    if nome and len(nome) >= 4:
        conds.append(Client.nome.ilike(f"%{nome}%"))
        conds.append(Client.razao_social.ilike(f"%{nome}%"))
    if conds:
        q = select(Client).where(or_(*conds), Client.deleted_at.is_(None))
        if ignorar_client_id:
            q = q.where(Client.id != ignorar_client_id)
        for c in (await db.execute(q.limit(10))).scalars().all():
            achados.append({
                "tipo": "cliente_existente",
                "id": c.id, "nome": c.nome or c.razao_social,
            })

    # 2. Nome do novo cliente aparece como parte contrária de algum caso
    nomes_busca = [n for n in [nome, parte_contraria] if n and len(n) >= 4]
    for n in nomes_busca:
        rows = (await db.execute(
            select(Case).where(
                Case.parte_contraria.ilike(f"%{n}%"),
                Case.deleted_at.is_(None),
            ).limit(10)
        )).scalars().all()
        for c in rows:
            achados.append({
                "tipo": "parte_contraria_em_caso",
                "case_id": c.id, "titulo": c.titulo,
                "parte": c.parte_contraria,
            })

    # 3. A parte contrária informada já é cliente nosso (CONFLITO grave)
    if parte_contraria and len(parte_contraria) >= 4:
        rows = (await db.execute(
            select(Client).where(
                or_(
                    Client.nome.ilike(f"%{parte_contraria}%"),
                    Client.razao_social.ilike(f"%{parte_contraria}%"),
                ),
                Client.deleted_at.is_(None),
            ).limit(5)
        )).scalars().all()
        for c in rows:
            achados.append({
                "tipo": "CONFLITO_parte_contraria_eh_cliente",
                "id": c.id, "nome": c.nome or c.razao_social,
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
