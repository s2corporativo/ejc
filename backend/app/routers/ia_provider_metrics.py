# app/routers/ia_provider_metrics.py — SHIM pós-consolidação D2 (19/08/2026).
# O conteúdo foi incorporado em ia_governanca.py (mesmo prefixo
# /ia-governanca). Este módulo re-exporta o router canônico para preservar
# qualquer import externo enquanto o main.py é atualizado.
from app.routers.ia_governanca import router  # noqa: F401
