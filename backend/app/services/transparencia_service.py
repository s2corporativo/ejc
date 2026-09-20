# ── app/services/transparencia_service.py ────────────────────────────────────
# Conector da API pública do CGU — Portal da Transparência (api-de-dados).
# Consulta as bases de SANÇÕES a empresas por CNPJ:
#   • CEIS  — Cadastro de Empresas Inidôneas e Suspensas (inidoneidade/suspensão);
#   • CNEP  — Cadastro Nacional de Empresas Punidas (Lei Anticorrupção 12.846/13);
#   • CEPIM — Cadastro de Entidades Privadas Impedidas (impedidas de convênio).
#
# CONTRATO DA API (padrão público CGU; a doc oficial em
# https://api.portaldatransparencia.gov.br/swagger-ui.html pode estar
# inacessível neste ambiente — por isso tudo é configurável via settings):
#   • GET {TRANSPARENCIA_BASE_URL}/{ceis|cnep|cepim}
#       header `chave-api-dados: <TRANSPARENCIA_API_KEY>` (chave grátis).
#       query: `cnpjSancionado` (nome do parâmetro pode variar — ver TODO) e
#       `pagina` (paginação 1..N; resposta é uma LISTA JSON de sanções).
#
# SEGREDO: a chave (TRANSPARENCIA_API_KEY) vai APENAS no header da requisição.
# Nunca aparece em URL, logs, exceções, audit log ou payloads devolvidos.
# ANTI-SSRF: a base URL vem de settings com DEFAULT fixo (host oficial); o
# usuário só fornece o CNPJ (14 dígitos, validado antes de qualquer chamada).
#
# CUSTO: a API é GRATUITA — não há teto de cobrança. O cache diário por
# (base, cnpj) existe para poupar a API e acelerar; linhas com mais de
# _RETENCAO_DIAS são purgadas (minimização LGPD — nomes/razões sociais).
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import text as sqltext
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.audit_log import criar_audit_log

logger = logging.getLogger("ejc.transparencia")

_RETENCAO_DIAS = 7
_BASES = ("ceis", "cnep", "cepim")
_TIMEOUT_S = 25.0
_MAX_PAGINAS = 10  # trava de segurança da paginação (cada base costuma ter 1-2 páginas)


# ── Erros tipados ─────────────────────────────────────────────────────────────

class IntegracaoDesligadaError(RuntimeError):
    """Integração desligada (TRANSPARENCIA_ENABLED=false) ou sem chave."""


class TransparenciaIndisponivelError(RuntimeError):
    """Falha de rede/HTTP ao alcançar a API (mensagem sem a chave/headers)."""


def http_status_para_erro(e: Exception) -> tuple[int, str]:
    """Mapeia erros tipados do conector → (status HTTP, detail) p/ os routers.

    As mensagens dos erros tipados nunca contêm a chave de API.
    """
    if isinstance(e, IntegracaoDesligadaError):
        return 503, str(e)
    if isinstance(e, TransparenciaIndisponivelError):
        return 502, str(e)
    return 502, "Falha ao consultar o Portal da Transparência. Tente novamente."


# ── Funções puras (testáveis) ─────────────────────────────────────────────────

def _so_digitos(v: Any) -> str:
    return re.sub(r"\D", "", str(v or ""))


def validar_cnpj(cnpj: str) -> str:
    """Normaliza para 14 dígitos; levanta ValueError se não tiver 14 dígitos."""
    d = _so_digitos(cnpj)
    if len(d) != 14:
        raise ValueError("CNPJ inválido: informe 14 dígitos (com ou sem máscara).")
    return d


def _primeiro(d: dict, *chaves: str, default=None):
    """Primeira chave presente e não-vazia (tolerância a variações da API)."""
    if not isinstance(d, dict):
        return default
    for k in chaves:
        v = d.get(k)
        if v not in (None, "", [], {}):
            return v
    return default


def _texto(v: Any) -> str:
    """Extrai um rótulo textual tolerante de dict/list/escalar."""
    if isinstance(v, dict):
        return str(_primeiro(
            v, "descricao", "descricaoResumida", "nome", "razaoSocial",
            "sigla", default="") or "")
    if isinstance(v, list):
        return "; ".join(t for t in (_texto(x) for x in v) if t)
    return str(v or "")


def normalizar_sancao(item: dict) -> dict:
    """Normaliza um item de CEIS/CNEP/CEPIM para o formato do EJC.

    Tolerante a variações de campo entre as três bases (shapes distintos): a
    CGU pode aninhar `sancionado`/`pessoaJuridica`, `orgaoSancionador`, etc.
    """
    item = item or {}
    sanc = _primeiro(item, "sancionado", "pessoaJuridica", "empresa", default={}) or {}
    orgao = _primeiro(item, "orgaoSancionador", "orgao", "orgaoLotacao", default={})
    return {
        "razao_social": (
            _primeiro(sanc, "nome", "razaoSocial", "nomeEmpresarial")
            or _primeiro(item, "nome", "razaoSocial", "nomeEmpresarial")
        ),
        "cnpj": _so_digitos(
            _primeiro(sanc, "codigoFormatado", "cnpjFormatado", "cnpj", "cpfCnpj",
                      default="")
            or _primeiro(item, "cnpjSancionado", "cnpj", default="")
        ) or None,
        "tipo_sancao": _texto(_primeiro(
            item, "tipoSancao", "tipoPena", "tipo", "descricaoResumida", default="")),
        "data_inicio": _primeiro(
            item, "dataInicioSancao", "dataInicio", "dataReferencia", "dataPublicacao"),
        "data_fim": _primeiro(item, "dataFimSancao", "dataFinalSancao", "dataFim"),
        "orgao_sancionador": _texto(orgao) or _primeiro(
            item, "orgaoSancionador", default=""),
        "fundamentacao": _texto(_primeiro(
            item, "fundamentacao", "textoLei", "motivo", "abrangenciaDefinidaDecisaoJudicial",
            default="")),
    }


# ── Estado persistido (sem migration — precedente infosimples_uso) ────────────

async def _ensure_tabela(db: AsyncSession) -> None:
    """Compatibilidade SQLite; PostgreSQL é gerido pela migration 162."""
    from app.core.database import runtime_ddl_permitido
    if not runtime_ddl_permitido(db):
        return
    await db.execute(sqltext("""
        CREATE TABLE IF NOT EXISTS transparencia_cache (
            id VARCHAR(36) PRIMARY KEY,
            dia DATE NOT NULL,
            base VARCHAR(16) NOT NULL,
            cnpj CHAR(14) NOT NULL,
            resultado JSONB NULL,
            user_id VARCHAR(36) NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    await db.execute(sqltext(
        "CREATE INDEX IF NOT EXISTS ix_transparencia_cache_lookup "
        "ON transparencia_cache (dia, base, cnpj)"
    ))


async def _purgar_antigos(db: AsyncSession) -> None:
    """Minimização LGPD: remove linhas além da retenção (contêm razão social)."""
    await db.execute(sqltext(
        "DELETE FROM transparencia_cache WHERE dia < (CURRENT_DATE - CAST(:d AS INTEGER))"
    ), {"d": _RETENCAO_DIAS})


async def _buscar_cache(
    db: AsyncSession, dia: date, base: str, cnpj: str
) -> list | None:
    row = (await db.execute(sqltext(
        "SELECT resultado FROM transparencia_cache "
        "WHERE dia = :dia AND base = :base AND cnpj = :cnpj "
        "  AND resultado IS NOT NULL "
        "ORDER BY created_at DESC LIMIT 1"
    ), {"dia": dia, "base": base, "cnpj": cnpj})).scalar()
    if row is None:
        return None
    if isinstance(row, (list, dict)):
        return row  # Postgres JSONB já vem desserializado
    return json.loads(row)


async def _registrar_cache(
    db: AsyncSession, dia: date, base: str, cnpj: str,
    resultado: list, user_id: str | None,
) -> None:
    await db.execute(sqltext(
        "INSERT INTO transparencia_cache (id, dia, base, cnpj, resultado, user_id) "
        "VALUES (:id, :dia, :base, :cnpj, CAST(:res AS JSONB), :uid)"
    ), {
        "id": str(uuid4()), "dia": dia, "base": base, "cnpj": cnpj,
        "res": json.dumps(resultado, ensure_ascii=False, default=str),
        "uid": user_id,
    })


# ── Chamada HTTP (isolada para mock nos testes) ───────────────────────────────

async def _get_json(url: str, params: dict, headers: dict, timeout_s: float):
    """GET → JSON. A chave está SÓ em `headers`; exceções httpx carregam
    URL/status, nunca os headers — a chave não vaza."""
    async with httpx.AsyncClient(timeout=timeout_s) as c:
        r = await c.get(url, params=params, headers=headers)
        r.raise_for_status()
        return r.json()


async def _consultar_base(base: str, cnpj: str) -> list[dict]:
    """Consulta uma base (ceis/cnep/cepim) para o CNPJ, paginando e
    normalizando. Erros de rede/HTTP viram TransparenciaIndisponivelError."""
    s = get_settings()
    url = f"{(s.TRANSPARENCIA_BASE_URL or '').rstrip('/')}/{base}"
    headers = {"chave-api-dados": s.TRANSPARENCIA_API_KEY, "Accept": "application/json"}
    itens: list[dict] = []
    try:
        for pagina in range(1, _MAX_PAGINAS + 1):
            resp = await _get_json(url, {
                # TODO(verificar-vps): confirmar o nome do parâmetro de filtro por
                # CNPJ (documentado como `cnpjSancionado`; algumas bases usam `cnpj`).
                "cnpjSancionado": cnpj,
                "pagina": pagina,
            }, headers, _TIMEOUT_S)
            # Resposta pública da CGU é uma LISTA; toleramos wrapper {data:[...]}.
            lote = resp if isinstance(resp, list) else (
                _primeiro(resp, "data", "registros", "content", default=[]) or []
                if isinstance(resp, dict) else [])
            if not lote:
                break
            itens.extend(x for x in lote if isinstance(x, dict))
            if len(lote) < 15:  # página incompleta → última página
                break
    except httpx.HTTPError as e:
        logger.warning("[transparencia] falha HTTP em %s: %s", base, type(e).__name__)
        raise TransparenciaIndisponivelError(
            f"Falha de rede/HTTP ao consultar o Portal da Transparência "
            f"({type(e).__name__}). Tente novamente em instantes."
        ) from None
    except (ValueError, KeyError):
        raise TransparenciaIndisponivelError(
            "Resposta inesperada (não-JSON) do Portal da Transparência."
        ) from None
    return [normalizar_sancao(x) for x in itens]


# ── API principal ─────────────────────────────────────────────────────────────

async def consultar_sancoes(
    db: AsyncSession,
    cnpj: str,
    *,
    user_id: str | None = None,
    user_role: str | None = None,
) -> dict:
    """Consulta CEIS/CNEP/CEPIM para o CNPJ e devolve as sanções normalizadas.

    Retorna {"cnpj", "ceis": [...], "cnep": [...], "cepim": [...],
    "tem_sancao": bool, "cache": bool}. Cada base é cacheada por dia (sem
    nova chamada HTTP se já consultada hoje). "cache" é True quando TODAS as
    bases vieram do cache (nenhuma chamada de rede feita).

    Levanta:
      • IntegracaoDesligadaError — flag off/sem chave (router → 503);
      • TransparenciaIndisponivelError — falha de rede/HTTP (router → 502).
    """
    s = get_settings()
    if not s.TRANSPARENCIA_ENABLED or not s.TRANSPARENCIA_API_KEY:
        raise IntegracaoDesligadaError(
            "Integração Portal da Transparência (CGU) desativada ou sem chave "
            "(TRANSPARENCIA_ENABLED/TRANSPARENCIA_API_KEY). A ativação é uma "
            "decisão do administrador."
        )
    cnpj = validar_cnpj(cnpj)
    hoje = datetime.now(timezone.utc).date()

    await _ensure_tabela(db)
    await _purgar_antigos(db)

    resultados: dict[str, list] = {}
    houve_chamada = False
    for base in _BASES:
        cache = await _buscar_cache(db, hoje, base, cnpj)
        if cache is not None:
            resultados[base] = cache
            continue
        houve_chamada = True
        itens = await _consultar_base(base, cnpj)
        await _registrar_cache(db, hoje, base, cnpj, itens, user_id)
        resultados[base] = itens

    tem_sancao = any(resultados[b] for b in _BASES)
    await criar_audit_log(
        db, user_id, user_role, "CONSULTA_SANCOES", "transparencia", None,
        detalhes=f"cnpj={cnpj} tem_sancao={tem_sancao} "
                 f"(cache={'sim' if not houve_chamada else 'nao'})",
        dados_depois={
            "cnpj": cnpj, "tem_sancao": tem_sancao,
            "contagem": {b: len(resultados[b]) for b in _BASES},
        },
    )
    await db.commit()

    return {
        "cnpj": cnpj,
        "ceis": resultados["ceis"],
        "cnep": resultados["cnep"],
        "cepim": resultados["cepim"],
        "tem_sancao": tem_sancao,
        "cache": not houve_chamada,
    }


async def status(db: AsyncSession) -> dict:
    """Status da integração para o frontend — booleans, sem a chave."""
    s = get_settings()
    return {
        "enabled": bool(s.TRANSPARENCIA_ENABLED),
        "configured": bool(s.TRANSPARENCIA_API_KEY),
        "bases": list(_BASES),
    }
