"""seeds/seed_all.py — seed idempotente pós-deploy.

Cria o usuário admin inicial se ainda não existir. Idempotente: rodar várias
vezes é seguro (não duplica, não sobrescreve). Async (usa o engine asyncpg do
app — não exige driver sync).

Segurança: NÃO contém senha hardcoded. Lê do ambiente:
  - ADMIN_EMAIL    (default: admin@ejc.local)
  - ADMIN_NAME     (default: Administrador EJC)
  - ADMIN_PASSWORD (se ausente, gera senha aleatória e a imprime UMA vez)
O admin é criado com must_change_password=True (troca obrigatória no 1º login).

Uso (dentro do container, WORKDIR /app):  python seeds/seed_all.py
"""
from __future__ import annotations

import asyncio
import os
import secrets as _secrets
from uuid import uuid4

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.models.user import User, UserRole


async def seed_admin() -> None:
    email = os.environ.get("ADMIN_EMAIL", "admin@ejc.local").strip().lower()
    nome = os.environ.get("ADMIN_NAME", "Administrador EJC").strip()
    senha = os.environ.get("ADMIN_PASSWORD", "").strip()
    senha_gerada = False
    if not senha:
        senha = _secrets.token_urlsafe(16)
        senha_gerada = True

    async with AsyncSessionLocal() as db:
        existing = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing:
            print(f"[seed] admin já existe: {email} — nenhuma ação.")
            return

        db.add(
            User(
                id=str(uuid4()),
                email=email,
                hashed_password=get_password_hash(senha),
                full_name=nome,
                role=UserRole.superadmin,
                must_change_password=True,
                is_active=True,
            )
        )
        await db.commit()
        print(f"[seed] admin criado: {email} (must_change_password=True)")
        if senha_gerada:
            print(f"[seed] SENHA TEMPORÁRIA (anote agora; troque no 1º login): {senha}")


async def main() -> None:
    await seed_admin()
    # Hooks idempotentes adicionais (feriados, súmulas) podem ser plugados aqui
    # numa fase posterior, sempre com checagem "já existe?" antes de inserir.
    print("[seed] concluído.")


if __name__ == "__main__":
    asyncio.run(main())
