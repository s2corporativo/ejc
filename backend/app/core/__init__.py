"""Bootstrap técnico do núcleo do EJC."""

from app.core.fastapi_compat import install_fastapi_route_introspection

# Executado antes da criação do app em ``app.main``. O adaptador é idempotente e
# mantém o despacho ASGI nativo, expondo apenas uma visão plana para auditorias.
install_fastapi_route_introspection()
