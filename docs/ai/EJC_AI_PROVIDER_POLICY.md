# EJC — AIProviderPolicy (política central de provedores)

Data: 2026-07-04 · Atualizado: 2026-07-26 · Código: `backend/app/services/ai/provider_policy.py`.

A `AIProviderPolicy` (provider_policy.py:43) decide, ANTES de qualquer chamada de modelo: quais providers são elegíveis, em que ordem tentar, se o conteúdo exige sanitização para destino externo e se a chamada é permitida. É **decisão pura** — não chama modelo; o despacho continua no `ai_gateway`.

## 0. Decisão do escritório (2026-07-26) — qualidade acima de custo, sempre

Dr. Clovis / De Paula Teixeira Advogados decidiu **explicitamente**, ciente do aumento de custo operacional de IA que isso implica, abrir mão do roteamento por custo que existia até esta data. A partir de 2026-07-26:

- **TODA tarefa de IA** — inclusive as que até então eram roteadas para Ollama/Groq por classificação de "tarefa econômica" (resumo, triagem, chat rápido) — passa a priorizar o **provedor mais capaz disponível**: Anthropic (Claude), elegibilidade permitindo.
- **Dentro do Anthropic**, o modelo escolhido é sempre o de **maior capacidade configurada** (`ANTHROPIC_MODEL_COMPLEXO`, ex. Opus) — não há mais tier "leve"/rápido (Haiku) por classificação de tarefa. Isso vale tanto no caminho do Núcleo Único (`AIProviderPolicy`/orchestrator) quanto no caminho legado (`ai_gateway.TASK_ROUTING`/`executar_tarefa_ia`/`system_prompts/router.py`) e no roteamento inteligente por complexidade (`model_router.py`, `ROTEAMENTO_PROVIDER_LEVE/MEDIO/PESADO=anthropic`).
- Ollama e Groq **continuam existindo na cadeia como FALLBACK** — usados quando Anthropic está indisponível, sem chave, ou bloqueado pelo kill-switch (`ANTHROPIC_ENABLED=false` / `AI_EXTERNAL_PROVIDERS_ALLOWED=false`) — nunca mais como escolha primária por custo.
- **O que NÃO mudou** (inegociável, não tocado por esta decisão): os kill-switches (`AI_EXTERNAL_PROVIDERS_ALLOWED`, `ANTHROPIC_ENABLED`, `OLLAMA_ENABLED`) continuam funcionando exatamente como antes; a barreira de sanitização de PII antes de qualquer provedor externo (`AI_REQUIRE_SANITIZATION_FOR_EXTERNAL`) continua obrigatória e continua removendo externos da cadeia se sobrar PII residual; HITL (`AI_REQUIRE_HITL`, `is_rascunho=True`) e o gate anti-alucinação de citações (`citation_gate.py`) continuam 100% intactos. Esta é uma mudança de **critério de escolha de provedor/modelo**, não de segurança/governança.
- **Custo operacional**: esperado um aumento MATERIAL do gasto com IA (ver `docs/ai/EJC_AI_COST_AND_AUDIT_POLICY.md`, §5, atualizado) — tarefas de altíssimo volume (triagem, resumo, prazos, honorários, audiência, RAG) que antes custavam ~0 (Ollama/Groq) ou usavam o tier rápido (Haiku) passam a usar Anthropic Opus. Monitorar via `/ia-saude/dashboard`; o baseline de custo "normal" deve ser recalibrado para refletir esta política, não o padrão anterior.

## 1. Entrada e saída

```python
AIProviderPolicy().avaliar(texto_completo, task_type, *,
                           ja_sanitizado=False, exige_fonte=False) -> PolicyDecision
```

`PolicyDecision` (provider_policy.py:32-40):

| Campo | Significado |
|---|---|
| `permitido: bool` | False = chamada bloqueada |
| `provider_chain: list[(provider, model|None)]` | Ordem de tentativa; model=None (o gateway resolve por tarefa) |
| `sanitizar_antes: bool` | Destino externo na cadeia exige conteúdo sanitizado |
| `motivo: str` | Justificativa da decisão (auditável) |
| `requer_hitl: bool` | Espelha `AI_REQUIRE_HITL` |
| `requer_fonte: bool` | Propaga `exige_fonte` do agente |
| `bloqueio_motivo: str|None` | Mensagem SEGURA de bloqueio (nunca ecoa conteúdo/valores de PII) |

O orchestrator invoca a policy após a sanitização do input (`ja_sanitizado=True`) e converte `permitido=False` em HTTP 422 com `bloqueio_motivo` (orchestrator.py:115-122).

## 2. Elegibilidade por provider (`_elegivel`, provider_policy.py:46-58)

| Provider | Condição |
|---|---|
| `ollama` | `OLLAMA_ENABLED` |
| `anthropic` | `ANTHROPIC_ENABLED` + `ANTHROPIC_API_KEY` + `AI_EXTERNAL_PROVIDERS_ALLOWED` |
| `groq` | `GROQ_API_KEY` + `AI_EXTERNAL_PROVIDERS_ALLOWED` |
| outros | sempre False |

`AI_EXTERNAL_PROVIDERS_ALLOWED=false` desliga TODOS os externos de uma vez (soberania de dados).

## 3. Ordem base — `AI_PROVIDER_PRIORITY`

CSV em Settings (default `ollama,anthropic,groq`, config.py:92). `_ordem_prioridade` (provider_policy.py:60-68) deduplica e normaliza; vazio → fallback `["ollama","anthropic","groq"]`. Cadeia base = prioridade filtrada por elegibilidade.

## 4. Priorização por perfil de tarefa — REVOGADA em 2026-07-26 (agora uniforme)

Até 2026-07-04 a policy diferenciava `TAREFAS_COMPLEXAS` (Anthropic à frente) de `TAREFAS_ECONOMICAS` = {resumo, triagem, chat_rapido} (Ollama/Groq à frente, custo ~zero). Essa distinção foi **removida** pela decisão do escritório (§0): a partir de 2026-07-26 a priorização é a MESMA para qualquer `task_type` (provider_policy.py, bloco "Priorização: sempre o provedor mais capaz elegível"):

- Anthropic elegível → vai para a FRENTE da cadeia, sempre, qualquer tarefa.
- Anthropic não elegível + Maritaca elegível → Maritaca (Sabiá) priorizada entre os EXTERNOS, mas nunca à frente de um provider LOCAL elegível (minimização LGPD — o dado só sai do VPS quando não há opção local; esta regra de minimização não mudou).
- `TAREFAS_COMPLEXAS` permanece como constante no código só para referência/documentação (vocabulário `TarefaIA`/task_types); não influencia mais a ordem.
- Aceita tanto nomes de `TarefaIA` quanto task_types do gateway (sem efeito na priorização, apenas vocabulário aceito).

## 5. Barreira LGPD (provider_policy.py:95-110)

Se há externo elegível e `AI_REQUIRE_SANITIZATION_FOR_EXTERNAL=true`:
1. `sanitizar_antes=True`; se `ja_sanitizado=False`, aplica `sanitizar_pii` internamente;
2. `validar_sem_pii` checa residual (CPF/CNPJ/processo/RG/e-mail/telefone/CEP);
3. residual encontrado → **externos removidos da cadeia** (fica só Ollama local, se habilitado); motivo registra apenas os TIPOS de PII;
4. cadeia vazia → `permitido=False` com `bloqueio_motivo` seguro: "Nenhum provedor de IA elegível... Habilite o Ollama local (OLLAMA_ENABLED=true) ou remova dados pessoais do texto" (provider_policy.py:123-136). O conteúdo jamais é ecoado.

## 6. Dupla barreira

A policy decide no núcleo, mas o `ai_gateway` **não confia** nessa decisão: antes de despachar a cada provider externo ele re-sanitiza toda mensagem e pula o provider se sobrar PII (`_sanitizar_messages_externo` + loop, ai_gateway.py:192-207, 333-347). Se todos os externos forem pulados por PII e não houver local, o gateway falha com mensagem segura (ai_gateway.py:242-247). Regras de elegibilidade são idênticas nos dois pontos (`_provider_elegivel`, ai_gateway.py:272-283).

## 7. Roteamento recomendado por cenário (atualizado 2026-07-26)

| Cenário | Cadeia resultante | Por quê |
|---|---|---|
| Qualquer tarefa (análise, minuta, dossiê, **resumo, triagem, chat rápido**), conteúdo limpo | anthropic → ollama → maritaca → groq | Qualidade acima de custo, TODA tarefa — Claude (MODEL_COMPLEXO) sempre priorizado quando elegível |
| Anthropic indisponível/sem chave, Maritaca elegível | maritaca priorizada entre externos (após locais elegíveis) | Melhor raciocínio jurídico PT-BR externo remanescente; minimização LGPD mantém local à frente |
| Qualquer tarefa com PII residual após sanitização | somente ollama | Externos removidos (LGPD) — inalterado |
| PII residual e `OLLAMA_ENABLED=false` | (vazia) → HTTP 422 | Bloqueio com motivo seguro — inalterado |
| `AI_EXTERNAL_PROVIDERS_ALLOWED=false` | somente ollama | Modo soberania total — inalterado |
| `ANTHROPIC_ENABLED=false` (kill-switch) | ollama → maritaca → groq | Claude fora sem apagar a chave — Ollama/Groq como fallback (nunca mais como escolha primária por custo) |

Antes de 2026-07-26: resumo/triagem/chat rápido eram roteados para Ollama/Groq por custo e Anthropic nem participava do `TASK_ROUTING` dessas tarefas. Essa distinção foi removida — ver §0 e §4.
