from app.services.system_prompts.tributario import PROMPT_TRIBUTARIO


def test_prompt_exige_marcos_antes_de_calcular_prazo() -> None:
    texto = PROMPT_TRIBUTARIO.casefold()
    assert "sem os marcos necessários, não dê data final" in texto
    assert "sempre calcular" not in texto
    assert "não invente prazo" in texto


def test_prompt_lef_preserva_tres_termos_iniciais_dos_embargos() -> None:
    texto = PROMPT_TRIBUTARIO.casefold()
    assert "depósito" in texto
    assert "fiança bancária/seguro garantia" in texto
    assert "intimação da penhora" in texto
    assert "não resuma automaticamente como \"30 dias da penhora\"" in texto


def test_prompt_paf_federal_reflete_lc_227_2026() -> None:
    texto = PROMPT_TRIBUTARIO.casefold()
    assert "20 dias úteis" in texto
    assert "31/03/2026" in texto
    assert "adi rfb 2/2026" in texto
    assert "geralmente 30 dias" in texto
    assert "nunca usar \"geralmente 30 dias\"" in texto


def test_prompt_reforma_usa_base_normativa_2026_e_rejeita_aliquota_generica() -> None:
    texto = PROMPT_TRIBUTARIO.casefold()
    for referencia in (
        "ec 132/2023",
        "lc 214/2025",
        "lc 227/2026",
        "decreto 12.955/2026",
        "atos rfb/cgibs",
    ):
        assert referencia in texto

    assert "não diga simplesmente\n   que \"cbs substitui o ipi\"" in texto
    assert "nunca aplicar uma alíquota genérica" in texto


def test_prompt_trata_credito_como_hipotese_e_nao_promessa() -> None:
    texto = PROMPT_TRIBUTARIO.casefold()
    assert "oportunidades potenciais" in texto
    assert "não escrever \"últimos 5 anos são recuperáveis\"" in texto
    assert "portal autenticado\n   não é api pública" in texto
