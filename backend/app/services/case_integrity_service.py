"""Regras de integridade compartilhadas do núcleo de Casos.

Este módulo existe para retirar do router decisões de domínio que precisam ser
idênticas em criação, edição e importação assistida:

- quem pode ser o responsável jurídico principal de um caso;
- unicidade do número processual por cliente, inclusive sob concorrência;
- sincronização do espelho legado ``cases`` com a fonte canônica ``processes``.

Nenhuma função faz commit. A transação pertence ao chamador para que alteração
de domínio e AuditLog sejam atômicos.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func as sqlfunc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case
from app.models.user import User
from app.schemas.process import ProcessCreate, ProcessUpdate
from app.services.processo_service import (
    atualizar_processo,
    criar_processo,
    processo_principal,
)
from app.services.validators_service import normalizar_cnj


RESPONSAVEL_JURIDICO_ROLES: frozenset[str] = frozenset(
    {"superadmin", "admin", "socio", "advogado", "advogado_auxiliar"}
)

_UNSET = object()


def _role_value(user: User) -> str:
    role = getattr(user, "role", "")
    return role.value if hasattr(role, "value") else str(role)


async def resolver_responsavel_juridico(
    db: AsyncSession,
    solicitante: User,
    responsavel_id: str | None,
) -> str:
    """Resolve e valida o responsável principal do caso.

    Secretaria e estagiário continuam podendo participar do intake quando o
    endpoint autorizar, mas não viram responsáveis jurídicos por fallback.
    Nesses perfis o responsável precisa ser informado explicitamente.

    Quando o próprio solicitante, já autenticado e com papel jurídico apto,
    assume o caso por fallback, não repetimos uma consulta de existência ao
    banco: a identidade já foi validada pelo fluxo de autenticação e o papel é
    checado aqui. Responsável indicado explicitamente continua sendo carregado
    e validado no banco para impedir usuário inexistente, inativo ou papel
    incompatível.
    """
    solicitante_role = _role_value(solicitante)

    if not responsavel_id:
        if solicitante_role not in RESPONSAVEL_JURIDICO_ROLES:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Informe um advogado responsável pelo caso. Usuários de intake "
                    "não podem assumir automaticamente a responsabilidade jurídica."
                ),
            )
        if getattr(solicitante, "is_active", True) is False:
            raise HTTPException(
                status_code=422,
                detail="Advogado responsável inexistente ou inativo.",
            )
        return str(solicitante.id)

    resolved_id = str(responsavel_id)
    responsavel = (
        await db.execute(
            select(User).where(
                User.id == resolved_id,
                User.deleted_at.is_(None),
                User.is_active.is_not(False),
            )
        )
    ).scalar_one_or_none()
    if responsavel is None:
        raise HTTPException(
            status_code=422,
            detail="Advogado responsável inexistente ou inativo.",
        )

    if _role_value(responsavel) not in RESPONSAVEL_JURIDICO_ROLES:
        raise HTTPException(
            status_code=422,
            detail=(
                "O responsável principal precisa ter papel jurídico compatível "
                "(advogado, advogado auxiliar, sócio ou gestão jurídica)."
            ),
        )
    return str(responsavel.id)


async def garantir_numero_processo_unico(
    db: AsyncSession,
    *,
    client_id: str,
    numero_processo: str | None,
    excluir_case_id: str | None = None,
) -> None:
    """Impede dois casos vivos do mesmo cliente com o mesmo número processual.

    O advisory lock serializa create/update concorrentes com a mesma chave.
    Números CNJ são comparados pelos 20 dígitos; numeração administrativa é
    comparada por texto normalizado, preservando o comportamento histórico.
    """
    numero = (numero_processo or "").strip()
    if not numero:
        return

    digitos_cnj = normalizar_cnj(numero)
    numero_chave = digitos_cnj if len(digitos_cnj) == 20 else numero.casefold()
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:chave))"),
        {"chave": f"case_duplicate:{client_id}:{numero_chave}"},
    )

    if len(digitos_cnj) == 20:
        numero_igual = (
            sqlfunc.regexp_replace(Case.numero_processo, r"\D", "", "g")
            == digitos_cnj
        )
    else:
        numero_igual = (
            sqlfunc.lower(sqlfunc.trim(Case.numero_processo)) == numero.casefold()
        )

    stmt = select(Case.id).where(
        Case.client_id == client_id,
        Case.deleted_at.is_(None),
        numero_igual,
    )
    if excluir_case_id:
        stmt = stmt.where(Case.id != excluir_case_id)

    existente = (await db.execute(stmt.limit(1))).scalar_one_or_none()
    if existente:
        raise HTTPException(
            status_code=409,
            detail="Já existe caso ativo para este cliente e número processual",
        )


async def sincronizar_processo_principal_do_caso(
    db: AsyncSession,
    *,
    case_id: str,
    numero_processo: str | None | object = _UNSET,
    tribunal: str | None | object = _UNSET,
    comarca: str | None | object = _UNSET,
    vara: str | None | object = _UNSET,
    valor_causa: Decimal | None | object = _UNSET,
    tipo: str | object = _UNSET,
) -> dict[str, Any] | None:
    """Atualiza/cria o processo principal usando exclusivamente o service canônico.

    ``_UNSET`` diferencia "campo não informado" de ``None`` deliberado. Isso é
    essencial para que limpar ``numero_processo`` no caso também limpe o número
    do processo principal, sem apagar tribunal/comarca/vara por acidente.
    """
    principal = await processo_principal(case_id, db)

    changes: dict[str, Any] = {}
    if numero_processo is not _UNSET:
        changes["numero_cnj"] = numero_processo
    if tribunal is not _UNSET:
        changes["tribunal"] = tribunal
    if comarca is not _UNSET:
        changes["comarca"] = comarca
    if vara is not _UNSET:
        changes["vara"] = vara
    if valor_causa is not _UNSET:
        changes["valor_causa"] = valor_causa
    if tipo is not _UNSET:
        changes["tipo"] = tipo

    if principal:
        if not changes:
            return principal
        return await atualizar_processo(
            principal["id"],
            ProcessUpdate(**changes),
            db,
        )

    # Sem processo canônico ainda: só cria quando há algum dado processual
    # material. Um PATCH que apenas limpa campo legado não fabrica processo vazio.
    material = any(
        value not in (None, "")
        for key, value in changes.items()
        if key != "tipo"
    )
    if not material:
        return None

    create_data: dict[str, Any] = {
        "numero_cnj": changes.get("numero_cnj"),
        "tribunal": changes.get("tribunal"),
        "comarca": changes.get("comarca"),
        "vara": changes.get("vara"),
        "valor_causa": changes.get("valor_causa"),
        "tipo": changes.get("tipo", "judicial"),
        "instancia": "1",
        "status": "ativo",
        "is_principal": True,
    }
    return await criar_processo(case_id, ProcessCreate(**create_data), db)
