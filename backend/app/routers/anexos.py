# ── app/routers/anexos.py ────────────────────────────────────────────────────
# Documento Único de Anexos — capa + índice + folhas de separação padronizadas,
# com a mesclagem dos anexos reais do caso. Acesso: staff (advogado+), gate de
# ownership do caso (EOAB/LGPD). Legendas escritas pela IA via ai_gateway (base
# anti-alucinação + AILog + HITL). Todo PDF sai marcado como material de apoio à
# petição — conferência do advogado obrigatória.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User
from app.services import anexos_service as svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/anexos", tags=["Anexos — Documento Único"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class AnexoItemIn(BaseModel):
    document_id: Optional[str] = Field(None, description="ID de documento do GED (mesmo caso)")
    titulo: Optional[str] = Field(None, max_length=255, description="Rótulo do índice")
    legenda: Optional[str] = Field(None, max_length=400, description="Síntese manual (pula IA)")


class AnexosIn(BaseModel):
    case_id: str
    referencia: Optional[str] = Field(None, max_length=120, description="Subtítulo do banner")
    rodape: Optional[str] = Field(None, max_length=160, description="Sobrescreve o rodapé do juízo")
    itens: list[AnexoItemIn] = Field(..., min_length=1, max_length=60)
    gerar_legendas_ia: bool = True


class RazoesIn(AnexosIn):
    objetivo: Optional[str] = Field(None, max_length=600, description="Pedido/objetivo central da manifestação")
    area: str = Field("Consumidor", max_length=60)
    nivel: str = Field("maximo", description="Nível de raciocínio: padrao | alto | maximo")
    formato: str = Field("json", description="json (texto + citações) ou pdf")


def _pode_gerar(cu: User) -> bool:
    return ROLE_LEVEL.get(getattr(cu.role, "value", str(cu.role)), 0) >= ROLE_LEVEL["advogado"]


async def _preparar(db: AsyncSession, cu: User, body: AnexosIn):
    if not _pode_gerar(cu):
        raise HTTPException(403, "Acesso restrito a advogado ou superior.")
    case = await verificar_acesso_caso(db, cu, body.case_id)  # 404/403 + retorna o caso
    ctx = await svc.montar_contexto(db, case, body.referencia)
    if body.rodape:
        ctx.rodape = body.rodape
    itens = await svc.resolver_itens(
        db,
        cu_id=cu.id,
        case_id=body.case_id,
        itens_in=[i.model_dump() for i in body.itens],
        com_ia=body.gerar_legendas_ia,
    )
    return ctx, itens


# ── Preview (HITL): índice + legendas, sem gerar o PDF ────────────────────────

@router.post("/preview", dependencies=[Depends(rate_limit("anexos-preview", 15))])
async def preview(
    body: AnexosIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Devolve o índice e as legendas propostas para revisão do advogado ANTES de
    gerar o PDF. As legendas são RASCUNHO — o advogado pode editá-las e reenviar
    com `legenda` preenchida por item.
    """
    ctx, itens = await _preparar(db, cu, body)
    return {
        "titulo_acao": ctx.titulo_acao,
        "partes": ctx.partes,
        "referencia": ctx.referencia,
        "rodape": ctx.rodape,
        "itens": [
            {
                "ordem": it.ordem,
                "titulo": it.titulo,
                "legenda": it.legenda,
                "document_id": it.document_id,
                "anexo_inlineavel": bool(svc._caminho_anexo(it)),
            }
            for it in itens
        ],
        "aviso": "Legendas geradas por IA são RASCUNHO — revise antes de gerar o PDF.",
    }


# ── Geração do PDF único ──────────────────────────────────────────────────────

@router.post("/gerar", dependencies=[Depends(rate_limit("anexos-gerar", 5))])
async def gerar(
    body: AnexosIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Gera o Documento Único de Anexos (PDF) e o devolve para download."""
    ctx, itens = await _preparar(db, cu, body)
    try:
        pdf = await svc.montar_documento_unico(ctx, itens)
    except RuntimeError:  # weasyprint ausente / erro de render
        logger.warning("Geração do documento único de anexos indisponível", exc_info=True)
        raise HTTPException(503, "Geração de PDF indisponível no momento")
    filename = f"anexos_{body.case_id[:8]}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Razões / Fundamentação Jurídica (o texto argumentativo) ───────────────────

@router.post("/razoes", dependencies=[Depends(rate_limit("anexos-razoes", 5))])
async def razoes(
    body: RazoesIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Gera as RAZÕES / fundamentação jurídica do caso — fato → direito →
    responsabilidade → dano → pedido — referenciando os anexos pelo número
    (Doc. 0X). Grounding nos documentos + RAG, verificação de citações e HITL.
    `formato=pdf` devolve a minuta em PDF (rascunho controlado); senão, JSON com
    o texto e o relatório de citações para revisão do advogado.
    """
    ctx, itens = await _preparar(db, cu, body)
    resultado = await svc.gerar_razoes_juridicas(
        db,
        cu_id=cu.id,
        case_id=body.case_id,
        ctx=ctx,
        itens=itens,
        objetivo=body.objetivo,
        area=body.area,
        nivel=body.nivel,
    )

    if body.formato == "pdf":
        from app.services.pdf_service import peca_para_pdf_async
        try:
            pdf = await peca_para_pdf_async(
                f"Razões — {ctx.titulo_acao.title()}",
                resultado["texto"],
                pronto_protocolo=False,
            )
        except RuntimeError:
            logger.warning("Geração do PDF de razões indisponível", exc_info=True)
            raise HTTPException(503, "Geração de PDF indisponível no momento")
        filename = f"razoes_{body.case_id[:8]}.pdf"
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return resultado
