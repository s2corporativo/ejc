#!/usr/bin/env python3
"""Cria/desativa usuários temporários de homologação na stack em execução.

Cria um superadmin QA e, quando as variáveis opcionais forem fornecidas, um
cliente_externo vinculado a cliente 100% fictício. Não imprime senha/TOTP.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from uuid import uuid4

sys.path.insert(0, "/app")

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.models.client import Client, ClientStatus, ClientTipo
from app.models.user import User, UserRole


def _env(nome: str, *, obrigatoria: bool = True) -> str:
    valor = os.environ.get(nome, "").strip()
    if obrigatoria and not valor:
        raise SystemExit(f"Variável obrigatória ausente: {nome}")
    return valor


async def _liberar_email(db, email: str) -> None:
    if not email:
        return
    existentes = (
        await db.execute(
            select(User).where(User.email == email.lower(), User.deleted_at.is_(None))
        )
    ).scalars().all()
    for existente in existentes:
        existente.is_active = False
        existente.deleted_at = datetime.now(timezone.utc)
        existente.email = f"{email}.encerrado.{existente.id[:8]}"


async def criar() -> None:
    email = _env("EJC_QA_EMAIL").lower()
    senha = _env("EJC_QA_PASSWORD")
    segredo = _env("EJC_QA_TOTP_SECRET")
    portal_email = _env("EJC_PORTAL_EMAIL", obrigatoria=False).lower()
    portal_senha = _env("EJC_PORTAL_PASSWORD", obrigatoria=False)
    portal_segredo = _env("EJC_PORTAL_TOTP_SECRET", obrigatoria=False)
    portal_marker = _env("EJC_QA_PORTAL_MARKER", obrigatoria=False)
    if "homolog" not in email and "qa" not in email:
        raise SystemExit("Barreira: e-mail temporário precisa conter homolog ou qa")
    if portal_email and (not portal_senha or not portal_segredo or not portal_marker):
        raise SystemExit("Credenciais/marker do Portal incompletos")
    if portal_marker and not portal_marker.startswith("HOMOLOG-FICTICIO"):
        raise SystemExit("Marker do Portal recusado")

    async with AsyncSessionLocal() as db:
        await _liberar_email(db, email)
        await _liberar_email(db, portal_email)

        staff = User(
            id=str(uuid4()),
            email=email,
            hashed_password=get_password_hash(senha),
            full_name="HOMOLOG-FICTICIO Advogado QA",
            role=UserRole.superadmin,
            must_change_password=False,
            totp_secret=segredo,
            totp_enabled=True,
            is_active=True,
            oab_number="MG 000000",
        )
        db.add(staff)

        portal_user_id = None
        if portal_email:
            cliente = Client(
                id=str(uuid4()),
                tipo=ClientTipo.PF,
                status=ClientStatus.ativo,
                nome=f"{portal_marker} Cliente Portal",
                email=portal_email,
                cidade="Betim",
                estado="MG",
                observacoes=f"Massa fictícia do Portal — {portal_marker}",
            )
            portal = User(
                id=str(uuid4()),
                email=portal_email,
                hashed_password=get_password_hash(portal_senha),
                full_name=f"{portal_marker} Usuário Portal",
                role=UserRole.cliente_externo,
                client_id=cliente.id,
                must_change_password=False,
                totp_secret=portal_segredo,
                totp_enabled=True,
                is_active=True,
            )
            db.add_all([cliente, portal])
            portal_user_id = portal.id

        await db.commit()
        print(
            f"QA_USERS_CREATED staff_id={staff.id} "
            f"portal_id={portal_user_id or 'nao_configurado'}"
        )


async def desativar() -> None:
    emails = {
        _env("EJC_QA_EMAIL").lower(),
        _env("EJC_PORTAL_EMAIL", obrigatoria=False).lower(),
    }
    emails.discard("")
    async with AsyncSessionLocal() as db:
        usuarios = (
            await db.execute(
                select(User).where(User.email.in_(emails), User.deleted_at.is_(None))
            )
        ).scalars().all()
        for usuario in usuarios:
            usuario.is_active = False
            usuario.deleted_at = datetime.now(timezone.utc)
            usuario.email = f"{usuario.email}.encerrado.{usuario.id[:8]}"
        await db.commit()
        print(f"QA_USERS_DISABLED count={len(usuarios)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("acao", choices=("criar", "desativar"))
    args = parser.parse_args()
    asyncio.run(criar() if args.acao == "criar" else desativar())


if __name__ == "__main__":
    main()
