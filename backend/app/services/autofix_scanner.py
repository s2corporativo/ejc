# ── app/services/autofix_scanner.py ───────────────────────────────────────────
"""Diagnóstico seguro e auditável do EJC para o módulo IA AutoFix.

O scanner é estritamente somente leitura: não altera arquivos, banco, permissões,
migrations ou produção. Ele compara o catálogo funcional com as rotas reais em
runtime, verifica ajuda contextual e identifica colisões e lacunas operacionais.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.redesign import ModuleHelp
from app.services.module_registry import MODULE_REGISTRY


EXPECTED_MODULES: list[dict[str, str]] = [
    {
        "module_key": str(module["module_key"]),
        "rota": str(module["frontend_route"]),
        "titulo": str(module["nome"]),
        "grupo": str(module["grupo"]),
    }
    for module in MODULE_REGISTRY
    if module.get("status", "ativo") == "ativo"
]


def _normalizar_module_key(value: str) -> str:
    return (value or "").strip().strip("/").lower()


def _normalizar_api_path(value: str) -> str:
    path = (value or "").strip().rstrip("/") or "/"
    if path == "/api/v1":
        return "/api"
    if path.startswith("/api/v1/"):
        return f"/api{path[len('/api/v1') :]}"
    return path


def _prefixo_estatico(value: str) -> str:
    """Remove parâmetros de rota para comparar catálogo e OpenAPI."""
    value = _normalizar_api_path(value)
    marker = value.find("{")
    if marker >= 0:
        value = value[:marker]
    return value.rstrip("/") or "/"


def _achado(
    tipo: str,
    severidade: str,
    titulo: str,
    detalhe: str,
    sugestao: str,
    alvo: str | None = None,
    evidencias: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "tipo": tipo,
        "severidade": severidade,
        "titulo": titulo,
        "detalhe": detalhe,
        "sugestao": sugestao,
        "alvo": alvo,
        "evidencias": evidencias or [],
        "aplicado": False,
        "requer_revisao_humana": True,
    }


def _coletar_rotas_api(app: Any | None) -> list[dict[str, Any]]:
    if app is None:
        return []
    rotas: list[dict[str, Any]] = []
    for route in getattr(app, "routes", []) or []:
        path = getattr(route, "path", "") or ""
        if not path.startswith("/api"):
            continue
        methods = sorted(
            method
            for method in (getattr(route, "methods", set()) or set())
            if method not in {"HEAD", "OPTIONS"}
        )
        rotas.append(
            {
                "path": path,
                "normalized_path": _normalizar_api_path(path),
                "methods": methods,
                "name": getattr(route, "name", None),
            }
        )
    return sorted(rotas, key=lambda route: (route["normalized_path"], route["methods"]))


def _rota_cobre_prefixo(route_path: str, configured_prefix: str) -> bool:
    route_path = _normalizar_api_path(route_path)
    prefix = _prefixo_estatico(configured_prefix)
    return route_path == prefix or route_path.startswith(prefix + "/") or (
        prefix.endswith("/") and route_path.startswith(prefix)
    )


def _detectar_colisoes(rotas_api: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for route in rotas_api:
        for method in route["methods"]:
            groups[(method, route["normalized_path"])].append(
                str(route.get("name") or "sem_nome")
            )
    return [
        {
            "method": method,
            "path": path,
            "handlers": handlers,
        }
        for (method, path), handlers in sorted(groups.items())
        if len(handlers) > 1
    ]


def _avaliar_catalogo(
    rotas_api: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    achados: list[dict[str, Any]] = []
    cobertura: list[dict[str, Any]] = []
    paths = [route["normalized_path"] for route in rotas_api]

    for module in MODULE_REGISTRY:
        if module.get("status", "ativo") != "ativo":
            continue
        prefixes = [str(prefix) for prefix in module.get("backend_prefixes", [])]
        resolved = [
            prefix
            for prefix in prefixes
            if any(_rota_cobre_prefixo(path, prefix) for path in paths)
        ]
        missing = [prefix for prefix in prefixes if prefix not in resolved]
        cobertura.append(
            {
                "module_key": module["module_key"],
                "nome": module["nome"],
                "frontend_route": module["frontend_route"],
                "configured_prefixes": prefixes,
                "resolved_prefixes": resolved,
                "missing_prefixes": missing,
                "covered": bool(resolved) or not prefixes,
            }
        )
        if prefixes and not resolved:
            achados.append(
                _achado(
                    "modulo_sem_backend_runtime",
                    "P1",
                    f"Módulo sem rota ativa: {module['nome']}",
                    (
                        "Nenhum prefixo backend declarado no catálogo foi localizado "
                        "nas rotas FastAPI carregadas."
                    ),
                    "Revisar montagem do router, aliases e contrato do frontend antes de liberar o módulo.",
                    str(module["module_key"]),
                    evidencias=missing,
                )
            )
        elif missing:
            achados.append(
                _achado(
                    "prefixo_backend_nao_resolvido",
                    "P2",
                    f"Contrato parcial: {module['nome']}",
                    "Parte dos prefixos backend declarados não foi localizada em runtime.",
                    "Confirmar se o prefixo é alias legado, rota opcional ou contrato obsoleto.",
                    str(module["module_key"]),
                    evidencias=missing,
                )
            )
    return achados, cobertura


async def gerar_diagnostico_basico(
    db: AsyncSession,
    app: Any | None = None,
) -> dict[str, Any]:
    """Gera diagnóstico sistêmico completo em modo somente leitura."""
    rows = (
        await db.execute(select(ModuleHelp.module_key).where(ModuleHelp.ativo == True))  # noqa: E712
    ).scalars().all()
    helps_ativos = sorted({_normalizar_module_key(row) for row in rows if row})

    rotas_api = _coletar_rotas_api(app)
    rotas_api_paths = {route["normalized_path"] for route in rotas_api}
    achados: list[dict[str, Any]] = []

    for meta in EXPECTED_MODULES:
        key = meta["module_key"]
        if key not in helps_ativos:
            achados.append(
                _achado(
                    "manual_ausente",
                    "P2",
                    f"Manual ausente: {meta['titulo']}",
                    f"Não há tópico ativo em module_help para module_key='{key}'.",
                    "Cadastrar visão geral, passo a passo, erros comuns e permissões.",
                    key,
                )
            )

    endpoints_criticos = {
        "/api/module-help": "Ajuda contextual",
        "/api/health": "Health check",
        "/api/health/ready": "Readiness",
        "/api/documents": "Documentos",
        "/api/clients": "Clientes",
        "/api/cases": "Casos",
        "/api/auth/login": "Autenticação",
    }
    for endpoint, name in endpoints_criticos.items():
        if not any(
            path == endpoint or path.startswith(endpoint + "/")
            for path in rotas_api_paths
        ):
            achados.append(
                _achado(
                    "endpoint_critico_nao_detectado",
                    "P0",
                    f"Endpoint crítico não detectado: {name}",
                    f"A rota '{endpoint}' não apareceu no inventário FastAPI em runtime.",
                    "Verificar registro do router, prefixo canônico e aliases antes do deploy.",
                    endpoint,
                )
            )

    catalog_findings, catalog_coverage = _avaliar_catalogo(rotas_api)
    achados.extend(catalog_findings)

    collisions = _detectar_colisoes(rotas_api)
    for collision in collisions:
        achados.append(
            _achado(
                "colisao_metodo_rota",
                "P1",
                f"Colisão {collision['method']} {collision['path']}",
                "Mais de um handler está registrado para o mesmo método e caminho normalizado.",
                "Remover sombreamento ou transformar uma das rotas em alias explícito e testado.",
                collision["path"],
                evidencias=collision["handlers"],
            )
        )

    counts: dict[str, int] = {}
    for finding in achados:
        counts[finding["severidade"]] = counts.get(finding["severidade"], 0) + 1

    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "INFO": 4}
    achados.sort(
        key=lambda finding: (
            order.get(finding["severidade"], 9),
            finding["tipo"],
            finding["titulo"],
        )
    )

    return {
        "modo": "diagnostico",
        "dry_run": True,
        "aplicou_correcoes": False,
        "requer_revisao_humana": True,
        "resumo": "Diagnóstico AutoFix concluído em modo somente leitura.",
        "metricas": {
            "modulos_esperados": len(EXPECTED_MODULES),
            "topicos_help_ativos": len(helps_ativos),
            "rotas_api_detectadas": len(rotas_api),
            "modulos_com_backend": sum(1 for item in catalog_coverage if item["covered"]),
            "colisoes_metodo_rota": len(collisions),
            "achados": len(achados),
            "por_severidade": counts,
        },
        "achados": achados,
        "inventario": {
            "modulos_esperados": EXPECTED_MODULES,
            "cobertura_catalogo": catalog_coverage,
            "helps_ativos": helps_ativos,
            "colisoes": collisions,
            "rotas_api_amostra": rotas_api[:300],
        },
        "proximos_passos": [
            "Corrigir P0 e P1 em branch própria com revisão humana.",
            "Cadastrar tópicos mínimos para módulos sem manual.",
            "Revalidar catálogo e rotas após cada alteração estrutural.",
            "Manter aplicação automática e deploy direto desabilitados.",
        ],
    }
