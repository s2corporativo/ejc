"""Compatibilidade controlada entre o EJC e o registro lazy de routers do FastAPI.

FastAPI 0.139+ preserva routers incluídos como objetos ``_IncludedRouter`` e
resolve as rotas efetivas sob demanda. O runtime HTTP e o OpenAPI continuam
funcionando, porém auditorias históricas do EJC consultam ``app.routes`` para
validar contratos, rate limits e colisões. Esta classe fornece uma visão plana
somente para introspecção, sem reverter as correções de segurança do framework.
"""
from __future__ import annotations

from typing import Any, Iterable

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def flatten_routes(routes: Iterable[Any]) -> list[Any]:
    """Retorna rotas efetivas, expandindo wrappers lazy quando disponíveis.

    Compatível também com versões anteriores do FastAPI/Starlette: rotas que
    não implementam ``effective_route_contexts`` são preservadas sem alteração.
    """
    flattened: list[Any] = []
    for route in routes:
        effective_contexts = getattr(route, "effective_route_contexts", None)
        if callable(effective_contexts):
            flattened.extend(effective_contexts())
        else:
            flattened.append(route)
    return flattened


class EJCFastAPI(FastAPI):
    """FastAPI com visão plana auditável das rotas e OpenAPI nativo preservado."""

    @property
    def routes(self) -> list[Any]:
        # O despacho HTTP continua usando ``self.router`` diretamente. Esta
        # propriedade é consumida por testes, manifests e verificadores do EJC.
        return flatten_routes(self.router.routes)

    def openapi(self) -> dict[str, Any]:
        """Gera schema com a árvore nativa, que entende ``_IncludedRouter``.

        O ``get_openapi`` atual precisa receber ``self.router.routes``; passar a
        visão plana faria os contextos efetivos serem ignorados pelo gerador.
        """
        get_version = getattr(self.router, "_get_routes_version", None)
        routes_version = get_version() if callable(get_version) else len(self.router.routes)
        cached_version = getattr(self, "_openapi_routes_version", None)

        if not self.openapi_schema or cached_version != routes_version:
            self.openapi_schema = get_openapi(
                title=self.title,
                version=self.version,
                openapi_version=self.openapi_version,
                summary=self.summary,
                description=self.description,
                terms_of_service=self.terms_of_service,
                contact=self.contact,
                license_info=self.license_info,
                routes=self.router.routes,
                webhooks=self.webhooks.routes,
                tags=self.openapi_tags,
                servers=self.servers,
                separate_input_output_schemas=self.separate_input_output_schemas,
                external_docs=self.openapi_external_docs,
            )
            self._openapi_routes_version = routes_version
        return self.openapi_schema
