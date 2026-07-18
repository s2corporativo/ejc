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

# O Motor de Peça usa o limiar advogado+ (ROLE_LEVEL >= advogado). O perfil
# advogado_auxiliar permanece na análise e na preparação do dossiê, mas não
# pode gerar pacote executivo nem encaminhar redação sem revisão do responsável.
defesas_revisoes.ADVOGADO_ROLES.discard("advogado_auxiliar")
defesas_revisoes_avancado.ADVOGADO_ROLES.discard("advogado_auxiliar")

novos_modulos.router.include_router(entrada_universal.router)
novos_modulos.router.include_router(entrada_universal_vinculo.router)
novos_modulos.router.include_router(defesas_revisoes.router)
# O pacote seguro vem antes do router avançado e substitui, em tempo de
# execução, a rota antiga de mesmo método/caminho que não bloqueava a peça.
novos_modulos.router.include_router(defesas_revisoes_pacote_seguro.router)
novos_modulos.router.include_router(defesas_revisoes_avancado.router)
