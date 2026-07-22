"""seeds/seed_socios_advogados.py — seed idempotente para cadastro dos sócios do escritório.

Cadastra os 3 sócios advogados do escritório com:
- Acesso total (role=socio)
- Sem necessidade de fator de autenticação (totp_enabled=False)
- Senha padrão: 35914546

Idempotente: rodar várias vezes é seguro (não duplica, atualiza se existir).

Uso (dentro do container, WORKDIR /app):  python seeds/seed_socios_advogados.py
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.models.user import User, UserRole


SOCIOS = [
    {
        "email": "soares@depaulateixeira.adv.br",
        "nome": "Clovis Soares",
    },
    {
        "email": "teixeira@depaulateixeira.adv.br",
        "nome": "João Pedro Teixeira",
    },
    {
        "email": "depaula@depaulateixeira.adv.br",
        "nome": "Guilherme Alves de Paula",
    },
]

SENHA_PADRAO = "35914546"


async def seed_socios() -> None:
    async with AsyncSessionLocal() as db:
        for socio_data in SOCIOS:
            email = socio_data["email"].strip().lower()
            nome = socio_data["nome"].strip()

            existing = (
                await db.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()

            if existing:
                # Atualiza para garantir que está ativo e sem totp
                existing.full_name = nome
                existing.role = UserRole.socio
                existing.is_active = True
                existing.totp_enabled = False
                existing.totp_secret = None
                existing.must_change_password = False
                print(f"[seed] sócio atualizado: {email} ({nome})")
            else:
                novo_usuario = User(
                    id=str(uuid4()),
                    email=email,
                    hashed_password=get_password_hash(SENHA_PADRAO),
                    full_name=nome,
                    role=UserRole.socio,
                    is_active=True,
                    totp_enabled=False,
                    totp_secret=None,
                    must_change_password=False,
                )
                db.add(novo_usuario)
                print(f"[seed] sócio criado: {email} ({nome})")

        await db.commit()
        print(f"[seed] todos os sócios cadastrados/atualizados com sucesso.")
        print(f"[seed] senha padrão para todos: {SENHA_PADRAO}")


async def main() -> None:
    await seed_socios()


if __name__ == "__main__":
    asyncio.run(main())
