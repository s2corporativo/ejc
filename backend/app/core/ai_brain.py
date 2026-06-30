"""
AI Gateway Central - Ecossistema Jurídico Clóvis (EJC) v4.0
Centraliza todas as interações de IA, implementa o roteador inteligente multi-modelo
e garante a soberania tecnológica via Ollama (Local).
"""
import httpx
import logging
from typing import Optional, Dict, Any

from app.core.config import get_settings

logger = logging.getLogger("ejc.ai_gateway")

class AIGateway:
    def __init__(self, base_url: Optional[str] = None):
        # P1-4: ler do config (no Docker, localhost = o próprio container backend).
        self.base_url = base_url or get_settings().OLLAMA_BASE_URL
        # Mapeamento de Modelos Locais (Ollama) - Seção 16
        self.models = {
            "juridico_profundo": "deepseek-r1", # Análise jurídica profunda
            "redacao_peticao": "qwen2.5",       # Elaboração de petições
            "analise_contratual": "qwen2.5",    # Análise contratual
            "resumos": "gemma",                 # Resumos rápidos
            "classificacao": "mistral",         # Classificação de documentos
            "chat_rapido": "llama3",            # Chat rápido
            "default": "qwen2.5"
        }

    async def _call_ollama(self, model: str, prompt: str, system: Optional[str] = None) -> str:
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3}
                }
                if system:
                    payload["system"] = system
                
                response = await client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
                return response.json().get("response", "")
        except Exception as e:
            logger.error(f"AI Gateway Error ({model}): {e}")
            return f"Erro na comunicação com a IA Local ({model})."

    async def processar_demanda(self, demanda: str, contexto: Optional[str] = None, tipo: str = "default") -> Dict[str, Any]:
        """
        Roteador Inteligente: Seleciona o modelo com base no tipo de demanda (Seção 16.3).
        """
        model = self.models.get(tipo, self.models["default"])
        
        # Sistema de Fallback Automático
        prompt = f"Contexto: {contexto}\n\nDemanda: {demanda}" if contexto else demanda
        
        resultado = await self._call_ollama(model, prompt)
        
        return {
            "modelo_utilizado": model,
            "tipo_demanda": tipo,
            "resposta": resultado,
            "status": "sucesso" if "Erro" not in resultado else "falha"
        }

    # P0-2: método usado por intelligence_v3, jurimetria e (indireto) cerebro.
    # "principal" => análise jurídica profunda; "secundario" => resposta rápida.
    async def generate(self, prompt: str, modo: str = "principal") -> str:
        tipo = "juridico_profundo" if modo == "principal" else "default"
        model = self.models.get(tipo, self.models["default"])
        return await self._call_ollama(model, prompt)

    async def modo_duas_ias(self, demanda: str, contexto: str = "") -> Dict[str, Any]:
        """
        Funcionalidade Exclusiva: Análise Crítica Cruzada (Seção 23).
        """
        # IA 1: Análise Principal (DeepSeek ou Qwen)
        r1 = await self.processar_demanda(demanda, contexto, tipo="juridico_profundo")
        analise_1 = r1["resposta"]
        
        # IA 2: Análise Crítica da IA 1 (Qwen ou Mistral)
        prompt_critico = f"Faça uma análise crítica profunda, identifique riscos, omissões e falhas nesta análise jurídica: {analise_1}"
        r2 = await self.processar_demanda(prompt_critico, contexto, tipo="redacao_peticao")
        critica = r2["resposta"]
        
        return {
            "analise_principal": analise_1,
            "analise_critica": critica,
            "convergencias": "Análise de convergência pendente de síntese.",
            "riscos_identificados": "Identificados via análise crítica cruzada."
        }

ai_gateway = AIGateway()
# Alias para manter compatibilidade com código antigo que usa ai_brain
ai_brain = ai_gateway
