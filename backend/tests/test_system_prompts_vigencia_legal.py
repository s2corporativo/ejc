"""Invariantes de vigência legal dos system prompts (auditoria de 2026-08-15, #1150).

Regressão dos achados P0/P1 da auditoria: o prompt não pode ensinar ao modelo
regra revogada com aparência de fonte. Cada asserção nomeia a lei que fixa a
regra atual — se um dia a lei mudar, o teste é o lugar onde isso aparece.
"""

from app.services.system_prompts.ambiental import PROMPT_AMBIENTAL
from app.services.system_prompts.civel import PROMPT_CIVEL
from app.services.system_prompts.contratual import PROMPT_CONTRATUAL
from app.services.system_prompts.honorarios import PROMPT_HONORARIOS
from app.services.system_prompts.padrao_ouro import PADRAO_OURO_PECA
from app.services.system_prompts.prazos import PROMPT_PRAZOS


# --- P0: contagem de prazos ------------------------------------------------

def test_prazo_trabalhista_e_contado_em_dias_uteis_apos_reforma_de_2017():
    """CLT art. 775, red. Lei 13.467/2017: prazos trabalhistas em dias úteis."""
    assert "CLT art. 775 = corridos" not in PROMPT_PRAZOS
    assert "CLT art. 775 (red. Lei 13.467/2017) = dias ÚTEIS" in PROMPT_PRAZOS


def test_prazos_recursais_trabalhistas_nao_sao_corridos():
    """RO (CLT 895) e ED (CLT 897-A) seguem a contagem do art. 775: dias úteis."""
    assert "8 corridos" not in PROMPT_PRAZOS
    assert "5 corridos" not in PROMPT_PRAZOS
    assert "Recurso Ordinário TRT→TST 8 ÚTEIS" in PROMPT_PRAZOS
    assert "ED trabalhistas 5 ÚTEIS" in PROMPT_PRAZOS


def test_prazo_do_jec_e_contado_em_dias_uteis_desde_a_lei_13728_de_2018():
    """Lei 9.099/95 art. 12-A, incluído pela Lei 13.728/2018."""
    assert "JEC (Lei 9.099/95) = corridos" not in PROMPT_PRAZOS
    assert "art. 12-A" in PROMPT_PRAZOS
    assert "Lei 13.728/2018" in PROMPT_PRAZOS


def test_recesso_forense_alcanca_o_prazo_trabalhista():
    """CLT art. 775-A (incl. Lei 13.467/2017) — não só o CPC art. 220."""
    assert "CLT art. 775-A" in PROMPT_PRAZOS


def test_prazo_administrativo_federal_nao_e_apresentado_como_dias_uteis():
    """Dec. 6.514/2008 não fixa dias úteis; a regra subsidiária (Lei 9.784/1999
    art. 66) é de dias contínuos. Contar como útil alonga o prazo e arrisca a
    intempestividade da defesa."""
    assert "IBAMA/Administrativo = úteis" not in PROMPT_PRAZOS
    assert "Administrativo federal/IBAMA = CORRIDOS" in PROMPT_PRAZOS
    assert "Lei 9.784/1999 art. 66" in PROMPT_PRAZOS

    assert "dias ÚTEIS, FATAIS" not in PROMPT_AMBIENTAL
    assert "dias CORRIDOS, FATAIS" in PROMPT_AMBIENTAL
    assert "Lei 9.784/1999 art. 66" in PROMPT_AMBIENTAL


# --- P1: honorários --------------------------------------------------------

def test_honorarios_citam_o_codigo_de_etica_vigente():
    """CED vigente é a Res. CFOAB 02/2015; o CED de 1995 (arts. 38/39) está revogado."""
    assert "CED arts. 38/39" not in PROMPT_HONORARIOS
    assert "Res. CFOAB 02/2015" in PROMPT_HONORARIOS
    assert "arts. 48-50" in PROMPT_HONORARIOS


def test_titularidade_da_sucumbencia_cita_o_artigo_23_do_estatuto():
    """Lei 8.906/94 art. 23 (titularidade); art. 22 §4º é pagamento direto."""
    assert "titularidade do advogado, art. 22 §4º EOAB" not in PROMPT_HONORARIOS
    assert "titularidade do advogado, art. 23 EOAB" in PROMPT_HONORARIOS


def test_vedacao_de_garantia_de_resultado_nao_se_funda_no_artigo_34_xx():
    """Art. 34, XX do EOAB é locupletamento; a vedação vem do CED e do Prov. 205/2021."""
    assert "art. 34, XX EOAB" not in PROMPT_HONORARIOS
    assert "Provimento CFOAB 205/2021" in PROMPT_HONORARIOS


def test_foro_de_eleicao_exige_pertinencia():
    """CPC art. 63, red. Lei 14.879/2024."""
    assert "Lei 14.879/2024" in PROMPT_HONORARIOS


# --- P1: juros e correção (Lei 14.905/2024) --------------------------------

def test_regra_supletiva_de_juros_e_correcao_esta_nos_prompts_patrimoniais():
    """Desde 30/08/2024: correção IPCA (CC 389 § único) e juros SELIC−IPCA
    (CC 406 §1º). Sem isso, o pedido condenatório sai no padrão antigo."""
    for prompt in (PROMPT_CIVEL, PROMPT_CONTRATUAL, PADRAO_OURO_PECA):
        assert "Lei 14.905/2024" in prompt
        assert "IPCA" in prompt
        assert "SELIC" in prompt


def test_prompts_nao_presumem_juros_de_um_por_cento_ao_mes():
    for prompt in (PROMPT_CIVEL, PADRAO_OURO_PECA):
        assert "presum" in prompt.lower()
        assert "1% ao mês" in prompt
