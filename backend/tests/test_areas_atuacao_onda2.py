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
    r = await ramos.trab_deposito(valor_condenacao=50_000.0,
                                  data_referencia=date(2026, 7, 1), cu=None)
    assert r["deposito_ro"] == ramos.TETO_DEPOSITO_RO    # condenação > teto → teto
    assert r["teto_ro"] == 12_127.64 and r["teto_rr"] == 24_255.28
    assert "323/2025" in r["fonte"]
    assert r["vigencia_tabela"].startswith("2025-08-01")
    _assert_metadados_regra(r)


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
    admin = await ramos.adm_multa_transito(**kw)
    transito = await ramos.transito_prazos_recurso(**kw)
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
