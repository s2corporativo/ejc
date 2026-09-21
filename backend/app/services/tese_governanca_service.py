"""Service — governança de Teses (pinned, fluxo de aprovação, fork, versões)
e injeção no system_prompt das ai_skills.

Regras de domínio:
- Só role de sócio aprova (``require_role_socio``).
- Editar ``conteudo_estruturado`` de tese aprovada (status=ativa + revisor_id)
  reverte para ``rascunho`` + ``revisor_id=None`` (re-aprovação obrigatória),
  e salva a versão anterior em ``TeseVersion``.
- ``listar_para_prompt(area, user_id)`` retorna pinned + selecionadas,
  preferindo o fork do usuário quando existe.
- ``injetar_no_prompt(system_prompt, area, user_id)`` anexa o bloco de Teses
  ao system_prompt da skill — é chamado por ``ai_skill_service``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tese import Tese, TeseFork, TeseVersion, TeseStatus
from app.models.user import User

logger = logging.getLogger("ejc.tese_governanca")

# Roles que podem aprovar (carimbar) uma Tese. Em produção, mapear para o
# sistema de roles do EJC (``app.core.security.ROLE_LEVEL``).
ROLES_APROVACAO = {"socio", "admin", "socio_diretor"}


def _pode_aprovar(user: User) -> bool:
    role = getattr(user, "role", None)
    role_val = role.value if hasattr(role, "value") else str(role)
    return role_val in ROLES_APROVACAO


async def editar_conteudo_estruturado(
    db: AsyncSession,
    tese_id: str,
    novo_conteudo: str,
    user: User,
) -> Tese:
    """Edita o conteudo_estruturado de uma tese. Se a tese estava aprovada
    (status=ativa + revisor_id), reverte para rascunho e salva versão anterior."""
    tese = await db.get(Tese, tese_id)
    if tese is None:
        raise ValueError("Tese não encontrada.")

    conteudo_anterior = tese.conteudo_estruturado
    if conteudo_anterior and conteudo_anterior != novo_conteudo:
        # salva versão anterior
        v = TeseVersion(
            id=str(uuid4()),
            tese_id=tese.id,
            conteudo=conteudo_anterior,
            version=1,  # placeholder; ver nota abaixo
            autor_id=user.id,
            note="Edição automática — versão anterior preservada",
        )
        db.add(v)
        # incrementa version na tese para refletir a nova edição
        # (usamos uma coluna derivada: max(version) de TeseVersion + 1)
        existing_versions = await db.execute(
            select(TeseVersion.version)
            .where(TeseVersion.tese_id == tese_id)
            .order_by(TeseVersion.version.desc())
            .limit(1)
        )
        last_v = existing_versions.scalar_one_or_none() or 0
        v.version = last_v + 1

    tese.conteudo_estruturado = novo_conteudo
    # se estava aprovada, reverte para rascunho (re-aprovação obrigatória)
    if tese.status == TeseStatus.ativa and tese.revisor_id is not None:
        tese.status = TeseStatus.rascunho
        tese.revisor_id = None
        tese.revisao_em = None
        logger.info("Tese %s voltou para rascunho após edição (re-aprovação)", tese_id)

    await db.commit()
    await db.refresh(tese)
    return tese


async def enviar_para_revisao(
    db: AsyncSession, tese_id: str, user: User, note: Optional[str] = None
) -> Tese:
    """Advogado envia tese para revisão do sócio. Status → rascunho (aguardando),
    revisor_id=None (ainda não carimbada)."""
    tese = await db.get(Tese, tese_id)
    if tese is None:
        raise ValueError("Tese não encontrada.")
    tese.status = TeseStatus.rascunho
    tese.revisor_id = None
    tese.revisao_em = None
    await db.commit()
    await db.refresh(tese)
    logger.info("Tese %s enviada para revisão por %s", tese_id, user.id)
    return tese


async def aprovar_tese(
    db: AsyncSession, tese_id: str, user: User, note: Optional[str] = None
) -> Tese:
    """Sócio carimba a tese — status=ativa + revisor_id + revisao_em.
    A partir daqui ela é elegível para injeção no prompt."""
    if not _pode_aprovar(user):
        raise PermissionError("Apenas sócio responsável pode aprovar teses.")
    tese = await db.get(Tese, tese_id)
    if tese is None:
        raise ValueError("Tese não encontrada.")
    tese.status = TeseStatus.ativa
    tese.revisor_id = user.id
    tese.revisao_em = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(tese)
    logger.info("Tese %s aprovada por %s em %s", tese_id, user.id, tese.revisao_em)
    return tese


async def toggle_pinned(db: AsyncSession, tese_id: str) -> Tese:
    tese = await db.get(Tese, tese_id)
    if tese is None:
        raise ValueError("Tese não encontrada.")
    tese.pinned = not tese.pinned
    await db.commit()
    await db.refresh(tese)
    return tese


async def upsert_fork(
    db: AsyncSession, tese_id: str, user: User, conteudo: Optional[str], note: Optional[str]
) -> TeseFork:
    """Cria ou atualiza o fork pessoal do advogado. Se conteudo vazio, copia
    da tese (conteudo_estruturado → descricao como fallback)."""
    tese = await db.get(Tese, tese_id)
    if tese is None:
        raise ValueError("Tese não encontrada.")
    fork_conteudo = conteudo or tese.conteudo_estruturado or tese.descricao

    existing = (
        await db.execute(
            select(TeseFork).where(
                and_(TeseFork.tese_id == tese_id, TeseFork.user_id == user.id)
            )
        )
    ).scalar_one_or_none()

    if existing:
        existing.conteudo = fork_conteudo
        existing.note = note
        await db.commit()
        await db.refresh(existing)
        return existing

    fork = TeseFork(
        id=str(uuid4()),
        tese_id=tese_id,
        user_id=user.id,
        conteudo=fork_conteudo,
        note=note,
    )
    db.add(fork)
    await db.commit()
    await db.refresh(fork)
    return fork


async def get_fork(db: AsyncSession, tese_id: str, user_id: str) -> Optional[TeseFork]:
    return (
        await db.execute(
            select(TeseFork).where(
                and_(TeseFork.tese_id == tese_id, TeseFork.user_id == user_id)
            )
        )
    ).scalar_one_or_none()


async def listar_versoes(db: AsyncSession, tese_id: str) -> list[TeseVersion]:
    res = await db.execute(
        select(TeseVersion)
        .where(TeseVersion.tese_id == tese_id)
        .order_by(TeseVersion.version.desc())
    )
    return list(res.scalars().all())


# ── Injeção no prompt ─────────────────────────────────────────────────────────

async def listar_para_prompt(
    db: AsyncSession,
    area: Optional[str],
    user_id: str,
    *,
    selecionadas_ids: Optional[list[str]] = None,
    limite: int = 8,
) -> list[Tese]:
    """Retorna as Teses que devem entrar no system_prompt da skill:
    1. Todas as ``pinned`` aprovadas (sempre entram — inegociáveis).
    2. As da área do caso (aprovadas), até ``limite``.
    3. As explicitamente selecionadas pelo usuário (aprovadas).
    Não retorna teses rascunho/arquivadas nem sem revisor_id.
    """
    cond_base = and_(
        Tese.status == TeseStatus.ativa,
        Tese.revisor_id.is_not(None),
        Tese.deleted_at.is_(None),
    )
    res = await db.execute(
        select(Tese).where(cond_base).order_by(Tese.pinned.desc(), Tese.updated_at.desc())
    )
    todas = list(res.scalars().all())

    pinned = [t for t in todas if t.pinned]
    da_area = [t for t in todas if area and t.area_juridica == area and not t.pinned]
    selecionadas = []
    if selecionadas_ids:
        sel_set = set(selecionadas_ids)
        selecionadas = [t for t in todas if t.id in sel_set and not t.pinned]

    # dedupe preservando ordem
    vistos: set[str] = set()
    out: list[Tese] = []
    for t in pinned + da_area + selecionadas:
        if t.id in vistos:
            continue
        vistos.add(t.id)
        out.append(t)
        if len(out) >= limite:
            break
    return out


def conteudo_para_prompt(tese: Tese, fork: Optional[TeseFork] = None) -> str:
    """Conteúdo que vai ao prompt: prefere o fork do usuário, depois o
    conteudo_estruturado, depois descricao (fallback legado)."""
    if fork and fork.conteudo:
        return fork.conteudo
    if tese.conteudo_estruturado:
        return tese.conteudo_estruturado
    return tese.descricao or ""


async def injetar_no_prompt(
    db: AsyncSession,
    system_prompt: str,
    *,
    area: Optional[str],
    user_id: str,
    selecionadas_ids: Optional[list[str]] = None,
) -> str:
    """Anexa o bloco de Teses aprovadas ao system_prompt da skill.

    Chamado por ``app.services.ai_skill_service`` antes de montar as messages.
    As Teses são conteúdo AUTORAL do escritório (gravado por sócio), então
    podem ir no SYSTEM — diferentemente do RAG, que vem de ingestão externa
    e por isso vai no USER (ver pente fino 03/09 em ai_skill_service).
    """
    try:
        teses = await listar_para_prompt(
            db, area, user_id, selecionadas_ids=selecionadas_ids
        )
    except Exception as exc:
        logger.warning("Falha ao listar teses para prompt: %s", type(exc).__name__)
        return system_prompt

    if not teses:
        return system_prompt

    blocos: list[str] = []
    for t in teses:
        fork = await get_fork(db, t.id, user_id)
        conteudo = conteudo_para_prompt(t, fork)
        if not conteudo:
            continue
        prefixo = "# " if t.pinned else ""
        blocos.append(f"### {prefixo}{t.titulo}\n{conteudo}")

    if not blocos:
        return system_prompt

    bloco_teses = (
        "\n\n## Teses do escritório (orientam a redação)\n"
        "As marcadas com # são inegociáveis. Respeite \"Riscos e armadilhas\", "
        "siga o \"Procedimento passo a passo\", use o \"Checklist de peças\".\n\n"
        + "\n\n---\n\n".join(blocos)
    )
    return system_prompt + bloco_teses
