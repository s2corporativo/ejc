# ── app/services/visual_law_theme.py ──────────────────────────────────────────
# Tema Visual Law central do EJC — padrão forense do "Documento Único de
# Anexos" em DOURADO com a logomarca De Paula Teixeira.
#
# TODO gerador de documento do sistema deve consumir este módulo:
#   - constantes de cor (paleta dourada institucional);
#   - logo_data_uri()  → logo em base64 (lazy + cache) — weasyprint não busca
#     URL externa, então a imagem é sempre embutida;
#   - css_tema()   → layout de folha forense (capa/separadores, página inteira);
#   - css_fluxo()  → documentos corridos multipágina (@page com rodapé repetido);
#   - render_banner / render_capa / render_rodape → blocos HTML prontos.
#
# Padrão visual (modelo forense do escritório):
#   banner de topo em dourado com a logo em tile BRANCO, palavra gigante
#   centralizada ("ANEXOS", "DOC. 01", tipo da peça), linha horizontal grossa
#   na cor do tema, título em caps, legenda-síntese e rodapé discreto com o
#   juízo/comarca (que deve vir do CASO quando disponível).
from __future__ import annotations

import base64
import html as html_lib
from functools import lru_cache
from pathlib import Path

# ── Paleta dourada institucional ──────────────────────────────────────────────
OURO_PROFUNDO = "#6F5711"   # base do banner (texto branco AA) e cabeçalhos de tabela
OURO = "#8F7117"            # palavra gigante, linhas do tema, títulos
OURO_CLARO = "#C9A227"      # detalhes, filetes e realces
OURO_PALHA = "#F7F1DC"      # fundos suaves (zebra discreta, quadros)
BANNER_TEXTO = "#ffffff"
BANNER_SUB = "#f3e9c9"
TEXTO = "#111827"
TEXTO_SUAVE = "#4b5563"
RODAPE_COR = "#6b7280"

_LOGO_CANDIDATOS = (
    Path(__file__).resolve().parents[1] / "assets" / "de-paula-teixeira-logo.jpg",
    Path(__file__).resolve().parents[1] / "static" / "brand" / "de-paula-teixeira-logo.jpg",
)


@lru_cache(maxsize=1)
def logo_path() -> Path | None:
    """Caminho do arquivo da logo, ou ``None`` se nenhum candidato existir.

    Existe para consumidores que precisam do ARQUIVO e não do data URI — o
    DOCX (python-docx) insere imagem por caminho/stream, não por base64.
    """
    for caminho in _LOGO_CANDIDATOS:
        if caminho.is_file():
            return caminho
    return None


@lru_cache(maxsize=1)
def logo_data_uri() -> str:
    """Logo De Paula Teixeira como data URI base64 (lazy, cache em memória)."""
    for caminho in _LOGO_CANDIDATOS:
        try:
            raw = caminho.read_bytes()
        except OSError:
            continue
        return "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")
    return ""


def esc(s: str | None) -> str:
    return html_lib.escape(s or "")


# ── CSS ───────────────────────────────────────────────────────────────────────

def _css_componentes() -> str:
    """Componentes compartilhados: banner, palavra gigante, índice, rodapé, tabelas."""
    return f"""
  .banner {{ background: linear-gradient(135deg, {OURO_PROFUNDO} 0%, {OURO} 100%);
             color: {BANNER_TEXTO}; padding: 12mm 18mm 10mm 18mm; text-align: center; }}
  .banner-logo-tile {{ display: inline-block; background: #ffffff; border-radius: 8px;
                       padding: 3mm 6mm; margin-bottom: 5mm; }}
  .banner-logo {{ height: 15mm; }}
  .banner-titulo {{ font-size: 15pt; font-weight: 800; letter-spacing: .2px;
                    color: {BANNER_TEXTO}; }}
  .banner-sub {{ font-size: 10.5pt; margin-top: 6px; color: {BANNER_SUB}; }}
  .hero {{ text-align: center; padding: 40mm 22mm 0 22mm; }}
  .palavra-gigante {{ font-size: 46pt; font-weight: 800; color: {OURO}; letter-spacing: 1px; }}
  .linha-tema {{ width: 62%; margin: 14px auto 20px auto; border: 0;
                 border-top: 3px solid {OURO}; }}
  .hero-kicker {{ font-size: 14pt; font-weight: 800; color: #1f2937;
                  text-transform: uppercase; letter-spacing: .4px; }}
  .legenda {{ font-size: 10.5pt; color: {TEXTO_SUAVE}; font-style: italic;
              margin: 12px auto 0 auto; max-width: 150mm; line-height: 1.5; }}
  .indice-titulo {{ text-align: center; font-size: 12pt; font-weight: 800; color: #1f2937;
                    text-transform: uppercase; margin: 6mm 0 5mm 0; }}
  .indice {{ margin: 0 24mm; }}
  .indice-linha {{ display: table; width: 100%; margin-bottom: 6px; font-size: 10.5pt; }}
  .indice-doc {{ display: table-cell; width: 22mm; font-weight: 800; color: {OURO};
                 white-space: nowrap; vertical-align: top; }}
  .indice-desc {{ display: table-cell; color: #374151; vertical-align: top; }}
  .rodape {{ position: absolute; bottom: 12mm; left: 0; right: 0; text-align: center;
             font-size: 8.5pt; color: {RODAPE_COR}; }}
  .rodape-logo {{ height: 14px; vertical-align: middle; margin-right: 6px;
                  background: #ffffff; padding: 1px 3px; border-radius: 3px; }}
  table.tema {{ width: 100%; border-collapse: collapse; margin: 8px 0 14px 0; }}
  table.tema th {{ background: {OURO_PROFUNDO}; color: #ffffff; padding: 7px 8px;
                   text-align: left; font-size: 9.2pt; font-weight: 700; }}
  table.tema td {{ padding: 6px 8px; border-bottom: 1px solid #e5e7eb;
                   font-size: 9.4pt; vertical-align: top; }}
  table.tema tr:nth-child(even) td {{ background: {OURO_PALHA}; }}
"""


def css_tema() -> str:
    """Folha forense (capa/separador): A4 sem margens, rodapé absoluto por folha."""
    return f"""
  @page {{ size: A4; margin: 0; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: "DejaVu Sans", Arial, sans-serif; color: {TEXTO}; }}
  .sheet {{ position: relative; width: 210mm; min-height: 297mm; padding: 0 0 26mm 0;
            page-break-after: always; }}
  .img-full {{ display: block; margin: 12mm auto 0 auto; max-width: 174mm;
               max-height: 232mm; object-fit: contain; }}
{_css_componentes()}"""


def css_fluxo(rodape_texto: str = "") -> str:
    """Documento corrido multipágina: @page com margens + rodapé repetido
    (texto do juízo/escritório + numeração de página)."""
    rodape = (rodape_texto or "").replace("\\", "").replace('"', "'")
    return f"""
  @page {{
    size: A4; margin: 20mm 16mm 24mm 16mm;
    @bottom-center {{
      content: "{rodape}  ·  p. " counter(page) " de " counter(pages);
      font-family: "DejaVu Sans", Arial, sans-serif;
      font-size: 8.5pt; color: {RODAPE_COR};
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: "DejaVu Sans", Arial, sans-serif; color: {TEXTO};
          font-size: 10.5pt; line-height: 1.55; }}
  h1 {{ font-size: 15pt; color: {OURO_PROFUNDO}; border-bottom: 2px solid {OURO_CLARO};
        padding-bottom: 6px; margin: 18px 0 10px 0; }}
  h2 {{ font-size: 12pt; color: {OURO}; margin: 22px 0 8px 0; padding-left: 8px;
        border-left: 4px solid {OURO_CLARO}; }}
  h3 {{ font-size: 10.8pt; color: #374151; margin: 14px 0 6px 0; }}
  p {{ margin: 0 0 8px 0; text-align: justify; }}
  table {{ width: 100%; border-collapse: collapse; margin: 8px 0 14px 0; }}
  th {{ background: {OURO_PROFUNDO}; color: #ffffff; padding: 7px 8px; text-align: left;
        font-size: 9.2pt; font-weight: 700; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #e5e7eb; font-size: 9.4pt;
        vertical-align: top; }}
  tr:nth-child(even) td {{ background: {OURO_PALHA}; }}
{_css_componentes()}"""


# ── Blocos HTML ───────────────────────────────────────────────────────────────

def render_banner(titulo: str, subtitulo: str = "") -> str:
    """Banner de topo dourado com a logo em tile branco, título da ação em caps
    e subtítulo com as partes (ex.: 'FULANO vs. BELTRANO — Reserva NNN')."""
    logo = logo_data_uri()
    tile = (
        f'<div class="banner-logo-tile"><img class="banner-logo" src="{logo}" '
        'alt="De Paula Teixeira Advogados"></div>'
    ) if logo else ""
    sub = f'<div class="banner-sub">{esc(subtitulo)}</div>' if subtitulo else ""
    return (
        '<div class="banner">'
        f"{tile}"
        f'<div class="banner-titulo">{esc(titulo)}</div>'
        f"{sub}"
        "</div>"
    )


def render_capa(palavra: str, titulo: str = "", legenda: str = "",
                tamanho_pt: int = 46) -> str:
    """Página de rosto: palavra gigante ('ANEXOS', 'DOC. 01', tipo da peça) +
    linha grossa do tema + título em caps + legenda-síntese."""
    kicker = f'<div class="hero-kicker">{esc(titulo)}</div>' if titulo else ""
    leg = f'<div class="legenda">{esc(legenda)}</div>' if legenda else ""
    return (
        '<div class="hero">'
        f'<div class="palavra-gigante" style="font-size:{tamanho_pt}pt">{esc(palavra)}</div>'
        '<hr class="linha-tema">'
        f"{kicker}{leg}"
        "</div>"
    )


def render_rodape(texto: str) -> str:
    """Rodapé discreto (juízo/comarca) com a logo pequena em fundo branco."""
    logo = logo_data_uri()
    img = f'<img class="rodape-logo" src="{logo}" alt="">' if logo else ""
    return f'<div class="rodape">{img}<span>{esc(texto)}</span></div>'


def html_doc(corpo: str, css: str | None = None, css_extra: str = "") -> str:
    """Documento HTML completo pronto para o weasyprint (CSS do tema embutido)."""
    estilo = css if css is not None else css_tema()
    return (
        '<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8">'
        f"<style>{estilo}{css_extra}</style></head><body>{corpo}</body></html>"
    )
