# ── app/tasks/rag_tasks.py ───────────────────────────────────────────────────
# Tasks Celery do RAG (Fase 3A).
#
# Workers Celery são processos SÍNCRONOS: cada task cria seu próprio event
# loop com asyncio.run e uma sessão de banco própria (AsyncSessionLocal),
# mesmo padrão dos scripts standalone (scripts/vetorizar_documentos.py).
# Como asyncio.run cria um loop NOVO a cada task, o pool do engine global é
# descartado ao final (engine.dispose()) — conexões asyncpg presas a um loop
# morto causariam "attached to a different loop" na task seguinte.
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.core.celery_app import celery_app

logger = logging.getLogger("ejc.tasks.rag")


async def _com_engine_limpo(coro) -> None:
    """Executa a corrotina e descarta o pool do engine no MESMO loop."""
    from app.core.database import engine
    try:
        await coro
    finally:
        await engine.dispose()


@celery_app.task(
    name="app.tasks.indexar_documento",
    bind=True, max_retries=3, default_retry_delay=30,
)
def indexar_documento_task(self, doc_id: str) -> str:
    """Gera embeddings dos chunks de um KnowledgeDoc (mesma lógica da
    _indexar_doc_bg usada pelos BackgroundTasks — fonte única de verdade)."""
    from app.routers.rag import _indexar_doc_bg
    try:
        asyncio.run(_com_engine_limpo(_indexar_doc_bg(doc_id)))
        return doc_id
    except Exception as exc:
        logger.warning("[celery] indexar_documento %s falhou: %s", doc_id, exc)
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.tasks.ocr_documento",
    bind=True, max_retries=2, default_retry_delay=60,
)
def ocr_documento_task(self, caminho_arquivo: str) -> dict:
    """OCR + extração estruturada de um arquivo já salvo em UPLOAD_DIR.

    Uso: processamento pesado fora do ciclo request/response (PDFs escaneados
    grandes). Retorna texto extraído (truncado) + dict de extração estruturada
    no result backend. O caminho é validado contra UPLOAD_DIR (path traversal).
    """
    from app.core.config import get_settings
    from app.services.extracao_estruturada import extrair_estruturas
    from app.services.ocr_service import extrair_texto_imagem, extrair_texto_pdf

    settings = get_settings()
    base = Path(settings.UPLOAD_DIR).resolve()
    caminho = Path(caminho_arquivo).resolve()
    if not str(caminho).startswith(str(base) + "/") and caminho != base:
        raise ValueError("Caminho fora do diretório de uploads")
    raw = caminho.read_bytes()

    if caminho.suffix.lower() == ".pdf":
        res = extrair_texto_pdf(raw)
    else:
        res = extrair_texto_imagem(raw)

    texto = res["texto"]
    return {
        "arquivo": caminho.name,
        "texto": texto[:300_000],  # mesmo teto por item da ingestão em lote
        "paginas": res.get("paginas"),
        "paginas_ocr": res.get("paginas_ocr"),
        "ocr_disponivel": res.get("ocr_disponivel"),
        "extracao": extrair_estruturas(texto),
    }
