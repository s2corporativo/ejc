# ── app/routers/entrada.py ───────────────────────────────────────────────────
# Entrada Única (Bloco 3 — docs/DESENHO_BLOCO3_TELAS.md, seção 4).
#
# POST /entrada/analisar      : multipart (texto e/ou arquivos) → proposta de
#                               caso (RASCUNHO persistido no DocumentIntakeBatch,
#                               inclusive no caminho só-texto, document_count=0).
# POST /entrada/{id}/criar-caso: cria Cliente→Caso→vínculos em UMA transação,
#                               com gates de servidor e idempotência.
#
# Router fino: toda a orquestração vive em services/entrada_service.py, que
# REUTILIZA os pipelines existentes (Entrada Universal, Entrevista Inteligente,
# índice cego de CPF/CNPJ, conflito de interesses). Nenhuma chamada de IA nova.
# RBAC: piso advogado (mesmo de triagem/entrevista — criar caso é ato
# privativo de advogado no resto do sistema).
from __future__ import annotations

import logging
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.document_intake import DocumentIntakeBatch
from app.models.user import User
from app.schemas.entrada import CriarCasoEntradaRequest
from app.services import entrada_service

logger = logging.getLogger("ejc.entrada_unica.router")
router = APIRouter(prefix="/entrada", tags=["Entrada Única"])


def _role_value(user: User) -> str:
    return getattr(user.role, "value", user.role)


async def exigir_advogado(cu: User = Depends(get_current_user)) -> User:
    """Piso mais alto entre as peças encadeadas (triagem/entrevista pede
    advogado) — criar caso é ato privativo de advogado."""
    if ROLE_LEVEL.get(_role_value(cu), 0) < ROLE_LEVEL["advogado"]:
        raise HTTPException(403, "Entrada Única restrita a advogados")
    return cu


@router.post("/analisar", dependencies=[Depends(rate_limit("entrada-analisar", 6))])
async def analisar(
    files: list[UploadFile] = File(default=[]),
    texto: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(exigir_advogado),
):
    """Cole o relato, arraste os documentos, ou os dois — exige relato com 40+
    caracteres OU ao menos 1 arquivo. IA indisponível NUNCA derruba a análise
    (degradado=true + avisos). Toda saída de IA é rascunho HITL com AILog."""
    texto_limpo = (texto or "").strip() or None
    if not files and len(texto_limpo or "") < 40:
        raise HTTPException(
            422, "Envie ao menos um arquivo ou um relato com 40+ caracteres"
        )

    # O rascunho persiste também no caminho só-texto (document_count=0):
    # a proposta editável sobrevive ao F5 dentro de batch.resultado.
    batch = DocumentIntakeBatch(
        id=str(uuid4()), status="processando", created_by=cu.id,
    )
    db.add(batch)
    await db.commit()

    try:
        proposta = await entrada_service.analisar_entrada(
            db, cu, batch=batch, files=files, texto=texto_limpo,
        )
        batch.status = "concluido"
        batch.document_count = len(proposta.get("documentos") or [])
        batch.total_bytes = int(proposta.pop("total_bytes", 0) or 0)
        batch.resultado = {"entrada_unica": proposta}
        await db.commit()
        return proposta
    except HTTPException:
        await db.rollback()  # limpa transação pendente antes de reusar a sessão
        batch.status = "erro"; await db.commit(); raise
    except Exception as exc:
        await db.rollback()  # limpa transação pendente antes de reusar a sessão
        batch.status = "erro"; await db.commit()
        logger.exception("Falha na análise da Entrada Única (lote %s)", batch.id)
        raise HTTPException(500, f"Falha ao analisar a entrada: {str(exc)[:180]}")


@router.post("/{rascunho_id}/criar-caso",
             dependencies=[Depends(rate_limit("entrada-criar-caso", 10))])
async def criar_caso(
    rascunho_id: str,
    payload: CriarCasoEntradaRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(exigir_advogado),
):
    """Cria o caso a partir do rascunho revisado, em UMA transação:
    Cliente (se novo) → Case (aberto, G1) → documentos vinculados → Deadline →
    CaseMovimento → AuditLog. Idempotente por rascunho (lock pessimista):
    dois cliques não criam dois casos."""
    resultado = await entrada_service.criar_caso_do_rascunho(
        db, cu, rascunho_id, payload,
    )
    await db.commit()
    return resultado
