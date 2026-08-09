# Reauditoria profunda do módulo de IA — EJC (2026-08-09)

> Reanálise minuciosa, feita **com acesso ao código-fonte** (diferente da auditoria externa de
> julho/2026), cobrindo: gateway e governança da IA, núcleo único de agentes, base de
> conhecimento e RAG, jurimetria (recorte MG/JEC), testes, radares de Compliance/Regulatório,
> integrações externas e provedores (Ollama, Anthropic, Maritaca, Groq). Inclui um **caso
> fictício de alta complexidade** com gabarito e rubrica, para servir de benchmark de qualidade
> jurídica da IA (Anexo A).
>
> Toda afirmação traz evidência `arquivo:linha`. Itens que exigem log de produção para
> confirmação final estão marcados **[PRODUÇÃO]**.

## Sumário executivo

O módulo de IA do EJC é, na arquitetura, **muito acima da média**: gateway único real (nenhum
SDK de LLM fora de `services/providers/`), barreira LGPD com pseudonimização reversível e
fail-closed, gate anti-alucinação de citações fail-secure, HITL em três camadas, piso de
sigilo por área não rebaixável, e ~1.000 testes estruturais na área de IA. Os 22 prompts de
ramo têm profundidade profissional genuína (dispositivo por dispositivo, súmulas nominadas).

Os problemas encontrados são de **três naturezas**:

1. **Erosão do "núcleo único"** — três caminhos de IA convivem (orchestrator, `gw_chat`
   direto, loop agêntico); só o primeiro aplica classificação, validador de resposta e
   política HITL completos. O fluxo de **audiência é o caso extremo**: tarefa registrada mas
   inalcançável, prompt de 14 linhas fora do núcleo, sem RAG nem validação de citações.
2. **Qualidade jurídica não medida** — existe maquinaria completa de avaliação
   (gold sets, LLM-judge, comparador de providers) e **zero golden answers reais**; o único
   benchmark quantitativo é de retrieval (Hit@5/MRR) com piso frouxo. Nenhum teste afirma que
   a IA respondeu **juridicamente certo**. O Anexo A ataca exatamente essa lacuna.
3. **Configuração de produção contradiz o desenho** — `OLLAMA_ENABLED=false` no compose de
   produção torna as áreas sensíveis (criminal, família, saúde) **sem IA nenhuma** (fail-closed
   correto, mas indisponibilidade não documentada), e o roteamento inteligente pode mandar
   tarefa leve para Groq (EUA) **antes** do provedor local, contrariando a minimização
   declarada.

As seções 5 (RAG/base de conhecimento e jurimetria MG/JEC) e 6 (radares e integrações)
consolidam as frentes específicas, incluindo a causa-raiz dos ingestores dos radares.

---

## 1. Gateway de IA e política de provedores

### 1.1 Arquitetura confirmada

- **Choke point real**: nenhum SDK de LLM (anthropic, groq, httpx p/ ollama/maritaca) é
  instanciado fora de `backend/app/services/providers/` — verificado por varredura. Só existem
  **4 provedores**: `ollama_provider.py`, `anthropic_provider.py`, `groq_provider.py`,
  `maritaca_provider.py`.
- Superfície pública do gateway (`services/ai_gateway.py`, 1.307 linhas): `chat()` (`:291`,
  caminho principal, ~76 arquivos consumidores), `executar_tarefa_ia()` (`:903`, por
  `TarefaIA`), `chat_agentico()` (`:1207`, um turno de tool-use), `transcrever_audio()`
  (`:556`, Groq Whisper), além de `health()`/`provedores_configurados()`/`ia_disponivel()`.
- **Fallback**: `TASK_ROUTING` (`ai_gateway.py:121-181`) declara a cadeia por tarefa
  (complexas: `ollama → anthropic → maritaca → groq`; leves omitem anthropic), reordenada por
  `AI_PROVIDER_PRIORITY` (default `ollama,anthropic,maritaca,groq`, `core/config.py:258`).
  Elegibilidade em `_provider_elegivel` (`:667-683`). Não há retry intra-provedor; resiliência
  é o fallback de cadeia (`:434-541`), com `fallback_motivo` PII-safe (classe do erro + HTTP
  status apenas, `:531-535`).
- **Modelos default por provedor**: Anthropic `claude-haiku-4-5` (rápido) /
  `claude-opus-4-8` (complexo) com thinking adaptativo e effort para modelos modernos
  (`anthropic_provider.py:220-238`); Groq `openai/gpt-oss-120b` (migrado do llama-3.3
  descontinuado, `config.py:107-112`); Maritaca `sabia-4`/`sabiazinho-4` (soberania `-br-sp`
  opt-in, validada no boot, `config.py:1047-1063`); Ollama por tarefa (deepseek-r1:8b,
  qwen2.5:14b, gemma3:9b — `config.py:662-666`).

### 1.2 Barreira LGPD (sanitização antes de provedor externo)

Ponto único `_chamar_com_barreira` (`ai_gateway.py:255-288`): para provedor externo com
`AI_REQUIRE_SANITIZATION_FOR_EXTERNAL=true` (default), aplica pseudonimização reversível
(marcadores `[CLIENTE_1]`, `[CPF_1]`… — mapa **só em memória**, reidratação local) ou
mascaramento irreversível; **PII residual → `_ProviderPulado` e o provedor externo nunca é
chamado**. Modo `LOCAL_COMPLETO` (áreas sensíveis: criminal, família, saúde, menores,
violência — `sanitization_policy.py:70-78`) remove todos os externos da cadeia; sem local
elegível, bloqueia com `RuntimeError` seguro (`:422`). O que é mascarado: CPF, CNPJ, nº CNJ,
RG, e-mail, telefone, CEP, cartão, chave PIX, OAB, endereço, data de nascimento contextual e
nomes das partes do caso. Guarda de boot: em produção, externo elegível + sanitização
desligada **derruba o deploy** (`config.py:1022-1044`).

### 1.3 Kill-switches e telemetria

- `AI_EXTERNAL_PROVIDERS_ALLOWED=false` desliga Anthropic+Groq+Maritaca de uma vez (aplicado
  em 3 camadas: gateway, provider_registry, provider_policy). Sem endpoint de runtime —
  desligar exige `.env` + restart (`get_settings` é `@lru_cache`).
- Três trilhas: **AILog** (banco, trilha legal — erro de gravação **propaga**),
  **AIProviderMetric** (só metadados, nunca prompt/resposta; painel
  `GET /ia-governanca/provedores`, `routers/ia_provider_metrics.py:51`) e **Langfuse**
  self-hosted opt-in (conteúdo só com host comprovadamente interno, fail-closed em DNS).
- Custo com fonte única `ai_cost.py` (tabela por provedor + busca web; `USD_BRL_RATE`).

### 1.4 Inventário de opções (flags de IA)

44 flags mapeadas em `core/config.py` — as decisivas:

| Grupo | Flags (default) |
|---|---|
| Liga/desliga | `AI_ENABLED` (true), `AI_EXTERNAL_PROVIDERS_ALLOWED` (true), `ANTHROPIC_ENABLED` (true), `MARITACA_ENABLED` (**false**), `OLLAMA_ENABLED` (true no código; **false no compose de produção**), `AI_AGENT_ENABLED` (**false**) |
| LGPD | `AI_REQUIRE_SANITIZATION_FOR_EXTERNAL` (true), `AI_ACCEPT_EXTERNAL_WITHOUT_SANITIZATION` (false), `AI_SANITIZATION_MODE_MAP` (""), `PII_ENCRYPTION_KEY`/`PII_HASH_KEY` (obrigatórias em prod) |
| HITL/qualidade | `AI_REQUIRE_HITL` (true), `CITACOES_POLITICA` (**bloquear**), `CITACOES_MODO_ESTRITO` (false), `DUAS_IAS_ENABLED` (true p/ `elaboracao_peca,auditoria_peca`), `FICHA_TRIAGEM_OBRIGATORIA` (true), `AI_LIVE_GROUNDING_ENABLED` (true), `AI_GROUNDING_DATAJUD_ENABLED` (false) |
| Roteamento | `AI_PROVIDER` (auto), `AI_PROVIDER_PRIORITY` (ollama,anthropic,maritaca,groq), `ROTEAMENTO_INTELIGENTE_ENABLED` (true), `ROTEAMENTO_PROVIDER_LEVE` (**groq**) / `MEDIO`/`PESADO` (anthropic), limiares 3/6 |
| RAG | `EMBEDDINGS_ENABLED` (true, provider local e5-large 1024d), `RAG_EXIGIR_APROVADO` (true), `RAG_SUMULAS_QUARENTENA` (true), `RAG_RERANK_ENABLED` (false), `RAG_MIN_SIM` (0.55), `RAG_HYDE_ENABLED` (false), `RAG_FTS_ENABLED` (false), `RAG_AUTO_REEMBED_ENABLED` (true) |
| Recursos | `AI_PROMPT_CACHING_ENABLED` (true), `AI_WEB_SEARCH_ENABLED` (false), `AI_RESPONSE_CACHE_ENABLED` (false), `AUDIO_TRANSCRIPTION_ENABLED` (false + 4 portões cumulativos), `AI_BUDGET_ALERTA_BRL` (0=off, **só alerta, não bloqueia**), tetos do agente (8 passos / 120k tokens / R$ 2,00) |

### 1.5 Achados do gateway (22, os principais)

| # | Achado | Gravidade | Evidência |
|---|---|---|---|
| A-1 | `AI_ENABLED` **não é consultado** por `chat()`/`executar_tarefa_ia()`/`chat_agentico()` — só por `ia_disponivel()` e checagens avulsas; não é kill-switch do gateway | Média | `ai_gateway.py:291-553` vs `:662` |
| A-3 | Roteamento inteligente promove **Groq (EUA) à frente do Ollama local** para tarefas leves (`ROTEAMENTO_PROVIDER_LEVE=groq`), contrariando a minimização declarada | Média-alta | `ai_gateway.py:745-750`; `config.py:287` |
| A-5 | Prompt com CPF em claro toma **422 no núcleo** (policy detecta e, sem Ollama, bloqueia) embora a barreira do gateway o pseudonimizasse — funcionalidade recusada sem necessidade | Média | `orchestrator.py:156-163`; `provider_policy.py:111-113` |
| A-7 | **Áreas sensíveis sem IA em produção**: `LOCAL_COMPLETO` + `OLLAMA_ENABLED:"false"` no compose ⇒ criminal/família/saúde sempre `RuntimeError` (fail-closed correto, indisponibilidade não documentada) | Alta operacional | `sanitization_policy.py:70-78`; `docker-compose.yml:89,154`; `ai_gateway.py:422` |
| A-10 | **Elo fraco do HITL de peça**: `POST /legal-docs/{id}/revisar` seta `human_reviewed=True` exigindo só acesso ao caso — sem papel de advogado, sem gate de citações, em paralelo ao caminho rigoroso `conferir-e-assinar` | Média-alta | `legal_docs.py:595-628` vs `:793-835` |
| A-11 | `AI_REQUIRE_HITL` tem alcance quase nulo: governa só o booleano `requer_revisao`; os bloqueios reais vêm de `LegalDoc.human_reviewed` + citation gate (o nome promete mais do que entrega) | Baixa-média | `hitl_policy.py:15-26` |
| A-2 | `_provider_elegivel` triplicado (gateway, registry, policy) — já divergiu no passado | Média | `ai_gateway.py:667`; `provider_registry.py:10`; `provider_policy.py:46` |
| A-4 | Cadeia vazia cai em `[("groq", …)]` sem checar chave/kill-switch — mitigado por monkey-patch de hardening no startup, código-base segue fail-open | Baixa-média | `ai_gateway.py:762-765`; `ai_core_hardening_patch.py:37-68` |
| A-9 | Áudio sai íntegro (sem sanitização possível) para Groq — 5 portões cumulativos, todos OFF; risco residual = um `true` acidental | Média | `ai_gateway.py:556-628` |
| A-12/13 | `chat_agentico` fora da telemetria de provedores, do `ai_cost` e do Langfuse (barreira LGPD ok, custo/latência invisíveis) | Baixa | `provider_metrics_runtime.py:88-197`; `ai_gateway.py:1284` |
| A-14 | `chat()` não grava AILog — trilha legal depende do chamador (76 consumidores) | Média (desenho) | `ai_gateway.py:291-553` |
| A-19 | Agente exige Anthropic (ponto único de falha) apesar de `maritaca.chat_tools` pronto e nunca chamado | Média | `ai_gateway.py:1264-1269`; `maritaca_provider.py:101-153` |
| A-15/16 | Flags lidas por `os.getenv` fora do Settings (`ai_tools.py:45`, `ia_saude.py:94-121`, `ai_cost.py:59`); painel `/ia-saude/estado-operacional` **omite Maritaca** | Baixa | citados |
| A-20 | `AI_PROVIDER` forçado inelegível degrada em silêncio para outro provedor (quem exigiu soberania recebe Anthropic/Groq sem aviso na API) | Baixa | `ai_gateway.py:734-738` |
| A-22 | `POST /ia-governanca/fontes/tjmg/coletar` dispara crawler ignorando `TJMG_INGEST_ENABLED` (intencional) e sem rate-limit | Baixa | `ia_governanca.py:501-527` |

### 1.6 Documentação de política ~1 mês atrás do código

Todos os `docs/ai/EJC_AI_*.md` (datados 2026-07-04) citam linhas e constantes que não existem
mais. Divergências materiais: `sanitizar_ou_abortar` **não aborta mais** (sanitiza e segue,
`ai_guard.py:19-48`) ao contrário do que a política LGPD afirma; Maritaca ausente da política
de provedores; preços/constantes de custo migrados para `ai_cost.py` com valores diferentes;
barreira externa documentada como mascaramento irreversível quando o default hoje é
pseudonimização reversível; roteamento inteligente, Duas IAs, cache, web search, agente e
Langfuse **sem doc de política**. Único doc atualizado: `DECISAO_CITACOES_MODO_ESTRITO.md`.

---

## 2. Governança da IA (HITL, citation gate, auditoria)

### 2.1 O que segura de verdade

- **Citation gate** (`services/citation_gate.py`, 378 linhas): política default `bloquear`
  com fail-secure (valor inválido cai em `bloquear`, `:86-92`); bloqueia CNJ com DV errado,
  súmula fora de faixa, tribunal inexistente, menção genérica e julgado sem tribunal+data;
  modo estrito opcional bloqueia súmula/artigo ausente da base curada; teto de 200 citações
  por verificação com sinalização de relatório parcial; falha de verificação → **503**
  fail-closed em política `bloquear`. As **3 únicas** transições de `status_hitl` para
  `revisado|aplicado` passam pelo gate (`routers/ai.py:216`, `ia_defensiva.py:163`,
  `legal_docs.py:811`), com override justificado (10–500 chars, anti log-injection) e trilha
  dupla em `AILog.fontes_rag` + `audit_logs` imutável.
- **HITL real em três camadas**: rótulo (`hitl_policy.aplicar` — `is_rascunho=True`
  **sempre**, inclusive com a flag desligada); peça (`LegalDoc.ai_generated=True` não avança
  para `aprovada|final|protocolada` sem `human_reviewed=True` + score de validação ≥75 +
  auditoria de jurisprudência; edição de conteúdo **zera** `human_reviewed`); agente
  (write-tools pausam com token servidor-side no Redis; **sem Redis = fail-closed**, aprovação
  one-shot, retomada por outro usuário recusada).
- **Governança visível**: `GET /ia-governanca/dashboard|fontes|guardrails|rag-curadoria`,
  telemetria `GET /ia-governanca/provedores` (a fonte de verdade sobre provedores, conforme a
  auditoria externa), curadoria de jurisprudência MG com allowlist de domínios oficiais e
  anti-SSRF (`ia_governanca.py:548-671`).

### 2.2 Onde a governança cede

1. **A-10 acima** — o caminho barato `POST /legal-docs/{id}/revisar` desbloqueia o gate de
   peça sem exigir papel jurídico nem citation gate.
2. **Nenhum invariante garante que todo endpoint gerador de IA passe por
   `hitl_policy` + `response_validator`** — cada endpoint é testado individualmente; um
   endpoint novo que esqueça o gate não quebra nada no CI (proposta de teste na §4).
3. Fluxos fora do núcleo (audiência, IA Defensiva, skills contextuais, `ia_especializada`)
   chamam `gw_chat` direto — a barreira LGPD segura (fica no gateway), mas classificação,
   validador de citações no caminho e pipeline reportado não se aplicam.

---

## 3. Núcleo único de IA — agentes, prompts, roteamento, peças

### 3.1 Mapa (todas as opções do núcleo)

- **38 agentes** (`ai/core/agent_registry.py:42-387`): 9 transversais (coordenador, caso,
  processo, documento, extração, redação, RAG, jurimetria, comunicação), **24 de ramo** (todos
  `exige_fonte=True`), 4 técnicos (3 restritos a superadmin/admin/socio).
- **21 tarefas** (`TarefaIA`) com configuração por tarefa (provider, modelo
  rápido/complexo, max_tokens 900–6000, temperatura 0.0–0.2 — PRAZOS em 0.0).
- **31 prompt keys** + extras; **76 skills** (28 de pipeline + 14 de ramo + 34 de módulo).
- **Classificador determinístico** (sem LLM): ~150 aliases + 33 keywords ordenadas; default
  `CaseAgent` — nunca falha.
- **Peças**: 33 tipos em 4 grupos, 17 áreas, 5 níveis de complexidade, 4 modos de produção
  (`livre|guiado|molde|agente`), flags de teses condicionais com regra anti-Frankenstein,
  ficha de triagem obrigatória (409 sem ela), pipeline de 7 etapas + auto-crítica adversarial
  (Duas IAs) + verificação de citações + `AILog` + `LegalDoc` rascunho. Ancoragem probatória
  real `(doc. NN)` vinda do GED; sem prova cadastrada, a IA é forçada a `[prova a juntar]` —
  não inventa documento.
- **Blindagens confirmadas**: anti-prompt-injection (contexto de terceiros nunca no system
  prompt — viaja como dado delimitado `[CONTEXTO]`), piso de sigilo derivado de `Case.area`
  (fonte que o cliente não controla), detector de resíduos de molde (vazamento entre clientes)
  com audit log sem conteúdo.

### 3.2 Prompts: profundidade real, com assimetria

Os 22 prompts de ramo em arquivo são de **qualidade profissional** — ex.: trabalhista cita
CLT arts. 2º-3º, 58, 71, 223-A/G, 477-487, 791-A, 818, Súmulas TST 6/268/331/437, Lei
13.467/17; criminal tem bloco próprio de sigilo LGPD; ambiental traz tabela de prazos IBAMA e
template de defesa. Em contraste, os prompts **inline** (`bancario`, `processo`,
`jurimetria_pred`) têm ~3 linhas — e dois deles servem agentes `exige_fonte=True`
(BankForensics, Jurimetry). `system_prompts/base.py` impõe a barreira ética (16 restrições
OAB/LGPD; nunca inventar acórdão — na dúvida, `"verificar: [tema] no [tribunal]"`) e o
`AVISO_RASCUNHO` (Provimento OAB 205/2021).

### 3.3 Lacunas do núcleo (as que importam)

| # | Lacuna | Evidência |
|---|---|---|
| N-1 | **`TarefaIA.AUDIENCIA` é código morto**: nenhum agente a usa, ausente do classificador, prompt = análise de caso. O fluxo real (`POST /ai/preparar-audiencia`) roda **fora do núcleo**, sem RAG, sem validação de citações, prompt de ~14 linhas, log `tipo_uso="outro"`. Não existe resumidor de atas | `system_prompts/__init__.py:84`; `routers/ai.py:451`; `ai_service.py:853-976` |
| N-2 | **Três caminhos de IA** convivem com o "núcleo único" (orchestrator; `gw_chat` direto em `ia_defensiva_service.py:307`, `ai_service.py:906-964`, `ia_especializada.py:92`, `ai_skill_service.py`, `peca_service.py`; loop agêntico). A regra declarada em `orchestrator.py:4-5` não corresponde ao código | citados |
| N-3 | **11 dos 24 agentes de ramo sem skill nativa** (7 também com tarefa genérica `ANALISE_CASO`): saúde, médico, agrário, agronegócio, eleitoral, internacional, contratual (+ sucessões, constitucional, juizados sem skill) — perdem bloco de método e calibração da área | `agent_registry.py:225-334` |
| N-4 | `_AGENTES_COM_CASO` omite 10 agentes de ramo → `precisa_caso=False` indevido | `intent_classifier.py:217-224` |
| N-5 | `SecurityLGPDOABAgent` **sem** `roles_permitidos` (pares técnicos exigem) — qualquer staff audita acessos | `agent_registry.py:379-386` |
| N-6 | Peça de trânsito sem especialização (`_AREA_PROMPT_KEY["transito"]=None` apesar de `PROMPT_TRANSITO` existir e estar registrado) | `peca_service.py:391,409-412`; `__init__.py:75` |
| N-7 | **Frontend não consome `/ai/core/*`** — núcleo alcançado só por wrappers; endpoints de introspecção sem tela | varredura `frontend/src`; `moduleRegistry.tsx:627` |
| N-8 | `licitacoes` é `CaseArea` sem agente/prompt/skill (mapeada p/ administrativo só em peças) | `models/case.py:39`; `taxonomia.py:228` |
| N-9 | Roteamento por keyword frágil por substring ("administrativo" captura "processo administrativo tributário"; "alimentos" captura contexto de consumo) — só a colisão "cláusula penal"×"penal" foi tratada | `intent_classifier.py:177-190` |
| N-10 | 14 das 28 skills de pipeline com `handler=None` — o `skill_pipeline` reportado ao usuário é parcialmente decorativo (2 ausências são deliberadas, de segurança) | `skill_registry.py:134-226` |
| N-11 | Três resoluções de área rodam em paralelo e podem divergir (classificador → agente; catálogo de skills → ramo; `Case.area` → sigilo); três taxonomias de área coexistem (27/17/14) | `intent_classifier.py`; `ejc_skill_catalog.py:267-315`; `taxonomia.py:232-242` |
| N-12 | Fluxos de contestação **triplicados**: IA Defensiva (fora do núcleo), Defesas e Revisões (no núcleo), Motor de Peça (orquestra os dois) | `ia_defensiva_service.py:16-25`; `defesas_revisoes.py:301`; `motor_peca_service.py:1-17` |

### 3.4 Superfícies de acionamento no frontend

Canônica: `/inteligencia` (`InteligenciaWorkspace.tsx`) com abas — Agente IA (SSE com HITL
retomável), Pergunta rápida, Analisar/revisar (+ PATCH HITL), Ferramentas/skills, Jurimetria,
Conhecimento, Saúde. Demais: modal de geração de peça (`PecaGeneratorModal`), Ficha de
Triagem, assistente contextual do caso, Sala Jurídica (10 modos), IA Defensiva no caso,
Defesas e Revisões, Raio-X, Governança da IA, Painel de Provedores, Biblioteca de Prompts.

---

## 4. Testes do módulo de IA

### 4.1 O que está bem coberto (~1.014 funções de teste em ~94 arquivos)

- **Invariantes que travam remoção de controle** (o que o CI realmente defende):
  kill-switch em 3 testes independentes (inclusive assert de zero chamadas ao provedor);
  barreira PII em **três camadas** (runtime, boot, modelo + fail-closed de nome que escapa);
  citation gate (fail-secure de política, 409/503 no HITL, anti log-injection, modo estrito
  com matriz on/off, e `inspect.getsource` que **impede fork do gate**); HITL do loop
  agêntico (token, expiração, Redis fora = fail-closed, one-shot, usuário divergente).
- CI roda a suíte com `RUN_DB_TESTS=1` contra pgvector real, `--cov-fail-under=65`, mais job
  `eval-smoke` com `agent_trajectory --max-violacoes-hitl 0` (**o gate de CI mais explícito do
  HITL**) — `.github/workflows/ci.yml:54,135-139,164-190`.

### 4.2 Lacunas críticas de cobertura

| Prio | Lacuna | Proposta |
|---|---|---|
| **P0** | **Zero golden answers jurídicas.** `app/eval/` tem `run_eval`, gate por área, LLM-judge e comparador de providers **ociosos**; só gold sets de exemplo (3 casos, jurisprudência placeholder). O próprio `app/eval/README.md:114-120` admite: "cobertura real por área é zero". O CI roda `run_eval --smoke` sem `--areas-obrigatorias` — valida formato de JSON, não qualidade | Curar `gold_set.jsonl` com 15–20 casos/área crítica e ligar `--areas-obrigatorias --min-recall-area 0.7` no `ci.yml:187`. O Anexo A é o primeiro caso |
| **P0** | Nenhum teste percorre as rotas e prova que **todo** endpoint gerador de IA aplica `hitl_policy` + `response_validator` — endpoint novo que esqueça o gate passa verde | Invariante estilo `test_agentes_invariantes.py` sobre `app.routes`/registro de handlers |
| P1 | `hitl_policy.py` com só 2 testes diretos (módulo mais fino do núcleo) | bordas de `aplicar` |
| P1 | **Smoke E2E de IA é cosmético**: 6 GETs com `expected:[200,404]` (módulo morto passa verde) e 1 POST sem assert de conteúdo | passo `ia.chat_ficticio` assertando `is_rascunho`, aviso HITL e ausência de PII |
| P2 | `indice_risco.py` e `services/jurimetria.py` sem teste funcional próprio | molde de `test_score_juridico_ia.py` |
| P2 | Nenhum teste de contrato com provedores reais (mudança de schema Anthropic/Maritaca só quebra em produção) | contrato gravado (cassettes) |
| P3 | Piso do único benchmark de retrieval frouxo: Hit@5 ≥ 0,30 com baseline 0,476 — regressão de 35% passa; e mede só o caminho textual (embeddings desligados no CI) | subir piso; medir caminho vetorial |

**Conclusão da §4**: os ~1.000 testes garantem que **os controles rodam**; nenhum garante que
**a resposta é juridicamente correta**. A régua de qualidade existe e está vazia.

---

## 5. RAG, base de conhecimento e jurimetria (MG/JEC)

*(Consolidação da frente específica — ver relatório da frente na descrição do PR; esta seção
resume o que a IA efetivamente sabe, o fluxo de retrieval e o estado real da jurimetria.)*

<!-- SEÇÃO 5: PREENCHIDA AO FIM DA FRENTE RAG -->

---

## 6. Radares de Compliance/Regulatório e integrações externas

*(Consolidação da frente específica — causa-raiz dos ingestores e inventário de integrações.)*

<!-- SEÇÃO 6: PREENCHIDA AO FIM DA FRENTE RADARES -->

---

## 7. Recomendações priorizadas

1. **[P0] Curar o gold set jurídico** e ligar o gate por área no CI — é a única forma de
   medir se prompt/modelo/reranker melhoram ou pioram a resposta. Começar pelo Anexo A.
2. **[P0] Invariante de rota**: teste que garante HITL + validador em todo endpoint gerador.
3. **[P0] Fechar o elo fraco A-10** (`/legal-docs/{id}/revisar`): exigir papel jurídico e
   citation gate, como no `conferir-e-assinar`.
4. **[P1] Decidir o par A-3/A-7** (minimização vs disponibilidade): ou religa Ollama em
   produção (devolvendo IA às áreas sensíveis e ao princípio local-primeiro), ou documenta a
   indisponibilidade e ajusta `ROTEAMENTO_PROVIDER_LEVE` para não furar a fila local.
5. **[P1] Trazer audiência para o núcleo** (N-1): prompt dedicado, agente, RAG e citações —
   ou remover a tarefa morta.
6. **[P1] Unificar elegibilidade de provedor** (A-2) numa função única importada pelos três
   consumidores.
7. **[P2] Completar os 11 agentes de ramo sem skill/tarefa própria** (N-3) e a peça de
   trânsito (N-6); revisar `_AGENTES_COM_CASO` (N-4) e `roles` do SecurityLGPDOABAgent (N-5).
8. **[P2] Atualizar `docs/ai/`** — hoje induz operação errada (custo, LGPD, roteamento).
9. **[P2] `AI_ENABLED` decidir**: ou vira kill-switch de verdade no gateway (A-1), ou é
   removida para não dar falsa sensação de controle.

---

## Anexo A — Caso fictício de alta complexidade (benchmark de qualidade jurídica)

> **Uso**: submeter o enunciado ao assistente do EJC (tarefa de análise de caso/parecer, via
> `ai_gateway` com HITL e citation gate ativos) e avaliar contra o gabarito e a rubrica.
> Nenhum dado é real. Desenhado para o recorte **MG/JEC** da jurimetria do sistema. Resultado
> esperado: **rascunho** retido para revisão de advogado — nunca resposta final automática.

### A.1 Enunciado (entrada para a IA)

Cliente: **Marta Helena Duarte**, 62 anos, aposentada, residente em Belo Horizonte/MG,
correntista do **Banco Aurora S.A.** há 18 anos.

1. **05/03/2026** — Marta recebe ligação de pessoa que se identifica como "gerência de
   segurança" do banco, informando tentativa de fraude no cartão. O interlocutor conhece
   nome completo, CPF, agência, conta e as três últimas transações reais.
2. Orientada a "regularizar o dispositivo", instala aplicativo de acesso remoto e digita a
   senha do app do banco. Em 40 minutos: **PIX de R$ 19.400,00**; **crédito pessoal
   pré-aprovado de R$ 21.000,00** contratado no app e transferido em dois PIX para contas de
   passagem em fintech; contratação de **título de capitalização de R$ 2.100,00**.
3. As operações destoam do perfil: nunca fez PIX acima de R$ 800,00; horário 23h–23h40;
   dispositivo novo, registrado minutos antes.
4. **06/03/2026** — boletim de ocorrência e reclamação no banco (protocolo).
   **20/03/2026** — banco nega ressarcimento por "culpa exclusiva da vítima", mantém a
   cobrança das parcelas do crédito (R$ 987,00/mês debitados da conta onde cai a
   aposentadoria) e, em **abril/2026**, negativa Marta no SPC/Serasa pela parcela sustada.
5. Descobre-se, por notícia e resposta da ANPD a requerimento, que o Banco Aurora sofreu
   **incidente de segurança confirmado em janeiro/2026**, com vazamento de nome, CPF, dados
   de conta e histórico transacional de correntistas de MG — o que explica o nível de detalhe
   do golpista (engenharia social qualificada pelo vazamento).
6. Marta tem **negativação anterior** por débito de telefonia de 2024, **quitado em 2025**
   mas ainda não baixado no cadastro à época da nova inscrição.
7. Pretende: devolução integral, cancelamento do "empréstimo" e do título de capitalização,
   baixa da negativação e dano moral. Prefere o **JEC de Belo Horizonte** pela rapidez e quer
   saber se pode, dado o valor.

Pergunta: **parecer completo de estratégia** — enquadramento, responsabilidade do banco e
teses de defesa esperadas, competência e cabimento no JEC/BH, pedidos e tutela de urgência,
ônus da prova, prognóstico fundamentado (jurimetria MG/JEC se disponível na base) e riscos.

### A.2 Gabarito mínimo (resposta de advogado experiente)

**1. Enquadramento e responsabilidade**
- Relação de consumo: CDC aplicável a bancos (**Súmula 297/STJ**); defeito do serviço,
  responsabilidade **objetiva** (**CDC, art. 14**).
- **Súmula 479/STJ**: fraudes e delitos de terceiros no âmbito de operações bancárias são
  **fortuito interno**. A entrega de senha mediante engenharia social alimentada por
  **vazamento imputável ao próprio banco** esvazia a tese de culpa exclusiva da vítima
  (CDC, art. 14, §3º, II): o risco foi criado/agravado pelo fornecedor.
- Falha concreta do antifraude: horário atípico, valores fora do perfil, dispositivo
  recém-cadastrado, contas de passagem — dever de monitoramento de operações discrepantes do
  perfil do correntista (linha consolidada do STJ).
- **LGPD (Lei 13.709/2018)**: arts. **42 a 45** (responsabilidade), art. 48 (comunicação do
  incidente — a resposta da ANPD é prova documental). Dano moral pela exposição cumulável com
  o material da fraude.
- Empréstimo contratado pelo fraudador: **inexistência/nulidade** em relação à correntista —
  declaração de inexigibilidade, vedação de descontos, devolução do debitado; repetição
  **em dobro** (**CDC, art. 42, parágrafo único** — cobrança mantida após reclamação formal,
  sem engano justificável).
- Título de capitalização: cancelamento e restituição integral (contratação fraudulenta;
  CDC, art. 39, I, no que couber).

**2. Negativação e dano moral**
- Inscrição de débito inexigível → dano moral; **obrigatório enfrentar a Súmula 385/STJ**
  (anotação anterior): como o débito anterior estava **quitado desde 2025** (manutenção
  indevida), a 385 tende a ser afastada — mas o risco de afastamento/redução do dano moral
  deve constar do parecer.
- Dano moral também pelo conjunto: idosa, verba alimentar atingida, vazamento LGPD, descaso
  pós-reclamação — não apenas pela negativação.

**3. Competência e cabimento no JEC/BH (recorte MG/JEC)**
- **Lei 9.099/95, art. 3º, I**: teto de **40 salários mínimos** — somar os pedidos econômicos
  (R$ 19.400 + R$ 21.000 + R$ 2.100 + parcelas debitadas + dano moral) contra o teto vigente
  na data do ajuizamento; se exceder, **renúncia expressa ao excedente** (art. 3º, §3º) ou
  vara cível. Acima de 20 SM, **advogado obrigatório** (art. 9º).
- Prova documental basta (extratos, protocolo, BO, resposta ANPD) — **sem perícia complexa**;
  se o banco suscitar perícia forense no dispositivo, avaliar risco de extinção por
  complexidade e ter plano B na justiça comum.
- Territorial: domicílio da consumidora (art. 4º, III, Lei 9.099/95 c/c CDC, art. 101, I) —
  Belo Horizonte. Sem custas/sucumbência em 1º grau (art. 55) — pesa na estratégia.

**4. Processo, prova e tutela**
- **Inversão do ônus** (CDC, art. 6º, VIII): logs, trilha antifraude e cadastro do
  dispositivo estão com o banco — pedir exibição.
- **Tutela de urgência** (CPC, art. 300): (i) suspensão dos descontos na conta da
  aposentadoria; (ii) exclusão/suspensão da negativação; (iii) abstenção de novas cobranças —
  perigo evidente (verba alimentar).
- Juros e correção **pós-Lei 14.905/2024**: correção pelo **IPCA** e juros pela **taxa
  legal** (SELIC deduzido o IPCA) — CC, arts. 389 e 406, redação vigente; dano moral: correção
  do arbitramento (**Súmula 362/STJ**), juros do evento danoso (**Súmula 54/STJ**),
  registrando a interação com o novo regime.
- Prescrição: **5 anos** (CDC, art. 27) — sem risco (fatos de 2026), mas consignar.

**5. Teses de defesa a antecipar**
(i) culpa exclusiva da vítima/fato de terceiro — rebatida pela 479 + nexo com o vazamento;
culpa concorrente como subsidiária; (ii) inaplicabilidade da 479 à "autofraude" — distinguir:
a engenharia social só foi possível pelos dados vazados do próprio banco e pela inação do
antifraude; (iii) Súmula 385 contra o dano moral — enfrentar como acima; (iv) complexidade da
causa para afastar o JEC — enfrentar como acima.

**6. Prognóstico (jurimetria)**
Fundamentado **na base MG/JEC do sistema**; sem amostra suficiente, a IA deve **dizer isso
expressamente** e dar prognóstico qualitativo por tese (material: alta; dano moral:
média-alta com risco 385; dobro do art. 42: média) — **jamais inventar percentuais ou
acórdãos** (violação = reprovação no citation gate).

### A.3 Rubrica de avaliação (gates objetivos)

| # | Critério | Reprova se |
|---|---|---|
| 1 | Toda afirmação jurídica com fonte (lei/artigo/súmula) e vigência | norma revogada ou "jurisprudência pacífica" sem fonte |
| 2 | Súmula 479/STJ aplicada ao fortuito interno | ausente |
| 3 | Súmula 385/STJ **enfrentada** | omitida ou mal aplicada |
| 4 | Teto 40 SM + renúncia (art. 3º, §3º) + advogado >20 SM | cálculo de alçada ausente |
| 5 | Juros/correção pós-Lei 14.905/2024 | 1% a.m. do art. 406 antigo sem ressalva |
| 6 | LGPD arts. 42–48 conectada ao nexo causal | vazamento tratado como irrelevante |
| 7 | Dobro do art. 42, §ú com requisito do engano justificável | dobro sem fundamento |
| 8 | Tutela com os 3 comandos + perigo (verba alimentar) | ausente |
| 9 | ≥3 das 4 teses de defesa antecipadas | menos de 3 |
| 10 | Jurimetria: números só com base declarada; senão, qualitativo com ressalva | percentual/acórdão inventado |
| 11 | Sem PII real; saída marcada como rascunho (HITL) | apresentada como parecer final |

---

*Relatório gerado no branch `claude/analise-modulo-ia-ha0hbi`. Achados fora do escopo desta
reanálise viram Issues próprias, conforme governança.*
