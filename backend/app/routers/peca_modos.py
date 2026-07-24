"""Sub-rotas de preparação dos modos de produção jurídica.

Estas rotas não redigem peças, não chamam IA e não criam documentos. A geração
continua exclusivamente em ``POST /pecas/gerar``, com os gates atuais de acesso,
ficha, RAG, AILog e revisão humana.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.user import User
from app.schemas.peca_workflow import (
    ModoProducao,
    ProducaoModoPreparada,
    ProducaoModoRequest,
)
from app.services.peca_service import (
    AREAS_DIREITO,
    AREAS_DIREITO_LABEL,
    TIPOS_PECA,
    TIPOS_PECA_GRUPO,
    TIPOS_PECA_VALIDOS,
)
from app.services.peca_workflow_service import (
    campos_guiados_obrigatorios,
    preparar_modo_producao,
)

router = APIRouter(prefix="/modos", tags=["Geração de Peças — Modos"])


def _garantir_piso_pecas(cu: User) -> None:
    role = getattr(getattr(cu, "role", None), "value", "")
    if ROLE_LEVEL.get(role, 0) < ROLE_LEVEL["estagiario"]:
        raise HTTPException(status_code=403, detail="Acesso negado")


@router.get("/meta")
async def meta_modos(cu: User = Depends(get_current_user)):
    """Catálogo dos quatro modos e dos campos guiados por tipo de peça."""

    _garantir_piso_pecas(cu)
    modos = [
        {
            "value": ModoProducao.LIVRE.value,
            "label": "Livre",
            "descricao": "Instrução direta do advogado com o contexto já validado.",
            "exige_caso": False,
            "exige_aprovacao": False,
        },
        {
            "value": ModoProducao.GUIADO.value,
            "label": "Guiado",
            "descricao": "Formulário jurídico estruturado por tipo de peça.",
            "exige_caso": False,
            "exige_aprovacao": False,
        },
        {
            "value": ModoProducao.MOLDE.value,
            "label": "Molde",
            "descricao": "Reutilização controlada de estrutura versionada do escritório.",
            "exige_caso": False,
            "exige_aprovacao": False,
        },
        {
            "value": ModoProducao.AGENTE.value,
            "label": "Agente",
            "descricao": "Plano determinístico com aprovação antes da redação.",
            "exige_caso": True,
            "exige_aprovacao": True,
        },
    ]
    return {
        "modos": modos,
        "tipos": [
            {
                "value": tipo,
                "label": TIPOS_PECA[tipo],
                "grupo": TIPOS_PECA_GRUPO[tipo],
                "campos_guiados": list(campos_guiados_obrigatorios(tipo)),
            }
            for tipo in TIPOS_PECA_VALIDOS
        ],
        "areas": [
            {"value": area, "label": AREAS_DIREITO_LABEL.get(area, area)}
            for area in AREAS_DIREITO
        ],
        "limites": {"documentos_considerados": 100},
        "hitl_obrigatorio": True,
        "endpoint_redacao": "/api/pecas/gerar",
    }


@router.post("/preparar", response_model=ProducaoModoPreparada)
async def preparar_modo(
    req: ProducaoModoRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Valida e estrutura o modo, sem iniciar a redação ou persistir peça."""

    _garantir_piso_pecas(cu)
    if req.tipo_peca not in TIPOS_PECA:
        raise HTTPException(
            status_code=422,
            detail=f"Tipo inválido. Use: {', '.join(TIPOS_PECA.keys())}",
        )
    if req.area_direito not in AREAS_DIREITO:
        raise HTTPException(
            status_code=422,
            detail=f"Área inválida. Use: {', '.join(AREAS_DIREITO)}",
        )
    if req.case_id:
        await verificar_acesso_caso(db, cu, req.case_id)

    return preparar_modo_producao(req)
