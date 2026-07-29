#!/usr/bin/env python3
"""Cria/desativa usuário temporário de homologação na stack já em execução.

Executado somente dentro do container backend de produção pelo workflow manual de QA.
Não imprime senha nem segredo TOTP. O usuário é identificável por e-mail fixo com
marcador HOMOLOG e é desativado ao final; logs de auditoria permanecem íntegros.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.models.user import User, UserRole


def _env(nome: str) -> str:
    valor = os.environ.get(nome, "").strip()
    if not valor:
        raise SystemExit(f"Variável obrigatória ausente: {nome}")
    return valor


async def criar() -> None:
    email = _env("EJC_QA_EMAIL").lower()
    senha = _env("EJC_QA_PASSWORD")
    segredo = _env("EJC_QA_TOTP_SECRET")
    if "homolog" not in email and "qa" not in email:
        raise SystemExit("Barreira: e-mail temporário precisa conter homolog ou qa")
    async with AsyncSessionLocal() as db:
        existente = (
            await db.execute(
                select(User).where(User.email == email, User.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if existente:
            existente.is_active = False
            existente.deleted_at = datetime.now(timezone.utc)
            existente.email = f"{email}.encerrado.{int(datetime.now().timestamp())}"
            await db.commit()
        usuario = User(
            id=str(uuid4()),
            email=email,
            hashed_password=get_password_hash(senha),
            full_name="HOMOLOG-FICTICIO Advogado QA",
            role=UserRole.superadmin,
            must_change_password=False,
            # Base32 em claro é compatibilidade legada aceita pelo login; no primeiro
            # uso o próprio backend tenta recifrar oportunisticamente.
            totp_secret=segredo,
            totp_enabled=True,
            is_active=True,
            oab_number="MG 000000",
        )
        db.add(usuario)
        await db.commit()
        print(f"QA_USER_CREATED id={usuario.id}")


async def desativar() -> None:
    email = _env("EJC_QA_EMAIL").lower()
    async with AsyncSessionLocal() as db:
        usuarios = (
            await db.execute(
                select(User).where(User.email == email, User.deleted_at.is_(None))
            )
        ).scalars().all()
        for usuario in usuarios:
            usuario.is_active = False
            usuario.deleted_at = datetime.now(timezone.utc)
            usuario.email = f"{email}.encerrado.{usuario.id[:8]}"
        await db.commit()
        print(f"QA_USERS_DISABLED count={len(usuarios)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("acao", choices=("criar", "desativar"))
    args = parser.parse_args()
    asyncio.run(criar() if args.acao == "criar" else desativar())


if __name__ == "__main__":
    main()
