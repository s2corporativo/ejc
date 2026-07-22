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


def role_str(cu: User) -> str:
    """Role do usuário como string (enum ou texto cru) — helper ÚNICO, reusado
    pelos services que precisam do role p/ auditoria/gates (antes duplicado)."""
    r = getattr(cu, "role", None)
    return r.value if hasattr(r, "value") else str(r)


def is_gestao(cu: User) -> bool:
    return ROLE_LEVEL.get(role_str(cu), 0) >= _NIVEL_GESTAO


def pode_ver_todos(user: User) -> bool:
    """Escopo de RELATÓRIO/dashboard: admin+ (admin=8, superadmin=9) enxerga TODA
    a base; equipe (advogado/auxiliar) vê só o próprio escopo. Limiar mais alto
    que is_gestao (socio+), que é o gate de ESCRITA em sub-recursos de caso.
    Helper único reusado por rentabilidade.py e case_health.py (antes duplicado)."""
    return ROLE_LEVEL.get(role_str(user), 0) >= ROLE_LEVEL["admin"]


async def verificar_acesso_caso(db: AsyncSession, cu: User, case_id: str) -> Case:
    """
    Gate de ownership para ESCRITAS em sub-recursos de um caso.

    - 404 se o caso não existe / soft-deleted.
    - Gestão (socio+) sempre passa.
    - Equipe passa se for responsável OU auxiliar do caso.
    - Caso ÓRFÃO (sem responsável NEM auxiliar): acessível SÓ à gestão (socio+),
      que já passou acima; perfis baixos (estagiário/secretaria/advogado sem
      vínculo) recebem 403. Hardening — antes um caso órfão liberava qualquer
      usuário interno (brecha). A gestão é o escape-hatch legítimo (assume/
      reatribui o caso), então não há lockout real.
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
    # Caso ÓRFÃO (sem responsável NEM auxiliar): ANTES era liberado a QUALQUER
    # usuário interno (salvaguarda anti-lockout p/ dados legados/triagem) —
    # brecha de segurança: estagiário/secretaria/advogado sem vínculo acessavam
    # sub-recursos de um caso sem dono. Agora um caso órfão só passa pela gestão
    # (is_gestao, verificado acima), que é o escape-hatch legítimo (pode assumir/
    # reatribuir o caso). Perfis baixos caem no 403 abaixo. Casos COM responsável
    # seguem inalterados (o vínculo acima decide).
    raise HTTPException(status_code=403, detail="Sem permissão para este caso")
