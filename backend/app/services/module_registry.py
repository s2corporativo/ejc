from __future__ import annotations

from typing import Any


MODULE_REGISTRY: list[dict[str, Any]] = [
    {
        "module_key": "clientes",
        "nome": "Clientes",
        "grupo": "Operação",
        "frontend_route": "/clientes",
        "backend_prefixes": ["/api/clients"],
        "status": "ativo",
        "perfis": ["admin", "socio", "advogado", "secretaria"],
        "dependencias": ["database", "audit"],
        "usa_ia": False,
        "dados_sensiveis": True,
    },
    {
        "module_key": "casos",
        "nome": "Casos e Processos",
        "grupo": "Jurídico",
        "frontend_route": "/casos",
        "backend_prefixes": ["/api/cases", "/api/processes"],
        "status": "ativo",
        "perfis": ["admin", "socio", "advogado", "estagiario", "secretaria"],
        "dependencias": ["clients", "documents", "deadlines"],
        "usa_ia": True,
        "dados_sensiveis": True,
    },
    {
        "module_key": "documentos",
        "nome": "Documentos",
        "grupo": "Produção",
        "frontend_route": "/documentos",
        "backend_prefixes": ["/api/documents", "/api/documentos-ia"],
        "status": "ativo",
        "perfis": ["admin", "socio", "advogado", "estagiario", "secretaria"],
        "dependencias": ["storage", "ocr", "cases", "ai_gateway"],
        "usa_ia": True,
        "dados_sensiveis": True,
    },
    {
        "module_key": "prazos",
        "nome": "Prazos",
        "grupo": "Jurídico",
        "frontend_route": "/prazos",
        "backend_prefixes": ["/api/deadlines", "/api/suspensoes"],
        "status": "ativo",
        "perfis": ["admin", "socio", "advogado", "estagiario", "secretaria"],
        "dependencias": ["cases", "notifications"],
        "usa_ia": False,
        "dados_sensiveis": True,
    },
    {
        "module_key": "financeiro",
        "nome": "Financeiro",
        "grupo": "Financeiro",
        "frontend_route": "/financeiro",
        "backend_prefixes": ["/api/financeiro", "/api/fees", "/api/despesas"],
        "status": "ativo",
        "perfis": ["admin", "socio", "financeiro"],
        "dependencias": ["clients", "cases", "audit"],
        "usa_ia": False,
        "dados_sensiveis": True,
    },
    {
        "module_key": "ia",
        "nome": "Núcleo de IA",
        "grupo": "Inteligência",
        "frontend_route": "/ia",
        "backend_prefixes": ["/api/ai", "/api/ai-core", "/api/ia-governanca"],
        "status": "ativo",
        "perfis": ["admin", "socio", "advogado"],
        "dependencias": ["ai_gateway", "rag", "audit"],
        "usa_ia": True,
        "dados_sensiveis": True,
    },
    {
        "module_key": "auditoria",
        "nome": "Auditoria",
        "grupo": "Administração",
        "frontend_route": "/auditoria",
        "backend_prefixes": ["/api/audit", "/api/compliance"],
        "status": "ativo",
        "perfis": ["admin", "socio"],
        "dependencias": ["database", "auth"],
        "usa_ia": False,
        "dados_sensiveis": True,
    },
    {
        "module_key": "autofix",
        "nome": "Diagnóstico do Sistema",
        "grupo": "Administração",
        "frontend_route": "/autofix",
        "backend_prefixes": ["/api/module-help/diagnostico-sistema"],
        "status": "beta",
        "perfis": ["admin", "socio"],
        "dependencias": ["module_help"],
        "usa_ia": False,
        "dados_sensiveis": False,
    },
]


def listar_modulos() -> list[dict[str, Any]]:
    return [dict(item) for item in MODULE_REGISTRY]


def gerar_mapa_modulos(rotas_api: list[dict[str, Any]], helps_ativos: list[str]) -> list[dict[str, Any]]:
    api_paths = [str(r.get("path", "")) for r in rotas_api]
    helps = set(helps_ativos)
    mapa: list[dict[str, Any]] = []
    for item in MODULE_REGISTRY:
        prefixes = [str(p) for p in item.get("backend_prefixes", [])]
        endpoints = [p for p in api_paths if any(p.startswith(prefix) for prefix in prefixes)]
        key = str(item["module_key"])
        mapa.append({
            **item,
            "tem_manual": key in helps,
            "qtd_endpoints_detectados": len(endpoints),
            "endpoints_detectados": sorted(endpoints)[:30],
            "precisa_revisao": key not in helps or len(endpoints) == 0 or item.get("status") != "ativo",
        })
    return mapa


def resumir_mapa_modulos(mapa: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(mapa),
        "sem_manual": sum(1 for m in mapa if not m.get("tem_manual")),
        "sem_endpoint_detectado": sum(1 for m in mapa if int(m.get("qtd_endpoints_detectados", 0)) == 0),
        "usam_ia": sum(1 for m in mapa if m.get("usa_ia")),
        "dados_sensiveis": sum(1 for m in mapa if m.get("dados_sensiveis")),
        "precisam_revisao": sum(1 for m in mapa if m.get("precisa_revisao")),
    }
