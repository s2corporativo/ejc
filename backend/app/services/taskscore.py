# ── app/services/taskscore.py ────────────────────────────────────────────────
# Taskscore (Bloco D) — produtividade e carga por advogado, a partir das tarefas
# (app.models.task). Sinaliza atraso e classifica carga de trabalho. Apenas
# leitura sobre dados existentes; respeita o controle de acesso por perfil.
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ROLE_LEVEL
from app.models.user import User
from app.models.task import Task, TaskStatus

PENDENTES = {TaskStatus.a_fazer, TaskStatus.fazendo}

# Faixas de carga por nº de tarefas pendentes (parametrizável).
def _carga(pendentes: int) -> str:
    if pendentes <= 5:
        return "baixa"
    if pendentes <= 15:
        return "normal"
    if pendentes <= 30:
        return "alta"
    return "sobrecarga"


def pode_ver_todos(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["admin"]


async def taskscore(db: AsyncSession, user: User) -> dict:
    """Produtividade por responsável. Admin+ vê todos; demais, apenas as próprias."""
    hoje = date.today()
    q = select(
        Task.responsavel_id, Task.status, Task.data_limite
    ).where(Task.deleted_at.is_(None))
    if not pode_ver_todos(user):
        q = q.where(Task.responsavel_id == user.id)
    linhas = (await db.execute(q)).all()

    # nomes dos responsáveis
    ids = {r.responsavel_id for r in linhas if r.responsavel_id}
    nomes: dict[str, str] = {}
    if ids:
        for uid, nome in (await db.execute(
            select(User.id, User.full_name).where(User.id.in_(ids))
        )).all():
            nomes[uid] = nome

    agreg: dict[str, dict] = {}
    for r in linhas:
        chave = nomes.get(r.responsavel_id, "(sem responsável)")
        a = agreg.setdefault(chave, {"total": 0, "concluidas": 0, "pendentes": 0, "atrasadas": 0})
        a["total"] += 1
        if r.status == TaskStatus.concluida:
            a["concluidas"] += 1
        if r.status in PENDENTES:
            a["pendentes"] += 1
            if r.data_limite is not None and r.data_limite < hoje:
                a["atrasadas"] += 1

    advogados = []
    for nome, a in agreg.items():
        advogados.append({
            "responsavel": nome,
            **a,
            "taxa_conclusao": round(a["concluidas"] / a["total"] * 100, 1) if a["total"] else None,
            "carga": _carga(a["pendentes"]),
        })
    advogados.sort(key=lambda x: x["pendentes"], reverse=True)

    return {
        "escopo": "equipe" if pode_ver_todos(user) else "próprias tarefas",
        "referencia": hoje.isoformat(),
        "totais": {
            "tarefas": sum(a["total"] for a in agreg.values()),
            "pendentes": sum(a["pendentes"] for a in agreg.values()),
            "atrasadas": sum(a["atrasadas"] for a in agreg.values()),
        },
        "por_responsavel": advogados,
        "legenda_carga": "baixa ≤5 · normal 6–15 · alta 16–30 · sobrecarga >30 (tarefas pendentes)",
    }
