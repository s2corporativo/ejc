# Laudo de Auditoria do Sistema de IA do EJC
**Data:** 2026-07-17 · **Escopo:** subsistema de Inteligência Artificial (backend `app/services/ai/**`, `ai_gateway`, RAG, providers, sanitização, validação, HITL) · **Método:** leitura direta do código + orientação por graphify + auditorias especialistas paralelas (backend, segurança, pesquisa de metodologia)

---

## 1. Sumário executivo

O sistema de IA do EJC é **arquiteturalmente maduro e bem governado** — significativamente acima da média para software jurídico. O "Núcleo Único" (`orchestrator.py`) centraliza toda chamada de IA sob um fluxo imutável (intenção → RBAC/ownership → contexto/RAG → sanitização LGPD → provider → validação de citações → HITL → AILog). Pseudonimização reversível, gate anti-alucinação de citações, modo adversarial "Duas IAs" e trilha de auditoria obrigatória já estão implementados e são de boa qualidade.

**O teto de inteligência hoje NÃO é o modelo** (produção já usa **Claude Opus 4.8** para tarefas complexas). O teto está em **três lacunas de engenharia de RAG e de raciocínio**:

1. **Recuperação (retrieval) sem reranking** e com embedding de 2021 → o modelo recebe contexto mais fraco do que poderia.
2. **Raciocínio jurídico não-estruturado** → depende de um prompt "nível de inteligência", sem decomposição IRAC/FIRAC, self-consistency ou tool-use ao vivo.
3. **Ausência de harness de avaliação** → não há baseline nem regressão de qualidade, então toda melhoria é feita "no escuro".

Além disso, há **1 inconsistência de severidade ALTA** (IA criminal bloqueada em produção por conflito entre política de sanitização e configuração de deploy).

**Recomendação central de metodologia:** adotar um ciclo **eval-driven** — montar um conjunto de avaliação jurídico (gold set) ANTES de qualquer mudança, medir baseline, e só então iterar em retrieval → raciocínio → modelo, medindo cada passo.

---

## 2. Arquitetura atual (fluxo de uma requisição)

```
Frontend (envia só IDs)
   │
   ▼
SingleAICoreOrchestrator.run()           app/services/ai/core/orchestrator.py
   │ 1. classify_intent → agente interno (AGENT_REGISTRY)
   │ 2. RBAC/ABAC + verificar_acesso_caso (fail-closed; cliente_externo bloqueado)
   │ 3. context_builder.montar_contexto → dossiê + RAG (ownership de doc/processo validado)
   │ 4. sanitizar_ou_abortar (defesa em profundidade de entrada)
   │ 5. AIProviderPolicy.avaliar (política central de provider)
   │ 6. ai_gateway.chat(...)  ─────────────┐
   │ 7. response_validator.validar         │  barreira FINAL de PII por provider externo
   │ 8. audit_logger.registrar (OBRIGATÓRIO; erro propaga)
   │ 9. adversarial.criticar_peca (Duas IAs, provider diverso, não bloqueia)
   │ 10. hitl_policy.aplicar → rascunho
   ▼
ai_gateway.chat()                         app/services/ai_gateway.py
   │ - ai_cache (dedup por TTL)
   │ - model_router (opt-in, LIGADO): score determinístico → tier → provider de partida
   │ - _resolver_cadeia: ordena por AI_PROVIDER_PRIORITY + elegibilidade
   │ - _chamar_com_barreira (FONTE ÚNICA de barreira LGPD):
   │       provider externo → pseudonimiza (marcadores) → verifica PII residual →
   │       chama provider → REIDRATA a resposta localmente
   │ - fallback automático na cadeia; Langfuse (self-host, no-op se off)
   ▼
Providers: anthropic (Opus 4.8 / Haiku 4.5) · groq (llama-3.3-70b) · ollama (local, off em prod)

RAG:  ai_service.buscar_contexto_rag()    app/services/ai_service.py
   │ - embeddings locais (fastembed): paraphrase-multilingual-mpnet-base-v2 (768d)
   │ - pgvector cosine (<=>), threshold _RAG_MIN_SIM=0.55
   │ - _fundir_lexical: RRF (semântico + pg_trgm similarity), k=60
   │ - isolamento por cliente (_escopo_cliente_do_caso, fail-closed)
   │ - gate de governança (docs bloqueados/pendentes/fictícios excluídos)
```

**Postura de produção real (`docker-compose.yml`):** `OLLAMA_ENABLED=false`, `AI_PROVIDER_PRIORITY="anthropic,groq,ollama"`. Ou seja: tarefas complexas vão para **Opus 4.8** (com pseudonimização reversível), Groq como fallback, Ollama não sobe. Toda tarefa jurídica tem default `EXTERNO_PSEUDONIMIZADO`.

---

## 3. Pontos fortes (maduros — preservar)

| Área | O que já está bem feito |
|---|---|
| **Barreira LGPD** | Fonte única `_chamar_com_barreira` (elimina divergência entre `chat()` e `executar_tarefa_ia()`); pseudonimização **reversível** com mapa que vive só em memória (nunca logado/persistido); 2ª barreira `validar_sem_pii` detecta PII estrutural residual e **pula** o provider externo. |
| **Anti-injection** | Contexto de terceiros (OCR/RAG/dossiê) nunca entra no system prompt; vai delimitado como DADO com instrução explícita de ignorar comandos. Na crítica adversarial, delimitador usa **token aleatório por chamada** (dificulta escape). |
| **Anti-alucinação** | Gate de citações (`citation_check`/`citation_gate`) confere súmulas/artigos contra base oficial; política "bloquear" força override justificado no HITL. Aplicado **inclusive à própria crítica adversarial**. |
| **Duas IAs** | Crítica adversarial prefere **provider diverso** (reduz erro correlacionado), gera nota de robustez, **nunca bloqueia** a entrega, e a jurisprudência que ela sugere também passa pelo gate. |
| **Governança** | AILog obrigatório com erro que **propaga** (sem trilha ⇒ sem resposta); HITL carimbado; detecção de promessa de resultado (vedação OAB). |
| **Isolamento** | RAG restrito ao `client_id` do próprio caso (fail-closed); ownership de `document_id`/`process_id` validado no builder (não confia só no gate de `case_id`). |
| **Operação** | Roteamento determinístico por custo/complexidade; cache de IA; observabilidade Langfuse; custo por provider (fonte única `ai_cost`). |

---

## 4. Achados: erros, falhas e inconsistências

> Severidade: 🔴 Alto · 🟠 Médio · 🟡 Baixo. Achados de segurança/backend em curso pelos auditores especialistas serão anexados; abaixo, os já **verificados diretamente no código**.

### 🔴 A-1 · IA criminal bloqueada em produção (inconsistência código × doc × deploy)
- **Onde:** `app/services/ai/sanitization_policy.py:66` mapeia `"criminal": LOCAL_COMPLETO`.
- **Conflito:** o docstring do mesmo arquivo (linhas 151-156) afirma "nenhuma tarefa tem mais default LOCAL_COMPLETO (inclusive `criminal`, agora `EXTERNO_PSEUDONIMIZADO`)". Código e documentação **divergem**.
- **Efeito em produção:** o compose tem `OLLAMA_ENABLED=false`. Uma tarefa criminal cai em `_restringir_cadeia_local_completo` (remove providers externos) → cadeia vazia → `RuntimeError("… habilite o Ollama")`. **A IA em matéria criminal não funciona em produção** (bloqueio, não vazamento — fail-closed, o que é seguro, mas a funcionalidade fica indisponível silenciosamente).
- **Decisão necessária (do escritório):** (a) subir Ollama on-prem para o tier criminal; **ou** (b) alinhar o código à decisão de produto (criminal → `EXTERNO_PSEUDONIMIZADO`) — o que **exige antes** reforçar o NER local contra nomes de vítima/testemunha que aparecem só no documento/OCR (o próprio comentário reconhece esse risco: a 2ª barreira pega PII estrutural, não nomes próprios não cadastrados como parte).

### 🟠 A-2 · Threshold de similaridade fixo e não calibrado
- **Onde:** `app/services/ai_service.py:130` — `_RAG_MIN_SIM = 0.55` hardcoded.
- **Problema:** o corte de similaridade não é configurável nem calibrado empiricamente. Para o cosseno do mpnet, 0.55 é arbitrário: pode **cortar precedente relevante** (recall baixo) ou **deixar passar ruído**. Sem eval set, não há como saber para que lado erra.
- **Correção:** tornar configurável (`RAG_MIN_SIM` em settings) e calibrar contra um gold set. Idealmente substituir "threshold fixo" por "top-k + reranker" (ver O-1).

### 🟠 A-3 · Parte lexical do híbrido é trigram (pg_trgm), não relevância lexical (BM25)
- **Onde:** `ai_service._fundir_lexical` usa `similarity(kc.conteudo, :q)` (pg_trgm) com corte `> 0.05` sobre `consulta[:300]`.
- **Problema:** pg_trgm é **similaridade fuzzy de string por trigramas de caracteres** — bom para typos, fraco para relevância de termos raros/técnicos. Para casar **citações exatas** (art., súmula, nº CNJ, "REsp") e jargão jurídico, `tsvector`/full-text (BM25) rankeia muito melhor. Além disso, truncar a consulta em 300 chars descarta sinal em queries longas.
- **Correção:** trocar a perna lexical do RRF por FTS Postgres (`to_tsvector('portuguese', …)` + `ts_rank_cd`) ou `pg_search`/ParadeDB (BM25 real). Baixo/médio esforço, mantém a fusão RRF já existente.

### 🟠 A-4 · Detecção de promessa de resultado (OAB) por regex frágil
- **Onde:** `response_validator._RE_PROMESSAS`.
- **Problema:** cobre frases óbvias ("garantia de êxito", "100% de chance") mas é **escapável por paráfrase** ("as chances são altíssimas e dificilmente perderemos"). É um alerta HITL, não um bloqueio — então o risco é moderado, mas a cobertura é ilusória.
- **Correção:** complementar com um classificador leve (pode ser o próprio Haiku 4.5 como juiz barato) ou ampliar o conjunto de padrões; manter como alerta, nunca reescrita silenciosa (a decisão atual de **não reescrever** está correta).

### 🟡 A-5 · Embedding desatualizado (ver também O-2)
- **Onde:** `embedding_service.py:23` — `paraphrase-multilingual-mpnet-base-v2` (2021, 768d).
- **Problema:** modelo generalista de 2021; recall inferior ao estado da arte multilíngue atual. Não é "erro", mas é dívida de qualidade que limita todo o RAG a montante.

### 🟡 A-6 · Proliferação de routers `ia_*` vs. princípio "Núcleo Único"
- **Observação:** há ~15+ routers com prefixo `ia_*`/IA (`ia_especializada`, `ia_defensiva`, `ia_extra`, `ia_citacoes`, `ia_governanca`, `veredito_ia`, `documento_ia`, `ia_saude`, …). O orquestrador afirma "nenhum módulo tem IA própria". **Vale confirmar** (auditoria backend em curso) que todos realmente convergem para `orchestrator`/`ai_gateway` e não montam pipelines paralelos com prompts divergentes — risco de inconsistência de contrato e de governança se algum atalhar o núcleo.

---

## 5. Oportunidades para aumentar inteligência e raciocínio jurídico

> Ordenado por **impacto × esforço**. As três primeiras são o "quick win" de maior retorno.

### O-1 · 🥇 Reranker cross-encoder no topo do retrieval — **impacto ALTO, esforço BAIXO**
Hoje o pipeline é `pgvector cosine → RRF com pg_trgm`. Falta o passo que mais melhora precisão de contexto em RAG jurídico: **reranking**.
- **Como:** recuperar top-N amplo (ex.: 30-50 chunks) via híbrido atual, depois reordenar com um **cross-encoder** e passar só os top-6-8 ao modelo.
- **Modelo:** `BAAI/bge-reranker-v2-m3` (multilíngue, roda local via `fastembed`/`sentence-transformers`, alinhado à sua estratégia de soberania — não sai do VPS). Alternativa gerenciada: Cohere Rerank (mas envia texto à nuvem).
- **Ganho:** menos "contexto irrelevante", que é a principal causa de raciocínio fraco e de alucinação por distração. É a alavanca de melhor ROI.

### O-2 · 🥈 Upgrade de embedding PT-BR — **impacto ALTO, esforço MÉDIO**
- **Candidatos:** `BAAI/bge-m3` (1024d; denso + esparso + multi-vetor num só modelo, forte multilíngue) ou `intfloat/multilingual-e5-large` (1024d). Para estilo jurídico BR, avaliar também **Maritaca Sabiá** como serviço de embedding/geração PT-BR legal-tuned.
- **Custo de migração:** mudar a coluna `knowledge_chunks.embedding` de `vector(768)` para `vector(1024)` (nova migration Alembic) + **reindexar todo o corpus** (regerar embeddings). BGE-M3 ainda entrega a perna **esparsa** de graça, o que ataca A-3 (lexical) no mesmo passo.
- **Recomendação:** decidir 768→1024 **guiado pelo eval set** (O-4) — medir recall antes/depois, não trocar às cegas.

### O-3 · 🥉 Raciocínio jurídico estruturado (IRAC/FIRAC) + extended thinking — **impacto ALTO, esforço MÉDIO**
Hoje o "raciocínio" é um parágrafo de prompt (`NIVEL_INTELIGENCIA_PROMPTS`). Estruturar de verdade:
- **Decomposição IRAC/FIRAC:** forçar o modelo a produzir, em etapas explícitas, **Fato → Questão → Regra (com fonte) → Aplicação → Conclusão**, separando fato/inferência/lacuna. Melhora a auditabilidade e a qualidade, e casa com o gate de citações (a "Regra" precisa de fonte verificável).
- **Extended thinking do Claude:** Opus 4.8 suporta raciocínio estendido — habilitar para tarefas `estrategia`/`elaboracao_peca`/`critica_adversarial` (as de tier pesado). Ganho direto de profundidade sem trocar de modelo. *(A cadeia de pensamento não deve ser exposta ao cliente — apenas usada internamente/para o revisor, coerente com "não revele cadeia de pensamento" já presente no prompt máximo.)*
- **Self-consistency** para questões de alto risco: gerar N respostas e consolidar/votar as conclusões convergentes (custo maior — reservar ao tier pesado).

### O-4 · Harness de avaliação jurídica (metodologia) — **impacto ALTO, esforço MÉDIO** — *pré-requisito das demais*
Sem isto, O-1/O-2/O-3 são apostas. Montar:
- **Gold set curado pelo escritório:** 50-150 casos-teste reais (pseudonimizados) com resposta/precedente esperado, cobrindo as áreas de atuação. É o ativo mais valioso e só o escritório pode produzir.
- **Métricas:** *faithfulness* (a resposta se apoia no contexto?), *context precision/recall* (o retrieval trouxe o certo?), *citação correta* (bate com a base oficial — você já tem o gate, basta medir a taxa).
- **Ferramentas:** **RAGAS** ou **DeepEval** para métricas de RAG; **promptfoo** para comparar prompts/modelos lado a lado em CI. **LLM-as-judge** com Haiku 4.5 (barato) para nota de qualidade jurídica; validar o juiz contra alguns julgamentos humanos.
- **Benchmarks públicos PT-BR** para calibrar o teto: **OAB-Bench**, **Magis-Bench**, **LegalBench-BR**.
- **Regressão em CI:** rodar o eval set a cada mudança de prompt/modelo/threshold e barrar queda. Transforma "achismo" em número.

### O-5 · Tool-use / grounding ao vivo — **impacto MÉDIO-ALTO, esforço MÉDIO-ALTO**
Em vez de só recuperar da base interna, dar ao modelo **ferramentas** para consultar legislação/jurisprudência atualizada (planalto, tribunais) em tempo de resposta, com verificação de fonte. Reduz alucinação e desatualização. Já existem integradores (`integrador-apis-externas-ejc`) — o passo é expor como *tools* ao Núcleo. Requer cuidado de LGPD (o que sai na consulta) e de latência.

### O-6 · HyDE / query expansion no retrieval — **impacto MÉDIO, esforço BAIXO**
Gerar uma "resposta hipotética" barata (Haiku) para a consulta e embutir **isso** na busca vetorial (HyDE), ou expandir a query com sinônimos jurídicos. Melhora recall quando o vocabulário do caso novo difere do registrado — exatamente o cenário que o `modo_or` já tenta cobrir de forma rudimentar.

### O-7 · Ajuste de tiering de modelo por custo/qualidade — **impacto MÉDIO, esforço BAIXO**
Com a pesquisa de modelos 2026 em mãos: usar **Claude Sonnet 5** como default de drafting de valor (qualidade quase-frontier a custo baixo), reservar **Opus 4.8** só para o passo final de raciocínio/crítica difícil, e **Haiku 4.5**/Groq para classificação/roteamento/reescrita de query. Ativar **prompt caching** (−90% em contexto repetido, ex.: system prompts e textos de lei) e **Batch API** (−50%) para lotes não-interativos. Piloto opcional de **Maritaca Sabiá-4** (128k, legal-tuned PT-BR, fornecedor no Brasil) para alto volume de redação BR.

---

## 6. Metodologia recomendada (ciclo eval-driven)

```
1. BASELINE   → montar gold set (O-4) e medir o pipeline ATUAL. Nada muda antes disso.
2. RETRIEVAL  → O-1 (reranker) → medir. O-3-lexical/A-3 (BM25) → medir. O-2 (embedding) → medir.
3. RACIOCÍNIO → O-3 (IRAC + extended thinking) → medir. Self-consistency no tier pesado → medir.
4. MODELO     → O-7 (tiering/caching) → medir custo × qualidade.
5. CI         → travar regressão; cada PR roda o eval set.
6. LOOP       → priorizar o próximo item pelo ganho medido, não pela intuição.
```
Princípio: **uma variável por vez, sempre medindo**. O gate de citações e o modo Duas IAs que você já tem são, na prática, dois avaliadores automáticos — a taxa de citações não-confirmadas e a nota de robustez já podem virar as **primeiras métricas** do baseline sem nenhum código novo.

---

## 7. Roteiro priorizado (fases)

| Fase | Itens | Esforço | Retorno |
|---|---|---|---|
| **0 — Corrigir e medir** | A-1 (decisão criminal), O-4 (gold set + baseline com métricas que já existem: taxa de citação não-confirmada, nota de robustez) | Baixo | Destrava criminal; cria a régua |
| **1 — Retrieval** | O-1 (reranker bge-v2-m3), A-3/A-2 (BM25 + threshold configurável) | Baixo-Médio | Maior salto de qualidade por real gasto |
| **2 — Raciocínio** | O-3 (IRAC + extended thinking), O-6 (HyDE) | Médio | Profundidade e auditabilidade jurídica |
| **3 — Corpus** | O-2 (embedding 1024d + reindex), guiado pelo eval | Médio | Recall; valida com número |
| **4 — Escala/custo** | O-7 (tiering/caching/batch), A-4 (promessa OAB), O-5 (tool-use) | Médio | Custo menor + grounding ao vivo |

---

### Anexos em processamento
Auditorias especialistas de **backend** (duplicação entre routers `ia_*`, timeouts/retries dos providers, contratos) e de **segurança/LGPD** (vazamento de PII em algum caminho, cross-tenant, `rag_public` sem auth, PII em log) foram disparadas em paralelo. O eixo de **escolha de modelos 2026** da pesquisa externa (Magis-Bench, Sabiá-4, tiering de custo, Sonnet 5, caching) já está incorporado nas seções 5 e 7.

---

## 8. Status de implementação (2026-07-17)

Todo o roteiro foi implementado neste PR — **cada mudança é aditiva e fail-safe** (com o flag desligado ou o recurso indisponível, o comportamento é idêntico ao atual, o padrão da casa). Como o ambiente de desenvolvimento não tem as dependências do backend e o CI está fora do ar (falha de infra/cota, não de código), a validação foi por `py_compile` + testes unitários novos; **a execução da suíte fica para quando o CI voltar**.

| Item | Status | Como |
|---|---|---|
| **O-1** reranker | ✅ feito | `ai/reranker.py` (cross-encoder local, `RAG_RERANK_ENABLED`) + pool no retrieval |
| **A-1** IA criminal | ✅ feito | `criminal → EXTERNO_PSEUDONIMIZADO`. O **reforço de NER já existia** (`pseudonymizer` 3ª passada + `ner_local`) — só faltava ligar |
| **A-2** threshold | ✅ feito | `RAG_MIN_SIM` configurável |
| **A-3** BM25/FTS | ✅ feito | 3ª perna RRF full-text + migration 095 (índice GIN); `RAG_FTS_ENABLED` (OFF) |
| **A-4** promessa OAB | ✅ feito | regex tolerante a acento/paráfrase (alerta, nunca reescrita) |
| **O-2** embedding | ✅ feito | BGE-M3 1024d configurável + migration 096 + reindex (runbook). **Requer migrate→reindex no deploy** |
| **O-3** FIRAC | ✅ feito | prompt FIRAC nos níveis alto/máximo. **Extended thinking do Opus 4.8 já estava ligado** no provider |
| **O-4** eval harness | ✅ feito | `app/eval/` (runner + gold set + README): hit@k/precision/recall/MRR, alucinação, groundedness |
| **O-5** grounding ao vivo | ✅ feito | validador confere citações via `verificador_jurisprudencia` (DataJud); `AI_LIVE_GROUNDING_ENABLED` (OFF) |
| **O-6** HyDE | ✅ feito | `_hyde_expandir` só na query densa; `RAG_HYDE_ENABLED` (OFF) |
| **O-7** caching/tiering | ✅ já existia | prompt caching + adaptive thinking já no `anthropic_provider` |

**Descobertas que reduziram o trabalho/risco:** o provider Anthropic **já** fazia prompt caching e extended thinking (O-7 + parte de O-3); o pseudonimizador **já** tinha NER local para nomes de vítima/testemunha (o pré-requisito de A-1); e o `verificador_jurisprudencia` **já** confirmava nº CNJ no DataJud (o núcleo de O-5). O sistema estava mais maduro do que o roteiro presumia.

**Flags novas (todas default-safe):** `RAG_RERANK_ENABLED=true`, `RAG_MIN_SIM=0.55`, `RAG_HYDE_ENABLED=false`, `RAG_FTS_ENABLED=false`, `EMBEDDINGS_MODEL=BAAI/bge-m3`, `EMBEDDINGS_DIM=1024`, `AI_LIVE_GROUNDING_ENABLED=false`.

**Ordem de ativação recomendada (eval-driven):** montar o gold set (O-4) e medir baseline → ligar reranker e comparar → migração/reindex do embedding (runbook) e comparar recall → ligar FTS/HyDE e comparar → ligar grounding ao vivo após validar DataJud. Uma variável por vez, sempre medindo.
