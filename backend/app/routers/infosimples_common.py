"""Adaptador HTTP compartilhado para consultas Infosimples existentes."""
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services import infosimples_service


async def executar_consulta(db: AsyncSession, cu: User, caminho: str, parametros: dict) -> dict:
    try:
        return await infosimples_service.consultar(
            db, caminho, parametros,
            user_id=cu.id, user_role=getattr(cu.role, "value", str(cu.role)),
        )
    except (
        infosimples_service.IntegracaoDesligadaError,
        infosimples_service.LimiteDiarioAtingidoError,
        infosimples_service.InfosimplesConsultaError,
        infosimples_service.InfosimplesIndisponivelError,
    ) as e:
        status_code, detail = infosimples_service.http_status_para_erro(e)
        raise HTTPException(status_code=status_code, detail=detail)
