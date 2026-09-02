"""Hook compartilhado de análise estratégica após documento entrar em um caso.

A rotina é deliberadamente assíncrona e, por padrão, tolerante a falha: o
vínculo/upload do GED já foi persistido antes da análise. O worker durável pode
pedir ``raise_on_error=True`` para acionar retry; callers legados continuam
fail-soft.

AILog/HITL permanecem obrigatórios. Quando há conteúdo útil, também é gerado um
CaseIntelligenceSnapshot append-only, não aprovado, ligado ao AILog.
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


def _lista(valor) -> list:
    """Normaliza saída variável do LLM para lista sem itens vazios."""
    if valor in (None, ""):
        return []
    if isinstance(valor, list):
        return [item for item in valor if item not in (None, "", {}, [])]
    return [valor]


def payload_snapshot_documento(resultado: dict, doc_id: str) -> dict:
    """Converte o parecer estratégico para o contrato do snapshot do caso."""
    estrategia = resultado.get("estrategia")
    jurimetria = (
        resultado.get("jurimetria")
        if isinstance(resultado.get("jurimetria"), dict)
        else {}
    )

    riscos = {
        "itens": _lista(resultado.get("riscos")),
        "pontos_fracos": _lista(resultado.get("pontos_fracos")),
        "chance_exito": jurimetria.get("chance_sucesso_percent"),
    }
    riscos = {chave: valor for chave, valor in riscos.items() if valor not in (None, [], "")}

    teses_brutas = _lista(resultado.get("teses_campeas"))
    titulos = [
        (item.get("titulo") if isinstance(item, dict) else item)
        for item in teses_brutas
    ]
    titulos = [titulo for titulo in titulos if titulo]
    teses = None
    if titulos:
        teses = {
            "principal": titulos[0],
            "secundarias": titulos[1:],
            "detalhe": [item for item in teses_brutas if isinstance(item, dict)],
        }

    payload = {
        "documento_id": doc_id,
        "fatos": resultado.get("sumario_fatos"),
        "teses": teses,
        "riscos": riscos or None,
        "pontos_fortes": _lista(resultado.get("pontos_fortes")),
        "estrategia": estrategia if isinstance(estrategia, dict) else None,
        "proximos_passos": _lista(resultado.get("proximos_passos")),
        "alertas": _lista(resultado.get("alertas")),
        "fontes": ["leitura_documento"]
        + (["rag_interno"] if resultado.get("_fontes_rag") else []),
    }
    if resultado.get("_verificacao_citacoes") is not None:
        payload["verificacao_citacoes"] = resultado["_verificacao_citacoes"]
    return {
        chave: valor
        for chave, valor in payload.items()
        if valor not in (None, [], {}, "")
    }


async def _gravar_snapshot_documento(
    db,
    *,
    case_id: str,
    doc_id: str,
    resultado,
    ai_log_id: str,
) -> None:
    if not isinstance(resultado, dict) or resultado.get("erro"):
        return
    payload = payload_snapshot_documento(resultado, doc_id)
    conteudo_juridico = set(payload) - {"documento_id", "fontes", "verificacao_citacoes"}
    if not conteudo_juridico:
        return

    from app.services import case_intelligence_service as cis

    await cis.gravar_snapshot_seguro(
        db,
        case_id=case_id,
        origem="documento",
        payload=cis.compactar_payload(payload),
        resumo=(resultado.get("sumario_fatos") or "Leitura estratégica de documento anexado")[:500],
        ai_log_ids=[ai_log_id],
        criado_por=None,
    )


async def analisar_documento_bg(
    case_id: str,
    ocr_text: str,
    doc_id: str,
    user_id: str,
    *,
    raise_on_error: bool = False,
) -> bool:
    """Analisa OCR, registra AILog/HITL e snapshot.

    Em falha, o comportamento padrão permanece fail-soft. Workers duráveis usam
    ``raise_on_error=True`` para transformar a falha em retry da fila.
    """
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

            log_id = str(uuid4())
            log = AILog(
                id=log_id,
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

            await _gravar_snapshot_documento(
                db,
                case_id=case_id,
                doc_id=doc_id,
                resultado=resultado,
                ai_log_id=log_id,
            )
        return True
    except Exception as exc:
        logger.warning(
            "Hook analise documental falhou; exception_type=%s",
            type(exc).__name__,
        )
        if raise_on_error:
            raise
        return False
