# ── tests/test_peca_presets.py ────────────────────────────────────────────────
# Integridade das tabelas de preset do gerador de peças e resolução de tipo
# (funções/dados puros — sem IA nem banco).
from app.services.peca_service import (
    TIPOS_PECA_VALIDOS,
    TIPO_PECA_LEGAL_DOC,
    ESTRUTURA_TIPO,
    _tipo_identificado,
)

# Presets adicionados nesta rodada (fase de execução + MS).
_NOVOS = [
    "cumprimento_sentenca",
    "impugnacao_cumprimento",
    "embargos_execucao",
    "mandado_seguranca",
]


def test_todo_tipo_valido_tem_mapeamento_legal_doc():
    faltando = [t for t in TIPOS_PECA_VALIDOS if t not in TIPO_PECA_LEGAL_DOC]
    assert not faltando, f"tipos sem TIPO_PECA_LEGAL_DOC: {faltando}"


def test_novos_presets_registrados_com_roteiro():
    for t in _NOVOS:
        assert t in TIPOS_PECA_VALIDOS
        assert t in TIPO_PECA_LEGAL_DOC
        assert t in ESTRUTURA_TIPO and len(ESTRUTURA_TIPO[t]) > 40


def test_roteiros_citam_base_legal():
    # Cada roteiro dos novos deve ancorar em dispositivo (CPC/Lei) — evita
    # preset "solto" sem espinha processual.
    assert "523" in ESTRUTURA_TIPO["cumprimento_sentenca"]
    assert "525" in ESTRUTURA_TIPO["impugnacao_cumprimento"]
    assert "91" in ESTRUTURA_TIPO["embargos_execucao"]        # arts. 914-917
    assert "12.016" in ESTRUTURA_TIPO["mandado_seguranca"]


def test_tipo_identificado_por_json():
    assert _tipo_identificado('{"tipo_confirmado": "cumprimento_sentenca"}') == "cumprimento_sentenca"
    assert _tipo_identificado('{"tipo": "mandado_seguranca"}') == "mandado_seguranca"


def test_tipo_identificado_por_texto_livre_com_acento():
    assert _tipo_identificado("Trata-se de mandado de segurança contra ato coator.") == "mandado_seguranca"
    assert _tipo_identificado("impugnação ao cumprimento de sentença") == "impugnacao_cumprimento"
    assert _tipo_identificado("embargos à execução fiscal") == "embargos_execucao"


def test_embargos_ambiguo_resolve_declaracao_por_padrao():
    # "embargos" sozinho continua = embargos de declaração (mais frequente);
    # embargos à execução exige o termo especifico.
    assert _tipo_identificado("oponho embargos") == "embargos_declaracao"
