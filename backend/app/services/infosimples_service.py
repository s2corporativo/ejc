# ── app/services/infosimples_service.py ──────────────────────────────────────
# Conector genérico da API Infosimples — agregador COMERCIAL de consultas a
# sites públicos brasileiros (tribunais, Receita Federal etc.).
#
# CONTRATO DA API (padrão público da Infosimples; a doc oficial em
# https://api.infosimples.com/consultas/docs pode estar inacessível neste
# ambiente — por isso tudo é configurável via settings):
#   • POST {INFOSIMPLES_BASE_URL}/{caminho}  (ex.: tribunal/tjmg/processo)
#     corpo form-urlencoded com `token`, `timeout` e os parâmetros da consulta
#     específica (ex.: numero_processo, cpf+birthdate…).
#   • Resposta JSON: `code` (200 = sucesso; 6xx = erro da consulta),
#     `code_message`, `data` (lista de resultados), `errors`,
#     `header` (metadados: preço/tempo em alguns casos) e
#     `site_receipts` (URLs de comprovantes da raspagem).
#
# CONTROLE DE CUSTO (cada consulta executada é COBRADA):
#   • Teto diário INFOSIMPLES_MAX_CONSULTAS_DIA — contador persistido na
#     tabela `infosimples_uso` (CREATE TABLE IF NOT EXISTS, sem migration —
#     precedente backup_drive_state/backup_service._ensure_state_table).
#     Toda chamada que CHEGA à API (sucesso OU erro 6xx) conta no teto.
#   • Cache do dia: a MESMA consulta (caminho + sha256 dos parâmetros, sem o
#     token) repetida no MESMO dia UTC devolve o resultado salvo SEM nova
#     cobrança. Só sucessos (code==200) são cacheados.
#   • Higiene/LGPD: linhas com mais de _RETENCAO_DIAS são purgadas
#     oportunisticamente (o cache pode conter dados pessoais da Receita —
#     retê-lo além do necessário violaria a minimização da LGPD).
#
# SEGREDOS: o token vai APENAS no corpo form-urlencoded da requisição. Nunca
# aparece em URL, logs, exceções, audit log ou payloads devolvidos ao caller.
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
from app.models.audit_log import criar_audit_log

logger = logging.getLogger("ejc.infosimples")

# Dias de retenção das linhas de uso/cache (contador diário só precisa do dia
# corrente; manter alguns dias dá trilha operacional sem acumular PII).
_RETENCAO_DIAS = 7


# ── Erros tipados ─────────────────────────────────────────────────────────────

class IntegracaoDesligadaError(RuntimeError):
    """Integração desligada (INFOSIMPLES_ENABLED=false) ou sem token."""


class LimiteDiarioAtingidoError(RuntimeError):
    """Teto diário de consultas pagas (INFOSIMPLES_MAX_CONSULTAS_DIA) atingido."""


class InfosimplesConsultaError(RuntimeError):
    """A API respondeu, mas a consulta retornou erro (code != 200).

    Carrega code/code_message da Infosimples — NUNCA o token (que só existe
    no corpo da requisição, jamais em mensagens).
    """

    def __init__(self, code: int, code_message: str, errors: list | None = None):
        self.code = code
        self.code_message = code_message or ""
        self.errors = errors or []
        super().__init__(
            f"Consulta Infosimples retornou erro {code}: {self.code_message}"
        )


class InfosimplesIndisponivelError(RuntimeError):
    """Falha de rede/HTTP ao alcançar a API (mensagem sem token/corpo)."""


# ── Funções puras (testáveis) ─────────────────────────────────────────────────

def hash_parametros(parametros: dict) -> str:
    """Chave de cache: sha256 do JSON canônico dos parâmetros (SEM o token)."""
    limpos = {k: v for k, v in (parametros or {}).items() if k != "token"}
    canonico = json.dumps(limpos, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonico.encode()).hexdigest()


def mascarar_parametros(parametros: dict) -> dict:
    """Versão dos parâmetros segura para audit log/telemetria (LGPD).

    Número de processo é público (ok em claro); CPF e data de nascimento são
    PII → mascarados. CNPJ é dado público de empresa (mantido).
    """
    mascarados: dict[str, Any] = {}
    for k, v in (parametros or {}).items():
        if k == "token":
            continue
        kl = k.lower()
        s = str(v)
        if "cpf" in kl:
            dig = "".join(ch for ch in s if ch.isdigit())
            mascarados[k] = f"{dig[:3]}{'*' * max(len(dig) - 5, 0)}{dig[-2:]}" if len(dig) >= 5 else "***"
        elif "birthdate" in kl or "nascimento" in kl:
            mascarados[k] = "**/**/****"
        else:
            mascarados[k] = v
    return mascarados


def _data_br_para_iso(data_str: str) -> str:
    """dd/mm/aaaa → aaaa-mm-dd (fallback: valor original truncado).

    Essencial para o MERGE TJMG: a chave de dedup [dj:hash16] usa data[:10]
    em ISO — sem esta conversão o mesmo movimento vindo do DataJud e da
    Infosimples ganharia hashes diferentes e duplicaria a timeline.
    """
    s = (data_str or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:10], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s[:10]


def _primeiro(d: dict, *chaves: str, default=None):
    """Primeira chave presente e não-vazia (tolerância a variações da API)."""
    for k in chaves:
        v = d.get(k)
        if v not in (None, "", [], {}):
            return v
    return default


def normalizar_processo_tjmg(item: dict) -> dict:
    """Normaliza um resultado de tribunal/tjmg/processo para o formato do EJC.

    Tolerante a variações de nome de campo (a Infosimples raspa o site do
    TJMG; o shape pode evoluir). Movimentos saem como {"data": ISO, "codigo":
    None, "descricao": str} — o MESMO formato consumido por
    datajud_service.upsert_movimentos_no_caso (dedup [dj:hash16] compartilhado).
    """
    item = item or {}
    movimentos: list[dict] = []
    brutos = _primeiro(item, "movimentacoes", "andamentos", "movimentos", default=[]) or []
    for m in brutos:
        if not isinstance(m, dict):
            continue
        descricao = str(_primeiro(m, "descricao", "movimento", "texto", "nome", default="")).strip()
        if not descricao:
            continue
        movimentos.append({
            "data": _data_br_para_iso(str(_primeiro(m, "data", "data_movimentacao", "dataHora", default=""))),
            "codigo": None,
            "descricao": descricao,
        })
    movimentos.sort(key=lambda mv: mv["data"])

    partes = []
    for p in (_primeiro(item, "partes", "polos", default=[]) or []):
        if isinstance(p, dict):
            partes.append({
                "nome": _primeiro(p, "nome", "parte", default=""),
                "tipo": _primeiro(p, "tipo", "polo", "qualificacao", default=""),
                "advogados": _primeiro(p, "advogados", "advogado", default=None),
            })
        elif isinstance(p, str):
            partes.append({"nome": p, "tipo": "", "advogados": None})

    return {
        "numero_processo": _primeiro(item, "numero_processo", "numero", "processo"),
        "classe": _primeiro(item, "classe", "classe_processual"),
        "assunto": _primeiro(item, "assunto", "assuntos"),
        "situacao": _primeiro(item, "situacao", "status", "situacao_processual"),
        "valor": _primeiro(item, "valor_causa", "valor", "valor_da_causa"),
        "orgao": _primeiro(item, "orgao_julgador", "vara", "comarca", "juizo"),
        "partes": partes,
        "movimentos": movimentos,
    }


def normalizar_receita_cpf(item: dict) -> dict:
    """Situação cadastral/nome oficial do retorno de receita-federal/cpf."""
    item = item or {}
    return {
        "nome": _primeiro(item, "nome", "nome_civil", "nome_completo"),
        "situacao_cadastral": _primeiro(
            item, "situacao_cadastral", "situacao", "descricao_situacao_cadastral"
        ),
        "data_inscricao": _primeiro(item, "data_inscricao", "data_de_inscricao"),
        "ano_obito": _primeiro(item, "ano_obito", "obito"),
        "comprovante": _primeiro(
            item, "codigo_comprovante", "comprovante_emissao", "comprovante"
        ),
    }


def normalizar_receita_cnpj(item: dict) -> dict:
    """Situação cadastral/razão social do retorno de receita-federal/cnpj."""
    item = item or {}
    return {
        "razao_social": _primeiro(item, "razao_social", "nome_empresarial", "nome"),
        "nome_fantasia": _primeiro(item, "nome_fantasia", "fantasia"),
        "situacao_cadastral": _primeiro(
            item, "situacao_cadastral", "situacao", "descricao_situacao_cadastral"
        ),
        "data_abertura": _primeiro(item, "data_abertura", "abertura", "data_inicio_atividade"),
        "natureza_juridica": _primeiro(item, "natureza_juridica"),
        "atividade_principal": _primeiro(
            item, "atividade_principal", "cnae_principal", "atividade_economica"
        ),
        "endereco": _primeiro(item, "endereco", "logradouro"),
        "capital_social": _primeiro(item, "capital_social"),
    }


def normalizar_car_imovel(item: dict) -> dict:
    """Normaliza um resultado de car-imovel (SICAR — Cadastro Ambiental Rural).

    Tolerante a variações de campo (a Infosimples raspa o SICAR; o shape pode
    evoluir). Coordenadas/polígono são devolvidos como vieram, quando houver.
    """
    item = item or {}
    return {
        "numero_car": _primeiro(item, "numero_car", "numero", "codigo_car", "registro_car", "car"),
        "area_ha": _primeiro(item, "area_ha", "area", "area_imovel", "area_total_ha"),
        "municipio": _primeiro(item, "municipio", "municipio_nome", "cidade"),
        "uf": _primeiro(item, "uf", "estado", "sigla_uf"),
        "situacao": _primeiro(item, "situacao", "situacao_cadastro", "status"),
        "condicao_cadastro": _primeiro(
            item, "condicao_cadastro", "condicao", "condicao_imovel"),
        "coordenadas": _primeiro(item, "coordenadas", "centroide", "latitude_longitude"),
        "poligono": _primeiro(item, "poligono", "perimetro", "geometria", "geometry"),
        "nome_imovel": _primeiro(item, "nome_imovel", "nome", "denominacao"),
    }


def normalizar_car_demonstrativo(item: dict) -> dict:
    """Normaliza um resultado de car-demonstrativo (situação/áreas ambientais).

    Tolerante a campos ausentes: reserva legal, APP, uso restrito e situação
    podem não vir em todos os imóveis."""
    item = item or {}
    return {
        "situacao": _primeiro(item, "situacao", "situacao_cadastro", "status"),
        "area_total": _primeiro(item, "area_total", "area_imovel", "area", "area_ha"),
        "reserva_legal": _primeiro(
            item, "reserva_legal", "area_reserva_legal", "rl"),
        "app": _primeiro(item, "app", "area_preservacao_permanente", "area_app"),
        "uso_restrito": _primeiro(item, "uso_restrito", "area_uso_restrito"),
        "area_consolidada": _primeiro(
            item, "area_consolidada", "area_rural_consolidada"),
        "vegetacao_nativa": _primeiro(
            item, "vegetacao_nativa", "remanescente_vegetacao_nativa"),
        "modulos_fiscais": _primeiro(item, "modulos_fiscais", "modulo_fiscal"),
    }


# ── Estado persistido (sem migration — precedente backup_drive_state) ─────────

async def _ensure_tabela(db: AsyncSession) -> None:
    """Cria a tabela de uso/cache se não existir (idempotente).

    Uma LINHA por consulta EXECUTADA (cobrada) na API: o contador diário é
    COUNT(*) do dia e o cache é o `resultado` da linha de sucesso.
    """
    await db.execute(sqltext("""
        CREATE TABLE IF NOT EXISTS infosimples_uso (
            id VARCHAR(36) PRIMARY KEY,
            dia DATE NOT NULL,
            caminho TEXT NOT NULL,
            parametros_hash CHAR(64) NOT NULL,
            code INTEGER NULL,
            resultado JSONB NULL,
            user_id VARCHAR(36) NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    await db.execute(sqltext(
        "CREATE INDEX IF NOT EXISTS ix_infosimples_uso_dia ON infosimples_uso (dia)"
    ))
    await db.execute(sqltext(
        "CREATE INDEX IF NOT EXISTS ix_infosimples_uso_cache "
        "ON infosimples_uso (dia, caminho, parametros_hash)"
    ))


async def _purgar_antigos(db: AsyncSession) -> None:
    """Minimização LGPD: remove linhas além da retenção (cache pode ter PII)."""
    await db.execute(sqltext(
        "DELETE FROM infosimples_uso WHERE dia < (CURRENT_DATE - CAST(:d AS INTEGER))"
    ), {"d": _RETENCAO_DIAS})


async def _buscar_cache(
    db: AsyncSession, dia: date, caminho: str, phash: str
) -> dict | None:
    row = (await db.execute(sqltext(
        "SELECT resultado FROM infosimples_uso "
        "WHERE dia = :dia AND caminho = :caminho AND parametros_hash = :ph "
        "  AND resultado IS NOT NULL "
        "ORDER BY created_at DESC LIMIT 1"
    ), {"dia": dia, "caminho": caminho, "ph": phash})).scalar()
    if row is None:
        return None
    return row if isinstance(row, dict) else json.loads(row)


async def _contar_uso_dia(db: AsyncSession, dia: date) -> int:
    return int((await db.execute(sqltext(
        "SELECT COUNT(*) FROM infosimples_uso WHERE dia = :dia"
    ), {"dia": dia})).scalar() or 0)


async def _registrar_uso(
    db: AsyncSession, dia: date, caminho: str, phash: str,
    code: int | None, resultado: dict | None, user_id: str | None,
) -> None:
    await db.execute(sqltext(
        "INSERT INTO infosimples_uso "
        "(id, dia, caminho, parametros_hash, code, resultado, user_id) "
        "VALUES (:id, :dia, :caminho, :ph, :code, CAST(:res AS JSONB), :uid)"
    ), {
        "id": str(uuid4()), "dia": dia, "caminho": caminho, "ph": phash,
        "code": code,
        "res": json.dumps(resultado, ensure_ascii=False, default=str)
               if resultado is not None else None,
        "uid": user_id,
    })


# ── Chamada HTTP (isolada para mock nos testes) ───────────────────────────────

async def _post_form(url: str, dados: dict, timeout_s: float) -> dict:
    """POST form-urlencoded → JSON. O token está SÓ em `dados` (corpo);
    exceções httpx carregam URL/status, nunca o corpo — o token não vaza."""
    async with httpx.AsyncClient(timeout=timeout_s) as c:
        r = await c.post(url, data=dados)
        r.raise_for_status()
        return r.json()


# ── API principal ─────────────────────────────────────────────────────────────

async def consultar(
    db: AsyncSession,
    caminho: str,
    parametros: dict,
    *,
    user_id: str | None = None,
    user_role: str | None = None,
) -> dict:
    """Executa (ou resolve do cache do dia) uma consulta paga na Infosimples.

    Retorna {"code", "code_message", "data", "header", "site_receipts",
    "cache": bool}. O bookkeeping de custo (linha em infosimples_uso + audit
    log) é COMMITADO aqui mesmo: uma consulta cobrada é fato consumado — não
    pode se perder num rollback do fluxo chamador.

    Levanta:
      • IntegracaoDesligadaError — flag off/sem token (router → 503);
      • LimiteDiarioAtingidoError — teto INFOSIMPLES_MAX_CONSULTAS_DIA (→ 429);
      • InfosimplesConsultaError — API respondeu code != 200 (com
        code/code_message, SEM token) — a chamada CONTA no teto diário;
      • InfosimplesIndisponivelError — falha de rede/HTTP (mensagem limpa).
    """
    s = get_settings()
    if not s.INFOSIMPLES_ENABLED or not s.INFOSIMPLES_TOKEN:
        raise IntegracaoDesligadaError(
            "Integração Infosimples desativada ou sem token configurado "
            "(INFOSIMPLES_ENABLED/INFOSIMPLES_TOKEN). Cada consulta é paga — "
            "a ativação é uma decisão do administrador."
        )
    caminho = (caminho or "").strip().strip("/")
    if not caminho:
        raise ValueError("Caminho da consulta Infosimples vazio.")

    hoje = datetime.now(timezone.utc).date()
    phash = hash_parametros(parametros)

    await _ensure_tabela(db)
    await _purgar_antigos(db)

    # 1) Cache do dia: mesma consulta já paga hoje → devolve sem nova cobrança.
    cacheado = await _buscar_cache(db, hoje, caminho, phash)
    if cacheado is not None:
        await criar_audit_log(
            db, user_id, user_role, "CONSULTA_PAGA", "infosimples", None,
            detalhes=f"{caminho} (cache do dia, sem cobrança)",
            dados_depois={
                "caminho": caminho, "parametros": mascarar_parametros(parametros),
                "cache": True,
            },
        )
        await db.commit()
        return {**cacheado, "cache": True}

    # 2) Teto de custo. (Checagem read-then-insert: corrida entre requisições
    #    simultâneas pode estourar o teto em poucas unidades — aceitável para
    #    um teto de custo diário; o contador persistido corrige no próximo hit.)
    usados = await _contar_uso_dia(db, hoje)
    if usados >= s.INFOSIMPLES_MAX_CONSULTAS_DIA:
        raise LimiteDiarioAtingidoError(
            f"Limite diário de consultas Infosimples atingido "
            f"({usados}/{s.INFOSIMPLES_MAX_CONSULTAS_DIA}). Cada consulta é "
            "cobrada — o teto (INFOSIMPLES_MAX_CONSULTAS_DIA) reinicia à "
            "meia-noite UTC."
        )

    # 3) Chamada real (paga). Token e timeout no corpo form-urlencoded.
    url = f"{(s.INFOSIMPLES_BASE_URL or '').rstrip('/')}/{caminho}"
    corpo = {**(parametros or {}),
             "token": s.INFOSIMPLES_TOKEN, "timeout": s.INFOSIMPLES_TIMEOUT}
    try:
        resposta = await _post_form(url, corpo, float(s.INFOSIMPLES_TIMEOUT) + 30.0)
    except httpx.HTTPError as e:
        # Sem retry: repetir uma consulta PAGA sem certeza do estado da
        # primeira poderia dobrar o custo. Mensagem sem corpo/token.
        logger.warning("[infosimples] falha HTTP em %s: %s", caminho, type(e).__name__)
        raise InfosimplesIndisponivelError(
            f"Falha de rede/HTTP ao consultar a Infosimples ({type(e).__name__}). "
            "Tente novamente em instantes."
        ) from None
    except (ValueError, KeyError):
        raise InfosimplesIndisponivelError(
            "Resposta inesperada (não-JSON) da Infosimples."
        ) from None

    code = int(resposta.get("code") or 0)
    code_message = str(resposta.get("code_message") or "")
    resultado = {
        "code": code,
        "code_message": code_message,
        "data": resposta.get("data") or [],
        "header": resposta.get("header") or {},
        "site_receipts": resposta.get("site_receipts") or [],
    }

    # 4) Bookkeeping da consulta EXECUTADA (cobrada): conta no teto mesmo em
    #    erro 6xx; só sucesso vira cache. Commit imediato (fato consumado).
    sucesso = code == 200
    await _registrar_uso(
        db, hoje, caminho, phash, code, resultado if sucesso else None, user_id,
    )
    await criar_audit_log(
        db, user_id, user_role, "CONSULTA_PAGA", "infosimples", None,
        detalhes=f"{caminho} (code={code})",
        dados_depois={
            "caminho": caminho, "parametros": mascarar_parametros(parametros),
            "code": code, "cache": False,
        },
    )
    await db.commit()

    if not sucesso:
        raise InfosimplesConsultaError(
            code, code_message, resposta.get("errors") or []
        )
    return {**resultado, "cache": False}


def http_status_para_erro(e: Exception) -> tuple[int, str]:
    """Mapeia erros tipados do conector → (status HTTP, detail) p/ os routers.

    Sem import de FastAPI aqui (service não conhece HTTP); as mensagens dos
    erros tipados nunca contêm o token.
    """
    if isinstance(e, IntegracaoDesligadaError):
        return 503, str(e)
    if isinstance(e, LimiteDiarioAtingidoError):
        return 429, str(e)
    if isinstance(e, (InfosimplesConsultaError, InfosimplesIndisponivelError)):
        return 502, str(e)
    return 502, "Falha ao consultar a Infosimples. Tente novamente em instantes."


async def status(db: AsyncSession) -> dict:
    """Status da integração para o frontend — booleans e contadores, sem token."""
    s = get_settings()
    usados = 0
    if s.INFOSIMPLES_ENABLED:
        try:
            await _ensure_tabela(db)
            usados = await _contar_uso_dia(db, datetime.now(timezone.utc).date())
        except Exception:  # telemetria nunca derruba o status
            logger.warning("[infosimples] falha ao contar uso do dia", exc_info=True)
    return {
        "enabled": bool(s.INFOSIMPLES_ENABLED),
        "configured": bool(s.INFOSIMPLES_TOKEN),
        "consultas_hoje": usados,
        "limite_diario": s.INFOSIMPLES_MAX_CONSULTAS_DIA,
    }
