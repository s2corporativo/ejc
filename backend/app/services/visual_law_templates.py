"""
Templates de Visual Law Sofisticado - EJC v4.0.
Configuração de estilos, tipografia e componentes visuais para PDFs (reportlab).
Paleta e logomarca vêm do tema central (visual_law_theme — dourado
De Paula Teixeira), garantindo o mesmo padrão dos geradores weasyprint.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
import os

from app.services import visual_law_theme as vlt

class VisualLawPDF:
    def __init__(self):
        # Paleta dourada institucional (tema central visual_law_theme).
        # Atributos mantêm os nomes antigos por compatibilidade de consumo.
        self.color_bronze = colors.HexColor(vlt.OURO)
        self.color_champagne = colors.HexColor(vlt.OURO_PALHA)
        self.color_text = colors.HexColor("#2C3E50")
        self.font_main = "Helvetica"
        self.font_bold = "Helvetica-Bold"
        # Logomarca De Paula Teixeira (mesma fonte do tema central).
        self.logo_path = os.path.join(
            os.path.dirname(__file__), "..", "assets", "de-paula-teixeira-logo.jpg"
        )

    def get_styles(self):
        styles = getSampleStyleSheet()
        
        styles.add(ParagraphStyle(
            name='LuxuryTitle',
            fontName=self.font_bold,
            fontSize=24,
            textColor=self.color_bronze,
            alignment=1,
            spaceAfter=30
        ))
        
        styles.add(ParagraphStyle(
            name='LegalText',
            fontName=self.font_main,
            fontSize=11,
            textColor=self.color_text,
            leading=14,
            alignment=4 
        ))
        
        return styles

    def get_header_logo(self):
        """Retorna o componente de imagem da logo para o cabeçalho."""
        if os.path.exists(self.logo_path):
            img = Image(self.logo_path, width=150, height=120)
            return img
        return None

    def criar_tabela_visual(self, data):
        """Cria uma tabela com design Visual Law."""
        t = Table(data, colWidths=[150, 350])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.color_bronze),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), self.font_bold),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), self.color_champagne),
            ('GRID', (0, 0), (-1, -1), 1, colors.white)
        ]))
        return t

visual_law_engine = VisualLawPDF()
