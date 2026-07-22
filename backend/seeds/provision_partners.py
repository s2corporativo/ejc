"""Provisionamento one-shot dos três sócios do escritório.

Este arquivo NÃO roda no boot e NÃO contém senhas. Execute-o somente no
container de produção, de forma interativa. Cada conta recebe senha temporária
forte e distinta, troca obrigatória no primeiro acesso e a política normal de
2FA do EJC.

Uso:
    python seeds/provision_partners.py
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from getpass import getpass
from typing import Callable
from uuid import uuid4

from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.models.audit_log import criar_audit_log
from app.models.user import User, UserRole
from app.services.security_service import validar_forca_senha


@dataclass(frozen=True)
class PartnerSpec:
    key: str
    full_name: str
    email: str


PARTNERS: tuple[PartnerSpec, ...] = (
    PartnerSpec("clovis", "Clovis Soares", "soares@depaulateixeira.adv.br"),
    PartnerSpec(
        "joao",
        "João Pedro Teixeira",
        "teixeira@depaulateixeira.adv.br",
    ),
    PartnerSpec(
        "guilherme",
        "Guilherme Alves de Paula",
        "depaula@depaulateixeira.adv.br",
    ),
)


class ProvisioningConflict(RuntimeError):
    """Estado existente exige conferência humana antes de continuar."""


def collect_temporary_passwords(
    partners: tuple[PartnerSpec, ...],
    password_reader: Callable[[str], str] = getpass,
) -> dict[str, str]:
    """Lê senhas sem eco, confirma, valida e impede reutilização."""
    passwords: dict[str, str] = {}
    used: set[str] = set()

    for partner in partners:
        first = password_reader(f"Senha temporária para {partner.email}: ")
        confirmation = password_reader(f"Confirme a senha para {partner.email}: ")
        if first != confirmation:
            raise ValueError(f"As senhas de {partner.email} não coincidem.")
        validar_forca_senha(first, partner.email)
        if first in used:
            raise ValueError("Cada sócio deve possuir uma senha temporária distinta.")
        used.add(first)
        passwords[partner.key] = first

    return passwords


async def _find_by_email(db, email: str, *, lock: bool = False) -> User | None:
    stmt = select(User).where(func.lower(User.email) == email.lower())
    if lock:
        stmt = stmt.with_for_update()
    rows = (await db.execute(stmt)).scalars().all()
    if len(rows) > 1:
        raise ProvisioningConflict(
            f"Há mais de um registro para {email}; revise ativos e soft-deleted."
        )
    return rows[0] if rows else None


def _validate_existing(user: User, partner: PartnerSpec) -> None:
    if user.deleted_at is not None:
        raise ProvisioningConflict(
            f"A conta {partner.email} está excluída logicamente; "
            "não será restaurada automaticamente."
        )
    if not user.is_active:
        raise ProvisioningConflict(
            f"A conta {partner.email} está administrativamente inativa; "
            "não será reativada automaticamente."
        )
    if user.full_name.strip().casefold() != partner.full_name.strip().casefold():
        raise ProvisioningConflict(
            f"A identidade existente de {partner.email} diverge do cadastro solicitado."
        )


async def provision_partners(
    password_reader: Callable[[str], str] = getpass,
) -> dict[str, str]:
    """Cria ou promove os três sócios sem redefinir conta já existente."""
    async with AsyncSessionLocal() as db:
        existing = {
            partner.key: await _find_by_email(db, partner.email)
            for partner in PARTNERS
        }

    missing = tuple(partner for partner in PARTNERS if existing[partner.key] is None)
    temporary_passwords = collect_temporary_passwords(missing, password_reader)
    statuses: dict[str, str] = {}

    async with AsyncSessionLocal() as db:
        async with db.begin():
            for partner in PARTNERS:
                user = await _find_by_email(db, partner.email, lock=True)
                if user is not None:
                    _validate_existing(user, partner)
                    if user.role == UserRole.superadmin and user.is_active:
                        statuses[partner.email] = "already_provisioned"
                        continue

                    before_role = getattr(user.role, "value", str(user.role))
                    user.role = UserRole.superadmin
                    await criar_audit_log(
                        db,
                        None,
                        "system",
                        "PROVISION_PARTNER",
                        "users",
                        user.id,
                        dados_antes={"role": before_role},
                        dados_depois={"role": UserRole.superadmin.value},
                    )
                    statuses[partner.email] = "promoted"
                    continue

                password = temporary_passwords.get(partner.key)
                if not password:
                    raise ProvisioningConflict(
                        f"A conta {partner.email} surgiu durante o provisionamento; "
                        "execute novamente para conferir o estado."
                    )

                user = User(
                    id=str(uuid4()),
                    email=partner.email.lower(),
                    hashed_password=get_password_hash(password),
                    full_name=partner.full_name,
                    role=UserRole.superadmin,
                    must_change_password=True,
                    totp_enabled=False,
                    totp_secret=None,
                    is_active=True,
                )
                db.add(user)
                await criar_audit_log(
                    db,
                    None,
                    "system",
                    "PROVISION_PARTNER",
                    "users",
                    user.id,
                    dados_depois={
                        "role": UserRole.superadmin.value,
                        "must_change_password": True,
                        "totp_enabled": False,
                    },
                )
                statuses[partner.email] = "created"

    return statuses


async def main() -> None:
    statuses = await provision_partners()
    for email, status in statuses.items():
        print(f"[partners] {email}: {status}")
    print(
        "[partners] concluído. As senhas não foram registradas; "
        "a troca no primeiro acesso e a política de 2FA permanecem ativas."
    )


if __name__ == "__main__":
    asyncio.run(main())
