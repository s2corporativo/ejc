# ── app/services/ai/agent/__init__.py ────────────────────────────────────────
# MÓDULO AGÊNTICO DE IA (scaffold funcional). A IA opera como um AGENTE com loop
# de tool-use (modelo decide → chama ferramenta → lê resultado → decide de novo),
# reusando o NÚCLEO existente e TODOS os guardrails (barreira LGPD, RBAC/ownership,
# AILog, gate de citações, HITL). Tudo atrás da flag AI_AGENT_ENABLED (default
# False): com ela desligada o comportamento do sistema é IDÊNTICO ao atual.
