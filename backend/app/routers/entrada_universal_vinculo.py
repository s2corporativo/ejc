# app/routers/entrada_universal_vinculo.py — SHIM pós-consolidação D3 (20/08/2026).
# Conteúdo incorporado em entrada_universal.py (mesmo prefixo
# /entrada-universal). Re-exporta o router canônico para preservar
# qualquer import externo enquanto o __init__.py é atualizado.
from app.routers.entrada_universal import router  # noqa: F401
