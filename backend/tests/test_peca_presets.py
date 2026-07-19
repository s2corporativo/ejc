# ── tests/test_peca_presets.py ────────────────────────────────────────────────
# Integridade das tabelas de preset do gerador de peças e resolução de tipo
# (funções/dados puros — sem IA nem banco).
from app.services.peca_service import (
    TIPOS_PECA,
    TIPOS_PECA_VALIDOS,
    TIPOS_PECA_GRUPO,
    GRUPOS_PECA_VALIDOS,
    TIPO_PECA_LEGAL_DOC,
    TIPOS_PECA_ALIASES,
    ESTRUTURA_TIPO,
    AREAS_DIREITO,
    AREAS_DIREITO_LABEL,
    _tipo_identificado,
)

# Presets adicionados nesta rodada (fase de execução + MS).
_NOVOS = [
    "cumprimento_sentenca",
    "impugnacao_cumprimento",
    "embargos_execucao",
    "mandado_seguranca",
]

# Fase A — lacunas do catálogo preenchidas (sem migration de enum).
_NOVOS_FASE_A = [
    "impugnacao_documentos",
    "manifestacao_preliminares",
    "especificacao_provas",
    "alegacoes_finais",
    "recurso_especial",
    "recurso_extraordinario",
    "resposta_notificacao",
    "confissao_divida",
    "termo_quitacao",
    "distrato",
    "requerimento_administrativo",
    "defesa_administrativa",
    "recurso_administrativo",
    "ata_reuniao",
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


# ── Fase A — invariantes de TIPOS_PECA ────────────────────────────────────────

def test_todo_tipo_valido_tem_grupo_valido():
    faltando = [t for t in TIPOS_PECA_VALIDOS if t not in TIPOS_PECA_GRUPO]
    assert not faltando, f"tipos sem grupo em TIPOS_PECA_GRUPO: {faltando}"
    for t in TIPOS_PECA_VALIDOS:
        assert TIPOS_PECA_GRUPO[t] in GRUPOS_PECA_VALIDOS, \
            f"tipo '{t}' com grupo inválido: {TIPOS_PECA_GRUPO[t]}"


def test_grupo_nao_referencia_tipo_inexistente():
    # Anti-drift: grupo mapeando chave que não é tipo válido (ex.: 'auto').
    orfaos = [t for t in TIPOS_PECA_GRUPO if t not in TIPOS_PECA_VALIDOS]
    assert not orfaos, f"grupo referencia tipos inexistentes: {orfaos}"


def test_todo_tipo_judicial_tem_estrutura_com_base_legal():
    # Tipos judiciais (não-extrajudiciais) precisam de roteiro estrutural na
    # etapa 7. Extrajudiciais seguem template próprio, não CPC — ficam de fora.
    for t in TIPOS_PECA_VALIDOS:
        if TIPOS_PECA_GRUPO[t] == "extrajudicial":
            continue
        assert t in ESTRUTURA_TIPO and len(ESTRUTURA_TIPO[t]) > 40, \
            f"tipo judicial '{t}' sem roteiro em ESTRUTURA_TIPO"


def test_todo_tipo_valido_tem_mapeamento_legal_doc_fase_a():
    faltando = [t for t in TIPOS_PECA_VALIDOS if t not in TIPO_PECA_LEGAL_DOC]
    assert not faltando, f"tipos sem TIPO_PECA_LEGAL_DOC: {faltando}"


def test_todo_alias_aponta_para_tipo_valido():
    invalidos = {a: v for a, v in TIPOS_PECA_ALIASES.items() if v not in TIPOS_PECA_VALIDOS}
    assert not invalidos, f"aliases apontando p/ tipo inexistente: {invalidos}"


def test_aliases_normalizados_sem_acento_e_minusculos():
    import unicodedata
    for alias in TIPOS_PECA_ALIASES:
        assert alias == alias.lower(), f"alias '{alias}' não está em minúsculas"
        sem_acento = "".join(
            c for c in unicodedata.normalize("NFKD", alias) if not unicodedata.combining(c)
        )
        assert alias == sem_acento, f"alias '{alias}' contém acento (não casaria no matcher)"


def test_novos_fase_a_registrados_completos():
    for t in _NOVOS_FASE_A:
        assert t in TIPOS_PECA_VALIDOS, f"'{t}' ausente de TIPOS_PECA"
        assert t in TIPOS_PECA_GRUPO, f"'{t}' sem grupo"
        assert t in TIPO_PECA_LEGAL_DOC, f"'{t}' sem mapeamento p/ enum PecaTipo"


def test_novos_fase_a_resolvem_pela_chave_sem_colisao():
    # A etapa 1 pode devolver o próprio value (via JSON tipo_confirmado): a
    # forma-chave normalizada deve resolver para ELA MESMA, não para um genérico.
    for t in _NOVOS_FASE_A:
        assert _tipo_identificado(t) == t, f"'{t}' não resolveu pela chave"
        assert _tipo_identificado('{"tipo_confirmado": "%s"}' % t) == t


def test_novos_fase_a_resolvem_pelo_label():
    for t in _NOVOS_FASE_A:
        label = TIPOS_PECA[t]
        assert _tipo_identificado(label) == t, \
            f"label '{label}' resolveu para {_tipo_identificado(label)}, esperado {t}"


def test_colisao_substring_impugnacao_documentos_vs_generica():
    # "impugnacao" genérica NÃO pode sombrear "impugnacao a documentos".
    assert _tipo_identificado("impugnação aos documentos juntados pela ré") == "impugnacao_documentos"
    # e a genérica isolada continua resolvendo para 'impugnacao'.
    assert _tipo_identificado("impugnação") == "impugnacao"


def test_colisao_recurso_especial_extraordinario_vs_ordinario():
    assert _tipo_identificado("interpõe recurso especial ao STJ") == "recurso_especial"
    assert _tipo_identificado("recurso extraordinário ao STF") == "recurso_extraordinario"
    assert _tipo_identificado("recurso ordinário trabalhista") == "recurso_ordinario"


def test_colisao_defesa_administrativa_vs_contestacao():
    # "defesa" sozinha = contestação; "defesa administrativa" tem tipo próprio.
    assert _tipo_identificado("apresenta defesa") == "contestacao"
    assert _tipo_identificado("defesa administrativa ao auto de infração") == "defesa_administrativa"


def test_colisao_resposta_notificacao_vs_notificacao():
    assert _tipo_identificado("resposta à notificação extrajudicial recebida") == "resposta_notificacao"
    assert _tipo_identificado("enviar notificação extrajudicial") == "notificacao"


def test_areas_label_cobre_todas_as_areas():
    faltando = [a for a in AREAS_DIREITO if a not in AREAS_DIREITO_LABEL]
    assert not faltando, f"áreas sem rótulo em AREAS_DIREITO_LABEL: {faltando}"
    assert len(AREAS_DIREITO) == 17, f"esperado 17 áreas, achou {len(AREAS_DIREITO)}"
