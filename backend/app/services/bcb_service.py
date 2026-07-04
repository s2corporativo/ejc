# ── app/services/bcb_service.py ──────────────────────────────────────────────
# Atualização monetária via API SGS do Banco Central (pública, sem chave).
# Séries mensais: IPCA 433 · IPCA-E 10764 · INPC 188 · SELIC mensal 4390 · TR 226
# Cálculo: fator composto dos índices + juros de mora simples (opcional).
from __future__ import annotations
import asyncio
import logging
import time
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

import httpx

logger = logging.getLogger("ejc.bcb")

SERIES = {
    "ipca":   {"codigo": 433,   "nome": "IPCA (IBGE)"},
    "ipca_e": {"codigo": 10764, "nome": "IPCA-E (IBGE)"},
    "inpc":   {"codigo": 188,   "nome": "INPC (IBGE)"},
    "selic":  {"codigo": 4390,  "nome": "SELIC acumulada no mês"},
    "tr":     {"codigo": 226,   "nome": "TR"},
}

_cache: dict[tuple, list] = {}   # cache em memória por (codigo, ini, fim)

# ── Painel de taxas "ao vivo" (card taxas-bacen do ramo Bancário) ─────────────
# Séries SGS oficiais: SELIC meta 432 (% a.a.) · CDI 12 (% a.d.) ·
# TR 226 (% a.m.) · IPCA-15 7478 (% a.m.). Shape consumido por
# frontend/src/pages/ramos/RamoBase.tsx (TaxasBacenView).
SERIES_PAINEL = {
    "selic_meta_aa":  {"codigo": 432,  "nome": "Meta SELIC (% a.a.)"},
    "cdi_diario":     {"codigo": 12,   "nome": "CDI (% a.d.)"},
    "tr_mensal":      {"codigo": 226,  "nome": "TR (% a.m.)"},
    "ipca_15_mensal": {"codigo": 7478, "nome": "IPCA-15 (% a.m.)"},
}


# Cache do painel (auditoria P3): as séries mudam no máximo 1x/dia — sem o
# cache cada request faria 4 HTTPs externos e arriscaria throttling do BCB.
_PAINEL_TTL_S = 600.0
_painel_cache: tuple[float, dict] | None = None


async def painel_taxas() -> dict:
    """Último valor divulgado de cada série do painel (concorrente + cache).
    Falha em uma série não derruba as demais (valor=None ⇒ 'indisponível')."""
    global _painel_cache
    agora = time.monotonic()
    if _painel_cache and agora - _painel_cache[0] < _PAINEL_TTL_S:
        return _painel_cache[1]

    async def _uma(cli: httpx.AsyncClient, chave: str, cfg: dict) -> tuple[str, dict]:
        info: dict = {"serie_sgs": cfg["codigo"], "nome": cfg["nome"],
                      "valor": None, "data": None}
        try:
            r = await cli.get(
                f"https://api.bcb.gov.br/dados/serie/bcdata.sgs."
                f"{cfg['codigo']}/dados/ultimos/1?formato=json"
            )
            r.raise_for_status()
            item = r.json()[0]
            info["valor"] = float(str(item["valor"]).replace(",", "."))
            info["data"] = item["data"]
        except Exception as e:      # rede/formato — degrada graciosamente
            logger.warning("painel_taxas: série %s indisponível: %s",
                           cfg["codigo"], e)
        return chave, info

    async with httpx.AsyncClient(timeout=10) as cli:
        pares = await asyncio.gather(*(
            _uma(cli, chave, cfg) for chave, cfg in SERIES_PAINEL.items()
        ))
    taxas = dict(pares)
    # Só cacheia se TODAS as séries vieram (falha parcial deve re-tentar logo).
    if all(v["valor"] is not None for v in taxas.values()):
        _painel_cache = (agora, taxas)
    return taxas


async def _buscar_serie(codigo: int, ini: date, fim: date) -> list[dict]:
    key = (codigo, ini.isoformat(), fim.isoformat())
    if key in _cache:
        return _cache[key]
    url = (
        f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
        f"?formato=json&dataInicial={ini.strftime('%d/%m/%Y')}"
        f"&dataFinal={fim.strftime('%d/%m/%Y')}"
    )
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(url)
        r.raise_for_status()
        data = r.json()
    _cache[key] = data
    return data


async def atualizar_valor(
    valor: float, data_inicial: date, data_final: date,
    indice: str = "ipca", juros_mora_pct_mes: float = 0.0,
) -> dict:
    """
    Corrige `valor` pelo índice no período + juros simples opcionais.
    Retorna memória de cálculo mês a mês (auditável).
    Convenção: aplica o índice de cada mês cheio entre as datas (pro-rata
    não aplicado — informado no resultado).
    """
    if indice not in SERIES:
        raise ValueError(f"Índice inválido. Use: {list(SERIES)}")
    if data_final <= data_inicial:
        raise ValueError("data_final deve ser posterior à data_inicial")

    serie = await _buscar_serie(SERIES[indice]["codigo"], data_inicial, data_final)

    v = Decimal(str(valor))
    fator = Decimal("1")
    memoria = []
    for item in serie:
        pct = Decimal(item["valor"].replace(",", "."))
        f_mes = Decimal("1") + pct / Decimal("100")
        fator *= f_mes
        memoria.append({
            "competencia": item["data"], "indice_pct": float(pct),
            "fator_acumulado": float(fator.quantize(Decimal("0.00000001"))),
        })

    corrigido = (v * fator).quantize(Decimal("0.01"), ROUND_HALF_UP)

    # Juros de mora simples (ex.: 1% a.m. — CC art. 406 c/c CTN 161 §1º)
    meses = len(serie)
    juros = Decimal("0")
    if juros_mora_pct_mes > 0:
        juros = (corrigido * Decimal(str(juros_mora_pct_mes)) / Decimal("100")
                 * Decimal(meses)).quantize(Decimal("0.01"), ROUND_HALF_UP)

    return {
        "valor_original": float(v),
        "indice": SERIES[indice]["nome"],
        "periodo": f"{data_inicial.isoformat()} → {data_final.isoformat()}",
        "meses_aplicados": meses,
        "fator_correcao": float(fator.quantize(Decimal("0.00000001"))),
        "valor_corrigido": float(corrigido),
        "juros_mora_pct_mes": juros_mora_pct_mes,
        "juros_mora": float(juros),
        "valor_final": float(corrigido + juros),
        "memoria_calculo": memoria,
        "fonte": f"Banco Central — SGS série {SERIES[indice]['codigo']}",
        "nota": "Meses conforme divulgação oficial do índice; pro-rata die não aplicado.",
    }
