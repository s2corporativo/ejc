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


# ── Review do PR #495 (Codex) — recesso forense, fases e proveniência ─────────

async def test_penal_suspende_contagem_no_recesso():
    """CPP art. 798-A: prazo iniciado antes do recesso não corre de 20/12 a 20/01."""
    citacao = date(2026, 12, 15)
    r = await ramos.pen_prazos(data_citacao=citacao, cu=None)
    vencimento = r["prazos"][0]["data"]
    # Sem suspensão seriam ~25/12; com a suspensão o prazo salta para depois de 20/01.
    assert vencimento > date(2027, 1, 20)
    assert vencimento == prazo_dias_corridos(citacao, 10, suspender_recesso=True)


async def test_trabalhista_aplica_recesso_clt_775a():
    intimacao = date(2026, 12, 15)
    r = await ramos.trab_prazos(data_intimacao=intimacao, cu=None)
    assert r["prazos"][0]["data"] == prazo_dias_uteis(intimacao, 8, aplicar_recesso=True)
    # A janela de 20/12 a 20/01 não pode ser contada como dias úteis.
    assert r["prazos"][0]["data"] > date(2027, 1, 20)


async def test_contestacao_cpc_aplica_recesso():
    citacao = date(2026, 12, 10)
    r = await ramos.civ_prazo_contestacao(data_citacao=citacao, tipo="cpc", cu=None)
    assert r["vencimento"] == prazo_dias_uteis(citacao, 15, aplicar_recesso=True)


async def test_transito_fase_cetran_avalia_o_prazo_do_cetran():
    ciencia = date(2026, 3, 2)
    r = await ramos.transito_prazos_recurso(
        valor_multa=293.47, fase="cetran",
        data_ciencia_decisao_jari=ciencia, cu=None,
    )
    assert r["prazo_avaliado"] == prazo_dias_corridos(ciencia, 30)
    assert r["dias_restantes"] == (prazo_dias_corridos(ciencia, 30) - date.today()).days


async def test_jari_dispensa_a_data_da_autuacao():
    """Quem só tem a notificação da penalidade precisa conseguir calcular a JARI."""
    pen = date(2026, 5, 4)
    r = await ramos.transito_prazos_recurso(
        valor_multa=100.0, fase="penalidade",
        data_notificacao_penalidade=pen, cu=None,
    )
    assert r["prazo_avaliado"] == prazo_dias_corridos(pen, 30)
    assert not isinstance(r["prazo_defesa_previa"], date)


async def test_fase_sem_marco_proprio_e_recusada():
    with pytest.raises(HTTPException) as exc:
        await ramos.transito_prazos_recurso(valor_multa=100.0, fase="cetran", cu=None)
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException):
        await ramos.transito_prazos_recurso(valor_multa=100.0, fase="inexistente", cu=None)


def test_recibo_de_calculo_prova_proveniencia():
    """O demonstrativo não pode confiar no endpoint/números vindos do cliente."""
    from app.core import calculo_recibo

    resultado = {"prazo_final": "2026-04-01", "valor": 1234.5, "aviso": "MINUTA"}
    recibo = calculo_recibo.emitir("/api/transito/ferramentas/prazos-recurso", resultado)

    ok = calculo_recibo.validar(recibo)
    assert ok is not None
    assert ok["endpoint"] == "/transito/ferramentas/prazos-recurso"  # prefixo /api removido
    assert ok["resultado"]["valor"] == 1234.5

    # Adulterar o corpo invalida a assinatura.
    corpo, _, assinatura = recibo.rpartition(".")
    assert calculo_recibo.validar(f"{corpo}x.{assinatura}") is None
    assert calculo_recibo.validar(f"{corpo}.{'0' * len(assinatura)}") is None
    assert calculo_recibo.validar("") is None
    assert calculo_recibo.validar("sem-ponto") is None

    # As linhas do documento saem do resultado assinado, sem rodapé/metadados.
    linhas = dict(calculo_recibo.linhas_do_resultado(ok["resultado"]))
    assert "aviso" not in linhas and "prazo final" in linhas


def test_recibo_expirado_nao_vale():
    import time as _t
    from app.core import calculo_recibo

    original = calculo_recibo.TTL_SEGUNDOS
    try:
        calculo_recibo.TTL_SEGUNDOS = -1  # já nasce vencido
        recibo = calculo_recibo.emitir("/x/ferramentas/y", {"a": 1})
        assert calculo_recibo.validar(recibo) is None
    finally:
        calculo_recibo.TTL_SEGUNDOS = original
    assert _t is not None


def test_route_class_assina_respostas_das_ferramentas():
    """Toda ferramenta de ramos sai assinada — inclusive as futuras."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core import calculo_recibo
    from app.routers.ramos import _ReciboRoute

    app = FastAPI()
    app.router.route_class = _ReciboRoute

    @app.get("/civel/ferramentas/exemplo")
    async def _ferramenta():
        return {"prazo_final": "2026-04-01", "aviso": "MINUTA"}

    @app.get("/civel/nao-e-ferramenta")
    async def _outra():
        return {"ok": True}

    cliente = TestClient(app)

    corpo = cliente.get("/civel/ferramentas/exemplo").json()
    assert "_recibo" in corpo
    assinado = calculo_recibo.validar(corpo["_recibo"])
    assert assinado is not None
    assert assinado["endpoint"] == "/civel/ferramentas/exemplo"
    assert assinado["resultado"]["prazo_final"] == "2026-04-01"

    # Rota que não é ferramenta não recebe recibo.
    assert "_recibo" not in cliente.get("/civel/nao-e-ferramenta").json()


def test_demonstrativo_rejeita_endpoint_alegado_pelo_cliente():
    """Não basta alegar uma ferramenta homologada: o número tem de vir assinado."""
    import inspect

    from app.routers import peca_geracao

    origem = inspect.getsource(peca_geracao.gerar_demonstrativo)
    # O gate consulta o endpoint do RECIBO, nunca um campo do request.
    assert 'status_ferramenta(assinado["endpoint"])' in origem
    assert "req.ferramenta_endpoint" not in origem
    # As linhas do documento derivam do resultado assinado.
    assert 'calculo_recibo.linhas_do_resultado(assinado["resultado"])' in origem
    # E o schema não aceita mais linhas/endpoint vindos do cliente.
    campos = peca_geracao.DemonstrativoRequest.model_fields
    assert "recibo" in campos
    assert "linhas" not in campos and "ferramenta_endpoint" not in campos
