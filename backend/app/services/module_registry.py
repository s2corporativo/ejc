"""Catálogo canônico de módulos do EJC (backend).

Sincronizado com frontend/src/config/moduleRegistry.tsx. Rotas devem apontar
sempre para a superfície canônica atual, nunca para aliases legados.
"""
from __future__ import annotations

from typing import Any


PERFIS_GESTAO = ["superadmin", "admin", "socio"]
PERFIS_JURIDICO = ["superadmin", "admin", "socio", "advogado", "advogado_auxiliar", "estagiario"]
PERFIS_OPERACAO = ["superadmin", "admin", "socio", "advogado", "secretaria"]
PERFIS_FINANCEIRO = ["superadmin", "admin", "socio", "financeiro"]


def _mod(
    module_key: str,
    nome: str,
    grupo: str,
    frontend_route: str,
    backend_prefixes: list[str],
    *,
    status: str = "ativo",
    perfis: list[str] | None = None,
    dependencias: list[str] | None = None,
    usa_ia: bool = False,
    dados_sensiveis: bool = True,
    responsavel_operacional: str = "gestao",
    responsavel_tecnico: str = "tech",
) -> dict[str, Any]:
    return {
        "module_key": module_key,
        "nome": nome,
        "grupo": grupo,
        "frontend_route": frontend_route,
        "backend_prefixes": backend_prefixes,
        "status": status,
        "perfis": perfis or PERFIS_GESTAO,
        "dependencias": dependencias or ["database"],
        "usa_ia": usa_ia,
        "dados_sensiveis": dados_sensiveis,
        "responsavel_operacional": responsavel_operacional,
        "responsavel_tecnico": responsavel_tecnico,
    }


MODULE_REGISTRY: list[dict[str, Any]] = [
    _mod(
        "dashboard", "Dashboard", "Operação", "/",
        ["/api/dashboard", "/api/health"],
        perfis=PERFIS_OPERACAO + ["financeiro"], dependencias=["database"],
        dados_sensiveis=False, responsavel_operacional="gestao",
    ),
    _mod(
        "clientes", "Clientes", "Operação", "/clientes",
        ["/api/clients", "/api/clients/{client_id}/dossie"],
        perfis=PERFIS_OPERACAO, dependencias=["database", "audit", "pii_crypto"],
        responsavel_operacional="atendimento",
    ),
    _mod(
        "atendimento", "Atendimento", "Operação", "/atividades?tab=relacionamento",
        ["/api/atendimentos", "/api/cases/{case_id}/mensagens", "/api/notifications"],
        perfis=PERFIS_GESTAO, dependencias=["clients", "notifications"],
        responsavel_operacional="atendimento",
    ),
    _mod(
        "crm", "CRM", "Operação", "/crm-leads",
        ["/api/atendimentos", "/api/clients"], perfis=PERFIS_OPERACAO,
        dependencias=["clients"], responsavel_operacional="atendimento",
    ),
    _mod(
        "casos", "Casos e Processos", "Jurídico", "/casos",
        ["/api/cases", "/api/processes", "/api/cases/{case_id}/partes", "/api/cases/{case_id}/areas"],
        perfis=PERFIS_JURIDICO + ["secretaria"],
        dependencias=["clients", "documents", "deadlines", "audit"],
        usa_ia=True, responsavel_operacional="juridico",
    ),
    _mod(
        "ajuizamento", "Ajuizamento", "Jurídico", "/ajuizamento",
        ["/api/ajuizamento"],
        perfis=PERFIS_JURIDICO,
        dependencias=["cases", "clients", "documents", "pecas", "audit", "external_api"],
        responsavel_operacional="juridico",
    ),
    _mod(
        "ajuizamento-perfis", "Perfis de tribunal", "Administração", "/ajuizamento/perfis",
        ["/api/ajuizamento/perfis"],
        perfis=["superadmin", "admin"],
        dependencias=["ajuizamento", "vault", "audit"],
        responsavel_operacional="gestao",
    ),
    _mod(
        "datajud", "Processos / DataJud", "Jurídico", "/datajud",
        ["/api/datajud", "/api/processes", "/api/movimentos"],
        perfis=PERFIS_JURIDICO, dependencias=["cases", "external_api"],
        responsavel_operacional="juridico",
    ),
    _mod(
        "prazos", "Prazos", "Jurídico", "/atividades?tipo=prazo",
        ["/api/deadlines", "/api/suspensoes", "/api/calendar"],
        perfis=PERFIS_JURIDICO + ["secretaria"], dependencias=["cases", "notifications"],
        responsavel_operacional="juridico",
    ),
    _mod(
        "intimacoes", "Intimações", "Jurídico", "/atividades?tipo=intimacao",
        ["/api/intimacoes", "/api/diario-oficial"], perfis=PERFIS_JURIDICO,
        dependencias=["cases", "deadlines"], usa_ia=True, responsavel_operacional="juridico",
    ),
    _mod(
        "tarefas", "Tarefas", "Jurídico", "/atividades?tipo=tarefa",
        ["/api/tasks", "/api/atividades"], perfis=PERFIS_JURIDICO + ["secretaria"],
        dependencias=["cases", "notifications"], responsavel_operacional="operacao",
    ),
    _mod(
        "ramos", "Áreas de Atuação", "Jurídico", "/areas-de-atuacao",
        ["/api/empresarial", "/api/civel", "/api/penal", "/api/areas", "/api/ambiental/estrategia", "/api/trabalhista/liquidacao", "/api/tributario/fiscal"],
        perfis=PERFIS_JURIDICO, dependencias=["cases", "ai_gateway"], usa_ia=True,
        responsavel_operacional="juridico",
    ),
    _mod(
        "documentos", "Documentos e GED", "Produção", "/documentos",
        ["/api/documents", "/api/documentos-ia", "/api/anexos", "/api/data-room"],
        perfis=PERFIS_JURIDICO + ["secretaria"],
        dependencias=["storage", "ocr", "cases", "ai_gateway"], usa_ia=True,
        responsavel_operacional="juridico",
    ),
    _mod(
        "pecas", "Peças", "Produção", "/pecas",
        ["/api/pecas", "/api/legal-docs", "/api/templates"], perfis=PERFIS_JURIDICO,
        dependencias=["cases", "documents", "ai_gateway"], usa_ia=True,
        responsavel_operacional="juridico",
    ),
    _mod(
        "checklists", "Checklists", "Produção", "/checklists",
        ["/api/checklists", "/api/clients/{client_id}/pending-items"],
        perfis=PERFIS_JURIDICO, dependencias=["cases", "documents"], usa_ia=True,
        responsavel_operacional="juridico",
    ),
    _mod(
        "workflow", "Workflows", "Produção", "/workflow",
        ["/api/workflow", "/api/kanban/columns", "/api/cases/{case_id}/kanban"],
        perfis=PERFIS_JURIDICO + ["secretaria"], dependencias=["tasks", "notifications"],
        responsavel_operacional="operacao",
    ),
    _mod(
        "assinaturas", "Assinaturas", "Produção", "/assinaturas",
        ["/api/signatures", "/api/procuracoes"], perfis=PERFIS_OPERACAO,
        dependencias=["documents", "clients"], responsavel_operacional="atendimento",
    ),
    _mod(
        "financeiro", "Financeiro", "Financeiro", "/financeiro",
        [
            "/api/financeiro", "/api/financeiro/consolidado", "/api/financeiro/atencao",
            "/api/financeiro/demonstrativo", "/api/fees", "/api/despesas", "/api/pix",
            "/api/nfse", "/api/office-contracts", "/api/relatorio",
        ],
        perfis=PERFIS_FINANCEIRO, dependencias=["clients", "cases", "audit"],
        responsavel_operacional="financeiro",
    ),
    _mod(
        "honorarios", "Precificação de Honorários", "Inteligência",
        "/inteligencia?tab=honorarios", ["/api/honorarios-oab"],
        perfis=PERFIS_GESTAO + ["advogado"],
        dependencias=["cases", "clients", "rag"], usa_ia=True,
        responsavel_operacional="juridico",
    ),
    _mod(
        "sociedade", "Sociedade", "Gestão", "/gestao-escritorio/sociedade",
        ["/api/sociedade", "/api/partner-withdrawals"], perfis=PERFIS_GESTAO,
        dependencias=["audit"], responsavel_operacional="gestao",
    ),
    _mod(
        "sala-juridica", "Sala Jurídica", "Inteligência", "/sala-juridica",
        ["/api/sala-juridica", "/api/ai"], perfis=PERFIS_JURIDICO,
        dependencias=["ai_gateway", "cases", "rag", "audit"], usa_ia=True,
        responsavel_operacional="juridico",
    ),
    _mod(
        "ia", "Núcleo de IA", "Inteligência", "/inteligencia?tab=ia",
        ["/api/ai", "/api/ai/core", "/api/ia-governanca", "/api/ia-saude", "/api/ai/skills"],
        perfis=PERFIS_JURIDICO, dependencias=["ai_gateway", "rag", "audit", "pii_sanitizer"],
        usa_ia=True, responsavel_operacional="juridico",
    ),
    _mod(
        "inteligencia", "Workspace de Inteligência", "Inteligência", "/inteligencia",
        ["/api/intelligence", "/api/cerebro", "/api/cases/{case_id}/indice-risco", "/api/cases/{case_id}/score-juridico"],
        perfis=PERFIS_JURIDICO, dependencias=["ai_gateway", "cases", "rag"],
        usa_ia=True, responsavel_operacional="juridico",
    ),
    _mod(
        "ferramentas-ia", "Ferramentas IA", "Inteligência", "/inteligencia?tab=ferramentas",
        ["/api/ai", "/api/ia-especializada", "/api/ia-defensiva", "/api/ia/critica-adversarial", "/api/ia/validar-citacoes"],
        perfis=PERFIS_JURIDICO, dependencias=["ai_gateway", "documents", "cases"],
        usa_ia=True, responsavel_operacional="juridico",
    ),
    _mod(
        "conhecimento", "Base de Conhecimento e RAG", "Inteligência",
        "/inteligencia?tab=conhecimento",
        ["/api/rag", "/api/rag/knowledge-base", "/api/teses", "/api/teses-v4", "/api/sumulas", "/api/jurisprudencias", "/api/jurisprudencia-externa"],
        perfis=PERFIS_GESTAO + ["advogado"], dependencias=["database", "pgvector", "embedding_service", "storage"],
        usa_ia=True, responsavel_operacional="juridico",
    ),
    _mod(
        "jurimetria", "Jurimetria", "Inteligência", "/inteligencia?tab=jurimetria",
        ["/api/jurimetria", "/api/analytics"], perfis=PERFIS_JURIDICO,
        dependencias=["cases", "teses", "analytics"], usa_ia=True,
        responsavel_operacional="juridico",
    ),
    _mod(
        "radar-regulatorio", "Radar Regulatório", "Inteligência", "/radar?modo=digest",
        ["/api/regulatorio"], perfis=PERFIS_JURIDICO,
        dependencias=["external_sources", "notifications"], usa_ia=True,
        responsavel_operacional="juridico",
    ),
    _mod(
        "diario-oficial", "Diário Oficial", "Inteligência", "/diario-oficial",
        ["/api/diario-oficial", "/api/intimacoes"], perfis=PERFIS_JURIDICO,
        dependencias=["external_sources", "deadlines"], usa_ia=True,
        responsavel_operacional="juridico",
    ),
    _mod(
        "portal", "Portal do Cliente", "Portal", "/portal", ["/api/portal"],
        perfis=["cliente_externo"], dependencias=["clients", "cases", "documents", "signatures"],
        responsavel_operacional="atendimento",
    ),
    _mod(
        "auditoria", "Auditoria e Conformidade", "Administração", "/auditoria",
        ["/api/audit", "/api/compliance", "/api/lgpd/registros", "/api/trash"],
        perfis=PERFIS_GESTAO, dependencias=["database", "auth", "audit"],
        responsavel_operacional="gestao",
    ),
    _mod(
        "produtividade", "Produtividade", "Administração", "/produtividade",
        ["/api/analytics/produtividade", "/api/timesheet", "/api/atividades"],
        perfis=PERFIS_GESTAO + ["advogado"], dependencias=["tasks", "cases", "users"],
        dados_sensiveis=True, responsavel_operacional="gestao",
    ),
    _mod(
        "usuarios", "Usuários e Segurança", "Administração", "/usuarios",
        ["/api/users", "/api/auth", "/api/api-keys"], perfis=["superadmin", "admin"],
        dependencias=["auth", "audit"], responsavel_operacional="gestao",
    ),
    _mod(
        "mapa-modulos", "Mapa de Módulos", "Administração", "/mapa-modulos",
        ["/api/system-modules"], status="beta", perfis=PERFIS_GESTAO,
        dependencias=["module_registry"], dados_sensiveis=False,
        responsavel_operacional="gestao",
    ),
    _mod(
        "central-diagnostico", "Central de Diagnóstico", "Administração", "/diagnostico",
        ["/api/diagnostico"], status="beta", perfis=PERFIS_GESTAO,
        dependencias=["module_help", "module_registry"], dados_sensiveis=False,
        responsavel_operacional="gestao",
    ),
]


def listar_modulos() -> list[dict[str, Any]]:
    return [dict(item) for item in MODULE_REGISTRY]


def module_keys_registradas() -> set[str]:
    return {str(item["module_key"]) for item in MODULE_REGISTRY}


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
            "endpoints_detectados": sorted(endpoints)[:50],
            "precisa_revisao": key not in helps or len(endpoints) == 0 or item.get("status") != "ativo",
        })
    return mapa


def resumir_mapa_modulos(mapa: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(mapa),
        "ativos": sum(1 for m in mapa if m.get("status") == "ativo"),
        "beta": sum(1 for m in mapa if m.get("status") == "beta"),
        "legados": sum(1 for m in mapa if m.get("status") == "legado"),
        "sem_manual": sum(1 for m in mapa if not m.get("tem_manual")),
        "sem_endpoint_detectado": sum(1 for m in mapa if int(m.get("qtd_endpoints_detectados", 0)) == 0),
        "usam_ia": sum(1 for m in mapa if m.get("usa_ia")),
        "dados_sensiveis": sum(1 for m in mapa if m.get("dados_sensiveis")),
        "precisam_revisao": sum(1 for m in mapa if m.get("precisa_revisao")),
    }
