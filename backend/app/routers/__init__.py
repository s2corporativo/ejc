# ── app/routers/__init__.py ─────────────────────────────────────────────────
# Re-exports de conveniência. NÃO há efeito colateral de registro aqui.
#
# Até a consolidação P3, Entrada Universal e Defesas/Revisões eram anexados ao
# router `novos_modulos` no momento do import deste arquivo. Isso acabou: o
# main.py registra os quatro explicitamente com `include_router` (ver os
# comentários "P3: registro explícito" lá). O texto anterior descrevia o
# mecanismo antigo e induzia a crer que importar este módulo monta rotas.
from app.routers import (  # noqa: E402 — re-exports deliberados
    defesas_revisoes as defesas_revisoes,
    defesas_revisoes_avancado as defesas_revisoes_avancado,
    defesas_revisoes_pacote_seguro as defesas_revisoes_pacote_seguro,
    entrada_universal as entrada_universal,
    novos_modulos as novos_modulos,
)

# A restrição do advogado_auxiliar (não gera pacote executivo nem encaminha
# redação sem revisão) vive nos próprios módulos: ROLES_MOTOR_PECA em
# defesas_revisoes.py e ROLES_PACOTE em defesas_revisoes_avancado.py — sem
# mutação de conjuntos compartilhados no import.

# POST /defesas-revisoes/avancado/pacote existe SÓ no pacote seguro (a
# implementação legada foi removida do router avançado — sem sombreamento).
