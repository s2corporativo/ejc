"""Onda 2 — Fase A: correção jurídica profunda (empresarial, cível/JEC, penal).

Padrão dos vizinhos: chamada direta às funções (sem harness de banco). Para cada
ferramenta corrigida: caso feliz, entrada inválida (422), marco ausente (422),
exceção legal e — onde couber — ano bissexto. Toda resposta corrigida carrega
`fontes`, `vigencia_regra` e `versao_regra`.
"""
from datetime import date

import pytest
from fastapi import HTTPException

from app.routers import ramos
from app.services.deadline_calculator import prazo_dias_uteis


def _assert_metadados_regra(r: dict):
    assert r["fontes"] and isinstance(r["fontes"], list)
    assert r["vigencia_regra"]
    assert r["versao_regra"] == "2026-07"
    assert "MINUTA" in r["aviso"]


def _assert_sem_selo(r: dict):
    assert "homologada" not in r
    assert "aviso_homologacao" not in r


# ══════════════════════════════════════════════════════════════════════════
# 1. /empresarial/ferramentas/prazos-rj (Lei 11.101/2005, red. Lei 14.112/2020)
# ══════════════════════════════════════════════════════════════════════════
async def test_prazos_rj_marcos_completos():
    r = await ramos.emp_prazos_rj(
        data_publicacao_deferimento=date(2026, 2, 2),
        data_deferimento=date(2026, 1, 30),
        data_concessao=date(2026, 10, 1),
        cu=None,
    )
    eventos = {m["evento"]: m for m in r["marcos"]}
    # Plano: 60 dias da PUBLICAÇÃO do deferimento (art. 53)
    assert eventos["Apresentação do plano de recuperação"]["data"] == date(2026, 4, 3)
    # Stay: 180 dias do deferimento, prorrogável 1x por igual período (art. 6º §4º)
    stay = eventos["Fim do stay period (suspensão das execuções)"]
    assert stay["data"] == date(2026, 7, 29)
    assert stay["data_com_prorrogacao_maxima"] == date(2027, 1, 25)
    # AGC: até 150 dias do deferimento (art. 56 §1º)
    agc = eventos["AGC para deliberar sobre o plano (se houver objeção de credor)"]
    assert agc["data"] == date(2026, 6, 29)
    # Supervisão: 2 anos da CONCESSÃO (art. 61)
    assert eventos["Fim da supervisão judicial"]["data"] == date(2028, 10, 1)
    assert r["marcos_nao_calculados"] == []
    _assert_metadados_regra(r)
    _assert_sem_selo(r)   # desbloqueada e fora da matriz


async def test_prazos_rj_calcula_so_marcos_com_input():
    r = await ramos.emp_prazos_rj(data_deferimento=date(2026, 1, 30), cu=None)
    eventos = [m["evento"] for m in r["marcos"]]
    assert len(eventos) == 2   # stay + AGC
    assert any("art. 53" in x for x in r["marcos_nao_calculados"])
    assert any("art. 61" in x for x in r["marcos_nao_calculados"])


async def test_prazos_rj_sem_nenhum_marco_422():
    with pytest.raises(HTTPException) as e:
        await ramos.emp_prazos_rj(cu=None)
    assert e.value.status_code == 422
    assert "termo inicial" in e.value.detail


async def test_prazos_rj_supervisao_bissexto():
    # Concessão em 29/02/2024 + 2 anos → 2026 não é bissexto → 28/02/2026.
    r = await ramos.emp_prazos_rj(data_concessao=date(2024, 2, 29), cu=None)
    sup = [m for m in r["marcos"] if "supervisão" in m["evento"]][0]
    assert sup["data"] == date(2026, 2, 28)


# ══════════════════════════════════════════════════════════════════════════
# 2. /empresarial/ferramentas/juros-mora (CC art. 406, red. Lei 14.905/2024)
# ══════════════════════════════════════════════════════════════════════════
async def test_juros_mora_legal_selic_menos_ipca():
    r = await ramos.empresarial_juros_mora(
        regime="legal", valor_principal=1_000.0,
        data_inicio_mora=date(2025, 1, 1), data_fim=date(2025, 12, 31),
        selic_acumulada_percent=10.0, ipca_acumulado_percent=4.0, cu=None,
    )
    assert len(r["componentes"]) == 1
    assert r["juros_mora_total"] == 60.0          # 1000 × (10% − 4%)
    assert r["total_devido"] == 1_060.0
    _assert_metadados_regra(r)
    _assert_sem_selo(r)


async def test_juros_mora_legal_taxa_negativa_vira_zero():
    # Exceção legal do art. 406 §3º: Selic − IPCA negativo → taxa ZERO.
    r = await ramos.empresarial_juros_mora(
        regime="legal", valor_principal=1_000.0,
        data_inicio_mora=date(2025, 1, 1), data_fim=date(2025, 12, 31),
        selic_acumulada_percent=3.0, ipca_acumulado_percent=5.0, cu=None,
    )
    assert r["juros_mora_total"] == 0.0
    assert r["componentes"][0]["taxa_zerada_art_406_p3"] is True


async def test_juros_mora_legal_sem_indices_422_orientando():
    with pytest.raises(HTTPException) as e:
        await ramos.empresarial_juros_mora(
            regime="legal", valor_principal=1_000.0,
            data_inicio_mora=date(2025, 1, 1), cu=None,
        )
    assert e.value.status_code == 422
    assert "BCB" in e.value.detail and "IBGE" in e.value.detail


async def test_juros_mora_inicio_antes_da_vigencia_exige_opcao():
    with pytest.raises(HTTPException) as e:
        await ramos.empresarial_juros_mora(
            regime="legal", valor_principal=1_000.0,
            data_inicio_mora=date(2024, 1, 1), data_fim=date(2025, 1, 1),
            selic_acumulada_percent=5.0, ipca_acumulado_percent=2.0, cu=None,
        )
    assert e.value.status_code == 422
    assert "aplicar_regra_anterior" in e.value.detail


async def test_juros_mora_segmentacao_1pct_ate_29_08_2024():
    # Mora desde 31/07/2024: regra antiga vai ATÉ 29/08/2024 (inclusive) — a nova
    # vigora a partir de 30/08. São 29 dias → 0,9667 mês × 1%.
    r = await ramos.empresarial_juros_mora(
        regime="legal", valor_principal=1_000.0,
        data_inicio_mora=date(2024, 7, 31), data_fim=date(2025, 7, 31),
        selic_acumulada_percent=10.0, ipca_acumulado_percent=4.0,
        aplicar_regra_anterior="sim", cu=None,
    )
    assert len(r["componentes"]) == 2
    antigo, novo = r["componentes"]
    assert "1% a.m." in antigo["parcela"]
    assert antigo["periodo"].endswith("2024-08-29")   # sem off-by-one no rótulo
    assert antigo["valor"] == 9.67                    # 1000 × 1% × 29/30 mês
    assert novo["valor"] == 60.0                      # 1000 × (10% − 4%)
    assert r["juros_mora_total"] == 69.67


async def test_juros_mora_periodo_todo_anterior_a_vigencia_sem_indices():
    """Mora encerrada ANTES de 30/08/2024: só a regra antiga incide — sem exigir
    Selic/IPCA e sem componente fantasma de período invertido."""
    r = await ramos.empresarial_juros_mora(
        regime="legal", valor_principal=1_000.0,
        data_inicio_mora=date(2024, 1, 1), data_fim=date(2024, 6, 30), cu=None,
    )
    assert len(r["componentes"]) == 1
    comp = r["componentes"][0]
    assert comp["periodo"] == "2024-01-01 a 2024-06-30"   # período NÃO invertido
    assert comp["valor"] > 0
    assert "INTEGRALMENTE anterior" in r["nota_regime"]
    _assert_metadados_regra(r)


async def test_juros_mora_convencionada():
    r = await ramos.empresarial_juros_mora(
        regime="convencionada", valor_principal=1_000.0,
        data_inicio_mora=date(2025, 1, 1), data_fim=date(2025, 1, 31),
        taxa_mensal_percent=2.0, multa_pct=2.0, cu=None,
    )
    assert r["juros_mora_total"] == 20.0          # 1000 × 2% × 1 mês (30 dias)
    assert r["multa"] == 20.0
    assert r["total_devido"] == 1_040.0
    assert "Usura" in r["nota_regime"]


async def test_juros_mora_convencionada_sem_taxa_422():
    with pytest.raises(HTTPException) as e:
        await ramos.empresarial_juros_mora(
            regime="convencionada", valor_principal=1_000.0,
            data_inicio_mora=date(2025, 1, 1), cu=None,
        )
    assert e.value.status_code == 422
    assert "taxa_mensal_percent" in e.value.detail


async def test_juros_mora_data_fim_anterior_ao_inicio_422():
    with pytest.raises(HTTPException) as e:
        await ramos.empresarial_juros_mora(
            regime="convencionada", valor_principal=1_000.0,
            data_inicio_mora=date(2025, 6, 1), data_fim=date(2025, 1, 1),
            taxa_mensal_percent=1.0, cu=None,
        )
    assert e.value.status_code == 422


# ══════════════════════════════════════════════════════════════════════════
# 3. /civel/ferramentas/prazos-contestacao (CPC 335/219/183 · Lei 9.099/95)
# ══════════════════════════════════════════════════════════════════════════
async def test_contestacao_rito_comum_15_dias_uteis():
    r = await ramos.civ_prazo_contestacao(
        rito="comum", marco="juntada_citacao", data_marco=date(2026, 3, 2), cu=None,
    )
    assert r["vencimento"] == date(2026, 3, 23)   # seg 02/03 + 15 dias úteis
    assert "15 dias úteis" in r["prazo"]
    assert "335" in r["base_legal"]
    _assert_metadados_regra(r)
    _assert_sem_selo(r)


async def test_contestacao_fazenda_publica_dobro_30_uteis_sem_quadruplo():
    r = await ramos.civ_prazo_contestacao(
        rito="fazenda_publica", marco="audiencia_conciliacao",
        data_marco=date(2026, 3, 2), cu=None,
    )
    # Dobro do art. 183 — mesma contagem do helper canônico em dobro.
    assert r["vencimento"] == prazo_dias_uteis(date(2026, 3, 2), 15, em_dobro=True)
    assert "dobro" in r["prazo"]
    assert "quádruplo" not in str(r)              # contradição da auditoria eliminada


async def test_contestacao_jec_sem_prazo_universal():
    r = await ramos.civ_prazo_contestacao(rito="jec", cu=None)
    assert r["prazo_calculado"] is None
    assert r["exige_ato_judicial_concreto"] is True
    assert "12-A" in r["orientacao"]              # dias úteis (Lei 13.728/2018)
    assert "audiência de instrução" in r["orientacao"]
    assert "vencimento" not in r
    _assert_metadados_regra(r)


async def test_contestacao_rito_comum_sem_marco_422():
    with pytest.raises(HTTPException) as e:
        await ramos.civ_prazo_contestacao(rito="comum", cu=None)
    assert e.value.status_code == 422
    assert "marco" in e.value.detail


async def test_contestacao_rito_invalido_422():
    with pytest.raises(HTTPException) as e:
        await ramos.civ_prazo_contestacao(rito="sumarissimo", cu=None)
    assert e.value.status_code == 422


# ══════════════════════════════════════════════════════════════════════════
# 4. /penal/ferramentas/prazos-processuais (CPP arts. 396, 798 e 798-A)
# ══════════════════════════════════════════════════════════════════════════
async def test_prazos_penais_dias_corridos():
    r = await ramos.pen_prazos(data_citacao=date(2026, 3, 2), cu=None)
    resposta = [p for p in r["prazos"] if p["evento"] == "Resposta à acusação"][0]
    # Seg 02/03 + 10 CORRIDOS (exclui o dia do começo) = qui 12/03 — dia útil.
    assert resposta["data"] == date(2026, 3, 12)
    assert "396" in resposta["base"] and "corridos" in resposta["base"]
    assert "CORRIDOS" in r["contagem"]
    assert "798-A" in r["nota_suspensao_798a"]    # exceção legal (Lei 14.365/2022)
    _assert_metadados_regra(r)
    _assert_sem_selo(r)


async def test_prazos_penais_vencimento_domingo_prorroga():
    # Qui 05/03/2026 + 10 corridos = dom 15/03 → prorroga p/ seg 16/03 (CPP 798 §3º).
    r = await ramos.pen_prazos(data_citacao=date(2026, 3, 5), cu=None)
    resposta = [p for p in r["prazos"] if p["evento"] == "Resposta à acusação"][0]
    assert resposta["data"] == date(2026, 3, 16)


# ══════════════════════════════════════════════════════════════════════════
# 5. /penal/ferramentas/verificar-anpp (CPP art. 28-A) — sem hardcode
# ══════════════════════════════════════════════════════════════════════════
_ANPP_OK = dict(
    pena_minima_anos=2.0,
    sem_violencia_grave_ameaca="sim",
    confissao_formal_circunstanciada="sim",
    reincidente="nao",
    conduta_criminal_habitual_reiterada_profissional="nao",
    beneficiado_anpp_transacao_sursis_5anos="nao",
    violencia_domestica_familiar_ou_razao_genero="nao",
)


async def test_anpp_elegivel_todos_requisitos():
    r = await ramos.pen_anpp(**_ANPP_OK, cu=None)
    assert r["elegivel_anpp"] is True
    assert all(x["atendido"] for x in r["requisitos"])
    assert len(r["requisitos"]) == 7
    assert r["condicoes_possiveis"]
    _assert_metadados_regra(r)
    _assert_sem_selo(r)


async def test_anpp_violencia_domestica_e_impeditivo_real():
    # Regressão do True hardcoded: agora o impeditivo do §2º IV é avaliado de fato.
    r = await ramos.pen_anpp(
        **{**_ANPP_OK, "violencia_domestica_familiar_ou_razao_genero": "sim"}, cu=None,
    )
    assert r["elegivel_anpp"] is False
    item = [x for x in r["requisitos"] if "§2º IV" in x["base"]][0]
    assert item["atendido"] is False
    assert item["situacao"] == "impeditivo presente"


async def test_anpp_pena_minima_4_anos_nao_elegivel():
    r = await ramos.pen_anpp(**{**_ANPP_OK, "pena_minima_anos": 4.0}, cu=None)
    assert r["elegivel_anpp"] is False
    assert r["condicoes_possiveis"] == []


async def test_anpp_entrada_invalida_422():
    with pytest.raises(HTTPException) as e:
        await ramos.pen_anpp(**{**_ANPP_OK, "reincidente": "talvez"}, cu=None)
    assert e.value.status_code == 422


# ══════════════════════════════════════════════════════════════════════════
# 6. Prescrição penal consolidada (CP arts. 109, 110, 115, 117)
# ══════════════════════════════════════════════════════════════════════════
async def test_prescricao_rotas_compartilham_implementacao():
    from fastapi import Response

    kw = dict(data_fato=date(2022, 5, 1), pena_maxima_anos=4.0, cu=None)
    canonica = await ramos.penal_prescricao(**kw)
    duplicata = await ramos.pen_prescricao(response=Response(), **kw)
    # A duplicata carrega o selo de depreciação (Onda 3) — resultado idêntico.
    for campo in ("deprecated", "sunset", "aviso_deprecacao"):
        duplicata.pop(campo)
    assert canonica["rota_canonica"] == "/penal/ferramentas/prescricao-penal"
    assert duplicata["rota_canonica"] == "/penal/ferramentas/prescricao-penal"
    # Mesmo resultado, só muda a rota consultada.
    canonica.pop("rota_consultada"), duplicata.pop("rota_consultada")
    assert canonica == duplicata
    assert canonica["prazo_prescricional_anos"] == 8       # 2 < pena ≤ 4 → 8 anos
    assert canonica["data_prescricao_estimada"] == date(2030, 5, 1)
    assert canonica["prescrito"] is False
    _assert_metadados_regra(canonica)
    _assert_sem_selo(canonica)


async def test_prescricao_sem_nenhuma_pena_422():
    with pytest.raises(HTTPException) as e:
        await ramos.penal_prescricao(data_fato=date(2022, 5, 1), cu=None)
    assert e.value.status_code == 422
    assert "110" in e.value.detail


async def test_prescricao_marcos_interruptivos_reiniciam_contagem():
    # Pena ≤ 2 e ≥ 1 → 4 anos. Fato 10/01/2010; denúncia recebida 01/06/2013
    # interrompe DENTRO do prazo; do marco até hoje passam > 4 anos → prescrito
    # no 2º intervalo (intercorrente).
    r = await ramos.penal_prescricao(
        data_fato=date(2010, 1, 10), pena_maxima_anos=1.5,
        marcos_interruptivos="2013-06-01", cu=None,
    )
    assert r["prazo_prescricional_anos"] == 4
    assert r["analise_intervalos"][0]["prescrito_no_intervalo"] is False
    assert r["analise_intervalos"][1]["prescrito_no_intervalo"] is True
    assert r["prescrito"] is True and r["intervalo_prescrito"] == 2


async def test_prescricao_marco_tardio_prescreve_no_primeiro_intervalo():
    # Marco veio DEPOIS de consumado o prazo do 1º intervalo → prescrição lá.
    r = await ramos.penal_prescricao(
        data_fato=date(2010, 1, 10), pena_maxima_anos=1.5,
        marcos_interruptivos="2015-01-01", cu=None,
    )
    assert r["intervalo_prescrito"] == 1


async def test_prescricao_pena_concreta_usa_art_110():
    r = await ramos.penal_prescricao(
        data_fato=date(2022, 5, 1), pena_maxima_anos=10.0, pena_concreta_anos=1.0, cu=None,
    )
    assert "110" in r["base_de_calculo"]
    assert r["prazo_prescricional_anos"] == 4              # pela CONCRETA, não pela máxima
    assert r["pena_considerada_anos"] == 1.0


async def test_prescricao_reducao_metade_art_115():
    # Pena < 1 → 3 anos; menor de 21 → metade = 18 meses. Fato 10/01/2025 →
    # limite 10/07/2026 (já vencido em 26/07/2026).
    r = await ramos.penal_prescricao(
        data_fato=date(2025, 1, 10), pena_maxima_anos=0.5,
        menor_21_na_data_fato="sim", cu=None,
    )
    assert r["reducao_metade_art_115"] is True
    assert r["prazo_prescricional_anos"] == 1.5
    assert r["data_prescricao_estimada"] == date(2026, 7, 10)
    assert r["prescrito"] is True


@pytest.mark.parametrize("marcos", ["nao-e-data", "2020-13-45", "2001-01-01"])
async def test_prescricao_marco_invalido_ou_anterior_ao_fato_422(marcos):
    with pytest.raises(HTTPException) as e:
        await ramos.penal_prescricao(
            data_fato=date(2010, 1, 10), pena_maxima_anos=2.0,
            marcos_interruptivos=marcos, cu=None,
        )
    assert e.value.status_code == 422


async def test_prescricao_bissexto_29_02():
    # 29/02/2020 + 4 anos → 2024 é bissexto → mantém 29/02/2024.
    r = await ramos.penal_prescricao(
        data_fato=date(2020, 2, 29), pena_maxima_anos=2.0, cu=None,
    )
    assert r["data_prescricao_estimada"] == date(2024, 2, 29)


# ══════════════════════════════════════════════════════════════════════════
# 7. /penal/ferramentas/dosimetria — simulador assistido (mantém selo)
# ══════════════════════════════════════════════════════════════════════════
async def test_dosimetria_trifasica_em_meses():
    # Cominada 2-8 anos (24-96 meses); 2 circunstâncias → base 24 + 72×2/8 = 42;
    # 1 agravante → 42 + 42/6 = 49; +1/3 → 65,33; −1/6 → 54,44 meses (4a6m).
    r = await ramos.penal_dosimetria(
        pena_minima_meses=24, pena_maxima_meses=96,
        circunstancias_judiciais_desfavoraveis=2,
        n_agravantes=1, n_atenuantes=0,
        causas_aumento="1/3", causas_diminuicao="1/6", cu=None,
    )
    assert r["fase_1"]["pena_base"]["total_meses"] == 42.0
    assert r["fase_2"]["pena_intermediaria"]["total_meses"] == 49.0
    assert r["fase_3"]["pena_definitiva"] == {"anos": 4, "meses": 6, "total_meses": 54.4}
    assert r["regime_inicial_indicativo"]["regime"].startswith("semiaberto")
    assert r["homologada"] is False               # permanece com selo (simulador)
    assert "simulador assistido" in r["aviso_homologacao"]
    _assert_metadados_regra(r)


async def test_dosimetria_sumula_231_trava_no_minimo():
    r = await ramos.penal_dosimetria(
        pena_minima_meses=24, pena_maxima_meses=96,
        circunstancias_judiciais_desfavoraveis=0,
        n_agravantes=0, n_atenuantes=2, cu=None,
    )
    assert r["fase_2"]["resultado_bruto_meses"] == 16.0    # 24 − 2×4
    assert r["fase_2"]["limitada_ao_minimo_sum_231_stj"] is True
    assert r["fase_2"]["pena_intermediaria"]["total_meses"] == 24.0


async def test_dosimetria_terceira_fase_pode_ultrapassar_maximo():
    r = await ramos.penal_dosimetria(
        pena_minima_meses=24, pena_maxima_meses=96,
        circunstancias_judiciais_desfavoraveis=8,          # base = máximo (96)
        causas_aumento="1/2", cu=None,
    )
    assert r["fase_3"]["pena_definitiva"]["total_meses"] == 144.0   # 96 × 3/2
    assert r["regime_inicial_indicativo"]["regime"] == "fechado"


@pytest.mark.parametrize("kwargs", [
    {"causas_aumento": "um terço"},                        # fração fora do formato
    {"causas_diminuicao": "3/2"},                          # diminuição ≥ 1 zeraria a pena
    {"causas_aumento": "0/3"},                             # numerador zero
    {"pena_maxima_meses": 12},                             # máx < mín
    {"circunstancias_judiciais_desfavoraveis": 9},         # fora de 0-8
])
async def test_dosimetria_entradas_invalidas_422(kwargs):
    base = dict(pena_minima_meses=24, pena_maxima_meses=96, cu=None)
    with pytest.raises(HTTPException) as e:
        await ramos.penal_dosimetria(**{**base, **kwargs})
    assert e.value.status_code == 422


# ══════════════════════════════════════════════════════════════════════════
# FASE B — 8. /trabalhista-esp/ferramentas/prazos (CLT art. 775 — dias ÚTEIS)
# ══════════════════════════════════════════════════════════════════════════
async def test_trab_prazos_dias_uteis():
    r = await ramos.trab_prazos(data_ciencia=date(2026, 3, 2), tipo_prazo="todos", cu=None)
    por_tipo = {p["tipo"]: p for p in r["prazos"]}
    # Seg 02/03 + 8 ÚTEIS = qui 12/03; + 5 ÚTEIS = seg 09/03 (não mais corridos).
    assert por_tipo["recurso_ordinario"]["data"] == prazo_dias_uteis(date(2026, 3, 2), 8)
    assert por_tipo["recurso_ordinario"]["data"] == date(2026, 3, 12)
    assert por_tipo["embargos_declaracao"]["data"] == date(2026, 3, 9)
    assert por_tipo["recurso_de_revista"]["data"] == date(2026, 3, 12)
    assert all(p["tipo_contagem"] == "úteis" for p in r["prazos"])
    assert "899 §1º" in r["nota_deposito_recursal"]      # recolhimento no prazo do recurso
    _assert_metadados_regra(r)
    _assert_sem_selo(r)


async def test_trab_prazos_filtra_por_tipo():
    r = await ramos.trab_prazos(data_ciencia=date(2026, 3, 2),
                                tipo_prazo="embargos_declaracao", cu=None)
    assert len(r["prazos"]) == 1
    assert r["prazos"][0]["tipo"] == "embargos_declaracao"


async def test_trab_prazos_tipo_invalido_422():
    with pytest.raises(HTTPException) as e:
        await ramos.trab_prazos(data_ciencia=date(2026, 3, 2), tipo_prazo="apelacao", cu=None)
    assert e.value.status_code == 422


# ══════════════════════════════════════════════════════════════════════════
# FASE B — 9. /trabalhista-esp/ferramentas/prescricao-trabalhista (Súm. 308 TST)
# ══════════════════════════════════════════════════════════════════════════
async def test_prescricao_trabalhista_quinquenal_retroativa():
    r = await ramos.trab_prescricao(
        data_extincao_contrato=date(2025, 1, 10),
        data_ajuizamento=date(2026, 3, 2), cu=None,
    )
    assert r["prescricao_bienal"]["limite_para_ajuizar"] == date(2027, 1, 10)
    assert r["prescricao_bienal"]["acao_dentro_da_bienal"] is True
    # RETROATIVA: ajuizamento − 5 anos (nada projetado para frente).
    assert r["prescricao_quinquenal"]["limite_retroativo"] == date(2021, 3, 2)
    _assert_metadados_regra(r)
    _assert_sem_selo(r)


async def test_prescricao_trabalhista_bienal_consumada():
    # Exceção legal: ajuizar após 2 anos da extinção fulmina a pretensão.
    r = await ramos.trab_prescricao(
        data_extincao_contrato=date(2023, 1, 10),
        data_ajuizamento=date(2026, 3, 2), cu=None,
    )
    assert r["prescricao_bienal"]["acao_dentro_da_bienal"] is False
    assert "CONSUMADA" in r["sintese"]


async def test_prescricao_trabalhista_ajuizamento_presumido_hoje():
    r = await ramos.trab_prescricao(data_extincao_contrato=date(2026, 1, 10), cu=None)
    assert r["data_ajuizamento"] == date.today()
    assert r["data_ajuizamento_presumida_hoje"] is True


async def test_prescricao_trabalhista_bienal_bissexto():
    # Extinção em 29/02/2024 + 2 anos → 2026 não é bissexto → 28/02/2026.
    r = await ramos.trab_prescricao(
        data_extincao_contrato=date(2024, 2, 29),
        data_ajuizamento=date(2026, 2, 27), cu=None,
    )
    assert r["prescricao_bienal"]["limite_para_ajuizar"] == date(2026, 2, 28)
    assert r["prescricao_bienal"]["acao_dentro_da_bienal"] is True


# ══════════════════════════════════════════════════════════════════════════
# FASE B — 10. Depósito recursal com tabela versionada por vigência
# ══════════════════════════════════════════════════════════════════════════
async def test_deposito_recursal_tabela_versionada():
    # 01/07/2026 cai na faixa do Ato 391/2025 (vigente de 01/08/2025 a 31/07/2026).
    r = await ramos.trab_deposito(valor_condenacao=50_000.0,
                                  data_referencia=date(2026, 7, 1), cu=None)
    assert r["deposito_ro"] == 13_813.83    # condenação > teto → teto da faixa
    assert r["teto_ro"] == 13_813.83 and r["teto_rr"] == 27_627.66
    assert "391/2025" in r["fonte"]
    assert r["vigencia_tabela"].startswith("2025-08-01")
    _assert_metadados_regra(r)


async def test_deposito_recursal_serie_historica_por_data_do_recurso():
    """Cada Ato do TST vale para o seu período — recurso antigo usa o teto da época.

    Antes desta correção a tabela só tinha uma faixa (com valor que não
    correspondia a Ato nenhum), então recurso anterior a ago/2025 era recusado.
    """
    esperado = [
        (date(2022, 9, 1), 12_296.38, 24_592.76, "430/2022"),
        (date(2023, 9, 1), 12_665.14, 25_330.28, "414/2023"),
        (date(2024, 9, 1), 13_133.46, 26_266.92, "366/2024"),
        (date(2025, 9, 1), 13_813.83, 27_627.66, "391/2025"),
        (date(2026, 8, 1), 14_411.57, 28_823.14, "381/2026"),
    ]
    for referencia, ro, rr, ato in esperado:
        r = await ramos.trab_deposito(valor_condenacao=999_999.0,
                                      data_referencia=referencia, cu=None)
        assert r["teto_ro"] == ro, f"{referencia}: teto RO divergente"
        assert r["teto_rr"] == rr, f"{referencia}: teto RR divergente"
        assert ato in r["fonte"], f"{referencia}: Ato esperado {ato}"


async def test_deposito_recursal_virada_de_vigencia_em_1o_de_agosto():
    """31/07 e 01/08 pertencem a Atos diferentes — a virada não pode escorregar."""
    vespera = await ramos.trab_deposito(valor_condenacao=999_999.0,
                                        data_referencia=date(2026, 7, 31), cu=None)
    virada = await ramos.trab_deposito(valor_condenacao=999_999.0,
                                       data_referencia=date(2026, 8, 1), cu=None)
    assert vespera["teto_ro"] == 13_813.83 and "391/2025" in vespera["fonte"]
    assert virada["teto_ro"] == 14_411.57 and "381/2026" in virada["fonte"]


async def test_deposito_recursal_periodo_sem_tabela_422():
    with pytest.raises(HTTPException) as e:
        await ramos.trab_deposito(valor_condenacao=1_000.0,
                                  data_referencia=date(2020, 1, 1), cu=None)
    assert e.value.status_code == 422
    assert "tetos" in e.value.detail


# ══════════════════════════════════════════════════════════════════════════
# FASE B — 11. Horas extras parametrizada + rota canônica /trabalhista-esp
# ══════════════════════════════════════════════════════════════════════════
async def test_horas_extras_componentes_discriminados():
    r = await ramos.trabalhista_horas_extras(
        salario_mensal=2_200.0, horas_extras_mes=10.0, divisor=220,
        percentual_he=50.0, incluir_dsr="sim", incluir_reflexo_fgts="sim", cu=None,
    )
    c = r["componentes"]
    assert c["valor_hora_normal"] == 10.0
    assert c["valor_horas_extras"] == 150.0              # 10 × 1,5 × 10
    assert c["dsr_sobre_he"] == 25.0                     # 150 ÷ 6
    assert c["fgts_8pct_sobre_he_dsr"] == 14.0           # 8% × 175
    assert r["total_mes_estimado"] == 189.0
    assert r["rota_canonica"] == "/trabalhista-esp/ferramentas/horas-extras"
    _assert_metadados_regra(r)


async def test_horas_extras_sem_dsr_e_sem_fgts():
    r = await ramos.trabalhista_horas_extras(
        salario_mensal=2_000.0, horas_extras_mes=10.0, divisor=200,
        percentual_he=60.0, incluir_dsr="nao", incluir_reflexo_fgts="nao", cu=None,
    )
    assert r["componentes"]["dsr_sobre_he"] == 0.0
    assert r["componentes"]["fgts_8pct_sobre_he_dsr"] == 0.0
    assert r["componentes"]["valor_horas_extras"] == 160.0   # 10 × 1,6 × 10
    assert r["total_mes_estimado"] == 160.0


@pytest.mark.parametrize("kwargs", [
    {"percentual_he": 40.0},                             # abaixo do mínimo constitucional
    {"divisor": 0},                                      # divisor inválido
    {"incluir_dsr": "talvez"},                           # sim/nao inválido
])
async def test_horas_extras_entradas_invalidas_422(kwargs):
    base = dict(salario_mensal=2_200.0, horas_extras_mes=10.0, divisor=220,
                incluir_dsr="sim", incluir_reflexo_fgts="sim", cu=None)
    with pytest.raises(HTTPException) as e:
        await ramos.trabalhista_horas_extras(**{**base, **kwargs})
    assert e.value.status_code == 422


def test_horas_extras_registrada_nas_duas_rotas():
    from app.main import app
    rotas = {(getattr(r, "path", "") or "") for r in app.routes}
    assert "/api/trabalhista-esp/ferramentas/horas-extras" in rotas   # canônica
    assert "/api/trabalhista/ferramentas/horas-extras" in rotas       # alias legado


# ══════════════════════════════════════════════════════════════════════════
# FASE B — 12. /transito/ferramentas/prazos-recurso (CTB 281-A/285/288) +
#              delegação de /admin-esp/ferramentas/recurso-multa-transito
# ══════════════════════════════════════════════════════════════════════════
async def test_transito_prazos_marcos_independentes_por_fase():
    defesa = await ramos.transito_prazos_recurso(
        fase="defesa_previa", data_notificacao_autuacao=date(2026, 3, 2), cu=None)
    jari = await ramos.transito_prazos_recurso(
        fase="jari", data_notificacao_penalidade=date(2026, 3, 2), cu=None)
    cetran = await ramos.transito_prazos_recurso(
        fase="cetran", data_ciencia_decisao_jari=date(2026, 3, 2), cu=None)
    # Todos: 30 dias do PRÓPRIO marco (nunca encadeado ao prazo anterior).
    assert defesa["vencimento"] == jari["vencimento"] == cetran["vencimento"]
    assert defesa["prazo"].startswith("prazo MÍNIMO de 30 dias")
    assert "281-A" in defesa["prazo"]
    assert "285" in jari["prazo"] and "288" in cetran["prazo"]
    assert "619" not in str(defesa)                      # sem resolução CONTRAN antiga
    _assert_metadados_regra(defesa)
    _assert_sem_selo(defesa)


async def test_transito_prazos_marco_ausente_422():
    with pytest.raises(HTTPException) as e:
        await ramos.transito_prazos_recurso(fase="jari", cu=None)
    assert e.value.status_code == 422
    assert "data_notificacao_penalidade" in e.value.detail


async def test_transito_prazos_data_errada_para_fase_422():
    with pytest.raises(HTTPException) as e:
        await ramos.transito_prazos_recurso(
            fase="jari", data_notificacao_penalidade=date(2026, 3, 2),
            data_notificacao_autuacao=date(2026, 3, 2), cu=None)
    assert e.value.status_code == 422
    assert "incompatível" in e.value.detail


async def test_admin_recurso_multa_delega_a_rota_canonica():
    kw = dict(fase="defesa_previa", data_notificacao_autuacao=date(2026, 3, 2),
              valor_multa=293.47, cu=None)
    from fastapi import Response

    admin = await ramos.adm_multa_transito(response=Response(), **kw)
    transito = await ramos.transito_prazos_recurso(**kw)
    for campo in ("deprecated", "sunset", "aviso_deprecacao"):
        admin.pop(campo)
    assert admin["rota_canonica"] == "/transito/ferramentas/prazos-recurso"
    admin.pop("rota_consultada"), transito.pop("rota_consultada")
    assert admin == transito                             # fonte única
    assert admin["descontos"]["desconto_40pct_sne"] == 176.08
    _assert_sem_selo(admin)


# ══════════════════════════════════════════════════════════════════════════
# FASE B — 13. /transito/ferramentas/pontuacao-cnh — sistema 20/30/40
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("gravissimas,limite", [(0, 40), (1, 30), (2, 20), (3, 20)])
async def test_pontuacao_cnh_sistema_20_30_40(gravissimas, limite):
    r = await ramos.transito_pontuacao_cnh(
        pontos_total=19, qtd_gravissimas=gravissimas,
        exerce_atividade_remunerada="nao", cu=None)
    assert r["limite_aplicavel"] == limite
    _assert_metadados_regra(r)
    _assert_sem_selo(r)


async def test_pontuacao_cnh_ear_limite_unico_40():
    # Regressão do "30 p/ EAR": condutor EAR tem limite ÚNICO de 40, mesmo com gravíssimas.
    r = await ramos.transito_pontuacao_cnh(
        pontos_total=35, qtd_gravissimas=2, exerce_atividade_remunerada="sim", cu=None)
    assert r["limite_aplicavel"] == 40
    assert r["atingiu_limite"] is False
    assert "curso preventivo" in r["nota_curso_preventivo_ear"]


async def test_pontuacao_cnh_atinge_limite():
    r = await ramos.transito_pontuacao_cnh(
        pontos_total=20, qtd_gravissimas=2, exerce_atividade_remunerada="nao", cu=None)
    assert r["atingiu_limite"] is True
    assert "suspensão" in r["situacao"]


@pytest.mark.parametrize("kwargs", [
    {"exerce_atividade_remunerada": "talvez"},
    {"pontos_total": -1},
    {"qtd_gravissimas": -2},
])
async def test_pontuacao_cnh_entradas_invalidas_422(kwargs):
    base = dict(pontos_total=10, qtd_gravissimas=0,
                exerce_atividade_remunerada="nao", cu=None)
    with pytest.raises(HTTPException) as e:
        await ramos.transito_pontuacao_cnh(**{**base, **kwargs})
    assert e.value.status_code == 422


# ══════════════════════════════════════════════════════════════════════════
# FASE C — 14. Consumidor: devolução em dobro (boa-fé objetiva, sem má-fé)
# ══════════════════════════════════════════════════════════════════════════
_DOBRO_OK = dict(valor_cobrado_indevidamente=100.0, houve_pagamento="sim",
                 cobranca_contraria_boa_fe_objetiva="sim", engano_justificavel="nao")


async def test_devolucao_dobro_boa_fe_objetiva_sem_ma_fe():
    r = await ramos.consumidor_devolucao_dobro(**_DOBRO_OK, cu=None)
    assert r["resultado"] == "dobro" and r["restituicao_estimada"] == 200.0
    assert len(r["analise_requisitos"]) == 3
    assert "30/03/2021" in r["nota_modulacao_temporal"]
    assert "má-fé" not in str([q["requisito"] for q in r["analise_requisitos"]]).lower() \
        or "não se exige má-fé" in r["analise_requisitos"][1]["requisito"]
    _assert_metadados_regra(r)
    _assert_sem_selo(r)


async def test_devolucao_dobro_engano_justificavel_simples():
    r = await ramos.consumidor_devolucao_dobro(
        **{**_DOBRO_OK, "engano_justificavel": "sim"}, cu=None)
    assert r["resultado"] == "simples" and r["restituicao_estimada"] == 100.0


async def test_devolucao_dobro_sem_pagamento_sem_repeticao():
    r = await ramos.consumidor_devolucao_dobro(
        **{**_DOBRO_OK, "houve_pagamento": "nao"}, cu=None)
    assert r["resultado"] == "sem_repeticao" and r["restituicao_estimada"] == 0.0


# ══════════════════════════════════════════════════════════════════════════
# FASE C — 15. Consumidor: prazos por pretensão (termo inicial correto)
# ══════════════════════════════════════════════════════════════════════════
async def test_prazos_cdc_repeticao_indebito_decenal():
    r = await ramos.consumidor_prazos_cdc(
        pretensao="repeticao_indebito_contratual", data_marco=date(2020, 6, 15), cu=None)
    assert r["instituto"] == "prescrição" and r["prazo"] == "10 anos"
    assert r["data_limite"] == date(2030, 6, 15)
    assert "738.991" in r["base_legal"]
    _assert_metadados_regra(r)
    _assert_sem_selo(r)


async def test_prazos_cdc_vicio_oculto_conta_do_aparecimento():
    with pytest.raises(HTTPException) as e:   # marco ausente do qualificador
        await ramos.consumidor_prazos_cdc(
            pretensao="vicio_oculto", data_marco=date(2026, 6, 1), cu=None)
    assert e.value.status_code == 422 and "bem_duravel" in e.value.detail
    r = await ramos.consumidor_prazos_cdc(
        pretensao="vicio_oculto", data_marco=date(2026, 6, 1), bem_duravel="sim", cu=None)
    assert r["prazo"] == "90 dias"
    assert r["data_limite"] == date(2026, 8, 30)          # sem prorrogação (decadência)
    assert "APARECIMENTO" in r["termo_inicial_correto"].upper() \
        or "evidenciado" in r["termo_inicial_correto"].lower()


async def test_prazos_cdc_acidente_de_consumo_5_anos():
    r = await ramos.consumidor_prazos_cdc(
        pretensao="acidente_de_consumo", data_marco=date(2024, 2, 29), cu=None)
    assert r["data_limite"] == date(2029, 2, 28)          # bissexto tratado
    assert "conhecimento do DANO" in r["termo_inicial_correto"]
    assert "§2º" in r["nota_causas_obstativas"]           # causas obstativas do art. 26


# ══════════════════════════════════════════════════════════════════════════
# FASE C — 16. Consumidor: negativação — checklist (Súm. 385 STJ)
# ══════════════════════════════════════════════════════════════════════════
async def test_negativacao_sem_anterior_in_re_ipsa():
    r = await ramos.consumidor_negativacao(existe_inscricao_anterior="nao", cu=None)
    assert r["sumula_385_aplicavel"] is False
    assert "in re ipsa" in r["conclusao_indicativa"]
    assert r["verificacoes_pendentes"]
    _assert_sem_selo(r)


async def test_negativacao_com_anterior_exige_qualificadores_422():
    with pytest.raises(HTTPException) as e:
        await ramos.consumidor_negativacao(existe_inscricao_anterior="sim", cu=None)
    assert e.value.status_code == 422


async def test_negativacao_com_anterior_legitima_checklist_nao_binario():
    r = await ramos.consumidor_negativacao(
        existe_inscricao_anterior="sim", inscricao_anterior_legitima_e_ativa="sim",
        origem_verificada="nao", cu=None)
    assert isinstance(r["sumula_385_aplicavel"], str)     # nunca sim/não seco
    assert any("ORIGEM" in v for v in r["verificacoes_pendentes"])
    assert "NÃO incidência" in r["conclusao_indicativa"]


# ══════════════════════════════════════════════════════════════════════════
# FASE C — 17. Dano moral sem faixas fixas (método bifásico)
# ══════════════════════════════════════════════════════════════════════════
async def test_dano_moral_sem_valores_hardcoded():
    r = await ramos.civ_dano_moral(tipo_caso="negativacao_indevida",
                                   salarios_minimos_pedido=10.0, cu=None)
    assert r["sem_valor_sugerido"] is True
    assert "faixa_orientativa_min" not in r and "faixa_orientativa_max" not in r
    assert "bifásico" in r["metodologia"]["metodo"]
    assert len(r["fatores"]) >= 5
    assert "tribunal" in r["orientacao_jurimetrica"]
    assert r["quantum_pedido_contextual"]["pedido_em_sm"] == 10.0
    _assert_metadados_regra(r)


# ══════════════════════════════════════════════════════════════════════════
# FASE C — 18. Previdenciário: sexo F|M e motor de marcos
# ══════════════════════════════════════════════════════════════════════════
async def test_tempo_contribuicao_sexo_f_regras_femininas():
    r = await ramos.previdenciario_tempo_contribuicao(
        idade=60, tempo_contribuicao_anos=32.0, sexo="F", ano=2026, cu=None)
    assert r["sexo"] == "feminino" and r["tempo_minimo_anos"] == 30


async def test_tempo_contribuicao_mulher_por_extenso_422():
    # Regressão do startswith("M"): "Mulher" era tratado como masculino.
    with pytest.raises(HTTPException) as e:
        await ramos.previdenciario_tempo_contribuicao(
            idade=60, tempo_contribuicao_anos=32.0, sexo="Mulher", cu=None)
    assert e.value.status_code == 422


async def test_prev_prazos_revisao_decadencia_10_anos_do_mes_seguinte():
    r = await ramos.previdenciario_prazos(
        natureza="revisao_ato_concessao", data_primeiro_pagamento=date(2025, 12, 15), cu=None)
    assert "2026-01-01" in r["marco_inicial"]             # dia 1º do mês seguinte (vira o ano)
    assert r["data_limite"] == date(2036, 1, 1)
    assert "13.846" in r["base"]
    _assert_metadados_regra(r)
    _assert_sem_selo(r)


async def test_prev_prazos_parcelas_prescricao_movel():
    r = await ramos.previdenciario_prazos(
        natureza="parcelas_atrasadas", data_ajuizamento=date(2026, 3, 10), cu=None)
    assert r["limite_retroativo"] == date(2021, 3, 10)
    assert "NÃO há data final única" in r["descricao"]


async def test_prev_prazos_marco_ausente_e_incompativel_422():
    with pytest.raises(HTTPException) as e1:
        await ramos.previdenciario_prazos(natureza="revisao_ato_concessao", cu=None)
    assert e1.value.status_code == 422
    with pytest.raises(HTTPException) as e2:
        await ramos.previdenciario_prazos(
            natureza="recurso_administrativo", data_ciencia_decisao=date(2026, 3, 2),
            data_primeiro_pagamento=date(2020, 1, 1), cu=None)
    assert e2.value.status_code == 422 and "incompatível" in e2.value.detail


async def test_prev_carencia_maternidade_empregada_isenta_ci_10():
    empregada = await ramos.previdenciario_carencia(
        beneficio="salario_maternidade", categoria="empregada", meses_contribuicao=0,
        decorre_acidente_ou_doenca_isenta="nao", cu=None)
    assert empregada["carencia_exigida"] == 0 and empregada["carencia_cumprida"] is True
    ci = await ramos.previdenciario_carencia(
        beneficio="salario_maternidade", categoria="contribuinte_individual_facultativa",
        meses_contribuicao=8, decorre_acidente_ou_doenca_isenta="nao", cu=None)
    assert ci["carencia_exigida"] == 10 and ci["faltam_meses"] == 2
    assert "27-A" in ci["nota_perda_qualidade"]
    _assert_metadados_regra(ci)


async def test_prev_carencia_auxilio_isento_por_acidente():
    r = await ramos.previdenciario_carencia(
        beneficio="auxilio_incapacidade", categoria="empregada", meses_contribuicao=1,
        decorre_acidente_ou_doenca_isenta="sim", cu=None)
    assert r["carencia_exigida"] == 0 and "26 II" in r["base_legal"]


# ══════════════════════════════════════════════════════════════════════════
# FASE C — 19. Bancário: classificação indicativa (sem "abusivo sim/não")
# ══════════════════════════════════════════════════════════════════════════
async def test_juros_abusivos_classificacao_indicativa():
    r = await ramos.bancario_juros_abusivos(
        taxa_contratada_mensal_pct=6.0, taxa_media_bacen_mensal_pct=3.0, cu=None)
    assert "indicio_abusividade" not in r
    assert r["razao_sobre_media"] == 2.0
    assert r["distancia_percentual"] == 100.0
    assert r["classificacao_indicativa"] == "substancialmente_acima"
    assert "não vinculante" in r["limiares_classificacao"]["substancialmente_acima"]
    assert len(r["comparabilidade_requisitos"]) == 6
    _assert_metadados_regra(r)


async def test_juros_abusivos_na_media_e_media_invalida():
    r = await ramos.bancario_juros_abusivos(
        taxa_contratada_mensal_pct=3.1, taxa_media_bacen_mensal_pct=3.0, cu=None)
    assert r["classificacao_indicativa"] == "na_media"
    with pytest.raises(HTTPException) as e:
        await ramos.bancario_juros_abusivos(
            taxa_contratada_mensal_pct=3.0, taxa_media_bacen_mensal_pct=0.0, cu=None)
    assert e.value.status_code == 422


async def test_analise_juros_sem_booleano_de_abusividade():
    r = await ramos.ban_juros(taxa_mensal_contratada=5.0, taxa_mensal_referencia=4.0,
                              valor_contratado=10_000.0, cu=None)
    assert "indicio_abusividade" not in r
    assert r["classificacao_indicativa"] == "acima_da_media"   # razão 1,25
    assert r["comparabilidade_requisitos"]


# ══════════════════════════════════════════════════════════════════════════
# FASE C — 20. Família: débito de alimentos por parcela (rito CPC 528 §7º)
# ══════════════════════════════════════════════════════════════════════════
async def test_debito_alimentos_separa_ritos():
    r = await ramos.familia_debito_alimentos(
        datas_vencimento_em_aberto="2025-08-05,2026-01-05,2026-02-05,2026-04-05",
        data_ajuizamento_execucao=date(2026, 3, 10), valor_parcela=1_000.0, cu=None)
    assert r["marco_corte_3_meses"] == date(2025, 12, 10)
    assert r["parcelas_rito_prisao"] == [date(2026, 1, 5), date(2026, 2, 5), date(2026, 4, 5)]
    assert r["parcelas_rito_expropriacao"] == [date(2025, 8, 5)]
    assert r["valores"]["debito_rito_prisao"] == 3_000.0
    assert r["valores"]["debito_rito_expropriacao"] == 1_000.0
    _assert_metadados_regra(r)


@pytest.mark.parametrize("datas", ["", "nao-e-data", "2026-15-99"])
async def test_debito_alimentos_datas_invalidas_422(datas):
    with pytest.raises(HTTPException) as e:
        await ramos.familia_debito_alimentos(
            datas_vencimento_em_aberto=datas,
            data_ajuizamento_execucao=date(2026, 3, 10), cu=None)
    assert e.value.status_code == 422


# ══════════════════════════════════════════════════════════════════════════
# FASE C — 21. ITCMD sem default de UF/alíquota
# ══════════════════════════════════════════════════════════════════════════
async def test_itcmd_exige_uf_e_aliquota_da_lei_estadual():
    r = await ramos.familia_itcmd(valor_monte=100_000.0, uf="mg", aliquota_percent=5.0,
                                  data_fato_gerador=date(2026, 2, 1), cu=None)
    assert r["uf"] == "MG" and r["itcmd_estimado"] == 5_000.0
    assert "Súm. 112 STF" in r["nota_aliquota"]
    _assert_metadados_regra(r)


@pytest.mark.parametrize("kwargs", [
    {"aliquota_percent": 9.0},                            # acima do teto do Senado (8%)
    {"uf": "M1"},                                         # UF inválida
])
async def test_itcmd_entradas_invalidas_422(kwargs):
    base = dict(valor_monte=100_000.0, uf="MG", aliquota_percent=5.0,
                data_fato_gerador=date(2026, 2, 1), cu=None)
    with pytest.raises(HTTPException) as e:
        await ramos.familia_itcmd(**{**base, **kwargs})
    assert e.value.status_code == 422


# ══════════════════════════════════════════════════════════════════════════
# FASE C — 22. Distrato (Lei 13.786/2018) com deduções e tetos por regime
# ══════════════════════════════════════════════════════════════════════════
async def test_distrato_deducoes_e_teto_por_regime():
    r = await ramos.imobiliario_distrato(
        valor_pago=100_000.0, regime_patrimonio_afetacao="sim",
        comissao_corretagem=5_000.0, meses_fruicao=10, valor_fruicao_mensal=500.0, cu=None)
    assert r["teto_legal_retencao_pct"] == 50.0
    assert r["memoria_calculo"]["pena_convencional"] == 50_000.0
    assert r["memoria_calculo"]["deducao_fruicao"] == 5_000.0
    assert r["valor_a_restituir"] == 40_000.0             # 100k − 50k − 5k − 5k
    assert "180" in r["prazo_devolucao"] and "30 dias" in r["prazo_devolucao"]
    _assert_metadados_regra(r)


async def test_distrato_percentual_acima_do_teto_422():
    with pytest.raises(HTTPException) as e:
        await ramos.imobiliario_distrato(
            valor_pago=100_000.0, regime_patrimonio_afetacao="nao",
            percentual_retencao=30.0, cu=None)            # teto sem afetação = 25%
    assert e.value.status_code == 422 and "25%" in e.value.detail


# ══════════════════════════════════════════════════════════════════════════
# FASE C — 23. Inputs mínimos: multa-mora por ente, LGPD, ambiental, tabelas
# ══════════════════════════════════════════════════════════════════════════
async def test_multa_mora_federal_calcula_estadual_orienta():
    fed = await ramos.tributario_multa_mora(ente="federal", valor_tributo=1_000.0,
                                            dias_atraso=100, cu=None)
    assert fed["percentual_multa"] == 20.0                # teto
    est = await ramos.tributario_multa_mora(ente="estadual", valor_tributo=1_000.0,
                                            dias_atraso=100, cu=None)
    assert est["calculo"] is None
    assert "NÃO se aplica" in est["orientacao"]
    with pytest.raises(HTTPException) as e:
        await ramos.tributario_multa_mora(ente="distrital", valor_tributo=1_000.0,
                                          dias_atraso=10, cu=None)
    assert e.value.status_code == 422


async def test_lgpd_incidente_exige_data_conhecimento():
    with pytest.raises(HTTPException) as e:
        await ramos.lgpd_prazos(tipo="incidente_anpd", data_evento=date(2026, 3, 2), cu=None)
    assert e.value.status_code == 422 and "data_conhecimento" in e.value.detail
    r = await ramos.lgpd_prazos(tipo="incidente_anpd",
                                data_conhecimento=date(2026, 3, 2), cu=None)
    assert r["prazo_final"] == date(2026, 3, 5)           # seg + 3 dias úteis
    assert "15" in r["versao_norma"]


async def test_simples_e_parcelamento_com_vigencia_tabela():
    s = await ramos.trib_simples_nacional(receita_bruta_12m=300_000.0, anexo="III", cu=None)
    assert "LC 155/2016" in s["vigencia_tabela"] and s["fonte"]
    p = await ramos.trib_parcelamento(valor_total_debito=60_000.0, parcelas=60,
                                      modalidade="parcelamento_comum", cu=None)
    assert p["vigencia_tabela"] and p["fonte"]


async def test_ambiental_exige_uf():
    with pytest.raises(HTTPException) as e:
        await ramos.amb_reserva_legal(area_imovel_ha=100.0, uf="XYZ", bioma="cerrado", cu=None)
    assert e.value.status_code == 422
    lic = await ramos.amb_licenciamento(uf="mg", fase="lp", porte="medio", cu=None)
    assert lic["uf"] == "MG" and "licenciador" in lic["nota_localizacao"]


# ══════════════════════════════════════════════════════════════════════════
# FASE D — invariante GLOBAL: nenhuma ferramenta sem metadados de regra
# ══════════════════════════════════════════════════════════════════════════
def test_invariante_toda_ferramenta_tem_metadados_ou_selo():
    """Toda rota /ferramentas/ de ramos.py deve responder com `versao_regra`
    (metadados de regra) OU estar na matriz de não homologadas. Impede que a
    lacuna das 25 ferramentas sem fonte/vigência volte a existir."""
    import inspect
    import re as _re
    from app.services.homologacao_ferramentas import FERRAMENTAS_NAO_HOMOLOGADAS

    src = inspect.getsource(ramos)
    blocos = _re.split(r'(@router\.get\("(/[^"]*ferramentas/[^"]*)"\))', src)
    faltando, total = [], 0
    pendentes: list[str] = []          # rotas empilhadas sobre o mesmo handler
    i = 1
    while i < len(blocos):
        caminho, corpo = blocos[i + 1], blocos[i + 2].split("@router.")[0]
        pendentes.append(caminho)
        i += 3
        if "async def" not in corpo:   # decorator de rota empilhado — segue p/ o próximo
            continue
        tem_meta = ("versao_regra" in corpo or "_com_regra(" in corpo
                    or "_prescricao_penal_consolidada(" in corpo
                    or "_prazos_recurso_transito(" in corpo)
        for rota in pendentes:
            total += 1
            if not (tem_meta or rota in FERRAMENTAS_NAO_HOMOLOGADAS):
                faltando.append(rota)
        pendentes = []
    assert total > 50, f"extração suspeita ({total} ferramentas)"
    assert not faltando, (
        f"{len(faltando)} ferramenta(s) sem `fontes`/`vigencia_regra`/`versao_regra` e fora da "
        "matriz de não homologadas:\n  " + "\n  ".join(faltando)
        + "\nAdicione os metadados de regra (ou @_com_regra) ou registre o selo na matriz.")


# ══════════════════════════════════════════════════════════════════════════
# FASE D — suspensão legal (recesso) nos prazos processuais
# ══════════════════════════════════════════════════════════════════════════
async def test_recesso_cpc_contestacao_20_12_a_20_01():
    """CPC art. 220: citação em 10/12/2025 → 15 dias úteis com suspensão de
    20/12 a 20/01. Antes do fix: 16/01/2026 (14 dias a MENOS)."""
    r = await ramos.civ_prazo_contestacao(
        rito="comum", marco="juntada_citacao", data_marco=date(2025, 12, 10), cu=None)
    assert r["suspensao_aplicada"]["aplicada"] is True
    assert r["suspensao_aplicada"]["vencimento_sem_suspensao"] == date(2026, 1, 16)
    assert r["vencimento"] == date(2026, 1, 30)
    assert r["suspensao_aplicada"]["dias_prorrogados"] == 14
    assert "220" in r["suspensao_aplicada"]["base"]


async def test_recesso_clt_775a_prazos_trabalhistas():
    r = await ramos.trab_prazos(data_ciencia=date(2025, 12, 10),
                                tipo_prazo="recurso_ordinario", cu=None)
    prazo = r["prazos"][0]
    assert prazo["suspensao_aplicada"]["aplicada"] is True
    # Sem a suspensão o RO vencia em 07/01/2026 (dentro do recesso) — 14 dias a menos.
    assert prazo["suspensao_aplicada"]["vencimento_sem_suspensao"] == date(2026, 1, 7)
    assert prazo["data"] > date(2026, 1, 20)
    assert prazo["suspensao_aplicada"]["dias_prorrogados"] > 0
    assert "775-A" in prazo["suspensao_aplicada"]["base"]


async def test_recesso_cpp_798a_prazo_penal():
    r = await ramos.pen_prazos(data_citacao=date(2025, 12, 15), cu=None)
    resposta = r["prazos"][0]
    assert resposta["suspensao_aplicada"]["aplicada"] is True
    assert resposta["suspensao_aplicada"]["vencimento_sem_suspensao"] == date(2025, 12, 26)
    assert resposta["data"] > date(2026, 1, 20)     # 5 dias já corridos + 5 após o recesso
    assert "798-A" in resposta["suspensao_aplicada"]["base"]


async def test_sem_recesso_nao_altera_prazo():
    r = await ramos.civ_prazo_contestacao(
        rito="comum", marco="juntada_citacao", data_marco=date(2026, 3, 2), cu=None)
    assert r["suspensao_aplicada"]["aplicada"] is False
    assert r["vencimento"] == date(2026, 3, 23)


# ══════════════════════════════════════════════════════════════════════════
# FASE D — datas de fim de mês (helpers) e efeitos no rito de alimentos
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("origem,meses,esperado", [
    (date(2026, 7, 31), -3, date(2026, 4, 30)),   # antes: 2026-04-28
    (date(2020, 1, 31), 18, date(2021, 7, 31)),   # antes: 2021-07-28
    (date(2026, 3, 31), -1, date(2026, 2, 28)),   # dia inexistente → último do mês
    (date(2024, 3, 31), -1, date(2024, 2, 29)),   # bissexto
    (date(2026, 1, 15), 6, date(2026, 7, 15)),
])
def test_add_meses_preserva_dia_ou_usa_ultimo_do_mes(origem, meses, esperado):
    assert ramos._add_meses_data(origem, meses) == esperado


async def test_alimentos_corte_fim_de_mes_nao_infla_rito_prisao():
    """Ajuizamento em 31/07/2026 → corte 30/04/2026. A parcela de 29/04 é
    ANTERIOR ao corte: vai para expropriação (antes ia para prisão civil)."""
    r = await ramos.familia_debito_alimentos(
        datas_vencimento_em_aberto="2026-04-29,2026-05-05,2026-06-05",
        data_ajuizamento_execucao=date(2026, 7, 31), cu=None)
    assert r["marco_corte_3_meses"] == date(2026, 4, 30)
    assert date(2026, 4, 29) in r["parcelas_rito_expropriacao"]
    assert date(2026, 4, 29) not in r["parcelas_rito_prisao"]


async def test_prescricao_penal_data_estimada_coerente_com_intervalo():
    """Prescrito no 1º intervalo → data estimada é a da CONSUMAÇÃO, não uma data
    futura projetada do último marco."""
    r = await ramos.penal_prescricao(
        data_fato=date(2010, 1, 10), pena_maxima_anos=1.5,
        marcos_interruptivos="2015-01-01", cu=None)
    assert r["prescrito"] is True and r["intervalo_prescrito"] == 1
    assert r["data_prescricao_estimada"] == date(2014, 1, 10)
    assert r["data_prescricao_estimada"] < date.today()
    assert r["prazo_prescricional_base_anos"] == 4


async def test_prescricao_penal_expoe_prazo_base_e_reduzido():
    r = await ramos.penal_prescricao(
        data_fato=date(2025, 1, 10), pena_maxima_anos=0.5,
        menor_21_na_data_fato="sim", cu=None)
    assert r["prazo_prescricional_base_anos"] == 3        # tabela do art. 109
    assert r["prazo_prescricional_anos"] == 1.5           # após o art. 115
    assert r["prazo_prescricional_meses"] == 18
    assert "art. 115" in r["memoria_prazo"]


# ══════════════════════════════════════════════════════════════════════════
# FASE D — matriz: semântica única de casamento de caminho
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("caminho", [
    "/penal/ferramentas/dosimetria",
    "/API/penal/ferramentas/dosimetria/",
    "  /penal/ferramentas/dosimetria  ",
    "//Penal//Ferramentas//Dosimetria",
])
def test_selo_e_gate_usam_a_mesma_normalizacao(caminho):
    from app.services import homologacao_ferramentas as hf
    assert hf.motivo_nao_homologada(caminho)
    assert hf.selo_homologacao(caminho, {})["homologada"] is False


def test_bloqueio_fora_da_matriz_nao_devolve_503_silencioso():
    from app.services import homologacao_ferramentas as hf
    with pytest.raises(KeyError):
        hf.bloquear_nao_homologada("/ferramenta/que/nao/existe")


# ══════════════════════════════════════════════════════════════════════════
# FASE D — ferramentas antes sem metadados: caso feliz + 422 + exceção legal
# ══════════════════════════════════════════════════════════════════════════
async def test_lgpd_multa_teto_e_rejeita_negativo():
    r = await ramos.lgpd_multa(faturamento_anual=10_000_000.0, cu=None)
    assert r["multa_2pct"] == 200_000.0 and r["e_apenas_teto"] is True
    grande = await ramos.lgpd_multa(faturamento_anual=10_000_000_000.0, cu=None)
    assert grande["teto_por_infracao"] == 50_000_000.0        # teto por infração
    assert grande["limitada_ao_teto_50mi"] is True
    with pytest.raises(HTTPException) as e:
        await ramos.lgpd_multa(faturamento_anual=-1.0, cu=None)
    assert e.value.status_code == 422
    _assert_metadados_regra(r)


async def test_lgpd_prazos_incidente_valor_canonico_e_alias():
    novo = await ramos.lgpd_prazos(tipo="incidente", data_conhecimento=date(2026, 3, 2), cu=None)
    legado = await ramos.lgpd_prazos(tipo="incidente_anpd",
                                     data_conhecimento=date(2026, 3, 2), cu=None)
    assert novo["tipo"] == legado["tipo"] == "incidente"      # alias normalizado
    assert novo["prazo_final"] == date(2026, 3, 5)


async def test_alimentos_calcular_sem_percentual_sugerido():
    r = await ramos.civ_alimentos(salario_devedor=5_000.0, percentual=30.0, filhos=2, cu=None)
    assert r["valor_mensal"] == 1_500.0
    assert r["sem_percentual_sugerido"] is True
    assert len(r["binomio_necessidade_possibilidade"]) == 3
    with pytest.raises(HTTPException) as e:
        await ramos.civ_alimentos(salario_devedor=-1.0, percentual=30.0, cu=None)
    assert e.value.status_code == 422
    _assert_metadados_regra(r)


async def test_usucapiao_prazos_por_modalidade_e_reducoes():
    r = await ramos.civ_usucapiao(tipo="extraordinaria", anos_posse=16.0, cu=None)
    assert r["prazo_minimo_anos"] == 15 and r["viavel_preliminarmente"] is True
    assert "10 anos" in r["requisitos"]["prazo_reduzido"]
    fam = await ramos.civ_usucapiao(tipo="familiar", anos_posse=1.0, cu=None)
    assert fam["prazo_minimo_anos"] == 2 and fam["preenche_prazo"] is False
    with pytest.raises(HTTPException) as e:
        await ramos.civ_usucapiao(tipo="extraordinaria", anos_posse=-1.0, cu=None)
    assert e.value.status_code == 422
    _assert_metadados_regra(r)


async def test_reajuste_aluguel_exige_indice_e_respeita_anualidade():
    r = await ramos.imobiliario_reajuste_aluguel(
        valor_atual=2_000.0, indice_percentual=5.0, indice_nome="IGP-M/FGV",
        data_base=date(2024, 1, 10), cu=None)
    assert r["valor_reajustado"] == 2_100.0 and r["periodicidade_anual_cumprida"] is True
    cedo = await ramos.imobiliario_reajuste_aluguel(
        valor_atual=2_000.0, indice_percentual=5.0, indice_nome="IPCA/IBGE",
        data_base=date(2026, 6, 1), cu=None)
    assert cedo["periodicidade_anual_cumprida"] is False
    assert cedo["valor_reajustado"] == 2_000.0        # exceção legal: anualidade
    with pytest.raises(HTTPException) as e:
        await ramos.imobiliario_reajuste_aluguel(
            valor_atual=2_000.0, indice_percentual=5.0, indice_nome="  ",
            data_base=date(2024, 1, 10), cu=None)
    assert e.value.status_code == 422


async def test_mandado_seguranca_120_dias_e_vencido():
    r = await ramos.adm_ms(data_ato_coator=date(2026, 6, 1), cu=None)
    assert r["prazo_impetracao"] == date(2026, 9, 29)
    assert r["vencido"] is False and "DECADENCIAL" in r["natureza_do_prazo"]
    velho = await ramos.adm_ms(data_ato_coator=date(2020, 1, 1), cu=None)
    assert velho["vencido"] is True and velho["dias_desde_o_vencimento"] > 0
    assert velho["urgente"] is False                  # vencido ≠ urgente
    _assert_metadados_regra(r)


async def test_superendividamento_minimo_existencial_25pct_sm():
    r = await ramos.ban_superendiv(renda_mensal=3_000.0, total_parcelas_mes=2_900.0, cu=None)
    esperado = round(ramos._sm_vigente() * 0.25, 2)
    assert r["minimo_existencial_referencia"] == esperado
    assert "25%" in r["criterio_minimo_existencial"]
    assert r["compromete_minimo_existencial"] is True
    assert "não há percentual legal" in r["nota_criterio"].lower()
    with pytest.raises(HTTPException) as e:
        await ramos.ban_superendiv(renda_mensal=0.0, total_parcelas_mes=100.0, cu=None)
    assert e.value.status_code == 422
    _assert_metadados_regra(r)


async def test_valor_multa_transito_multiplicador_valido():
    r = await ramos.transito_valor_multa(gravidade="gravissima", multiplicador=3, cu=None)
    assert r["valor_total"] == round(293.47 * 3, 2)
    assert r["vigencia_tabela"] and r["fonte"]
    with pytest.raises(HTTPException) as e:
        await ramos.transito_valor_multa(gravidade="leve", multiplicador=3, cu=None)
    assert e.value.status_code == 422                 # multiplicador só p/ gravíssima
    _assert_metadados_regra(r)


async def test_reajuste_contrato_administrativo_exige_indice_e_data_base():
    r = await ramos.adm_reajuste_contrato(
        valor_original=100_000.0, indice_acumulado_pct=5.0, meses_contrato=12,
        indice_nome="IPCA/IBGE", data_base=date(2025, 1, 10), cu=None)
    assert r["valor_do_reajuste"] == 5_000.0
    assert r["indice_nome"] == "IPCA/IBGE"
    assert r["proximo_aniversario_data_base"] == date(2026, 1, 10)
    with pytest.raises(HTTPException) as e:
        await ramos.adm_reajuste_contrato(
            valor_original=100_000.0, indice_acumulado_pct=5.0, meses_contrato=12,
            indice_nome="", data_base=date(2025, 1, 10), cu=None)
    assert e.value.status_code == 422
    _assert_metadados_regra(r)


async def test_taxas_bacen_degrada_graciosamente(monkeypatch):
    from app.services import bcb_service

    async def falha():
        raise RuntimeError("SGS fora do ar")

    monkeypatch.setattr(bcb_service, "painel_taxas", falha)
    r = await ramos.bancario_taxas_bacen(cu=None)
    assert r["dados_disponiveis"] is False
    assert r["indisponibilidade"]
    assert r["taxas"] == {}
    _assert_metadados_regra(r)


async def test_reforma_tributaria_estimativa_nao_vinculante():
    r = await ramos.trib_reforma_tributaria(
        receita_bruta_anual=1_000_000.0, regime_atual="simples",
        atividade="servicos", ano_analise="2026", cu=None)
    assert r["estimativa_nao_vinculante"] is True
    assert "NÃO VINCULANTE" in r["estimativa_informativa_iva_pleno"]["carater"]
    # Ferramenta INFORMATIVA (não é minuta de cálculo): valida só os metadados.
    assert r["fontes"] and r["vigencia_regra"] and r["versao_regra"] == "2026-07"
    assert "Revisão humana obrigatória" in r["aviso"]


async def test_auto_infracao_ambiental_prescricao_dec_6514():
    r = await ramos.amb_auto_infracao(
        data_ciencia=date(2026, 3, 2), valor_multa=10_000.0,
        tipo_infracao="degradacao", cu=None)
    assert "art. 21" in r["prescricao_administrativa"]
    assert "3 anos" in r["prescricao_administrativa"]     # intercorrente
    _assert_metadados_regra(r)


@pytest.mark.parametrize("chamada", [
    lambda: ramos.civ_partilha_divorcio(regime_bens="comunhao_parcial", cu=None),
    lambda: ramos.civ_prescricao_consumidor(data_fato=date(2024, 6, 15),
                                            tipo_vicio="fato_produto", cu=None),
    lambda: ramos.civ_rescisao_locacao(
        data_inicio=date(2025, 1, 10), data_rescisao_pretendida=date(2026, 1, 10),
        valor_aluguel=2_000.0, prazo_contrato_meses=30,
        multa_contratual_alugueis=3.0, cu=None),
    lambda: ramos.trib_prescricao_decadencia(data_fato_gerador=date(2024, 3, 10),
                                             tipo="homologacao", cu=None),
    lambda: ramos.trib_auto_infracao_prazos(data_ciencia=date(2026, 3, 2),
                                            valor_multa=1_000.0, cu=None),
    lambda: ramos.trib_regime_tributario(receita_bruta_anual=1_000_000.0,
                                         lucro_estimado_pct=20.0, cu=None),
    lambda: ramos.amb_crimes_ambientais(tipo_crime="poluicao", cu=None),
    lambda: ramos.amb_tac(tipo_dano="desmatamento", cu=None),
    lambda: ramos.amb_licenciamento(uf="MG", cu=None),
    lambda: ramos.amb_reserva_legal(area_imovel_ha=100.0, uf="MG", cu=None),
    lambda: ramos.previdenciario_tempo_contribuicao(idade=62, tempo_contribuicao_anos=35.0,
                                                    sexo="M", cu=None),
    lambda: ramos.ban_ba(data_notificacao=date(2026, 3, 2), valor_divida=10_000.0,
                         bem_descricao="veículo", cu=None),
    lambda: ramos.trab_verbas_rescisorias(
        salario=3_000.0, data_admissao=date(2024, 1, 5), data_demissao=date(2026, 1, 20),
        saldo_fgts=6_000.0, cu=None),
])
async def test_fase_d_ferramentas_carimbam_metadados(chamada):
    r = await chamada()
    assert r["fontes"] and isinstance(r["fontes"], list)
    assert r["vigencia_regra"] and r["versao_regra"] == "2026-07"
    # Disclaimer HITL: "MINUTA" nas calculadoras; ferramentas informativas usam
    # "ESTIMATIVA/INFORMATIVO" + revisão humana obrigatória.
    aviso = r.get("aviso", "")
    assert "MINUTA" in aviso or "Revisão humana obrigatória" in aviso


# ══════════════════════════════════════════════════════════════════════════
# ONDA 3 §4.5 — duplicatas anunciam depreciação (sem mudar o resultado)
# ══════════════════════════════════════════════════════════════════════════
def test_duplicatas_marcadas_deprecated_no_openapi():
    from app.main import app

    esperado = {
        "/api/penal/ferramentas/prescricao-punitiva",
        "/api/admin-esp/ferramentas/recurso-multa-transito",
        "/api/trabalhista/ferramentas/horas-extras",
    }
    depreciadas = {getattr(r, "path", "") for r in app.routes if getattr(r, "deprecated", False)}
    assert esperado <= depreciadas, f"faltam marcadas: {esperado - depreciadas}"
    # As canônicas NÃO podem estar depreciadas.
    for canonica in ("/api/penal/ferramentas/prescricao-penal",
                     "/api/transito/ferramentas/prazos-recurso",
                     "/api/trabalhista-esp/ferramentas/horas-extras"):
        assert canonica not in depreciadas


async def test_duplicata_penal_carimba_cabecalhos_e_campos():
    from fastapi import Response

    resp = Response()
    r = await ramos.pen_prescricao(response=resp, data_fato=date(2022, 5, 1),
                                   pena_maxima_anos=4.0, cu=None)
    assert resp.headers["Deprecation"] == "true"
    assert resp.headers["Sunset"] == ramos._SUNSET_DUPLICATAS
    assert 'rel="successor-version"' in resp.headers["Link"]
    assert r["deprecated"] is True
    assert r["rota_canonica"] == "/penal/ferramentas/prescricao-penal"
    assert "DEPRECIADA" in r["aviso_deprecacao"]


async def test_duplicata_transito_carimba_e_mantem_resultado():
    from fastapi import Response

    kw = dict(fase="defesa_previa", data_notificacao_autuacao=date(2026, 3, 2), cu=None)
    resp = Response()
    dup = await ramos.adm_multa_transito(response=resp, **kw)
    canonica = await ramos.transito_prazos_recurso(**kw)
    assert resp.headers["Deprecation"] == "true"
    assert dup["deprecated"] is True
    assert dup["rota_canonica"] == "/transito/ferramentas/prazos-recurso"
    # Resultado jurídico permanece idêntico ao da canônica.
    assert dup["vencimento"] == canonica["vencimento"]
    assert dup["prazo"] == canonica["prazo"]
