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

# Consolidação da Sala de Guerra: Sentinela global permanece no router v3, mas
# simulação adversarial e Visual Law passam a existir também dentro do workspace
# canônico do caso, sem duplicar implementação ou persistência.
from app.routers import sala_de_guerra, sala_de_guerra_facade  # noqa: E402

sala_de_guerra.router.include_router(sala_de_guerra_facade.router)

# Linha do tempo e saúde operacional são sub-recursos da entidade Caso. A
# inclusão aqui preserva uma única montagem de `/cases` no main.py.
from app.routers import cases, case_timeline  # noqa: E402

cases.router.include_router(case_timeline.router)

# Saúde da carteira é sub-recurso do Dashboard, sem novo mount em main.py.
from app.routers import dashboard, dashboard_operational  # noqa: E402

dashboard.router.include_router(dashboard_operational.router)
