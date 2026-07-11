# ── app/routers/solicitacoes_documentos.py ───────────────────────────────────
# Solicitação de documentos ao CLIENTE — lado do ADVOGADO (migration 084).
#
#   POST /casos/{case_id}/solicitacoes-documentos → cria solicitação + itens,
#        e-mail ao cliente (template determinístico) + sino no Portal.
#   GET  /casos/{case_id}/solicitacoes-documentos → lista com itens.
#
# Segurança (padrão provas.py): piso advogado+ na escrita, ownership do caso
# via verificar_acesso_caso (404/403), rate limit por rota, audit log em toda
# escrita, validação Pydantic v2. Canais: e-mail + sino APENAS.
from __future__ import annotations

import logging
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.audit_log import criar_audit_log
from app.models.client import Client
from app.models.prova import Prova
from app.models.solicitacao_documento import (
    SolicitacaoDocumento,
    SolicitacaoDocumentoItem,
)
from app.models.user import User
from app.services.solicitacao_documento_service import (
    MAX_ITENS,
    MIN_ITENS,
    montar_email_solicitacao,
)

logger = logging.getLogger("ejc.solicitacoes_documentos")
router = APIRouter(
    prefix="/casos/{case_id}/solicitacoes-documentos",
    tags=["Solicitações de Documentos"],
)


# ── Schemas (Pydantic v2) ─────────────────────────────────────────────────────

class ItemIn(BaseModel):
    nome: str = Field(min_length=1, max_length=255)
    descricao: Optional[str] = Field(default=None, max_length=2000)
    prova_id: Optional[str] = Field(default=None, max_length=36)


class SolicitacaoIn(BaseModel):
    itens: list[ItemIn] = Field(min_length=MIN_ITENS, max_length=MAX_ITENS)
    mensagem: Optional[str] = Field(default=None, max_length=4000)


def _exigir_advogado(cu: User) -> None:
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["advogado"]:
        raise HTTPException(
            status_code=403,
            detail="Apenas advogados podem solicitar documentos ao cliente",
        )


def _out_item(i: SolicitacaoDocumentoItem, completo: bool = False) -> dict:
    base = {
        "id": i.id,
        "nome": i.nome,
        "descricao": i.descricao,
        "status": i.status,
    }
    if completo:
        base["documento_id"] = i.documento_id
        base["enviado_em"] = i.enviado_em
    return base


# ── Rotas ─────────────────────────────────────────────────────────────────────

@router.post("", status_code=201,
             dependencies=[Depends(rate_limit("solicitacoes-doc-criar", 15))])
async def criar_solicitacao(
    case_id: str,
    payload: SolicitacaoIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Cria a solicitação + itens e comunica o cliente (e-mail determinístico
    ao clients.email + sino no Portal para os usuários cliente_externo)."""
    _exigir_advogado(cu)
    case = await verificar_acesso_caso(db, cu, case_id)

    # prova_id (opcional) precisa pertencer ao MESMO caso — mesmo racional do
    # document_id em provas.py (não vaza existência de prova de outro caso).
    for item in payload.itens:
        if item.prova_id:
            p = (await db.execute(select(Prova).where(
                Prova.id == item.prova_id,
                Prova.deleted_at.is_(None),
            ))).scalar_one_or_none()
            if p is None or p.case_id != case_id:
                raise HTTPException(
                    status_code=400,
                    detail="Prova inválida ou de outro caso",
                )

    sol = SolicitacaoDocumento(
        id=str(uuid4()),
        case_id=case_id,
        client_id=case.client_id,
        mensagem=(payload.mensagem or None),
        status="pendente",
        created_by=cu.id,
    )
    db.add(sol)
    itens_orm: list[SolicitacaoDocumentoItem] = []
    for item in payload.itens:
        i = SolicitacaoDocumentoItem(
            id=str(uuid4()),
            solicitacao_id=sol.id,
            prova_id=item.prova_id,
            nome=item.nome.strip(),
            descricao=item.descricao,
            status="pendente",
        )
        db.add(i)
        itens_orm.append(i)

    await criar_audit_log(
        db, cu.id, cu.role.value, "CREATE", "solicitacoes_documentos", sol.id,
        detalhes=f"caso {case_id}: {len(itens_orm)} documento(s) solicitado(s)",
    )
    await db.commit()

    # ── Comunicação ao cliente (fail-safe: falha de canal não desfaz a
    # solicitação já persistida) ─────────────────────────────────────────────
    try:
        from app.services.datajud_sync_service import usuarios_portal_do_cliente
        from app.services.notification_service import enviar_email, notificar

        cli = (await db.execute(select(Client).where(
            Client.id == case.client_id, Client.deleted_at.is_(None),
        ))).scalar_one_or_none()

        assunto, corpo = montar_email_solicitacao(
            cli.nome_exibicao if cli else "cliente",
            [{"nome": i.nome, "descricao": i.descricao} for i in itens_orm],
            payload.mensagem,
        )
        if cli and cli.email:
            await enviar_email(cli.email, assunto, corpo)

        for uid in await usuarios_portal_do_cliente(db, case.client_id):
            await notificar(
                db, uid,
                "Documentos solicitados pelo escritório",
                f"O escritório solicitou {len(itens_orm)} documento(s). "
                "Envie-os pela seção Documentos do Portal.",
                tipo="documento", link="/portal/documentos",
                forcar_sino=True,
            )
    except Exception as e:
        logger.warning(
            "[SolicitacaoDoc] comunicação ao cliente falhou (solicitação %s): %s",
            sol.id, e,
        )

    return {
        "id": sol.id,
        "case_id": sol.case_id,
        "status": sol.status,
        "itens": [_out_item(i) for i in itens_orm],
    }


@router.get("", dependencies=[Depends(rate_limit("solicitacoes-doc-listar", 60))])
async def listar_solicitacoes(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Lista as solicitações do caso (não deletadas), com os itens."""
    await verificar_acesso_caso(db, cu, case_id)

    sols = (await db.execute(
        select(SolicitacaoDocumento).where(
            SolicitacaoDocumento.case_id == case_id,
            SolicitacaoDocumento.deleted_at.is_(None),
        ).order_by(SolicitacaoDocumento.created_at.desc())
    )).scalars().all()

    data = []
    for s in sols:
        itens = (await db.execute(
            select(SolicitacaoDocumentoItem).where(
                SolicitacaoDocumentoItem.solicitacao_id == s.id
            ).order_by(SolicitacaoDocumentoItem.created_at)
        )).scalars().all()
        data.append({
            "id": s.id,
            "mensagem": s.mensagem,
            "status": s.status,
            "created_at": s.created_at,
            "itens": [_out_item(i, completo=True) for i in itens],
        })
    return {"data": data}
