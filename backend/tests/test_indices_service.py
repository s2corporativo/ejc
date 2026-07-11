"""Índices oficiais BCB (indices_service) — Bloco 1 das APIs públicas.

Cobertura (tudo SEM rede — httpx mockado na indireção _get_json):
  • paginação por década do SGS (janela máx. 10 anos por chamada);
  • fator de correção com valores conhecidos (IPCA 2 meses);
  • taxa legal (série 29543) acumulada;
  • cache hit: segunda chamada não vai ao BCB;
  • BCB fora do ar → serve cache e loga warning;
  • Selic EC 113 (série 4390) e regras do endpoint /indices/atualizar-valor;
  • sintaxe OData corrigida do PTAX (function import com @parametros).
"""
from datetime import date, timedelta

import pytest

from app.services import indices_service as isvc


@pytest.fixture(autouse=True)
def _isolado(monkeypatch):
    """Sem rede, sem banco: cache em memória zerado e persistência no-op."""
    isvc.limpar_cache_memoria()
    isvc._ultimos_cache = None

    async def _sem_db_carregar(codigo):
        return None

    async def _sem_db_persistir(codigo, ent):
        return None

    monkeypatch.setattr(isvc, "_db_carregar", _sem_db_carregar)
    monkeypatch.setattr(isvc, "_db_persistir", _sem_db_persistir)
    yield
    isvc.limpar_cache_memoria()


def _mock_sgs(monkeypatch, valores_por_data: dict):
    """Mocka _get_json devolvendo os pontos da série que caem na janela
    pedida (dataInicial/dataFinal). Registra cada chamada."""
    chamadas = []

    async def fake(url, params=None):
        chamadas.append({"url": url, "params": dict(params or {})})
        if "/dados/ultimos/" in url:
            if not valores_por_data:
                return []
            d = max(valores_por_data)
            return [{"data": d.strftime("%d/%m/%Y"),
                     "valor": str(valores_por_data[d])}]
        ini = date(*reversed([int(x) for x in params["dataInicial"].split("/")]))
        fim = date(*reversed([int(x) for x in params["dataFinal"].split("/")]))
        return [{"data": d.strftime("%d/%m/%Y"), "valor": str(v)}
                for d, v in sorted(valores_por_data.items()) if ini <= d <= fim]

    monkeypatch.setattr(isvc, "_get_json", fake)
    return chamadas


# ══════════════════════════════════════════════════════════════════════════
# SGS: paginação por década
# ══════════════════════════════════════════════════════════════════════════
async def test_paginacao_por_decada(monkeypatch):
    # um ponto por ano de 2001 a 2023 — período de 23 anos exige ≥3 janelas
    valores = {date(a, 6, 1): "0.5" for a in range(2001, 2024)}
    chamadas = _mock_sgs(monkeypatch, valores)

    serie = await isvc.obter_serie("ipca", date(2001, 1, 1), date(2023, 12, 31))

    assert len(serie) == 23                      # nada perdido entre janelas
    assert len(chamadas) >= 3                    # 23 anos ÷ 10 anos/janela
    for c in chamadas:
        ini = date(*reversed([int(x) for x in c["params"]["dataInicial"].split("/")]))
        fim = date(*reversed([int(x) for x in c["params"]["dataFinal"].split("/")]))
        assert (fim - ini).days <= 3600          # janela ≤ 10 anos
    # janelas contíguas: 2ª começa no dia seguinte ao fim da 1ª
    fim1 = date(*reversed([int(x) for x in chamadas[0]["params"]["dataFinal"].split("/")]))
    ini2 = date(*reversed([int(x) for x in chamadas[1]["params"]["dataInicial"].split("/")]))
    assert ini2 == fim1 + timedelta(days=1)


# ══════════════════════════════════════════════════════════════════════════
# Fator de correção e atualização — valores conferíveis à mão
# ══════════════════════════════════════════════════════════════════════════
async def test_fator_correcao_ipca_dois_meses(monkeypatch):
    _mock_sgs(monkeypatch, {date(2024, 1, 1): "0.5", date(2024, 2, 1): "1.0"})
    fc = await isvc.fator_correcao("ipca", date(2024, 1, 1), date(2024, 2, 28))
    # (1 + 0,5%) × (1 + 1,0%) = 1,01505
    assert fc["fator"] == pytest.approx(1.01505)
    assert fc["meses_aplicados"] == 2
    assert fc["codigo_sgs"] == 433
    assert [m["valor_pct"] for m in fc["memoria_calculo"]] == [0.5, 1.0]
    assert fc["memoria_calculo"][-1]["fator_acumulado"] == pytest.approx(1.01505)


async def test_atualizar_valor_com_memoria(monkeypatch):
    _mock_sgs(monkeypatch, {date(2024, 1, 1): "0.5", date(2024, 2, 1): "1.0"})
    r = await isvc.atualizar_valor(1000.0, "ipca", date(2024, 1, 1), date(2024, 2, 28))
    assert r["valor_corrigido"] == 1015.05
    assert r["valor_final"] == 1015.05           # sem juros de mora
    assert len(r["memoria_calculo"]) == 2


async def test_serie_diaria_recusada_no_fator(monkeypatch):
    _mock_sgs(monkeypatch, {})
    with pytest.raises(ValueError):
        await isvc.fator_correcao("selic_diaria", date(2024, 1, 1), date(2024, 2, 1))
    with pytest.raises(ValueError):
        await isvc.fator_correcao("inexistente", date(2024, 1, 1), date(2024, 2, 1))


# ══════════════════════════════════════════════════════════════════════════
# Taxa Legal (Lei 14.905/2024, série 29543) e Selic EC 113 (4390)
# ══════════════════════════════════════════════════════════════════════════
async def test_juros_taxa_legal_acumulada(monkeypatch):
    chamadas = _mock_sgs(monkeypatch, {date(2024, 9, 1): "1.0", date(2024, 10, 1): "1.0"})
    r = await isvc.juros_taxa_legal(1000.0, date(2024, 9, 1), date(2024, 10, 31))
    # fator (1,01)² = 1,0201 → juros = 1000 × 0,0201 = 20,10
    assert r["fator"] == pytest.approx(1.0201)
    assert r["juros"] == 20.10
    assert r["valor_com_juros"] == 1020.10
    assert "14.905" in r["base_legal"]
    assert all("29543" in c["url"] for c in chamadas)   # série certa


async def test_selic_acumulada_ec113(monkeypatch):
    chamadas = _mock_sgs(monkeypatch, {date(2024, 1, 1): "1.0"})
    r = await isvc.selic_acumulada(date(2024, 1, 1), date(2024, 1, 31))
    assert r["fator"] == pytest.approx(1.01)
    assert "EC 113" in r["base_legal"]
    assert all("4390" in c["url"] for c in chamadas)


# ══════════════════════════════════════════════════════════════════════════
# Cache
# ══════════════════════════════════════════════════════════════════════════
async def test_cache_hit_sem_nova_chamada(monkeypatch):
    # período todo no passado (mensal) → coberto ⇒ sem TTL
    chamadas = _mock_sgs(monkeypatch, {date(2020, 1, 1): "0.5", date(2020, 2, 1): "1.0"})
    s1 = await isvc.obter_serie("ipca", date(2020, 1, 1), date(2020, 2, 28))
    n_apos_primeira = len(chamadas)
    s2 = await isvc.obter_serie("ipca", date(2020, 1, 1), date(2020, 2, 28))
    assert len(chamadas) == n_apos_primeira      # ZERO chamadas novas
    assert s1 == s2
    # sub-período também é servido do cache
    await isvc.obter_serie("ipca", date(2020, 2, 1), date(2020, 2, 28))
    assert len(chamadas) == n_apos_primeira


async def test_bcb_fora_serve_cache_com_warning(monkeypatch, caplog):
    hoje = date.today()
    m_atual = hoje.replace(day=1)
    _mock_sgs(monkeypatch, {m_atual: "0.7"})
    await isvc.obter_serie("taxa_legal", m_atual, hoje)   # popula o cache

    # TTL vencido (período toca o presente) + BCB fora do ar
    codigo = isvc.SERIES["taxa_legal"]["codigo"]
    isvc._MEM[codigo]["fetched_at"] -= isvc._TTL_PRESENTE_S + 1

    async def caiu(url, params=None):
        raise RuntimeError("BCB fora do ar")

    monkeypatch.setattr(isvc, "_get_json", caiu)
    with caplog.at_level("WARNING", logger="ejc.indices"):
        serie = await isvc.obter_serie("taxa_legal", m_atual, hoje)
    assert serie and float(serie[0][1]) == 0.7            # cache serviu
    assert any("usando cache" in r.message for r in caplog.records)


async def test_bcb_fora_sem_cache_levanta(monkeypatch):
    async def caiu(url, params=None):
        raise RuntimeError("BCB fora do ar")

    monkeypatch.setattr(isvc, "_get_json", caiu)
    with pytest.raises(isvc.BCBIndisponivel):
        await isvc.obter_serie("ipca", date(2024, 1, 1), date(2024, 2, 1))


# ══════════════════════════════════════════════════════════════════════════
# Olinda: PTAX (sintaxe OData corrigida) e taxa de juros
# ══════════════════════════════════════════════════════════════════════════
async def test_ptax_sintaxe_odata_function_import(monkeypatch):
    chamadas = []

    async def fake(url, params=None):
        chamadas.append({"url": url, "params": dict(params or {})})
        return {"value": [{"cotacaoCompra": 5.43, "cotacaoVenda": 5.44,
                           "dataHoraCotacao": "2026-01-15 13:09:02.871"}]}

    monkeypatch.setattr(isvc, "_get_json", fake)
    cotacoes = await isvc.ptax(date(2026, 1, 15), date(2026, 1, 16))
    assert len(cotacoes) == 1
    c = chamadas[0]
    # function import com parâmetros NOMEADOS (probe tomou 400 sem isto)
    assert ("CotacaoDolarPeriodo(dataInicialCotacao=@dataInicialCotacao,"
            "dataFinalCotacao=@dataFinalCotacao)") in c["url"]
    # datas MM-DD-YYYY entre aspas simples
    assert c["params"]["@dataInicialCotacao"] == "'01-15-2026'"
    assert c["params"]["@dataFinalCotacao"] == "'01-16-2026'"
    assert c["params"]["$format"] == "json"


async def test_taxa_juros_filtra_modalidade_e_instituicao(monkeypatch):
    rows = [
        {"Mes": "2026-05", "Modalidade": "CRÉDITO PESSOAL NÃO-CONSIGNADO - PRÉ-FIXADO",
         "InstituicaoFinanceira": "BANCO ALFA S.A.", "Posicao": 2,
         "TaxaJurosAoMes": 5.1, "TaxaJurosAoAno": 81.6},
        {"Mes": "2026-05", "Modalidade": "CRÉDITO PESSOAL NÃO-CONSIGNADO - PRÉ-FIXADO",
         "InstituicaoFinanceira": "BANCO BETA S.A.", "Posicao": 1,
         "TaxaJurosAoMes": 3.2, "TaxaJurosAoAno": 45.9},
        {"Mes": "2026-05", "Modalidade": "AQUISIÇÃO DE VEÍCULOS - PRÉ-FIXADO",
         "InstituicaoFinanceira": "BANCO ALFA S.A.", "Posicao": 3,
         "TaxaJurosAoMes": 1.9, "TaxaJurosAoAno": 25.3},
    ]

    async def fake(url, params=None):
        if params and params.get("$top") == "1":
            return {"value": [{"Mes": "2026-05"}]}
        return {"value": rows}

    monkeypatch.setattr(isvc, "_get_json", fake)
    r = await isvc.taxa_juros_modalidade(modalidade="crédito pessoal")
    assert r["total"] == 2
    assert r["taxas"][0]["InstituicaoFinanceira"] == "BANCO BETA S.A."  # Posicao
    r2 = await isvc.taxa_juros_modalidade(modalidade="crédito pessoal",
                                          instituicao="alfa")
    assert r2["total"] == 1 and "ALFA" in r2["taxas"][0]["InstituicaoFinanceira"]


# ══════════════════════════════════════════════════════════════════════════
# Router: regras do POST /indices/atualizar-valor
# ══════════════════════════════════════════════════════════════════════════
async def test_endpoint_regras(monkeypatch):
    from app.routers import indices as r_ind

    _mock_sgs(monkeypatch, {date(2024, 1, 1): "1.0", date(2024, 2, 1): "1.0"})
    base = dict(valor=1000.0, data_inicial=date(2024, 1, 1),
                data_final=date(2024, 2, 28))

    # correcao pura: 1000 × 1,01² = 1020,10
    out = await r_ind.atualizar_valor(
        r_ind.AtualizarValorIn(indice="ipca", regra="correcao", **base), cu=None)
    assert out["valor_final"] == 1020.10
    assert len(out["etapas"]) == 1

    # correcao + taxa legal: juros sobre o valor CORRIGIDO
    out2 = await r_ind.atualizar_valor(
        r_ind.AtualizarValorIn(indice="ipca", regra="correcao_mais_taxa_legal",
                               **base), cu=None)
    assert out2["valor_final"] == pytest.approx(1020.10 * 1.0201, abs=0.01)
    assert len(out2["etapas"]) == 2
    assert "14.905" in out2["etapas"][1]["base_legal"]

    # selic_ec113: Selic exclusiva (série 4390), sem cumulação
    out3 = await r_ind.atualizar_valor(
        r_ind.AtualizarValorIn(indice="ipca", regra="selic_ec113", **base), cu=None)
    assert out3["valor_final"] == 1020.10
    assert "EC 113" in out3["etapas"][0]["base_legal"]


async def test_endpoint_gate_flag_desligada(monkeypatch):
    from fastapi import HTTPException
    from app.core.config import get_settings
    from app.routers import indices as r_ind

    monkeypatch.setattr(get_settings(), "INDICES_BCB_ENABLED", False)
    with pytest.raises(HTTPException) as exc:
        await r_ind.series(cu=None)
    assert exc.value.status_code == 503
