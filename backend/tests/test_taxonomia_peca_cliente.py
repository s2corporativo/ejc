# ── backend/tests/test_taxonomia_peca_cliente.py ─────────────────────────────
# P2: peças de cliente vindas do Google Drive não podem entrar no RAG
# compartilhado como categoria não-restrita (vazamento cross-client).
# classificar_drive_file é PURO (sem DB) — roda mesmo no sandbox.
from app.services.google_drive_taxonomy import classificar_drive_file


def _cat(nome, caminho=None, mime=None):
    return classificar_drive_file(nome, caminho, mime).categoria


# ── Peça de cliente → peca_interna (categoria RESTRITA / fail-closed no RAG) ──

def test_contestacao_com_numero_cnj_vira_peca_interna():
    dec = classificar_drive_file("Contestação 0801234-56.2023.8.13.0079 Fulano.docx")
    assert dec.categoria == "peca_interna"
    assert dec.excluir is False
    assert dec.tipo_fonte == "peca_cliente_restrita"
    assert any(s.startswith("processo_cnj:") for s in dec.sinais)


def test_numero_cnj_sem_pontuacao_tambem_detecta():
    # NNNNNNN DD AAAA J TR OOOO sem separadores.
    assert _cat("Recurso 08012345620238130079.pdf") == "peca_interna"


def test_pasta_de_cliente_no_caminho_vira_peca_interna():
    assert _cat("Petição inicial.pdf", "Clientes/Fulano de Tal/Petição inicial.pdf") == "peca_interna"


def test_cpf_no_nome_vira_peca_interna():
    # CPF válido por dígito verificador (111.444.777-35).
    dec = classificar_drive_file("Procuração 111.444.777-35.pdf")
    assert dec.categoria == "peca_interna"
    assert "cpf_no_nome" in dec.sinais


def test_cnpj_no_nome_vira_peca_interna():
    # CNPJ válido por dígito verificador (11.222.333/0001-81).
    assert _cat("Contrato 11.222.333/0001-81.pdf") == "peca_interna"


def test_pasta_casos_no_caminho():
    assert _cat("agravo.docx", "Casos/Empresa X/agravo.docx") == "peca_interna"


# ── Falso-positivo numérico: timestamp/ID não é CPF/CNPJ (dígito verificador) ─

def test_timestamp_no_nome_de_modelo_nao_vira_peca_interna():
    # 14 dígitos de timestamp reprovam no dígito verificador de CNPJ → modelo.
    assert _cat("Modelo_Contestacao_20231015093012.pdf") == "modelo_documento_juridico"


def test_id_numerico_invalido_no_modelo_nao_vira_peca_interna():
    # 11 dígitos que não formam CPF válido não disparam restrição.
    assert _cat("Minuta Recurso 12345678901.docx") == "modelo_documento_juridico"


def test_pasta_contencioso_de_biblioteca_de_modelos_nao_vira_peca_interna():
    # "Contencioso" é organização por área de uma biblioteca de modelos, não
    # pasta de cliente — não deve sobre-restringir o modelo genérico.
    assert _cat(
        "peticao.docx", "Modelos/Contencioso Cível/peticao.docx"
    ) == "modelo_documento_juridico"


# ── Modelo genérico → segue modelo_documento_juridico (NÃO vira peca_interna) ─

def test_modelo_generico_permanece_modelo():
    dec = classificar_drive_file("Modelo de Contestação Trabalhista.docx")
    assert dec.categoria == "modelo_documento_juridico"


def test_minuta_generica_permanece_modelo():
    assert _cat("Minuta de Recurso de Apelação.docx") == "modelo_documento_juridico"


# ── Precedência normativa mantida (não viram peca_interna) ───────────────────

def test_sumula_nao_vira_peca_interna():
    assert _cat("Súmula 7 STJ.docx") == "sumula_stj"


def test_lei_nao_vira_peca_interna():
    dec = classificar_drive_file("Lei 8.112.pdf")
    assert dec.categoria != "peca_interna"
    assert dec.categoria.startswith("legislacao")


def test_jurisprudencia_nao_vira_peca_interna():
    dec = classificar_drive_file("Acórdão TJMG sobre honorários.pdf")
    assert dec.categoria != "peca_interna"
    assert dec.categoria.startswith("jurisprudencia")
