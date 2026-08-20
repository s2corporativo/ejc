"""Kanban columns and case kanban management."""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ownership import verificar_acesso_caso
from app.models.user import User

_TEAM = {"superadmin", "admin", "socio", "advogado", "advogado_auxiliar", "estagiario"}
_TERMINAIS = {"arquivado", "encerrado"}


def _req_team(cu: User = Depends(get_current_user)) -> User:
    # Mover cartão é organização visual; alteração de status jurídico fica nos
    # fluxos canônicos de Case, com seus gates e trilha de auditoria próprios.
    if cu.role.value not in _TEAM:
        raise HTTPException(status_code=403, detail="Acesso restrito à equipe jurídica")
    return cu


router = APIRouter(prefix="/kanban", tags=["Kanban"])
casos_router = APIRouter(prefix="", tags=["Kanban — Casos"])


def _status_terminal_da_coluna(nome: str) -> Optional[str]:
    """Retorna apenas estados terminais explicitamente representados na coluna.

    Colunas operacionais como "Aguardando prazo" e "Suspenso" não mudam mais
    `Case.status`. A migration 126 já retirou esses conceitos do enum de status;
    o Kanban não deve recriar uma segunda máquina de estados por inferência de nome.
    """
    if not nome:
        return None
    n = nome.lower()
    if "arquiv" in n:
        return "arquivado"
    if "acordo" in n or "encerrad" in n or "entregue" in n:
        return "encerrado"
    return None


@router.get("/columns")
async def list_kanban_columns(
    legal_area: Optional[str] = "default",
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        text("SELECT id, name, legal_area, position, color, icon FROM kanban_columns WHERE is_active=true AND legal_area=:area ORDER BY position"),
        {"area": legal_area},
    )
    rows = result.mappings().all()
    return [dict(r) for r in rows]


@casos_router.patch("/cases/{case_id}/kanban")
async def update_case_kanban(
    case_id: str,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(_req_team),
):
    kanban_column = body.get("kanban_column")
    kanban_position = body.get("kanban_position", 0)

    # IDOR: só quem atua no caso (ou gestão) move o cartão.
    await verificar_acesso_caso(db, current_user, case_id)

    # Serializa a decisão visual com qualquer transição canônica concorrente.
    # O Kanban não escreve status; o lock evita mover um cartão com uma leitura
    # obsoleta enquanto outro endpoint encerra/arquiva/reabre o caso.
    row = (
        await db.execute(
            text(
                "SELECT status FROM cases "
                "WHERE id=:id AND deleted_at IS NULL FOR UPDATE"
            ),
            {"id": case_id},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(404, "Case not found")

    status_atual = row["status"]
    status_terminal_alvo = _status_terminal_da_coluna(kanban_column or "")

    # Kanban é organização, não máquina de estados. Entrar em estado terminal
    # exige endpoints dedicados; sair de estado terminal exige o fluxo canônico
    # de reabertura, que registra auditoria e limpa metadados de forma controlada.
    if status_terminal_alvo and status_terminal_alvo != status_atual:
        raise HTTPException(
            status_code=422,
            detail=(
                "Use POST /cases/{id}/arquivar"
                if status_terminal_alvo == "arquivado"
                else "Use POST /cases/{id}/encerrar (exige pós-mortem)"
            ),
        )
    if status_atual in _TERMINAIS and status_terminal_alvo != status_atual:
        raise HTTPException(
            status_code=422,
            detail="Reabra o caso pelo fluxo canônico antes de movê-lo para coluna ativa",
        )

    await db.execute(
        text(
            "UPDATE cases SET kanban_column=:col, kanban_position=:pos, "
            "updated_at=NOW() WHERE id=:id"
        ),
        {"col": kanban_column, "pos": kanban_position, "id": case_id},
    )
    await db.commit()
    return {"ok": True, "status_sincronizado": None}


# Compatibilidade (PR #1218): o endereço canônico antigo GET /api/kanban-columns
# (router sem prefixo + decorator "/kanban-columns", montado sob /api) agora
# vive em /api/kanban/columns. Redirect 308 — o destino reautentica
# (HTTPBearer), mesmo desenho dos PRs #1215/#1217.
_compat = APIRouter(prefix="", tags=["Kanban — Compatibilidade"])


from fastapi.responses import RedirectResponse as _RR


@_compat.get("/kanban-columns")
async def _redirect_kanban_columns(
    # Conservador: o endereço movido (Onda 2) manteve o mesmo gate de auth —
    # o redirect exige credencial antes de redirecionar; o destino reautentica.
    current_user: User = Depends(get_current_user),
) -> _RR:
    del current_user
    return _RR(url="/api/kanban/columns", status_code=308)
