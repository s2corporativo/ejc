"""Marca de origem-IA que VIAJA com o documento + dados FIXOS do escritório.

Auditoria de geração de documentos:
  (A/B) OAB, endereço, CEP e CNPJ do escritório vêm da FONTE ÚNICA (settings
        ESCRITORIO_*); vazios no .env viram placeholder EXPLÍCITO, nunca dado
        inventado nem "A PREENCHER" mudo.
  (C)   O aviso de rascunho-IA agora é EMBUTIDO no PDF/DOCX exportado quando a
        peça é ai_generated e ainda NÃO foi human_reviewed (minuta não revisada);
        a versão revisada sai LIMPA. Sem gate de bloqueio no download.
"""
from __future__ import annotations

import io

from app.core.config import Settings, get_settings
from app.services.document_format import marca_minuta_ia
from app.services.docx_service import gerar_docx
from app.services.pdf_service import _texto_peca_para_html


_MARCA = "MINUTA GERADA POR IA"


# ── (C) DOCX: a marca viaja com o arquivo, condicional à revisão ──────────────
def test_docx_minuta_nao_revisada_contem_marca_ia():
    dados = gerar_docx("Petição Inicial", "# Petição\n\nCorpo.", meta={"minuta_ia": True})
    doc = _abrir_docx(dados)
    texto = "\n".join(p.text for p in doc.paragraphs)
    assert _MARCA in texto
    assert "NAO PROTOCOLAR SEM REVISAO" in texto


def test_docx_peca_revisada_sai_limpa_sem_marca_ia():
    # human_reviewed=True → o router não seta minuta_ia; versão final limpa.
    dados = gerar_docx("Petição Inicial", "# Petição\n\nCorpo.", meta={"minuta_ia": False})
    doc = _abrir_docx(dados)
    texto = "\n".join(p.text for p in doc.paragraphs)
    assert _MARCA not in texto


def test_docx_sem_meta_nao_marca_como_minuta_ia():
    dados = gerar_docx("Documento", "corpo", meta=None)
    doc = _abrir_docx(dados)
    texto = "\n".join(p.text for p in doc.paragraphs)
    assert _MARCA not in texto


# ── (C) PDF (caminho HTML puro, sem depender de weasyprint) ───────────────────
def test_pdf_html_minuta_nao_revisada_contem_marca_ia():
    html = _texto_peca_para_html("Petição", "DOS FATOS\n\nCorpo.", minuta_ia=True)
    assert _MARCA in html
    assert 'class="ia-minuta"' in html


def test_pdf_html_peca_revisada_sai_limpa_sem_marca_ia():
    html = _texto_peca_para_html("Petição", "DOS FATOS\n\nCorpo.", minuta_ia=False)
    assert _MARCA not in html
    assert "ia-minuta" not in html


# ── (A/B) Dados FIXOS do escritório: fonte única + fallback explícito ─────────
def test_placeholder_explicito_quando_setting_vazia():
    # Vazio no .env → placeholder VISÍVEL, nunca string vazia silenciosa.
    assert Settings._ou_placeholder("", "OAB/MG nº ___") == "[OAB/MG nº ___ - preencher em .env]"
    assert Settings._ou_placeholder("   ", "CEP") == "[CEP - preencher em .env]"


def test_setting_preenchida_e_usada_sem_placeholder():
    assert Settings._ou_placeholder("  12.345 ", "OAB/MG nº ___") == "12.345"


def test_helpers_escritorio_nunca_retornam_vazio():
    s = get_settings()
    for valor in (s.escritorio_oab(), s.escritorio_endereco(), s.escritorio_cep()):
        assert valor and valor.strip()


def test_docx_timbre_traz_oab_e_endereco_do_escritorio():
    from app.services import docx_service

    dados = gerar_docx("Peça", "corpo", meta=None)
    doc = _abrir_docx(dados)
    header = doc.sections[0].header
    texto_header = "\n".join(p.text for p in header.paragraphs)
    assert "OAB/MG" in texto_header
    assert docx_service.settings.escritorio_endereco() in texto_header


def test_procuracao_usa_dados_do_escritorio_e_remove_placeholders_legados():
    from app.models.case import Case
    from app.models.client import Client
    from app.services.documental import _procuracao

    s = get_settings()
    case = Case(titulo="Cobranca X", numero_processo=None)
    cli = Client(nome="Fulano de Tal")
    texto = _procuracao(case, cli, "Dra. Beltrana")

    # Dados FIXOS agora vêm das settings (nome + cidade/UF de assinatura).
    assert s.ESCRITORIO_NOME in texto
    assert f"{s.ESCRITORIO_CIDADE}/{s.ESCRITORIO_ESTADO}," in texto
    # Placeholders legados de dado FIXO NÃO escapam mais para o documento.
    assert "[OAB/MG no ____]" not in texto
    assert "[endereco do escritorio]" not in texto
    assert "[Cidade]/MG" not in texto
    # A DATA depende do caso e permanece placeholder de revisão.
    assert "[data]" in texto


def _abrir_docx(dados: bytes):
    assert isinstance(dados, bytes) and dados[:2] == b"PK"
    from docx import Document

    return Document(io.BytesIO(dados))
