# ── app/services/autofix_scanner.py ───────────────────────────────────────────
"""Diagnóstico seguro do EJC para o módulo IA AutoFix.

Fase 1: somente leitura / dry-run. Este serviço não altera arquivos, banco,
permissões, migrations nem produção. Ele apenas consolida sinais de saúde para
revisão humana.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.redesign import ModuleHelp


EXPECTED_MODULES: list[dict[str, str]] = [
    {"module_key": "dashboard", "rota": "/", "titulo": "Dashboard", "grupo": "Operação"},
    {"module_key": "clientes", "rota": "/clientes", "titulo": "Clientes", "grupo": "Operação"},
    {"module_key": "casos", "rota": "/casos", "titulo": "Casos", "grupo": "Jurídico"},
    {"module_key": "datajud", "rota": "/datajud", "titulo": "Processos / DataJud", "grupo": "Jurídico"},
    {"module_key": "prazos", "rota": "/prazos", "titulo": "Prazos", "grupo": "Jurídico"},
    {"module_key": "intimacoes", "rota": "/intimacoes", "titulo": "Intimações", "grupo": "Jurídico"},
    {"module_key": "tarefas", "rota": "/tarefas", "titulo": "Tarefas", "grupo": "Jurídico"},
    {"module_key": "documentos", "rota": "/documentos", "titulo": "Documentos", "grupo": "Produção"},
    {"module_key": "pecas", "rota": "/pecas", "titulo": "Peças", "grupo": "Produção"},
    {"module_key": "checklists", "rota": "/checklists", "titulo": "Checklists", "grupo": "Produção"},
    {"module_key": "workflow", "rota": "/workflow", "titulo": "Workflows", "grupo": "Produção"},
    {"module_key": "financeiro", "rota": "/financeiro", "titulo": "Financeiro", "grupo": "Financeiro"},
    {"module_key": "honorarios", "rota": "/honorarios", "titulo": "Honorários", "grupo": "Financeiro"},
    {"module_key": "ia", "rota": "/ia", "titulo": "IA Jurídica", "grupo": "Inteligência"},
    {"module_key": "inteligencia", "rota": "/inteligencia", "titulo": "Inteligência", "grupo": "Inteligência"},
    {"module_key": "ferramentas-ia", "rota": "/ferramentas-ia", "titulo": "Ferramentas IA", "grupo": "Inteligência"},
    {"module_key": "conhecimento", "rota": "/conhecimento", "titulo": "Conhecimento", "grupo": "Inteligência"},
    {"module_key": "jurimetria", "rota": "/jurimetria", "titulo": "Jurimetria", "grupo": "Inteligência"},
    {"module_key": "auditoria", "rota": "/auditoria", "titulo": "Auditoria", "grupo": "Administração"},
    {"module_key": "usuarios", "rota": "/usuarios", "titulo": "Usuários", "grupo": "Administração"},
    {"module_key": "autofix", "rota": "/autofix", "titulo": "IA AutoFix", "grupo": "Administração"},
]


def _normalizar_module_key(value: str) -> str:
    return (value or "").strip().strip("/").lower()


def _achado(tipo: str, severidade: str, titulo: str, detalhe: str, sugestao: str, alvo: str | None = None) -> dict[str, Any]:
    return {
        "tipo": tipo,
        "severidade": severidade,
        "titulo": titulo,
        "detalhe": detalhe,
        "sugestao": sugestao,
        "alvo": alvo,
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
            m for m in (getattr(route, "methods", set()) or set())
            if m not in {"HEAD", "OPTIONS"}
        )
        rotas.append({"path": path, "methods": methods, "name": getattr(route, "name", None)})
    return sorted(rotas, key=lambda r: r["path"])


async def gerar_diagnostico_basico(db: AsyncSession, app: Any | None = None) -> dict[str, Any]:
    """Gera diagnóstico básico do sistema em modo somente leitura."""
    rows = (await db.execute(
        select(ModuleHelp.module_key).where(ModuleHelp.ativo == True)  # noqa: E712
    )).scalars().all()
    helps_ativos = sorted({_normalizar_module_key(r) for r in rows if r})

    rotas_api = _coletar_rotas_api(app)
    rotas_api_paths = {r["path"] for r in rotas_api}
    achados: list[dict[str, Any]] = []

    for meta in EXPECTED_MODULES:
        key = meta["module_key"]
        if key not in helps_ativos:
            achados.append(_achado(
                "manual_ausente",
                "P2",
                f"Manual ausente: {meta['titulo']}",
                f"Não há tópico ativo em module_help para module_key='{key}'.",
                "Cadastrar tópico mínimo com visão geral, passo a passo, erros comuns e permissões.",
                key,
            ))

    endpoints_criticos = {
        "/api/module-help/": "Ajuda contextual",
        "/api/health": "Health check",
        "/api/health/ready": "Readiness",
        "/api/documents/": "Documentos",
        "/api/clients/": "Clientes",
        "/api/cases/": "Casos",
    }
    for endpoint, nome in endpoints_criticos.items():
        if endpoint not in rotas_api_paths:
            achados.append(_achado(
                "endpoint_critico_nao_detectado",
                "P1",
                f"Endpoint crítico não detectado: {nome}",
                f"A rota '{endpoint}' não apareceu no inventário FastAPI em runtime.",
                "Verificar registro do router em main.py e o prefixo real da rota.",
                endpoint,
            ))

    contagem_por_severidade: dict[str, int] = {}
    for a in achados:
        contagem_por_severidade[a["severidade"]] = contagem_por_severidade.get(a["severidade"], 0) + 1

    ordem = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "INFO": 4}
    achados.sort(key=lambda a: (ordem.get(a["severidade"], 9), a["tipo"], a["titulo"]))

    return {
        "modo": "diagnostico",
        "dry_run": True,
        "aplicou_correcoes": False,
        "requer_revisao_humana": True,
        "resumo": "Diagnóstico AutoFix básico concluído em modo somente leitura.",
        "metricas": {
            "modulos_esperados": len(EXPECTED_MODULES),
            "topicos_help_ativos": len(helps_ativos),
            "rotas_api_detectadas": len(rotas_api),
            "achados": len(achados),
            "por_severidade": contagem_por_severidade,
        },
        "achados": achados,
        "inventario": {
            "modulos_esperados": EXPECTED_MODULES,
            "helps_ativos": helps_ativos,
            "rotas_api_amostra": rotas_api[:160],
        },
        "proximos_passos": [
            "Cadastrar tópicos mínimos para módulos sem manual.",
            "Expandir o botão de ajuda contextual para todos os módulos principais.",
            "Validar endpoints críticos antes de qualquer correção assistida.",
            "Manter correção automática desligada até existir revisão humana e CI verde.",
        ],
    }
