"""
Cérebro Único (camada de compatibilidade) — Ecossistema Jurídico Clóvis (EJC)

CONSOLIDADO: este módulo era um gateway paralelo que chamava o Ollama DIRETO
via httpx (sem fallback, sem Claude, sem registro) — com OLLAMA_ENABLED=False
em produção, tudo que dependia dele falhava. Agora todos os métodos delegam ao
Cérebro Único real (app.services.ai_gateway), que roteia
Ollama → Anthropic (Claude) → Groq com fallback automático.

Assinaturas e formatos de retorno foram preservados: os módulos que importam
`ai_gateway`/`ai_brain` daqui (war_room, jurimetria, intelligence_v3, teses_v4,
cerebro, motor_estrategico, etc.) não precisam mudar.
"""
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("ejc.ai_gateway")

# Tipos legados deste módulo → task_type do gateway único (TASK_ROUTING).
_TIPO_TASK = {
    "juridico_profundo":  "analise_juridica",
    "redacao_peticao":    "elaboracao_peca",
    "analise_contratual": "analise_contrato",
    "resumos":            "resumo",
    "classificacao":      "chat_rapido",
    "chat_rapido":        "chat_rapido",
    "default":            "chat_rapido",
}


class AIGateway:
    """Shim de compatibilidade — delega ao gateway único (services.ai_gateway)."""

    def __init__(self, base_url: Optional[str] = None):
        # base_url mantido só por compatibilidade de assinatura; a resolução de
        # provedor/modelo agora é toda do gateway único.
        self.base_url = base_url

    async def _chat(self, prompt: str, tipo: str, nivel: str):
        # Import tardio: evita ciclo de import na subida do app.
        from app.services.ai_gateway import chat as gateway_chat
        task_type = _TIPO_TASK.get(tipo, "chat_rapido")
        return await gateway_chat(
            [{"role": "user", "content": prompt}],
            task_type=task_type,
            nivel_inteligencia=nivel,
        )

    async def processar_demanda(self, demanda: str, contexto: Optional[str] = None,
                                tipo: str = "default") -> Dict[str, Any]:
        """Contrato antigo preservado: {modelo_utilizado, tipo_demanda, resposta, status}.
        Callers legados detectam falha por status == "falha" e/ou "Erro" na resposta."""
        prompt = f"Contexto: {contexto}\n\nDemanda: {demanda}" if contexto else demanda
        nivel = "alto" if tipo == "juridico_profundo" else "padrao"
        try:
            resp = await self._chat(prompt, tipo, nivel)
            return {
                "modelo_utilizado": f"{resp.provedor}/{resp.modelo}",
                "tipo_demanda": tipo,
                "resposta": resp.texto,
                "status": "sucesso",
            }
        except Exception as e:
            logger.error(f"AI Gateway Error ({tipo}): {e}")
            return {
                "modelo_utilizado": None,
                "tipo_demanda": tipo,
                "resposta": "Erro na comunicação com a IA (todos os provedores indisponíveis).",
                "status": "falha",
            }

    # P0-2: método usado por intelligence_v3, jurimetria e (indireto) cerebro.
    # "principal" => análise jurídica profunda; "secundario" => resposta rápida.
    async def generate(self, prompt: str, modo: str = "principal") -> str:
        tipo = "juridico_profundo" if modo == "principal" else "default"
        nivel = "alto" if modo == "principal" else "padrao"
        try:
            resp = await self._chat(prompt, tipo, nivel)
            return resp.texto
        except Exception as e:
            logger.error(f"AI Gateway Error (generate/{modo}): {e}")
            # Callers antigos detectam falha por "Erro" na string.
            return "Erro na comunicação com a IA."

    async def modo_duas_ias(self, demanda: str, contexto: str = "") -> Dict[str, Any]:
        """Funcionalidade Exclusiva: Análise Crítica Cruzada (Seção 23) —
        agora com as duas passadas roteadas pelo gateway único."""
        # IA 1: Análise Principal (análise jurídica profunda)
        r1 = await self.processar_demanda(demanda, contexto, tipo="juridico_profundo")
        analise_1 = r1["resposta"]

        # IA 2: Análise Crítica da IA 1 (redação/qualidade)
        prompt_critico = (
            "Faça uma análise crítica profunda, identifique riscos, omissões e "
            f"falhas nesta análise jurídica: {analise_1}"
        )
        r2 = await self.processar_demanda(prompt_critico, contexto, tipo="redacao_peticao")

        return {
            "analise_principal": analise_1,
            "analise_critica": r2["resposta"],
            "convergencias": "Análise de convergência pendente de síntese.",
            "riscos_identificados": "Identificados via análise crítica cruzada.",
        }


ai_gateway = AIGateway()
# Alias para manter compatibilidade com código antigo que usa ai_brain
ai_brain = ai_gateway
