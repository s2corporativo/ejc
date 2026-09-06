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

Gate SEED_ON_BOOT (DB-13, auditoria de camadas 06/09/2026): default "1"
roda tudo (admin + catálogos + skills + base jurídica + reembed). Com "0"
(ou false/no/off) roda SOMENTE o admin — para produção, onde o boot não
aplica migrations (RUN_MIGRATIONS=0) e um seed contra schema atrasado podia
derrubar o container. Os demais seeds passam a ser passo do deploy, depois
do `alembic upgrade head`.

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


_SEED_ON_BOOT_DESLIGADO = {"0", "false", "no", "off"}


def seed_on_boot_ativo(valor: str | None = None) -> bool:
    """True = roda todos os seeds; False = só o admin. Lê SEED_ON_BOOT
    (default "1"). Valor não reconhecido conta como LIGADO — o modo seguro
    para dev/CI, que dependem dos catálogos."""
    bruto = os.environ.get("SEED_ON_BOOT", "1") if valor is None else valor
    return bruto.strip().lower() not in _SEED_ON_BOOT_DESLIGADO


def _em_pytest() -> bool:
    """True quando o seed roda dentro de uma sessão pytest (nunca baixa modelo)."""
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


async def vetorizar_orfaos_pos_seed() -> dict:
    """C1 (análise E2E de IA 2026-09-03): o seed nasce VETORIZADO.

    Antes, os documentos iniciais (súmulas conferidas, legislação) ficavam sem
    vetor até o job horário `reembed_rag_orfaos` (:20) — na primeira hora após
    a instalação a busca semântica devolvia vazio. Aqui, quando o provider de
    embeddings está disponível, reaproveita-se o MESMO reindexador idempotente
    do script/job (`scripts.reembedar_chunks_orfaos.reembedar`), que só toca
    chunk com `embedding IS NULL`. Desligável com SEED_EMBED_ORFAOS=false;
    em pytest nunca executa (não baixa modelo).

    Retorna um resumo {"executado": bool, "motivo": str|None, ...contagens}.
    """
    from app.core.config import get_settings

    s = get_settings()
    if not s.SEED_EMBED_ORFAOS:
        print("[seed] reembed de órfãos desligado (SEED_EMBED_ORFAOS=false).")
        return {"executado": False, "motivo": "desligado"}
    if _em_pytest():
        return {"executado": False, "motivo": "pytest"}

    from app.services import embedding_service

    if not embedding_service.disponivel():
        print("[seed] embeddings indisponíveis — chunks do seed ficam para o "
              "job horário reembed_rag_orfaos.")
        return {"executado": False, "motivo": "embeddings_indisponiveis"}

    from scripts import reembedar_chunks_orfaos as reembed_mod

    resumo = await reembed_mod.reembedar(batch_size=max(1, int(s.RAG_AUTO_REEMBED_BATCH)))
    resumo = dict(resumo or {})
    print(f"[seed] reembed de chunks órfãos: docs ok={resumo.get('ok', 0)} "
          f"erros={resumo.get('erros', 0)}")
    return {"executado": True, "motivo": None, **resumo}


async def main() -> None:
    await seed_admin()

    if not seed_on_boot_ativo():
        print("[seed] SEED_ON_BOOT desligado — só o admin foi semeado; rode os "
              "demais seeds no deploy, após as migrations.")
        return

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
    # C1: vetoriza na hora o que o seed acabou de gravar (idempotente,
    # best-effort, só com embeddings disponíveis).
    await _rodar_seed_async("reembed_orfaos_pos_seed", vetorizar_orfaos_pos_seed)
    print("[seed] concluído.")


if __name__ == "__main__":
    asyncio.run(main())
