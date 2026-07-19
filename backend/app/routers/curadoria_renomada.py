from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.core.rate_limit import rate_limit

# Gestão do escritório — quem pode disparar sincronização/ingestão da base.
_GESTAO = ["superadmin", "admin", "socio"]

# INDISPONIBILIDADE EXPLÍCITA (auditoria 2026-07-19): a "base de teses renomadas"
# curada não existe. Os handlers ANTES devolviam lista vazia / sucesso fabricado /
# string fixa — mock enganoso que fingia dados/ingestão reais. Enquanto a base não
# for implementada e ligada ao RAG, os endpoints respondem 503 honesto em vez de
# simular resultado. Para pesquisa jurisprudencial real, ver /api/search e
# /api/knowledge-hub (RAG híbrido).
_INDISPONIVEL = (
    "Curadoria de teses renomadas ainda não está disponível: a base curada não foi "
    "implementada. Use a Pesquisa (/api/search) e o Conhecimento Jurídico "
    "(/api/rag) para busca real enquanto este módulo não é ativado."
)

router = APIRouter(prefix="/curadoria", tags=["Curadoria Renomada"])

class TeseRenomada(BaseModel):
    id: Optional[int] = None
    titulo: str
    autor: str
    ramo: str
    conteudo: str
    precedentes: List[str]
    taxa_sucesso_estimada: float

@router.get("/teses", response_model=List[TeseRenomada])
async def listar_teses(ramo: Optional[str] = None, cu: User = Depends(get_current_user)):
    # Indisponível — não fingir base vazia (ver _INDISPONIVEL).
    raise HTTPException(status_code=503, detail=_INDISPONIVEL)

@router.post("/teses/sincronizar", dependencies=[Depends(rate_limit("curadoria-sincronizar", 10))])
async def sincronizar_teses_externas(cu: User = Depends(require_roles(_GESTAO))):
    """
    Sincroniza teses de fontes oficiais e juristas renomados para o RAG.
    Indisponível — antes retornava sucesso fabricado sem ingerir nada.
    """
    raise HTTPException(status_code=503, detail=_INDISPONIVEL)

@router.get("/analise-vencedora/{caso_id}", dependencies=[Depends(rate_limit("curadoria-analise", 15))])
async def analise_vencedora(caso_id: str, cu: User = Depends(get_current_user)):
    """
    Analisa um caso específico cruzando com a base de teses renomadas.
    Indisponível — antes retornava string fixa e não validava ownership do caso;
    ao ligar à lógica real, aplicar verificar_acesso_caso(db, cu, caso_id).
    """
    raise HTTPException(status_code=503, detail=_INDISPONIVEL)
