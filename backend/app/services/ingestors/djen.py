# ── app/services/ingestors/djen.py ──────────────────────────────────────────
# Ingestor de comunicações processuais do DJEN (Diário de Justiça Eletrônico
# Nacional) via API Comunica/CNJ (Resolução CNJ 569/2024).
#     GET https://comunicaapi.pje.jus.br/api/v1/comunicacao
# Pública, sem autenticação. Consulta por OAB monitorada (numeroOab + ufOab),
# janela incremental diária (dataDisponibilizacaoInicio/Fim) e paginação.
#
# Papel no EJC: a retenção da API Comunica é LIMITADA — este ingestor
# persiste cada comunicação como documento RAG (knowledge_docs), tornando o
# EJC o arquivo histórico permanente e pesquisável do escritório.
#
# Relação com o fluxo de intimações (migration 065 / djen_service.py):
# `job_djen_intimacoes` (scheduler, 06h30) já alimenta a tabela
# djen_comunicacoes por advogado com OAB cadastrada no cadastro de usuários
# (djen_service.capturar_para_advogado: dedup, vínculo a caso, notificação).
# Este ingestor NÃO duplica esse fluxo: ele cobre a persistência RAG das
# OABs em DJEN_OABS_MONITORADAS (que podem incluir OABs sem usuário no EJC).
#
# Rate limit: a API não documenta limites — postura conservadora: coleta
# SEQUENCIAL (OAB a OAB, página a página) com pausa entre páginas.
#
# VALIDAÇÃO REAL: o ambiente de desenvolvimento/CI não alcança
# comunicaapi.pje.jus.br (proxy bloqueia o host). Todos os testes usam
# fixtures/mocks; a validação contra a API real só é possível na VPS.
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections import Counter

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.djen_service import (
    buscar_caso_ativo_por_processo,
    classificar_erro_fonte,
    extrair_numero_cnj,
    extrair_total_djen,
    normalizar_processo,
)
from app.services.djen_http import (
    DJEN_COMUNICACAO_URL,
    DJEN_ITENS_POR_PAGINA,
    obter_proxy_djen,
)
from app.services.ingestion_service import fetch, upsert_documento

logger = logging.getLogger("ejc.ingestao.djen")

BASE = DJEN_COMUNICACAO_URL
ITENS_POR_PAGINA = DJEN_ITENS_POR_PAGINA
MAX_PAGINAS = 200         # 200×50 = teto conservador de 10.000 itens
MAX_RETRIES_PAGINA_VAZIA = 2
PAUSA_ENTRE_PAGINAS = 0.5  # segundos — conservador (API sem rate limit documentado)

_TAG_RE = re.compile(r"<[^>]+>")


def parse_oabs(csv: str) -> list[tuple[str, str]]:
    """Converte o CSV de settings ("12345/MG,67890/MG") em [(numero, UF)]."""
    oabs: list[tuple[str, str]] = []
    for parte in (csv or "").split(","):
        parte = parte.strip()
        if not parte:
            continue
        num, sep, uf = parte.partition("/")
        num = re.sub(r"\D", "", num)
        uf = uf.strip().upper()
        if not sep or not num or len(uf) != 2 or not uf.isalpha():
            logger.warning(f"DJEN: OAB monitorada inválida ignorada: {parte!r}")
            continue
        oabs.append((num, uf))
    return oabs


def _campo(it: dict, *nomes: str) -> str:
    for n in nomes:
        v = it.get(n)
        if v:
            return str(v)
    return ""


def _limpar_html(texto: str) -> str:
    return _TAG_RE.sub(" ", texto or "").strip()


def chave_origem(it: dict) -> str:
    ext = it.get("id") or it.get("hash")
    if ext:
        return f"djen:{ext}"
    base = "|".join([
        _campo(it, "numeroProcesso", "numero_processo", "numeroprocessocommascara"),
        _campo(it, "dataDisponibilizacao", "data_disponibilizacao"),
        _campo(it, "tipoComunicacao", "tipo_comunicacao"),
        _campo(it, "texto"),
    ])
    # SHA-1 usado como chave de deduplicacao/identidade, nunca como
    # assinatura, token ou senha. Ver docs/seguranca/SAST_BASELINE.md
    # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1
    return "djen:" + hashlib.sha1(base.encode("utf-8")).hexdigest()


def montar_documento(it: dict) -> dict | None:
    if not isinstance(it, dict):
        return None
    texto = _limpar_html(_campo(it, "texto"))
    if not texto:
        return None

    tribunal = _campo(it, "siglaTribunal", "sigla_tribunal")[:20]
    tipo = _campo(it, "tipoComunicacao", "tipo_comunicacao")
    orgao = _campo(it, "nomeOrgao", "nome_orgao", "orgao")
    data = _campo(it, "dataDisponibilizacao", "data_disponibilizacao")[:10]
    link = _campo(it, "link")
    num_proc = _campo(it, "numeroProcesso", "numero_processo",
                      "numeroprocessocommascara")
    if not num_proc:
        num_proc = extrair_numero_cnj(texto) or ""

    cab = [f"Comunicação processual (DJEN){' — ' + tribunal if tribunal else ''}"]
    if num_proc:
        cab.append(f"Processo: {num_proc}")
    if tipo:
        cab.append(f"Tipo: {tipo}")
    if orgao:
        cab.append(f"Órgão: {orgao}")
    if data:
        cab.append(f"Disponibilização: {data}")

    titulo = " — ".join(x for x in [
        f"DJEN {tribunal}".strip(), tipo, f"proc. {num_proc}" if num_proc else "",
    ] if x)
    return {
        "titulo": titulo[:500] or "DJEN — comunicação processual",
        "categoria": "comunicacao_processual",
        "conteudo": "\n".join(cab) + "\n\n" + texto,
        "chave_origem": chave_origem(it),
        "fonte": "djen",
        "tribunal": tribunal or None,
        "confianca": "alta",
        "extra": {
            "numero_processo": normalizar_processo(num_proc) or None,
            "tipo_comunicacao": tipo or None,
            "orgao": orgao or None,
            "data_disponibilizacao": data or None,
            "link": link or None,
        },
    }


def _extrair_itens(payload) -> list[dict]:
    if isinstance(payload, dict):
        items = payload.get("items")
        return items if isinstance(items, list) else []
    return payload if isinstance(payload, list) else []


class DjenContratoError(RuntimeError):
    """A consulta ao DJEN não foi respondida no contrato esperado."""


def _classificar_falha_coleta(exc: Exception) -> str:
    """Resume a causa sem carregar OAB, PII ou segredo para logs/Sentry."""
    if isinstance(exc, DjenContratoError):
        msg = str(exc).lower()
        if "json válido" in msg:
            return "payload_invalido"
        if "página" in msg or "paginação" in msg:
            return "paginacao_incompleta"
        return "contrato_invalido"
    if isinstance(exc, RuntimeError) and "DJEN_HTTP_PROXY_URL" in str(exc):
        return "configuracao_proxy"
    return classificar_erro_fonte(exc)


async def _coletar_oab(numero: str, uf: str, ini: str, fim: str) -> list[dict]:
    """Coleta paginada e não confunde página vazia transitória com fim."""
    itens: list[dict] = []
    total_fonte: int | None = None
    pagina = 1
    retries_vazia = 0
    while pagina <= MAX_PAGINAS:
        params = {
            "numeroOab": numero,
            "ufOab": uf,
            "dataDisponibilizacaoInicio": ini,
            "dataDisponibilizacaoFim": fim,
            "itensPorPagina": ITENS_POR_PAGINA,
            "pagina": pagina,
        }
        cache = None
        cache_key = "djen:consulta:" + hashlib.sha256(
            json.dumps(params, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        try:
            import redis.asyncio as aioredis
            url = getattr(get_settings(), "REDIS_URL", "")
            ttl = int(getattr(get_settings(), "DJEN_CACHE_TTL_SEGUNDOS", 900) or 0)
            if url and ttl > 0:
                cache = aioredis.from_url(
                    url, socket_connect_timeout=0.5, socket_timeout=0.5,
                    decode_responses=True,
                )
                cached = await cache.get(cache_key)
                if cached:
                    payload = json.loads(cached)
                    r = None
                else:
                    r = await fetch(BASE, params=params, timeout=30,
                                    proxy=obter_proxy_djen(), trust_env=False)
            else:
                r = await fetch(BASE, params=params, timeout=30,
                                proxy=obter_proxy_djen(), trust_env=False)
        except Exception:
            r = await fetch(BASE, params=params, timeout=30,
                            proxy=obter_proxy_djen(), trust_env=False)
        finally:
            if cache is not None:
                try:
                    await cache.aclose()
                except Exception:
                    pass
        if r is not None:
            try:
                payload = r.json()
            except ValueError:
                payload = None
            if payload is not None:
                try:
                    import redis.asyncio as aioredis
                    url = getattr(get_settings(), "REDIS_URL", "")
                    ttl = int(getattr(get_settings(), "DJEN_CACHE_TTL_SEGUNDOS", 900) or 0)
                    if url and ttl > 0:
                        cache = aioredis.from_url(
                            url, socket_connect_timeout=0.5, socket_timeout=0.5,
                            decode_responses=True,
                        )
                        await cache.set(cache_key, json.dumps(payload, ensure_ascii=False), ex=ttl)
                except Exception:
                    pass
                finally:
                    if cache is not None:
                        try:
                            await cache.aclose()
                        except Exception:
                            pass
        try:
            if payload is None:
                raise ValueError
            lote = _extrair_itens(payload)
        except ValueError:
            logger.warning(f"DJEN OAB {numero}/{uf} p.{pagina}: JSON inválido")
            if pagina == 1:
                raise DjenContratoError(
                    f"DJEN OAB {numero}/{uf}: resposta sem JSON válido na "
                    "primeira página — consulta não foi respondida."
                )
            break

        reportado = extrair_total_djen(payload)
        if reportado is not None:
            total_fonte = reportado

        if not lote:
            if total_fonte is not None and len(itens) < total_fonte:
                if retries_vazia < MAX_RETRIES_PAGINA_VAZIA:
                    retries_vazia += 1
                    await asyncio.sleep(PAUSA_ENTRE_PAGINAS * retries_vazia)
                    continue
                raise DjenContratoError(
                    f"DJEN OAB {numero}/{uf}: página {pagina} vazia antes de "
                    "completar o total reportado"
                )
            return itens

        retries_vazia = 0
        itens.extend(x for x in lote if isinstance(x, dict))
        if total_fonte is not None and len(itens) >= total_fonte:
            return itens
        if len(lote) < ITENS_POR_PAGINA and total_fonte is None:
            return itens
        pagina += 1
        await asyncio.sleep(PAUSA_ENTRE_PAGINAS)

    if pagina > MAX_PAGINAS:
        raise DjenContratoError(
            f"DJEN OAB {numero}/{uf}: paginação atingiu teto sem provar exaustão"
        )
    return itens


async def ingerir(db: AsyncSession) -> tuple[int, int]:
    """Ingere comunicações no RAG e falha alto quando nenhuma OAB foi coletada."""
    from datetime import date, timedelta
    s = get_settings()
    oabs = parse_oabs(s.DJEN_OABS_MONITORADAS)
    if not oabs:
        logger.info("DJEN: nenhuma OAB monitorada configurada — nada a fazer")
        return 0, 0

    fim = date.today()
    ini = fim - timedelta(days=max(1, s.DJEN_INGEST_JANELA_DIAS))

    novos = total = 0
    oabs_ok = oabs_erro = 0
    causas_falha: Counter[str] = Counter()
    for numero, uf in oabs:
        try:
            itens = await _coletar_oab(numero, uf, ini.isoformat(), fim.isoformat())
            oabs_ok += 1
            n_oab = 0
            for it in itens:
                doc = montar_documento(it)
                if not doc:
                    continue
                num_proc = (doc.get("extra") or {}).get("numero_processo")
                case = await buscar_caso_ativo_por_processo(db, num_proc)
                if case is None:
                    logger.info(
                        "DJEN OAB %s/%s: comunicação do processo %s sem caso "
                        "ativo cadastrado — ingestão RAG pulada (evita PII de terceiros)",
                        numero, uf, num_proc or "?",
                    )
                    continue
                doc["case_id"] = case.id
                doc["client_id"] = case.client_id
                doc["extra"]["oab_monitorada"] = f"{numero}/{uf}"
                doc["extra"]["rag_status"] = "aprovado"
                doc["extra"]["tipo_fonte"] = "comunicacao_processual_oficial"
                total += 1
                res = await upsert_documento(db, **doc)
                if res in ("novo", "atualizado"):
                    novos += 1
                    n_oab += 1
                if total % 50 == 0:
                    await db.commit()
            await db.commit()
            logger.info(f"DJEN OAB {numero}/{uf}: {n_oab} novos / {len(itens)} itens")
        except Exception as e:
            oabs_erro += 1
            causa = _classificar_falha_coleta(e)
            causas_falha[causa] += 1
            await db.rollback()
            logger.warning(
                "DJEN: falha de coleta; causa=%s tipo=%s",
                causa, type(e).__name__,
            )

    if oabs_erro and not oabs_ok:
        resumo = ",".join(
            f"{causa}:{quantidade}"
            for causa, quantidade in sorted(causas_falha.items())
        ) or "indeterminada"
        raise DjenContratoError(
            "DJEN: todas as OABs configuradas falharam na coleta "
            f"(oabs_total={len(oabs)}; causas={resumo})"
        )
    if oabs_erro:
        logger.warning(
            "DJEN: coleta parcial — oabs_ok=%s oabs_erro=%s", oabs_ok, oabs_erro
        )
    return novos, total
