# ── app/services/datajud_service.py ──────────────────────────────────────────
# Consulta de movimentações processuais via API Pública do DataJud/CNJ.
#
# CONTRATO DA API (verificado em 2026-07 contra a documentação oficial):
#   • Host: https://api-publica.datajud.cnj.jus.br
#   • Endpoint por tribunal: POST /{alias}/_search (ex.: /api_publica_tjmg/_search)
#   • Auth: header "Authorization: APIKey <chave pública divulgada pelo CNJ>"
#     — a chave é PÚBLICA e de uso geral, publicada pelo DPJ/CNJ na wiki.
#   • Corpo: query Elasticsearch DSL, ex.:
#       {"query": {"match": {"numeroProcesso": "<20 dígitos, sem máscara>"}}}
#   • Resposta: formato Elasticsearch — hits.hits[]._source com numeroProcesso,
#     tribunal, grau, classe{codigo,nome}, orgaoJulgador{nome} e
#     movimentos[]{codigo, nome, dataHora} (Tabelas Processuais Unificadas).
# Fontes: https://datajud-wiki.cnj.jus.br/api-publica/ (Acesso e Exemplos),
#         https://www.cnj.jus.br/sistemas/datajud/api-publica/ e o tutorial
#         oficial (cnj.jus.br/wp-content/uploads/2023/05/tutorial-api-publica-
#         datajud-beta.pdf). Dados do DataJud são metadados PÚBLICOS; ainda
#         assim, NUNCA logar corpo de resposta nem a API key (LGPD/higiene).
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings
from app.models.case import Case, CaseMovimento

logger = logging.getLogger("ejc.datajud")

# Compat: consumidores externos (ex.: crawler_precedentes) leem flags via
# `datajud_service.settings` — manter o alias de módulo apontando para o
# singleton cacheado. Internamente as funções usam get_settings() direto.
settings = get_settings()

# Fallback histórico; a fonte de verdade é get_settings().DATAJUD_BASE_URL.
BASE = "https://api-publica.datajud.cnj.jus.br"


class DataJudDesabilitadoError(RuntimeError):
    """Integração desligada (DATAJUD_ENABLED=false) ou sem chave configurada."""


class TribunalNaoMapeadoError(ValueError):
    """Número CNJ válido, mas o tribunal (segmento J.TR) não tem alias mapeado."""


def _erro_datajud_transitorio(exc: BaseException) -> bool:
    """Retry apenas quando repetir pode resolver: transporte, 429 ou 5xx.

    Erros 4xx de contrato/autenticação não são repetidos: isso evita multiplicar
    carga e esconder configuração inválida atrás de três tentativas inúteis.
    """
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        status = exc.response.status_code
        return status == 429 or status >= 500
    return False


# ── Cache TTL em memória da consulta processual (premissa de worker único) ───
# Chave: número CNJ (20 dígitos). Valor: (monotônico da gravação, resultado).
# Só resultado de SUCESSO entra (inclusive None = "não localizado", que é
# resposta válida do CNJ); erro nunca é cacheado. TTL 0 desliga o cache.
# NUNCA serve cache com a integração desligada — o kill-switch prevalece.
_CACHE_CONSULTA: dict[str, tuple[float, dict | None]] = {}
_CACHE_MAX_ENTRADAS = 512
_CACHE_MISS = object()


def _cache_ttl_segundos() -> int:
    try:
        return int(getattr(get_settings(), "DATAJUD_CACHE_TTL_SEGUNDOS", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _cache_obter(numero_limpo: str):
    """Resultado cacheado ainda válido, ou _CACHE_MISS."""
    ttl = _cache_ttl_segundos()
    if ttl <= 0:
        return _CACHE_MISS
    entrada = _CACHE_CONSULTA.get(numero_limpo)
    if entrada is None:
        return _CACHE_MISS
    gravado_em, valor = entrada
    if time.monotonic() - gravado_em > ttl:
        _CACHE_CONSULTA.pop(numero_limpo, None)
        return _CACHE_MISS
    return valor


def _cache_gravar(numero_limpo: str, valor: dict | None) -> None:
    if _cache_ttl_segundos() <= 0:
        return
    if len(_CACHE_CONSULTA) >= _CACHE_MAX_ENTRADAS:
        # Poda simples: expirados primeiro; se nada expirou, descarta o mais antigo.
        agora = time.monotonic()
        ttl = _cache_ttl_segundos()
        for k in [k for k, (t, _) in _CACHE_CONSULTA.items() if agora - t > ttl]:
            _CACHE_CONSULTA.pop(k, None)
        if len(_CACHE_CONSULTA) >= _CACHE_MAX_ENTRADAS:
            mais_antigo = min(_CACHE_CONSULTA, key=lambda k: _CACHE_CONSULTA[k][0])
            _CACHE_CONSULTA.pop(mais_antigo, None)
    _CACHE_CONSULTA[numero_limpo] = (time.monotonic(), valor)


def _cache_limpar() -> None:
    """Uso em testes (e eventual troca de chave/config em runtime)."""
    _CACHE_CONSULTA.clear()


# ── Limitador de requisições (premissa de worker único — mesma família do
# cache acima). Token bucket ingênuo: guarda só o instante da última
# concessão e espera o intervalo mínimo antes de liberar a próxima. Não
# distribui entre workers — se o EJC ganhar múltiplos workers, isto precisa
# virar Redis (mesma nota que já vale para o cache de consulta).
_ULTIMA_CONCESSAO: float = 0.0
_RATE_LOCK = asyncio.Lock()


def _rate_limit_rps() -> float:
    try:
        valor = float(getattr(get_settings(), "DATAJUD_RATE_LIMIT_RPS", 5.0) or 0.0)
    except (TypeError, ValueError):
        valor = 5.0
    return valor if valor > 0 else 0.0


async def _aguardar_rate_limit() -> None:
    """Espaça as chamadas ao DataJud pelo limite configurado (req/s).

    Desliga sozinho se DATAJUD_RATE_LIMIT_RPS <= 0 (sem limite). Cada
    tentativa de retry passa por aqui de novo — 429/5xx já reduz o ritmo via
    backoff exponencial do @retry; isto cobre o caso feliz (todas as
    tentativas bem-sucedidas de uma varredura em lote não estourando o
    limite desconhecido do CNJ).
    """
    global _ULTIMA_CONCESSAO
    intervalo = 1.0 / _rate_limit_rps() if _rate_limit_rps() else 0.0
    if intervalo <= 0:
        return
    async with asyncio.timeout(30):
        async with _RATE_LOCK:
            agora = time.monotonic()
            espera = (_ULTIMA_CONCESSAO + intervalo) - agora
            if espera > 0:
                await asyncio.sleep(espera)
            _ULTIMA_CONCESSAO = time.monotonic()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    retry=retry_if_exception(_erro_datajud_transitorio),
    reraise=True,
)
async def _datajud_search(alias: str, payload: dict, headers: dict) -> dict:
    await _aguardar_rate_limit()
    s = get_settings()
    cache = None
    cache_key = "datajud:consulta:" + hashlib.sha256(
        json.dumps({"alias": alias, "payload": payload}, sort_keys=True, default=str).encode()
    ).hexdigest()
    try:
        import redis.asyncio as aioredis
        if s.REDIS_URL and _cache_ttl_segundos() > 0:
            cache = aioredis.from_url(
                s.REDIS_URL, socket_connect_timeout=0.5, socket_timeout=0.5,
                decode_responses=True,
            )
            valor = await cache.get(cache_key)
            if valor:
                return json.loads(valor)
    except Exception:
        cache = None
    finally:
        if cache is not None:
            try:
                await cache.aclose()
            except Exception:
                pass
    base = (s.DATAJUD_BASE_URL or BASE).rstrip("/")
    async with httpx.AsyncClient(timeout=s.DATAJUD_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{base}/{alias}/_search", json=payload, headers=headers
        )
        response.raise_for_status()
        resultado = response.json()
    try:
        import redis.asyncio as aioredis
        if s.REDIS_URL and _cache_ttl_segundos() > 0:
            cache = aioredis.from_url(
                s.REDIS_URL, socket_connect_timeout=0.5, socket_timeout=0.5,
                decode_responses=True,
            )
            await cache.set(cache_key, json.dumps(resultado, default=str), ex=_cache_ttl_segundos())
    except Exception:
        pass
    finally:
        if cache is not None:
            try:
                await cache.aclose()
            except Exception:
                pass
    return resultado


async def buscar_lote_paginado(
    alias: str,
    query: dict,
    headers: dict,
    *,
    tamanho_pagina: int = 10,
    maximo: int = 10_000,
) -> list[dict]:
    """Varre um índice do DataJud com paginação `search_after` sobre `@timestamp`.

    Contrato verificado: `size` padrão 10, máximo 10.000; a API Pública não
    aceita `from`/offset para paginação profunda, só `search_after`. Usada
    pelo módulo de saneamento (não pela consulta avulsa por número, que
    continua em `consultar_processo`/`consultar_movimentos`). Levanta o mesmo
    ``httpx.*`` de ``_datajud_search`` após os retries; não engole erro.
    """
    tamanho_pagina = max(1, min(tamanho_pagina, 10_000))
    payload: dict = {
        **query,
        "size": tamanho_pagina,
        "sort": [{"@timestamp": {"order": "asc"}}],
    }
    coletados: list[dict] = []
    search_after = None
    while len(coletados) < maximo:
        # Última página pode pedir menos que tamanho_pagina: evita puxar (e
        # descartar) itens de mais de uma API externa rate-limited (achado
        # de revisão — antes sempre pedia a página cheia e truncava no fim).
        restante = maximo - len(coletados)
        pagina = dict(payload, size=min(tamanho_pagina, restante))
        if search_after is not None:
            pagina["search_after"] = search_after
        data = await _datajud_search(alias, pagina, headers)
        hits = (data.get("hits") or {}).get("hits") or []
        if not hits:
            break
        coletados.extend(hits)
        if len(hits) < pagina["size"]:
            break
        search_after = hits[-1].get("sort")
        if not search_after:
            break
    return coletados[:maximo]


async def buscar_documento_saneamento(
    numero_cnj: str, tribunal_alias: str | None = None,
) -> dict | None:
    """Documento completo (`_source`) para o painel de reconciliação.

    Diferente de ``consultar_processo`` (que já normaliza para
    classe/orgao/movimentos, uso do card de andamentos), devolve o `_source`
    cru — o módulo de saneamento precisa de campos que aquele normalizador
    descarta: ``dataAjuizamento``, ``tribunal``, ``grau``, ``formato``,
    ``sistema`` e sobretudo ``nivelSigilo`` (tratamento restrito).
    """
    s = get_settings()
    if not s.DATAJUD_ENABLED or not s.DATAJUD_API_KEY:
        raise DataJudDesabilitadoError(
            "Integração DataJud desativada ou sem chave configurada "
            "(DATAJUD_ENABLED/DATAJUD_API_KEY)."
        )
    alias = (tribunal_alias or "").strip() or alias_do_numero(numero_cnj)
    if not alias:
        raise TribunalNaoMapeadoError(
            "Tribunal não mapeado para consulta ao DataJud (segmento J.TR do "
            "número CNJ fora do mapa atualmente suportado)."
        )
    n = re.sub(r"\D", "", numero_cnj or "")
    payload = {"query": {"match": {"numeroProcesso": n}}, "size": 1}
    headers = {
        "Authorization": f"APIKey {s.DATAJUD_API_KEY}",
        "Content-Type": "application/json",
    }
    data = await _datajud_search(alias, payload, headers)
    hits = (data.get("hits") or {}).get("hits") or []
    if not hits:
        return None
    return hits[0].get("_source") or {}


# Segmento J.TR do número CNJ (NNNNNNN-DD.AAAA.J.TR.OOOO) → alias do endpoint.
# Tabela de códigos J/TR: Resolução CNJ nº 65/2008 (numeração única) — cruzada
# e confirmada contra as entradas já existentes (TJMG=8.13, TJSP=8.26,
# TJRJ=8.19 batem exatamente com a tabela oficial). Cobertura ampliada
# (auditoria RAG) para TODOS os TJs e TRTs — antes só 3 TJs e 1 TRT tinham
# alias mapeado, o que limitava a consulta de andamentos (DataJud) a uma
# fração pequena da Justiça Estadual/Trabalhista.
#   J=8 Justiça Estadual/DF | J=5 Justiça do Trabalho | J=4 Justiça Federal
#   J=3 STJ | J=1 STF (numeração própria, não mapeada aqui — ver nota abaixo)
_SEG_TR_ALIAS = {
    # ── Justiça Estadual (J=8) — todos os 26 estados + DF ──────────────────
    ("8", "01"): "api_publica_tjac",
    ("8", "02"): "api_publica_tjal",
    ("8", "03"): "api_publica_tjap",
    ("8", "04"): "api_publica_tjam",
    ("8", "05"): "api_publica_tjba",
    ("8", "06"): "api_publica_tjce",
    ("8", "07"): "api_publica_tjdft",  # Distrito Federal e Territórios
    ("8", "08"): "api_publica_tjes",
    ("8", "09"): "api_publica_tjgo",
    ("8", "10"): "api_publica_tjma",
    ("8", "11"): "api_publica_tjmt",
    ("8", "12"): "api_publica_tjms",
    ("8", "13"): "api_publica_tjmg",   # Justiça Estadual MG
    ("8", "14"): "api_publica_tjpa",
    ("8", "15"): "api_publica_tjpb",
    ("8", "16"): "api_publica_tjpr",
    ("8", "17"): "api_publica_tjpe",
    ("8", "18"): "api_publica_tjpi",
    ("8", "19"): "api_publica_tjrj",   # Justiça Estadual RJ
    ("8", "20"): "api_publica_tjrn",
    ("8", "21"): "api_publica_tjrs",
    ("8", "22"): "api_publica_tjro",
    ("8", "23"): "api_publica_tjrr",
    ("8", "24"): "api_publica_tjsc",
    ("8", "25"): "api_publica_tjse",
    ("8", "26"): "api_publica_tjsp",   # Justiça Estadual SP
    ("8", "27"): "api_publica_tjto",
    # ── Justiça do Trabalho (J=5) — TST + todas as 24 regiões ──────────────
    ("5", "00"): "api_publica_tst",    # TST (TR=00 no segmento trabalhista)
    ("5", "01"): "api_publica_trt1",
    ("5", "02"): "api_publica_trt2",
    ("5", "03"): "api_publica_trt3",   # Justiça do Trabalho 3ª Região (MG)
    ("5", "04"): "api_publica_trt4",
    ("5", "05"): "api_publica_trt5",
    ("5", "06"): "api_publica_trt6",
    ("5", "07"): "api_publica_trt7",
    ("5", "08"): "api_publica_trt8",
    ("5", "09"): "api_publica_trt9",
    ("5", "10"): "api_publica_trt10",
    ("5", "11"): "api_publica_trt11",
    ("5", "12"): "api_publica_trt12",
    ("5", "13"): "api_publica_trt13",
    ("5", "14"): "api_publica_trt14",
    ("5", "15"): "api_publica_trt15",
    ("5", "16"): "api_publica_trt16",
    ("5", "17"): "api_publica_trt17",
    ("5", "18"): "api_publica_trt18",
    ("5", "19"): "api_publica_trt19",
    ("5", "20"): "api_publica_trt20",
    ("5", "21"): "api_publica_trt21",
    ("5", "22"): "api_publica_trt22",
    ("5", "23"): "api_publica_trt23",
    ("5", "24"): "api_publica_trt24",
    # ── Justiça Federal (J=4) — todos os 6 TRFs ─────────────────────────────
    ("4", "01"): "api_publica_trf1",   # Justiça Federal 1ª Região
    ("4", "02"): "api_publica_trf2",
    ("4", "03"): "api_publica_trf3",
    ("4", "04"): "api_publica_trf4",
    ("4", "05"): "api_publica_trf5",
    ("4", "06"): "api_publica_trf6",   # TRF6 (MG, criado em 2022)
    # ── STJ (J=3) ────────────────────────────────────────────────────────────
    ("3", "00"): "api_publica_stj",    # STJ
}
# NOTA: STF (J=1) não foi incluído — sua numeração de processos não segue o
# mesmo padrão J.TR de tribunal regional/regional (é o topo da hierarquia,
# sem "regiões"), e o DataJud também não fornece texto integral de acórdãos
# (só metadados de movimentação) — não resolve o gap de INGESTÃO DE
# JURISPRUDÊNCIA (STF/TCU/CARF) apontado na auditoria, apenas o de consulta
# de andamento processual. Ver auditoria RAG para o roadmap de conectores de
# jurisprudência propriamente ditos (texto integral/ementas).


def alias_do_numero(numero_cnj: str) -> str | None:
    """Extrai J e TR do número CNJ e mapeia para o alias do tribunal.

    Fallback claro: retorna None quando o número não tem 20 dígitos ou o
    tribunal não está no mapa (o chamador decide entre erro 422 e log).
    """
    n = re.sub(r"\D", "", numero_cnj or "")
    if len(n) != 20:
        return None
    j, tr = n[13], n[14:16]
    return _SEG_TR_ALIAS.get((j, tr))


# Compat: nome antigo usado internamente antes da função virar pública.
_alias_do_numero = alias_do_numero


def _hash_mov(data: str, descricao: str) -> str:
    # SHA-1 usado como chave de deduplicacao/identidade, nunca como
    # assinatura, token ou senha. Ver docs/seguranca/SAST_BASELINE.md
    # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1
    return hashlib.sha1(f"{data}|{descricao}".encode()).hexdigest()[:16]


async def consultar_processo(numero_cnj: str) -> dict | None:
    """Consulta o DataJud; ausência é None e falha de integração propaga.

    Não confunde flag/chave ausente, 401/403, rate limit ou indisponibilidade
    com "processo não encontrado". O router traduz cada classe para 503/502.
    """
    s = get_settings()
    if not s.DATAJUD_ENABLED or not s.DATAJUD_API_KEY:
        raise DataJudDesabilitadoError(
            "Integração DataJud desativada ou sem chave configurada "
            "(DATAJUD_ENABLED/DATAJUD_API_KEY)."
        )
    alias = _alias_do_numero(numero_cnj)
    if not alias:
        raise TribunalNaoMapeadoError(
            "Tribunal não mapeado para consulta ao DataJud."
        )

    n = re.sub(r"\D", "", numero_cnj)
    cacheado = _cache_obter(n)
    if cacheado is not _CACHE_MISS:
        return cacheado

    payload = {"query": {"match": {"numeroProcesso": n}}, "size": 1}
    headers = {
        "Authorization": f"APIKey {s.DATAJUD_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        data = await _datajud_search(alias, payload, headers)
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            _cache_gravar(n, None)
            return None
        src = hits[0]["_source"]
        movs = []
        for m in src.get("movimentos", []) or []:
            movs.append({
                "data": m.get("dataHora", "")[:10],
                "descricao": m.get("nome", ""),
            })
        resultado = {
            "classe": (src.get("classe") or {}).get("nome"),
            "orgao": (src.get("orgaoJulgador") or {}).get("nome"),
            "movimentos": movs,
        }
        _cache_gravar(n, resultado)
        return resultado
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        # Nunca registrar número do processo, payload, corpo ou header.
        status = (
            exc.response.status_code
            if isinstance(exc, httpx.HTTPStatusError)
            and exc.response is not None
            else None
        )
        logger.warning(
            "DataJud falhou após retries (tipo=%s status=%s)",
            type(exc).__name__, status,
        )
        raise


async def buscar_processo_bruto(
    numero_processo: str, tribunal_alias: str,
) -> dict:
    """Consulta crua (JSON Elasticsearch completo) por número + alias explícito.

    Caminho ÚNICO de saída para o wrapper app/integrations/datajud_client.py —
    mesma chave (settings.DATAJUD_API_KEY), mesmo retry/backoff, mesma base URL
    e timeout dos demais caminhos. Mesmo idioma de degradação graciosa: flag
    desligada ou chave ausente → DataJudDesabilitadoError (o router traduz
    para 503); falha de rede/HTTP propaga httpx.* após os retries.
    """
    s = get_settings()
    if not s.DATAJUD_ENABLED or not s.DATAJUD_API_KEY:
        raise DataJudDesabilitadoError(
            "Integração DataJud desativada ou sem chave configurada "
            "(DATAJUD_ENABLED/DATAJUD_API_KEY)."
        )
    n = re.sub(r"\D", "", numero_processo or "")
    payload = {"query": {"match": {"numeroProcesso": n}}}
    headers = {
        "Authorization": f"APIKey {s.DATAJUD_API_KEY}",
        "Content-Type": "application/json",
    }
    return await _datajud_search(tribunal_alias, payload, headers)


# ── Etapa 13 — consulta normalizada de andamentos (router /andamentos) ───────
async def consultar_movimentos(
    numero_cnj: str, tribunal_alias: str | None = None,
) -> list[dict]:
    """Consulta a API Pública do DataJud e devolve os movimentos normalizados.

    Retorna lista ordenada (mais antigo → mais recente) de dicts
    {"data": ISO-8601, "codigo": int|None, "descricao": str} a partir de
    hits.hits[]._source.movimentos[] (codigo/nome/dataHora — ver contrato no
    topo do módulo). Processo não localizado → lista vazia.

    Levanta:
      • DataJudDesabilitadoError — flag desligada ou chave ausente;
      • TribunalNaoMapeadoError — segmento J.TR sem alias no mapa;
      • httpx.* — falha de rede/HTTP após os retries (mensagens sem a chave).
    """
    s = get_settings()
    if not s.DATAJUD_ENABLED or not s.DATAJUD_API_KEY:
        raise DataJudDesabilitadoError(
            "Integração DataJud desativada ou sem chave configurada "
            "(DATAJUD_ENABLED/DATAJUD_API_KEY)."
        )
    alias = (tribunal_alias or "").strip() or alias_do_numero(numero_cnj)
    if not alias:
        raise TribunalNaoMapeadoError(
            "Tribunal não mapeado para consulta ao DataJud (segmento J.TR do "
            "número CNJ fora do mapa atualmente suportado)."
        )

    n = re.sub(r"\D", "", numero_cnj or "")
    payload = {"query": {"match": {"numeroProcesso": n}}, "size": 1}
    headers = {
        "Authorization": f"APIKey {s.DATAJUD_API_KEY}",
        "Content-Type": "application/json",
    }
    data = await _datajud_search(alias, payload, headers)
    hits = (data.get("hits") or {}).get("hits") or []
    if not hits:
        return []
    src = hits[0].get("_source") or {}
    movimentos = []
    for m in src.get("movimentos") or []:
        nome = (m.get("nome") or "").strip()
        if not nome:
            continue
        movimentos.append({
            "data": m.get("dataHora") or "",
            "codigo": m.get("codigo"),
            "descricao": nome,
        })
    movimentos.sort(key=lambda mv: mv["data"])
    return movimentos


async def upsert_movimentos_no_caso(
    db: AsyncSession, case: Case, movimentos: list[dict],
) -> tuple[int, int]:
    """Upsert idempotente dos movimentos do DataJud em case_movimentos.

    Dedup pela MESMA chave de sincronizar_caso — hash(data[:10]|descricao)
    embutido na descrição como sufixo "[dj:<hash16>]" — para que reexecutar a
    sincronização (por qualquer um dos endpoints) nunca duplique um movimento
    já importado. Retorna (novos, total_recebidos). Commit é do chamador.
    """
    existentes = (await db.execute(
        select(CaseMovimento.descricao).where(CaseMovimento.case_id == case.id)
    )).scalars().all()
    hashes_exist = {
        m.group(1)
        for d in existentes
        if (m := re.search(r"\[dj:([0-9a-f]{16})\]", d or ""))
    }

    novos = 0
    for mov in movimentos:
        h = _hash_mov((mov.get("data") or "")[:10], mov.get("descricao") or "")
        if h in hashes_exist:
            continue
        hashes_exist.add(h)  # dedup também dentro do próprio lote
        data_ev = None
        if mov.get("data"):
            try:
                data_ev = datetime.fromisoformat(mov["data"][:10])
            except ValueError:
                data_ev = None
            if data_ev is not None and data_ev.tzinfo is None:
                data_ev = data_ev.replace(tzinfo=timezone.utc)
        db.add(CaseMovimento(
            id=str(uuid4()), case_id=case.id, tipo="andamento_oficial",
            descricao=f"{mov['descricao']} [dj:{h}]",
            data_evento=data_ev,
            created_by=None,
        ))
        novos += 1
        # MESMO gatilho de prazos do sincronizar_caso: como os dois caminhos
        # compartilham a chave de dedup, um movimento importado aqui nunca é
        # reprocessado pelo job noturno — sem esta chamada, o deadline
        # automático desse movimento jamais seria criado (prazo perdido).
        prazos = _detectar_prazos_criticos(mov.get("descricao") or "", data_ev)
        for p in prazos:
            await _criar_deadline_automatico(db, case, p, mov.get("descricao") or "")
    # Telemetria de sync avança também por este caminho (paridade com o legado).
    case.last_synced_at = datetime.now(timezone.utc)
    return novos, len(movimentos)


# ── Parser de movimentos → deadlines automáticos ─────────────────────────────
# Palavras-chave detectadas em movimentos do DataJud que geram prazos processuais.
# Os prazos em dias úteis seguem as regras do CPC/CLT vigentes.
# O advogado DEVE revisar — são alertas, não decisões autônomas (HITL).
_MOVIMENTOS_CRITICOS: list[dict] = [
    {
        "padrao": re.compile(r"cita[çc][aã]o|citado", re.I),
        "titulo": "Contestação (prazo pós-citação)",
        "dias_uteis": 15,
        "tipo": "processual",
        "aviso": "CPC art. 335 — 15 dias úteis da citação. Verificar modalidade.",
    },
    {
        "padrao": re.compile(r"intima[çc][aã]o\s+para\s+manifesta[çc][aã]o", re.I),
        "titulo": "Manifestação (intimação)",
        "dias_uteis": 15,
        "tipo": "processual",
        "aviso": "CPC art. 218, §3º — 15 dias úteis (prazo geral).",
    },
    {
        "padrao": re.compile(r"senten[çc]a|julgamento\s+procedente|julgamento\s+improcedente", re.I),
        "titulo": "Apelação (prazo pós-sentença)",
        "dias_uteis": 15,
        "tipo": "processual",
        "aviso": "CPC art. 1.003, §5º — 15 dias úteis da publicação.",
    },
    {
        "padrao": re.compile(r"ac[oó]rd[aã]o", re.I),
        "titulo": "Recurso Especial/Extraordinário (pós-acórdão)",
        "dias_uteis": 15,
        "tipo": "processual",
        "aviso": "CPC art. 1.003, §5º — 15 dias úteis. Verificar admissibilidade.",
    },
    {
        "padrao": re.compile(r"embargo[s]?\s+de\s+declara[çc][aõ]o|embargos\s+declaratórios", re.I),
        "titulo": "Resposta aos Embargos de Declaração",
        "dias_uteis": 15,
        "tipo": "processual",
        "aviso": "CPC art. 1.023, §2º — 15 dias úteis para responder.",
    },
    {
        "padrao": re.compile(r"laudo\s+pericial|perí?cia\s+realizada", re.I),
        "titulo": "Manifestação sobre laudo pericial",
        "dias_uteis": 15,
        "tipo": "processual",
        "aviso": "CPC art. 477 — 15 dias úteis do depósito do laudo.",
    },
    {
        "padrao": re.compile(r"audi[eê]ncia\s+designada|audi[eê]ncia\s+marcada", re.I),
        "titulo": "Preparação para audiência",
        "dias_uteis": 5,
        "tipo": "interno",
        "aviso": "Alerta interno: preparar caso 5 dias úteis antes.",
    },
]


def _detectar_prazos_criticos(
    descricao: str, data_evento: datetime | None
) -> list[dict]:
    """Barreira jurídica: DataJud não materializa nem calcula prazo operacional.

    Movimento DataJud, isoladamente, não comprova publicação, termo inicial,
    regime ou calendário aplicável. O cálculo deve ocorrer somente no motor
    canônico com revisão humana (HITL).
    """
    return []


async def sincronizar_caso(db: AsyncSession, case: Case) -> int:
    """
    Busca movimentos oficiais e insere os NOVOS em case_movimentos.
    Dedup por hash(data|descricao) embutido na descrição.
    Detecta automaticamente movimentos críticos e cria deadlines preliminares.
    Retorna qtd de movimentos inseridos.
    """
    if not case.numero_processo:
        return 0
    
    case.sync_pending = True
    try:
        info = await consultar_processo(case.numero_processo)
        if not info:
            case.sync_pending = False
            case.last_synced_at = datetime.now(timezone.utc)
            case.sync_error = "Processo não localizado no DataJud"
            return 0
        
        case.sync_error = None
    except Exception as e:
        case.sync_pending = False
        case.sync_error = str(e)
        raise e

    existentes = (await db.execute(
        select(CaseMovimento.descricao).where(CaseMovimento.case_id == case.id)
    )).scalars().all()
    hashes_exist = set()
    for d in existentes:
        m = re.search(r"\[dj:([0-9a-f]{16})\]", d or "")
        if m:
            hashes_exist.add(m.group(1))

    inseridos = 0
    for mov in info["movimentos"]:
        h = _hash_mov(mov["data"], mov["descricao"])
        if h in hashes_exist:
            continue
        data_ev = None
        if mov["data"]:
            data_ev = datetime.fromisoformat(mov["data"])
            # CaseMovimento.data_evento é timestamptz — torna aware (UTC) quando o
            # ISO vier naive, evitando comparação naive vs aware no banco.
            if data_ev.tzinfo is None:
                data_ev = data_ev.replace(tzinfo=timezone.utc)
        db.add(CaseMovimento(
            id=str(uuid4()), case_id=case.id, tipo="andamento_oficial",
            descricao=f"{mov['descricao']} [dj:{h}]",
            data_evento=data_ev,
            created_by=None,
        ))
        inseridos += 1

        # Detectar movimentos críticos → criar deadlines preliminares
        prazos = _detectar_prazos_criticos(mov["descricao"], data_ev)
        for p in prazos:
            await _criar_deadline_automatico(db, case, p, mov["descricao"])

    # Sucesso: metadados de sync atualizados SEMPRE. Antes só eram atualizados
    # dentro de _criar_deadline_automatico, que roda apenas quando há prazo
    # crítico — então um caso sincronizado sem prazo (o caso comum) ficava com
    # sync_pending=True indefinidamente e last_synced_at nunca avançava.
    case.sync_pending = False
    case.last_synced_at = datetime.now(timezone.utc)
    return inseridos


async def _criar_deadline_automatico(
    db: AsyncSession, case: Case, prazo: dict, origem_mov: str
) -> None:
    """Barreira jurídica fail-closed: DataJud nunca persiste Deadline.

    Mantida por compatibilidade interna com callers legados, sem tocar banco,
    calcular vencimento ou registrar conteúdo processual em log. Prazo
    operacional exige motor canônico e revisão humana (HITL).
    """
    logger.warning(
        "[DataJud] criação automática de prazo bloqueada; "
        "exige motor canônico e revisão humana"
    )
    return None


# ── BUG-16: sincronização de PRAZOS a partir do DataJud ──────────────────────
def _ref_datajud(numero_cnj: str, data: str, titulo: str) -> str:
    """Chave estável de dedup de prazo: hash(CNJ|data|titulo)."""
    n = re.sub(r"\D", "", numero_cnj or "")
    # SHA-1 usado como chave de deduplicacao/identidade, nunca como
    # assinatura, token ou senha. Ver docs/seguranca/SAST_BASELINE.md
    # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1
    return hashlib.sha1(f"{n}|{data}|{titulo}".encode()).hexdigest()[:32]


async def sincronizar_prazos_datajud(
    caso_id: str, numero_cnj: str, db: AsyncSession
) -> dict:
    """Puxa movimentos do DataJud e cria prazos (deadlines) não-duplicados.

    - Dedup por `referencia_datajud` (hash CNJ|data|titulo) — nunca reimporta
      o mesmo prazo.
    - Cada prazo é RASCUNHO/HITL: origem='datajud', exige revisão do advogado.
    - Fail-safe: se o DataJud estiver indisponível/sem movimentos, retorna 0 sem
      quebrar o fluxo que a chamou.

    Retorna {"criados": int, "encontrados": int, "erro": str|None}.
    """
    from app.models.deadline import Deadline

    if not numero_cnj:
        return {"criados": 0, "encontrados": 0, "erro": "Caso sem número CNJ."}

    try:
        info = await consultar_processo(numero_cnj)
    except Exception as e:
        logger.warning(f"[DataJud] consulta de prazos falhou p/ {numero_cnj}: {e}")
        return {"criados": 0, "encontrados": 0, "erro": str(e)[:200]}

    if not info or not info.get("movimentos"):
        return {"criados": 0, "encontrados": 0, "erro": None}

    # Responsável do caso (para atribuir o prazo).
    case = (await db.execute(
        select(Case).where(Case.id == caso_id)
    )).scalar_one_or_none()
    responsavel_id = getattr(case, "advogado_responsavel_id", None) if case else None

    # Referências já importadas (dedup por referencia_datajud).
    from sqlalchemy import text as _text
    refs_existentes = set((await db.execute(_text(
        "SELECT referencia_datajud FROM deadlines "
        "WHERE case_id = :cid AND referencia_datajud IS NOT NULL"
    ), {"cid": caso_id})).scalars().all())

    criados = 0
    encontrados = 0
    for mov in info["movimentos"]:
        data_ev = datetime.fromisoformat(mov["data"]) if mov.get("data") else None
        prazos = _detectar_prazos_criticos(mov["descricao"], data_ev)
        for p in prazos:
            encontrados += 1
            ref = _ref_datajud(numero_cnj, mov.get("data", ""), p["titulo"])
            if ref in refs_existentes:
                continue
            db.add(Deadline(
                id=str(uuid4()),
                case_id=caso_id,
                titulo=p["titulo"],
                descricao=(
                    f"[ALERTA AUTOMÁTICO — DataJud]\n"
                    f"Movimento: {mov['descricao'][:200]}\n"
                    f"{p['aviso']}\n"
                    f"⚠️ Revisar e confirmar o prazo antes de qualquer uso (HITL/OAB)."
                ),
                data_prazo=p["data_prazo"],
                tipo=p["tipo"],
                status="pendente",
                responsavel_id=responsavel_id,
                origem="datajud",
                referencia_datajud=ref,
            ))
            refs_existentes.add(ref)
            criados += 1

    return {"criados": criados, "encontrados": encontrados, "erro": None}
