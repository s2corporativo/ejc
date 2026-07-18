"""Calculadoras dos ramos (vitrine ramosConfig.ts) — cobertura mínima por grupo
+ teste de CONTRATO config×rotas.

Contexto (auditoria 2026-07): ~20 cards da vitrine dos ramos apontavam para
endpoints inexistentes (clique → 404 "Falha no cálculo"). Os endpoints foram
implementados em app/routers/ramos.py com os MESMOS paths/params do config.
O teste de contrato no fim deste arquivo impede a regressão: todo `endpoint:`
declarado em frontend/src/pages/ramos/ramosConfig.ts precisa existir como
rota GET real no app montado.
"""
from datetime import date
import os
import re

import pytest

from app.routers import ramos


# ══════════════════════════════════════════════════════════════════════════
# Administrativo — reajuste de contrato administrativo (anualidade, Lei 14.133 art. 92)
# ══════════════════════════════════════════════════════════════════════════
async def test_reajuste_contrato_respeita_anualidade():
    ainda_nao = await ramos.adm_reajuste_contrato(
        valor_original=100_000.0, indice_acumulado_pct=5.0, meses_contrato=10, cu=None,
    )
    assert ainda_nao["elegivel_para_reajuste"] is False
    assert ainda_nao["novo_valor_do_contrato"] == 100_000.0

    ok = await ramos.adm_reajuste_contrato(
        valor_original=100_000.0, indice_acumulado_pct=5.0, meses_contrato=12, cu=None,
    )
    assert ok["elegivel_para_reajuste"] is True
    assert ok["valor_do_reajuste"] == 5_000.0
    assert ok["novo_valor_do_contrato"] == 105_000.0


# ══════════════════════════════════════════════════════════════════════════
# Tributário — faixa e alíquota efetiva do Simples Nacional (LC 123 art. 18 §1º-A)
# ══════════════════════════════════════════════════════════════════════════
async def test_simples_nacional_faixa_2_anexo_iii():
    r = await ramos.trib_simples_nacional(
        receita_bruta_12m=300_000.0, anexo="III", cu=None,
    )
    assert r["faixa"] == 2
    assert r["aliquota_nominal_pct"] == 11.2
    assert r["parcela_a_deduzir"] == 9_360
    # efetiva = (300000×11,2% − 9360) / 300000 = 8,08%
    assert r["aliquota_efetiva_pct"] == pytest.approx(8.08, abs=1e-4)
    assert r["das_mensal_estimado"] == pytest.approx(300_000 / 12 * 0.0808, abs=0.01)


async def test_simples_nacional_primeira_faixa_sem_deducao():
    r = await ramos.trib_simples_nacional(
        receita_bruta_12m=100_000.0, anexo="I", cu=None,
    )
    assert r["faixa"] == 1
    assert r["aliquota_efetiva_pct"] == pytest.approx(4.0)


async def test_simples_nacional_acima_do_teto():
    r = await ramos.trib_simples_nacional(
        receita_bruta_12m=5_000_000.0, anexo="III", cu=None,
    )
    assert r["excede_teto"] is True


async def test_prescricao_decadencia_homologacao_5_anos_do_fg():
    r = await ramos.trib_prescricao_decadencia(
        data_fato_gerador=date(2024, 3, 10), tipo="homologacao", cu=None,
    )
    assert r["data_limite_para_o_fisco_lancar"] == date(2029, 3, 10)
    assert "150" in r["base_legal"]


async def test_prescricao_decadencia_173_i_marco_exercicio_seguinte():
    r = await ramos.trib_prescricao_decadencia(
        data_fato_gerador=date(2024, 3, 10), tipo="credito_nao_constituido", cu=None,
    )
    assert r["marco_inicial"].endswith("(2025-01-01)")
    assert r["data_limite_para_o_fisco_lancar"] == date(2030, 1, 1)


# ══════════════════════════════════════════════════════════════════════════
# Cível — multa proporcional na rescisão de locação (Lei 8.245 art. 4º)
# ══════════════════════════════════════════════════════════════════════════
async def test_rescisao_locacao_multa_proporcional():
    # 12 de 30 meses cumpridos → multa = 3 aluguéis × 18/30 = R$ 3.600,00
    r = await ramos.civ_rescisao_locacao(
        data_inicio=date(2025, 1, 10), data_rescisao_pretendida=date(2026, 1, 10),
        valor_aluguel=2_000.0, tipo_locacao="residencial", quem_rescinde="locatario",
        prazo_contrato_meses=30, multa_contratual_alugueis=3.0, cu=None,
    )
    assert r["meses_cumpridos"] == 12
    assert r["meses_restantes"] == 18
    assert r["multa_proporcional_devida"] == 3_600.0
    assert "8.245" in r["base"]


async def test_rescisao_locacao_contrato_cumprido_sem_multa():
    r = await ramos.civ_rescisao_locacao(
        data_inicio=date(2023, 1, 1), data_rescisao_pretendida=date(2026, 1, 1),
        valor_aluguel=2_000.0, tipo_locacao="residencial", quem_rescinde="locatario",
        prazo_contrato_meses=30, multa_contratual_alugueis=3.0, cu=None,
    )
    assert r["multa_proporcional_devida"] == 0.0
    assert r["contrato_integralmente_cumprido"] is True


async def test_prescricao_consumidor_vicio_30_90_dias():
    r = await ramos.civ_prescricao_consumidor(
        data_fato=date(2026, 1, 1), tipo_vicio="servico_ou_produto", cu=None,
    )
    assert r["instituto"] == "decadência"
    assert r["nao_duravel_30_dias"]["data_limite"] == date(2026, 1, 31)
    assert r["duravel_90_dias"]["data_limite"] == date(2026, 4, 1)


async def test_prescricao_consumidor_fato_do_produto_5_anos():
    r = await ramos.civ_prescricao_consumidor(
        data_fato=date(2024, 6, 15), tipo_vicio="fato_produto", cu=None,
    )
    assert r["data_limite"] == date(2029, 6, 15)
    assert "27" in r["base_legal"]


# ══════════════════════════════════════════════════════════════════════════
# Ambiental — prazo de defesa Dec. 6.514/08 (20 dias, prorroga p/ dia útil)
# ══════════════════════════════════════════════════════════════════════════
async def test_auto_infracao_ambiental_prazo_20_dias_prorrogado():
    # Seg 02/03/2026 + 20 dias corridos = dom 22/03 → prorroga p/ seg 23/03
    r = await ramos.amb_auto_infracao(
        data_ciencia=date(2026, 3, 2), valor_multa=10_000.0,
        tipo_infracao="degradacao", cu=None,
    )
    assert r["vencimento_legal"] == date(2026, 3, 23)
    assert r["pagamento_com_desconto"]["valor_com_desconto"] == 7_000.0
    assert r["conversao_da_multa"]["ate_a_defesa"]["desconto_pct"] == 60
    assert "6.514" in r["base"]


async def test_reserva_legal_percentual_por_bioma():
    r = await ramos.amb_reserva_legal(
        area_imovel_ha=100.0, bioma="amazonia", inscrito_car=True, cu=None,
    )
    assert r["percentual_reserva_legal"] == 80
    assert r["area_reserva_legal_ha"] == 80.0

    r20 = await ramos.amb_reserva_legal(
        area_imovel_ha=100.0, bioma="mata_atlantica", inscrito_car=False, cu=None,
    )
    assert r20["percentual_reserva_legal"] == 20
    assert "OBRIGATÓRIA" in r20["car"]


# ══════════════════════════════════════════════════════════════════════════
# Trabalhista — verbas rescisórias (fachada da calculadora CLT + shape do card)
# ══════════════════════════════════════════════════════════════════════════
async def test_verbas_rescisorias_shape_e_consistencia():
    r = await ramos.trab_verbas_rescisorias(
        salario=3_000.0, data_admissao=date(2024, 1, 5), data_demissao=date(2026, 1, 20),
        tipo_rescisao="sem_justa_causa", saldo_fgts=6_000.0, aviso_previo="indenizado",
        cu=None,
    )
    # Shape exigido pelo VerbaRescisView (RamoBase.tsx)
    esperadas = {"saldo_salario", "aviso_previo", "decimo_terceiro_proporcional",
                 "ferias_proporcionais_mais_um_terco", "fgts_rescisorio_8pct", "multa_fgts"}
    assert set(r["verbas"]) == esperadas
    assert r["total_bruto_estimado"] == pytest.approx(sum(r["verbas"].values()), abs=0.01)
    # 2 anos completos → aviso 30 + 3×2 = 36 dias (Lei 12.506/11)
    assert r["dados_contrato"]["tempo_contrato_anos"] == 2
    assert r["dados_contrato"]["dias_aviso_previo"] == 36
    assert r["verbas"]["aviso_previo"] == pytest.approx(3_000 / 30 * 36, abs=0.01)
    # Multa FGTS 40% sobre o saldo informado
    assert r["verbas"]["multa_fgts"] == pytest.approx(6_000 * 0.40, abs=0.01)
    assert "aviso" in r


async def test_verbas_rescisorias_rescisao_indireta_equivale_sem_justa_causa():
    kw = dict(salario=3_000.0, data_admissao=date(2024, 1, 5),
              data_demissao=date(2026, 1, 20), saldo_fgts=6_000.0,
              aviso_previo="indenizado", cu=None)
    indireta = await ramos.trab_verbas_rescisorias(tipo_rescisao="rescisao_indireta", **kw)
    sem_jc = await ramos.trab_verbas_rescisorias(tipo_rescisao="sem_justa_causa", **kw)
    assert indireta["verbas"] == sem_jc["verbas"]


# ══════════════════════════════════════════════════════════════════════════
# Bancário — painel taxas BACEN (shape do TaxasBacenView; rede mockada)
# ══════════════════════════════════════════════════════════════════════════
async def test_taxas_bacen_shape(monkeypatch):
    from app.services import bcb_service

    async def fake_painel():
        return {ch: {"valor": 10.5, "data": "01/07/2026",
                     "serie_sgs": cfg["codigo"], "nome": cfg["nome"]}
                for ch, cfg in bcb_service.SERIES_PAINEL.items()}

    monkeypatch.setattr(bcb_service, "painel_taxas", fake_painel)
    r = await ramos.bancario_taxas_bacen(cu=None)
    assert set(r["taxas"]) == {"selic_meta_aa", "cdi_diario", "tr_mensal", "ipca_15_mensal"}
    assert all("valor" in v and "data" in v for v in r["taxas"].values())
    assert "aviso" in r


# ══════════════════════════════════════════════════════════════════════════
# Trabalhista — depósito recursal (CLT art. 899 §1º): condenação limitada ao teto
# ══════════════════════════════════════════════════════════════════════════
async def test_deposito_recursal_condenacao_abaixo_do_teto_recolhe_condenacao():
    # Condenação < teto RO → recolhe o valor da condenação (não 50%).
    r = await ramos.trab_deposito(valor_condenacao=8_000.0, cu=None)
    assert r["deposito_ro"] == 8_000.0
    assert r["deposito_rr"] == 8_000.0
    assert r["teto_ro_2026"] == ramos.TETO_DEPOSITO_RO
    assert r["teto_rr_2026"] == ramos.TETO_DEPOSITO_RR


async def test_deposito_recursal_condenacao_1_5x_teto_recolhe_o_teto():
    # Condenação = 1,5× teto RO → depósito do RO é o TETO (não 50% = 0,75× teto,
    # que geraria recurso deserto). RR ainda tem folga (1,5×teto_RO < teto_RR).
    valor = round(ramos.TETO_DEPOSITO_RO * 1.5, 2)   # 18.191,46
    r = await ramos.trab_deposito(valor_condenacao=valor, cu=None)
    assert r["deposito_ro"] == ramos.TETO_DEPOSITO_RO           # limitado ao teto
    assert r["deposito_rr"] == round(valor, 2)                  # abaixo do teto RR
    # Regressão: com a lógica antiga (50%) daria metade do valor → deserto.
    assert r["deposito_ro"] != round(valor * 0.50, 2)


# ══════════════════════════════════════════════════════════════════════════
# Penal — prescrição punitiva: fato em 29/02 não pode estourar ValueError
# ══════════════════════════════════════════════════════════════════════════
async def test_prescricao_punitiva_fato_29_02_nao_quebra():
    # pena 0.5 → prazo 3 anos; 29/02/2020 + 3 = 2023 (NÃO bissexto). A rotina antiga
    # fazia date(2023, 2, 29) e estourava ValueError; o helper corrige → 28/02/2023.
    r = await ramos.pen_prescricao(
        pena_maxima_anos=0.5, data_fato=date(2020, 2, 29), cu=None,
    )
    assert r["prazo_prescricional_anos"] == 3
    assert r["data_prescricao_estimada"] == date(2023, 2, 28)


async def test_prescricao_punitiva_29_02_para_ano_bissexto():
    # pena 2.0 → prazo 4 anos (tabela: não é > 2, mas é > 1); 29/02/2020 + 4 = 2024
    # (bissexto) → mantém 29/02/2024, sem estourar.
    r = await ramos.pen_prescricao(
        pena_maxima_anos=2.0, data_fato=date(2020, 2, 29), cu=None,
    )
    assert r["prazo_prescricional_anos"] == 4
    assert r["data_prescricao_estimada"] == date(2024, 2, 29)


# ══════════════════════════════════════════════════════════════════════════
# Empresarial — CADE art. 88 I e II: exige DOIS grupos (750mi E 75mi)
# ══════════════════════════════════════════════════════════════════════════
async def test_cade_apenas_um_grupo_grande_nao_obriga():
    # Grupo maior ≥ 750mi mas segundo grupo NÃO informado → indeterminado/não obriga.
    r = await ramos.emp_cade(
        valor_faturamento_br=800_000_000.0, valor_operacao=100_000_000.0, cu=None,
    )
    assert r["notificacao_obrigatoria"] is False
    assert r["grupo_maior_atinge_750mi"] is True
    assert r["segundo_grupo_informado"] is False


async def test_cade_segundo_grupo_abaixo_de_75mi_nao_obriga():
    r = await ramos.emp_cade(
        valor_faturamento_br=800_000_000.0, valor_operacao=100_000_000.0,
        valor_faturamento_outro_grupo=50_000_000.0, cu=None,
    )
    assert r["grupo_menor_atinge_75mi"] is False
    assert r["notificacao_obrigatoria"] is False


async def test_cade_dois_grupos_acima_dos_limiares_obriga():
    r = await ramos.emp_cade(
        valor_faturamento_br=800_000_000.0, valor_operacao=100_000_000.0,
        valor_faturamento_outro_grupo=90_000_000.0, cu=None,
    )
    assert r["grupo_maior_atinge_750mi"] is True
    assert r["grupo_menor_atinge_75mi"] is True
    assert r["notificacao_obrigatoria"] is True
    assert r["prazo_notificacao"] is not None


# ══════════════════════════════════════════════════════════════════════════
# CONTRATO config×rotas — todo `endpoint:` do ramosConfig.ts existe no app.
# Impede regressão de "vitrine quebrada" (card renderizado → 404 no clique).
# ══════════════════════════════════════════════════════════════════════════
def _ramos_config_endpoints() -> list[str]:
    here = os.path.dirname(os.path.abspath(__file__))
    cfg = os.path.abspath(os.path.join(
        here, "..", "..", "frontend", "src", "pages", "ramos", "ramosConfig.ts"))
    if not os.path.isfile(cfg):
        return []
    src = open(cfg, encoding="utf-8").read()
    endpoints = re.findall(r'endpoint:\s*"([^"]+)"', src)
    # normaliza: remove querystring e barra final ("/cases/?area=x" → "/cases")
    return sorted({e.split("?")[0].rstrip("/") for e in endpoints})


def test_todos_endpoints_do_ramos_config_existem_no_app():
    endpoints = _ramos_config_endpoints()
    if not endpoints:
        pytest.skip("frontend/src ausente neste checkout — nada a verificar")
    assert len(endpoints) > 50, f"extração suspeita ({len(endpoints)} endpoints)"

    from app.main import app
    rotas_get = {
        (getattr(r, "path", "") or "").rstrip("/")
        for r in app.routes
        if "GET" in (getattr(r, "methods", None) or set())
    }
    faltando = [e for e in endpoints if f"/api{e}" not in rotas_get]
    assert not faltando, (
        f"{len(faltando)} endpoint(s) declarados em ramosConfig.ts SEM rota GET no "
        f"backend (cards renderizam mas o clique dá 404):\n  " + "\n  ".join(faltando)
        + "\nImplemente a rota em app/routers/ramos.py ou remova o card do config."
    )
