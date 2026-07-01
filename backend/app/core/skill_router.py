"""
Roteador de Especialidades do EJC.
Identifica o ramo do direito do caso e aciona a Skill correspondente automaticamente.
"""
import logging

logger = logging.getLogger("skill_router")

class SkillRouter:
    def __init__(self):
        self.specialties = {
            "tributario": ["imposto", "pis", "cofins", "monofasico", "tributo", "receita", "selic", "icms"],
            "trabalhista": ["clt", "vinculo", "hora extra", "verbas", "tst", "trabalho", "rescisao"],
            "empresarial": ["sociedade", "contrato", "pj", "societario", "m&a", "empresa", "falencia"],
            "civil": ["indenizacao", "danos", "contrato civil", "posse", "propriedade", "familia"],
            "administrativo": ["licitacao", "pregao", "edital", "concurso", "servidor", "tcu", "pncp"]
        }

    def identificar_ramo(self, texto: str) -> str:
        texto = texto.lower()
        pontuacao = {k: 0 for k in self.specialties.keys()}
        
        for ramo, keywords in self.specialties.items():
            for word in keywords:
                if word in texto:
                    pontuacao[ramo] += 1
        
        # Retorna o ramo com maior pontuação, ou 'geral' se empate/zero
        ramo_vencedor = max(pontuacao, key=pontuacao.get)
        if pontuacao[ramo_vencedor] == 0:
            return "geral"
        return ramo_vencedor

    def get_skill_instruction(self, ramo: str) -> str:
        instructions = {
            "tributario": "Acionando Skill Especialista em Direito Tributário. Foco em recuperação de créditos e análise de Selic/IPCA.",
            "trabalhista": "Acionando Skill Especialista em Direito do Trabalho. Foco em jurisprudência do TST e cálculos de verbas.",
            "empresarial": "Acionando Skill Especialista em Direito Empresarial e Societário. Foco em contratos e governança.",
            "administrativo": "Acionando Skill Especialista em Direito Administrativo. Foco em licitações e decisões do TCU.",
            "civil": "Acionando Skill Especialista em Direito Civil. Foco em responsabilidade e contratos.",
            "geral": "Acionando Assistente Jurídico Geral. Análise multisetorial."
        }
        return instructions.get(ramo, instructions["geral"])

skill_router = SkillRouter()
