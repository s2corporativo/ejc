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
    case_timeline,
    cases,
    dashboard,
    dashboard_operational,
    defesas_revisoes,
    defesas_revisoes_avancado,
    defesas_revisoes_pacote_seguro,
    entrada_universal,
    entrada_universal_vinculo,
    novos_modulos,
    sala_de_guerra,
    sala_de_guerra_facade,
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

# As capacidades avançadas passam a existir no contexto do caso sem duplicar
# as implementações históricas, que permanecem ativas durante a transição.
sala_de_guerra.router.include_router(sala_de_guerra_facade.router)

# Timeline e saúde são projeções de leitura sobre entidades existentes; o router
# de casos continua sendo o ponto canônico de ownership e URL.
cases.router.include_router(case_timeline.router)

# A saúde da carteira reutiliza o prefixo /dashboard já montado pelo main.py.
dashboard.router.include_router(dashboard_operational.router)
