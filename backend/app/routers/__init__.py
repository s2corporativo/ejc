# ── app/routers/__init__.py ─────────────────────────────────────────────────
# Imports com efeitos controlados de registro de rotas complementares.
#
# main.py importa `app.routers` antes de incluir explicitamente os routers.
# Estes imports registram sub-rotas complementares sem exigir nova entrada no
# grande inventário de imports do main.py.
from app.routers import google_drive_knowledge  # noqa: F401

# Entrada Universal e Defesas/Revisões são anexados ao router `novos_modulos`,
# que já é montado pelo main.py sob /api. Os prefixos próprios são preservados.
from app.routers import (  # noqa: E402
    defesas_revisoes,
    defesas_revisoes_avancado,
    defesas_revisoes_pacote_seguro,
    entrada_universal,
    entrada_universal_vinculo,
    novos_modulos,
    peca_geracao,
    peca_modos,
)

# A restrição do advogado_auxiliar (não gera pacote executivo nem encaminha
# redação sem revisão) vive nos próprios módulos: ROLES_MOTOR_PECA em
# defesas_revisoes.py e ROLES_PACOTE em defesas_revisoes_avancado.py — sem
# mutação de conjuntos compartilhados no import.

novos_modulos.router.include_router(entrada_universal.router)
novos_modulos.router.include_router(entrada_universal_vinculo.router)
novos_modulos.router.include_router(defesas_revisoes.router)
# POST /defesas-revisoes/avancado/pacote existe SÓ no pacote seguro (a
# implementação legada foi removida do router avançado — sem sombreamento).
novos_modulos.router.include_router(defesas_revisoes_pacote_seguro.router)
novos_modulos.router.include_router(defesas_revisoes_avancado.router)

# Os modos Livre/Guiado/Molde/Agente apenas preparam o pipeline. A redação
# permanece no router canônico /pecas/gerar, incluído pelo main.py.
peca_geracao.router.include_router(peca_modos.router)
