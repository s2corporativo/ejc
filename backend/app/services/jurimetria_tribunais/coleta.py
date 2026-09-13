"""Coleta de processos públicos no DataJud para a jurimetria dos tribunais.

Reusa ``datajud_service.buscar_lote_paginado``. Regras:

  • opt-in duplo: ``JURIMETRIA_TRIBUNAIS_ENABLED`` E
    ``DATAJUD_ENABLED``/``DATAJUD_API_KEY``;
  • limite de processos por consulta e indicação explícita de truncamento;
  • cache curto apenas para lotes pequenos, com teto de entradas/documentos;
    o kill-switch/credencial é verificado ANTES de servir qualquer cache;
  • datas são validadas como calendário ISO antes de qualquer chamada externa;
  • TJMG é o recorte principal (Betim, Contagem e BH). TRT3 é benchmark
    trabalhista de MG; JEC/Turmas Recursais são derivados do lote TJMG sem
    segunda chamada nem duplicação de dados.
"""
from __future__ import annotations

import json
import time
from datetime import date
from typing import Any

from fastapi import HTTPException

from app.core.config import get_settings
from app.integrations.feature_flags import require_enabled
from app.services.datajud_service import (
    DataJudDesabilitadoError,
    buscar_lote_paginado,
)

ALIAS_TJMG = "api_publica_tjmg"
ALIAS_TRT3 = "api_publica_trt3"

MUNICIPIOS: dict[str, dict[str, Any]] = {
    "belo_horizonte": {"nome": "Belo Horizonte", "ibge": 3106200},
    "contagem": {"nome": "Contagem", "ibge": 3118601},
    "betim": {"nome": "Betim", "ibge": 3106705},
}
MUNICIPIOS_PADRAO = ("betim", "contagem", "belo_horizonte")

# Nunca retenha em memória os lotes grandes usados para estatística. O cache é
# somente uma otimização para recortes já estreitos. Assim o teto absoluto é
# 4 × 500 documentos, e não 64 × 2.000 históricos processuais completos.
_CACHE: dict[str, tuple[float, list[dict], dict[str, Any]]] = {}
_CACHE_MAX = 4
_CACHE_DOCS_MAX = 500


def municipios_validos(chaves: list[str] | None) -> list[str]:
    """Normaliza a lista pedida; ignora desconhecidos; vazio → recorte padrão."""
    pedidos = [
        str(c).strip().lower().replace(" ", "_")
        for c in (chaves or [])
        if c
    ]
    validos = [c for c in pedidos if c in MUNICIPIOS]
    return validos or list(MUNICIPIOS_PADRAO)


def _data_iso(valor: str | None, campo: str) -> date | None:
    if not valor:
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"{campo} deve ser uma data ISO válida (AAAA-MM-DD).",
        ) from None


def _filtros_comuns(
    *,
    grau: str | None = None,
    classe: int | None = None,
    assunto: int | None = None,
    desde: str | None = None,
    ate: str | None = None,
) -> list[dict]:
    data_desde = _data_iso(desde, "desde")
    data_ate = _data_iso(ate, "ate")
    if data_desde and data_ate and data_desde > data_ate:
        raise HTTPException(
            status_code=422,
            detail="desde não pode ser posterior a ate.",
        )

    filtro: list[dict] = []
    if grau:
        filtro.append({"term": {"grau": grau}})
    if classe:
        filtro.append({"term": {"classe.codigo": int(classe)}})
    if assunto:
        filtro.append({"term": {"assuntos.codigo": int(assunto)}})
    if desde or ate:
        faixa: dict[str, str] = {}
        if desde:
            faixa["gte"] = desde
        if ate:
            faixa["lte"] = ate
        filtro.append({"range": {"dataAjuizamento": faixa}})
    return filtro


def montar_query(
    municipios: list[str],
    *,
    grau: str | None = None,
    classe: int | None = None,
    assunto: int | None = None,
    desde: str | None = None,
    ate: str | None = None,
) -> dict:
    """Query Elasticsearch DSL para o índice do TJMG."""
    should: list[dict] = []
    for chave in municipios:
        m = MUNICIPIOS[chave]
        should.append({"match_phrase": {"orgaoJulgador.nome": m["nome"]}})
        should.append({"term": {"orgaoJulgador.codigoMunicipioIBGE": m["ibge"]}})
    return {
        "query": {
            "bool": {
                "should": should,
                "minimum_should_match": 1,
                "filter": _filtros_comuns(
                    grau=grau,
                    classe=classe,
                    assunto=assunto,
                    desde=desde,
                    ate=ate,
                ),
            }
        }
    }


def montar_query_trt3(
    *,
    classe: int | None = None,
    assunto: int | None = None,
    desde: str | None = None,
    ate: str | None = None,
) -> dict:
    """Query do TRT3/MG; o próprio índice delimita a 3ª Região."""
    filtros = _filtros_comuns(
        classe=classe,
        assunto=assunto,
        desde=desde,
        ate=ate,
    )
    if not filtros:
        return {"query": {"match_all": {}}}
    return {"query": {"bool": {"filter": filtros}}}


def eh_jec(doc: dict) -> bool:
    """Classifica JEC/Turma Recursal somente por metadado público."""
    grau = str(doc.get("grau") or "").strip().upper()
    if grau in {"JE", "JEC"}:
        return True
    orgao = str((doc.get("orgaoJulgador") or {}).get("nome") or "").casefold()
    return "juizado especial" in orgao or "turma recursal" in orgao


def filtrar_jec(docs: list[dict]) -> list[dict]:
    """Subconjunto idempotente do lote TJMG; não faz I/O nem duplica dados."""
    return [doc for doc in docs if eh_jec(doc)]


def _headers() -> dict[str, str]:
    s = get_settings()
    if not s.DATAJUD_ENABLED or not s.DATAJUD_API_KEY:
        raise DataJudDesabilitadoError(
            "Integração DataJud desativada ou sem chave configurada "
            "(DATAJUD_ENABLED/DATAJUD_API_KEY)."
        )
    return {
        "Authorization": f"APIKey {s.DATAJUD_API_KEY}",
        "Content-Type": "application/json",
    }


def _chave_cache(query: dict, maximo: int, alias: str = ALIAS_TJMG) -> str:
    return json.dumps(
        {"alias": alias, "q": query, "max": maximo},
        sort_keys=True,
        ensure_ascii=False,
    )


def limpar_cache() -> None:
    _CACHE.clear()


async def _coletar_alias(
    alias: str,
    query: dict,
    *,
    maximo: int,
    ttl: int,
) -> tuple[list[dict], dict[str, Any]]:
    # Segurança: revogação/kill-switch prevalece até sobre resposta cacheada.
    headers = _headers()
    chave = _chave_cache(query, maximo, alias)
    agora = time.time()

    if ttl > 0:
        cacheado = _CACHE.get(chave)
        if cacheado and cacheado[0] > agora:
            docs = cacheado[1]
            meta = dict(cacheado[2])
            meta["cache"] = True
            return docs, meta

    hits = await buscar_lote_paginado(
        alias,
        query,
        headers,
        tamanho_pagina=min(500, maximo),
        maximo=maximo,
    )
    docs = [h.get("_source") or {} for h in hits if isinstance(h, dict)]
    meta = {
        "cache": False,
        "coletado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(agora)),
        "maximo": maximo,
        "n_documentos": len(docs),
        "truncado": len(docs) >= maximo,
        "alias": alias,
    }

    # Lote grande nunca fica residente: acima de 500 docs, o custo de memória
    # supera o ganho de evitar nova consulta. Recortes pequenos mantêm TTL.
    if ttl > 0 and len(docs) <= _CACHE_DOCS_MAX:
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[chave] = (agora + ttl, docs, dict(meta))

    return docs, meta


async def coletar(
    municipios: list[str],
    *,
    classe: int | None = None,
    assunto: int | None = None,
    desde: str | None = None,
    ate: str | None = None,
) -> tuple[list[dict], dict[str, Any]]:
    """Devolve documentos TJMG ``_source`` + metadados da coleta."""
    require_enabled("jurimetria_tribunais", "Jurimetria dos tribunais (DataJud)")
    s = get_settings()
    maximo = max(
        1,
        int(getattr(s, "JURIMETRIA_TRIBUNAIS_MAX_PROCESSOS", 2000) or 2000),
    )
    ttl = int(
        getattr(s, "JURIMETRIA_TRIBUNAIS_CACHE_TTL_SEGUNDOS", 3600) or 0
    )
    query = montar_query(
        municipios,
        classe=classe,
        assunto=assunto,
        desde=desde,
        ate=ate,
    )
    return await _coletar_alias(ALIAS_TJMG, query, maximo=maximo, ttl=ttl)


async def coletar_trt3(
    *,
    classe: int | None = None,
    assunto: int | None = None,
    desde: str | None = None,
    ate: str | None = None,
) -> tuple[list[dict], dict[str, Any]]:
    """Benchmark trabalhista de MG via índice público específico do TRT3."""
    require_enabled("jurimetria_tribunais", "Jurimetria dos tribunais (DataJud)")
    s = get_settings()
    maximo = max(
        1,
        int(getattr(s, "JURIMETRIA_TRIBUNAIS_MAX_PROCESSOS", 2000) or 2000),
    )
    ttl = int(
        getattr(s, "JURIMETRIA_TRIBUNAIS_CACHE_TTL_SEGUNDOS", 3600) or 0
    )
    query = montar_query_trt3(
        classe=classe,
        assunto=assunto,
        desde=desde,
        ate=ate,
    )
    return await _coletar_alias(ALIAS_TRT3, query, maximo=maximo, ttl=ttl)
