"""Gate canônico de titularidade para registros de cliente.

O módulo evita que fluxos fora do router de Clientes repitam consultas sem
segregação de carteira. Endpoints de conflito de interesses continuam podendo
cruzar a base inteira, mas qualquer retorno identificável deve passar por este
gate antes de expor id, nome ou documento ao usuário.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ownership import is_gestao, role_str
from app.models.case import Case
from app.models.client import Client
from app.models.user import User

# A secretaria opera o CRM institucional e, por decisão de produto, enxerga a
# carteira completa. Advogados permanecem segregados por responsabilidade/vínculo.
_CLIENTES_VISAO_TOTAL = {"secretaria"}


async def pode_ver_cliente(
    db: AsyncSession,
    user: User,
    client: Client,
) -> bool:
    """Retorna se ``user`` pode identificar/usar ``client``.

    Gestão e secretaria veem toda a base. Advogado/auxiliar passa somente quando
    é responsável direto pelo cliente ou integra ao menos um caso não excluído do
    mesmo cliente. A função não deve ser usada para eliminar a verificação ética
    de conflito; serve para impedir enumeração e vínculo transcarteira.
    """
    if is_gestao(user) or role_str(user) in _CLIENTES_VISAO_TOTAL:
        return True
    if client.responsavel_id == user.id:
        return True

    vinculo = (
        await db.execute(
            select(Case.id)
            .where(
                Case.client_id == client.id,
                Case.deleted_at.is_(None),
                or_(
                    Case.advogado_responsavel_id == user.id,
                    Case.advogado_auxiliar_id == user.id,
                ),
            )
            .limit(1)
        )
    ).first()
    return vinculo is not None


async def obter_cliente_autorizado(
    db: AsyncSession,
    user: User,
    client_id: str | None,
) -> Client:
    """Carrega um cliente com resposta 404 uniforme quando inacessível.

    O 404 evita confirmar que o UUID pertence a outra carteira.
    """
    if not client_id:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    client = (
        await db.execute(
            select(Client).where(
                Client.id == client_id,
                Client.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if client is None or not await pode_ver_cliente(db, user, client):
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return client


def visao_total_clientes(user: User) -> bool:
    """Mesmo limiar de ``pode_ver_cliente``: gestão (socio+) e secretaria (CRM
    institucional, decisão de produto) enxergam a carteira completa."""
    return is_gestao(user) or role_str(user) in _CLIENTES_VISAO_TOTAL


def ids_clientes_visiveis(user: User):
    """Subquery com os IDs de clientes da carteira do usuário — espelho SQL de
    ``pode_ver_cliente`` para filtrar LISTAGENS em uma única query (mesmo padrão
    de centro_custos._ids_casos_visiveis): responsável direto pelo cliente OU
    responsável/auxiliar de ao menos um caso não excluído do cliente."""
    return (
        select(Client.id)
        .where(
            Client.deleted_at.is_(None),
            or_(
                Client.responsavel_id == user.id,
                Client.id.in_(
                    select(Case.client_id).where(
                        Case.deleted_at.is_(None),
                        or_(
                            Case.advogado_responsavel_id == user.id,
                            Case.advogado_auxiliar_id == user.id,
                        ),
                    )
                ),
            ),
        )
        .scalar_subquery()
    )


def pode_ver_caso_resumido(user: User, case: Case) -> bool:
    """Gate sem nova consulta para resultados de busca/preview de casos."""
    if is_gestao(user):
        return True
    return user.id in (
        case.advogado_responsavel_id,
        case.advogado_auxiliar_id,
    )
