"""
Gerador de Visual Law PDF — EJC v3.0
Cria infográficos e linhas do tempo em PDF no padrão Bronze & Elegance.
"""
import logging
from fpdf import FPDF

logger = logging.getLogger("visual_law_pdf")

class VisualLawPDF(FPDF):
    def header(self):
        # Logo ou Título Bronze
        self.set_font('Arial', 'B', 12)
        self.set_text_color(184, 134, 11) # Bronze Primary (#B8860B)
        self.cell(0, 10, 'EJC — Ecossistema Jurídico (Relatório Visual)', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Página {self.page_no()} | Confidencial Dr. Clovis', 0, 0, 'C')

    def gerar_cronologia(self, eventos: list, output_path: str):
        """
        Gera uma linha do tempo elegante em PDF.
        """
        self.add_page()
        self.set_font('Arial', 'B', 16)
        self.set_text_color(44, 44, 44) # Charcoal
        self.cell(0, 15, 'Cronologia Processual Estratégica', 0, 1, 'L')
        self.ln(5)
        
        for item in eventos:
            # Data em destaque (Bronze)
            self.set_font('Arial', 'B', 11)
            self.set_text_color(184, 134, 11)
            self.cell(40, 10, item.get('data', 'S/D'), 0, 0, 'L')
            
            # Descrição do Evento
            self.set_font('Arial', '', 11)
            self.set_text_color(44, 44, 44)
            self.multi_cell(0, 10, item.get('evento', 'Evento não descrito'), 0, 'L')
            
            # Linha separadora Champagne
            self.set_draw_color(245, 230, 211) # Champagne
            self.line(self.get_x(), self.get_y(), self.get_x() + 190, self.get_y())
            self.ln(2)
            
        self.output(output_path)
        return output_path

visual_law_pdf = VisualLawPDF()
