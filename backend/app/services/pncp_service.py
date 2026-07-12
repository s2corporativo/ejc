# ── app/services/pncp_service.py ──────────────────────────────────────────────
# Conector da API pública do PNCP — Portal Nacional de Contratações Públicas
# (Lei 14.133/2021). Consulta PÚBLICA, SEM chave/segredo.
#
# CONTRATO DA API (padrão público PNCP; doc em
# https://pncp.gov.br/api/consulta/swagger-ui/index.html pode estar
# inacessível neste ambiente — por isso tudo é configurável via settings):
#   • GET {PNCP_BASE_URL}/contratacoes/publicacao
#       query: dataInicial, dataFinal (YYYYMMDD), codigoModalidadeContratacao
#       (int; 6 = pregão eletrônico), uf, codigoMunicipioIbge (opcional),
#       pagina, tamanhoPagina.
#   • Resposta JSON: {"data": [...], "totalRegistros", "totalPaginas", ...}.
#
# ANTI-SSRF: a base URL vem de settings com DEFAULT fixo (host oficial); o
# usuário só fornece filtros (datas/uf/município/modalidade), validados antes
# da chamada. Sem chave ⇒ sem segredo a proteger.
#
# CACHE: dados públicos sem PII (contratações são atos públicos) — cache por
# (dia UTC, filtros) para poupar a API; retenção mais longa que os conectores
# com PII. Tabela via CREATE TABLE IF NOT EXISTS (sem migration).
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import text as sqltext
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

logger = logging.getLogger("ejc.pncp")

# Dados públicos (sem PII): retenção generosa — o cache é só performance.
_RETENCAO_DIAS = 30
_TIMEOUT_S = 25.0
# TODO(verificar-vps): confirmar o código IBGE de Betim/MG (3106705) e se a API
# usa `codigoMunicipioIbge` como nome de parâmetro.
MUNICIPIO_BETIM_IBGE = "3106705"


# ── Erros tipados ─────────────────────────────────────────────────────────────

class IntegracaoDesligadaError(RuntimeError):
    """Integração desligada (PNCP_ENABLED=false)."""


class PNCPIndisponivelError(RuntimeError):
    """Falha de rede/HTTP ao alcançar a API pública do PNCP."""


def http_status_para_erro(e: Exception) -> tuple[int, str]:
    if isinstance(e, IntegracaoDesligadaError):
        return 503, str(e)
    if isinstance(e, PNCPIndisponivelError):
        return 502, str(e)
    return 502, "Falha ao consultar o PNCP. Tente novamente em instantes."


# ── Funções puras (testáveis) ─────────────────────────────────────────────────

def _primeiro(d: dict, *chaves: str, default=None):
    if not isinstance(d, dict):
        return default
    for k in chaves:
        v = d.get(k)
        if v not in (None, "", [], {}):
            return v
    return default


def _fmt_data(v: Any) -> str:
    """Aceita date/datetime ou str; devolve YYYYMMDD (formato do PNCP)."""
    if isinstance(v, (date, datetime)):
        return v.strftime("%Y%m%d")
    s = "".join(ch for ch in str(v or "") if ch.isdigit())
    if len(s) != 8:
        raise ValueError("Data inválida: use YYYYMMDD (ou um objeto date).")
    # valida que é uma data real
    datetime.strptime(s, "%Y%m%d")
    return s


def normalizar_contratacao(item: dict) -> dict:
    """Normaliza um item de contratações/publicacao para o formato do EJC.

    Tolerante a variações de campo (a API do PNCP evolui e aninha o órgão em
    `orgaoEntidade`/`unidadeOrgao`)."""
    item = item or {}
    orgao = _primeiro(item, "orgaoEntidade", "orgao", "unidadeOrgao", default={}) or {}
    return {
        "numero_controle_pncp": _primeiro(
            item, "numeroControlePNCP", "numeroControlePncp", "numeroControle"),
        "orgao": _primeiro(orgao, "razaoSocial", "nome", "nomeUnidade")
                 if isinstance(orgao, dict) else str(orgao),
        "orgao_cnpj": _primeiro(orgao, "cnpj", "cnpjOrgao") if isinstance(orgao, dict) else None,
        "objeto": _primeiro(item, "objetoCompra", "objeto", "informacaoComplementar"),
        "valor_total_estimado": _primeiro(
            item, "valorTotalEstimado", "valorEstimado", "valorTotal"),
        "modalidade": _primeiro(item, "modalidadeNome", "modalidadeContratacaoNome",
                                "codigoModalidadeContratacao"),
        "data_abertura_proposta": _primeiro(
            item, "dataAberturaProposta", "dataInicioRecebimentoProposta"),
        "data_encerramento_proposta": _primeiro(
            item, "dataEncerramentoProposta", "dataFimRecebimentoProposta"),
        "uf": _primeiro(item, "unidadeOrgaoUfSigla", "ufSigla", "uf")
              or (_primeiro(orgao, "ufSigla", "uf") if isinstance(orgao, dict) else None),
        "link": _primeiro(item, "linkSistemaOrigem", "link", "urlSistemaOrigem"),
    }


def _chave_cache(filtros: dict) -> str:
    canonico = json.dumps(filtros, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonico.encode()).hexdigest()


# ── Estado persistido (sem migration — precedente infosimples_uso) ────────────

async def _ensure_tabela(db: AsyncSession) -> None:
    await db.execute(sqltext("""
        CREATE TABLE IF NOT EXISTS pncp_cache (
            id VARCHAR(36) PRIMARY KEY,
            dia DATE NOT NULL,
            chave CHAR(64) NOT NULL,
            resultado JSONB NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    await db.execute(sqltext(
        "CREATE INDEX IF NOT EXISTS ix_pncp_cache_lookup ON pncp_cache (dia, chave)"
    ))


async def _purgar_antigos(db: AsyncSession) -> None:
    await db.execute(sqltext(
        "DELETE FROM pncp_cache WHERE dia < (CURRENT_DATE - CAST(:d AS INTEGER))"
    ), {"d": _RETENCAO_DIAS})


async def _buscar_cache(db: AsyncSession, dia: date, chave: str) -> dict | None:
    row = (await db.execute(sqltext(
        "SELECT resultado FROM pncp_cache "
        "WHERE dia = :dia AND chave = :chave AND resultado IS NOT NULL "
        "ORDER BY created_at DESC LIMIT 1"
    ), {"dia": dia, "chave": chave})).scalar()
    if row is None:
        return None
    if isinstance(row, (list, dict)):
        return row
    return json.loads(row)


async def _registrar_cache(db: AsyncSession, dia: date, chave: str, resultado: dict) -> None:
    await db.execute(sqltext(
        "INSERT INTO pncp_cache (id, dia, chave, resultado) "
        "VALUES (:id, :dia, :chave, CAST(:res AS JSONB))"
    ), {
        "id": str(uuid4()), "dia": dia, "chave": chave,
        "res": json.dumps(resultado, ensure_ascii=False, default=str),
    })


# ── Chamada HTTP (isolada para mock nos testes) ───────────────────────────────

async def _get_json(url: str, params: dict, timeout_s: float):
    async with httpx.AsyncClient(timeout=timeout_s) as c:
        r = await c.get(url, params=params)
        r.raise_for_status()
        return r.json()


# ── API principal ─────────────────────────────────────────────────────────────

async def listar_contratacoes(
    db: AsyncSession,
    *,
    data_inicial,
    data_final,
    uf: str = "MG",
    municipio_ibge: str | None = None,
    modalidade: int = 6,
    pagina: int = 1,
) -> dict:
    """Lista contratações públicas do PNCP no período/filtros e normaliza.

    Retorna {"itens": [...], "total_registros", "total_paginas", "pagina",
    "cache": bool}. Cache por (dia UTC, filtros): a mesma consulta no dia não
    refaz a chamada HTTP.

    Levanta:
      • IntegracaoDesligadaError — flag off (router → 503);
      • PNCPIndisponivelError — falha de rede/HTTP (router → 502);
      • ValueError — filtros inválidos (router → 422).
    """
    s = get_settings()
    if not s.PNCP_ENABLED:
        raise IntegracaoDesligadaError(
            "Integração PNCP desativada (PNCP_ENABLED=false). A ativação é uma "
            "decisão do administrador."
        )

    di = _fmt_data(data_inicial)
    df = _fmt_data(data_final)
    if df < di:
        raise ValueError("dataFinal deve ser igual ou posterior à dataInicial.")
    pagina = max(1, int(pagina))

    filtros = {
        # TODO(verificar-vps): confirmar nomes exatos dos parâmetros do PNCP
        # (`codigoModalidadeContratacao`, `codigoMunicipioIbge`) e o default de
        # modalidade (6 = pregão eletrônico) na versão publicada da API.
        "dataInicial": di,
        "dataFinal": df,
        "codigoModalidadeContratacao": int(modalidade),
        "uf": (uf or "").upper() or None,
        "codigoMunicipioIbge": municipio_ibge or None,
        "pagina": pagina,
        "tamanhoPagina": 50,
    }
    query = {k: v for k, v in filtros.items() if v is not None}

    hoje = datetime.now(timezone.utc).date()
    chave = _chave_cache(query)
    await _ensure_tabela(db)
    await _purgar_antigos(db)

    cacheado = await _buscar_cache(db, hoje, chave)
    if cacheado is not None:
        await db.commit()
        return {**cacheado, "cache": True}

    url = f"{(s.PNCP_BASE_URL or '').rstrip('/')}/contratacoes/publicacao"
    try:
        resp = await _get_json(url, query, _TIMEOUT_S)
    except httpx.HTTPStatusError as e:
        # 204/404 do PNCP significam "sem resultados" para o filtro — não é erro.
        if e.response is not None and e.response.status_code in (204, 404):
            resp = {}
        else:
            logger.warning("[pncp] falha HTTP: %s", type(e).__name__)
            raise PNCPIndisponivelError(
                f"Falha ao consultar o PNCP ({type(e).__name__}). Tente novamente."
            ) from None
    except httpx.HTTPError as e:
        logger.warning("[pncp] falha HTTP: %s", type(e).__name__)
        raise PNCPIndisponivelError(
            f"Falha ao consultar o PNCP ({type(e).__name__}). Tente novamente."
        ) from None
    except (ValueError, KeyError):
        raise PNCPIndisponivelError("Resposta inesperada (não-JSON) do PNCP.") from None

    dados = (resp.get("data") if isinstance(resp, dict) else resp) or []
    itens = [normalizar_contratacao(x) for x in dados if isinstance(x, dict)]
    resultado = {
        "itens": itens,
        "total_registros": int(_primeiro(resp, "totalRegistros", "totalElementos",
                                          default=len(itens)) or 0)
        if isinstance(resp, dict) else len(itens),
        "total_paginas": int(_primeiro(resp, "totalPaginas", "totalPages", default=1) or 1)
        if isinstance(resp, dict) else 1,
        "pagina": pagina,
        "fonte": "PNCP — Portal Nacional de Contratações Públicas",
    }
    await _registrar_cache(db, hoje, chave, resultado)
    await db.commit()
    return {**resultado, "cache": False}


async def status(db: AsyncSession | None = None) -> dict:
    """Status da integração para o frontend (sem segredos — PNCP é aberto)."""
    s = get_settings()
    return {
        "enabled": bool(s.PNCP_ENABLED),
        "sem_chave": True,
        "modalidade_padrao": 6,
    }
