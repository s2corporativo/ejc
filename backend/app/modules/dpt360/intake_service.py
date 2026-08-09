from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ownership import is_gestao
from app.models.audit_log import criar_audit_log
from app.models.document_intake import DocumentIntakeBatch
from app.models.user import User
from app.modules.dpt360.intake_schemas import DptInboundOpportunity, DptInboundOpportunityOut
from app.modules.dpt360.schemas import DptOpportunityQueueItem


def _role(user: User) -> str:
    return str(
        getattr(getattr(user, "role", None), "value", getattr(user, "role", ""))
    )


async def list_inbound_opportunities(
    db: AsyncSession,
    user: User,
    *,
    limit: int = 100,
) -> list[DptOpportunityQueueItem]:
    """Fila mínima e sem PII para tornar o intake operacionalmente descobrível."""
    query = select(DocumentIntakeBatch).where(
        DocumentIntakeBatch.modalidade == "dpt360_oportunidade"
    )
    if not is_gestao(user):
        query = query.where(DocumentIntakeBatch.created_by == user.id)

    rows = (
        await db.execute(
            query.order_by(DocumentIntakeBatch.created_at.desc()).limit(
                max(1, min(limit, 200))
            )
        )
    ).scalars().all()

    output: list[DptOpportunityQueueItem] = []
    for batch in rows:
        result = batch.resultado if isinstance(batch.resultado, dict) else {}
        opportunity = result.get("dpt360_opportunity")
        data = opportunity if isinstance(opportunity, dict) else {}
        output.append(
            DptOpportunityQueueItem(
                intake_id=batch.id,
                status=str(data.get("status") or batch.nivel_prontidao or batch.status),
                created_at=batch.created_at,
                origem=str(data.get("origem") or "") or None,
                urgencia_declarada=(
                    str(data.get("urgencia_declarada") or "") or None
                ),
            )
        )
    return output


async def create_inbound_opportunity(
    db: AsyncSession,
    user: User,
    payload: DptInboundOpportunity,
) -> DptInboundOpportunityOut:
    if (
        payload.origem == "site_depaulateixeira"
        and not payload.consentimento_privacidade
    ):
        raise HTTPException(
            status_code=422,
            detail="O lead do site só pode ser importado quando o consentimento/aviso de privacidade estiver registrado.",
        )

    batch = DocumentIntakeBatch(
        id=str(uuid4()),
        status="concluido",
        modalidade="dpt360_oportunidade",
        nivel_prontidao="triagem_pendente",
        document_count=0,
        total_bytes=0,
        created_by=user.id,
        resultado={
            "dpt360_opportunity": {
                "origem": payload.origem,
                "pagina": payload.pagina,
                "campanha": payload.campanha,
                "assunto": payload.assunto,
                "mensagem": payload.mensagem,
                "empresa": payload.empresa,
                "contato": payload.contato,
                "email": str(payload.email) if payload.email else None,
                "telefone": payload.telefone,
                "urgencia_declarada": payload.urgencia_declarada,
                "consentimento_privacidade": payload.consentimento_privacidade,
                "external_ref": payload.external_ref,
                "status": "triagem_pendente",
            }
        },
    )
    db.add(batch)

    # Auditoria deliberadamente minimizada: nenhum campo livre do lead
    # (nome/e-mail/telefone/mensagem/campanha/página/assunto/external_ref) é
    # duplicado no log WORM. O batch funcional mantém os dados sob retenção.
    await criar_audit_log(
        db,
        user_id=user.id,
        user_role=_role(user),
        acao="CREATE",
        entidade="dpt360_opportunity",
        registro_id=batch.id,
        detalhes="Oportunidade empresarial recebida para triagem interna.",
        dados_depois={
            "origem": payload.origem,
            "urgencia_declarada": payload.urgencia_declarada,
            "consentimento_privacidade": payload.consentimento_privacidade,
        },
    )
    await db.commit()
    await db.refresh(batch)

    return DptInboundOpportunityOut(
        intake_id=batch.id,
        status="triagem_pendente",
        origem=payload.origem,
        created_at=batch.created_at.isoformat() if batch.created_at else None,
        next_step="Revisar na fila DPT de oportunidades antes de criar Cliente ou Caso.",
    )
