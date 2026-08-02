"""Smoke das ferramentas jurídicas (Issue #648 — Bloco 4 do plano de lançamento).

Garante por teste HTTP real (TestClient + dependency_overrides, padrão de
tests/test_ia_endpoints_payload.py) que TODAS as ferramentas das áreas
prioritárias respondem com parâmetros plausíveis:

  • ramos.py:   trabalhista-esp (4) · bancario (4) · tributario (7) ·
                transito (3) · civel (7) · consumidor (3) ·
                empresarial (juros-mora, prazos-rj)
  • calculadoras.py: as 8 rotas
  • analise_bancaria.py: /abusividade e /cet

Contrato do smoke:
  • 200 com payload JSON dict → ferramenta funciona;
  • 503 com detail.codigo == "ferramenta_nao_homologada" → indisponibilidade
    CONTROLADA (matriz de homologação) — comportamento correto, não falha;
  • qualquer outro status (500, 422 com entrada válida, 404) → regressão.

Rotas depreciadas do inventário (docs/FERRAMENTAS_JURIDICAS_SEM_INTERFACE.md)
ficam FORA por decisão de escopo, assim como /analise-bancaria/contrato (exige
provedor de IA; a degradação dele tem testes próprios).

Datas fixas em todos os casos — nada de date.today() na entrada. Rotas que
consultam o BCB (correção monetária, abusividade) usam o mesmo mock dos
vizinhos test_liquidacao_trabalhista.py e test_cet_abusividade.py (sem rede).
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import UserRole
from app.routers import analise_bancaria, calculadoras, ramos
from app.services import abusividade_service, bcb_service


class _FakeUser:
    id = "u-smoke-ferramentas"
    role = UserRole.advogado
    full_name = "Advogado Smoke"


async def _fake_db():
    yield None  # nenhuma ferramenta abaixo toca o banco


@pytest.fixture()
def cli() -> TestClient:
    app = FastAPI()
    app.include_router(ramos.router)
    app.include_router(calculadoras.router)
    app.include_router(analise_bancaria.router)
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    app.dependency_overrides[get_db] = _fake_db
    return TestClient(app)


def _assert_smoke(r):
    """200 + dict, ou 503 controlado da matriz de homologação."""
    if r.status_code == 503:
        detail = r.json().get("detail")
        assert isinstance(detail, dict) and detail.get("codigo") == \
            "ferramenta_nao_homologada", f"503 NÃO controlado: {r.text}"
        return
    assert r.status_code == 200, f"{r.request.url} → {r.status_code}: {r.text}"
    body = r.json()
    assert isinstance(body, dict), f"payload não é dict: {type(body)}"
    assert body, "payload vazio"


# ══════════════════════════════════════════════════════════════════════════
# GET /<área>/ferramentas/* — parâmetros plausíveis, datas fixas
# ══════════════════════════════════════════════════════════════════════════
CASOS_GET = [
    # ── trabalhista-esp (4) ──────────────────────────────────────────────
    ("/trabalhista-esp/ferramentas/prazos",
     {"data_ciencia": "2026-03-10", "tipo_prazo": "todos"}),
    ("/trabalhista-esp/ferramentas/prescricao-trabalhista",
     {"data_extincao_contrato": "2024-05-10", "data_ajuizamento": "2026-03-10"}),
    ("/trabalhista-esp/ferramentas/deposito-recursal",
     {"valor_condenacao": 100_000, "data_referencia": "2026-07-01"}),
    ("/trabalhista-esp/ferramentas/verbas-rescisorias",
     {"salario": 3_000, "data_admissao": "2022-01-10", "data_demissao": "2026-01-09",
      "tipo_rescisao": "sem_justa_causa", "saldo_fgts": 10_000,
      "aviso_previo": "indenizado"}),
    # ── bancario (4) ─────────────────────────────────────────────────────
    ("/bancario/ferramentas/analise-juros",
     {"taxa_mensal_contratada": 8.0, "taxa_mensal_referencia": 4.0,
      "valor_contratado": 10_000}),
    ("/bancario/ferramentas/busca-apreensao",
     {"data_notificacao": "2026-03-02", "valor_divida": 25_000,
      "bem_descricao": "Veiculo GM Onix 2020"}),
    ("/bancario/ferramentas/juros-abusivos",
     {"taxa_contratada_mensal_pct": 8.0, "taxa_media_bacen_mensal_pct": 4.0}),
    ("/bancario/ferramentas/superendividamento",
     {"renda_mensal": 3_000, "total_parcelas_mes": 1_800}),
    # ── tributario (7) ───────────────────────────────────────────────────
    ("/tributario/ferramentas/auto-infracao-prazos",
     {"data_ciencia": "2026-03-02", "valor_multa": 10_000, "esfera": "federal"}),
    ("/tributario/ferramentas/multa-mora",
     {"ente": "federal", "valor_tributo": 10_000, "dias_atraso": 90}),
    ("/tributario/ferramentas/parcelamento",
     {"valor_total_debito": 120_000, "parcelas": 60, "modalidade": "pert"}),
    ("/tributario/ferramentas/prescricao-decadencia",
     {"data_fato_gerador": "2024-03-10", "tipo": "homologacao"}),
    ("/tributario/ferramentas/reforma-tributaria",
     {"receita_bruta_anual": 1_000_000, "regime_atual": "lucro_presumido",
      "atividade": "servicos", "ano_analise": "2027"}),
    ("/tributario/ferramentas/regime-tributario",
     {"receita_bruta_anual": 1_000_000, "lucro_estimado_pct": 20.0,
      "atividade": "servicos"}),
    ("/tributario/ferramentas/simples-nacional",
     {"receita_bruta_12m": 300_000, "anexo": "III"}),
    # ── transito (3) ─────────────────────────────────────────────────────
    ("/transito/ferramentas/pontuacao-cnh",
     {"pontos_total": 25, "qtd_gravissimas": 1,
      "exerce_atividade_remunerada": "nao"}),
    ("/transito/ferramentas/prazos-recurso",
     {"fase": "defesa_previa", "data_notificacao_autuacao": "2026-03-02",
      "valor_multa": 293.47}),
    ("/transito/ferramentas/valor-multa",
     {"gravidade": "gravissima", "multiplicador": 3}),
    # ── civel (7) ────────────────────────────────────────────────────────
    ("/civel/ferramentas/alimentos-calcular",
     {"salario_devedor": 5_000, "percentual": 30, "filhos": 2}),
    ("/civel/ferramentas/calculo-dano-moral",
     {"tipo_caso": "negativacao_indevida", "salarios_minimos_pedido": 10}),
    ("/civel/ferramentas/partilha-divorcio",
     {"regime_bens": "comunhao_parcial", "data_casamento": "2015-05-10",
      "data_separacao_fatos": "2025-06-01"}),
    ("/civel/ferramentas/prazos-contestacao",
     {"rito": "comum", "marco": "juntada_citacao", "data_marco": "2026-03-02"}),
    ("/civel/ferramentas/prescricao-consumidor",
     {"data_fato": "2024-03-10", "tipo_vicio": "fato_produto"}),
    ("/civel/ferramentas/rescisao-locacao",
     {"data_inicio": "2025-01-10", "data_rescisao_pretendida": "2026-01-10",
      "valor_aluguel": 2_000, "tipo_locacao": "residencial",
      "quem_rescinde": "locatario", "prazo_contrato_meses": 30,
      "multa_contratual_alugueis": 3.0}),
    ("/civel/ferramentas/usucapiao-verificar",
     {"tipo": "extraordinaria", "anos_posse": 16, "posse_mansa": True}),
    # ── consumidor (3) ───────────────────────────────────────────────────
    ("/consumidor/ferramentas/devolucao-dobro",
     {"valor_cobrado_indevidamente": 500, "houve_pagamento": "sim",
      "cobranca_contraria_boa_fe_objetiva": "sim", "engano_justificavel": "nao"}),
    ("/consumidor/ferramentas/negativacao-indevida",
     {"existe_inscricao_anterior": "nao"}),
    ("/consumidor/ferramentas/prazos-cdc",
     {"pretensao": "vicio_oculto", "data_marco": "2026-02-02",
      "bem_duravel": "sim"}),
    # ── empresarial (2 do escopo) ────────────────────────────────────────
    ("/empresarial/ferramentas/juros-mora",
     {"regime": "legal", "valor_principal": 10_000,
      "data_inicio_mora": "2025-01-01", "data_fim": "2025-12-31",
      "selic_acumulada_percent": 10.0, "ipca_acumulado_percent": 4.0}),
    ("/empresarial/ferramentas/prazos-rj",
     {"data_publicacao_deferimento": "2026-02-02",
      "data_deferimento": "2026-01-30", "data_concessao": "2026-10-01"}),
    # ── calculadoras (GETs sem rede) ─────────────────────────────────────
    ("/calculadoras/tipos-rescisao", {}),
    ("/calculadoras/inss", {"salario": 3_000}),
    ("/calculadoras/irrf", {"rendimento": 5_000, "inss": 550, "dependentes": 1}),
    ("/calculadoras/prescricao/tipos", {}),
]


@pytest.mark.parametrize("path,params", CASOS_GET, ids=[c[0] for c in CASOS_GET])
def test_ferramenta_get_responde(cli, path, params):
    _assert_smoke(cli.get(path, params=params))


def test_calculadora_custas_tjmg_fail_closed_503(cli):
    """Degradação CONTROLADA por desenho (não é regressão): a tabela de faixas
    do Anexo I da Lei 14.939/2003 não está carregada de propósito — o serviço
    falha fechado (503) em vez de inventar valor de custas. A carga da tabela
    oficial é decisão jurídica (fonte oficial do TJMG), fora do smoke; ver
    test_calc_custas.py::test_analisar_sem_tabela_oficial_retorna_503."""
    r = cli.get("/calculadoras/custas-tjmg", params={"valor_causa": 50_000})
    assert r.status_code == 503, r.text
    assert "FAIXAS_CUSTAS" in r.json()["detail"]


# ══════════════════════════════════════════════════════════════════════════
# calculadoras — POSTs
# ══════════════════════════════════════════════════════════════════════════
def test_calculadora_rescisao_trabalhista(cli):
    r = cli.post("/calculadoras/trabalhista/rescisao", json={
        "salario": 3_000, "admissao": "2022-01-10", "demissao": "2026-01-09",
        "tipo": "sem_justa_causa", "aviso_indenizado": True,
        "saldo_fgts": 10_000, "dependentes": 1,
    })
    _assert_smoke(r)


def test_calculadora_prescricao(cli):
    r = cli.post("/calculadoras/prescricao", json={
        "chave": "reparacao_civil", "termo_inicial": "2024-03-10",
    })
    _assert_smoke(r)


def test_calculadora_correcao_monetaria(cli, monkeypatch):
    """BCB mockado (mesmo padrão de test_liquidacao_trabalhista) — sem rede."""
    async def fake(valor, data_inicial, data_final, indice="ipca",
                   juros_mora_pct_mes=0.0):
        return {"fator_correcao": 1.10, "valor_corrigido": valor * 1.10,
                "meses_aplicados": 24, "fonte": "bcb", "memoria_calculo": []}

    monkeypatch.setattr(bcb_service, "atualizar_valor", fake)
    r = cli.post("/calculadoras/correcao-monetaria", json={
        "valor": 10_000, "data_inicial": "2024-01-10",
        "data_final": "2026-01-10", "indice": "ipca", "juros_mora_pct_mes": 1.0,
    })
    _assert_smoke(r)


# ══════════════════════════════════════════════════════════════════════════
# analise-bancaria — /abusividade (Olinda mockado) e /cet (determinístico)
# ══════════════════════════════════════════════════════════════════════════
def test_analise_bancaria_abusividade(cli, monkeypatch):
    """Olinda/BCB mockado (mesmo padrão de test_cet_abusividade) — sem rede."""
    async def fake_olinda(params: dict) -> list:
        if params.get("$select") == "InicioPeriodo":
            return [{"InicioPeriodo": "2024-03-01"}]
        return [{"Modalidade": "Crédito pessoal não-consignado - Pré-fixado",
                 "Segmento": "PESSOA FÍSICA",
                 "TaxaJurosAoMes": t, "TaxaJurosAoAno": t * 14}
                for t in (3.0, 4.0, 5.0)]

    monkeypatch.setattr(abusividade_service, "olinda_get", fake_olinda)
    r = cli.post("/analise-bancaria/abusividade", json={
        "taxa_contrato_am_pct": 8.0, "modalidade": "credito_pessoal",
        "data_contrato": "2024-03-10", "valor_financiado": 10_000,
        "n_parcelas": 12,
    })
    _assert_smoke(r)
    body = r.json()
    assert body["veredito"] and body["taxa_media"] is not None


def test_analise_bancaria_cet(cli):
    r = cli.post("/analise-bancaria/cet", json={
        "valor_liberado": 10_000, "data_liberacao": "2026-01-10",
        "n_parcelas": 12, "valor_parcela": 1_000,
        "primeiro_vencimento": "2026-02-10",
        "tarifas_incluidas": 350, "iof": 120, "cet_informado_aa_pct": 20.0,
    })
    _assert_smoke(r)
    assert "cet_anual_pct" in r.json()
