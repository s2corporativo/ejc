# ── tests/test_ia_parser.py ──────────────────────────────────────────────────
# BUG-03: extração segura de título de caso a partir de respostas de IA.
from app.services.ia_parser import (
    extrair_titulo_caso,
    sanitizar_resposta_ia,
    titulo_e_json_bruto,
)

FALLBACK = "Caso sem título (revisar manualmente)"


# ── JSON válido ───────────────────────────────────────────────────────────────

def test_json_valido_titulo():
    r = '{"titulo": "Ação de Cobrança c/c Danos Morais", "area": "civil"}'
    assert extrair_titulo_caso(r) == "Ação de Cobrança c/c Danos Morais"


def test_json_valido_assunto():
    r = '{"assunto": "Rescisão indireta", "chance_exito": 70}'
    assert extrair_titulo_caso(r) == "Rescisão indireta"


def test_json_aninhado_identificacao_processual():
    r = '{"identificacao_processual": {"assunto": "Reclamatória Trabalhista"}}'
    assert extrair_titulo_caso(r) == "Reclamatória Trabalhista"


def test_ordem_preferencia_titulo_antes_de_assunto():
    r = '{"assunto": "X", "titulo": "Título Preferido"}'
    assert extrair_titulo_caso(r) == "Título Preferido"


# ── JSON dentro de cercas ```json ─────────────────────────────────────────────

def test_json_com_cercas_fence():
    r = '```json\n{"titulo": "Mandado de Segurança", "area": "administrativo"}\n```'
    assert extrair_titulo_caso(r) == "Mandado de Segurança"


def test_json_com_cerca_generica():
    r = '```\n{"nome": "Habeas Corpus"}\n```'
    assert extrair_titulo_caso(r) == "Habeas Corpus"


def test_json_com_texto_antes_e_depois():
    r = 'Claro! Aqui está:\n{"titulo": "Execução Fiscal"}\nEspero ter ajudado.'
    assert extrair_titulo_caso(r) == "Execução Fiscal"


# ── JSON parcial/quebrado (regex fallback) ────────────────────────────────────

def test_json_quebrado_regex_fallback():
    r = '{"titulo": "Ação Revisional de Contrato", "pontos_fortes": incompl'
    assert extrair_titulo_caso(r) == "Ação Revisional de Contrato"


def test_json_quebrado_sem_titulo_extraivel():
    r = '{"foo": 1, "bar": [1,2,3'  # nada legível
    assert extrair_titulo_caso(r) == FALLBACK


# ── Texto plano ───────────────────────────────────────────────────────────────

def test_texto_plano():
    r = "Ação de Indenização por Acidente de Trânsito"
    assert extrair_titulo_caso(r) == r


def test_texto_plano_multilinha_pega_primeira():
    r = "Ação Trabalhista\n\nDetalhes irrelevantes aqui."
    assert extrair_titulo_caso(r) == "Ação Trabalhista"


def test_texto_plano_truncado_200():
    r = "A" * 500
    out = extrair_titulo_caso(r)
    assert len(out) == 200


# ── Casos de borda ────────────────────────────────────────────────────────────

def test_vazio_retorna_fallback():
    assert extrair_titulo_caso("") == FALLBACK
    assert extrair_titulo_caso("   ") == FALLBACK


def test_none_retorna_fallback():
    assert extrair_titulo_caso(None) == FALLBACK  # type: ignore[arg-type]


def test_json_sem_chave_de_titulo_vira_fallback():
    r = '{"area": "civil", "chance_exito": 50}'
    assert extrair_titulo_caso(r) == FALLBACK


# ── sanitizar_resposta_ia ─────────────────────────────────────────────────────

def test_sanitizar_dict():
    assert sanitizar_resposta_ia('{"a": 1}') == {"a": 1}


def test_sanitizar_fence():
    assert sanitizar_resposta_ia('```json\n{"a": 1}\n```') == {"a": 1}


def test_sanitizar_texto_plano_none():
    assert sanitizar_resposta_ia("apenas texto") is None


def test_sanitizar_lista_none():
    # lista não é dict — retorna None
    assert sanitizar_resposta_ia("[1,2,3]") is None


# ── guard do endpoint ─────────────────────────────────────────────────────────

def test_guard_detecta_json_bruto():
    assert titulo_e_json_bruto('{"titulo": "x"}') is True
    assert titulo_e_json_bruto("[1,2]") is True
    assert titulo_e_json_bruto("```json") is True


def test_guard_aceita_titulo_normal():
    assert titulo_e_json_bruto("Ação de Cobrança") is False
