"""Compatibilidade controlada com o registro lazy de routers do FastAPI.

FastAPI 0.139+ preserva routers incluídos como objetos internos e resolve as
rotas efetivas sob demanda. O runtime HTTP continua correto, mas auditorias
históricas do EJC consultam ``app.routes`` para validar contratos, rate limits
e colisões. Este módulo expõe uma visão plana somente para introspecção e
mantém a árvore nativa para a geração do OpenAPI.
"""
from __future__ import annotations

from typing import Any, Iterable

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute

_INSTALL_FLAG = "_ejc_route_introspection_installed"


def flatten_routes(routes: Iterable[Any]) -> list[Any]:
    """Expande wrappers lazy e preserva rotas tradicionais.

    No FastAPI novo, os itens expandidos são contextos efetivos. Eles carregam
    o caminho, método, endpoint e dependências já combinados com todos os
    prefixes/includes, enquanto ``original_route`` aponta para o APIRoute de
    origem. Consumidores não devem exigir o tipo concreto antigo.
    """
    flattened: list[Any] = []
    for route in routes:
        effective_contexts = getattr(route, "effective_route_contexts", None)
        if callable(effective_contexts):
            flattened.extend(effective_contexts())
        else:
            flattened.append(route)
    return flattened


def is_api_route(route: Any) -> bool:
    """Reconhece APIRoute clássico e contexto efetivo de APIRoute lazy."""
    if isinstance(route, APIRoute):
        return True
    return isinstance(getattr(route, "original_route", None), APIRoute)


def _flat_routes(app: FastAPI) -> list[Any]:
    return flatten_routes(app.router.routes)


def _openapi_with_native_tree(app: FastAPI) -> dict[str, Any]:
    """Gera o schema com a árvore lazy nativa do framework."""
    get_version = getattr(app.router, "_get_routes_version", None)
    routes_version = get_version() if callable(get_version) else len(app.router.routes)
    cached_version = getattr(app, "_openapi_routes_version", None)

    if not app.openapi_schema or cached_version != routes_version:
        app.openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            summary=app.summary,
            description=app.description,
            terms_of_service=app.terms_of_service,
            contact=app.contact,
            license_info=app.license_info,
            routes=app.router.routes,
            webhooks=app.webhooks.routes,
            tags=app.openapi_tags,
            servers=app.servers,
            separate_input_output_schemas=app.separate_input_output_schemas,
            external_docs=app.openapi_external_docs,
        )
        app._openapi_routes_version = routes_version
    return app.openapi_schema


def install_fastapi_route_introspection() -> None:
    """Instala o adaptador uma única vez no processo do EJC.

    A alteração é restrita à propriedade de introspecção e ao gerador OpenAPI;
    o despacho ASGI continua usando ``app.router`` diretamente.
    """
    if getattr(FastAPI, _INSTALL_FLAG, False):
        return

    FastAPI.routes = property(_flat_routes)  # type: ignore[assignment]
    FastAPI.openapi = _openapi_with_native_tree  # type: ignore[method-assign]
    setattr(FastAPI, _INSTALL_FLAG, True)


class EJCFastAPI(FastAPI):
    """Variante explícita para testes e novas aplicações internas."""

    routes = property(_flat_routes)
    openapi = _openapi_with_native_tree
