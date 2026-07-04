# ── app/services/ai/core/__init__.py ─────────────────────────────────────────
# NÚCLEO ÚNICO DE IA — orquestrador + registries de agentes/skills + módulos de
# validação/HITL/auditoria. Import leve: os módulos internos fazem imports
# tardios das dependências pesadas (gateway, RAG, ORM) para evitar ciclos.
