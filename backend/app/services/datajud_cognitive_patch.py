# ── app/services/datajud_cognitive_patch.py ───────────────────────────────────
"""Integra DataJud ao RAG nativo preservando os fluxos existentes.

A neutralização de criação automática de prazos é barreira crítica de segurança.
Feed cognitivo, categoria RAG e scheduler são complementares e podem degradar sem
reativar o caminho legado de materialização automática de Deadline.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings

logger = logging.getLogger("ejc.datajud.cognitive_patch")
_INSTALADO = False


async def _nao_criar_deadline_datajud(*_args, **_kwargs) -> None:
    """Defesa em profundidade: DataJud nunca persiste Deadline automaticamente."""
    logger.warning(
        "Criação automática de Deadline por DataJud bloqueada: "
        "exige revisão humana de publicação, termo inicial, regime e calendário."
    )
    return re.sub(r"\D", "", valor or "")


async def _fonte_exata(numero_cnj: str, tribunal_alias: str | None = None) -> dict | None:
    from app.services import datajud_service as dj

    settings = get_settings()
    if not settings.DATAJUD_ENABLED or not settings.DATAJUD_API_KEY:
        raise dj.DataJudDesabilitadoError(
            "Integração DataJud desativada ou sem chave configurada."
        )
    numero = _numero_limpo(numero_cnj)
    alias = (tribunal_alias or "").strip() or dj.alias_do_numero(numero)
    if not alias:
        raise dj.TribunalNaoMapeadoError("Tribunal não mapeado para o DataJud")

    payload = {"query": {"match": {"numeroProcesso": numero}}, "size": 10}
    headers = {
        "Authorization": f"APIKey {settings.DATAJUD_API_KEY}",
        "Content-Type": "application/json",
    }
    data = await dj._datajud_search(alias, payload, headers)
    for hit in ((data.get("hits") or {}).get("hits") or []):
        source = hit.get("_source") or {}
        if _numero_limpo(source.get("numeroProcesso")) == numero:
            return source
    return None


async def _consultar_movimentos_exatos(
    numero_cnj: str,
    tribunal_alias: str | None = None,
) -> list[dict[str, Any]]:
    source = await _fonte_exata(numero_cnj, tribunal_alias)
    if not source:
        return []
    movimentos: list[dict[str, Any]] = []
    for movimento in source.get("movimentos") or []:
        descricao = (movimento.get("nome") or "").strip()
        if descricao:
            movimentos.append({
                "data": movimento.get("dataHora") or "",
                "codigo": movimento.get("codigo"),
                "descricao": descricao,
            })
    movimentos.sort(key=lambda item: item["data"])
    return movimentos


async def _consultar_processo_exato(numero_cnj: str) -> dict | None:
    source = await _fonte_exata(numero_cnj)
    if not source:
        return None
    movimentos = [
        {
            "data": (movimento.get("dataHora") or "")[:10],
            "descricao": (movimento.get("nome") or "").strip(),
        }
        for movimento in source.get("movimentos") or []
        if (movimento.get("nome") or "").strip()
    ]
    movimentos.sort(key=lambda item: item["data"])
    return {
        "classe": (source.get("classe") or {}).get("nome"),
        "orgao": (source.get("orgaoJulgador") or {}).get("nome"),
        "movimentos": movimentos,
    }


async def _alimentar_sem_quebrar(db, case) -> None:
    try:
        from app.services.datajud_cognitive_feed import alimentar_caso
        async with db.begin_nested():
            await alimentar_caso(db, case, embutir_vetores=False)
    except Exception as exc:
        logger.warning(
            "Movimentação preservada, mas feed cognitivo falhou para %s: %s",
            getattr(case, "numero_interno", None) or getattr(case, "id", "?"),
            f"{type(exc).__name__}: {str(exc)[:180]}",
        )


def _instalar_wrappers() -> None:
    from app.services import datajud_service as dj

    if getattr(dj, "_ejc_cognitive_feed_installed", False):
        return
    original_upsert = dj.upsert_movimentos_no_caso
    original_sync = dj.sincronizar_caso
    original_detectar = dj._detectar_prazos_criticos

    async def upsert_com_feed(db, case, movimentos):
        resultado = await original_upsert(db, case, movimentos)
        await _alimentar_sem_quebrar(db, case)
        return resultado

    async def sync_com_feed(db, case):
        resultado = await original_sync(db, case)
        await _alimentar_sem_quebrar(db, case)
        return resultado

    def detectar_sem_criar_prazo(descricao, data_evento):
        sugestoes = original_detectar(descricao, data_evento)
        if sugestoes:
            logger.info(
                "DataJud detectou possível providência, mas nenhum prazo foi criado automaticamente."
            )
        return []

    async def sincronizar_prazos_bloqueado(*args, **kwargs):
        del args, kwargs
        return {
            "criados": 0,
            "ignorados": 0,
            "erros": 0,
            "bloqueado": True,
            "motivo": "Prazos DataJud exigem cálculo canônico e confirmação humana.",
        }

    dj._criar_deadline_automatico = _nao_criar_deadline_datajud
    dj._detectar_prazos_criticos = detectar_sem_criar_prazo
    dj.sincronizar_prazos_datajud = sincronizar_prazos_bloqueado

    dj.consultar_movimentos = _consultar_movimentos_exatos
    dj.consultar_processo = _consultar_processo_exato
    dj.upsert_movimentos_no_caso = upsert_com_feed
    dj.sincronizar_caso = sync_com_feed

    try:
        from app.routers import cases as cases_router
        cases_router._dj_sync = sync_com_feed
    except Exception as exc:
        logger.warning("Não foi possível atualizar cases._dj_sync: %s", exc)
    try:
        from app.services import datajud_sync_service as sync_clientes
        sync_clientes.consultar_movimentos = _consultar_movimentos_exatos
        sync_clientes.upsert_movimentos_no_caso = upsert_com_feed
    except Exception as exc:
        logger.warning("Não foi possível atualizar o sync DataJud de clientes: %s", exc)

    dj._ejc_cognitive_feed_installed = True


def _registrar_categoria_restrita() -> None:
    from app.services import ai_service
    if "andamento_processual" not in ai_service._RESTRICTED_CATS:
        ai_service._RESTRICTED_CATS.append("andamento_processual")


async def _job_feed_datajud() -> None:
    try:
        from app.core.database import AsyncSessionLocal
        from app.services.datajud_cognitive_feed import alimentar_lote
        async with AsyncSessionLocal() as db:
            resultado = await alimentar_lote(db, limite=100)
        logger.info("Job feed DataJud: %s", resultado)
    except Exception as exc:
        logger.error("Job feed DataJud falhou: %s", type(exc).__name__)


def _registrar_job() -> None:
    from app.services import scheduler

    scheduler.get_scheduler().add_job(
        _job_feed_datajud,
        CronTrigger(hour=3, minute=10),
        id="datajud_cognitive_feed",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )


def instalar() -> None:
    global _INSTALADO
    if _INSTALADO:
        return

    # Segurança jurídica: se estes wrappers falharem, a instalação falha e o
    # caller deve impedir boot. Não marcar _INSTALADO antes desta etapa.
    _instalar_wrappers()

    # Recursos cognitivos são complementares. Falhas aqui não podem remover a
    # barreira de prazos nem transformar indisponibilidade externa em outage.
    try:
        _registrar_categoria_restrita()
    except Exception as exc:
        logger.error("Categoria RAG DataJud indisponível: %s", type(exc).__name__)
    try:
        _registrar_job()
    except Exception as exc:
        logger.error("Scheduler do feed DataJud indisponível: %s", type(exc).__name__)

    _INSTALADO = True
    logger.info("Barreira crítica DataJud instalada; feed cognitivo ativado quando disponível")
