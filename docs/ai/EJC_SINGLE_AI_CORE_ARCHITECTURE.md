# EJC — Arquitetura do Núcleo Único de IA

Data: 2026-07-04 · Complementa: `EJC_SINGLE_AI_CORE_AUDIT.md` (situação anterior).

Princípio: **existe UMA IA no EJC**. Nenhuma tela chama modelo; nenhum módulo tem pipeline próprio. Toda tarefa de IA passa pelo `SingleAICoreOrchestrator` (backend/app/services/ai/core/orchestrator.py:64) ou, nos wrappers legados, pelo mesmo `ai_gateway`.

## 1. Fluxo ponta a ponta

```
frontend (lib/aiCore.ts — só intenção/IDs/pergunta)
  │ POST /api/ai/core/{chat,task,analyze,generate,report}
  ▼
routers/ai_core.py  ── _staff_only (cliente_externo → 403, ai_core.py:28)
  ▼
SingleAICoreOrchestrator.run (orchestrator.py:67)
  1. classify_intent (intent_classifier.py:119) → agente interno
  2. RBAC/ABAC: role do agente + verificar_acesso_caso (orchestrator.py:88-96)
  3. context_builder.montar_contexto (dossiê/documento/processo/RAG)
  4. ai_guard.sanitizar_ou_abortar — LGPD, abort 422 (orchestrator.py:110-112)
  5. AIProviderPolicy().avaliar → PolicyDecision (provider_policy.py:70)
  6. ai_gateway.chat(task_type do gateway) → cadeia de providers
       └─ barreira FINAL de PII p/ externo (ai_gateway.py:197-207)
       └─ providers/{ollama,anthropic,groq}_provider.chat
  7. response_validator.validar — citações/promessa/sem base (response_validator.py:38)
  8. custo BRL (ai_gateway._custo_brl) quando provider=anthropic
  9. audit_logger.registrar → AILog (erro PROPAGA — sem trilha, sem resposta)
 10. hitl_policy.aplicar → is_rascunho/requer_revisao/status_hitl="gerado"
  ▼
resposta padronizada (dict) → frontend exibe rascunho para revisão humana
```

## 2. Responsabilidades dos módulos de `services/ai/`

| Módulo | Responsabilidade | Referência |
|---|---|---|
| `core/orchestrator.py` | Único ponto de execução; encadeia todas as etapas | orchestrator.py:64-194 |
| `core/intent_classifier.py` | Determinístico (tabelas+keywords, sem LLM): task_type/domain/mensagem → agente + TarefaIA | intent_classifier.py:119 |
| `core/agent_registry.py` | 14 agentes internos como METADADO puro (domínios, tarefa padrão, roles, skills) | agent_registry.py:42 |
| `core/skill_registry.py` | 28 skills com contrato documentado; handlers delegam a serviços existentes; skills de patch sem handler de propósito | skill_registry.py:103 |
| `core/context_builder.py` | Monta contexto real no backend (dossiê ≤8k, doc ≤6k, processo, RAG ≤6 chunks); cofre nunca entra em prompt | context_builder.py:37 |
| `core/response_validator.py` | Pós-modelo: citation_check, promessa de resultado (alerta, nunca reescreve), prefixo "SEM BASE VERIFICÁVEL" | response_validator.py:38 |
| `core/hitl_policy.py` | Carimba toda resposta como rascunho HITL | hitl_policy.py:15 |
| `core/audit_logger.py` | Ponte única para AILog via ai_guard.registrar_ai_log (erro propaga) | audit_logger.py:45 |
| `provider_policy.py` | Decisão pura de elegibilidade/ordem de providers + barreira LGPD | provider_policy.py:43 |

Fora de `ai/`: `ai_gateway.py` (dispatch + fallback + barreira final), `sanitizer.py`/`ai_guard.py` (LGPD), `citation_check.py` (anti-alucinação), `system_prompts/` (prompts + router de modelo por tarefa), `case_context.py` (dossiê sanitizado).

## 3. Contratos

`SingleAICoreOrchestrator.run` (orchestrator.py:67-81) — keyword-only:

```python
async def run(*, db=None, user=None, task_type: str, domain: str | None = None,
              mensagem: str, case_id: str | None = None,
              document_id: str | None = None, process_id: str | None = None,
              params: dict | None = None, usar_rag: bool = True,
              nivel_inteligencia: str = "alto") -> dict
```

Dict de resposta padronizado (orchestrator.py:172-193 + hitl_policy.aplicar):

| Campo | Conteúdo |
|---|---|
| `conteudo` | Texto validado (pode vir prefixado com "SEM BASE VERIFICÁVEL") |
| `agente`, `skill_pipeline`, `task_type`, `domain`, `tarefa` | Roteamento resolvido |
| `modelo` (`provider/modelo`), `provider` | O que realmente respondeu |
| `fontes` (titulo/categoria/fonte), `citacoes` | Rastreabilidade RAG + citation_check |
| `alertas`, `sem_base_verificavel`, `revisao_obrigatoria` | Saída do response_validator |
| `custo_estimado_brl`, `tokens_input`, `tokens_output`, `log_id` | Custo/auditoria |
| `is_rascunho` (sempre True), `requer_revisao`, `status_hitl`="gerado", `aviso_hitl` | Carimbo HITL |

Endpoints (routers/ai_core.py, prefixo `/api/ai/core`): `POST /chat|/task|/analyze|/generate|/report` + introspecção `GET /agents|/skills|/status` (só metadados/booleans — nunca chaves, ai_core.py:179). Client frontend: `frontend/src/lib/aiCore.ts` (aiChat/aiTask/aiAnalyze/aiGenerate/aiReport/aiStatus).

## 4. Como estender SEM criar IA paralela

**Novo agente**: adicionar `AgenteInterno` em `agent_registry.py` (nome, domínios, `tarefa_padrao` de TarefaIA, `prompt_key`, `exige_fonte`, `roles_permitidos`, skills via `_skills(...)`); registrar o prompt em `system_prompts/__init__.py` (SYSTEM_PROMPTS); mapear task_type/keywords em `intent_classifier.py` (TASK_TYPE_PARA_AGENTE / _KEYWORDS_PARA_AGENTE); se precisar de perfil de gateway próprio, usar `_AGENTE_GATEWAY_OVERRIDE` (orchestrator.py:57). Nenhum código de execução novo — o agente só parametriza o `run()`.

**Nova skill**: adicionar `Skill(...)` em `skill_registry.py` com contrato completo; handler deve delegar a um serviço existente (import tardio). Skill que aplica mudança/ação sensível fica com `handler=None` (execução exige processo humano).

**Proibido**: novo router que chame provider direto, httpx para modelo fora de `providers/`, novo INSERT manual em ai_logs, prompt montado no frontend. Endpoints legados são wrappers do núcleo/gateway (matriz em `EJC_AI_ENDPOINT_MIGRATION_MATRIX.md`).
