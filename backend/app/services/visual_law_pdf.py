# ── app/services/visual_law_pdf.py ────────────────────────────────────────────
# Visual Law PDF (Sala de Guerra) — cronologia processual em HTML→PDF via
# weasyprint, com o tema dourado central (visual_law_theme).
#
# Reescrito de FPDF para weasyprint:
#   - FIX (singleton): a antiga instância global de FPDF acumulava páginas
#     entre requests — cada chamada fazia add_page() no MESMO objeto, e o PDF
#     seguinte saía com as cronologias anteriores dentro. Agora cada chamada
#     de gerar_cronologia monta um HTML novo e renderiza um PDF independente;
#     a classe é stateless e a instância de módulo existe só por
#     compatibilidade com os consumidores (routers/sala_de_guerra_v3.py,
#     services/geracao_documental.py).
from __future__ import annotations

import logging

from app.services import visual_law_theme as vlt

logger = logging.getLogger("ejc.visual_law_pdf")

_CSS_TIMELINE = f"""
  .conteudo {{ padding: 2mm 2mm 0 2mm; }}
  .tl-item {{ display: table; width: 100%; border-bottom: 1px solid {vlt.OURO_PALHA};
              padding: 6px 0; page-break-inside: avoid; }}
  .tl-data {{ display: table-cell; width: 34mm; font-weight: 800; color: {vlt.OURO};
              vertical-align: top; }}
  .tl-evento {{ display: table-cell; color: #1f2937; vertical-align: top; }}
"""


class VisualLawPDF:
    """Gerador stateless de PDFs Visual Law (tema dourado De Paula Teixeira)."""

    def gerar_cronologia(self, eventos: list, output_path: str) -> str:
        """Gera a linha do tempo processual — um PDF novo e independente por
        chamada (sem estado acumulado entre requests)."""
        from weasyprint import HTML

        linhas = "".join(
            '<div class="tl-item">'
            f'<div class="tl-data">{vlt.esc(str(item.get("data") or "S/D"))}</div>'
            f'<div class="tl-evento">{vlt.esc(str(item.get("evento") or "Evento não descrito"))}</div>'
            "</div>"
            for item in (eventos or [])
        ) or '<p class="legenda">Nenhum evento informado.</p>'

        corpo = (
            vlt.render_banner(
                "CRONOLOGIA PROCESSUAL ESTRATÉGICA",
                "EJC — Ecossistema Jurídico (Relatório Visual)",
            )
            + f'<div class="conteudo"><h2>Linha do Tempo</h2>{linhas}</div>'
        )
        html = vlt.html_doc(
            corpo,
            css=vlt.css_fluxo("Confidencial — De Paula Teixeira Advogados"),
            css_extra=_CSS_TIMELINE,
        )
        HTML(string=html).write_pdf(output_path)
        logger.info("Cronologia Visual Law gerada em %s (%d eventos)",
                    output_path, len(eventos or []))
        return output_path


# Instância de módulo mantida por compatibilidade de import — é stateless.
visual_law_pdf = VisualLawPDF()
