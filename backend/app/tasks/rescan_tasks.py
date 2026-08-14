"""Tarefa de rescan/backfill de SHA-256 (Épico #1019 A3.2).

Disparo pelo padrão do repositório: Celery quando disponível e
alcancável, ``BackgroundTasks`` do FastAPI como caminho padrão.
``executar_rescan_task`` mantém a sessão, o batch e a auditoria em um
único ponto; a rota apenas aceita e retorna o ``batch_id``.
"""
import logging
import os
from pathlib import Path

from app.services import document_rescan_service
from app.services.document_rescan_service import RescanResultado

logger = logging.getLogger("ejc.tasks.rescan")


def agendar_rescan(
    batch_id: str,
    background_tasks=None,
    settings=None,
) -> str:
    """Agenda ``executar_rescan_task``. Retorna o mecanismo usado
    (``celery`` | ``background``)."""
    from app.core.config import get_settings

    cfg = settings or get_settings()
    if cfg.CELERY_ENABLED and _redis_alcancavel(cfg.REDIS_URL):
        try:
            indexador = _obter_task_celery()
            indexador.delay(batch_id)
            return "celery"
        except Exception as excecao:  # nunca derruba a aceitação do lote
            logger.warning(
                "[rescan] enfileirar no Celery falhou (%s: %s) — "
                "caindo para BackgroundTasks",
                type(excecao).__name__, str(excecao)[:200],
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


def _obter_task_celery():
    try:
        from app.tasks.rag_tasks import indexar_documento_task
        return indexar_documento_task
    except Exception:
        raise RuntimeError("task Celery indisponível")


async def executar_rescan_task(batch_id: str) -> None:
    """Executa o rescan do batch: seleciona documentos vigentes, calcula
    os SHA-256 (local ou remoto via rclone), compara com o intake e grava
    os itens + a conclusão do batch."""
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
            await db.flush()

            resultado = await document_rescan_service.executar_rescan(
                upload_root=upload_root,
                rclone_config=rclone_config,
                documentos=documentos,
                db=db,
                batch_id=batch_id,
            )
            await _concluir_batch(db, batch_id, resultado)
        except Exception as excecao:  # lote não derruba o worker
            await db.rollback()
            logger.exception(
                "[rescan] execução do batch %s falhou (%s: %s)",
                batch_id, type(excecao).__name__, str(excecao)[:200],
            )
            raise


def _configuracao_rclone(cfg) -> dict | None:
    """Retorna a configuração rclone quando os caminhos existem;
    ``None`` mantém o comportamento seguro (sem fonte remota) do serviço.
    Nenhum segredo é registrado em log."""
    config_path = getattr(cfg, "RCLONE_CONFIG_PATH", "") or ""
    work_dir = getattr(cfg, "RCLONE_WORK_DIR", "") or ""
    if not config_path or not os.path.isfile(config_path):
        return None
    if not work_dir or not os.path.isdir(work_dir):
        return None
    return {
        "config_path": Path(config_path),
        "remote": str(getattr(cfg, "RCLONE_REMOTE", "")).strip(),
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


async def _concluir_batch(
    db, batch_id: str, resultado: RescanResultado,
) -> None:
    from sqlalchemy import update

    from app.models import DocumentHashRescanBatch

    divergencias = [
        d for d in resultado.divergencias if d.get("motivo")
    ]
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
        "[rescan] batch %s concluído: processados=%s concluidos=%s "
        "erros=%s indisponiveis=%s divergencias=%s",
        batch_id,
        resultado.itens_processados,
        resultado.itens_concluidos,
        resultado.itens_erro,
        resultado.itens_nao_disponiveis,
        len(divergencias),
    )
