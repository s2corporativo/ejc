"""
Módulo de Banco de Teses Jurídicas Estruturado - EJC v4.0 (Seção 3.122).
Cadastro, ranking de desempenho e reaproveitamento inteligente de teses.
"""
import logging
from uuid import uuid4
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Column, String, Text, Float, DateTime, func, select, Boolean
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.database import Base, get_db
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.core.rate_limit import rate_limit

# Model ORM
class TeseJuridica(Base):
    __tablename__ = "teses_juridicas_v4"
    id = Column(String(36), primary_key=True)
    titulo = Column(String(255), nullable=False)
    descricao = Column(Text, nullable=False)
    fundamentacao = Column(Text, nullable=False)
    jurisprudencia = Column(Text, nullable=True)
    taxa_sucesso = Column(Float, default=0.0)
    area_juridica = Column(String(50), nullable=False)
    tribunal = Column(String(100), nullable=True)
    magistrado = Column(String(100), nullable=True)
    vencedora = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# Schemas
class TeseCreate(BaseModel):
    titulo: str
    descricao: str
    fundamentacao: str
    jurisprudencia: Optional[str] = None
    area_juridica: str
    tribunal: Optional[str] = None
    magistrado: Optional[str] = None

class TeseResponse(TeseCreate):
    id: str
    taxa_sucesso: float
    vencedora: bool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/teses-v4", tags=["Banco de Teses Jurídicas"])

@router.post("/", response_model=TeseResponse, status_code=201,
             dependencies=[Depends(require_roles(["admin", "socio", "advogado"]))])
async def criar_tese(payload: TeseCreate, db: AsyncSession = Depends(get_db)):
    t = TeseJuridica(id=str(uuid4()), **payload.model_dump())
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t

@router.get("/", response_model=List[TeseResponse])
async def listar_teses(
    area: Optional[str] = None,
    vencedoras: bool = False,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(TeseJuridica)
    if area:
        q = q.where(TeseJuridica.area_juridica == area)
    if vencedoras:
        q = q.where(TeseJuridica.vencedora == True)
    
    q = q.order_by(TeseJuridica.taxa_sucesso.desc())
    res = await db.execute(q)
    return res.scalars().all()

@router.get("/sugestao-ia", dependencies=[Depends(rate_limit("teses-sugestao-ia", 15))])
async def sugerir_teses_ia(
    contexto: str = Query(..., min_length=3, max_length=12000),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Sugestão de teses pela IA integrada ao RAG (Seção 3.136).

    Consolidado: gateway CENTRAL (app.services.ai_gateway) + sanitização LGPD
    com abort em PII residual + AILog obrigatório (auditoria HITL).
    """
    from app.services import ai_gateway as gateway_central
    from app.services.ai_guard import sanitizar_ou_abortar, registrar_ai_log
    from app.models.ai_log import AITipoUso

    contexto_limpo, pii = sanitizar_ou_abortar(contexto)

    # Lista as teses reais do banco (listar_teses) e usa as 5 primeiras como
    # contexto para a IA. NÃO é busca vetorial/RAG — é listagem direta no DB.
    teses_existentes = await listar_teses(db=db)
    contexto_teses = "\n".join([f"- {t.titulo}: {t.descricao}" for t in teses_existentes[:5]])

    prompt = (
        f"Com base no contexto do caso: {contexto_limpo}\n\n"
        f"E nestas teses do escritório:\n{contexto_teses}\n\n"
        "Sugira a melhor estratégia e novas teses. Não invente julgados/artigos; "
        "não prometa resultado. Toda sugestão é rascunho sob revisão do advogado."
    )
    try:
        resp = await gateway_central.chat(
            [{"role": "user", "content": prompt}],
            task_type="analise_juridica",
        )
    except Exception:
        logger.exception("Falha na chamada de IA (teses v4)")
        raise HTTPException(502, "IA indisponível no momento")

    log_id = await registrar_ai_log(
        db,
        user_id=cu.id,
        tipo_uso=AITipoUso.analise_caso,
        case_id=None,
        prompt_sanitizado=prompt,
        pii_removida=pii,
        resposta=resp.texto,
        modelo=f"{resp.provedor}/{resp.modelo}",
        tokens_input=resp.input_tokens,
        tokens_output=resp.output_tokens,
    )

    # Shape legado do processar_demanda preservado + campos de auditoria.
    return {
        "modelo_utilizado": f"{resp.provedor}/{resp.modelo}",
        "tipo_demanda": "juridico_profundo",
        "resposta": resp.texto,
        "status": "sucesso",
        "log_id": log_id,
        "is_rascunho": True,
        "aviso_hitl": "Rascunho sujeito à revisão humana (HITL obrigatório — OAB).",
    }
