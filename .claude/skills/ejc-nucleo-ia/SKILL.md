---
name: ejc-nucleo-ia
description: >
  Trabalhar DENTRO do Núcleo Único de IA do EJC (backend/app/services/ai/core/ +
  backend/app/services/system_prompts/): adicionar/alterar agentes jurídicos internos,
  prompts por ramo do direito, skills reutilizáveis do pipeline, roteamento por área e a
  barreira ética OAB/LGPD — sem quebrar os invariantes de CI. Use SEMPRE que a tarefa
  envolver: novo agente jurídico, novo ramo do direito no assistente interno, novo
  system_prompt, editar AGENT_REGISTRY/SKILL_REGISTRY, intent_classifier, TarefaIA/
  CONFIGURACOES, exige_fonte/validate_citations, HITL/rascunho, ou "agente que atua dentro
  do EJC". Aciona em: "novo agente jurídico EJC", "adicionar ramo do direito", "novo
  system_prompt", "agent_registry", "skill_registry", "intent_classifier", "Núcleo Único
  de IA", "AgenteInterno", "TarefaIA", "barreira BASE_PROMPT", "assistente jurídico interno".
---

# Núcleo Único de IA do EJC — como trabalhar dentro dele

Subsistema que faz os agentes de IA "atuarem dentro do EJC" e assistirem os advogados.
É a área **mais sensível** do sistema (gera minuta/análise jurídica): a ordem reitora é
**Segurança/OAB > Cobertura > Eficiência**. Nunca inverta.

> Antes de ler código cru, oriente-se pelo grafo: `graphify query "agent_registry"`,
> `graphify explain "system_prompts"`. Inclua esta regra do graphify no prompt de todo
> subagente que explorar código. Após editar, o hook roda `graphify update .`.

## Mapa (fonte da verdade)

| Peça | Arquivo | Papel |
|---|---|---|
| Barreira ética | `system_prompts/base.py` | `BASE_PROMPT` (IDENTIDADE+RESTRIÇÕES OAB+COMPORTAMENTO) e `AVISO_RASCUNHO` |
| Prompt por ramo | `system_prompts/<ramo>.py` | `PROMPT_<RAMO> = BASE_PROMPT + "<regra da área>" + AVISO_RASCUNHO` |
| Registro de prompts | `system_prompts/__init__.py` | `SYSTEM_PROMPTS: dict[str,str]` (prompt_key → texto) |
| Router modelo/tarefa | `system_prompts/router.py` | `TarefaIA` (enum) + `CONFIGURACOES` (provider/modelo/tokens/temp) |
| Agentes internos | `ai/core/agent_registry.py` | `AGENT_REGISTRY: dict[str,AgenteInterno]` (metadado puro) |
| Skills do pipeline | `ai/core/skill_registry.py` | `SKILL_REGISTRY` (capacidade reutilizável; `handler=None` = não automática) |
| Roteamento | `ai/core/intent_classifier.py` | `TASK_TYPE_PARA_AGENTE` + `_KEYWORDS_PARA_AGENTE` (determinístico, sem LLM) |
| Execução | `ai/core/orchestrator.py` | único `run()`; agente só parametriza o pipeline base |
| Invariantes (CI) | `tests/test_agentes_invariantes.py` | trava regressões — mantenha SEMPRE verde |

Pipeline base de todo agente (`_PIPELINE_BASE`): classify_intent → sanitize_for_external_provider
→ check_pii_residual → select_ai_provider → call_model → mark_as_draft → log_ai_interaction.

## Receita — adicionar um agente/ramo jurídico novo

1. **Prompt** — crie `system_prompts/<ramo>.py` no molde de `consumidor.py`:
   ```python
   from .base import BASE_PROMPT, AVISO_RASCUNHO
   PROMPT_<RAMO> = BASE_PROMPT + """

   ## FUNÇÃO: <RAMO> — ESPECIALIZAÇÃO TÉCNICA
   LEGISLAÇÃO BASE: <leis/códigos>.
   EIXOS DA ANÁLISE: <numerados>.
   SAÍDA: <estrutura>. Cite a base legal; sem fonte verificável → escreva "verificar".
   """ + AVISO_RASCUNHO
   ```
2. **Registrar** em `system_prompts/__init__.py`: importe `PROMPT_<RAMO>` e adicione
   `"<ramo>": PROMPT_<RAMO>` em `SYSTEM_PROMPTS`.
3. **Tarefa/modelo**: por padrão reuse `TarefaIA.ANALISE_CASO` (mesmo perfil de modelo) —
   NÃO crie `TarefaIA` novo a menos que precise divergir modelo/tokens. Se criar um
   `TarefaIA` DE ÁREA, então: `prompt_key == tarefa.value`, adicione entrada em
   `CONFIGURACOES` e inclua a tarefa em `_TAREFAS_DE_AREA` no teste (o invariante proíbe
   tarefa de área cair no genérico `analise_caso`).
4. **Agente** em `ai/core/agent_registry.py`:
   ```python
   "<X>LawAgent": AgenteInterno(
       nome="<X>LawAgent", descricao="...", dominios=["<ramo>", "<sinônimos>"],
       tarefa_padrao=TarefaIA.ANALISE_CASO, prompt_key="<ramo>",
       exige_fonte=True,
       skills=_skills("build_case_context", "retrieve_rag_sources", "validate_citations"),
   ),
   ```
5. **Roteamento** em `ai/core/intent_classifier.py`: adicione as chaves de área e sinônimos
   em `TASK_TYPE_PARA_AGENTE` → `"<X>LawAgent"`, e uma tupla em `_KEYWORDS_PARA_AGENTE`
   (mais específico primeiro) para o fallback por mensagem.
6. **Invariante**: se o agente faz afirmação normativa (lei/súmula/precedente), inclua o
   nome em `_AGENTES_NORMATIVOS` no teste — ele passa a EXIGIR `exige_fonte=True` +
   `validate_citations` + `retrieve_rag_sources`.
7. **Frontend (se deve aparecer na UI)**: registre em `frontend/src/config/moduleRegistry.tsx`
   (consumido por `MapaModulos.tsx` / `AgenteIA.tsx`).
8. **Validar**: `cd backend && python -m pytest tests/test_agentes_invariantes.py tests/test_ai_core_nucleo.py -v` e `graphify update .`.

## Regras invioláveis (a barreira)

- **Todo** prompt = `BASE_PROMPT + <regra> + AVISO_RASCUNHO`. Nunca um system prompt sem a
  base (fura OAB/LGPD/anti-alucinação). O teste `test_prompt_key_das_novas_areas_carrega_barreira`
  confere `IDENTIDADE` e `RASCUNHO` no texto.
- Agente normativo → `exige_fonte=True` + `retrieve_rag_sources` + `validate_citations`.
  Só citar RAG com status "aprovado" (nunca "pendente"/"recusado").
- Toda saída é RASCUNHO (HITL). `cliente_externo` NUNCA acessa o núcleo (bloqueado no
  orchestrator/router). Skills de patch (`apply_authorized_patch`/`rollback_patch`) têm
  `handler=None` DE PROPÓSITO — aplicação de mudança nunca é automática.
- Não crie um 2º caminho de execução de IA fora do `orchestrator.run` / `ai_gateway.chat`
  (ponto único de despacho, custo e AILog).

## Antes de dar por concluído
`qa-tests` (invariantes verdes) → `security-auditor` (tocou barreira/PII/roles) →
`code-reviewer` → `verifier`. Nunca marque teste de invariante como skip/xfail.
