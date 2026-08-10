# ── app/services/datajud_cognitive_patch.py ───────────────────────────────────
"""Integra DataJud ao RAG nativo preservando os fluxos existentes.

A integração de movimentações é somente informacional/cognitiva. Enquanto o
motor auditável por regime da Issue #968 não estiver integrado, nenhum caminho
DataJud pode materializar ``Deadline`` ou calcular vencimento a partir da data
do movimento. Isso evita depender da ordem de instalação de um único wrapper
para preservar o HITL jurídico.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings

logger = logging.getLogger("ejc.datajud.cognitive_patch")
_INSTALADO = False
PRAZO_DATAJUD_MOTIVO_BLOQUEIO = (
    "calculo_automatico_bloqueado_ate_motor_auditavel_por_regime"
)


def _numero_limpo(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


async def _fonte_exata(
    numero_cnj: str,
    tribunal_alias: str | None = None,
) -> dict | None:
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
            movimentos.append(
                {
                    "data": movimento.get("dataHora") or "",
                    "codigo": movimento.get("codigo"),
                    "descricao": descricao,
                }
            )
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


async def _criar_deadline_bloqueado(*_args, **_kwargs) -> None:
    """Fail-safe: DataJud não cria prazo fatal sem termo/regime auditáveis."""
    return None


async def _sincronizar_prazos_bloqueado(
    _caso_id: str,
    _numero_cnj: str,
    _db,
) -> dict[str, Any]:
    """Mantém contrato do endpoint sem produzir ``Deadline``.

    A sincronização de movimentos continua ativa. O endpoint de prazos informa
    explicitamente que a revisão humana é necessária até a conclusão da #968.
    """
    return {
        "criados": 0,
        "encontrados": 0,
        "erro": None,
        "revisao_necessaria": True,
        "motivo": PRAZO_DATAJUD_MOTIVO_BLOQUEIO,
    }


def _instalar_wrappers() -> None:
    from app.services import datajud_service as dj

    if getattr(dj, "_ejc_cognitive_feed_installed", False):
        return
    original_upsert = dj.upsert_movimentos_no_caso
    original_sync = dj.sincronizar_caso

    async def upsert_com_feed(db, case, movimentos):
        resultado = await original_upsert(db, case, movimentos)
        await _alimentar_sem_quebrar(db, case)
        return resultado

    async def sync_com_feed(db, case):
        resultado = await original_sync(db, case)
        await _alimentar_sem_quebrar(db, case)
        return resultado

    def detectar_sem_criar_prazo(_descricao, _data_evento):
        # Não executa a heurística legada nem para "sugerir": ela usa a data do
        # movimento como base e não conhece regime/termo inicial. O movimento
        # segue disponível no feed cognitivo para revisão do advogado.
        return []

    dj.consultar_movimentos = _consultar_movimentos_exatos
    dj.consultar_processo = _consultar_processo_exato
    dj.upsert_movimentos_no_caso = upsert_com_feed
    dj.sincronizar_caso = sync_com_feed
    dj._detectar_prazos_criticos = detectar_sem_criar_prazo
    dj._criar_deadline_automatico = _criar_deadline_bloqueado
    dj.sincronizar_prazos_datajud = _sincronizar_prazos_bloqueado

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
    _instalar_wrappers()
    _registrar_categoria_restrita()
    # Onda 3 §4.1: o router datajud_intelligence é registrado explicitamente
    # em app/main.py (antes era anexado a andamentos.router por patch daqui).
    _registrar_job()
    _INSTALADO = True
    logger.info("Feed cognitivo DataJud instalado")
