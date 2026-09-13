"""Coleta de processos públicos no DataJud para a jurimetria dos tribunais.

Reusa ``datajud_service.buscar_lote_paginado`` (search_after sobre
@timestamp, contrato já verificado pelo módulo de saneamento). Regras:

  • opt-in duplo: ``JURIMETRIA_TRIBUNAIS_ENABLED`` (esta funcionalidade) E
    ``DATAJUD_ENABLED``/``DATAJUD_API_KEY`` (a integração). Sem qualquer um,
    resposta controlada — nunca 500, nunca I/O externo;
  • limite de processos por consulta (``JURIMETRIA_TRIBUNAIS_MAX_PROCESSOS``)
    — a API Pública é rate-limited e o ``n`` real vai na resposta;
  • cache TTL em memória por consulta (premissa de worker único do EJC);
    erro nunca entra no cache; kill-switch prevalece sobre cache;
  • TJMG continua sendo o recorte principal (Betim, Contagem e BH). TRT3 é
    coletado como benchmark trabalhista de MG e JEC/Turmas Recursais são
    derivados do próprio lote TJMG, sem uma segunda chamada e sem duplicação.

Campos do documento DataJud usados: ``numeroProcesso``, ``grau``, ``classe``,
``assuntos``, ``orgaoJulgador{codigo,nome}``, ``dataAjuizamento``,
``movimentos[]{codigo,nome,dataHora}`` — a mesma forma que as fixtures de
``tests/test_saneamento_*`` e o contrato documentado em ``datajud_service``.
"""
from __future__ import annotations

import json
import time
from typing import Any

from app.core.config import get_settings
from app.integrations.feature_flags import require_enabled
from app.services.datajud_service import (
    DataJudDesabilitadoError,
    buscar_lote_paginado,
)

ALIAS_TJMG = "api_publica_tjmg"
ALIAS_TRT3 = "api_publica_trt3"

# Recorte inicial decidido pelo titular (Issue #1527): Betim, Contagem e Belo
# Horizonte. Códigos IBGE verificados um a um na API de localidades do IBGE
# (servicodados.ibge.gov.br/api/v1/localidades/municipios/{id}) em 05/09/2026:
# Belo Horizonte 3106200, Contagem 3118601, Betim 3106705 — todos /MG.
# O filtro principal é o NOME do órgão julgador (contrato confirmado do DataJud:
# ``orgaoJulgador.nome``); o código IBGE é cláusula alternativa para índices
# que o preencham.
MUNICIPIOS: dict[str, dict[str, Any]] = {
    "belo_horizonte": {"nome": "Belo Horizonte", "ibge": 3106200},
    "contagem": {"nome": "Contagem", "ibge": 3118601},
    "betim": {"nome": "Betim", "ibge": 3106705},
}
MUNICIPIOS_PADRAO = ("betim", "contagem", "belo_horizonte")

_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_MAX = 64


def municipios_validos(chaves: list[str] | None) -> list[str]:
    """Normaliza a lista pedida; ignora desconhecidos; vazio → recorte padrão."""
    pedidos = [
        str(c).strip().lower().replace(" ", "_")
        for c in (chaves or [])
        if c
    ]
    validos = [c for c in pedidos if c in MUNICIPIOS]
    return validos or list(MUNICIPIOS_PADRAO)


def _filtros_comuns(
    *,
    grau: str | None = None,
    classe: int | None = None,
    assunto: int | None = None,
    desde: str | None = None,
    ate: str | None = None,
) -> list[dict]:
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
    """Query Elasticsearch DSL para o índice do TJMG.

    ``grau`` None traz 1º e 2º grau juntos: a taxa de reforma precisa dos dois
    registros do mesmo ``numeroProcesso``.
    """
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
    """Query do TRT3/MG sem inventar filtro geográfico inexistente.

    O próprio índice ``api_publica_trt3`` já delimita a 3ª Região. Aplicamos
    somente filtros TPU/data informados pelo usuário. Sem filtro, ``match_all``
    preserva a semântica de benchmark regional completo.
    """
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
    """Classifica recorte JEC/Turma Recursal apenas por metadado público.

    Não infere a partir do conteúdo da decisão. Usa ``grau`` quando a fonte o
    identifica como JE/JEC e, como fallback, o nome do órgão julgador.
    """
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
    chave = _chave_cache(query, maximo, alias)
    agora = time.time()

    if ttl > 0:
        cacheado = _CACHE.get(chave)
        if cacheado and cacheado[0] > agora:
            docs = cacheado[1]
            return docs, {
                "cache": True,
                "coletado_em": None,
                "maximo": maximo,
                "n_documentos": len(docs),
                "alias": alias,
            }

    hits = await buscar_lote_paginado(
        alias,
        query,
        _headers(),
        tamanho_pagina=min(500, maximo),
        maximo=maximo,
    )
    docs = [h.get("_source") or {} for h in hits if isinstance(h, dict)]

    if ttl > 0:
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[chave] = (agora + ttl, docs)

    return docs, {
        "cache": False,
        "coletado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(agora)),
        "maximo": maximo,
        "n_documentos": len(docs),
        "truncado": len(docs) >= maximo,
        "alias": alias,
    }


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
