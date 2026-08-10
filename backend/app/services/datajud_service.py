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
#
# REGRA P0 / Issue #968:
# DataJud é fonte de movimentação, NÃO fonte autônoma de vencimento processual.
# Enquanto não existir o motor auditável por regime, publicação, termo inicial
# e calendário jurisdicional, este serviço não materializa Deadline nem calcula
# vencimento a partir da data de um movimento.
from __future__ import annotations

import hashlib
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
PRAZO_DATAJUD_MOTIVO_BLOQUEIO = (
    "calculo_automatico_bloqueado_ate_motor_auditavel_por_regime"
)


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


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    retry=retry_if_exception(_erro_datajud_transitorio),
    reraise=True,
)
async def _datajud_search(alias: str, payload: dict, headers: dict) -> dict:
    s = get_settings()
    base = (s.DATAJUD_BASE_URL or BASE).rstrip("/")
    async with httpx.AsyncClient(timeout=s.DATAJUD_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{base}/{alias}/_search", json=payload, headers=headers
        )
        response.raise_for_status()
        return response.json()


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
            movs.append(
                {
                    "data": m.get("dataHora", "")[:10],
                    "descricao": m.get("nome", ""),
                }
            )
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
            type(exc).__name__,
            status,
        )
        raise


async def buscar_processo_bruto(
    numero_processo: str,
    tribunal_alias: str,
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
    numero_cnj: str,
    tribunal_alias: str | None = None,
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
        movimentos.append(
            {
                "data": m.get("dataHora") or "",
                "codigo": m.get("codigo"),
                "descricao": nome,
            }
        )
    movimentos.sort(key=lambda mv: mv["data"])
    return movimentos


async def upsert_movimentos_no_caso(
    db: AsyncSession,
    case: Case,
    movimentos: list[dict],
) -> tuple[int, int]:
    """Upsert idempotente dos movimentos do DataJud em ``case_movimentos``.

    Dedup pela mesma chave de ``sincronizar_caso`` — hash(data[:10]|descricao)
    embutido na descrição como sufixo ``[dj:<hash16>]``. O método importa
    somente movimentação oficial; ele deliberadamente NÃO cria prazo.
    """
    existentes = (
        await db.execute(
            select(CaseMovimento.descricao).where(CaseMovimento.case_id == case.id)
        )
    ).scalars().all()
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
        hashes_exist.add(h)
        data_ev = None
        if mov.get("data"):
            try:
                data_ev = datetime.fromisoformat(mov["data"][:10])
            except ValueError:
                data_ev = None
            if data_ev is not None and data_ev.tzinfo is None:
                data_ev = data_ev.replace(tzinfo=timezone.utc)
        db.add(
            CaseMovimento(
                id=str(uuid4()),
                case_id=case.id,
                tipo="andamento_oficial",
                descricao=f"{mov['descricao']} [dj:{h}]",
                data_evento=data_ev,
                created_by=None,
            )
        )
        novos += 1

    case.last_synced_at = datetime.now(timezone.utc)
    return novos, len(movimentos)


def _detectar_prazos_criticos(
    _descricao: str,
    _data_evento: datetime | None,
) -> list[dict]:
    """Compatibilidade fail-safe do parser legado de prazos.

    O DataJud informa movimentações; a data do movimento não prova, sozinha,
    disponibilização, publicação, termo inicial, regime nem calendário aplicável.
    Por isso não há sugestão de vencimento até a reconstrução canônica da #968.
    """
    return []


async def sincronizar_caso(db: AsyncSession, case: Case) -> int:
    """Sincroniza movimentações oficiais sem criar prazos automaticamente."""
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
    except Exception as exc:
        case.sync_pending = False
        # Não persiste mensagem externa potencialmente sensível; a classe é
        # suficiente para diagnóstico operacional e mantém o detalhe no log da
        # camada que tratou a integração.
        case.sync_error = f"Falha DataJud ({type(exc).__name__})"
        raise

    existentes = (
        await db.execute(
            select(CaseMovimento.descricao).where(CaseMovimento.case_id == case.id)
        )
    ).scalars().all()
    hashes_exist = {
        match.group(1)
        for descricao in existentes
        if (match := re.search(r"\[dj:([0-9a-f]{16})\]", descricao or ""))
    }

    inseridos = 0
    for mov in info["movimentos"]:
        h = _hash_mov(mov["data"], mov["descricao"])
        if h in hashes_exist:
            continue
        hashes_exist.add(h)
        data_ev = None
        if mov["data"]:
            try:
                data_ev = datetime.fromisoformat(mov["data"])
            except ValueError:
                data_ev = None
            if data_ev is not None and data_ev.tzinfo is None:
                data_ev = data_ev.replace(tzinfo=timezone.utc)
        db.add(
            CaseMovimento(
                id=str(uuid4()),
                case_id=case.id,
                tipo="andamento_oficial",
                descricao=f"{mov['descricao']} [dj:{h}]",
                data_evento=data_ev,
                created_by=None,
            )
        )
        inseridos += 1

    case.sync_pending = False
    case.last_synced_at = datetime.now(timezone.utc)
    return inseridos


async def _criar_deadline_automatico(
    _db: AsyncSession,
    _case: Case,
    _prazo: dict,
    _origem_mov: str,
) -> None:
    """Compatibilidade fail-safe: DataJud não materializa ``Deadline``."""
    return None


def _ref_datajud(numero_cnj: str, data: str, titulo: str) -> str:
    """Chave estável legada mantida para compatibilidade e reconciliação futura."""
    n = re.sub(r"\D", "", numero_cnj or "")
    return hashlib.sha1(f"{n}|{data}|{titulo}".encode()).hexdigest()[:32]


async def sincronizar_prazos_datajud(
    _caso_id: str,
    numero_cnj: str,
    _db: AsyncSession,
) -> dict:
    """Contrato compatível, deliberadamente sem criação automática de prazo.

    Movimentações continuam disponíveis pela sincronização normal. A conversão
    para prazo fatal depende de revisão humana e do motor auditável da #968.
    """
    if not numero_cnj:
        return {
            "criados": 0,
            "encontrados": 0,
            "erro": "Caso sem número CNJ.",
            "revisao_necessaria": True,
            "motivo": PRAZO_DATAJUD_MOTIVO_BLOQUEIO,
        }
    return {
        "criados": 0,
        "encontrados": 0,
        "erro": None,
        "revisao_necessaria": True,
        "motivo": PRAZO_DATAJUD_MOTIVO_BLOQUEIO,
    }
