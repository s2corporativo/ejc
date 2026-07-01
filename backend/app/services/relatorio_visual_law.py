"""
Gerador de Relatórios Visual Law - EJC v4.0.
Transforma dados complexos em relatórios PDF de alto impacto visual.
"""
from app.services.visual_law_templates import visual_law_engine
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import A4
import io

class RelatorioVisualLaw:
    async def gerar_dossie_estrategico(self, caso_data: dict) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = visual_law_engine.get_styles()
        
        elements = []
        
        # Cabeçalho de Luxo
        elements.append(Paragraph("DOSSIÊ ESTRATÉGICO DE CASO", styles['LuxuryTitle']))
        elements.append(Spacer(1, 12))
        
        # Quadro de Resumo Visual
        data = [
            ["CAMPO", "INFORMAÇÃO"],
            ["CLIENTE", caso_data.get('cliente_nome', 'N/A')],
            ["PROCESSO", caso_data.get('numero_processo', 'N/A')],
            ["ÁREA", caso_data.get('area', 'N/A')],
            ["RISCO", caso_data.get('risco', 'MÉDIO')]
        ]
        elements.append(visual_law_engine.criar_tabela_visual(data))
        elements.append(Spacer(1, 24))
        
        # Análise Jurídica
        elements.append(Paragraph("ANÁLISE TÉCNICA", styles['LegalText']))
        elements.append(Paragraph(caso_data.get('analise', 'Aguardando processamento...'), styles['LegalText']))
        
        doc.build(elements)
        return buffer.getvalue()

relatorio_engine = RelatorioVisualLaw()
