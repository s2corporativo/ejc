# ── app/services/ai/core/skill_registry.py ───────────────────────────────────
# REGISTRO DE SKILLS do Núcleo Único de IA.
#
# Skill = capacidade REUTILIZÁVEL com contrato documentado (finalidade, entrada,
# saída, permissões, riscos, pré/pós-condições). O handler, quando existe,
# delega para o serviço já consolidado do EJC (import tardio — evita ciclos).
# Skills de PATCH têm handler=None DE PROPÓSITO: aplicação/rollback de mudança
# em código NUNCA é automática — exige autorização humana explícita e trilha
# de rollback (política RepairAgent).
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

from app.services.ai.core.ejc_skill_catalog import native_skill_specs

_STAFF = "qualquer usuário interno (staff); cliente_externo bloqueado no núcleo"
_TECNICO = "superadmin/admin/socio"


@dataclass(frozen=True)
class Skill:
    nome: str
    finalidade: str
    entrada: str
    saida: str
    permissoes: str = _STAFF
    riscos: str = "baixo"
    pre_condicoes: str = ""
    pos_condicoes: str = ""
    logs: str = "registrada via AILog quando envolve chamada de modelo"
    tratamento_erro: str = "exceções propagam ao orchestrator (HTTP 4xx/5xx seguro)"
    handler: Callable | None = None


# ── Handlers (import tardio p/ evitar ciclos de import) ──────────────────────

def _h_classify_intent(**kw):
    from app.services.ai.core.intent_classifier import classify_intent
    return classify_intent(**kw)


def _h_resolve_native_skills(**kw):
    from app.services.ai.core.ejc_skill_catalog import resolve_native_skill_plan
    return resolve_native_skill_plan(**kw)


async def _h_build_case_context(db, case_id, **kw):
    from app.services.case_context import montar_dossie
    return await montar_dossie(db, case_id, **kw)


async def _h_retrieve_rag(db, consulta, **kw):
    from app.services.ai_service import buscar_contexto_rag
    return await buscar_contexto_rag(db, consulta, **kw)


def _h_sanitize(texto, nomes_proteger=None):
    from app.services.ai_guard import sanitizar_ou_abortar
    return sanitizar_ou_abortar(texto, nomes_proteger)


def _h_check_pii(texto):
    from app.services.sanitizer import validar_sem_pii
    return validar_sem_pii(texto)


def _h_select_provider(texto, task_type, **kw):
    from app.services.ai.provider_policy import AIProviderPolicy
    return AIProviderPolicy().avaliar(texto, task_type, **kw)


async def _h_call_model(messages, **kw):
    from app.services import ai_gateway
    return await ai_gateway.chat(messages, **kw)


async def _h_validate_citations(db, texto):
    from app.services.citation_check import verificar_citacoes
    return await verificar_citacoes(db, texto)


def _h_mark_as_draft(resultado):
    from app.services.ai.core import hitl_policy
    return hitl_policy.aplicar(resultado)


async def _h_log_interaction(db, **kw):
    from app.services.ai.core import audit_logger
    return await audit_logger.registrar(db, **kw)


def _h_estimate_cost(model, tokens_input, tokens_output):
    from app.services.ai_gateway import _custo_brl
    return _custo_brl(model, tokens_input or 0, tokens_output or 0)


def _h_diagnose_system(max_chars: int = 12000):
    """Lê o GRAPH_REPORT (contexto técnico) — SEM segredos, com truncamento."""
    from pathlib import Path
    caminho = Path("graphify-out/GRAPH_REPORT.md")
    if not caminho.exists():
        return "GRAPH_REPORT.md indisponível — rode graphify no repositório."
    texto = caminho.read_text(encoding="utf-8", errors="replace")[:max_chars]
    return texto


# ── Registro ──────────────────────────────────────────────────────────────────
# Ordem = ordem lógica do pipeline; consultar via get_skill()/listar_skills().

SKILL_REGISTRY: dict[str, Skill] = {s.nome: s for s in [
    Skill("classify_intent", "Classificar intenção/domínio e rotear ao agente interno",
          "task_type, domain, mensagem", "IntentResultado(agente, tarefa, flags)",
          riscos="baixo (determinístico, sem LLM)",
          pos_condicoes="sempre resolve um agente (default CaseAgent)",
          handler=_h_classify_intent),
    Skill("resolve_native_skills",
          "Selecionar deterministicamente uma skill de ramo e uma de módulo do EJC",
          "task_type, domain, mensagem, module_key, surface",
          "NativeSkillPlan(ramo, módulo, skills, métodos)",
          riscos="baixo (determinístico, sem LLM)",
          pos_condicoes="no máximo uma skill de ramo e uma de módulo, ambas canônicas",
          handler=_h_resolve_native_skills),
    Skill("build_case_context", "Montar dossiê consolidado e sanitizado do caso",
          "db, case_id", "dict{texto, meta, nomes_proteger} | None",
          pre_condicoes="ownership do caso já validado (ABAC)",
          pos_condicoes="texto sem PII estrutural", handler=_h_build_case_context),
    Skill("build_process_context", "Resumir metadados processuais (fase, tribunal, rito)",
          "db, process_id", "bloco de contexto textual",
          pos_condicoes="número CNJ omitido (PII estrutural)", handler=None),
    Skill("build_document_context", "Extrair texto OCR de documento do GED para análise",
          "db, document_id", "bloco [DOCUMENTO] truncado",
          riscos="médio — sigilo documental",
          pre_condicoes="documento FORA do cofre (confidencialidade normal)",
          handler=None),
    Skill("retrieve_rag_sources", "Buscar fontes na base de conhecimento (pgvector, 768d)",
          "db, consulta, limite, categorias", "list[dict{titulo, conteudo, categoria, fonte}]",
          pos_condicoes="fontes retornadas ao usuário para citação",
          handler=_h_retrieve_rag),
    Skill("sanitize_for_external_provider", "Sanitizar PII (LGPD) com abort em residual",
          "texto, nomes_proteger", "(texto_limpo, houve_remocao)",
          riscos="alto se ignorada — vazamento LGPD",
          pos_condicoes="HTTP 422 se PII estrutural persistir", handler=_h_sanitize),
    Skill("check_pii_residual", "Segunda barreira: detectar PII estrutural residual",
          "texto", "list[str] tipos encontrados (vazia = limpo)",
          handler=_h_check_pii),
    Skill("select_ai_provider", "Decidir cadeia de providers (policy central)",
          "texto, task_type, ja_sanitizado, exige_fonte", "PolicyDecision",
          pos_condicoes="externo só entra na cadeia com conteúdo sem PII",
          handler=_h_select_provider),
    Skill("call_model", "Chamar modelo via ai_gateway (ponto ÚNICO de despacho)",
          "messages, task_type, temperature, max_tokens", "GatewayResponse",
          riscos="médio — custo por token em providers pagos",
          pre_condicoes="conteúdo sanitizado; policy permitiu",
          handler=_h_call_model),
    Skill("validate_citations", "Conferir súmulas/artigos citados contra a base oficial",
          "db, texto", "dict{total, confirmadas, nao_encontradas, citacoes}",
          pos_condicoes="não confirmadas viram alerta HITL", handler=_h_validate_citations),
    Skill("mark_as_draft", "Carimbar resposta como rascunho HITL (OAB)",
          "resultado dict", "resultado com is_rascunho/requer_revisao/status_hitl",
          handler=_h_mark_as_draft),
    Skill("log_ai_interaction", "Gravar AILog (prompt sanitizado, fontes, tokens, custo)",
          "db, user, tarefa, ...", "log_id",
          riscos="crítico se omitida — IA sem trilha de auditoria",
          pos_condicoes="erro de gravação PROPAGA (não segue sem log)",
          handler=_h_log_interaction),
    Skill("estimate_ai_cost", "Estimar custo BRL da chamada (pricing por modelo)",
          "model, tokens_input, tokens_output", "float BRL",
          handler=_h_estimate_cost),
    Skill("generate_legal_draft", "Gerar minuta/peça jurídica (pipeline multi-etapa)",
          "tema, tipo_peca, contexto do caso", "rascunho de peça + citações verificadas",
          riscos="alto — conteúdo jurídico; SEMPRE rascunho",
          pos_condicoes="citation_check aplicado; HITL obrigatório", handler=None),
    Skill("summarize_document", "Resumir documento (OCR) de forma estruturada",
          "texto do documento", "resumo técnico", handler=None),
    Skill("extract_structured_data", "Extrair campos estruturados de documento",
          "texto, schema desejado", "dict campos", handler=None),
    Skill("analyze_deadline", "Analisar prazos processuais e datas fatais",
          "contexto processual", "prazos + base legal",
          riscos="alto — prazo fatal; dupla conferência humana", handler=None),
    Skill("analyze_financial_case", "Analisar honorários/financeiro do caso (tabela OAB/MG)",
          "contexto do caso + parâmetros", "análise financeira rascunho", handler=None),
    Skill("analyze_bank_statement", "Analisar extrato/contrato bancário (encargos, tarifas)",
          "texto do extrato/contrato", "apontamentos de abusividade + base normativa",
          pos_condicoes="cálculos são estimativas sujeitas a perícia", handler=None),
    Skill("diagnose_system_module", "Diagnosticar módulo do EJC via grafo de código",
          "nome do módulo/sintoma", "diagnóstico com base no GRAPH_REPORT",
          permissoes=_TECNICO,
          pre_condicoes="contexto técnico SEM segredos (.env, chaves, tokens)",
          handler=_h_diagnose_system),
    Skill("generate_repair_plan", "Propor plano de reparo (passos, riscos, rollback)",
          "diagnóstico", "plano ordenado com testes de verificação",
          permissoes=_TECNICO, pos_condicoes="plano é PROPOSTA — nada é executado",
          handler=None),
    Skill("generate_patch_preview", "Gerar prévia textual de patch (diff proposto)",
          "plano de reparo", "diff/na forma de texto para revisão",
          permissoes=_TECNICO, riscos="médio — nunca aplicado automaticamente",
          handler=None),
    Skill("apply_authorized_patch", "Aplicar patch APÓS autorização humana explícita",
          "patch aprovado + autorização registrada", "n/a",
          permissoes=_TECNICO, riscos="ALTO — mudança de código em produção",
          pre_condicoes="AUTORIZAÇÃO HUMANA EXPLÍCITA + backup/rollback preparados",
          pos_condicoes="NUNCA automática: handler ausente de propósito — aplicar "
                        "manualmente ou via processo de deploy revisado",
          handler=None),
    Skill("rollback_patch", "Reverter patch aplicado (trilha de rollback)",
          "identificação do patch", "n/a",
          permissoes=_TECNICO, riscos="ALTO",
          pos_condicoes="NUNCA automática: handler ausente de propósito",
          handler=None),
    Skill("audit_design_system", "Auditar consistência do design system do frontend",
          "escopo (página/componente)", "achados priorizados",
          permissoes=_TECNICO, handler=None),
    Skill("generate_saas_redesign_plan", "Propor plano de redesign SaaS (visual law)",
          "escopo + objetivos", "plano priorizado com critérios de aceite",
          permissoes=_TECNICO, handler=None),
    Skill("generate_report", "Gerar relatório executivo do domínio solicitado",
          "domínio + dados do contexto", "relatório estruturado rascunho",
          handler=None),
]}

# As 49 skills nativas são geradas a partir das fontes canônicas de ramos e
# módulos. Elas são instruções de método incorporadas ao pipeline central; não
# abrem gateway, provider, router ou agente executor paralelo.
for _spec in native_skill_specs():
    if _spec.name in SKILL_REGISTRY:
        raise RuntimeError(f"Skill nativa duplicada: {_spec.name}")
    _is_legal = _spec.kind == "legal_area"
    SKILL_REGISTRY[_spec.name] = Skill(
        nome=_spec.name,
        finalidade=_spec.description,
        entrada="intenção, contexto autorizado, documentos e parâmetros do módulo",
        saida="método especializado aplicado ao rascunho auditável",
        permissoes=(
            "superadmin/admin/socio/advogado/advogado_auxiliar"
            if _is_legal else _STAFF
        ),
        riscos=(
            "alto — mérito jurídico; revisão humana obrigatória"
            if _is_legal else "médio — operação sujeita a RBAC e confirmação"
        ),
        pre_condicoes="RBAC/ABAC, ownership e contexto validados pelo núcleo único",
        pos_condicoes=(
            "rascunho HITL; fontes e dados ausentes explicitados"
            if _is_legal
            else "nenhuma mutação ou envio sem ferramenta e confirmação humana"
        ),
        handler=None,
    )


def get_skill(nome: str) -> Skill:
    return SKILL_REGISTRY[nome]


def listar_skills() -> list[dict]:
    """Metadados públicos (sem handlers) — introspecção segura p/ /ai/core/skills."""
    return [
        {
            "nome": s.nome, "finalidade": s.finalidade, "entrada": s.entrada,
            "saida": s.saida, "permissoes": s.permissoes, "riscos": s.riscos,
            "pre_condicoes": s.pre_condicoes, "pos_condicoes": s.pos_condicoes,
            "automatica": s.handler is not None,
        }
        for s in SKILL_REGISTRY.values()
    ]
