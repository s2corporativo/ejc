# ── services/providers/__init__.py ───────────────────────────────────────────
# Provedores de IA disponíveis no EJC.
# Importados on-demand pelo ai_gateway para evitar falhas quando
# um provider está desativado (ex.: Ollama desligado).
from app.services.providers import groq_provider, ollama_provider, maritaca_provider

__all__ = ["groq_provider", "ollama_provider", "maritaca_provider"]
