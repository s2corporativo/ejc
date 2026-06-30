# ── app/core/ownership.py ─────────────────────────────────────────────────────
# Ownership de CASO (RBAC + ABAC) — gate canônico p/ ESCRITAS em sub-recursos.
# Reusa o mesmo limiar de gestão de cases._filtro_visibilidade (ROLE_LEVEL["socio"]),
# fonte única de verdade. Módulo dedicado (não em security.py/cases.py) p/ evitar
# import circular: sub-recursos importam daqui, e este só importa models + ROLE_LEVEL.
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ROLE_LEVEL
from app.models.case import Case
from app.models.user import User

# Gestão = socio+ (socio=7, admin=8, superadmin=9) — vê/edita tudo.
_NIVEL_GESTAO = ROLE_LEVEL["socio"]


def _role_str(cu: User) -> str:
    r = getattr(cu, "role", None)
    return r.value if hasattr(r, "value") else str(r)


def is_gestao(cu: User) -> bool:
    return ROLE_LEVEL.get(_role_str(cu), 0) >= _NIVEL_GESTAO


async def verificar_acesso_caso(db: AsyncSession, cu: User, case_id: str) -> Case:
    """
    Gate de ownership para ESCRITAS em sub-recursos de um caso.

    - 404 se o caso não existe / soft-deleted.
    - Gestão (socio+) sempre passa.
    - Equipe passa se for responsável OU auxiliar do caso.
    - SALVAGUARDA anti-lockout: caso sem responsável NEM auxiliar (ambos NULL)
      → liberado p/ qualquer usuário interno (dados legados/triagem).
    - 403 caso contrário.

    cliente_externo já é barrado pelo AuthMiddleware fora de
    /portal,/auth,/signatures,/notifications — não é tratado aqui.
    Retorna o Case carregado (o handler pode reaproveitar sem novo SELECT).
    """
    case = (await db.execute(
        select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    )).scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Caso não encontrado")

    if is_gestao(cu):
        return case
    if cu.id in (case.advogado_responsavel_id, case.advogado_auxiliar_id):
        return case
    if case.advogado_responsavel_id is None and case.advogado_auxiliar_id is None:
        return case

    raise HTTPException(status_code=403, detail="Sem permissão para este caso")
