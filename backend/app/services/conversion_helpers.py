"""Primitivas de preview: nunca devolvem identidade/contagem de carteira protegida."""
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case, CaseStatus
from app.models.user import User
from app.core.client_ownership import pode_ver_caso_resumido


def alerta_protegido(tipo: str, mensagem: str) -> dict[str, Any]:
    return {
        "tipo": tipo,
        "nome": "Correspondência protegida na base do escritório",
        "mensagem": mensagem,
        "protegido": True,
        "confirmado": False,
    }


def deduplicar_alertas(alertas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Preserva ordem e colapsa alertas sem usar identificadores protegidos."""
    unicos: list[dict[str, Any]] = []
    vistos: set[tuple[str, str, str]] = set()
    for alerta in alertas:
        chave = tuple(str(alerta.get(k) or "") for k in ("tipo", "nome", "mensagem"))
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(alerta)
    return unicos


async def casos_ativos_do_cliente(
    db: AsyncSession, user: User, client_id: str, *, can_view=pode_ver_caso_resumido,
) -> list[dict[str, Any]]:
    """Casos ativos para client_id já autorizado pelo chamador.

    Protegidos colapsam numa entrada; a consulta não amplia a carteira.
    can_view permite conservar os pontos históricos de monkeypatch.
    """
    rows = (await db.execute(
        select(Case).where(
            Case.client_id == client_id,
            Case.deleted_at.is_(None),
            Case.status.notin_([CaseStatus.encerrado, CaseStatus.arquivado]),
        ).limit(10)
    )).scalars().all()
    ativos: list[dict[str, Any]] = []
    houve_protegido = False
    for caso in rows:
        if can_view(user, caso):
            ativos.append({
                "id": caso.id, "titulo": caso.titulo,
                "numero_interno": caso.numero_interno, "protegido": False,
            })
        else:
            houve_protegido = True
    if houve_protegido:
        ativos.append({
            "id": None, "titulo": "Caso protegido",
            "numero_interno": None, "protegido": True,
        })
    return ativos
