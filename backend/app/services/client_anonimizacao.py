# ── app/services/client_anonimizacao.py ───────────────────────────────────────
# Direito ao esquecimento (LGPD art. 17) — Bloco 6b da auditoria EJC.
#
# NÃO é exclusão física. A LGPD (art. 16, II) permite reter dados quando
# necessário para cumprimento de obrigação legal/regulatória (fiscal, dever
# de guarda de honorários/processos) — por isso o registro do cliente
# permanece (id, casos, financeiro), mas os campos de identificação pessoal
# são substituídos por placeholders. Reversível apenas no sentido técnico de
# "não apaga histórico jurídico/fiscal"; a PII em si NÃO é recuperável após
# a anonimização (é sobrescrita, não só ocultada).
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.case import Case, CaseStatus
from app.models.user import User
from app.models.audit_log import criar_audit_log

_MARCADOR = "[ANONIMIZADO — LGPD ART. 17]"

# Casos nestes status representam representação jurídica EM CURSO — o
# escritório tem obrigação de saber quem é o cliente enquanto atua por ele.
# Anonimizar durante isso comprometeria o próprio dever profissional (EOAB).
_STATUS_BLOQUEIA_ANONIMIZACAO = {
    CaseStatus.triagem, CaseStatus.ativo, CaseStatus.suspenso, CaseStatus.acordo,
}


async def verificar_bloqueios(db: AsyncSession, client_id: str) -> list[str]:
    """Retorna motivos que impedem a anonimização agora (lista vazia = liberado)."""
    motivos = []
    casos_ativos = (await db.execute(
        select(Case.numero_interno, Case.status).where(
            Case.client_id == client_id,
            Case.deleted_at.is_(None),
            Case.status.in_(_STATUS_BLOQUEIA_ANONIMIZACAO),
        )
    )).all()
    if casos_ativos:
        numeros = ", ".join(c.numero_interno or "sem número" for c in casos_ativos)
        motivos.append(
            f"{len(casos_ativos)} caso(s) em representação ativa ({numeros}). "
            "Encerre ou arquive antes de anonimizar — o escritório precisa "
            "identificar o cliente enquanto atua por ele (dever profissional OAB)."
        )
    return motivos


async def anonimizar_cliente(
    db: AsyncSession, client_id: str, executor_id: str, executor_role: str,
    motivo: str | None = None, forcar: bool = False,
) -> dict:
    """
    Executa a anonimização. Levanta HTTPException se bloqueado (a menos que
    forcar=True — reservado para gestão, com o bloqueio registrado no log
    mesmo assim, para rastreabilidade da decisão de forçar).
    """
    cliente = (await db.execute(
        select(Client).where(Client.id == client_id, Client.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not cliente:
        raise HTTPException(404, "Cliente não encontrado")
    if cliente.anonimizado_em:
        raise HTTPException(409, "Cliente já foi anonimizado anteriormente")

    bloqueios = await verificar_bloqueios(db, client_id)
    if bloqueios and not forcar:
        raise HTTPException(409, {
            "mensagem": "Anonimização bloqueada — resolva as pendências ou "
                        "confirme com forcar=true (decisão registrada em auditoria).",
            "bloqueios": bloqueios,
        })

    agora = datetime.now(timezone.utc)

    # Sobrescreve PII. Mantém: id, tipo, status, created_at, relacionamentos
    # (casos, documentos, financeiro) — preservados por obrigação legal.
    cliente.nome = _MARCADOR if cliente.nome else cliente.nome
    cliente.razao_social = _MARCADOR if cliente.razao_social else cliente.razao_social
    cliente.nome_fantasia = None
    # Cutover C6/LGPD: cpf/cnpj em texto puro não existem mais (dropados na
    # migration 112). Limpa os campos cifrados/hash — senão a anonimização
    # ficaria incompleta (cpf_enc ainda decifrável, cpf_hash ainda comparável).
    cliente.cpf_enc = None
    cliente.cnpj_enc = None
    cliente.cpf_hash = None
    cliente.cnpj_hash = None
    cliente.data_nascimento = None
    cliente.profissao = None
    cliente.email = None
    cliente.telefone = None
    cliente.whatsapp = None
    cliente.cep = None
    cliente.logradouro = None
    cliente.numero = None
    cliente.complemento = None
    cliente.bairro = None
    cliente.observacoes = None
    cliente.anonimizado_em = agora

    # Portal do cliente: desativa qualquer login vinculado — a identidade que
    # existia (nome/e-mail) não corresponde mais aos dados reais.
    usuarios_portal = (await db.execute(
        select(User).where(User.client_id == client_id, User.is_active.is_(True))
    )).scalars().all()
    for u in usuarios_portal:
        u.is_active = False

    # Log de auditoria SEM PII — só o fato, quem autorizou, e se foi forçado
    # apesar de bloqueios (rastreabilidade da decisão).
    detalhes = f"Anonimização LGPD art.17. Motivo: {motivo or 'não informado'}."
    if bloqueios:
        detalhes += f" FORÇADO apesar de {len(bloqueios)} bloqueio(s) ativo(s)."
    await criar_audit_log(
        db, executor_id, executor_role, "ANONIMIZAR_LGPD", "clients", client_id,
        detalhes=detalhes,
    )
    await db.commit()

    return {
        "client_id": client_id,
        "anonimizado_em": agora.isoformat(),
        "portal_desativado_para": [u.id for u in usuarios_portal],
        "bloqueios_ignorados": bloqueios if bloqueios else None,
    }
