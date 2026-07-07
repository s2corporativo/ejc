# ── app/routers/__init__.py ─────────────────────────────────────────────────
# Imports com efeitos controlados de registro de rotas complementares.
#
# main.py importa `app.routers` antes de incluir explicitamente os routers.
# Este import registra as sub-rotas Google Drive dentro do router RAG existente,
# sem exigir alteração no main.py.
from app.routers import google_drive_knowledge  # noqa: F401
