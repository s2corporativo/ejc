"""seeds/seed_all.py — seed idempotente pós-deploy.

Cria o usuário admin inicial se ainda não existir. Idempotente: rodar várias
vezes é seguro (não duplica, não sobrescreve). Async (usa o engine asyncpg do
app — não exige driver sync).

Segurança: NÃO contém senha hardcoded. Lê do ambiente:
  - ADMIN_EMAIL    (default: admin@ejc.adv.br — domínio válido). VALIDADO com a
                   MESMA regra do login (pydantic EmailStr) ANTES de criar o
                   admin: um endereço que o login recusaria (ex.: TLD reservado
                   .local/.invalid/.test ou 'localhost') ABORTA o seed com erro
                   claro, em vez de criar um admin que nunca consegue logar.
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

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.models.user import User, UserRole

# Valida ADMIN_EMAIL com o MESMO validador do login. O /auth/login declara
# `email: EmailStr` (routers/auth.py); um ADMIN_EMAIL que o EmailStr recusa
# (TLD reservado *.local/*.invalid/*.test ou 'localhost') criaria um admin que
# NUNCA autentica (login → 422) — footgun silencioso de go-live. Reusar o mesmo
# TypeAdapter garante paridade exata com a regra do login.
_ADMIN_EMAIL_ADAPTER = TypeAdapter(EmailStr)


def validar_admin_email(email: str) -> str:
    """Devolve o e-mail normalizado se válido para login; senão levanta
    ValueError acionável. Falha AQUI (antes de gravar o usuário) em vez de
    criar um admin inacessível em silêncio."""
    try:
        return _ADMIN_EMAIL_ADAPTER.validate_python(email)
    except ValidationError as exc:
        raise ValueError(
            f"ADMIN_EMAIL inválido para login: {email!r}. O /auth/login usa "
            "pydantic EmailStr e recusaria este endereço (ex.: TLD reservado "
            ".local/.invalid/.test ou 'localhost'), criando um admin que não "
            "consegue autenticar. Defina ADMIN_EMAIL com um domínio real "
            "(ex.: admin@seudominio.adv.br) e rode o seed novamente."
        ) from exc


async def seed_admin() -> None:
    email = os.environ.get("ADMIN_EMAIL", "admin@ejc.adv.br").strip().lower()
    # Barreira de go-live: aborta ANTES de criar admin que o login rejeitaria.
    email = validar_admin_email(email)
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


async def _rodar_seed_sync(nome: str, fn) -> None:
    """Roda seed síncrono fora do event loop sem interromper os demais."""
    try:
        await asyncio.to_thread(fn)
    except (Exception, SystemExit) as exc:  # noqa: BLE001 — seed best-effort
        print(f"[seed] AVISO: seed '{nome}' falhou (não-fatal): {exc}")


async def _rodar_seed_async(nome: str, coro_fn) -> None:
    """Roda um seed ASSÍNCRONO best-effort (usa o engine async do app).

    Mesmo contrato de `_rodar_seed_sync`: uma falha NUNCA aborta o bootstrap
    (o entrypoint roda `seed_all` com `set -e`, então um seed que propague
    exceção derrubaria o boot inteiro).
    """
    try:
        await coro_fn()
    except (Exception, SystemExit) as exc:  # noqa: BLE001 — seed best-effort
        print(f"[seed] AVISO: seed '{nome}' falhou (não-fatal): {exc}")


async def main() -> None:
    await seed_admin()

    from app.seeds.redesign_seed import seed as seed_document_types

    await _rodar_seed_sync("document_types_master", seed_document_types)

    from app.seeds.skills_seed import seed_skills_sync
    from app.seeds.skills_ferramentas_seed import seed as seed_skills_ferramentas
    from app.seeds.skills_workflows_seed import seed as seed_skills_workflows
    from app.seeds.skills_expansion_seed import seed as seed_skills_expansion
    from app.seeds.skills_contextual_areas_seed import seed as seed_skills_contextual_areas
    from app.seeds.skills_native_ejc_seed import seed as seed_skills_native_ejc

    await _rodar_seed_sync("ejc_skills", seed_skills_sync)
    await _rodar_seed_sync("ejc_skills_ferramentas", seed_skills_ferramentas)
    await _rodar_seed_sync("ejc_skills_workflows", seed_skills_workflows)
    await _rodar_seed_sync("ejc_skills_expansion", seed_skills_expansion)
    await _rodar_seed_sync("ejc_skills_contextual_areas", seed_skills_contextual_areas)
    await _rodar_seed_sync("ejc_skills_native_ejc", seed_skills_native_ejc)

    # Base de conhecimento jurídica REAL (P0 — auditoria da Central de IA): sem
    # isto o RAG de um ambiente recém-provisionado fica sem fonte real e a IA
    # cai no conhecimento paramétrico. Súmulas conferidas (OFFLINE) semeiam
    # SEMPRE; a legislação do Planalto (REDE) é existence-guarded + bounded por
    # timeout p/ nunca estourar a janela de health-check do deploy. Idempotente
    # e best-effort — ver app/seeds/base_juridica_seed.py.
    from app.seeds.base_juridica_seed import seed_base_juridica

    await _rodar_seed_async("base_juridica_real", seed_base_juridica)
    print("[seed] concluído.")


if __name__ == "__main__":
    asyncio.run(main())
