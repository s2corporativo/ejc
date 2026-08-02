# 06 — IA, RAG e knowledge graph jurídico (Fase 6)

> **Classificação global: FUNCIONAL COM RESSALVAS.** A arquitetura de IA é a parte mais sólida do
> EJC. Os achados P1 são de **cobertura de kill-switch** e **degradação silenciosa** — não de
> vazamento de dados. Três hipóteses do escopo da auditoria foram **refutadas** com evidência.

## 0. Quatro estruturas distintas — não confundir

| Estrutura | O que é | Onde | Situação |
|---|---|---|---|
| Grafo Graphify | grafo do **código-fonte** do repositório | `graphify-out/` | ferramenta de dev — ver `02` |
| Banco vetorial | `knowledge_chunks.embedding vector(1024)` + HNSW | PostgreSQL/pgvector | **FUNCIONAL** |
| RAG | ingestão → chunking → embedding → busca híbrida | `services/ai_service.py`, `ingestion_service.py` | **FUNCIONAL COM RESSALVAS** |
| Knowledge graph **jurídico** | grafo de teses/precedentes/normas | — | **NÃO LOCALIZADO** (§7) |

## 1. Gateway — `services/ai_gateway.py` (1 307 linhas)

**Invariante confirmada: toda chamada de IA passa pelo gateway.** Busca por SDK de provider
(`anthropic`, `openai`, `groq`, `ollama`) e por URL de API fora de `services/providers/` e do
gateway retornou **zero bypass real**. Os 5 candidatos foram lidos e são falsos positivos:
`services/credential_testers.py:175,188,199` faz `GET /v1/models` para **testar chave** (não envia
prompt nem PII) e `core/config.py:191,648` são defaults declarados.
Verificação independente minha: `grep -rn maritaca_provider` → 4 arquivos, todos legítimos.

**Cadeia de fallback:** `AI_PROVIDER_PRIORITY` (`config.py:258`) = `ollama → anthropic → maritaca
→ groq`, aplicada em `_ordenar_por_prioridade` (`:686`) e filtrada por `_provider_elegivel`
(`:667`). `TASK_ROUTING` (`:121-181`) define 9 tarefas e seus candidatos.

**Timeouts por provider:** Ollama 180 s · Anthropic 120 s · Maritaca 90 s · Groq 60 s.
**Retries: não existem** — a estratégia é fallback lateral (`:434-541`). Um 429/529 transitório da
Anthropic degrada imediatamente para outro provider em vez de esperar (P2).

### 1.1 Kill-switches — quatro flags, coberturas diferentes

| Flag | Default | Desliga | Aplicado em |
|---|---|---|---|
| `AI_EXTERNAL_PROVIDERS_ALLOWED` | `true` | Anthropic + Groq + Maritaca (soberania) | `_provider_elegivel:667` — **cobre tudo** |
| `AI_REQUIRE_SANITIZATION_FOR_EXTERNAL` | `true` | a barreira de PII | `_chamar_com_barreira:274`, `chat_agentico:1275` |
| `AI_AGENT_ENABLED` | `false` | módulo agêntico | fora do gateway |
| **`AI_ENABLED`** | `true` | **nada dentro do gateway** | só `transcrever_audio:574` e `ia_disponivel():662` |

> ### 🔴 P1 — o kill-switch de IA é contornável
>
> `chat()` (`ai_gateway.py:291`) e `executar_tarefa_ia()` (`:903`) **não consultam `AI_ENABLED`**.
> A verificação foi delegada aos chamadores e a cobertura é parcial. Confirmado por mim:
>
> | Router | `AI_ENABLED` | usa gateway |
> |---|---|---|
> | `routers/provas.py` | **0** | sim |
> | `routers/teses.py` | **0** | sim |
> | `routers/jurisprudencia_interna.py` | **0** | sim |
> | `routers/prompts_juridicos.py` | **0** | sim |
> | `routers/ia_saude.py` | **0** | sim |
>
> Com `AI_ENABLED=false`, esses endpoints **continuam gerando e cobrando IA**. `ai_tools.py:48`
> agrava: relê `os.getenv("AI_ENABLED")` cru em vez de `settings`.
> **Correção mínima:** mover o gate para dentro de `chat()` / `executar_tarefa_ia()` /
> `chat_agentico()`. É mudança de comportamento — exige decisão do titular.

**Tratamento de erro (bom):** `str(e)` cru fica só no log interno; para Langfuse e
`fallback_motivo` sai apenas `type(e).__name__` + status HTTP (`:526-541`). `_ProviderPulado`
(`:245`) distingue "PII residual" de falha real — nesse caso **o conteúdo nunca foi enviado**.

**P2 — `cache_hit` não gera `AILog`** (`:361-377`): zera custo corretamente, mas deixa buraco na
auditoria de uso de IA.

## 2. PII — barreira LGPD

**O que é removido antes de provider externo** (`services/sanitizer.py:15-43`): CPF, CNPJ, número
CNJ, RG, e-mail, telefone, CEP, cartão, chave PIX, **OAB** (`:35`), **endereço/logradouro**
(`:39-43`), data de nascimento contextual (`:47-51`).

**Dois modos, propositalmente distintos:**
- `sanitizar_pii` (`:54`) — externo: mascara tudo, inclusive CPF/CNPJ.
- `sanitizar_pii_interno` (`:94`) — usa `_PATTERNS[2:]`, **mantendo CPF/CNPJ em claro**;
  documentado para uso exclusivo com Ollama local.

**Aplicação em todos os caminhos** via `_chamar_com_barreira` (`:255`), fonte única compartilhada
por `chat()` (`:442`) e `executar_tarefa_ia()` (`:1007`). O caminho agêntico usa
`_pseudonimizar_agentico` (`:1187`), que desce **recursivamente** por `input` de tool aninhado.
Segunda barreira: `validar_sem_pii` roda sobre o texto **já sanitizado**; sobrando PII, o provider
é **pulado sem ser chamado**.

**Boot guard (bom):** `config.py:989-1004` — em produção, `AI_REQUIRE_SANITIZATION_FOR_EXTERNAL=
false` com provider externo elegível **falha o boot**, salvo opt-in explícito.

**Testes:** `tests/test_sanitizer.py` e `tests/test_ai_gateway_barreira.py` provam o contrato
crítico (provider externo com PII residual é pulado; provider local não passa pela sanitização).

**Ressalvas:**
- **P2 — nome próprio só é sanitizado se o chamador passar `nomes_proteger`/`entidades`**
  (`sanitizer.py:77-89`). Sem isso, nomes de partes vão íntegros ao provedor externo. É a maior
  superfície residual de PII.
- **P2 — `validar_sem_pii` não checa 2 dos 11 padrões**: `sanitizer.py:134-144` monta `checks` com
  os índices 0-6, 9, 10 — omite `[7]` CARTAO e `[8]` CHAVE_PIX.

**Criptografia em repouso — `services/pii_crypto.py` (114 linhas):** `encrypt/decrypt` com
**Fernet** (não determinístico); `hash_documento` com **HMAC-SHA256** determinístico como índice
cego (permite UNIQUE/dedup/conflito de interesses sem guardar o valor). Chaves em
`PII_ENCRYPTION_KEY` e `PII_HASH_KEY`; ausência levanta `RuntimeError` (`:43-49`, `:80-84`).
`decrypt` levanta em vez de mascarar (`:60-72`) — correto. Limitação assumida e documentada
(`:17-19`): **busca parcial de CPF é impossível**.

## 3. HITL e citation gate

**HITL não é desligável no essencial.** `services/ai/core/hitl_policy.py:21-27`: `AI_REQUIRE_HITL`
(default `True`) controla apenas `requer_revisao`; **`is_rascunho` é `True` incondicionalmente**,
com comentário registrando que a flag existe só para testes. `executar_tarefa_ia` devolve
`is_rascunho / requer_revisao = True` fixos (`ai_gateway.py:958,1097`).

**Citation gate — obrigatório por default e fail-secure.** `CITACOES_POLITICA` (`config.py:233`)
= `bloquear` (default) | `marcar` | `desligado`. `politica_citacoes()`
(`citation_gate.py:78-93`) **força `bloquear` diante de valor inválido**, com warning — erro de
configuração não rebaixa o gate. Bloqueiam (`avaliar_bloqueantes:135-195`): citação `suspeita`;
citação `generica`; julgado `identificada` sem tribunal **e** sem data. Falha da verificação sob
política `bloquear` ⇒ **503 fail-closed** (`:333-339`).

**Override auditado (bom):** exige justificativa de 10-500 chars, colapsa whitespace
(anti-log-injection), rejeita o marcador reservado, e grava trilha **dupla** — `AILog.fontes_rag`
+ `audit_logs` (`:357-377`).

**~45 testes** cobrem o bloqueio: `tests/test_citation_gate.py` e
`tests/test_citation_gate_hardening.py` (409 na `ia_defensiva`, 503 sob `bloquear`, injeção de
marcador, modo estrito on/off, política inválida caindo no modo seguro).

> ### 🟠 P1 — o gate não roda na geração de peça
>
> Confirmado por mim: `routers/peca_geracao.py` e `routers/peca_geracao_router.py` têm **zero**
> referência a `citation_gate`. `aplicar_gate_hitl` só é chamado em `routers/ai.py:216`,
> `routers/ia_defensiva.py:163` e `routers/legal_docs.py:794`.
>
> Isso é **por desenho** — a peça nasce rascunho e o gate morde na aprovação. Mas significa que
> **quem consumir a peça fora do fluxo HITL não passa pelo gate.** É a costura a fechar antes do
> primeiro protocolo real. Decisão do titular: o gate deve rodar também na geração?

## 4. RAG

**Ingestão** (`services/ingestion_service.py`): fetch com anti-SSRF (`_validar_sem_ssrf:64`) →
normalização (`:148`) → chunking → UPSERT idempotente por `chave_origem` + `hash_conteudo` SHA-1.
Reingestão com conteúdo diferente **versiona** (`vigente=False`, chunks antigos preservados,
migration 068).

**Chunking:** 1 200 chars com 150 de overlap (`:53-54`), corte em fronteira de frase (`:158`).
`chunk_texto_com_paginas` (`:191`) preserva número de página → `knowledge_chunks.pagina`
(migration 120). OCR **não** está no pipeline RAG — vive em `entrada_universal_service.py` /
`documento_service.py`.

**Embeddings** (`services/embedding_service.py`): `intfloat/multilingual-e5-large`, **1024d**, via
**fastembed ONNX (sem torch)**. Protocolo E5 (`query: `/`passage: `) aplicado só se `"e5"` no nome
(`:102`). Três guardas boas: `validar_modelo_local` (`:46`) confere dimensão declarada × real
**antes** de baixar pesos; `_validar_dimensao` (`:113`) descarta lote com dimensão errada;
**contagem tudo-ou-nada** (`:201-206`) descarta o lote se o provider devolver menos vetores que
textos — corrige o defeito histórico dos "26k chunks órfãos com documento marcado como indexado".

**Índices (`knowledge_chunks`):** HNSW `vector_cosine_ops` (migration 096); GIN FTS
`to_tsvector('portuguese')`; GIN `gin_trgm_ops`. A colisão de nome entre as migrations 001 e 009
é resolvida pela 011 (`ALTER INDEX … RENAME` + criação do trgm real) — **cadeia verificada,
consistente**. `SET LOCAL hnsw.ef_search = 100` na transação de busca (`ai_service.py:390`).

**Busca híbrida** (`ai_service.buscar_contexto_rag:300` + `_fundir_lexical:171`): perna densa
pgvector (`<=>`, corte `RAG_MIN_SIM=0.55`) + trigram (`similarity() > 0.05`) + **FTS português**
(`RAG_FTS_ENABLED=False` por default), fundidas por **RRF k=60**. Cada perna falha isolada sem
derrubar as outras. HyDE opt-in (default off). **Rerank** cross-encoder local
`BAAI/bge-reranker-base` (default off), com degradação graciosa.

> ### 🟠 P1 — sem embeddings o RAG vira `ILIKE`, e ninguém é avisado
>
> `buscar_contexto_rag:415-450` cai para `ILIKE` puro quando `EMBEDDINGS_ENABLED=false` ou o
> provider falha. Há um warning único por processo (`:346-353`) — **audível, mas não monitorado**:
> nenhum heartbeat afere se a busca semântica está de fato ativa.
> Casa exatamente com a armadilha conhecida "**monitoramento afere execução, não resultado**".

## 5. Isolamento do RAG — hipótese REFUTADA

> **O escopo da auditoria classificava vazamento entre clientes como P0 provável. Não é.**
> O filtro existe, é aplicado às **quatro** consultas e tem teste row-level.

Filtro (`services/ai_service.py:69-73`), verificado por mim — **5 ocorrências** no arquivo
(1 definição + 4 consultas):

```sql
_RESTRICTED_CATS = ["peca_interna","peca_escritorio","precedente_interno","comunicacao_processual"]
_FILTRO_ESCOPO_RAG = "AND (kd.categoria <> ALL(:restr_cats) OR kd.client_id = :scope_cli)"
```

`WHERE` completo de toda consulta de retrieval (idêntico em `:374-380`, `:200-205`, `:244-250`,
`:443-448`): `deleted_at IS NULL` + predicado da perna + filtro de escopo + `vigente` +
bloqueio de `confidence_level='bloqueado'`/`rag_status` reprovado + `rag_status='aprovado'`
(default) + quarentena de súmula não conferida + exclusão de conteúdo fictício.

**Um usuário pode recuperar chunk de outro cliente?** Não, para conteúdo restrito. `scope_cli` vem
de `_escopo_cliente_do_caso` (`:155-168`), que faz `SELECT client_id FROM cases WHERE id = :cid` —
**sempre o cliente do caso em contexto, nunca parâmetro do usuário**. Sem caso, `scope_cli = ""` e
o `OR` nunca casa ⇒ nenhum restrito entra (**fail-closed**). Legislação, súmulas e jurisprudência
são globais **por desenho** — não é vazamento.

**Testes:** `tests/test_rag_isolation.py` (assinatura, categorias, fragmento SQL, captura de
SQL+params) e `tests/test_rag_isolation_dblevel.py` (**row-level contra Postgres real**: dois docs
`precedente_interno` com o mesmo termo e `client_id` distintos, separados só pelo filtro — roda
com `RUN_DB_TESTS=1`), além de `test_rag_scope_cliente_dblevel.py` e `test_e2e_smoke_isolamento.py`.

**Ressalvas reais:**
- **Não há filtro por usuário ou escritório.** O isolamento é **por cliente**. Qualquer usuário
  staff com acesso ao caso recupera o conteúdo restrito daquele cliente. Coerente com um escritório
  pequeno, mas é decisão que precisa ser consciente (P2 — decisão do titular).
- **P2 — 6 call sites não propagam `scope_client_id`:** `documento_service.py:572,722`,
  `matriz_teses_service.py:252`, `knowledge_governance.py:724,756`, `peca_service.py:628`.
  Fail-closed ⇒ **não vaza**, mas esses caminhos nunca enxergam precedente interno do próprio
  cliente — **perda silenciosa de recall**, justamente em `matriz_teses`, que mais precisaria.
- **P3 — duas taxonomias coexistem:** `base_rag` (`publica|escritorio|caso`, migration 119) e
  `categoria`+`client_id`. **O filtro usa a segunda**; a primeira não governa retrieval.
- **P2 (banco) — `knowledge_chunks` não tem coluna de escopo própria** (`models/rag.py:80-96`): só
  `doc_id`. O isolamento depende do JOIN com `knowledge_docs` estar presente em **toda** query,
  inclusive a vetorial. Hoje está; é invariante a proteger com teste.

## 6. Providers e modelos

| Provider | Var | Valor | Veredito |
|---|---|---|---|
| anthropic | `ANTHROPIC_MODEL_COMPLEXO` | `claude-opus-4-8` | válido |
| anthropic | `ANTHROPIC_MODEL_RAPIDO` | `claude-haiku-4-5-20251001` | válido |
| groq | `GROQ_MODEL` | `openai/gpt-oss-120b` | plausível |
| groq | `GROQ_TRANSCRIPTION_MODEL` | `whisper-large-v3` | válido |
| maritaca | `MARITACA_MODEL` | `sabia-4` / `sabiazinho-4` | válidos; **não-soberanos** (variantes `-br-sp` exigidas se `MARITACA_EXIGIR_SOBERANIA=true`) |
| ollama | `OLLAMA_MODEL_ANALISE`/`CONTRATO` | `deepseek-r1:8b` | tag existente |
| ollama | `OLLAMA_MODEL_PETICAO` | `qwen2.5:14b` | tag existente |
| ollama | **`OLLAMA_MODEL_RESUMO`/`CHAT`** | **`gemma3:9b`** | ⚠️ **suspeito** |
| embeddings | `EMBEDDINGS_MODEL` | `multilingual-e5-large` (1024d) | casa com `vector(1024)` |

**P2 — `gemma3:9b` provavelmente não existe.** Gemma 3 é publicada em 1b/4b/12b/27b; 9b é tamanho
do **Gemma 2**. Consta em `config.py:660-661` **e** em `.env.example:280-281`. Se o tag estiver
errado, `resumo` e `chat_rapido` falham no Ollama e caem silenciosamente para Maritaca/Groq
(externo) — **degradação de soberania sem alarme**. Confirmável com `ollama pull gemma3:9b` no
VPS. **[NÃO CONFIRMADO nesta sessão — sem acesso ao registry Ollama]**

**P3 —** `_modelos_cache` do Ollama (`ollama_provider.py:15`) é global e **nunca invalidado**: um
`ollama pull` após o boot só é visto no restart.
**P3 —** `ai_cost.py` não conhece modelos novos ⇒ custo 0 ⇒ dashboards e `AI_BUDGET_ALERTA_BRL`
subestimam.

## 7. Knowledge graph jurídico — NÃO LOCALIZADO

Busca por `nodes|edges|vertices|arestas|networkx|neo4j|rdflib|grafo_` em todo `backend/app/`:
**um único hit**, falso positivo (`notification_service.py:87` — "Edge/WNS", o navegador).
Nenhuma dependência de grafo em `requirements.txt`.

O que existe é **relacional, não grafo**:
- `models/tese.py` — repositório plano com métricas (`vezes_usada`, `taxa_sucesso`), `tags` em CSV.
  **Sem relação tese↔tese.**
- `models/matriz_teses.py` — cadeia por caso: `LegalIssue` → `ThesisCandidate` (FK `issue_id`) →
  `AuthorityRecord`. Campos `precedentes`, `fatos_relacionados`, `vulnerabilidades` são **JSONB de
  listas**, não arestas consultáveis.
- `models/jurisprudencia_interna.py`.

**Não há proveniência de aresta, traversal, nem consumidor de grafo.** Se o knowledge graph
jurídico é objetivo de produto, ele **ainda não existe** — o que existe é uma base vetorial com
metadados. Registrar como decisão de produto, não como defeito.

## 8. Achados priorizados

| # | Achado | Evidência | Classificação | P |
|---|---|---|---|---|
| 1 | `AI_ENABLED` não é aplicado no gateway; ≥5 routers sem gate | `ai_gateway.py:291,903`; 5 routers com grep 0 | INSEGURA (operacional) | **P1** |
| 2 | Sem embeddings o RAG vira `ILIKE`, sem monitorar resultado | `ai_service.py:343-353,415-450` | PARCIAL | **P1** |
| 3 | Citation gate não roda na geração de peça | `routers/peca_geracao*.py` sem `citation_gate` | FUNCIONAL C/ RESSALVAS | **P1** |
| 4 | Zero retries — 429/529 vira fallback lateral | `ai_gateway.py:434-541` | FUNCIONAL C/ RESSALVAS | P2 |
| 5 | 6 call sites sem `scope_client_id` (perda de recall) | `documento_service.py:572,722`; `matriz_teses_service.py:252` | PARCIAL | P2 |
| 6 | `gemma3:9b` provavelmente inexistente | `config.py:660-661`; `.env.example:280` | PENDENTE DE CONFIG. | P2 |
| 7 | `validar_sem_pii` omite CARTAO e CHAVE_PIX | `sanitizer.py:134-144` | FUNCIONAL C/ RESSALVAS | P2 |
| 8 | Nome próprio só sanitizado com `entidades` explícito | `sanitizer.py:77-89` | FUNCIONAL C/ RESSALVAS | P2 |
| 9 | `cache_hit` não gera `AILog` | `ai_gateway.py:361-377` | FUNCIONAL C/ RESSALVAS | P2 |
| 10 | Isolamento por cliente, não por advogado | `ai_service.py:155-168` | decisão de produto | P2 |
| 11 | Knowledge graph jurídico | grep: 1 falso positivo | **NÃO LOCALIZADA** | P3 |
| 12 | `_modelos_cache` Ollama nunca invalidado | `ollama_provider.py:15-31` | FUNCIONAL C/ RESSALVAS | P3 |
| 13 | `ai_cost.py` sem modelos novos ⇒ custo 0 | `ai_cost.py:16-32` | FUNCIONAL C/ RESSALVAS | P3 |
| 14 | Duas taxonomias (`base_rag` vs `categoria`) | `models/rag.py:37,46` | FUNCIONAL C/ RESSALVAS | P3 |

## 9. Hipóteses do escopo que foram REFUTADAS

1. **Isolamento do RAG misturando clientes** — filtro presente nas 4 consultas, fail-closed, com
   teste row-level contra Postgres.
2. **Agente/router chamando provider direto** — zero bypass; todos os candidatos lidos e
   descartados.
3. **Índices RAG faltando** — a colisão 001/009 é resolvida pela 011; cadeia verificada.

## 10. Limitações desta fase

Sem banco: não validei execução de query, planos, presença física dos índices, nem a dimensão real
da coluna. **Hipótese não verificável aqui e materialmente relevante:** com
`RAG_EXIGIR_APROVADO=true` (default) e acervo não curado, o RAG pode retornar **vazio** em
produção. Verificar com `SELECT rag_status, count(*) FROM knowledge_docs GROUP BY 1`.

## 11. Decisões que exigem o titular

1. `AI_ENABLED` deve virar kill-switch real dentro do gateway? (muda comportamento de endpoints hoje funcionais)
2. O citation gate deve rodar também na **geração** de peça, ou permanece só na aprovação?
3. Isolamento por **cliente** basta, ou é preciso escopo por advogado/carteira?
4. `gemma3:9b` — corrigir para `gemma3:12b`/`gemma2:9b`, ou o VPS já tem esse tag?
5. Knowledge graph jurídico é objetivo de produto? Hoje **não existe**.
