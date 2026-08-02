# 04 — Agentes (Fase 4)

> **Há duas camadas distintas de "agente" no EJC. Confundi-las produz diagnóstico errado.**
>
> - **Camada A — Claude Code:** `.claude/agents/*.md` (12). São ferramentas de **desenvolvimento**.
> - **Camada B — produto:** `backend/app/services/ai/core/` (37 agentes jurídicos). São **features**
>   entregues ao advogado.
>
> A camada A não roda em produção. A camada B não ajuda a escrever código.

---

# CAMADA A — agentes do Claude Code (12)

Todos versionados em git. **Nenhum declara `model:`**; só 2 declaram `tools:` — os outros 10
herdam o conjunto completo de ferramentas.

| Agente | Finalidade | Ferramentas | Modelo | Status |
|---|---|---|---|---|
| `ejc` | orquestrador; ponto de entrada padrão | todas | não declarado | ativa |
| `backend-fastapi` | `backend/app` | todas | não declarado | ativa |
| `frontend-react` | `frontend/src` | todas | não declarado | ativa |
| `db-migrations` | Alembic, schema, pgvector | todas | não declarado | ativa |
| `security-auditor` | segurança, **somente leitura** | `Read, Grep, Glob, Bash` | não declarado | ativa |
| `qa-tests` | pytest/vitest | todas | não declarado | ativa |
| `ci-triage` | falhas do GitHub Actions | todas | não declarado | ativa |
| `app-runner` | sobe a stack, navega no browser | todas | não declarado | ativa |
| `code-reviewer` | skill `code-review` sobre o diff | `Read, Grep, Glob, Bash` | não declarado | ativa |
| `verifier` | skill `verify` | todas | não declarado | ativa |
| `simplifier` | skill `simplify` (aplica correções) | todas | não declarado | ativa |
| `researcher` | skill `deep-research` (pesquisa externa) | todas | não declarado | ativa |

**Achado A1 — P3. Agentes ensinam stack que o projeto baniu.**
`security-auditor.md:12` cita "JWT (python-jose/PyJWT)" e `backend-fastapi.md:8` cita
"python-jose/PyJWT, passlib/bcrypt". O `CLAUDE.md` registra que **passlib e python-jose foram
removidos deliberadamente**. `frontend-react.md:3,8` descreve "React 18 / react-router-dom v6",
enquanto o repositório está em **React 19 / router 7**. → **OBSOLETA (parcialmente)**.

**Achado A2 — P2. 10 dos 12 agentes não declaram ferramenta.** Um agente de auditoria
(`security-auditor`) declara corretamente o conjunto somente-leitura; os demais herdam tudo,
inclusive `Write`/`Edit`. Para agentes cuja função é diagnosticar (não corrigir), isso é
permissão maior que a necessária.

**Achado A3 — P2. Nenhum agente cita nenhuma skill de projeto.** Varredura dos 19 nomes de
`.claude/skills/` contra `.claude/agents/`: **zero ocorrências**. As skills que os agentes citam
(`run`, `code-review`, `verify`, `simplify`, `deep-research`, `security-review`) **não existem em
`.claude/skills/`** — são globais/embutidas. Ver `05-skills.md`.

---

# CAMADA B — agentes jurídicos internos (37)

Localização: `backend/app/services/ai/core/agent_registry.py` + `backend/app/services/system_prompts/`.
Endpoints em `backend/app/routers/ai_core.py` (`/ai/core/chat|task|analyze|generate|report|agents|skills|status`).

## B1. Natureza

`AgenteInterno` é um **dataclass congelado** (`agent_registry.py:23-34`) — metadado puro, sem
código de execução. **Nenhum agente tem modelo ou provider próprio**: o modelo é resolvido pela
`TarefaIA` → `_TAREFA_PARA_GATEWAY` (`orchestrator.py:40-64`) → `ai_gateway`. Todos passam pelo
mesmo `_PIPELINE_BASE` (`agent_registry.py:17-20`) e **todos recebem carimbo HITL**
(`orchestrator.py:368` → `hitl_policy.aplicar`, que força `is_rascunho=True` mesmo com
`AI_REQUIRE_HITL=false`).

## B2. Inventário — 37 agentes

**Coordenação e núcleo (7):** `EJCCoordinatorAgent`, `CaseAgent` (**default do roteador**),
`ProcessAgent`, `DocumentAgent`, `LegalWritingAgent` (exige fonte), `RAGResearchAgent` (exige
fonte), `JurimetryAgent` (exige fonte).

**Ramos do direito (26):** Bancário, Ambiental, Digital/LGPD, Consumidor, Tributário,
Previdenciário, Empresarial, Trabalhista, Penal, Família, Administrativo, Sucessões,
Imobiliário, Constitucional, Juizados, Cível, Trânsito, Saúde, Médico, Agrário, Agronegócio,
Eleitoral, Internacional, Contratual — **todos com `exige_fonte=True`**.

**Apoio (4):** `FinanceAgent` (honorários, tabela OAB/MG), `ClientCommunicationAgent`,
`SecurityLGPDOABAgent`, e três de operação técnica restritos a **superadmin/admin/socio**:
`SystemHealthAgent`, `RepairAgent`, `UIUXAgent`.

**HITL universal:** não há agente sem carimbo de rascunho.
**`cliente_externo` é bloqueado duas vezes** — `ai_core.py:30-33` e `orchestrator.py:118-119`.

## B3. Roteamento

`intent_classifier.py` — **determinístico, sem LLM**. `classify_intent` (`:239-283`), em ordem:

1. `task_type` na tabela `TASK_TYPE_PARA_AGENTE` (~160 aliases, `:22-168`);
2. `task_type` genérico (`chat`, `case_analysis`, `report`) → **`domain` refina** (`:255-259`);
3. `domain` puro (`:260-261`);
4. **31 tuplas de keyword**, mais específica primeiro (`:171-211`);
5. **Fallback: `CaseAgent`** (`:268-269`) — *"nunca falha, sempre roteia"*.

**Roteador central:** `SingleAICoreOrchestrator.run` (`orchestrator.py:73-368`). Os wrappers
legados apontam para ele (`legal_chat_service.py:308,448`, `jurimetria.py:276`, `cerebro.py:25`).

**Controle de custo e loop:**
- **Caminho síncrono:** **uma** chamada de modelo por requisição (`:266`) — sem loop, sem recursão.
  Custo no `AILog` (`:286-301`). Rate limit por endpoint em `ai_core.py:108,123,140,157,173`
  (20/15/15/15/10).
- **Caminho agêntico** (`ai/agent/loop.py`, separado): orçamento explícito em `ai/agent/budget.py`
  — `max_steps=8`, `max_tokens_total=120000`, `max_custo_brl=2.00`. Laço com condição única
  `while not budget.deve_parar()` (`loop.py:408`), cobrindo passos, tokens **e** custo.
  → **proteção contra loop: EXISTE**, e é a implementação mais sólida das duas.

**Anti-injection (bem feito):** contexto de terceiros (OCR/RAG/dossiê) **nunca entra no system
prompt** — vai delimitado em `[CONTEXTO]…[/CONTEXTO]` dentro da mensagem do usuário, com instrução
explícita de ignorar comandos ali dentro (`orchestrator.py:186-197`).

**Piso de sigilo por área** (`:202-244`): a área real do caso (`Case.area`, que o cliente **não**
controla) tem precedência sobre `task_type`/`domain` do corpo da requisição, e viaja em parâmetro
próprio (`modo_sanitizacao`) sem sobrescrever `task_type`. Sem `try/except` — falha fecha.

## B4. Provider direto — invariante CONFIRMADA

Nenhum agente chama provider fora do `ai_gateway`. Todos os imports de provider partem de
`services/ai_gateway.py` (linhas 603, 633, 873-885, 1283). Única exceção lida e descartada:
`services/credential_testers.py:175` faz `GET /v1/models` para **testar chave** — não envia
conteúdo do usuário. Verificação independente minha em `06-ia-rag-grafo-juridico.md` §1.

## B5. Achados

| # | Achado | Evidência | Classificação | P |
|---|---|---|---|---|
| B5.1 | **`skill_pipeline` é declarativo, não executável** — só **1** dos 17 handlers do `SKILL_REGISTRY` é invocado | `orchestrator.py:185` é a única chamada `.handler()` em todo `app/`; verificado por mim | PARCIAL / código-espelho | **P2** |
| B5.2 | **12 agentes de ramo sem skill nativa** — `_LEGAL_DATA` cobre 14 de 26 ramos | `ejc_skill_catalog.py:77-150`; faltam Sucessões, Constitucional, Juizados, Saúde, Médico, Agrário, Agronegócio, Eleitoral, Internacional, Contratual | PARCIALMENTE INTEGRADA | P2 |
| B5.3 | **Prompts duplicados** | `PROMPT_ANALISE_CASO` serve 4 chaves (`system_prompts/__init__.py:56,57,83,84`); `EJCCoordinator` = `CaseAgent`; `DigitalLGPD` = `SecurityLGPDOAB` | DUPLICADA | P2 |
| B5.4 | **`RAGResearchAgent` sem prompt próprio** — usa o genérico do `CaseAgent` apesar de `exige_fonte=True` | `__init__.py:83`; o teste de invariantes só cobre as 10 `_TAREFAS_DE_AREA`, e `PESQUISA_JURIDICA` não está na lista | DUPLICADA | P2 |
| B5.5 | **8 agentes só com cobertura estrutural** — sem teste de roteamento ou comportamento | `ProcessAgent`, `DocumentAgent`, `FinanceAgent`, `ClientCommunicationAgent`, `SystemHealthAgent`, `RepairAgent`, `UIUXAgent`, `SecurityLGPDOABAgent` | SEM TESTE | P2 |
| B5.6 | **`SkillRouter` é um segundo classificador**, mais pobre (5 ramos vs 37 agentes), rodando **antes** do `intent_classifier` e poluindo o prompt | `core/skill_router.py:10-16,34-42`; consumido por `routers/cerebro.py:32-42`. Sem teste | DUPLICADA / OBSOLETA | **P2** |
| B5.7 | Drift de comentário: "49 skills nativas" — são 48 | `skill_registry.py:231` | — | P3 |

## B6. Cobertura jurídica — nenhuma lacuna de capacidade

Mapeado, **nada criado** (a auditoria proíbe criar agente nesta fase).

| Capacidade | Situação | Evidência |
|---|---|---|
| Triagem | EXISTE | `system_prompts/triagem.py`; `routers/ficha_triagem.py`, `triagem_entrevista.py`, `intake.py` |
| Análise documental | EXISTE | `DocumentAgent`; `services/document_intake_service.py` |
| Análise processual | EXISTE | `ProcessAgent`; prompt `processo` |
| Estratégia | EXISTE | `CaseAgent`; `services/legal_case_orchestrator.py`, `raio_x_advogado_service.py` |
| Pesquisa / jurisprudência | EXISTE | `RAGResearchAgent`; `routers/rag.py`, `jurisprudencia_*.py`; `services/verificador_jurisprudencia.py` |
| Elaboração de peças | EXISTE | `LegalWritingAgent`; `services/peca_service.py`, `motor_peca_service.py` |
| Revisão de citações | EXISTE | `services/citation_gate.py`, `citation_check.py`; skill `validate_citations` |
| Prazos | EXISTE | `ProcessAgent` + `analyze_deadline`; `services/deadline_calculator.py` — ⚠️ a skill tem `handler=None`; o cálculo real está no service |
| Comunicação ao cliente | EXISTE | `ClientCommunicationAgent` |
| Contratos / honorários | EXISTE | `ContractLawAgent`, `FinanceAgent`; `system_prompts/honorarios.py` |
| Jurimetria | EXISTE | `JurimetryAgent`; `services/jurimetria.py` |
| Curadoria da base | EXISTE | skill nativa `modulo_conhecimento`; `services/conhecimento_ingest/`; `routers/rag_governance.py` |

## B7. Testes

`tests/test_agentes_invariantes.py` garante: todo alias → agente existente; toda keyword → agente
existente; todo `prompt_key` ∈ `SYSTEM_PROMPTS`; toda `TarefaIA` ∈ `CONFIGURACOES`; toda skill de
agente ∈ `SKILL_REGISTRY`; agentes normativos exigem fonte.
`tests/test_ai_core_nucleo.py` congela o inventário de 37 agentes e a contagem de skills.
Complementam: `test_native_ejc_skill_catalog.py`, `test_ai_skill_oab_gate.py`,
`test_blindagem_prompts_ia.py`, `test_agent_tools_motores.py`, `test_eval_agent_trajectory.py`.

**Sem teste algum:** os 16 handlers não invocados do `SKILL_REGISTRY` (B5.1) e o `SkillRouter` (B5.6).

## B8. Testes adversariais pedidos pelo escopo — não executados

O escopo pede exercitar cada agente com entrada contraditória, documento sem relação, tentativa de
obter dado de outro caso, ausência de provider, timeout, resposta inválida, RAG indisponível e
conteúdo com instrução maliciosa. **Não foi possível nesta sessão**: sem Postgres, sem Redis, sem
provider de IA e sem chaves. As proteções correspondentes foram verificadas **por leitura**
(anti-injection em `orchestrator.py:186-197`; piso de sigilo em `:202-244`; fail-closed do escopo
RAG; orçamento do loop agêntico). **Exercitar de fato exige ambiente de homologação — está no
plano de correção como item de verificação, não como achado.**
