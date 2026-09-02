"""Tarefa de rescan/backfill de SHA-256 do GED.

Disparo pelo padrão do repositório: Celery quando disponível e alcançável,
BackgroundTasks como fallback. A task Celery é própria do rescan; nunca reutiliza
a task de indexação RAG.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from app.core.celery_app import celery_app
from app.services import document_rescan_service
from app.services.document_rescan_service import RescanResultado

logger = logging.getLogger("ejc.tasks.rescan")


def agendar_rescan(
    batch_id: str,
    background_tasks=None,
    settings=None,
) -> str:
    from app.core.config import get_settings

    cfg = settings or get_settings()
    if cfg.CELERY_ENABLED and _redis_alcancavel(cfg.REDIS_URL):
        try:
            rescan_documentos_task.delay(batch_id)
            return "celery"
        except Exception as excecao:
            logger.warning(
                "[rescan] Celery indisponível; exception_type=%s",
                type(excecao).__name__,
            )
    if background_tasks is not None:
        background_tasks.add_task(executar_rescan_task, batch_id)
        return "background"
    raise RuntimeError("nenhum mecanismo de background disponível")


def _redis_alcancavel(url: str, timeout: float = 1.0) -> bool:
    try:
        import socket
        from urllib.parse import urlparse
        parts = urlparse(url.replace("redis://", "http://").replace("rediss://", "https://"))
        host = parts.hostname or "localhost"
        porta = parts.port or 6379
        with socket.create_connection((host, porta), timeout=timeout):
            return True
    except OSError:
        return False


async def _com_engine_limpo(coro):
    from app.core.database import engine
    try:
        return await coro
    finally:
        await engine.dispose()


@celery_app.task(
    name="app.tasks.document_rescan",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def rescan_documentos_task(self, batch_id: str) -> str:
    """Wrapper Celery real do rescan; recebe somente o ID opaco do lote."""
    try:
        asyncio.run(_com_engine_limpo(executar_rescan_task(batch_id)))
        return batch_id
    except Exception:
        logger.warning("[rescan] task falhou; batch_id=%s", batch_id)
        raise self.retry(exc=RuntimeError("document_rescan_failed"))


async def executar_rescan_task(batch_id: str) -> None:
    from app.core.config import get_settings

    cfg = get_settings()
    upload_root = Path(cfg.UPLOAD_DIR)
    rclone_config = _configuracao_rclone(cfg)

    async with _sessao() as db:
        try:
            batch = await _buscar_batch(db, batch_id)
            if batch is None:
                return
            documentos = await document_rescan_service.selecionar_documentos(
                db,
                document_ids=_documentos_do_batch(batch),
                client_id=batch.cliente_id,
                case_id=batch.caso_id,
            )
            batch.iniciado_em = _agora()
            batch.status = "processando"
            await db.commit()

            resultado = await document_rescan_service.executar_rescan(
                upload_root=upload_root,
                rclone_config=rclone_config,
                documentos=documentos,
                db=db,
                batch_id=batch_id,
            )
            await _concluir_batch(db, batch_id, resultado)
        except Exception as excecao:
            await db.rollback()
            await _marcar_batch_falhou(db, batch_id)
            logger.warning(
                "[rescan] execução falhou; batch_id=%s exception_type=%s",
                batch_id,
                type(excecao).__name__,
            )
            raise


def _configuracao_rclone(cfg) -> dict | None:
    config_path = getattr(cfg, "RCLONE_CONFIG_PATH", "") or ""
    work_dir = getattr(cfg, "RCLONE_WORK_DIR", "") or ""
    if not config_path or not os.path.isfile(config_path):
        return None
    if not work_dir or not os.path.isdir(work_dir):
        return None
    remote = str(getattr(cfg, "RCLONE_REMOTE", "")).strip()
    if not remote:
        return None
    return {
        "config_path": Path(config_path),
        "remote": remote,
        "work_dir": Path(work_dir),
    }


def _sessao():
    from app.core.database import AsyncSessionLocal
    return AsyncSessionLocal()


def _agora():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc)


async def _buscar_batch(db, batch_id: str):
    from sqlalchemy import select
    from app.models import DocumentHashRescanBatch

    query = (
        select(DocumentHashRescanBatch)
        .where(DocumentHashRescanBatch.id == batch_id)
        .with_for_update(nowait=False)
    )
    resultado = await db.execute(query)
    return resultado.scalar_one_or_none()


def _documentos_do_batch(batch) -> list[str] | None:
    if not batch.document_ids_json:
        return None
    import json
    try:
        ids = json.loads(batch.document_ids_json)
    except (TypeError, ValueError):
        return None
    return [str(item) for item in ids if isinstance(item, str) and item]


async def _marcar_batch_falhou(db, batch_id: str) -> None:
    from sqlalchemy import update
    from app.models import DocumentHashRescanBatch

    await db.execute(
        update(DocumentHashRescanBatch)
        .where(DocumentHashRescanBatch.id == batch_id)
        .values(status="falhou", concluido_em=_agora())
    )
    await db.commit()


async def _concluir_batch(db, batch_id: str, resultado: RescanResultado) -> None:
    from sqlalchemy import update
    from app.models import DocumentHashRescanBatch

    await db.execute(
        update(DocumentHashRescanBatch)
        .where(DocumentHashRescanBatch.id == batch_id)
        .values(
            status="concluido",
            total_selecionado=resultado.itens_processados,
            total_concluidos=resultado.itens_concluidos,
            total_erros=resultado.itens_erro,
            total_nao_disponiveis=resultado.itens_nao_disponiveis,
            concluido_em=_agora(),
        )
    )
    await db.commit()
    logger.info(
        "[rescan] batch concluído; batch_id=%s processados=%s concluidos=%s erros=%s indisponiveis=%s",
        batch_id,
        resultado.itens_processados,
        resultado.itens_concluidos,
        resultado.itens_erro,
        resultado.itens_nao_disponiveis,
    )
