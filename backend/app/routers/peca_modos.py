"""Router: modos controlados de produção jurídica (Livre, Guiado, Molde, Agente).

Duas rotas:
- GET  /pecas/modos/meta   → catálogo de modos, campos guiados e requisitos
- POST /pecas/modos/preparar → valida e prepara o modo para o pipeline canônico

Nenhuma chamada de IA. Nenhuma persistência. Saída é um contrato de preparação
que o frontend anexa a ``instrucoes_adicionais`` de POST /pecas/gerar.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import get_current_user, ROLE_LEVEL
from app.core.ownership import verificar_acesso_caso
from app.core.database import get_db
from app.models.user import User
from app.schemas.peca_workflow import (
    ConfiguracaoMolde,
    ModoProducao,
    ProducaoModoRequest,
    ReferenciaDocumento,
)
from app.services.peca_workflow_service import (
    campos_guiados_obrigatorios,
    preparar_modo_producao,
)
from app.services.peca_service import TIPOS_PECA, AREAS_DIREITO
from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/pecas/modos", tags=["Modos de Produção"])
logger = logging.getLogger(__name__)


# ── Catálogo de modos ────────────────────────────────────────────────────────

_MODOS_META = [
    {
        "value": "livre",
        "label": "Modo Livre",
        "descricao": "Instrução livre do advogado. O pipeline decide a estrutura.",
        "exige_caso": False,
        "exige_aprovacao": False,
    },
    {
        "value": "guiado",
        "label": "Modo Guiado",
        "descricao": "Formulário estruturado por tipo de peça.",
        "exige_caso": False,
        "exige_aprovacao": False,
    },
    {
        "value": "molde",
        "label": "Modo Molde",
        "descricao": "Reaproveita a estrutura de uma peça anterior do escritório.",
        "exige_caso": False,
        "exige_aprovacao": False,
    },
    {
        "value": "agente",
        "label": "Modo Agente",
        "descricao": "Planejamento em etapas com aprovação antes da redação.",
        "exige_caso": True,
        "exige_aprovacao": True,
    },
]


@router.get("/meta")
async def modos_meta(
    cu: User = Depends(get_current_user),
):
    """Catálogo dos modos de produção: requisitos, campos guiados por tipo
    e endpoint canônico de redação. Piso de role = estagiário."""
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["estagiario"]:
        raise HTTPException(403, "Acesso negado")

    tipos = []
    for value, label in TIPOS_PECA.items():
        campos = list(campos_guiados_obrigatorios(value))
        tipos.append({
            "value": value,
            "label": label,
            "grupo": "",  # Frontend já usa /pecas/meta para grupos
            "campos_guiados": campos,
        })

    areas = [{"value": a, "label": a.replace("_", " ").title()} for a in AREAS_DIREITO]

    return {
        "modos": _MODOS_META,
        "tipos": tipos,
        "areas": areas,
        "limites": {"documentos_considerados": 100},
        "hitl_obrigatorio": True,
        "endpoint_redacao": "/api/pecas/gerar",
    }


# ── Preparação do modo ───────────────────────────────────────────────────────

class RefDocRequest(BaseModel):
    documento_id: str = Field(..., min_length=1, max_length=64)
    versao: Optional[int] = Field(default=None, ge=1)
    hash_conteudo: Optional[str] = Field(default=None, min_length=6, max_length=128)
    nome: Optional[str] = Field(default=None, max_length=500)


class MoldeRequest(BaseModel):
    referencia: RefDocRequest
    preservar: list[str] = Field(
        default_factory=lambda: [
            "ordem_dos_topicos",
            "titulos",
            "estilo",
            "estrutura_argumentativa",
            "padrao_de_pedidos",
        ],
        max_length=20,
    )
    substituir: list[str] = Field(
        default_factory=lambda: [
            "partes",
            "fatos",
            "datas",
            "valores",
            "fundamentos_especificos",
            "pedidos_aplicaveis",
        ],
        max_length=30,
    )


class PrepararModoRequest(BaseModel):
    modo: str = Field(..., description="livre | guiado | molde | agente")
    case_id: Optional[str] = Field(default=None, max_length=64)
    tipo_peca: str = Field(..., min_length=2, max_length=100)
    area_direito: str = Field(..., min_length=2, max_length=100)
    instrucao_livre: Optional[str] = Field(default=None, max_length=6000)
    respostas_guiadas: dict[str, Any] = Field(default_factory=dict)
    documentos_considerados: list[RefDocRequest] = Field(
        default_factory=list, max_length=100,
    )
    molde: Optional[MoldeRequest] = None
    aprovado_para_redacao: bool = False


@router.post("/preparar")
async def preparar_modo(
    req: PrepararModoRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Valida e prepara um modo de produção sem chamar IA.

    A saída (``ProducaoModoPreparada``) contém ``instrucoes_pipeline`` que o
    frontend anexa ao campo ``instrucoes_adicionais`` de ``POST /pecas/gerar``.
    """
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["estagiario"]:
        raise HTTPException(403, "Acesso negado")

    # Valida modo
    try:
        modo = ModoProducao(req.modo)
    except ValueError:
        raise HTTPException(
            422, f"Modo inválido. Use: {', '.join(m.value for m in ModoProducao)}"
        )

    # Valida tipo e área contra o catálogo canônico
    if req.tipo_peca not in TIPOS_PECA:
        raise HTTPException(
            422, f"Tipo inválido. Use: {', '.join(TIPOS_PECA.keys())}"
        )
    if req.area_direito not in AREAS_DIREITO:
        raise HTTPException(
            422, f"Área inválida. Use: {', '.join(AREAS_DIREITO)}"
        )

    # Ownership do caso (quando vinculado)
    if req.case_id:
        await verificar_acesso_caso(db, cu, req.case_id)

    # Monta o contrato interno
    try:
        entrada = ProducaoModoRequest(
            modo=modo,
            case_id=req.case_id,
            tipo_peca=req.tipo_peca,
            area_direito=req.area_direito,
            instrucao_livre=req.instrucao_livre,
            respostas_guiadas=req.respostas_guiadas,
            documentos_considerados=[
                ReferenciaDocumento(
                    documento_id=d.documento_id,
                    versao=d.versao,
                    hash_conteudo=d.hash_conteudo,
                    nome=d.nome,
                )
                for d in req.documentos_considerados
            ],
            molde=ConfiguracaoMolde(
                referencia=ReferenciaDocumento(
                    documento_id=req.molde.referencia.documento_id,
                    versao=req.molde.referencia.versao,
                    hash_conteudo=req.molde.referencia.hash_conteudo,
                    nome=req.molde.referencia.nome,
                ),
                preservar=req.molde.preservar,
                substituir=req.molde.substituir,
            ) if req.molde else None,
            aprovado_para_redacao=req.aprovado_para_redacao,
        )
    except Exception as e:
        logger.warning("[PecaModos] schema invalido: %s", e)
        raise HTTPException(422, f"Dados invalidos: {e}")

    resultado = preparar_modo_producao(entrada)

    logger.info(
        "[PecaModos] modo=%s tipo=%s area=%s pronto=%s bloqueios=%d",
        req.modo, req.tipo_peca, req.area_direito,
        resultado.pronto_para_redacao, len(resultado.bloqueios),
    )

    return resultado.model_dump()
