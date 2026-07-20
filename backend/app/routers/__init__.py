# ── app/routers/__init__.py ─────────────────────────────────────────────────
# Imports com efeitos controlados de registro de rotas complementares.
from app.routers import google_drive_knowledge  # noqa: F401

from app.routers import (  # noqa: E402
    defesas_revisoes,
    defesas_revisoes_avancado,
    defesas_revisoes_pacote_seguro,
    entrada_universal,
    entrada_universal_vinculo,
    novos_modulos,
)

novos_modulos.router.include_router(entrada_universal.router)
novos_modulos.router.include_router(entrada_universal_vinculo.router)
novos_modulos.router.include_router(defesas_revisoes.router)
novos_modulos.router.include_router(defesas_revisoes_pacote_seguro.router)
novos_modulos.router.include_router(defesas_revisoes_avancado.router)

# Sentinela permanece global; War Room e Visual Law também ficam no caso.
from app.routers import sala_de_guerra, sala_de_guerra_facade  # noqa: E402

sala_de_guerra.router.include_router(sala_de_guerra_facade.router)

# Timeline e saúde operacional são sub-recursos de Caso.
from app.routers import case_timeline, cases  # noqa: E402

cases.router.include_router(case_timeline.router)

# A saúde agregada é sub-recurso do Dashboard já montado no main.py.
from app.routers import dashboard, dashboard_operational  # noqa: E402

dashboard.router.include_router(dashboard_operational.router)

# Governança das tarefas é introspecção do Núcleo Único, não um novo executor.
from app.routers import ai_core, ai_task_policies  # noqa: E402

ai_core.router.include_router(ai_task_policies.router)
