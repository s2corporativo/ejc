"""
Router: Geração de peças jurídicas com pipeline 7 etapas + SSE streaming.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.core.ownership import verificar_acesso_caso
from app.models.user import User
from app.models.ai_log import AILog
from app.models.legal_doc import LegalDoc, PecaTipo, PecaStatus
from app.services.peca_service import gerar_peca_pipeline, TIPOS_PECA, AREAS_DIREITO
from app.services.advogado_style_service import montar_instrucoes_estilo_para_prompt
from datetime import date
from uuid import uuid4

router = APIRouter(prefix="/pecas", tags=["Geração de Peças"])


class GerarPecaRequest(BaseModel):
    tipo_peca: str = Field(..., description=f"Tipo: {', '.join(TIPOS_PECA.keys())}")
    area_direito: str = Field(..., description=f"Área: {', '.join(AREAS_DIREITO)}")
    descricao_fatos: str = Field(..., min_length=50, max_length=10000)
    pedidos: str = Field(..., min_length=10, max_length=3000)
    nomes_proteger: list[str] = Field(default=[], description="Nomes para anonimizar (LGPD)")
    case_id: Optional[str] = None
    instrucoes_adicionais: Optional[str] = Field(None, max_length=1000)


@router.post("/gerar")
async def gerar_peca(
    req: GerarPecaRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Pipeline 7 etapas para geração de peças jurídicas com SSE streaming.
    Retorna Server-Sent Events: step(1-7) → concluido com o documento completo.
    """
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["estagiario"]:
        raise HTTPException(403, "Acesso negado")

    if req.tipo_peca not in TIPOS_PECA:
        raise HTTPException(422, f"Tipo inválido. Use: {', '.join(TIPOS_PECA.keys())}")

    if req.area_direito not in AREAS_DIREITO:
        raise HTTPException(422, f"Área inválida. Use: {', '.join(AREAS_DIREITO)}")

    # Bloco 5 (continuação): case_id existia mas sem checagem de ownership —
    # checado ANTES de abrir o stream SSE, para 403 vir como erro normal (não
    # quebrar a conexão a meio da geração).
    escopo_cli = None
    if req.case_id:
        await verificar_acesso_caso(db, cu, req.case_id)
        from app.services.ai_service import _escopo_cliente_do_caso
        escopo_cli = await _escopo_cliente_do_caso(db, req.case_id)

    async def stream():
        try:
            instrucoes = req.instrucoes_adicionais or ""
            estilo = await montar_instrucoes_estilo_para_prompt(db, cu.id)
            if estilo:
                instrucoes = (
                    f"{instrucoes}\n\n[ESTILO DO ADVOGADO]\n{estilo}"
                    if instrucoes else f"[ESTILO DO ADVOGADO]\n{estilo}"
                )[:2500]

            async for chunk in gerar_peca_pipeline(
                db=db,
                user_id=cu.id,
                tipo_peca=req.tipo_peca,
                area_direito=req.area_direito,
                descricao_fatos=req.descricao_fatos,
                pedidos=req.pedidos,
                scope_client_id=escopo_cli,
                nomes_proteger=req.nomes_proteger,
                case_id=req.case_id,
                instrucoes_adicionais=instrucoes,
            ):
                yield chunk
        except Exception as e:
            import json
            yield f"event: erro\ndata: {json.dumps({'detail': str(e)[:300]}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/")
async def listar_pecas(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    case_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Lista peças geradas pelo usuário (logs com tipo elaboracao_peca)."""
    from app.models.ai_log import AITipoUso
    from sqlalchemy import func as sqlfunc

    q = select(AILog).where(AILog.tipo_uso == AITipoUso.redacao_peca)

    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        q = q.where(AILog.user_id == cu.id)

    if case_id:
        q = q.where(AILog.case_id == case_id)

    q = q.order_by(AILog.created_at.desc())

    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery())
    )).scalar()
    rows = (await db.execute(
        q.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()

    return {
        "data": [
            {
                "id": l.id,
                "case_id": l.case_id,
                "modelo": l.modelo,
                "status_hitl": l.status_hitl.value,
                "pii_removida": l.pii_removida,
                "tokens_input": l.tokens_input,
                "tokens_output": l.tokens_output,
                "created_at": l.created_at,
            }
            for l in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


class LinhaDemonstrativo(BaseModel):
    label: str
    valor: str


class DemonstrativoRequest(BaseModel):
    titulo: str = Field(..., min_length=2, max_length=200)
    base_legal: Optional[str] = Field(None, max_length=300)
    linhas: list[LinhaDemonstrativo] = Field(default=[])
    rodape: Optional[str] = Field(None, max_length=2000)
    case_id: Optional[str] = None


@router.post("/demonstrativo", status_code=201)
async def gerar_demonstrativo(
    req: DemonstrativoRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Converte o resultado de uma calculadora em um Demonstrativo de Cálculo
    salvo como peça (LegalDoc) rascunho — vinculável a um caso. Reusa a esteira
    de peças existente; resultado é MINUTA (revisão humana obrigatória)."""
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["estagiario"]:
        raise HTTPException(403, "Acesso negado")
    if req.case_id:
        await verificar_acesso_caso(db, cu, req.case_id)  # ownership do caso vinculado

    linhas_txt = "\n".join(f"  • {l.label}: {l.valor}" for l in req.linhas) or "  (sem itens)"
    partes = [
        f"DEMONSTRATIVO DE CÁLCULO — {req.titulo}",
        f"\nElaborado em {date.today().strftime('%d/%m/%Y')} por {cu.full_name}"
        + (f" (OAB {cu.oab_number})" if getattr(cu, "oab_number", None) else ""),
        "\nMEMÓRIA DE CÁLCULO:\n" + linhas_txt,
    ]
    if req.base_legal:
        partes.append(f"\nFUNDAMENTO: {req.base_legal}")
    if req.rodape:
        partes.append(f"\n{req.rodape}")
    partes.append(
        "\n____________________________________________________________\n"
        "MINUTA gerada a partir de calculadora — revisão humana obrigatória. "
        "Conferir índices, datas-base, correção monetária e juros antes de qualquer uso."
    )
    conteudo = "\n".join(partes)

    doc = LegalDoc(
        id=str(uuid4()),
        titulo=f"Demonstrativo — {req.titulo}"[:255],
        tipo_peca=PecaTipo.outro,
        status=PecaStatus.rascunho,
        conteudo=conteudo,
        ai_generated=False,
        case_id=req.case_id or None,
        created_by=cu.id,
    )
    db.add(doc)
    await db.commit()
    return {"id": doc.id, "titulo": doc.titulo, "conteudo": conteudo,
            "detail": "Demonstrativo salvo como rascunho em Peças."}
