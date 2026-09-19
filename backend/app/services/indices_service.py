# ── app/services/indices_service.py ──────────────────────────────────────────
# Fonte OFICIAL de índices econômicos para cálculos judiciais (Bloco 1 das
# APIs públicas). Clientes:
#   • BCB SGS  — séries mensais/diárias (IPCA, INPC, IGP-M, SELIC, CDI, TR,
#     poupança e a TAXA LEGAL da Lei 14.905/2024, série 29543), com paginação
#     automática pela janela máxima de 10 anos por chamada.
#   • BCB Olinda — taxaJuros (revisional bancária, por modalidade/instituição)
#     e PTAX (câmbio oficial, sintaxe OData de function import corrigida).
#
# CACHE em duas camadas:
#   1. memória do processo (dict por código de série);
#   2. tabela `indices_bcb_cache` criada via CREATE TABLE IF NOT EXISTS —
#      mesmo precedente de backup_drive_state (SEM migration Alembic).
# A chamada só vai ao BCB quando o cache não cobre o período pedido (ou o
# período toca o presente e a última consulta passou de 24h). BCB fora do ar
# ⇒ serve o cache disponível e loga warning (nunca inventa valor).
#
# Todas as funções de negócio são puras sobre a série obtida e devolvem
# memória de cálculo auditável (HITL — o advogado revisa).
from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

import httpx

from app.core.config import get_settings

logger = logging.getLogger("ejc.indices")

# ── Séries SGS suportadas (código BCB → metadados) ────────────────────────────
# tipo: "mensal" (índice de competência, muda 1x/mês) | "diaria".
SERIES: dict[str, dict] = {
    "selic_diaria":    {"codigo": 11,    "nome": "SELIC diária (% a.d.)",                  "tipo": "diaria"},
    "selic_meta":      {"codigo": 432,   "nome": "Meta SELIC definida pelo Copom (% a.a.)", "tipo": "diaria"},
    "selic_mensal":    {"codigo": 4390,  "nome": "SELIC acumulada no mês (%)",              "tipo": "mensal"},
    "cdi_diaria":      {"codigo": 12,    "nome": "CDI (% a.d.)",                            "tipo": "diaria"},
    "cdi_mensal":      {"codigo": 4391,  "nome": "CDI acumulado no mês (%)",                "tipo": "mensal"},
    "ipca":            {"codigo": 433,   "nome": "IPCA (IBGE, % a.m.)",                     "tipo": "mensal"},
    "inpc":            {"codigo": 188,   "nome": "INPC (IBGE, % a.m.)",                     "tipo": "mensal"},
    "igpm":            {"codigo": 189,   "nome": "IGP-M (FGV, % a.m.)",                     "tipo": "mensal"},
    "ipca15":          {"codigo": 7478,  "nome": "IPCA-15 (IBGE, % a.m.)",                  "tipo": "mensal"},
    # IPCA-E (SGS 10764): apesar do nome ("acumulado trimestral"), a sondagem ao
    # vivo (scripts/probe_apis.py) mostrou que a 10764 devolve o MESMO valor
    # MENSAL que a 7478 (IPCA-15) — no SGS ela é publicada como VARIAÇÃO MENSAL;
    # o acumulado trimestral é uma agregação externa. Por isso o rótulo diz
    # "variação mensal" e a composição mensal (produto de 1+v/100) está correta.
    "ipca_e":          {"codigo": 10764, "nome": "IPCA-E (IBGE, variação mensal — IPCA-15/IPCA-E)", "tipo": "mensal"},
    "tr":              {"codigo": 226,   "nome": "TR (% a.m.)",                             "tipo": "mensal"},
    "poupanca_antiga": {"codigo": 25,    "nome": "Poupança até 03/05/2012 (% a.m.)",        "tipo": "mensal"},
    "poupanca":        {"codigo": 195,   "nome": "Poupança após 04/05/2012 (% a.m.)",       "tipo": "mensal"},
    "taxa_legal":      {"codigo": 29543, "nome": "Taxa Legal — Lei 14.905/2024 (% a.m.)",   "tipo": "mensal"},
}

_SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
_SGS_ULTIMOS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados/ultimos/{n}"

# Janela máxima do SGS é 10 anos por chamada — pagina abaixo disto.
_JANELA_MAX_DIAS = 3600

OLINDA_TAXA_MENSAL = ("https://olinda.bcb.gov.br/olinda/servico/taxaJuros/"
                      "versao/v2/odata/TaxasJurosMensalPorMes")
OLINDA_TAXA_DIARIA = ("https://olinda.bcb.gov.br/olinda/servico/taxaJuros/"
                      "versao/v2/odata/TaxasJurosDiariaPorInicioPeriodo")
# PTAX: function import OData — os nomes dos parâmetros DEVEM casar com a
# assinatura oficial (@dataInicialCotacao/@dataFinalCotacao, datas MM-DD-YYYY
# entre aspas simples). O probe de 11/07/2026 tomou 400 exatamente por isso.
OLINDA_PTAX = ("https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
               "CotacaoDolarPeriodo(dataInicialCotacao=@dataInicialCotacao,"
               "dataFinalCotacao=@dataFinalCotacao)")


class BCBIndisponivel(RuntimeError):
    """BCB fora do ar e sem cache que cubra o período pedido."""


# ── HTTP (indireção única — testes mockam aqui, sem rede) ─────────────────────

async def _get_json(url: str, params: dict | None = None):
    timeout = get_settings().INDICES_BCB_TIMEOUT
    async with httpx.AsyncClient(timeout=timeout) as cli:
        r = await cli.get(url, params=params)
        r.raise_for_status()
        return r.json()


# ── Cliente SGS com paginação por década ──────────────────────────────────────

def _parse_item(item: dict) -> tuple[date, Decimal]:
    d = datetime.strptime(item["data"], "%d/%m/%Y").date()
    v = Decimal(str(item["valor"]).replace(",", "."))
    return d, v


async def _sgs_buscar(codigo: int, ini: date, fim: date) -> dict[date, Decimal]:
    """GET paginado no SGS respeitando a janela máxima de 10 anos por chamada."""
    valores: dict[date, Decimal] = {}
    cursor = ini
    while cursor <= fim:
        fim_janela = min(fim, cursor + timedelta(days=_JANELA_MAX_DIAS))
        data = await _get_json(_SGS_URL.format(codigo=codigo), params={
            "formato": "json",
            "dataInicial": cursor.strftime("%d/%m/%Y"),
            "dataFinal": fim_janela.strftime("%d/%m/%Y"),
        })
        for item in data or []:
            try:
                d, v = _parse_item(item)
            except Exception:      # item malformado não derruba a série
                continue
            valores[d] = v
        cursor = fim_janela + timedelta(days=1)
    return valores


async def sgs_ultimos(codigo: int, n: int = 1) -> list[dict]:
    """Últimos N valores divulgados de uma série (endpoint /dados/ultimos)."""
    data = await _get_json(_SGS_ULTIMOS_URL.format(codigo=codigo, n=n),
                           params={"formato": "json"})
    return data or []


# ── Cache persistente (tabela via CREATE TABLE IF NOT EXISTS) ─────────────────
# Camada 1: memória do processo. Camada 2: Postgres (sobrevive a restart).
# Persistência é best-effort: falha de banco NUNCA quebra o cálculo.

_TTL_PRESENTE_S = 24 * 3600.0   # revalida diárias/mês corrente a cada 24h
_MEM: dict[int, dict] = {}      # codigo -> {valores, ini, fim, fetched_at}


def _agora() -> float:
    return time.monotonic()      # indireção p/ testes (padrão bcb_service)


async def _db_carregar(codigo: int) -> dict | None:
    """Hidrata o cache em memória a partir da tabela (cold start)."""
    try:
        from sqlalchemy import text as sqltext
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await _ensure_cache_table(db)
            meta = (await db.execute(sqltext(
                "SELECT data_inicial, data_final, consultado_em "
                "FROM indices_bcb_cache_meta WHERE codigo = :c"
            ), {"c": codigo})).mappings().first()
            if not meta:
                return None
            rows = (await db.execute(sqltext(
                "SELECT data, valor FROM indices_bcb_cache WHERE codigo = :c"
            ), {"c": codigo})).all()
        idade = 0.0
        try:
            consultado = meta["consultado_em"]
            if consultado is not None:
                idade = max(
                    (datetime.now(consultado.tzinfo) - consultado).total_seconds(), 0.0)
        except Exception:
            idade = _TTL_PRESENTE_S  # sem timestamp confiável → força revalidar
        return {
            "valores": {r[0]: Decimal(str(r[1])) for r in rows},
            "ini": meta["data_inicial"], "fim": meta["data_final"],
            "fetched_at": _agora() - idade,
        }
    except Exception as exc:
        logger.debug("indices: cache DB indisponível p/ série %s (%s)", codigo, exc)
        return None


async def _ensure_cache_table(db) -> None:
    from app.core.database import runtime_ddl_permitido
    if not runtime_ddl_permitido(db):
        return
    from sqlalchemy import text as sqltext
    await db.execute(sqltext("""
        CREATE TABLE IF NOT EXISTS indices_bcb_cache (
            codigo INTEGER NOT NULL,
            data DATE NOT NULL,
            valor NUMERIC(20, 10) NOT NULL,
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (codigo, data)
        )
    """))
    await db.execute(sqltext("""
        CREATE TABLE IF NOT EXISTS indices_bcb_cache_meta (
            codigo INTEGER PRIMARY KEY,
            data_inicial DATE NOT NULL,
            data_final DATE NOT NULL,
            consultado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))


async def _db_persistir(codigo: int, ent: dict) -> None:
    """Grava valores + meta no Postgres (best-effort, nunca lança)."""
    try:
        from sqlalchemy import text as sqltext
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await _ensure_cache_table(db)
            for d, v in ent["valores"].items():
                await db.execute(sqltext("""
                    INSERT INTO indices_bcb_cache (codigo, data, valor, atualizado_em)
                    VALUES (:c, :d, :v, NOW())
                    ON CONFLICT (codigo, data) DO UPDATE
                        SET valor = EXCLUDED.valor, atualizado_em = NOW()
                """), {"c": codigo, "d": d, "v": v})
            await db.execute(sqltext("""
                INSERT INTO indices_bcb_cache_meta
                    (codigo, data_inicial, data_final, consultado_em)
                VALUES (:c, :ini, :fim, NOW())
                ON CONFLICT (codigo) DO UPDATE SET
                    data_inicial = LEAST(indices_bcb_cache_meta.data_inicial, EXCLUDED.data_inicial),
                    data_final = GREATEST(indices_bcb_cache_meta.data_final, EXCLUDED.data_final),
                    consultado_em = NOW()
            """), {"c": codigo, "ini": ent["ini"], "fim": ent["fim"]})
            await db.commit()
    except Exception as exc:
        logger.warning("indices: falha ao persistir cache da série %s: %s", codigo, exc)


def limpar_cache_memoria() -> None:
    """Zera o cache em memória (usado em testes/diagnóstico)."""
    _MEM.clear()


# ── Obtenção de série com cache ───────────────────────────────────────────────

def _cache_cobre(ent: dict | None, cfg: dict, ini: date, fim: date) -> bool:
    if not ent or ent["ini"] > ini or ent["fim"] < fim:
        return False
    # Período que toca o presente pode ganhar valores novos: diárias sempre,
    # mensais quando o fim pedido cai no mês corrente → TTL de 24h.
    toca_presente = (cfg["tipo"] == "diaria" and fim >= date.today() - timedelta(days=3)) \
        or (cfg["tipo"] == "mensal" and fim >= date.today().replace(day=1))
    if toca_presente and _agora() - ent["fetched_at"] >= _TTL_PRESENTE_S:
        return False
    return True


async def obter_serie(indice: str, data_inicial: date, data_final: date
                      ) -> list[tuple[date, Decimal]]:
    """Série SGS no período, ordenada por data. Cache-first; BCB fora do ar
    ⇒ usa o cache existente (warning); sem cache ⇒ BCBIndisponivel."""
    cfg = SERIES.get(indice)
    if not cfg:
        raise ValueError(f"Índice inválido. Use: {list(SERIES)}")
    if data_final < data_inicial:
        raise ValueError("data_final deve ser igual ou posterior à data_inicial")

    codigo = cfg["codigo"]
    ent = _MEM.get(codigo)
    if ent is None:
        ent = await _db_carregar(codigo)
        if ent:
            _MEM[codigo] = ent

    if not _cache_cobre(ent, cfg, data_inicial, data_final):
        try:
            if ent:
                # INVARIANTE de integridade: o range declarado [ini,fim] SEMPRE
                # tem os dados de fato armazenados. Se o pedido é DISJUNTO do
                # envelope já cacheado (deixa um buraco entre os dois intervalos),
                # buscar só [data_inicial, data_final] estenderia [ini,fim] para
                # [min,max] com o MIOLO vazio — e um pedido futuro que caísse no
                # buraco seria declarado "coberto" e voltaria série VAZIA, zerando
                # o fator de correção (fator=1.0) sem erro. Nesses casos buscamos
                # a ENVELOPE INTEIRA no BCB para preencher o buraco.
                disjunto = data_inicial > ent["fim"] or data_final < ent["ini"]
                busca_ini = min(ent["ini"], data_inicial) if disjunto else data_inicial
                busca_fim = max(ent["fim"], data_final) if disjunto else data_final
                novos = await _sgs_buscar(codigo, busca_ini, busca_fim)
                ent["valores"].update(novos)
                ent["ini"] = min(ent["ini"], data_inicial)
                ent["fim"] = max(ent["fim"], data_final)
                ent["fetched_at"] = _agora()
            else:
                novos = await _sgs_buscar(codigo, data_inicial, data_final)
                ent = {"valores": novos, "ini": data_inicial,
                       "fim": data_final, "fetched_at": _agora()}
            _MEM[codigo] = ent
            # _db_persistir grava TODOS os pontos de ent["valores"] (não só os
            # novos) + meta LEAST/GREATEST → o cache DB mantém o mesmo invariante:
            # meta[ini,fim] ⟹ linhas cobrindo [ini,fim] (o envelope acima garante).
            await _db_persistir(codigo, ent)
        except Exception as exc:
            if ent and ent["valores"]:
                logger.warning(
                    "indices: BCB indisponível p/ série %s (%s) — usando cache "
                    "(%d ponto(s), pode estar defasado)",
                    codigo, exc, len(ent["valores"]))
            else:
                raise BCBIndisponivel(
                    f"BCB SGS indisponível para a série {codigo} e sem cache "
                    f"local: {exc}") from exc

    return sorted(
        ((d, v) for d, v in ent["valores"].items()
         if data_inicial <= d <= data_final),
        key=lambda t: t[0],
    )


# ── Funções de negócio (memória de cálculo auditável) ─────────────────────────

_Q8 = Decimal("0.00000001")
_Q2 = Decimal("0.01")


# Séries cuja acumulação é ADITIVA (soma dos percentuais), não capitalização.
# Base metodológica: para débitos da Fazenda sob a EC 113/2021, art. 3º, o
# Manual de Cálculos da Justiça Federal ACUMULA a Selic mensal por SOMA dos
# percentuais mensais (a série SGS 4390 já é "Selic acumulada no mês") — NÃO
# por produto (1+vᵢ/100). Índices de correção monetária (IPCA, INPC, IGP-M...)
# seguem a capitalização multiplicativa normal.
_ACUMULA_POR_SOMA: frozenset[str] = frozenset({"selic_mensal"})


def _compor(serie: list[tuple[date, Decimal]], *, soma: bool = False
            ) -> tuple[Decimal, list[dict]]:
    """Fator acumulado com memória passo a passo.

    - soma=False (default): capitalização composta Π(1 + vᵢ/100) — correta para
      ÍNDICES de correção monetária (IPCA, INPC, IGP-M, taxa legal...).
    - soma=True: acumulação ADITIVA 1 + Σ(vᵢ/100) — Selic mensal (série 4390)
      sob a EC 113/2021, art. 3º (Manual de Cálculos da Justiça Federal).
    """
    fator = Decimal("1")
    memoria = []
    for d, pct in serie:
        parcela = pct / Decimal("100")
        f_mes = Decimal("1") + parcela      # informativo (fator do mês isolado)
        if soma:
            fator += parcela                # 1 + Σ(vᵢ/100)
        else:
            fator *= f_mes                  # Π(1 + vᵢ/100)
        memoria.append({
            "competencia": d.strftime("%m/%Y"),
            "data": d.isoformat(),
            "valor_pct": float(pct),
            "fator_periodo": float(f_mes.quantize(_Q8)),
            "fator_acumulado": float(fator.quantize(_Q8)),
        })
    return fator, memoria


async def fator_correcao(indice: str, data_inicial: date, data_final: date) -> dict:
    """Fator de correção/acumulação MENSAL do índice. Capitalização composta
    (produto de 1+v/100) para índices de correção; acumulação por SOMA para a
    Selic mensal (série 4390) sob a EC 113/2021 (ver _ACUMULA_POR_SOMA)."""
    cfg = SERIES.get(indice)
    if not cfg:
        raise ValueError(f"Índice inválido. Use: {list(SERIES)}")
    if cfg["tipo"] != "mensal":
        raise ValueError(f"'{indice}' é série diária — o fator de correção usa "
                         "séries mensais (ex.: ipca, inpc, igpm, selic_mensal)")
    serie = await obter_serie(indice, data_inicial, data_final)
    # selic_mensal (EC 113/2021) acumula por SOMA; demais índices, por produto.
    fator, memoria = _compor(serie, soma=indice in _ACUMULA_POR_SOMA)
    metodo = "soma dos percentuais (EC 113/2021, art. 3º)" \
        if indice in _ACUMULA_POR_SOMA else "capitalização composta (produto)"
    return {
        "indice": indice,
        "nome": cfg["nome"],
        "codigo_sgs": cfg["codigo"],
        "periodo": f"{data_inicial.isoformat()} → {data_final.isoformat()}",
        "meses_aplicados": len(serie),
        "metodo_acumulacao": metodo,
        "fator": float(fator.quantize(_Q8)),
        "percentual_acumulado": float(((fator - 1) * 100).quantize(Decimal("0.000001"))),
        "memoria_calculo": memoria,
        "fonte": f"Banco Central — SGS série {cfg['codigo']}",
    }


async def atualizar_valor(valor: float, indice: str, data_inicial: date,
                          data_final: date, juros_mora_pct_mes: float = 0.0) -> dict:
    """Atualiza `valor` pelo índice no período (+ juros de mora simples
    opcionais, mesma convenção do bcb_service legado)."""
    if valor <= 0:
        raise ValueError("valor deve ser positivo")
    fc = await fator_correcao(indice, data_inicial, data_final)
    v = Decimal(str(valor))
    fator = Decimal(str(fc["fator"]))
    corrigido = (v * fator).quantize(_Q2, ROUND_HALF_UP)

    juros = Decimal("0")
    if juros_mora_pct_mes > 0:
        juros = (corrigido * Decimal(str(juros_mora_pct_mes)) / Decimal("100")
                 * Decimal(fc["meses_aplicados"])).quantize(_Q2, ROUND_HALF_UP)

    return {
        **fc,
        "valor_original": float(v),
        "valor_corrigido": float(corrigido),
        "juros_mora_pct_mes": juros_mora_pct_mes,
        "juros_mora": float(juros),
        "valor_final": float(corrigido + juros),
        "nota": "Meses conforme divulgação oficial; pro-rata die não aplicado.",
    }


async def juros_taxa_legal(valor: float, data_inicial: date, data_final: date) -> dict:
    """Juros legais pela TAXA LEGAL (Lei 14.905/2024 — CC art. 406): série SGS
    29543 (Selic − IPCA, já calculada pelo BCB) acumulada no período."""
    if valor <= 0:
        raise ValueError("valor deve ser positivo")
    fc = await fator_correcao("taxa_legal", data_inicial, data_final)
    v = Decimal(str(valor))
    juros = (v * (Decimal(str(fc["fator"])) - 1)).quantize(_Q2, ROUND_HALF_UP)
    return {
        **fc,
        "valor_base": float(v),
        "juros": float(juros),
        "valor_com_juros": float(v + juros),
        "base_legal": ("CC art. 406, §§1º-3º (red. Lei 14.905/2024) c/c "
                       "Resolução CMN 5.171/2024 — série SGS 29543"),
    }


async def selic_acumulada(data_inicial: date, data_final: date) -> dict:
    """SELIC acumulada (série 4390) — regra da EC 113/2021, art. 3º: débitos da
    Fazenda Pública corrigidos EXCLUSIVAMENTE pela Selic (sem cumulação com
    correção monetária ou juros)."""
    fc = await fator_correcao("selic_mensal", data_inicial, data_final)
    return {
        **fc,
        "base_legal": "EC 113/2021, art. 3º — Selic exclusiva, vedada cumulação",
    }


# ── Olinda: taxas de juros por modalidade/instituição (revisional) ────────────

async def taxa_juros_modalidade(modalidade: str | None = None,
                                instituicao: str | None = None,
                                top: int = 200) -> dict:
    """Taxas de juros por instituição financeira (série MENSAL do Olinda).
    Busca o mês mais recente e filtra client-side por substring (robusto a
    variações de caixa/acentuação da API — mesmo padrão do abusividade_service).
    """
    ult = await _get_json(OLINDA_TAXA_MENSAL, params={
        "$top": "1", "$orderby": "Mes desc", "$select": "Mes", "$format": "json",
    })
    meses = (ult or {}).get("value") or []
    if not meses:
        raise LookupError("BCB/Olinda sem dados na série mensal de taxas de juros")
    mes_ref = meses[0]["Mes"]

    data = await _get_json(OLINDA_TAXA_MENSAL, params={
        "$filter": f"Mes eq '{mes_ref}'",
        "$select": ("Mes,Modalidade,Posicao,InstituicaoFinanceira,"
                    "TaxaJurosAoMes,TaxaJurosAoAno"),
        "$top": "20000",
        "$format": "json",
    })
    rows = (data or {}).get("value") or []
    if modalidade:
        m = modalidade.casefold()
        rows = [r for r in rows if m in (r.get("Modalidade") or "").casefold()]
    if instituicao:
        i = instituicao.casefold()
        rows = [r for r in rows
                if i in (r.get("InstituicaoFinanceira") or "").casefold()]
    rows = sorted(rows, key=lambda r: (r.get("Posicao") or 0))[:top]
    return {
        "mes_referencia": mes_ref,
        "modalidade": modalidade,
        "instituicao": instituicao,
        "total": len(rows),
        "taxas": rows,
        "fonte": "Banco Central — Olinda taxaJuros (TaxasJurosMensalPorMes)",
    }


async def ptax(data_inicial: date, data_final: date) -> list[dict]:
    """Cotações PTAX (USD) no período — sintaxe OData de function import
    corrigida: parâmetros nomeados @dataInicialCotacao/@dataFinalCotacao com
    datas 'MM-DD-YYYY' entre aspas simples."""
    if data_final < data_inicial:
        raise ValueError("data_final deve ser igual ou posterior à data_inicial")
    fmt = "%m-%d-%Y"
    data = await _get_json(OLINDA_PTAX, params={
        "@dataInicialCotacao": f"'{data_inicial.strftime(fmt)}'",
        "@dataFinalCotacao": f"'{data_final.strftime(fmt)}'",
        "$format": "json",
        "$top": "2000",
    })
    return (data or {}).get("value") or []


# ── Painel: séries suportadas com último valor (cache curto) ──────────────────

_ULTIMOS_TTL_S = 600.0
_ultimos_cache: tuple[float, list[dict]] | None = None


async def listar_series() -> list[dict]:
    """Catálogo das séries suportadas com o último valor divulgado de cada uma
    (concorrente; falha em uma série não derruba as demais)."""
    global _ultimos_cache
    if _ultimos_cache and _agora() - _ultimos_cache[0] < _ULTIMOS_TTL_S:
        return _ultimos_cache[1]

    async def _uma(chave: str, cfg: dict) -> dict:
        info = {"indice": chave, "nome": cfg["nome"], "codigo_sgs": cfg["codigo"],
                "tipo": cfg["tipo"], "ultimo_valor": None, "ultima_data": None}
        try:
            itens = await sgs_ultimos(cfg["codigo"], 1)
            if itens:
                d, v = _parse_item(itens[0])
                info["ultimo_valor"] = float(v)
                info["ultima_data"] = d.isoformat()
        except Exception as exc:
            logger.warning("indices: último valor indisponível p/ série %s: %s",
                           cfg["codigo"], exc)
        return info

    out = list(await asyncio.gather(*(_uma(k, c) for k, c in SERIES.items())))
    if all(i["ultimo_valor"] is not None for i in out):
        _ultimos_cache = (_agora(), out)
    return out
