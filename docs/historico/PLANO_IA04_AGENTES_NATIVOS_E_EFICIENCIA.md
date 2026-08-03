# Plano — Agentes Nativos por Atuação + Eficiência do Núcleo de IA (EJC)

> Documento de PLANEJAMENTO. Nada aqui é executado automaticamente — cada fase abre
> como trabalho revisável (diff + testes + auditoria) antes de merge. Baseado no
> mapeamento verificado do Núcleo Único de IA (`system_prompts/`, `ai/core/*`),
> da biblioteca de prompts (`PromptJuridico`), das skills configuráveis (`EjcSkill`)
> e da infraestrutura de tasks/observabilidade (Celery/Redis, Langfuse, `ai_cost`).
> Princípio reitor: **Segurança/OAB > Cobertura > Eficiência** — nunca inverter essa ordem.

---

## 0. Achado que muda a ordem de execução (bloqueante, ler primeiro)

A investigação encontrou **quatro sistemas paralelos** que geram prompt para o LLM,
não dois:

| # | Sistema | Onde | Passa pela barreira central (`BASE_PROMPT`/`aplicar_base`)? |
|---|---|---|---|
| 1 | Núcleo Único (`system_prompts` + `agent_registry` + `orchestrator`) | `backend/app/services/ai/core/*`, `services/system_prompts/*` | **Sim** — é a própria fonte |
| 2 | Pipeline legada (`ai_service.py`) | `backend/app/services/ai_service.py` | Não — regra inline própria (já mapeado em `MAPA_PROMPTS_IA03.md`) |
| 3 | **Skills configuráveis no banco** (`EjcSkill`) | `models/ai_skill.py`, `services/ai_skill_service.py` | **Não verificado** — `system_prompt` é texto livre gravado no banco, sem referência a `BASE_PROMPT` |
| 4 | **Biblioteca de prompts do usuário** (`PromptJuridico`) | `models/prompt_juridico.py`, `routers/prompts_juridicos.py:executar_prompt()` | **Não verificado** — `conteudo` é texto livre com placeholders `{{variavel}}`, editável por qualquer usuário com acesso |

Os sistemas 3 e 4 são o maior risco real hoje: um usuário (ou admin) pode criar uma
skill ou um prompt novo pelo banco/UI que **nunca passa pelas 16 regras de
`BASE_PROMPT`** (proibição de inventar jurisprudência/processo, aviso de rascunho,
LGPD). Isso é pior que uma lacuna de cobertura de agente, porque não deixa rastro
no código — só no banco.

**Consequência para este plano:** a Fase 1 (auditoria de segurança dos sistemas 3/4)
é pré-requisito e bloqueia as Fases 2-3 (novos agentes). Não faz sentido multiplicar
agentes no Núcleo Único enquanto os outros dois canais de execução de prompt
continuam sem a mesma barreira.

---

## 1. Fase 1 — Auditoria e correção da barreira central em EjcSkill/PromptJuridico (bloqueante)

**Objetivo:** garantir que TODA execução de IA no sistema — não só o Núcleo Único —
carregue `BASE_PROMPT` (ou o equivalente `_REGRA_FONTES`/`AVISO_RASCUNHO`) antes de
sair para o provedor.

1. Ler `ai_skill_service.executar_skill()` e `prompts_juridicos.executar_prompt()`
   linha a linha; confirmar se `system_prompt`/`conteudo` do usuário é usado como
   system prompt FINAL (sem prefixo) ou se algo já injeta a base.
2. Se não injeta: alterar os dois pontos de execução para compor
   `BASE_PROMPT + <system_prompt do usuário> + AVISO_RASCUNHO` (mesmo padrão do
   pacote `system_prompts/`), preservando o texto do usuário como a parte
   específica, nunca substituindo-o.
3. Adicionar validação de criação/edição (`criar_prompt`, `atualizar_prompt` em
   `prompts_juridicos.py`; criação de `EjcSkill`): bloquear ou avisar se o
   conteúdo tentar remover/contradizer a barreira (heurística simples: recusar
   se contiver instruções tipo "ignore restrições anteriores").
4. Confirmar que `EjcSkill.oab_restricted` e `requires_human_review` realmente
   são checados em algum ponto do fluxo de execução (hoje parecem apenas
   colunas descritivas) — se não forem aplicados, é dado morto e deve virar
   enforcement real (bloquear execução/forçar `is_rascunho=True`).
5. Garantir que agentes com `exige_fonte=True` (Núcleo Único) e as skills/prompt
   library que citam jurisprudência só usem chunks do RAG com
   `RagStatus == "aprovado"` em `ia_governanca.py` — nunca "pendente"/"recusado".

**Validação:** `qa-tests` cobre os três caminhos de execução com o mesmo teste de
invariante (barreira presente na string final enviada ao provedor).
`security-auditor` revisa antes de prosseguir para a Fase 2.

---

## 2. Fase 2 — Cobertura de atuações jurídicas faltantes

Baseado em `CaseArea` (`models/case.py`) e nos modelos especializados já existentes
(`especializado.py`, `environmental.py`), quatro áreas reais do escritório caem hoje
no prompt genérico `PROMPT_ANALISE_CASO` sem regra normativa própria:

| Área (`CaseArea`) | Situação atual | Ação |
|---|---|---|
| `consumidor` | sem prompt_key dedicado | criar `system_prompts/consumidor.py` com base CDC (Lei 8.078/90), súmulas STJ de repetição, inversão do ônus da prova |
| `tributario` | sem prompt_key dedicado | criar `system_prompts/tributario.py` com base CTN, execução fiscal (Lei 6.830/80), prescrição/decadência tributária |
| `previdenciario` | sem prompt_key dedicado | criar `system_prompts/previdenciario.py` com base Lei 8.213/91, prazos do INSS, benefícios por incapacidade |
| `empresarial` | sem prompt_key dedicado (mas já tem `EmpresarialTipo`/`EmpresarialStatus` em `especializado.py`) | criar `system_prompts/empresarial.py` cruzando com os tipos já modelados (contratos societários, M&A, recuperação judicial) |

Para cada uma: `prompt_key` novo em `SYSTEM_PROMPTS`, `AgenteInterno` novo (ou
reuso de `CaseAgent` com `dominios` estendido — decidir por área durante
implementação, conforme a diferença de comportamento exigida), entrada em
`TASK_TYPE_PARA_AGENTE`. Reusar `TarefaIA.ANALISE_CASO` (mesmo perfil de modelo)
— não criar `TarefaIA` novo a menos que o roteamento de modelo precise divergir.

**Não pertinentes hoje** (não implementar sem confirmação): licitação/compliance já
existe (`LicitacaoComplianceAgent`) mas pode estar em descomissionamento —
confirmar com o usuário antes de expandir esse agente.

---

## 3. Fase 3 — Consistência de roteamento e dados

1. **`checklist.area_juridica`** (`models/checklist.py:27`) é `String(60)` livre,
   não usa o enum `CaseArea`. Alinhar para evitar que o roteamento de agente por
   área dependa de string digitada divergente do enum canônico (migration leve +
   validação Pydantic no schema de entrada).
2. **`_AREA_TASK`** em `ai_skill_service.py` só mapeia 3 buckets
   (`juridico`/`financeiro`/`operacional`) para `task_type` do `ai_gateway.chat()`
   — grosseiro demais para herdar o roteamento de modelo certo (Groq barato vs.
   Claude complexo) por área jurídica real. Avaliar rotear `EjcSkill.area` pelos
   mesmos `dominios`/`tarefa_padrao` do `agent_registry`, reaproveitando a
   granularidade já construída em vez de manter um segundo mapa paralelo.
3. Toda `TarefaIA` nova (se vier a existir) precisa de entrada correspondente em
   `CONFIG` (`system_prompts/router.py`) — nunca deixar membro órfão (cai em
   `default` silenciosamente ou quebra).

---

## 4. Fase 4 — Testes de invariante anti-lacuna/anti-regressão

Um único teste parametrizado que percorre os registries e falha se:
- algum alias em `TASK_TYPE_PARA_AGENTE` aponta para agente inexistente em
  `AGENT_REGISTRY`;
- algum `prompt_key` de agente não existe em `SYSTEM_PROMPTS`;
- alguma `tarefa_padrao` não tem entrada em `CONFIG`;
- algum agente jurídico com afirmação normativa tem `exige_fonte=False` mas o
  `prompt_key` associado não contém `_REGRA_FONTES`;
- (novo, pós-Fase 1) `executar_skill()`/`executar_prompt()` sempre compõem
  `BASE_PROMPT` no system prompt final enviado ao provedor (mock do client).

Isso transforma os achados deste plano em proteção permanente contra regressão
futura, em vez de correção pontual.

---

## 5. Fase 5 — Eficiência do sistema (achados concretos, não genéricos)

Grounded na infraestrutura real já existente — o objetivo é **reusar padrões que
já funcionam** em vez de introduzir camadas novas:

1. **Cache de resposta para chamadas idênticas.** `ai_gateway` hoje refaz a
   chamada ao provedor mesmo quando `case_id + task_type + hash(mensagem)`
   repete dentro de uma janela curta (ex.: usuário reenvia o mesmo caso após
   falha de rede, ou dois membros da equipe pedem a mesma análise). Adicionar
   cache de curto TTL (Redis, que já está disponível via `REDIS_URL`/
   `core/rate_limit.py`) chaveado por hash da requisição evita gasto duplicado
   de tokens/custo (`ai_cost.py` já mede — só falta evitar o refetch).
2. **Reaproveitar o padrão de fallback gracioso do `dispatcher.py`.** O
   dispatcher de indexação RAG (`tasks/dispatcher.py`) já resolve bem
   Celery-se-disponível → `BackgroundTasks`-senão. Ingestões pesadas que hoje
   rodam só como `BackgroundTasks` in-process (ex.: `sumulas_ingestion.py`,
   ingestão de jurisprudência em `ia_governanca.py:importar_jurisprudencia_mg`)
   deveriam passar pelo MESMO dispatcher — evita bloquear o worker web em
   ingestões grandes quando Celery está disponível, sem exigir Celery em
   ambientes sem Redis.
3. **Cache do embedding de query em buscas RAG repetidas.** `embedding_service.py`
   já faz singleton lazy-load do modelo (bom); falta cache do vetor de queries
   frequentes/repetidas (ex.: mesmo termo de busca por múltiplos usuários no
   mesmo dia) — LRU pequeno em memória evita recomputar embedding idêntico.
4. **Dashboard de custo agregado por período/área.** `ai_cost.py` calcula custo
   por chamada e grava em `AILog`; `ia_governanca.dashboard_governanca()` já
   agrega alguns dados de governança RAG. Verificar se já existe visão agregada
   de custo por área jurídica/mês — se não, é dado que já existe em `AILog` e só
   falta uma query de agregação, sem nova infraestrutura.
5. **Monitorar (não reverter) a decisão de desativar sanitização de PII.**
   `sanitizer.py` documenta uma decisão deliberada do titular (2026-07-05):
   PII vai em claro para provedores externos porque o mascaramento degradava a
   análise. Não é bug — é trade-off assumido. Sugestão de eficiência que NÃO
   contradiz a decisão: acrescentar ao Langfuse/AILog uma métrica de "volume de
   dado sensível que saiu para provedor externo (Anthropic/Groq) por período",
   para o titular acompanhar a exposição sem reverter o comportamento.
6. **Consolidar duplicação de tokens de prompt.** Cada `prompt_key` em
   `SYSTEM_PROMPTS` já reusa `BASE_PROMPT` (bom, DRY). Ao criar os 4 prompts da
   Fase 2, medir o tamanho de contexto resultante (`BASE_PROMPT` + `_REGRA_FONTES`
   + regra da área) — se aproximar do limite de tokens configurado por `TarefaIA`
   em `CONFIG`, considerar uma versão condensada de `_REGRA_FONTES` para tarefas
   de alto volume (ex.: `TRIAGEM`, que já usa Groq/tokens=1200).

---

## 6. Ordem de execução e responsáveis (agentes do projeto)

1. `security-auditor` + `backend-fastapi` — Fase 1 (bloqueante, prioridade máxima).
2. `backend-fastapi` — Fases 2 e 3 (podem rodar em paralelo entre si, mas só
   depois da Fase 1 fechada).
3. `qa-tests` — Fase 4, em paralelo assim que cada registry novo existir.
4. `backend-fastapi` — Fase 5, independente das demais (pode começar a qualquer
   momento; não mexe em regra de segurança).
5. `code-reviewer` → `verifier` — antes de qualquer merge.
6. `graphify update .` após cada fase.

## 7. Critérios de aceite

- [ ] `executar_skill()` e `executar_prompt()` comprovadamente injetam `BASE_PROMPT`
      (teste automatizado, não só leitura de código).
- [ ] `RagStatus` "aprovado" é o único status citável por agentes/skills com
      `exige_fonte=True`.
- [ ] 4 novas áreas jurídicas com prompt_key, agente e roteamento cobertos por teste.
- [ ] `checklist.area_juridica` usa `CaseArea` (ou é validado contra ele).
- [ ] Teste de invariante (Fase 4) rodando no CI.
- [ ] Pelo menos 1 melhoria de eficiência da Fase 5 implementada e medida
      (ex.: cache de resposta com hit-rate reportado).
- [ ] `security-auditor` sem achados críticos abertos.
