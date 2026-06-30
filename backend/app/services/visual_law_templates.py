"""
Templates de Visual Law Sofisticado - EJC v4.0.
Configuração de estilos, tipografia e componentes visuais para PDFs de luxo.
Inclui integração com a logomarca De Paula Teixeira.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
import os

class VisualLawPDF:
    def __init__(self):
        # Paleta Bronze & Elegance
        self.color_bronze = colors.HexColor("#CD7F32")
        self.color_champagne = colors.HexColor("#F7E7CE")
        self.color_text = colors.HexColor("#2C3E50")
        self.font_main = "Helvetica" 
        self.font_bold = "Helvetica-Bold"
        # P1-3: caminho relativo ao pacote (antes /home/ubuntu/..., inexistente no container)
        self.logo_path = os.path.join(os.path.dirname(__file__), "..", "assets", "logo.png")

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
