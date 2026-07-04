"""Tema Visual Law central — dourado + logomarca De Paula Teixeira.

Garante que os geradores herdam o padrão forense do "Documento Único de
Anexos": banner dourado com logo em tile branco, palavra gigante, linha do
tema, rodapé com o juízo do caso e paleta única em todos os módulos.
"""
from __future__ import annotations

from app.services import visual_law_theme as vlt
from app.services import anexos_service as anx
from app.services.anexos_service import ContextoAnexos, ItemAnexo


def _ctx() -> ContextoAnexos:
    return ContextoAnexos(
        titulo_acao="AÇÃO DE INDENIZAÇÃO — DANOS MORAIS",
        partes="Fulano vs. Beltrano",
        referencia="Reserva 46190319300",
        rodape="Juizado Especial Cível da Comarca de Betim/MG",
    )


# ── Módulo central ────────────────────────────────────────────────────────────

def test_logo_data_uri_embutida_e_cacheada():
    uri = vlt.logo_data_uri()
    assert uri.startswith("data:image/jpeg;base64,")
    assert vlt.logo_data_uri() is uri  # lru_cache — não relê o arquivo


def test_paleta_dourada_oficial():
    assert vlt.OURO_PROFUNDO == "#6F5711"
    assert vlt.OURO == "#8F7117"
    assert vlt.OURO_CLARO == "#C9A227"


def test_banner_dourado_com_logo_em_tile_branco():
    html = vlt.render_banner("AÇÃO DE INDENIZAÇÃO", "Fulano vs. Beltrano — Reserva 123")
    assert "banner-logo-tile" in html          # tile de fundo branco
    assert "data:image/jpeg;base64," in html   # logo embutida (weasyprint offline)
    assert "Fulano vs. Beltrano" in html


def test_capa_tem_palavra_gigante_linha_do_tema_e_legenda():
    html = vlt.render_capa("DOC. 01", "Comprovante de Pagamento",
                           "Comprova o desembolso da diária adicional")
    assert "palavra-gigante" in html and "DOC. 01" in html
    assert "linha-tema" in html
    assert "Comprova o desembolso" in html


def test_rodape_discreto_com_logo_e_juizo():
    html = vlt.render_rodape("Juizado Especial Cível da Comarca de Betim/MG")
    assert "rodape-logo" in html
    assert "Betim/MG" in html


def test_css_tema_sem_azul_antigo():
    css = vlt.css_tema()
    assert vlt.OURO in css and vlt.OURO_PROFUNDO in css
    assert "#22506e" not in css and "#1f4e79" not in css  # azul-marinho antigo fora


# ── Anexos (Documento Único) herda o tema ─────────────────────────────────────

def test_capa_de_anexos_no_tema_dourado_com_logo():
    html = anx.cover_html(_ctx(), [ItemAnexo(ordem=1, titulo="Comprovante PIX")])
    assert vlt.OURO in html                       # cor do tema no CSS
    assert "linear-gradient" in html              # banner dourado
    assert "data:image/jpeg;base64," in html      # logo embutida
    assert "Betim/MG" in html                     # juízo do caso no rodapé
    assert "ANEXOS" in html and "Doc. 01" in html


def test_separador_de_anexos_no_tema_dourado():
    html = anx.separador_html(_ctx(), ItemAnexo(ordem=2, titulo="Contrato", legenda="Prova do vínculo"))
    assert "DOC. 02" in html and "Prova do vínculo" in html
    assert vlt.OURO in html and "data:image/jpeg;base64," in html


# ── pdf_service (peças, relatórios, dossiê de caso, LGPD) herda o tema ────────

def test_pdf_service_html_base_dourado_e_sem_tokens():
    from app.services import pdf_service
    assert vlt.OURO in pdf_service._HTML_BASE
    assert vlt.OURO_PROFUNDO in pdf_service._HTML_BASE
    assert "#1e3a8a" not in pdf_service._HTML_BASE  # azul-marinho antigo fora
    assert "§OURO" not in pdf_service._HTML_BASE    # tokens todos substituídos


# ── Visual Law PDF (Sala de Guerra): weasyprint + stateless ──────────────────

def test_cronologia_nao_acumula_paginas_entre_chamadas(tmp_path):
    """Regressão do bug do singleton FPDF: a instância global acumulava as
    páginas da chamada anterior — o 2º PDF saía com a cronologia do 1º."""
    from pypdf import PdfReader
    from app.services.visual_law_pdf import visual_law_pdf

    eventos = [{"data": "01/01/2026", "evento": "Distribuição da inicial"}]
    p1, p2 = tmp_path / "a.pdf", tmp_path / "b.pdf"
    visual_law_pdf.gerar_cronologia(eventos, str(p1))
    visual_law_pdf.gerar_cronologia(eventos, str(p2))
    assert len(PdfReader(str(p1)).pages) == len(PdfReader(str(p2)).pages) == 1


# ── Diagramas Mermaid recebem o init dourado (determinístico) ─────────────────

def test_mermaid_recebe_init_dourado_idempotente():
    from app.services.visual_law import aplicar_tema_dourado

    out = aplicar_tema_dourado("timeline\n    title Linha do Tempo")
    assert out.startswith("%%{init") and vlt.OURO in out
    assert aplicar_tema_dourado(out) == out  # não duplica o init
