# ── app/routers/__init__.py ─────────────────────────────────────────────────
# Imports com efeitos controlados de registro de rotas complementares.
#
# main.py importa `app.routers` antes de incluir explicitamente os routers.
# Estes imports registram sub-rotas complementares sem exigir nova entrada no
# grande inventário de imports do main.py.

# Entrada Universal e Defesas/Revisões são anexados ao router `novos_modulos`,
# que já é montado pelo main.py sob /api. Os prefixos próprios são preservados.
from app.routers import (  # noqa: E402 — re-exports deliberados:
    # o import dispara o registro de sub-rotas complementares (side effect
    # controlado documentado acima), mesmo padrão do main.py pré-P3.
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
