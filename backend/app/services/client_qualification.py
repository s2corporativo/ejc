"""Checklist de qualificação sem decifrar ou expor documentos pessoais."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client


async def carregar_qualificacao_cliente(
    db: AsyncSession, client_id: str, *, incluir_endereco: bool = False,
) -> tuple[Client | None, list[str]]:
    client = (await db.execute(
        select(Client).where(Client.id == client_id, Client.deleted_at.is_(None))
    )).scalar_one_or_none()
    faltas: list[str] = []
    if client is None:
        faltas.append("cliente do caso não encontrado (ou excluído)")
    else:
        if not (client.nome or client.razao_social):
            faltas.append("nome/razão social")
        if not (client.cpf_enc or client.cnpj_enc):
            faltas.append("CPF/CNPJ")
        if incluir_endereco:
            end_faltas = [rotulo for rotulo, valor in (
                ("logradouro", client.logradouro), ("número", client.numero),
                ("cidade", client.cidade), ("UF", client.estado),
            ) if not valor]
            if end_faltas:
                faltas.append("endereço: " + ", ".join(end_faltas))
    return client, faltas
