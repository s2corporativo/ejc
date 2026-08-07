"""
AI Gateway LEGADO (shim de compatibilidade) — Ecossistema Jurídico Clóvis (EJC).

DEPRECATED: NÃO use este módulo em código novo.
  • Novos fluxos de IA devem passar pelo NÚCLEO ÚNICO:
      app.services.ai.core.orchestrator.orchestrator.run(...)
  • Chamadas de baixo nível devem usar o gateway central:
      app.services.ai_gateway.chat(...)

Este arquivo mantém APENAS a interface pública histórica (AIGateway com
`processar_demanda`, `generate` e `modo_duas_ias`, singletons `ai_gateway` e
`ai_brain`) para os ~16 consumidores legados. O MIOLO foi reescrito:
  1. sanitiza PII (app.services.sanitizer.sanitizar_pii) ANTES de qualquer envio;
  2. delega ao gateway central (app.services.ai_gateway.chat), que aplica a
     cadeia de providers por prioridade (anthropic → maritaca → groq) e a
     barreira final de PII para providers externos (LGPD);
  3. erros retornam mensagem segura (sem stack trace nem conteúdo do prompt).
"""
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("ejc.ai_gateway")

_ERRO_SEGURO = "Erro na comunicação com a IA. Tente novamente em instantes."

# Mapeamento tipo legado → task_type do gateway central, derivado dos modelos
# hardcoded antigos (deepseek-r1 → análise profunda; qwen2.5 → redação/contrato;
# gemma → resumos; llama3 → chat rápido).
_TIPO_PARA_TASK_TYPE: Dict[str, str] = {
    "juridico_profundo":  "analise_juridica",   # era deepseek-r1
    "redacao_peticao":    "elaboracao_peca",    # era qwen2.5
    "analise_contratual": "analise_contrato",   # era qwen2.5
    "resumos":            "resumo",             # era gemma
    "classificacao":      "resumo",             # era mistral (classificação rápida)
    "chat_rapido":        "chat_rapido",        # era llama3
    "default":            "chat_rapido",        # generate simples
}


class AIGateway:
    """DEPRECATED — casca de compatibilidade sobre o gateway central.

    Interface pública preservada; o transporte agora é
    app.services.ai_gateway.chat (nenhum httpx direto).
    """

    def __init__(self, base_url: Optional[str] = None):
        # Mantidos por compatibilidade de assinatura/atributos; não são mais
        # usados para transporte (o gateway central resolve provider/modelo).
        self.base_url = base_url
        self.models = dict(_TIPO_PARA_TASK_TYPE)

    async def _chamar_central(
        self, prompt: str, tipo: str, system: Optional[str] = None
    ) -> Dict[str, Any]:
        """Sanitiza PII e delega ao gateway central. Nunca propaga exceção."""
        # Import tardio e com alias: o singleton legado abaixo também se chama
        # `ai_gateway` — o alias evita shadowing do MÓDULO novo.
        from app.services import ai_gateway as gateway_central
        from app.services.sanitizer import sanitizar_pii

        task_type = _TIPO_PARA_TASK_TYPE.get(tipo, "chat_rapido")
        prompt_limpo, _ = sanitizar_pii(prompt or "")
        messages: list[dict] = []
        if system:
            system_limpo, _ = sanitizar_pii(system)
            messages.append({"role": "system", "content": system_limpo})
        messages.append({"role": "user", "content": prompt_limpo})
        try:
            resp = await gateway_central.chat(messages, task_type=task_type)
            return {
                "ok": True,
                "texto": resp.texto,
                "modelo": f"{resp.provedor}/{resp.modelo}",
            }
        except Exception as e:
            # Erro seguro: loga só tipo + resumo; nunca ecoa prompt/stack ao cliente.
            logger.error(
                f"AI Gateway legado ({task_type}): {type(e).__name__}: {str(e)[:200]}"
            )
            return {"ok": False, "texto": _ERRO_SEGURO, "modelo": task_type}

    async def processar_demanda(
        self, demanda: str, contexto: Optional[str] = None, tipo: str = "default"
    ) -> Dict[str, Any]:
        """
        DEPRECATED — Roteador legado (Seção 16.3). Delegado ao gateway central.
        Mesmo shape de retorno: {modelo_utilizado, tipo_demanda, resposta, status}.
        """
        prompt = f"Contexto: {contexto}\n\nDemanda: {demanda}" if contexto else demanda
        r = await self._chamar_central(prompt, tipo)
        return {
            "modelo_utilizado": r["modelo"],
            "tipo_demanda": tipo,
            "resposta": r["texto"],
            "status": "sucesso" if r["ok"] else "falha",
        }

    # P0-2: método usado por intelligence_v3, jurimetria e (indireto) cerebro.
    # "principal" => análise jurídica profunda; "secundario" => resposta rápida.
    async def generate(self, prompt: str, modo: str = "principal") -> str:
        """DEPRECATED — retorna str (como antes); erro vira mensagem segura."""
        tipo = "juridico_profundo" if modo == "principal" else "default"
        r = await self._chamar_central(prompt, tipo)
        return r["texto"]

    async def modo_duas_ias(self, demanda: str, contexto: str = "") -> Dict[str, Any]:
        """
        DEPRECATED — Análise Crítica Cruzada (Seção 23), agora via gateway central.
        Mesmo shape de retorno de antes.
        """
        # IA 1: Análise Principal (análise jurídica profunda)
        r1 = await self.processar_demanda(demanda, contexto, tipo="juridico_profundo")
        analise_1 = r1["resposta"]

        # IA 2: Análise Crítica da IA 1
        prompt_critico = (
            "Faça uma análise crítica profunda, identifique riscos, omissões e "
            f"falhas nesta análise jurídica: {analise_1}"
        )
        r2 = await self.processar_demanda(prompt_critico, contexto, tipo="redacao_peticao")
        critica = r2["resposta"]

        return {
            "analise_principal": analise_1,
            "analise_critica": critica,
            "convergencias": "Análise de convergência pendente de síntese.",
            "riscos_identificados": "Identificados via análise crítica cruzada.",
        }


ai_gateway = AIGateway()
# Alias para manter compatibilidade com código antigo que usa ai_brain
ai_brain = ai_gateway
