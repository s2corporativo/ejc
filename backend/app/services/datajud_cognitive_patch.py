# ── app/services/datajud_cognitive_patch.py ───────────────────────────────────
"""Instalação aditiva do feed cognitivo nos fluxos DataJud já existentes.

O EJC possui mais de uma entrada legítima de sincronização (botão no caso,
router de andamentos e job diário). Para não duplicar routers nem reescrever
módulos grandes, este instalador envolve as funções centrais compartilhadas no
startup. O padrão é o mesmo utilizado pelos demais patches de integração em
``event_subscribers.py``.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings

logger = logging.getLogger("ejc.datajud_cognitive_patch")
_INSTALADO = False


def _numero_limpo(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


async def _fonte_exata(numero_cnj: str, tribunal_alias: str | None = None) -> dict | None:
    """Consulta por match compatível com a API e exige igualdade pós-resposta.

    O Elasticsearch pode devolver correspondência aproximada. O EJC nunca deve
    atribuir movimentos de outro processo ao caso, portanto são examinados até
    dez hits e só é aceito ``_source.numeroProcesso`` exatamente igual.
    """
    from app.services import datajud_service as dj

    s = get_settings()
    if not s.DATAJUD_ENABLED or not s.DATAJUD_API_KEY:
        raise dj.DataJudDesabilitadoError(
            "Integração DataJud desativada ou sem chave configurada "
            "(DATAJUD_ENABLED/DATAJUD_API_KEY)."
        )
    numero = _numero_limpo(numero_cnj)
    alias = (tribunal_alias or "").strip() or dj.alias_do_numero(numero)
    if not alias:
        raise dj.TribunalNaoMapeadoError(
            "Tribunal não mapeado para consulta ao DataJud."
        )
    payload = {"query": {"match": {"numeroProcesso": numero}}, "size": 10}
    headers = {
        "Authorization": f"APIKey {s.DATAJUD_API_KEY}",
        "Content-Type": "application/json",
    }
    data = await dj._datajud_search(alias, payload, headers)
    for hit in ((data.get("hits") or {}).get("hits") or []):
        src = hit.get("_source") or {}
        if _numero_limpo(src.get("numeroProcesso")) == numero:
            return src
    return None


async def _consultar_movimentos_exatos(
    numero_cnj: str, tribunal_alias: str | None = None,
) -> list[dict[str, Any]]:
    src = await _fonte_exata(numero_cnj, tribunal_alias)
    if not src:
        return []
    movimentos: list[dict[str, Any]] = []
    for mov in src.get("movimentos") or []:
        descricao = (mov.get("nome") or "").strip()
        if not descricao:
            continue
        movimentos.append({
            "data": mov.get("dataHora") or "",
            "codigo": mov.get("codigo"),
            "descricao": descricao,
        })
    movimentos.sort(key=lambda item: item["data"])
    return movimentos


async def _consultar_processo_exato(numero_cnj: str) -> dict | None:
    src = await _fonte_exata(numero_cnj)
    if not src:
        return None
    movimentos = []
    for mov in src.get("movimentos") or []:
        descricao = (mov.get("nome") or "").strip()
        if not descricao:
            continue
        movimentos.append({
            # Compatibilidade com sincronizar_caso legado: apenas YYYY-MM-DD.
            "data": (mov.get("dataHora") or "")[:10],
            "descricao": descricao,
        })
    movimentos.sort(key=lambda item: item["data"])
    return {
        "classe": (src.get("classe") or {}).get("nome"),
        "orgao": (src.get("orgaoJulgador") or {}).get("nome"),
        "movimentos": movimentos,
    }


async def _alimentar_sem_quebrar(db, case) -> None:
    """Feed best-effort: falha cognitiva não apaga andamento já coletado."""
    try:
        from app.services.datajud_cognitive_feed import alimentar_caso
        await alimentar_caso(db, case, embutir_vetores=False)
    except Exception as exc:
        logger.warning(
            "Movimentos persistidos, mas alimentação cognitiva falhou para caso %s: %s",
            getattr(case, "numero_interno", None) or getattr(case, "id", "?"),
            f"{type(exc).__name__}: {str(exc)[:180]}",
        )


def _instalar_wrappers_datajud() -> None:
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
                "DataJud detectou %d possível(is) providência(s); nenhum prazo foi "
                "criado automaticamente (fonte informativa, HITL obrigatório).",
                len(sugestoes),
            )
        return []

    # Consulta exata + alimentação por todas as entradas existentes.
    dj.consultar_movimentos = _consultar_movimentos_exatos
    dj.consultar_processo = _consultar_processo_exato
    dj.upsert_movimentos_no_caso = upsert_com_feed
    dj.sincronizar_caso = sync_com_feed

    # Módulos importados ANTES deste instalador podem ter guardado a referência
    # antiga com ``from ... import função``. Atualizamos essas referências para
    # que o botão existente no caso e o job de clientes usem o mesmo núcleo.
    try:
        from app.routers import cases as cases_router
        cases_router._dj_sync = sync_com_feed
    except Exception as exc:  # pragma: no cover - defesa de startup
        logger.warning("Não foi possível atualizar cases._dj_sync: %s", exc)
    try:
        from app.services import datajud_sync_service as sync_clientes
        sync_clientes.consultar_movimentos = _consultar_movimentos_exatos
        sync_clientes.upsert_movimentos_no_caso = upsert_com_feed
    except Exception as exc:  # pragma: no cover - defesa de startup
        logger.warning("Não foi possível atualizar o sync DataJud de clientes: %s", exc)

    # DataJud não é fonte de termo inicial. Mantemos a heurística apenas para
    # classificar o documento cognitivo; a criação de Deadline é desativada.
    dj._detectar_prazos_criticos = detectar_sem_criar_prazo
    dj._ejc_cognitive_feed_installed = True
    logger.info("Feed cognitivo DataJud instalado nos fluxos nativos")


def _registrar_categoria_restrita() -> None:
    """Impede recuperação cruzada entre clientes na busca RAG."""
    from app.services import ai_service
    categoria = "andamento_processual"
    if categoria not in ai_service._RESTRICTED_CATS:
        ai_service._RESTRICTED_CATS.append(categoria)
    logger.info("Categoria RAG %s registrada como restrita por cliente", categoria)


def _registrar_subrouter() -> None:
    from app.routers import andamentos
    from app.routers import datajud_intelligence

    marcador = "_ejc_datajud_intelligence_router_installed"
    if getattr(andamentos.router, marcador, False):
        return
    andamentos.router.include_router(datajud_intelligence.router)
    setattr(andamentos.router, marcador, True)
    logger.info("Rotas de governança DataJud → IA registradas em /casos")


async def _job_feed_datajud() -> None:
    """Backfill incremental horário; os órfãos são vetorizados no job das :20."""
    try:
        from app.core.database import AsyncSessionLocal
        from app.services.datajud_cognitive_feed import alimentar_lote

        async with AsyncSessionLocal() as db:
            resultado = await alimentar_lote(db, limite=100, embutir_vetores=False)
        logger.info("Job feed cognitivo DataJud: %s", resultado)
    except Exception as exc:  # nunca derruba o scheduler
        logger.error(
            "Job feed cognitivo DataJud falhou: %s",
            f"{type(exc).__name__}: {str(exc)[:200]}",
        )


def _registrar_job() -> None:
    """Agenda às :10; o auto-reembed nativo roda às :20."""
    from app.services import scheduler

    s = scheduler.get_scheduler()
    s.add_job(
        _job_feed_datajud,
        CronTrigger(minute=10),
        id="datajud_cognitive_feed",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )


def instalar() -> None:
    global _INSTALADO
    if _INSTALADO:
        return
    _instalar_wrappers_datajud()
    _registrar_categoria_restrita()
    _registrar_subrouter()
    _registrar_job()
    _INSTALADO = True
