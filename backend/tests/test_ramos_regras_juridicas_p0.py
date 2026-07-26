"""Regressão das correções jurídicas P0 da auditoria de 26/07/2026.

Cobre as calculadoras de app/routers/ramos.py cujas regras estavam
materialmente erradas (prazos JEC/penal/trabalhista, trânsito, RJ, CADE,
juros legais, dobro do CDC, previdenciário) e o anti mass-assignment do
CRUD genérico. As ferramentas são funções puras (sem DB) — chamadas direto.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from app.routers import ramos
from app.services.deadline_calculator import prazo_dias_corridos, prazo_dias_uteis

CIT = date(2026, 3, 2)  # segunda-feira


async def test_jec_nao_inventa_prazo_de_contestacao():
    r = await ramos.civ_prazo_contestacao(data_citacao=CIT, tipo="jec", cu=None)
    assert r["vencimento"] is None
    assert "audiência" in r["base_legal"]


async def test_contestacao_cpc_15_uteis():
    r = await ramos.civ_prazo_contestacao(data_citacao=CIT, tipo="cpc", cu=None)
    assert r["vencimento"] == prazo_dias_uteis(CIT, 15)


async def test_penal_resposta_acusacao_continua_da_citacao():
    r = await ramos.pen_prazos(data_citacao=CIT, cu=None)
    resposta = r["prazos"][0]
    assert resposta["data"] == prazo_dias_corridos(CIT, 10)  # CPP 798: contínuos
    assert "citação" in resposta["base"] or "citacao" in resposta["base"]


async def test_trabalhista_ro_em_dias_uteis_da_intimacao():
    r = await ramos.trab_prazos(data_intimacao=CIT, cu=None)
    ro, deposito, ed = r["prazos"]
    assert ro["data"] == prazo_dias_uteis(CIT, 8)       # CLT 775: úteis
    assert deposito["data"] == prazo_dias_uteis(CIT, 8)
    assert ed["data"] == prazo_dias_uteis(CIT, 5)


async def test_transito_defesa_previa_30_dias_e_jari_exige_marco_proprio():
    r = await ramos.transito_prazos_recurso(
        data_notificacao=CIT, valor_multa=293.47, cu=None,
    )
    assert r["prazo_defesa_previa"] == prazo_dias_corridos(CIT, 30)
    # JARI/CETRAN não derivam mais da autuação: sem o marco próprio, não há data
    assert not isinstance(r["prazo_recurso_jari"], date)
    assert not isinstance(r["prazo_recurso_cetran"], date)
    pen = date(2026, 5, 4)
    r2 = await ramos.transito_prazos_recurso(
        data_notificacao=CIT, valor_multa=293.47,
        data_notificacao_penalidade=pen, cu=None,
    )
    assert r2["prazo_recurso_jari"] == prazo_dias_corridos(pen, 30)


async def test_admin_e_transito_dao_a_mesma_resposta():
    a = await ramos.adm_multa_transito(data_notificacao=CIT, valor_multa=100.0, cu=None)
    t = await ramos.transito_prazos_recurso(data_notificacao=CIT, valor_multa=100.0, cu=None)
    assert a["prazo_defesa_previa"] == t["prazo_defesa_previa"]
    assert a["valor_desconto_20pct"] == t["valor_desconto_20pct"] == 80.0
    assert "risco_suspensao" not in a  # 20 pontos fixos removido


async def test_ear_suspende_apenas_com_40_pontos():
    r = await ramos.transito_pontuacao_cnh(
        pontos_total=35, infracoes_gravissimas_12m=2,
        categoria_profissional="sim", cu=None,
    )
    assert r["limite_aplicavel"] == 40
    assert r["atingiu_limite"] is False


async def test_rj_marcos_contam_do_deferimento_e_supervisao_da_concessao():
    defer = date(2026, 2, 2)
    r = await ramos.emp_prazos_rj(data_deferimento_processamento=defer, cu=None)
    plano = next(p for p in r["prazos"] if "plano" in p["evento"].lower())
    assert plano["data"] == prazo_dias_corridos(defer, 60)
    supervisao = next(p for p in r["prazos"] if "supervisão" in p["evento"].lower())
    assert supervisao["data"] is None  # exige data da concessão


async def test_cade_sem_prazo_ficticio_de_30_dias():
    r = await ramos.emp_cade(
        valor_faturamento_br=800_000_000.0, valor_operacao=1.0,
        valor_faturamento_outro_grupo=80_000_000.0, cu=None,
    )
    assert r["notificacao_obrigatoria"] is True
    assert "30 dias" not in str(r["prazo_notificacao"])
    assert "PRÉVIA" in r["prazo_notificacao"]


async def test_juros_sem_taxa_pactuada_nao_presume_1pct():
    r = await ramos.empresarial_juros_mora(
        valor_principal=10_000.0, meses_atraso=6, cu=None,
    )
    assert r["juros_mora"] is None and r["total_devido"] is None
    assert "14.905" in r["observacao"]
    r2 = await ramos.empresarial_juros_mora(
        valor_principal=10_000.0, meses_atraso=6, taxa_juros_mensal_pct=1.0, cu=None,
    )
    assert r2["juros_mora"] == 600.0 and r2["total_devido"] == 10_800.0


async def test_dobro_cdc_default_sem_ma_fe():
    r = await ramos.consumidor_devolucao_dobro(valor_cobrado=100.0, cu=None)
    assert r["aplica_dobro"] is True and r["restituicao"] == 200.0
    r2 = await ramos.consumidor_devolucao_dobro(
        valor_cobrado=100.0, engano_justificavel="sim", cu=None,
    )
    assert r2["aplica_dobro"] is False and r2["restituicao"] == 100.0


async def test_prescricao_cobranca_indevida_decenal():
    r = await ramos.consumidor_prazos_cdc(
        data_fato=date(2020, 1, 10), tipo="cobranca_indevida", cu=None,
    )
    assert r["prazo_final"].year == 2030  # CC 205 / EAREsp 738.991 (era 3 anos)


async def test_previdenciario_sexo_estrito():
    with pytest.raises(HTTPException):
        await ramos.previdenciario_tempo_contribuicao(
            idade=60, tempo_contribuicao_anos=30, sexo="X", cu=None,
        )
    r = await ramos.previdenciario_tempo_contribuicao(
        idade=60, tempo_contribuicao_anos=30, sexo="Mulher", cu=None,
    )
    assert r["sexo"] == "feminino"  # startswith("M") classificava como homem


async def test_previdenciario_prescricao_e_janela_movel():
    r = await ramos.previdenciario_prazos(
        data_marco=date(2026, 7, 1), tipo="prescricao_parcelas", cu=None,
    )
    assert r["parcelas_prescritas_anteriores_a"] == date(2021, 7, 1)
    assert "prazo_final" not in r


async def test_carencia_maternidade_isenta_para_empregada():
    r = await ramos.previdenciario_carencia(
        meses_contribuicao=0, beneficio="salario_maternidade",
        categoria="empregado", cu=None,
    )
    assert r["carencia_exigida"] == 0 and r["carencia_cumprida"] is True
    r2 = await ramos.previdenciario_carencia(
        meses_contribuicao=8, beneficio="salario_maternidade",
        categoria="contribuinte_individual", cu=None,
    )
    assert r2["carencia_exigida"] == 10 and r2["carencia_cumprida"] is False


def test_crud_patch_nao_expoe_soft_delete_nem_auditoria():
    from app.models.especializado import CivelCase
    protegidos = {"id", "case_id", "created_at", "updated_at", "deleted_at"}
    allowed = {
        c.key for c in CivelCase.__table__.columns
        if c.key not in ("id", "case_id", "created_at", "updated_at",
                         "deleted_at", "created_by", "criado_por")
    }
    assert not (allowed & protegidos)
