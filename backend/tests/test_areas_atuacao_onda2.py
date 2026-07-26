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
    # Mora desde 31/07/2024: 30 dias sob a regra antiga (1 mês × 1%) + regra nova.
    r = await ramos.empresarial_juros_mora(
        regime="legal", valor_principal=1_000.0,
        data_inicio_mora=date(2024, 7, 31), data_fim=date(2025, 7, 31),
        selic_acumulada_percent=10.0, ipca_acumulado_percent=4.0,
        aplicar_regra_anterior="sim", cu=None,
    )
    assert len(r["componentes"]) == 2
    antigo, novo = r["componentes"]
    assert "1% a.m." in antigo["parcela"]
    assert antigo["valor"] == 10.0                # 1000 × 1% × 1 mês
    assert novo["valor"] == 60.0                  # 1000 × (10% − 4%)
    assert r["juros_mora_total"] == 70.0


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
    kw = dict(data_fato=date(2022, 5, 1), pena_maxima_anos=4.0, cu=None)
    canonica = await ramos.penal_prescricao(**kw)
    duplicata = await ramos.pen_prescricao(**kw)
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
