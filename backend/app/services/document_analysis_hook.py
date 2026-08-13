"""Hook compartilhado de análise estratégica após documento entrar em um caso.

A rotina é deliberadamente assíncrona e tolerante a falha: o vínculo/upload do
GED já foi persistido antes da análise. Qualquer indisponibilidade de IA vira
warning e não desfaz o ato documental. AILog/HITL permanecem obrigatórios.
"""
from __future__ import annotations

import json
import logging
from uuid import uuid4

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.models.ai_log import AILog, AITipoUso, AIStatusHITL, classificar_risco_ia
from app.services.analise_estrategica import analisar_caso

logger = logging.getLogger(__name__)


async def analisar_documento_bg(
    case_id: str,
    ocr_text: str,
    doc_id: str,
    user_id: str,
) -> None:
    """Analisa documento com OCR no contexto do caso e registra AILog/HITL."""
    try:
        async with AsyncSessionLocal() as db:
            row = await db.execute(
                text(
                    "SELECT titulo, area, numero_processo, client_id "
                    "FROM cases WHERE id = :id"
                ),
                {"id": case_id},
            )
            caso = row.fetchone()

            resultado = await analisar_caso(
                titulo=(caso.titulo if caso else "") or "",
                area=(caso.area if caso else "") or "",
                numero_processo=(caso.numero_processo if caso else "") or "",
                texto_documento=ocr_text,
                scope_client_id=(caso.client_id if caso else None),
                case_id=case_id,
                db=db,
            )

            fontes = None
            if isinstance(resultado, dict) and resultado.get("_fontes_rag"):
                fontes = json.dumps(resultado["_fontes_rag"], ensure_ascii=False)[:2000]

            log = AILog(
                id=str(uuid4()),
                user_id=user_id,
                case_id=case_id,
                tipo_uso=AITipoUso.analise_caso,
                modelo="auto-analise-doc",
                prompt_sanitizado=f"[auto] analise estrategica do documento {doc_id}",
                resposta=json.dumps(resultado, ensure_ascii=False)[:8000],
                fontes_rag=fontes,
                risco_ia=classificar_risco_ia("analise_juridica"),
                status_hitl=AIStatusHITL.gerado,
            )
            db.add(log)
            await db.commit()
    except Exception as exc:  # fail-safe: ato documental já foi persistido
        logger.warning("Hook analise doc falhou: %s", exc)
