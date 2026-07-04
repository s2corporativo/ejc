"""
Módulo de Diplomacia Digital — EJC v3.0
Gestão de Ativos Financeiros Judiciais e Estratégia de Liquidez.
"""
import logging
from math import pow

logger = logging.getLogger("diplomacia_digital")

class DiplomaciaDigital:
    def __init__(self, selic_atual: float = 0.1075):
        self.selic = selic_atual

    def calcular_ponto_equilibrio(
        self,
        valor_causa: float,
        prob_exito: float,
        tempo_anos: float,
        selic_anual: float | None = None,
        custas_pct: float = 0.0,
        honorarios_sucumbencia_pct: float = 0.0,
    ):
        """
        Calcula o Valor Presente Líquido (VPL) do processo para sugerir o acordo ideal.
        VPL = (Valor * Probabilidade - Custos) / (1 + Selic)^Tempo

        Retrocompatível: com os defaults (sem custos, selic da instância) o
        resultado numérico é idêntico ao contrato original usado por
        /diplomacia-v3/calcular-acordo — apenas chaves ADITIVAS foram incluídas
        (custos_estimados, custos_detalhe, selic_anual).
        """
        selic = self.selic if selic_anual is None else selic_anual
        valor_esperado = valor_causa * prob_exito
        custas = valor_causa * custas_pct
        # Sucumbência só é devida em caso de derrota → ponderada pela prob. de perda
        honorarios = valor_causa * honorarios_sucumbencia_pct * (1 - prob_exito)
        custos = custas + honorarios
        vpl = (valor_esperado - custos) / pow((1 + selic), tempo_anos)

        # Sugestão de acordo: VPL + 5% de margem de conveniência
        sugestao_acordo = vpl * 1.05

        return {
            "valor_causa": valor_causa,
            "probabilidade_exito": prob_exito,
            "tempo_estimado_anos": tempo_anos,
            "valor_presente_liquido": round(vpl, 2),
            "sugestao_acordo_ideal": round(sugestao_acordo, 2),
            "custo_oportunidade_perda": round(valor_esperado - vpl, 2),
            "custos_estimados": round(custos, 2),
            "custos_detalhe": {
                "custas": round(custas, 2),
                "honorarios_sucumbencia_esperados": round(honorarios, 2),
            },
            "selic_anual": selic,
        }

    async def gerar_dossie_pressao(self, dados_acordo: dict) -> dict:
        """
        Gera os argumentos do Dossiê de Pressão (Visual Law) via gateway
        central de IA (task_type="estrategia").

        `dados_acordo` deve ser o dict retornado por calcular_ponto_equilibrio.
        Retorna {"status", "dossie", "dados_acordo", "modelo", "provedor"} ou
        {"status": "erro", "mensagem": ...} em falha real — nunca texto fixo.
        """
        obrigatorios = (
            "valor_causa", "probabilidade_exito", "tempo_estimado_anos",
            "valor_presente_liquido", "sugestao_acordo_ideal",
        )
        faltantes = [c for c in obrigatorios if dados_acordo.get(c) is None]
        if faltantes:
            return {
                "status": "erro",
                "mensagem": f"Dados insuficientes para o dossiê: faltam {', '.join(faltantes)}.",
            }

        prompt = (
            "Gere um argumento de negociação (Dossiê de Pressão) dirigido ao "
            "advogado da parte contrária, com base EXCLUSIVAMENTE nos números "
            "abaixo, calculados por Valor Presente Líquido (VPL) com a Selic "
            f"de {self.selic:.4f}:\n"
            f"- Valor da causa: R$ {dados_acordo['valor_causa']}\n"
            f"- Probabilidade de perda da parte contrária: {dados_acordo['probabilidade_exito']}\n"
            f"- Tempo estimado do processo: {dados_acordo['tempo_estimado_anos']} anos\n"
            f"- Valor presente líquido: R$ {dados_acordo['valor_presente_liquido']}\n"
            f"- Sugestão de acordo ideal: R$ {dados_acordo['sugestao_acordo_ideal']}\n"
            f"- Custo de oportunidade da perda: R$ {dados_acordo.get('custo_oportunidade_perda', '—')}\n\n"
            "Regras: NÃO invente estatísticas, percentuais ou valores além dos "
            "fornecidos; se algum dado relevante não estiver acima, diga "
            "explicitamente que ele falta. Foque em demonstrar que o acordo "
            "hoje é racional para evitar custas e juros futuros."
        )
        try:
            from app.services import ai_gateway
            resp = await ai_gateway.chat(
                [{"role": "user", "content": prompt}], task_type="estrategia"
            )
        except Exception as e:
            logger.exception("[diplomacia] falha ao gerar dossiê")
            # Mensagem genérica ao caller (não vaza provedor/config); detalhe no log.
            return {"status": "erro", "mensagem": "Falha na geração do dossiê pela IA."}

        return {
            "status": "success",
            "dossie": resp.texto,
            "dados_acordo": dados_acordo,
            "modelo": resp.modelo,
            "provedor": resp.provedor,
        }

diplomacia = DiplomaciaDigital()
