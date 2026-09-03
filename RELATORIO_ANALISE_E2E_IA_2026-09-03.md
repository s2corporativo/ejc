# Relatório — Análise ponta a ponta do EJC com foco em IA · 03/09/2026

Pedido do titular: "análise completa de ponta a ponta — possíveis erros, rotas,
fluxos, inteligência, central de conhecimento da IA, todas as APIs e ligações
de IA". Repositório `s2corporativo/ejc`, head `802c8ed` (main), branch
`claude/ai-system-end-to-end-analysis-b44lgi`.

**Suposição registrada** (CLAUDE.md, fluxo de trabalho): o pedido foi lido como
*auditar com evidência real, corrigir o que for pontual, de baixo risco e fora
de PR ativo, e registrar o restante com arquivo:linha para decisão*. Nenhuma
mudança de comportamento de IA, RBAC ou contrato de API entrou sem ser
regressão de teste ou defeito reproduzido.

**Método de verificação.** Cada achado abaixo carrega um marcador:
- `[VERIFICADO]` — reproduzido ao vivo ou conferido por leitura direta do
  código pelo autor deste relatório.
- `[SUBAGENTE]` — apontado por uma das quatro frentes de auditoria paralelas
  (núcleo de IA/RAG, rotas backend×frontend, integrações/provedores, frontend
  de IA), com arquivo:linha, **não** reproduzido pelo autor. Não vira afirmação
  do PR até ser conferido; vale como pauta de conferência.
- `[FALSO POSITIVO]` — apontado por subagente e **refutado** por reprodução.

---

## 1. Veredito executivo

1. **A `main` estava vermelha.** A suíte completa do backend no head `802c8ed`
   tem **17 falhas em 6.776 testes** (`[VERIFICADO]`, §3). Todas são deriva de
   fakes/ledger deixada pelos merges #1365 (assinaturas) e #1348/#1349
   (clientes): o código está certo, os testes não acompanharam. Corrigidas
   neste PR. O portão local exigido pelo CLAUDE.md ("suíte completa uma vez
   antes do push") não foi cumprido nesses merges — é a crítica central deste
   relatório, pela mesma razão do pente fino de 30/08: um portão que não roda
   não protege.
2. **O sistema sobe e funciona do zero** (`[VERIFICADO]`): 146 migrations em
   PostgreSQL 16 + pgvector 0.6.0 limpo, head único `155`; app real de pé;
   login → troca de senha obrigatória → painéis de diagnóstico; pipeline de
   embeddings local (`multilingual-e5-large`, 1024d) vetoriza e a busca
   semântica governada devolve súmulas; sem provedor de IA configurado, toda
   porta de IA degrada com 502 e mensagem leiga, nunca 500.
3. **Arquitetura de IA íntegra nos invariantes** (`[VERIFICADO]` por leitura +
   quatro frentes convergentes): gateway único (zero import de SDK fora de
   `services/providers/`), kill-switch `AI_ENABLED` como requisito de todo
   provedor na fonte única (`provider_registry`), barreira LGPD única antes de
   provedor externo, HITL estrutural (`is_rascunho` incondicional), gate de
   citações fail-closed, RAG com gate de aprovação/vigência/quarentena em
   todas as pernas, isolamento por cliente fail-closed.
4. **O que limita a IA hoje não é arquitetura, é configuração e ligação**: os
   painéis divergem entre si sobre provedores (cinco cópias da regra de
   elegibilidade fora da fonte única), o cadastro de conhecimento tinha como
   opção padrão uma categoria que o backend rejeita sempre, e a Biblioteca de
   Prompts exibia o JSON cru em vez da resposta. Três desses defeitos foram
   corrigidos aqui; o resto está em §5–§7 com arquivo:linha.

---

## 2. Ambiente e portões (evidência — substitui o CI indisponível)

Container remoto sem Docker; Python 3.11.15, Node 22.22.2, PostgreSQL 16.13
+ pgvector 0.6.0 (cluster efêmero `initdb`, porta 5433), fastembed com
`intfloat/multilingual-e5-large` baixado no primeiro uso. Dados exclusivamente
fictícios (admin `admin.e2e@ejc.adv.br`), banco descartável.

| Portão | Comando | Head `802c8ed` (antes) | Branch (depois) |
|---|---|---|---|
| Migrations do zero | `alembic upgrade head` em PG16+pgvector limpo | ✅ 146 migrations, head `155_indices_listagem_espinha` | idem |
| Lint backend | `ruff check app` | ✅ | ✅ |
| Suíte backend completa (com `RUN_DB_TESTS=1`) | `pytest tests -q` | ❌ **17 failed**, 6776 passed, 66 skipped | ✅ **6797 passed**, 0 failed, 66 skipped |
| Typecheck frontend | `npm run lint` (tsc) | ✅ | ✅ |
| Testes frontend | `npm test` | ✅ 110 arquivos, 594 passed | ✅ 110 arquivos, 594 passed |
| Build frontend | `npm run build` | ✅ | ✅ |
| Revisão de segurança (`security-auditor`, diff de auth/config) | — | — | ✅ aprovado com ressalvas; as ressalvas (§3.7, §3.8) foram fechadas na branch |
| App ao vivo | `/api/health/ready`, `/api/diagnostico/central`, `/api/architecture/{routes,semantic-audit}` | ✅ ready; 866 rotas, 0 duplicatas, 0 violações semânticas; 8 ok / 2 alerta esperados (sem provedor de IA; jobs sem execução no processo novo) / 0 erro | — |
| RAG ao vivo | `/api/rag/status`, `/api/rag/buscar` | ✅ 24 docs seed → 0 vetorizados no boot; após `reembedar_chunks_orfaos` 24/24 e busca semântica devolve resultados | — |

---

## 3. Defeitos CORRIGIDOS neste PR

### 3.1 `[VERIFICADO]` 17 testes vermelhos na `main` (deriva pós-merge)

| Grupo | Causa (merge) | Arquivos de teste | Correção |
|---|---|---|---|
| 8× `ValueError: not enough values to unpack (expected 4, got 2)` | #1365 passou a selecionar `(id, titulo, mimetype, filename)` em `signatures.listar` (`routers/signatures.py:189-196`); fakes devolviam 2-tuplas | `test_correcoes_go_live.py`, `test_pente_fino_onda1.py`, `test_portal_fees_melhorias.py` | fakes com 4 colunas |
| 6× `'_Res' object has no attribute 'first'` | #1348 introduziu `pode_ver_cliente` com `.first()` (`core/client_ownership.py:54`) | `test_lgpd_registros.py`, `test_sociedades_cliente.py` | `_Res.first()` |
| 1× `ValidationError: senha_inicial ≥ 10` | #1349 subiu `SENHA_MIN_LEN`; o teste usava senha de 8 chars esperando o 400 do handler | `test_clients_sigilo_titularidade_dblevel.py` | senha longa sem dígito (exercita `validar_forca_senha`) |
| 2× ledger de rotas | #1365 publicou `POST /api/signatures/{sig_id}/documento-visualizado` sem registro; #1348/#1349 adicionaram `rate_limit` (`_dep`) em `/clients/{id}/ia-analise` e `/export/clientes.csv` sem registro | `test_rotas_registro_explicito.py` | entradas em `ADICOES_INTENCIONAIS` e `AUTH_ALTERACOES_INTENCIONAIS` (só acréscimo de dependência; nenhum gate removido) |

### 3.2 `[VERIFICADO]` Testador do Cofre validava chave Anthropic já revogada
`backend/app/services/credential_testers.py:184` — `s.ANTHROPIC_API_KEY or
os.getenv("ANTHROPIC_API_KEY", "")`. Com o `.env` injetado por `env_file`, a
revogação pelo Cofre (Settings=`""`) era anulada pelo fallback e o painel
respondia "configurada". O provider (`anthropic_provider._api_key()`) já havia
removido esse padrão e o documenta como falha. Correção: lê só Settings.
Teste: `test_analise_e2e_2026_09_03.py::test_testar_anthropic_ignora_env_apos_revogacao`.

### 3.3 `[VERIFICADO]` `GET /ai/status` e gate de `/ai/executar` liam `os.getenv`
`backend/app/routers/ai_tools.py:45-70` — `_ai_enabled()` e o painel ignoravam
Settings/Cofre, `*_ENABLED`, `AI_EXTERNAL_PROVIDERS_ALLOWED` e Maritaca, e
afirmavam `modelo_complexo="(=rapido)"` fora do container (default real:
`claude-opus-4-8`). Observado ao vivo: `/ai/status` dizia `modelo_rapido:
claude-haiku-4-5-20251001, modelo_complexo: (=rapido)` enquanto
`/ia-governanca/provedores` (fonte de verdade) dizia `claude-opus-4-8`.
Correção: Settings + `provider_registry.provider_elegivel/motivo_inelegivel`
(mesma fonte de `/ia-governanca/provedores`); campo novo `motivos_inelegiveis`
com os mesmos textos já expostos por `/ia-governanca/provedores`. Testes:
`test_ai_status_le_settings_e_registry`, `test_ai_enabled_segue_settings_nao_env`.

### 3.4 `[VERIFICADO]` Central de Conhecimento: opção padrão do formulário sempre dava 422
`frontend/src/pages/Conhecimento.tsx:34,40,134,147,462-463` oferecia
`peca_escritorio` (default) e `precedente_interno`; o backend rejeita ambas
(`ai_service._RESTRICTED_CATS`, `routers/rag.py:118`) — conteúdo de
cliente/caso exige fluxo dedicado. Removidas do catálogo e dos dois modais;
default passa a `jurisprudencia`.

### 3.5 `[VERIFICADO]` Biblioteca de Prompts exibia JSON cru
`frontend/src/pages/Prompts.tsx:97` lia `resultado ?? conteudo ?? texto`; o
backend devolve `resposta` (`routers/prompts_juridicos.py:299`). Caía sempre
no `JSON.stringify(data)`. Corrigido (chave `resposta` primeiro).

### 3.6 `[VERIFICADO]` Quatro chamadas do frontend caíam em 307 para o prefixo legado
Reproduzido ao vivo: `GET /api/v1/clients → 307 Location: /api/clients/`,
idem `/cases`, `POST /api/v1/timesheet → 307 /api/timesheet/`. O middleware de
versão reescreve o path antes do `redirect_slashes`, então o redirect sai para
`/api/...` (legado, `Deprecation: true`). Corrigidos com barra final:
`SalaJuridica.tsx:639,766`, `EntradaUnica/Confirmacao.tsx:61`,
`CasoDetalhe/TabTimeline.tsx:93`. Mesma classe dos shims fechados em 30/08.

### 3.7 `[VERIFICADO]` Gate `cliente_externo` inerte em `/ai/status` e `/ai/executar`
Achado da revisão de segurança deste PR (`security-auditor`), confirmado por
reprodução: `UserRole` é `(str, Enum)` sem `__str__`, então em Python 3.11
`str(UserRole.cliente_externo) == "UserRole.cliente_externo"` e a comparação
em `routers/ai_tools.py:54` nunca batia. Sem exploração hoje — o
`AuthMiddleware` (`auth_middleware.py:200-213`) barra o portal antes do
router — mas a segunda camada estava quebrada. Corrigido (compara pelo
`.value`); teste com `User(role=UserRole.cliente_externo)` real.

### 3.8 `[VERIFICADO]` Higiene: `_anthropic_key()` morto com o padrão inseguro
`ai_gateway.py:248-250` mantinha `settings.ANTHROPIC_API_KEY or os.getenv(...)`
sem nenhum chamador e com docstring "mesma resolução do provider" (já falsa).
Removido para que a classe de defeito de §3.2 não volte por reuso.

---

## 4. Refutado

### 4.1 `[FALSO POSITIVO]` "Rótulo composto rebaixa o piso LOCAL_COMPLETO"
Subagente do núcleo de IA reportou como P0 que
`sanitization_policy.rotulo_de_sigilo_reforcado` devolveria `violencia`
(externo pseudonimizado) para `"violencia sexual"`. Reproduzido com a
configuração real do app: `violencia sexual → crimes_sexuais`, `guarda de
menor → menores`, `criminal sexual → crimes_sexuais`, `abuso sexual →
crimes_sexuais`, `Vara da Infância e Juventude → infancia_juventude` — todos
`LOCAL_COMPLETO`. O stub de config usado pelo subagente não reproduz o mapa
real. Nada a corrigir; sugere-se apenas ampliar
`tests/test_sigilo_piso_area.py` com esses rótulos compostos para travar o
comportamento.

---

## 5. Achados NÃO corrigidos — decisão do titular ou fora de escopo pontual

Ordem: severidade, depois raio de efeito. "PR ativo" indica arquivo pertencente
a PR aberto (regra 10 do CLAUDE.md — não tocado).

### 5.1 Ligações de IA / provedores

| # | Sev. | Achado | Onde | Status |
|---|---|---|---|---|
| A1 | P1 | `resumo` e `chat_rapido` não têm `anthropic` na cadeia (`TASK_ROUTING`). No desenho de produção do compose (Ollama desligado, Maritaca/Groq sem chave) a cadeia é vazia **com Anthropic saudável** — e essas tarefas são o destino de `TarefaIA.DEFAULT/TRIAGEM/RESUMO` do orquestrador e da conversa livre da Sala Jurídica. A `AIProviderPolicy` aprova (monta cadeia por prioridade) e o gateway falha por cadeia vazia. | `ai_gateway.py:173-182`, `orchestrator.py:62-64`, `legal_chat_service.py:56` | `[VERIFICADO]` por leitura. Decisão de custo/roteamento: acrescentar `("anthropic", None)` ao fim das duas cadeias (modelo rápido, custo Haiku) ou completar a cadeia com elegíveis restantes quando vazia |
| A2 | P2 | `MARITACA_ENABLED` com três defaults: `config.py:201` = `False`, `.env.example:121` = `false`, `docker-compose.yml:108,170` = `${MARITACA_ENABLED:-true}`. Quem sobe o stack sem a variável roda Maritaca **ligada**, com modelos default não soberanos (`sabia-4`), contrariando código e doc. | compose × config | `[SUBAGENTE]` — decisão do titular: alinhar as três fontes |
| A3 | P2 | Cinco cópias da regra de elegibilidade fora do `provider_registry`: `integration_status.py:126-158` (omite `GROQ_ENABLED`, `AI_EXTERNAL_PROVIDERS_ALLOWED`), `ia_saude.py:89`, `config.py:1138-1141`, `ai_gateway.health():688-691` (que ainda **gasta cota** batendo no Groq a cada consulta). É o item V2-6.3 do plano mestre, agora com linhas. | idem | `[SUBAGENTE]` — refatoração de painéis para `provider_elegivel()` |
| A4 | P2 | `claude-opus-5` não está em `_MODERN_PREFIXES` (`anthropic_provider.py:30-36`): configurar esse modelo envia `temperature` e recebe 400, com fallback silencioso para Maritaca/Groq. `ai_cost.py:16-22` não precifica `claude-opus-5`/`claude-fable-5*` (custo 0 no AILog) e precifica `claude-sonnet-5` a 3/15 (tabela vigente: 2/10). `claude-haiku-4-5-20251001` é ID com sufixo de data (canônico: `claude-haiku-4-5`). | provider + custo | `[VERIFICADO]` IDs por grep; preços conferidos com a tabela vigente do skill `claude-api` |
| A5 | P2 | Sem deadline agregado na cadeia de fallback (120+90+60+180 s em série). | `ai_gateway.py:487-599` | `[SUBAGENTE]` |
| A6 | P2 | Cache de resposta consultado **antes** da resolução da cadeia: com `AI_RESPONSE_CACHE_ENABLED=true`, desligar `AI_ENABLED` não corta entregas durante o TTL; cache hit não grava AILog; tarefa `LOCAL_COMPLETO` (conteúdo em claro) é cacheável. Flag nasce `False`. | `ai_gateway.py:398-421,1017-1034`, `ai_cache.py:46-49` | `[SUBAGENTE]` |
| A7 | P2 | Custo Anthropic subestimado: `cache_read/creation_input_tokens` não precificados (`AI_PROMPT_CACHING_ENABLED=True` por default). | `ai_cost.py:56-60` | `[SUBAGENTE]` |
| A8 | P3 | `_chamar_provedor` despacha provedor desconhecido para Groq (`ai_gateway.py:955-957`); `_anthropic_key()` morto com o padrão `os.getenv` (`ai_gateway.py:248-250`); métrica `provider="policy"` fora da soma por provedor. | gateway | `[SUBAGENTE]` |
| A9 | P2 | `docs/ai/EJC_ANTHROPIC_PROVIDER_INTEGRATION.md` e `EJC_AI_PROVIDER_POLICY.md` desatualizados (modelo complexo, prioridade default, Maritaca ausente). | docs | `[SUBAGENTE]` — docs-only |

### 5.2 Núcleo de IA (sanitização, HITL, custo)

| # | Sev. | Achado | Onde | Status |
|---|---|---|---|---|
| B1 | P1 | AI Skills não consultam `Case.sigilo_reforcado` nem passam `modo_sanitizacao` (provider externo por default). | `ai_skill_service.py:182-188`, `routers/ai_skills.py:92-107` | `[SUBAGENTE]` — conferir e corrigir com `modo_sigilo_do_caso` (padrão já usado em `orchestrator.py:251`) |
| B2 | P1 | Nove serviços chamam o gateway com conteúdo de caso sem `modo_sanitizacao` (`peca_service`, `motor_peca_service`, `dossie_service`, `matriz_teses_service`, `case_intel`, `deep_research_service`, `checklist_ia`, `anexos_service`, `ai_skill_service`). Mitigação existente: NER local pseudonimiza nomes mesmo sem `entidades`. | ver §5.2 do relatório do subagente | `[SUBAGENTE]` — `peca_service` e `motor_peca_service` pertencem a PRs ativos (#1376/#1384) |
| B3 | P1 | Dez call sites com `db`+`user` que chamam o gateway sem gravar `AILog` (`score_juridico.py:93`, `jurisprudencia_interna.py:231`, `honorarios_oab`, `analise_bancaria`, `checklist_ia.py:89`, `movimento_ia.py:54`, `document_classifier.py:145`, `visual_law.py:87`, `analise_estrategica.py:234`, `diplomacia_digital.py:80`) — custo e trilha LGPD invisíveis. | idem | `[SUBAGENTE]` |
| B4 | P1 | Loop agêntico valida com `fontes=None` (`ai/agent/loop.py:535`): toda resposta sem citação confirmada sai carimbada "SEM BASE VERIFICÁVEL" mesmo com RAG usado; fontes nunca chegam ao AILog. | agente | `[SUBAGENTE]` |
| B5 | P2 | `ProcessAgent` (prazos) e outros 7 agentes sem `exige_fonte=True` (`agent_registry.py:63-70`); rotas que devolvem texto de LLM sem `is_rascunho/requer_revisao` (`teses.py:544-600`, `jurisprudencia_interna.py:218-250`, `provas.py:411`, `honorarios_oab`, `analise_bancaria`); `documento_ia.py:187-198` perde o carimbo HITL nos ramos de erro. | HITL | `[SUBAGENTE]` |
| B6 | P2 | Piso `AI_NIVEL_INTELIGENCIA_MERITO` nunca alcançado pelo núcleo: schemas de `/ai/core/*` e o orquestrador informam `"alto"` por default, e `_nivel_piso` só vale quando o chamador não informa nível. Persiste o achado de 18/08 pela ponta oposta. | `routers/ai_core.py:45`, `orchestrator.py:90`, `ai_gateway.py:107-141` | `[SUBAGENTE]` |
| B7 | P2 | `deep_research` grava AILog sem tokens/custo e faz duas chamadas para um log. | `deep_research_service.py:168-178` | `[SUBAGENTE]` |

### 5.3 Central de conhecimento (RAG)

| # | Sev. | Achado | Onde | Status |
|---|---|---|---|---|
| C1 | P2 | Seed deixa os 24 documentos iniciais **sem vetor** até o job horário `reembed_rag_orfaos` (`:20`); na primeira hora após instalação a busca semântica devolve vazio (observado ao vivo: `vetorizado: 0` após seed). | `seeds/seed_all.py` × `scheduler.py:1213` | `[VERIFICADO]` — rodar o reembed ao final do seed quando embeddings estiverem disponíveis |
| C2 | P2 | Auto-aprovação: documento sem estado de governança **nasce aprovado** (`knowledge_autoapproval.py:98-101`). | governança | `[SUBAGENTE]` — PRs #1382/#1383 (RAG governança) estão abertos e podem já cobrir; conferir antes de duplicar |
| C3 | P2 | Cobertura/saúde da base contam documentos que o gate de recuperação exclui (sem `rag_status`, vigência, quarentena, corpus fictício). | `rag_coverage.py:57-59`, `knowledge_governance.py:425-429` | `[SUBAGENTE]` |
| C4 | P2 | `scope_case_id` propagado em 5 de 37 call sites — intimação de outro processo do mesmo cliente volta a entrar como contexto. | `ai_service.py:75-105` + call sites | `[SUBAGENTE]` |
| C5 | P2 | `legal_chunker` corta em 2.400 chars (> janela de 512 tokens do e5-large; cauda sem vetor) e não é usado pela ingestão de produção (só script). | `legal_chunker.py:12`, `ingestion_service.py:53` | `[SUBAGENTE]` |
| C6 | P2 | `rag_public`: chave `knowledge:write` sem `client_id` aceita `client_id/case_id` arbitrários do payload (fica `pendente`, mas polui a fila de outro cliente). | `routers/rag_public.py:321` | `[SUBAGENTE]` |
| C7 | P2 | Roteamento por ramo: 14 chaves em `ejc_skill_catalog._LEGAL_DATA` contra 27 áreas canônicas; `civel`/`penal` fora do enum (`civil`/`criminal`); `native_skill_coverage()` compara um conjunto consigo mesmo e nunca acusa ramo faltante. | `ejc_skill_catalog.py:77-150,267-291,387-406` | `[SUBAGENTE]` |
| C8 | P1 (UX) | Aprovação de conhecimento na aba Curadoria: um clique, sem exibir o conteúdo, sem `notas`, e o endpoint audit-logado `POST /rag/governanca/docs/{id}/revisar` **não tem chamador** no frontend. | `GovernancaIA.tsx:121-137`, `KnowledgeGovernancePanel.tsx` | `[SUBAGENTE]` — decisão de fluxo |
| C9 | P1 (UX) | Importação de jurisprudência envia `aprovar_para_rag: true` fixo, sem checkbox/confirmação, e ignora o `aviso` do extrator. | `GovernancaIA.tsx:167-193` | `[SUBAGENTE]` |

### 5.4 Rotas, RBAC e fluxos

| # | Sev. | Achado | Onde | Status |
|---|---|---|---|---|
| D1 | P2 | `secretaria` pode criar caso (`_PODE_CRIAR_CASO`) mas leva 403 em `GET /cases/` (`requer_equipe_juridica`): cria e não vê. | `routers/cases.py:68-72,122,243` | `[SUBAGENTE]` — decisão de RBAC |
| D2 | P2 | `module_registry.py` promete papéis que o router nega (`produtividade` → advogado; `casos` → secretaria) e `moduleRegistry.tsx` tem 18 entradas sem `roles` (financeiro vê "Casos" no menu e toma 403). | `module_registry.py:100,163,384`; `moduleRegistry.tsx:356-369,477-495,683-693` | `[SUBAGENTE]` |
| D3 | P2 | CORS não lista `PUT` (`main.py:329`) e existem 2 rotas + 2 chamadas `PUT` (preferências de notificação, lifecycle de módulos). Latente com nginx same-origin. | `main.py` (PR ativo #1377/#1379) | `[SUBAGENTE]` |
| D4 | P2 | `DataRoom.tsx:72` pagina `/documents/` com `per_page` (ignorado; o router só entende `page_size`) — seletor sempre limitado aos 20 mais recentes. Reproduzido: `?per_page=100 → 200` sem efeito. | `DataRoom.tsx` (PR ativo #1403) | `[VERIFICADO]` |
| D5 | P2 | `Deadline.origem="entrada_unica"` fora de todo contrato declarado (comentário da coluna: `manual|datajud`; tipo TS: `manual|datajud|importacao_ia`). | `entrada_service.py:659`, `models/deadline.py:65-68`, `types/index.ts:110` | `[SUBAGENTE]` |
| D6 | P2 | 14 handlers mutantes sem `try/catch` (falha vira silêncio): `TabPartes.tsx:38`, `TabResumo.tsx:151,459`, `TabMemoria.tsx:44`, `CasoDetalhe.tsx:468,481`, `DataRoom.tsx:60,77`, `Workflow.tsx:91`, `SalaJuridica.tsx:402`, `IA.tsx:156` (marcação HITL — 403/409 do gate de citações sem mensagem), `SecurityMenu.tsx:102`, `AnaliseExtratos.tsx:103`. | frontend | `[SUBAGENTE]` |
| D7 | P3 | `ErrorBoundary` envia stack sem truncar; backend limita a 8000 chars → 422 e o crash não é registrado. | `ErrorBoundary.tsx:46-48`, `observabilidade.py:21-23` | `[SUBAGENTE]` |
| D8 | P3 | `/ia-governanca/provedores` fora do registry com lista literal de papéis (`App.tsx:170-177`). | frontend | `[SUBAGENTE]` |

### 5.5 Frontend de IA (contrato e HITL na tela)

| # | Sev. | Achado | Onde | Status |
|---|---|---|---|---|
| E1 | P1 | FAQ/Glossário (`ConteudoJuridico.tsx:25-46`) descarta `is_rascunho/aviso/aviso_hitl/log_id` devolvidos pelo backend e não tem `.catch` — conteúdo destinado ao portal sem aviso de rascunho. | frontend | `[SUBAGENTE]` |
| E2 | P1 | `detail` cru do FastAPI renderizado direto no JSX (`IaDefensivaCaso.tsx:113/331`, `Conhecimento.tsx:186/301,398/507`): em 422 o `detail` é array de objetos → `Objects are not valid as a React child`, ErrorBoundary derruba a aba. | frontend | `[SUBAGENTE]` |
| E3 | P2 | Painel de Provedores mapeia `operacional/atencao/indisponivel/...` mas o backend emite `nao_configurado/sem_registro/operacional/degradado/critico`: provedor **crítico** aparece cinza de "desabilitado". Observado ao vivo o vocabulário do backend. | `PainelProvedoresIA.tsx:108-130` × `ia_governanca.py:788-799` | `[VERIFICADO]` (vocabulário) |
| E4 | P2 | Saúde da IA: erro de carga vira painel de zeros (`DashboardIA.tsx:12-18`). | frontend | `[SUBAGENTE]` |
| E5 | P2 | IA Defensiva e tela IA sem caminho de `override_citacoes` (409 do gate trava o fluxo; o padrão correto existe em `Pecas.tsx:376-402`). | `IaDefensivaCaso.tsx:59-67`, `IA.tsx:156-162` | `[SUBAGENTE]` |
| E6 | P2 | Limites de tamanho do backend não espelhados no Assistente IA (`/ai/resumir-texto` max 12.000 chars; a UI só exige > 4). | `AssistenteIA.tsx:74-102` | `[SUBAGENTE]` |
| E7 | P2 | Botões privativos de advogado/sócio visíveis a estagiário/auxiliar (`SalaJuridica.tsx:876-895` converter/vincular; `Prompts.tsx:195-201` excluir). | frontend | `[SUBAGENTE]` |
| E8 | P2 | Streams sem cleanup na desmontagem (`AgenteIA.tsx:73`; polling de `MotorTeses.tsx:66-92` até 180 s). | frontend | `[SUBAGENTE]` |

### 5.6 Integrações externas e operação

| # | Sev. | Achado | Onde | Status |
|---|---|---|---|---|
| F1 | P2 | Teto diário de consultas **pagas** da Infosimples com TOCTOU (COUNT depois INSERT, sem lock) e tabela `infosimples_uso` criada em runtime fora do Alembic. | `infosimples_service.py:265-289,313-336,406` | `[SUBAGENTE]` |
| F2 | P2 | `ingestion_service.fetch(validar_ssrf=True)` valida o IP mas requisita pelo hostname (DNS rebinding residual); `rag_public` e `document_url_import_service` fazem certo. Mitigado por allowlist de domínios oficiais. | `ingestion_service.py:74-87` | `[SUBAGENTE]` |
| F3 | P2 | `TRANSPARENCIA_*`, `RAG_AUTO_REEMBED_*`, `OLLAMA_TIMEOUT`, `AI_LIVE_GROUNDING_ENABLED`, `AI_AGENT_MAX_CUSTO_BRL` e outros existem em `Settings` e não no `.env.example` (o item AUD27-P1-5 manda "religar `RAG_AUTO_REEMBED_ENABLED`" sem a variável estar documentada). | `.env.example` × `config.py` | `[SUBAGENTE]` — docs/config |
| F4 | P3 | Heartbeat cobre 8 de ~41 jobs; `backup_drive` (o mais caro em falha) fora do heartbeat e do painel; jobs sem `misfire_grace_time` (restart no horário = execução do dia perdida em silêncio). | `heartbeat_service.py:13-20`, `scheduler.py:39` | `[SUBAGENTE]` |
| F5 | P3 | Google Drive (10 variáveis OAuth) fora do Cofre e do painel de integrações; webhook Evolution com segredo lido no import e token compartilhado (não HMAC do corpo); `DJEN_OABS_MONITORADAS` com OABs reais como default em `config.py:503`; outbox de eventos sem relay (`event_bus.py:34-63`). | diversos | `[SUBAGENTE]` |

---

## 6. Confirmado OK (não re-auditar sem reprodução)

- Gateway único: zero SDK de provedor fora de `services/providers/`; a única
  chamada HTTP direta à Anthropic é o teste de credencial (`/v1/models`), não
  inferência.
- Kill-switch e elegibilidade no **caminho de execução**: fonte única
  `provider_registry._requisitos`, consumida por gateway, policy e
  `_resolver_cadeia` (fail-closed; sem "Groq como último recurso"). AUD27-P0-1
  de fato fechado.
- Barreira LGPD única (`_chamar_com_barreira`), pseudonimização reversível só
  em memória, `_ProviderPulado`, NER local em terceira passada; piso
  `LOCAL_COMPLETO` não rebaixável por config e íntegro para rótulos compostos
  (§4.1).
- HITL estrutural (`hitl_policy.aplicar` mantém `is_rascunho=True` mesmo com
  `AI_REQUIRE_HITL=false`); gate de citações fail-closed (política inválida →
  bloquear; falha de verificação → 503; override com justificativa + AuditLog).
- RAG: 1024d coerente entre `config`, `models/rag.py`, migration 096 (HNSW
  cosine) e runbook; três validações independentes de dimensão/contagem; teto
  de lote (incidente OOM 27/08) presente; gate de recuperação aplicado em todas
  as pernas e no `citation_check`; dedup por origem + SHA-1 preservando decisão
  humana; isolamento por cliente fail-closed.
- Superfície pública: 12 rotas fora do JWT, todas com outro mecanismo (auth,
  ICS com HMAC, link de Data Room, API key do RAG público, webhook com secret
  obrigatório). Portal do cliente confinado por middleware, routers e guards.
- Registro de routers: 0 duplicatas, 0 colisões de template, 0 router morto
  (os 9 `ramos_*` são montados por `ramos.py`); 866 rotas ao vivo.
- Login → refresh → 2FA coerente ponta a ponta; contratos de caso, prazo e
  geração de peça batem; 0 chamadas mutantes sem corpo; 0 divergência de
  método; 0 prefixo `/api/v1` duplicado no cliente `api`.
- Sem `dangerouslySetInnerHTML` no frontend; renderizador Markdown valida
  `href`; sem `verify=False`; timeouts em 100% dos clientes HTTP; nenhuma chave
  em log ou em resposta de API; Cofre devolve só `last4`.
- Scheduler sem duplicidade (gate `ENABLE_SCHEDULER`, uvicorn sem `--workers`,
  worker Celery com scheduler desligado); backup com mutex cross-container.

---

## 7. Sugestões priorizadas (custo × retorno)

1. **Fechar A1 (cadeia vazia em `resumo`/`chat_rapido`)** — uma linha por
   cadeia; é a quebra funcional mais provável em produção com IA externa.
2. **Guarda de portão**: hook de pre-push que rode `pytest` completo antes do
   push em branch que toca `backend/` (o repo já tem `scripts/ci-local.sh`);
   os 17 vermelhos de §3.1 não teriam entrado na `main`.
3. **Unificar os painéis de provedores** em `provider_elegivel()` (A3) e
   alinhar o vocabulário do Painel de Provedores (E3) — fecha V2-6.3 na parte
   de IA de uma vez.
4. **Ledger de rotas como pré-requisito de merge**: rota nova ou dependência
   de auth nova sem entrada no ledger = PR não mesclável.
5. **Sigilo reforçado em todos os call sites** (B1/B2) com uma função única
   `modo_sigilo_para_case_id(db, case_id)` — a auditoria de 15/08 fechou o
   orquestrador; os serviços periféricos ficaram para trás.
6. **AILog em todo call site com `db`+`user`** (B3) — sem isso o painel de
   custo e a trilha LGPD (art. 37) não representam o gasto real.
7. **Frontend HITL**: E1/E2/E5 são os que podem expor rascunho sem aviso ou
   derrubar a tela; C8/C9 são decisão de fluxo do titular.

---

## 8. Dados fictícios e LGPD

Ambiente descartável desta sessão: admin fictício `admin.e2e@ejc.adv.br`,
banco `ejc_app`/`ejc_test` em cluster efêmero, 24 súmulas do seed. Nenhum dado
real, nenhum acesso a produção, nenhum segredo versionado. As sondas de IA
foram feitas **sem** provedor configurado — nenhum conteúdo saiu do container.

---

## 9. Críticas, sugestões e alterações — mais inteligente e mais simples

Base: tudo o que foi medido nesta sessão (§2–§6) mais as auditorias de 18/08
(capacidade) e 30/08 (E2E). Onde a proposta muda decisão de produto, custo ou
RBAC, está marcada como **decisão do titular**.

### 9.1 Críticas estruturais (o que impede o sistema de ser mais inteligente)

1. **A inteligência depende da porta, não da pergunta.** A mesma capacidade
   existe em cinco endpoints com contratos diferentes (`/ai/analisar-caso`,
   `/ai/core/analyze`, `/ai/casos/{id}/assistente`, `/ia-especializada/*`,
   `/ia-defensiva/analisar`; idem para chat, minuta e resumo). Só o
   orquestrador aplica sigilo do caso, escopo cliente+caso, RAG, nível, FIRAC,
   HITL e AILog de uma vez; as outras portas aplicam subconjuntos (§5.2 B1–B3).
   Consequência prática medida: nove serviços sem `modo_sanitizacao`, dez
   call sites sem AILog, quatro vocabulários HITL concorrentes.
2. **O teto de inteligência é configuração morta.** O piso
   `AI_NIVEL_INTELIGENCIA_MERITO=maximo` nunca é alcançado porque o núcleo
   informa `"alto"` por default (B6); o protocolo FIRAC continua desligado por
   default (18/08); o contexto entregue ao modelo usa ~2,5% da janela (18/08);
   a instalação limpa nasce com 24 súmulas sem vetor (C1); 11 das 27 áreas
   canônicas não têm método de ramo (C7); o chunker jurídico existe e não está
   no caminho de produção (C5). Nenhum desses limites exige modelo melhor.
3. **Fontes de verdade existem, mas as cópias vencem.** Elegibilidade de
   provedores (1 fonte, 5 cópias), áreas do direito (1 enum, 6 listas),
   catálogo de módulos (3 catálogos), ledger de rotas (manual), tipos TS
   escritos à mão contra schemas Pydantic (`origem` de prazo com 4 valores
   reais contra 2–3 declarados). Toda auditoria desde julho encontra a mesma
   classe de defeito porque a causa (cópia manual) não foi removida.
4. **O painel de custo não é confiável.** Sem AILog em dez call sites, sem
   preço para tokens de prompt caching, `deep_research` a custo zero e modelos
   novos sem tabela (A4, A7, B3, B7): o número que o titular vê para decidir
   orçamento de IA está subestimado por construção.
5. **Não há régua.** O gold set (A-8 de 18/08) segue aberto. Sem avaliação
   reproduzível, "mais inteligente" não é mensurável, e cada mudança de prompt
   ou de provedor é um salto no escuro — inclusive as propostas abaixo.
6. **O processo deixa a `main` envelhecer.** Dezessete testes vermelhos
   entraram por merges recentes sem que o portão local rodasse; o ledger de
   rotas não foi atualizado por três PRs; o harness E2E já tinha envelhecido em
   silêncio em agosto. O CI parado virou ausência de portão, não portão local.

### 9.2 Alterações para deixar o sistema mais inteligente

| # | Alteração | Efeito esperado | Esforço | Decisão |
|---|---|---|---|---|
| I1 | **Uma porta de IA por capacidade** (`analisar`, `redigir`, `resumir`, `conversar`, `extrair`), todas resolvidas por `orchestrator.executar(tarefa, contexto)`, que aplica sigilo, escopo cliente+caso, RAG, nível, FIRAC, gate de citações, HITL e AILog. Os 25 endpoints de `ai.py` e os periféricos viram adaptadores finos e depois shims 308. | Elimina B1–B3, B5, C4 e a fragmentação de 18/08 de uma vez; qualidade deixa de depender da porta | Grande (2 ondas) | Titular (quebra frontend por etapas) |
| I2 | **Nível por tarefa, não por chamador**: default `None` nos schemas de `/ai/core/*` e no orquestrador; `_nivel_piso` decide; FIRAC ligado para tarefas de mérito; nos modelos Anthropic modernos usar `thinking: adaptive` + `output_config.effort` (`xhigh` para peça/estratégia, `low` para triagem/resumo) em vez de `temperature`. | O "carro bem projetado" passa a receber combustível; custo controlado por tarefa | Pequeno | Autor (já autorizado pela política de piso) |
| I3 | **Contexto do caso como dossiê estruturado**: `context_builder` monta fatos, partes, documentos classificados, prazos, teses vinculadas, intimações **do caso** (`scope_case_id` obrigatório quando há `scope_client_id`) e base legal da área, com o prefixo estável sob prompt caching (já ligado). | Usa a janela do modelo; fecha C4; reduz alucinação por falta de fato | Médio | Autor |
| I4 | **Base de conhecimento que nasce pronta e cresce sozinha**: seed vetoriza ao final (C1); chunker jurídico no caminho de produção com teto derivado da janela do modelo (C5); auto-ingestão das intimações DJEN e das peças aprovadas (`ingerir-ai-log` já existe) por caso; curadoria pelo endpoint audit-logado `revisar` com o conteúdo visível (C8); métricas de cobertura derivadas do mesmo filtro do gate (C3). | Busca semântica útil desde a instalação; base cresce com o trabalho real do escritório | Médio | Autor; C8/C9 titular |
| I5 | **Agentes com fonte**: acumular fontes do RAG no loop (B4); `exige_fonte=True` em `ProcessAgent`/`SecurityLGPDOABAgent` (B5); taxonomia única `AREAS_CANONICAS` no roteamento por ramo, com método para as 11 áreas faltantes e cobertura calculada contra o enum (C7). | Fim do "SEM BASE VERIFICÁVEL" falso; prazos e LGPD com citação obrigatória | Pequeno/médio | Autor; métodos de ramo exigem advogado |
| I6 | **Grounding ao vivo por default nas tarefas de mérito**: `AI_LIVE_GROUNDING_ENABLED` e `AI_GROUNDING_DATAJUD_ENABLED` documentados no `.env.example` e ligados quando a integração estiver configurada. | Resposta confere andamento/jurisprudência real antes de afirmar | Pequeno | Titular (custo de chamadas) |
| I7 | **Régua**: gold set de 30 casos anonimizados (peça esperada, citações válidas, área, prazo) + script `eval/` com LLM-juiz e `citation_check`; roda em todo PR que toque prompt, provedor ou RAG e publica delta. | "Mais inteligente" vira número; protege contra regressão de prompt | Médio | Titular (curadoria jurídica humana) |
| I8 | **Cadeia de provedores por tarefa completa e com deadline** (A1, A5): Anthropic no fim de `resumo`/`chat_rapido`; `AI_CHAIN_DEADLINE_SECONDS`; `claude-opus-5` em `_MODERN_PREFIXES` e na tabela de custo (A4). | Sem cadeia vazia em produção; sem request de 7 min; custo real | Pequeno | Titular (custo) |
| I9 | **Custo verdadeiro**: AILog em todo call site com `db`+`user` (B3), tokens de cache precificados (A7), `deep_research` com tokens (B7), alerta de budget por área. | Painel de custo confiável para decidir | Pequeno/médio | Autor |

### 9.3 Alterações para deixar o sistema mais simples

| # | Alteração | Efeito esperado | Esforço | Decisão |
|---|---|---|---|---|
| S1 | **Gerar, não copiar**: tipos TS e enums (`CaseArea`, `DeadlineOrigem`, status) gerados do OpenAPI (`openapi-typescript`) num passo de build; apagar as 6 listas de áreas, os `AREA_LABEL` locais e o tipo `Deadline` manual. Teste de paridade vira desnecessário. | Fim da classe de defeito "cópia que diverge" no frontend | Médio | Autor |
| S2 | **Um painel de diagnóstico**: `/diagnostico/central` consome `provider_registry` (elegibilidade + motivo) e `integration_status` passa a chamar a mesma função; remover `/ai/status` e o `_estado_provedores` de `ia_saude` (A3); Painel de Provedores com o vocabulário do backend (E3). | V2-6.3 fechado; um lugar para olhar | Pequeno/médio | Autor |
| S3 | **Perfil de IA em vez de 12 flags**: `AI_PROFILE=externo|local|hibrido|desligado` deriva `*_ENABLED`, `AI_EXTERNAL_PROVIDERS_ALLOWED` e prioridade; compose herda os defaults do código (A2); teste que reprova campo de `Settings` ausente do `.env.example` (F3). | Configuração impossível de ficar incoerente entre código, `.env.example` e compose | Pequeno/médio | Titular (defaults) |
| S4 | **Poda de superfície guiada por telemetria**: ciclo trimestral com `/uso-rotas` (90 dias sem uso → 308 + `Deprecation` → remoção); remover o prefixo legado `/api` quando a telemetria mostrar zero uso; `PUT` → `PATCH` nas duas rotas restantes (D3). | ~350 rotas sem consumidor deixam de ser superfície de ataque e manutenção | Médio (contínuo) | Titular (janela de telemetria) |
| S5 | **Módulos 34 → 10–12 e o Caso como espaço de trabalho** (V3-B3/B4 do plano mestre): Entrada Única → Caso → (documentos, prazos, peças, IA) numa tela; menu com o que sobra. RBAC de tela derivado do `module_registry` do backend, nunca de lista literal (D2, D8). | Advogado leva um caso do início ao protocolo sem conhecer o sistema — critério de lançamento | Grande | Titular (plano próprio já existe) |
| S6 | **Ledger de rotas automático**: snapshot OpenAPI regenerado pelo teste com diff revisável no PR (rota nova ou auth alterada aparece como diff, não como assert quebrado). Pre-push obrigatório com `ruff` + `pytest` (backend tocado) e `tsc` + `vitest` (frontend tocado), usando `scripts/ci-local.sh`. | Os 17 vermelhos e os 3 PRs sem ledger não teriam entrado | Pequeno | Autor |
| S7 | **Um jeito de carregar e um jeito de errar no frontend**: hook `useCarregar` (carregando / vazio / falhou) e `mensagemErroHttp` em todo handler (D6, D7, E2, E4); `detail` cru nunca vai ao JSX. | Fim das falhas silenciosas e das telas que caem em 422 | Médio (mecânico) | Autor |
| S8 | **Um vocabulário HITL**: `hitl_policy.aplicar()` como último passo de toda rota que devolve texto de modelo; remover `requer_revisao_humana`/`necessita_revisao_humana` (B5); UI exibe `aviso_hitl` por padrão em todo componente de resultado (E1). | Frontend e painéis enxergam todo rascunho | Pequeno/médio | Autor |
| S9 | **Cortes já pautados** (plano mestre CORTE-1..7 e CL-A5): jurimetria/predição, `diplomacia-v3`, Victory Vault, notícias, sociedade, skills sem uso em log, `UI.tsx` de 1.437 linhas. | Menos superfície, menos prompt sem dono, menos risco disciplinar | Médio | Titular |

### 9.4 Ordem sugerida (três ondas)

1. **Onda 1 — barato e imediato** (autor, sem decisão de produto): I2, I5, I9,
   S2, S6, S7, S8 e os pontos pequenos de I4 (seed vetoriza; chunker no
   caminho). Fecha a maior parte dos P1 do §5 e devolve confiança ao painel de
   custo e ao ledger.
2. **Onda 2 — decisões do titular com uma linha de código cada**: I8 (cadeia
   e deadline), I6 (grounding), S3 (perfil de IA e defaults), D1 (secretaria),
   C8/C9 (fluxo de aprovação de conhecimento), I7 (gold set: começa com 10
   casos).
3. **Onda 3 — estrutural**: I1 (uma porta por capacidade), I3 (dossiê de
   contexto), S1 (tipos gerados), S4 (poda por telemetria), S5 (34 → 10–12).
   I1 e S5 são a mesma direção do parecer arquitetural já aprovado; o que este
   relatório acrescenta é a evidência de que a fragmentação custa qualidade
   jurídica mensurável hoje, não só manutenção.

**Critério de sucesso de cada onda**: o gold set (I7) melhora ou não piora, a
suíte completa fica verde no push, e `/ia-governanca/provedores`,
`/diagnostico/central` e o painel de custo dizem a mesma coisa.

---

## 10. Execução das ondas (03/09/2026, por ordem do titular)

O titular autorizou executar as três ondas do §9.4 até o fim. Registro do que
entrou, com o mesmo critério de verificação do resto do relatório: só é
`[VERIFICADO]` o que foi conferido no código ou provado por teste desta sessão.

**Método.** Cinco frentes em worktrees isolados (núcleo de IA, RAG/contexto,
configuração/diagnóstico, frontend, portas por capacidade), integradas na
branch e submetidas aos portões completos. Regra 10 do `CLAUDE.md` respeitada:
arquivo pertencente a PR aberto não foi tocado — cada exceção está listada
abaixo.

### 10.1 Entregue

| Item do §9 | O que entrou | Onde |
|---|---|---|
| **I2** nível por tarefa | `nivel_inteligencia` vira `Optional[str] = None` nos schemas de `/ai/core/*` e no orquestrador; `None` deixa `_nivel_piso` decidir (mérito → `maximo`, que aciona FIRAC; econômicas → `padrao`) | `routers/ai_core.py`, `services/ai/core/orchestrator.py` |
| **I8** cadeia e deadline | `anthropic` no fim das cadeias `resumo` e `chat_rapido` (modelo rápido); `AI_CHAIN_DEADLINE_SECONDS=240` com `asyncio.timeout` em volta do laço de provedores | `ai_gateway.py`, `config.py` |
| **A4** modelos e preços | `claude-opus-5` em `_MODERN_PREFIXES`; tabela de custo com Opus 5, Sonnet 5 corrigido para 2/10, família Fable; modelo fora da tabela vira `warning`, não custo zero silencioso | `providers/anthropic_provider.py`, `ai_cost.py` |
| **A7** custo de cache | `cache_creation_input_tokens` × 1,25 e `cache_read_input_tokens` × 0,10 do preço de input, propagados até o `AILog` | `ai_cost.py`, `ai_gateway.py` |
| **A6** cache × kill-switch | Consulta ao cache só depois de haver cadeia elegível; cache hit grava `AILog`; tarefa `LOCAL_COMPLETO` deixa de ser cacheável | `ai_gateway.py`, `ai_cache.py` |
| **A8** fail-closed | Provedor desconhecido levanta erro em vez de cair no Groq; `health()` usa a fonte única e não gasta cota do provedor | `ai_gateway.py` |
| **I9/B3** AILog | Registro em nove call sites que tinham `db`+`user` e não gravavam (score jurídico, jurisprudência interna, honorários, análise bancária, checklist, movimento, classificador de documento, visual law, análise estratégica) | routers e services citados |
| **S8** vocabulário HITL | `hitl_policy.aplicar()` como último passo nas rotas que devolvem texto de modelo, inclusive nos ramos de erro do `documento_ia` | `routers/teses.py`, `jurisprudencia_interna.py`, `provas.py`, `honorarios_oab.py`, `analise_bancaria.py`, `documento_ia.py` |
| **I5/B4** agentes com fonte | Fontes do RAG acumuladas no loop e passadas ao validador (fim do "SEM BASE VERIFICÁVEL" falso); `exige_fonte=True` em prazos e LGPD/OAB; áreas do catálogo alinhadas ao enum canônico; empate de palavra-chave deixa de escolher por ordem alfabética | `services/ai/agent/**`, `agent_registry.py`, `ejc_skill_catalog.py` |
| **C1** seed vetorizado | O seed reindexa os órfãos ao final quando os embeddings estão disponíveis (`SEED_EMBED_ORFAOS`) — busca semântica útil desde o primeiro boot | `seeds/seed_all.py`, `scripts/reembedar_chunks_orfaos.py` |
| **C5** chunk × janela | `EMBEDDINGS_MAX_CHARS=1800` limita o chunker jurídico e o corte por tamanho; chunker jurídico entra no caminho de produção da ingestão manual e da API pública | `legal_chunker.py`, `routers/rag.py`, `routers/rag_public.py` |
| **C3** métricas pelo gate | `filtros_gate_rag()` vira fragmento único, usado por cobertura e saúde; `usable_docs` passa a refletir o que o RAG realmente recupera | `ai_service.py`, `rag_coverage.py`, `knowledge_governance.py` |
| **C4** escopo por caso | `scope_case_id` propagado onde o caso já era conhecido (análise de caso, teses ocultas, contrato, deep research, dossiê, tools do agente) | diversos services |
| **C6** rag_public | Chave irrestrita não aceita mais `client_id`/`case_id` no payload; chave restrita só o próprio cliente, com 422 explícito | `routers/rag_public.py` |
| **B7** deep research | `AILog` com tokens e custo somando as duas chamadas; entidades do caso propagadas | `deep_research_service.py` |
| **I3** dossiê de contexto | Contexto do caso em seções de ordem estável (base legal, partes, documentos, prazos, teses, intimações do caso, pergunta), com tetos por seção e total | `services/ai/core/context_builder.py` |
| **DJEN → RAG** | A captura por advogado passa a ingerir a intimação vinculada ao caso (`rag_status=pendente`; curadoria segue humana) | `djen_service.py` |
| **S3** perfil de IA | `AI_PROFILE` (`externo\|local\|hibrido\|desligado`) deriva flags e prioridade; compose alinhado ao código | `config.py`, `docker-compose*.yml` |
| **A2/F3** configuração | `MARITACA_ENABLED` com o mesmo default nas três fontes; `.env.example` documenta todo campo de `Settings`, travado por teste de paridade | `.env.example`, `tests/test_env_example_paridade.py` |
| **S2/A3** painéis | Diagnóstico e saúde da IA consultam `provider_registry`; fim das cópias que ignoravam `GROQ_ENABLED` e o kill-switch de externos | `integration_status.py`, `routers/ia_saude.py` |
| **S6** portões | `scripts/ledger_rotas.py` (diff revisável do ledger) e pre-push por área do diff (`scripts/instalar_hooks.sh`) | `backend/scripts/`, `scripts/hooks/` |
| **S4** poda | `scripts/poda_rotas.py` lista candidatas por telemetria; `API_ROTAS_DEPRECIADAS`/`API_ROTAS_SUNSET` marcam rotas antes da remoção | `backend/scripts/`, `core/api_version_middleware.py` |
| **F4** jobs | Heartbeat por resultado para backup e reembed; `misfire_grace_time` para o disparo perdido não sumir em silêncio | `heartbeat_service.py`, `scheduler.py` |
| **D3** CORS | `PUT` na lista de métodos (duas rotas o usam) | `main.py` |
| **S7/D6/E2/E4** frontend | `useCarregar` com três estados aplicado às abas e painéis; `try/catch` nos handlers mutantes; `detail` cru nunca vai ao JSX; stack do `ErrorBoundary` truncado | `frontend/src/lib/useCarregar.ts` e telas |
| **E1/E3/E5/E7/E8** frontend | Aviso HITL no FAQ/Glossário; vocabulário real de status no painel de provedores; diálogo de override de citações reutilizável; botões por papel; streams com cleanup | telas de IA |
| **C8/C9** conhecimento | Aprovação passa pelo endpoint audit-logado, com o conteúdo à vista e notas obrigatórias; importação de jurisprudência não aprova mais por padrão | `GovernancaIA.tsx`, `KnowledgeGovernancePanel.tsx`, `RevisaoConhecimentoDialog.tsx` |
| **S1** tipos gerados | `scripts/gerar_tipos_frontend.py` emite `types/gerado.ts` (áreas, enums de prazo, papéis) com teste que reprova arquivo desatualizado; listas locais passam a derivar dele | backend + frontend |
| **S5** menu | Removidas da navegação as entradas do Bloco 4 (jurimetria/predição, Victory Vault, radar, notícias, sociedade); Diagnóstico e Usuários saem do menu e ganham cartão em Configurações → Administração | `moduleRegistry.tsx`, `Configuracoes.tsx` |

### 10.2 Não entregue, com motivo

- **D1 — `secretaria` cria caso e não lista.** `routers/cases.py` pertence ao
  PR aberto #1380 (regra 10). A correção é de RBAC e precisa da decisão do
  titular entre dar leitura escopada ou tirar a permissão de criar.
- **C2 — auto-aprovação de documento não governado.** Coberto pelos PRs
  abertos #1382/#1383; não duplicado aqui.
- **B1/B2 parciais — sigilo reforçado em `peca_service` e `motor_peca_service`.**
  Ambos pertencem aos PRs abertos #1376/#1384. Os demais call sites receberam
  a propagação.
- **Chunker jurídico dentro de `ingestion_service`.** O arquivo está em PR
  aberto; a entrada em produção foi feita pelos call sites (`chunks=`), então
  os ingestores automáticos (Planalto, súmulas, TJMG) seguem no corte por
  tamanho até aquele PR fechar.
- **Menu em 12 entradas.** Ficou em 16. As quatro restantes (Sala Jurídica,
  Raio-X do processo, Banco de Teses, DPT360) só sairiam do menu virando abas
  do hub de Inteligência — isso é o Bloco 3 do plano (o caso como espaço de
  trabalho), redesenho com consequência de UX, não troca de flag. Escondê-las
  sem destino as deixaria inalcançáveis, o que é pior que uma entrada a mais.

### 10.3 Portões (evidência)

| Portão | Resultado |
|---|---|
| `ruff check app` | ✅ limpo |
| `pytest` completo com `RUN_DB_TESTS=1` (PG16 + pgvector) | ✅ **6.927 passed**, 66 skipped, 0 failed |
| `alembic upgrade head` do zero | ✅ head `155_indices_listagem_espinha` (sem migration nova) |
| `npm run lint` (tsc) | ✅ limpo |
| `npm test` | ✅ 117 arquivos, **626 passed** |
| `npm run build` | ✅ |
| `scripts/ledger_rotas.py --verificar` | ✅ sem divergência não declarada |
| App ao vivo com todas as ondas | ✅ boot limpo, 41 jobs, `/api/health/ready` ready, 866 rotas e 0 duplicatas |
| `/api/ai/status` ao vivo | ✅ agora diz `claude-opus-4-8` (antes `(=rapido)`) e lista os quatro provedores com motivo, pela fonte única |
| Seed em banco novo (C1) | ✅ **25 de 25 trechos vetorizados** ao final do seed — antes ficavam em 0 até o job horário |

### 10.4 Correções feitas na integração

- Os testes novos do frontend usavam `toHaveTextContent`, matcher de jest-dom
  que este projeto não instala. Reescritos para `textContent` + `toMatch`/
  `toContain` em vez de acrescentar dependência.
- Um teste de FAQ/Glossário exigia a mensagem genérica de IA indisponível; o
  contrato real é melhor (o detalhe técnico é filtrado e a tela usa o fallback
  específico da ação). A asserção foi alinhada ao contrato, mantendo a parte
  que importa: dialeto de infraestrutura nunca chega ao advogado.
- O teste de paridade de `.env.example` pegou, na integração, uma variável
  nova sem documentação (`DJEN_CAPTURA_INGERIR_RAG`) — exatamente o que ele
  existe para pegar. Documentada.
