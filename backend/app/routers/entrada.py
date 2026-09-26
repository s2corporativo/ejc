# ── app/routers/entrada.py ───────────────────────────────────────────────────
# Entrada Única (Bloco 3 — docs/DESENHO_BLOCO3_TELAS.md, seção 4).
#
# POST /entrada/analisar:
#   - multipart texto/arquivos → proposta de caso (rascunho persistido);
#   - com ?case_id=<id> → dossiê jurídico profundo do caso já criado.
# POST /entrada/{id}/criar-caso: cria Cliente→Caso→vínculos em UMA transação,
#                               com gates de servidor e idempotência.
#
# Router fino: toda a orquestração vive em services/entrada_service.py e
# services/entrada_juridica_service.py, que REUTILIZAM os pipelines existentes.
# RBAC: piso advogado (mesmo de triagem/entrevista e motor de peça).
from __future__ import annotations

import logging
from typing import Annotated, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.document_intake import DocumentIntakeBatch
from app.models.user import User
from app.schemas.entrada import (
    CriarCasoEntradaRequest,
    VincularCasoExistenteEntradaRequest,
)
from app.services import entrada_juridica_service, entrada_service
from app.services.contract_migration import mark_contract_response

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
    case_id: Annotated[Optional[str], Query(max_length=36)] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(exigir_advogado),
    response: Response = None,
):
    """Porta única de análise jurídica.

    Sem `case_id`: relato/documentos → proposta preliminar de novo caso.
    Com `case_id`: caso oficial existente → dossiê jurídico profundo versionado
    em RASCUNHO. Em ambos os modos, RBAC/HITL/auditoria continuam obrigatórios.
    """
    if case_id:
        resultado = await entrada_juridica_service.gerar_dossie_juridico(db, cu, case_id)
        mark_contract_response(response, route="/entrada/analisar")
        return resultado

    texto_limpo = (texto or "").strip() or None
    if not files and len(texto_limpo or "") < 40:
        raise HTTPException(
            422, "Envie ao menos um arquivo ou um relato com 40+ caracteres"
        )
    if texto_limpo and len(texto_limpo) > 15_000:
        raise HTTPException(422, "Relato excede 15.000 caracteres")

    batch = DocumentIntakeBatch(
        id=str(uuid4()), status="processando", created_by=cu.id,
    )
    db.add(batch)
    await db.commit()

    try:
        proposta = await entrada_service.analisar_entrada(
            db, cu, batch=batch, files=files, texto=texto_limpo,
        )
        proposta["conteudo_identificado"] = entrada_juridica_service.identificar_conteudo(
            texto_limpo,
            [
                {"titulo": d.get("nome"), "tipo": d.get("classificacao")}
                for d in (proposta.get("documentos") or [])
                if isinstance(d, dict)
            ],
        )
        batch.status = "concluido"
        batch.document_count = len(proposta.get("documentos") or [])
        batch.total_bytes = int(proposta.pop("total_bytes", 0) or 0)
        batch.resultado = {"entrada_unica": proposta}
        await db.commit()
        mark_contract_response(response, route="/entrada/analisar")
        return proposta
    except HTTPException:
        await db.rollback()
        batch.status = "erro"
        await db.commit()
        raise
    except Exception as exc:
        await db.rollback()
        batch.status = "erro"
        await db.commit()
        logger.exception("Falha na análise da Entrada Única (lote %s)", batch.id)
        raise HTTPException(
            500, "Falha ao analisar a entrada. Os originais enviados foram "
                 "preservados; tente novamente ou contate a gestão.",
        ) from exc


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


@router.post(
    "/{rascunho_id}/vincular-caso/{case_id}",
    dependencies=[Depends(rate_limit("entrada-vincular-caso", 10))],
)
async def vincular_caso_existente(
    rascunho_id: str,
    case_id: str,
    payload: VincularCasoExistenteEntradaRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(exigir_advogado),
):
    """Vincula um CNJ confirmado a caso existente sem criar caso duplicado."""
    resultado = await entrada_service.vincular_rascunho_ao_caso_existente(
        db, cu, rascunho_id, case_id, payload,
    )
    await db.commit()
    return resultado
