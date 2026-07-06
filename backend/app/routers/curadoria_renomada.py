from fastapi import APIRouter, Depends
from typing import List, Optional
from pydantic import BaseModel
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.core.rate_limit import rate_limit

# Gestão do escritório — quem pode disparar sincronização/ingestão da base.
_GESTAO = ["superadmin", "admin", "socio"]

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
    # Simulação de busca no banco de dados de curadoria
    return []

@router.post("/teses/sincronizar", dependencies=[Depends(rate_limit("curadoria-sincronizar", 10))])
async def sincronizar_teses_externas(cu: User = Depends(require_roles(_GESTAO))):
    """
    Sincroniza teses de fontes oficiais e juristas renomados para o RAG.
    """
    # Lógica para ingerir teses coletadas
    return {"status": "sucesso", "mensagem": "Teses sincronizadas e vetorizadas."}

@router.get("/analise-vencedora/{caso_id}", dependencies=[Depends(rate_limit("curadoria-analise", 15))])
async def analise_vencedora(caso_id: int, cu: User = Depends(get_current_user)):
    """
    Analisa um caso específico cruzando com a base de teses renomadas.
    """
    # Lógica de match semântico com a base de elite
    return {"analise": "Sugestão de tese baseada em juristas renomados..."}
