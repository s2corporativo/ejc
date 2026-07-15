"""seeds/seed_all.py — seed idempotente pós-deploy.

Cria o usuário admin inicial se ainda não existir. Idempotente: rodar várias
vezes é seguro (não duplica, não sobrescreve). Async (usa o engine asyncpg do
app — não exige driver sync).

Segurança: NÃO contém senha hardcoded. Lê do ambiente:
  - ADMIN_EMAIL    (default: admin@ejc.adv.br — NUNCA usar TLD .local:
                    o EmailStr do login rejeita e o admin não consegue logar)
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
    email = os.environ.get("ADMIN_EMAIL", "admin@ejc.adv.br").strip().lower()
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
    """Roda um seed SÍNCRONO (psycopg2) fora do event loop. Não-fatal: uma
    falha é registrada mas não aborta os demais seeds nem o deploy."""
    try:
        await asyncio.to_thread(fn)
    except (Exception, SystemExit) as e:  # noqa: BLE001 — seed best-effort:
        # os seeds síncronos chamam sys.exit(1) em má-configuração (URL vazia),
        # que é SystemExit (BaseException) e escaparia de `except Exception`,
        # abortando o bootstrap. Capturamos ambos para honrar o "não-fatal".
        print(f"[seed] AVISO: seed '{nome}' falhou (não-fatal): {e}")


async def main() -> None:
    await seed_admin()
    # Catálogo de tipos de documento (item 4.3): a tabela document_types_master
    # é criada VAZIA pela migration 062 e nunca era populada no bootstrap, então
    # a classificação automática de documentos falhava com "rode o seed". O seed
    # já existe e é idempotente (por tipo_key) — basta rodá-lo a cada deploy.
    from app.seeds.redesign_seed import seed as seed_document_types
    await _rodar_seed_sync("document_types_master", seed_document_types)
    # Skills/Ferramentas de IA (item 5.6): a tabela ejc_skills também nascia
    # vazia, deixando o seletor de "Ferramenta" em Ferramentas de IA sem opções.
    # Seeds idempotentes (por name); ferramentas dependem das skills, nesta ordem.
    from app.seeds.skills_seed import seed_skills_sync
    from app.seeds.skills_ferramentas_seed import seed as seed_skills_ferramentas
    from app.seeds.skills_workflows_seed import seed as seed_skills_workflows
    await _rodar_seed_sync("ejc_skills", seed_skills_sync)
    await _rodar_seed_sync("ejc_skills_ferramentas", seed_skills_ferramentas)
    # Fluxos especializados por matéria (tributário, imobiliário, cível,
    # consumidor, administrativo e provas). Permanecem no MESMO núcleo de
    # skills; este seed só amplia o catálogo sem criar agentes paralelos.
    await _rodar_seed_sync("ejc_skills_workflows", seed_skills_workflows)
    print("[seed] concluído.")


if __name__ == "__main__":
    asyncio.run(main())
