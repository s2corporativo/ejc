# EJC — Auditoria de verificação e novos achados (2026-08-27)

## 0. Antes de ler isto

Este documento **não é** uma auditoria forense do zero. O EJC já tem uma: 13
rodadas em `docs/auditoria/relatorios/parte-01..13`, consolidadas em
`docs/auditoria/relatorios/2026-08-21-auditoria-forense.md`, com um backlog
canônico e verificável em `docs/PLANO_MESTRE_STATUS.md` (65 itens). O
`CLAUDE.md` do repositório proíbe re-auditar sem reproduzir. Este relatório
obedece essa regra: verifica no código de hoje (commit `5c0c776`, 111 commits
depois da auditoria de 21/08) o que mudou, e só registra como achado novo o
que não tem ID correspondente no backlog canônico.

**Diferença de método, importante:** a auditoria de 21/08 foi *black-box*
— chamadas HTTPS à API de produção, sem acesso ao código-fonte. Esta é o
oposto — leitura estática de código-fonte (6 frentes paralelas: backend,
banco/migrations, frontend, segurança/LGPD, núcleo de IA/RAG, testes/CI/dívida
técnica), **sem acesso a produção, ao banco real ou ao navegador**. As duas
metodologias são complementares, não substitutas — nenhuma das duas
sozinha define o estado real do sistema em produção. Toda vez que um número
de produção (contagem de embeddings, proporção de documentos sem `case_id`
etc.) é citado abaixo sem confirmação, está marcado NÃO CONFIRMADO.

**Nenhuma correção foi aplicada.** Este é só o mapeamento. Achados que
pareçam simples de corrigir permanecem como estão até uma tarefa própria de
correção — inclusive porque `docs/PLANO_MESTRE_STATUS.md` estabelece que o
flip de status de um item acontece **na mesma PR que o corrige**, nunca numa
PR de auditoria separada. Por isso este documento não altera nenhuma linha
existente da tabela canônica — só propõe, ao final, quais linhas merecem
reverificação por quem pegar aquele item.

---

## 1. Resumo executivo

O sistema está em estado ativo de remediação — não parado desde a auditoria
de 21/08. Dos 65 itens do backlog canônico: 11 mesclados, 4 verificados, 15
em andamento, 35 pendentes (`scripts/status_check.sh --resumo`, 2026-08-27).
Nesta verificação, **5 itens marcados "pendente" já parecem resolvidos no
código** (a tabela não foi atualizada — não é evidência de trabalho não
feito, é evidência de checklist desatualizado) e **2 itens marcados
"pendente" reproduzem parcialmente** (parte do sintoma original foi corrigida,
parte continua).

O achado mais sério desta rodada é novo e não estava em nenhum backlog
anterior: **o kill-switch documentado de IA (`AI_ENABLED=false`) não
desliga o ponto de entrada oficial do Núcleo Único (`/ai/core/*`)** — ver
AUD27-P0-01. Em segundo lugar, um endpoint de criação de caso
(`POST /cases/`) escapou da correção de RBAC que acabou de ser aplicada em
14 routers irmãos (commit `4ab8618`, 26/08) — mesma classe de bug, mesmo
padrão de correção disponível, só não foi migrado — ver AUD27-P1-01.

Nenhum heads divergente no Alembic, nenhuma migration destrutiva nova, nenhum
segredo hardcoded, nenhuma branch remota órfã (contrariando o alerta da
missão sobre "múltiplos agentes trabalhando em paralelo" — não há evidência
disso agora), e a suíte de testes é extensa (542 arquivos de teste backend,
113 no frontend) com lacunas pontuais, não sistêmicas.

## 2. Registro de achados novos

Prioridades conforme a missão: P0 = perda de dado/exposição de
segredo/bypass de auth/corrupção de banco. P1 = módulo essencial
quebrado/autorização inconsistente. P2 = funcionalidade parcialmente
quebrada/integração incompleta/ausência de testes. P3 = débito técnico sem
impacto operacional imediato.

| ID | Prioridade | Módulo | Camada | Problema | Evidência | Impacto |
|---|---|---|---|---|---|---|
| AUD27-P0-01 | **P0** | Núcleo de IA | Backend | Kill-switch `AI_ENABLED` não protege `/ai/core/*` (endpoint oficial do Núcleo Único) | `backend/app/routers/ai_core.py:109-199`; `services/ai/core/orchestrator.py`; `provider_policy.py:73-136`; `provider_registry.py:10-47` — nenhum checa `AI_ENABLED` | Desligar a IA pela flag documentada não impede geração de peças/análises por esse caminho durante um incidente |
| AUD27-P1-01 | P1 | Casos | Backend/RBAC | `POST /cases/` usa `require_roles()` hierárquico (não `_exact`) — `financeiro`/`estagiario` passam mesmo fora da lista pretendida na criação de caso | `backend/app/routers/cases.py:223-225` | Papel de faturamento cria registro de caso com dados pessoais de cliente — mesma classe de bug do commit `4ab8618`, não migrada neste endpoint |
| AUD27-P1-02 | P1 | Núcleo de IA | Testes | `ai_skills.py` (609 linhas, OCR/transcrição/skills) sem nenhum teste | 0 ocorrências em `backend/tests/` | Área crítica (HITL, gate de citações) sem rede de segurança de regressão |
| AUD27-P2-01 | P2 | Governança IA | Backend | `/ia-governanca/guardrails` conta peças de casos excluídos — reintroduz em painel específico o sintoma que V2-3.3 já corrigiu em dashboard/listagem | `backend/app/routers/ia_governanca.py:558-559` | Painel de governança mostra número inflado de peças "sem revisão" |
| AUD27-P2-02 | P2 | Qualidade IA | Backend/RBAC | `qualidade.py` (`/verificar-citacoes`, `/consistencia`, `/simular-adversario`) usa piso hierárquico sem comentário de intenção — `financeiro` pode acessar | `backend/app/routers/qualidade.py:69,76,92` | Papel fora da equipe jurídica dispara análise de IA sobre conteúdo de peça/tese; intenção não confirmada |
| AUD27-P2-03 | P2 | Inteligência Jurídica | Testes | `cerebro.py` (Cérebro do EJC) sem teste funcional, só existência de rota no snapshot OpenAPI | `grep -rln cerebro backend/tests/` → só `snapshots/openapi_rotas_baseline.json` | Endpoint estratégico de IA sem cobertura de comportamento |
| AUD27-P2-04 | P2 | Observabilidade | Infra | Sentry pronto no código (scrub LGPD, `send_default_pii=False`) mas sem `SENTRY_DSN`; recomendado por 3 relatórios de auditoria distintos, sem item no backlog canônico | `backend/app/main.py:198-208`; `.env.example:645`; `docs/observabilidade.md` | Falhas em produção só aparecem em log de container, ninguém é avisado proativamente |
| AUD27-P2-05 | P2 | Áreas jurídicas | Frontend | `AREAS_FALLBACK` (frontend) tem 24 áreas, enum backend `CaseArea` tem 25 — falta `licitacoes` | `frontend/src/lib/areaCatalog.ts:4-28` vs `backend/app/models/case.py:9-39` | Se `GET /areas` falhar, seletor de área não oferece "Licitações"; `areaLabel("licitacoes")` retorna o slug cru |
| AUD27-P2-06 | P2 | Áreas jurídicas | Frontend | 4ª manifestação de taxonomia de área (`areasWorkspace.ts::AREAS_CANONICAS`, 26 entradas, rótulos "Direito X") diverge de `AREAS_FALLBACK` (24, rótulos "X") | `frontend/src/pages/ramos/areasWorkspace.ts:29-55` | Rótulo da mesma área pode aparecer diferente em telas distintas |
| AUD27-P2-07 | P2 | RAG/Biblioteca Jurídica | IA | Cobertura de RAG ainda insuficiente após lotes 001/002 (25/08): 8 das ~29 áreas antes sem fonte ganharam 1 documento cada, mas todos com `rag_status=pendente` (não contam como base viva); ~21 áreas seguem sem nenhuma fonte | commits `2fd5d69`, `b7a5321`; `docs/biblioteca_juridica/README.md:60` | Agentes com `exige_fonte=True` nessas áreas continuam sem base verificável |
| AUD27-P3-01 | P3 | CI/CD | Infra | `governanca.yml`/`auto-integracao.yml` seguem armados no YAML (`on: pull_request`/`workflow_run`) — podem reativar merge automático sem revisão se o Actions da conta voltar | leitura direta dos 2 arquivos | Reativação silenciosa do merge automático (§6-A) sem decisão consciente |
| AUD27-P3-02 | P3 | Módulos a cortar | Backend | CORTE-2/CORTE-3 parcialmente executados (routers já movidos para `_dead_code/` desde 12/08) mas status "pendente" não reflete a nuance; `services/diplomacia_digital.py` e `core/victory_vault.py` seguem ativos | `backend/app/routers/_dead_code/README.md`; `services/diplomacia_digital.py` (importado por `visual_law_core.py:23`) | Risco de retrabalho ou de subestimar o que falta cortar |
| AUD27-P3-03 | P3 | Cliente 360 | Frontend | Aba morta inalcançável `"ia_cliente"` em `DossieCliente.tsx` (não está em `abas` nem em `validTabs`) | `frontend/src/pages/DossieCliente.tsx:1579-1593` vs `:1249-1256`,`:990-997` | Nenhum em runtime; confunde manutenção futura |
| AUD27-P3-04 | P3 | Layout | Frontend | `components/Layout.tsx` (669 linhas) não é importado por nada — substituído por `LayoutReference.tsx` | 0 ocorrências de import | Código morto |
| AUD27-P3-05 | P3 | Dashboard | Frontend | `DashboardLegalTechPremium.tsx` (480 linhas), autodescrito "componente de demonstração", não importado por nenhuma página | cabeçalho do arquivo; 0 imports externos | Código morto |
| AUD27-P3-06 | P3 | UI/CSS | Frontend | CORTE-7 subestimado: `UI.tsx` cresceu para 1484 linhas (era 1437); CSS global são 12 arquivos/7815 linhas (título do item diz "8") | `frontend/src/components/UI.tsx`; `main.tsx:5-24` + `index.css:2` | Dívida de consolidação visual maior que a registrada |
| AUD27-P3-07 | P3 | Backlog | Docs | `PLANO_MESTRE_STATUS.md` cita números de migration desatualizados pela renumeração de 22-23/08: CL-A2 diz "migration 149" (real: `152_thesis_candidate_tese_banco.py`), CL-B3 diz "migration 148" (real: `151_case_status_anterior.py`) | `docs/PLANO_MESTRE_STATUS.md:82,88` | Quem seguir o backlog para auditar essas colunas abre o arquivo errado |
| AUD27-P3-08 | P3 | Diversos routers | Backend | Padrão de `UPDATE` dinâmico via f-string (`text(f"UPDATE ... SET {','.join(sets)}...")`) com allowlist estática de coluna — seguro hoje, frágil se um refactor futuro passar a aceitar dict cru do request | `office_contracts.py:128`, `agenda_eventos.py:212`, `pending_items.py:257`, `memoria_institucional.py:160`, `bank_analysis.py:135` | Nenhum hoje; risco latente de SQLi por nome de coluna em regressão futura |
| AUD27-P3-09 | P3 | Usuários/DJEN | Backend | `oab_number` e `djen_oab_numero` seguem sem reconciliação (subitem já citado em V2-3.5, ainda aberto) | `backend/app/models/user.py:43,48` | Débito técnico; dois campos de mesmo propósito sem fonte única |
| AUD27-P3-10 | P3 | Casos | Backend | `DELETE /cases/{id}` bloqueia por prazo/honorário/peça protocolada, mas não bloqueia nem cascateia peças em status não-terminal (ex. rascunho) | `backend/app/routers/cases.py:661-701` | Peças em rascunho de caso excluído ficam fisicamente órfãs (mitigado na UI pela visibilidade herdada, não na integridade referencial) |
| AUD27-P3-11 | P3 | Banco | DB | Tabelas "espinha" (`cases`, `documents`, `deadlines`, `clients`) sem índice em `deleted_at`, usado em ~138 arquivos como filtro de soft-delete; outras tabelas já receberam esse índice em migrations dedicadas | `backend/alembic/versions/001_inicial.py` (cases/documents/deadlines sem index) | NÃO CONFIRMADO impacto real (precisa de `EXPLAIN ANALYZE` em produção) — estrutural |

## 3. Detalhamento dos achados P0/P1

### AUD27-P0-01 — Kill-switch de IA não cobre o Núcleo Único

- **Evidência:** `backend/app/routers/ai_core.py` define os 5 endpoints
  oficiais do Núcleo (`/ai/core/chat`, `/task`, `/analyze`, `/generate`,
  `/report`, linhas 109-199) chamando `SingleAICoreOrchestrator.run()`
  diretamente. Nenhum ponto do caminho router → orchestrator →
  `provider_policy.avaliar()` → `provider_registry` checa
  `settings.AI_ENABLED`. Em contraste, `AI_ENABLED` é checado em ~15 pontos
  de entrada legados (`ai_service.py`, `case_intel.py`,
  `motor_peca_service.py`, routers `intake.py`, `ia_saude.py`, `ai.py`
  etc.) — o kill-switch existe e é real, só não cobre o caminho que o
  próprio sistema documenta como oficial hoje.
- **Causa provável:** o Núcleo Único (`services/ai/core/`) foi construído
  depois dos pontos de entrada legados e herdou o próprio kill-switch
  separado (`AI_EXTERNAL_PROVIDERS_ALLOWED`, que desliga só provedores
  externos, não a IA inteira) sem herdar a checagem de `AI_ENABLED`.
- **Impacto:** se o titular (ou um incidente jurídico/de segurança) exigir
  desligar a IA via `AI_ENABLED=false`, o Núcleo Único continua respondendo
  por `/ai/core/*` enquanto houver qualquer provedor elegível (Ollama local
  sempre conta). Kill-switch cosmético para essa superfície.
- **Dependências:** nenhuma migration; mudança pontual de código.
- **Correção recomendada:** checar `settings.AI_ENABLED` uma única vez em
  `SingleAICoreOrchestrator.run()` (cobre todos os call sites de uma vez),
  levantando 503, ou como dependency FastAPI no `APIRouter` de
  `ai_core.py`.
- **Teste necessário:** cobrir em `test_agentes_invariantes.py` (ou
  equivalente) um caso `AI_ENABLED=false` → `/ai/core/chat` deve recusar.
- **Risco de regressão:** baixo — é uma checagem aditiva no início do fluxo.
- **Rollback:** trivial (reverter o commit).

### AUD27-P1-01 — `POST /cases/` fora do padrão RBAC recém-corrigido

- **Evidência:** `backend/app/routers/cases.py:223-225` usa
  `require_roles([...,"secretaria"])`. Como `require_roles()` (sem
  `_exact`) tem fallback hierárquico por `ROLE_LEVEL`, e `secretaria` é o
  papel de nível mais baixo da lista, qualquer papel de nível igual ou
  maior passa — incluindo `estagiario` e `financeiro`, que o comentário do
  próprio código ("M16: criar caso = equipe jurídica/gestão/intake") não
  pretende incluir.
- **Causa provável:** é literalmente a mesma classe de bug da Issue #694,
  que o commit `4ab8618` (26/08) acabou de corrigir em 14 routers de
  ferramentas jurídicas — este endpoint ficou de fora da migração.
- **Impacto:** `financeiro` (papel de faturamento, sem relação com atuação
  jurídica) consegue criar casos com dados pessoais de cliente —
  inconsistente com a exclusão de `financeiro` já adotada em
  `EQUIPE_JURIDICA` e nos 14 routers já corrigidos.
- **Dependências:** nenhuma — o padrão de correção (`require_roles_exact`)
  já existe e está testado (`test_rbac_equipe_juridica_694.py`).
- **Correção recomendada:** trocar por
  `require_roles_exact(["superadmin","admin","socio","advogado","advogado_auxiliar","secretaria"])`,
  igual ao padrão do `4ab8618`.
- **Teste necessário:** estender `test_rbac_matrix.py`/
  `test_rbac_equipe_juridica_694.py` para cobrir `POST /cases/`.
- **Risco de regressão:** baixo — troca de função de gate por outra já em
  uso no mesmo arquivo de segurança.
- **Rollback:** trivial.

### AUD27-P1-02 — `ai_skills.py` sem cobertura de teste

- **Evidência:** `backend/app/routers/ai_skills.py` (609 linhas, endpoints
  `/ai/skills/list`, `/execute`, `/execute-doc`, `/transcribe-media`) — zero
  ocorrência em `backend/tests/` (por nome de arquivo ou por rota).
- **Causa provável:** módulo relativamente novo, cobertura de teste não
  acompanhou.
- **Impacto:** área crítica por regra #3/#7 do `CLAUDE.md` (toda mudança de
  IA passa por gate de HITL/citação) sem rede de segurança de regressão.
- **Correção recomendada:** `backend/tests/test_ai_skills_router.py`
  cobrindo os 4 endpoints com o padrão do repo (`_FakeDB`/
  `dependency_overrides`).
- **Risco de regressão:** N/A (é adição de teste, não mudança de
  comportamento).

## 4. Itens do backlog canônico — estado reproduzido hoje

Tabela só dos itens onde a verificação de código mudou algo em relação ao
que `docs/PLANO_MESTRE_STATUS.md` registra. Itens não listados aqui foram
verificados como consistentes com a tabela canônica (ex. V2-2.2, V2-4.3,
CORTE-1/4/5, alembic single head) ou não foram objeto desta rodada.

| ID canônico | Status na tabela | Reprodução hoje (2026-08-27) | Ação sugerida |
|---|---|---|---|
| V2-3.6 | pendente | **Parece resolvido.** Commit `c1a060e` (22/08) corrigiu o pré-preenchimento do wizard Sala→Caso; o backend sempre gravou `descricao_fatos` corretamente — o bug era só no frontend. | Reverificar e flipar para `verificado` na PR que também resolver o item, citando `c1a060e` |
| CL-C1 | pendente | **Parece resolvido.** Campo `saudavel` já removido de `case_health.py` (comentário no código datado 24/08, "Classe C do plano-mestre") | Reverificar/flipar |
| CL-C2 | pendente | **Reenquadrado, não pendente.** Decisão deliberada e documentada no código de **não** unificar os limiares (respondem perguntas diferentes: saúde do caso vs. probabilidade de êxito) — `health_thresholds.py` nunca foi criado por decisão consciente, não por atraso | Reverificar; se a decisão for aceita, marcar `verificado` com nota "reenquadrado, ver comentário em case_health.py" em vez de "pendente" |
| V2-6.1 | pendente | **Parece resolvido.** Middleware `api_version_middleware.py` (desde commit `8bc0c41`, 15/08) reescreve `/api/v1/{path}` → `/api/{path}`; nenhum router declara prefixo `/v1` duplicado hoje. Se ainda reproduzir em produção, é questão de deploy defasado (produção usa lote manual), não de código. | Reverificar contra produção antes de flipar (deploy manual pode estar atrasado) |
| V2-5.1 | pendente `[ALTO]` | **Parece resolvido, backend e frontend.** As 15 rotas de calculadora têm `endpoint:` em `frontend/src/pages/ramos/ramosConfig.ts`, renderizadas por `RamoBase.tsx`/`RamoFerramenta.tsx` (componente funcional real, não stub) em `/areas-de-atuacao/:slug`, aba "ferramentas". Autoria da integração não identificada nesta auditoria. | Reverificar em navegador (skill `app-runner`) antes de flipar — esta auditoria não testou UI ao vivo |
| V2-3.3 | em-andamento | **Parcial.** Dashboard e listagem de peças (`legal_docs.py`, `dashboard.py`) já filtram peças de caso excluído. `/ia-governanca/guardrails` **não** filtra — ver AUD27-P2-01. `DELETE /cases/{id}` bloqueia por prazo/honorário/peça protocolada mas não cascateia peças em status não-terminal — ver AUD27-P3-10. | Manter `em-andamento`; os dois achados novos acima são o que falta para fechar |
| V2-3.5 | pendente | **Majoritariamente resolvido.** 4 dos 5 vínculos citados no achado original já corrigidos (`ai_log_id`, `Caso.jurimetria` removido, `descricao_fatos`, cascata parcial). Só `oab_number`×`djen_oab_numero` (subitem 5) segue aberto — ver AUD27-P3-09. | Reduzir escopo do item para só o subitem 5, ou fechar e abrir um item específico para ele |
| CL-A2 | em-andamento | Coluna `tese_banco_id` existe, mas na migration **152**, não 149 como a tabela registra (renumeração de 22-23/08 não propagada ao texto) | Corrigir a referência de migration na mesma PR que flipar o status |
| V2-1.5 | pendente | **Parcial / achado original possivelmente impreciso.** A maioria das rotas testáveis hoje responde; `/assinaturas` (real: `/signatures`) e `/crm/leads` (CRM é sub-recurso de `clients.py`, não módulo próprio) provavelmente eram erro de path no laudo original, não bug de rota. O 307 de barra final em rotas sem `redirect_slashes` ajustado ainda reproduz. | Reverificar com HTTP real antes de fechar — esta auditoria foi só estática |
| V2-6.5 | pendente | **Denominador cresceu.** 853 decoradores de rota hoje vs. ~453 rotas distintas citadas em julho — quase dobrou. Proporção de órfãs não recalculada (exigiria cruzar com uso real do frontend, método da auditoria de julho). Tende a estar pior em termos absolutos, não confirmado em proporção. | Recalcular com o mesmo método (cruzamento de bundle JS) antes de estimar prioridade de correção |
| CORTE-2 / CORTE-3 | pendente | **Parcialmente executado.** A camada de *router* já foi movida para `backend/app/routers/_dead_code/` em 12/08 (`diplomacia_v3.py`, `victory_vault_router.py`), mas os *services* subjacentes (`diplomacia_digital.py`, `core/victory_vault.py`) seguem ativos e usados (`teses_vitoriosas` continua com leitura/escrita real) | Ver AUD27-P3-02; reescrever a descrição do item para refletir "router cortado, service pendente" |

## 5. O que não mudou (confirmado consistente com a tabela canônica)

- **Alembic:** head único (`153_legal_doc_client_id`), sem divergência; 9
  migrations novas desde 21/08, todas com `downgrade()` funcional ou
  justificativa documentada de irreversibilidade; `MIGRATION_RESERVATIONS.md`
  bate com o diretório real.
- **CL-A5** (`teses_juridicas_v4`/`teses_vitoriosas`): ainda ativos e em
  uso — nenhuma migration os remove.
- **V2-3.4** (`case_id` opcional no upload de documento): ainda reproduz —
  nenhum commit recente toca esse fluxo.
- **V2-4.3** (citação incorreta "OAB Prov. 205/2021"): ainda em 22 arquivos,
  incluindo uma mensagem de erro HTTP visível ao usuário final
  (`legal_docs.py:584`) — nada mudou desde 21/08; segue corretamente
  marcado como pendente de decisão de um advogado real, não de código.
- **V2-2.2** (embeddings): comportamento do código confirmado como descrito
  na tabela (default `EMBEDDINGS_ENABLED=true`, self-heal real e ativo via
  scheduler). Dois commits novos (`2fd5d69`, `b7a5321`, 25/08) adicionam 8
  documentos de biblioteca jurídica cobrindo 8 das ~29 áreas antes sem
  fonte — incremento real, mas todos com `rag_status=pendente` (não contam
  como base viva até revisão humana) — ver AUD27-P2-07.
- **CORTE-1/4/5** (jurimetria, radar de notícias, sociedade): todos ativos e
  registrados em `main.py` — status "pendente" confere.
- **Segurança geral:** sem segredo hardcoded, sem SQL injection explorável,
  sem reintrodução de `passlib`/`python-jose`, isolamento cliente-documento
  (`legal_docs.py`) bem implementado e testado, sanitização de PII para IA
  externa em vigor e não enfraquecida, HITL obrigatório no servidor (não
  contornável pelo frontend), isolamento de RAG entre clientes/casos
  fail-closed e robusto.
- **Branches remotas:** só `main` e a branch de trabalho desta auditoria —
  nenhum indício de trabalho paralelo não integrado no momento desta
  checagem.
- **Dependências frontend:** 8 diretas, todas em uso — nenhuma órfã.
- **Routers backend:** nenhum router órfão (não registrado em `main.py`)
  encontrado entre os 162 arquivos de `backend/app/routers/`.

## 6. Não verificável nesta rodada

| Área | Motivo | Evidência/acesso necessário |
|---|---|---|
| Contagem real de embeddings em produção (0/47.359 ou atual) | Auditoria é código-fonte apenas, sem acesso a banco de produção (governança §9 do CLAUDE.md) | Consulta ao Postgres de produção |
| `SENTRY_DSN` preenchido em produção | Mesma restrição de acesso | `.env` do VPS |
| Se V2-6.1/V2-5.1 realmente funcionam para o usuário final | Verificação estática de código, sem servidor rodando nem navegador | Sessão com `app-runner` contra ambiente vivo |
| Proporção real de rotas órfãs (V2-6.5) | Exige cruzamento sistemático bundle JS × rotas, método da auditoria de julho, fora do orçamento desta rodada | Reexecução do método da Parte 11 |
| Uso real (telemetria) das skills de IA (CORTE-6) | Análise estática não mostra chamada em runtime | Logs/telemetria de produção |
| Se pipelines Woodpecker pós-`e747079` (26/08) estão passando | Sem acesso ao painel Woodpecker a partir deste ambiente | Painel `ci.depaulateixeira.adv.br` |
| Necessidade real dos índices em `deleted_at` (AUD27-P3-11) | Depende de `EXPLAIN ANALYZE` com dados de produção/staging | Acesso a banco com volume real |
| Contagem exata de testes coletados (`pytest --collect-only`) | Ambiente desta auditoria não tinha as dependências completas instaladas | `pip install -r requirements.txt` completo |

## 7. Notas técnicas (qualitativas, 0-10)

Não são uma reavaliação completa — refletem o que esta rodada + a tabela
canônica sustentam com evidência, não uma auditoria de UX/DevOps dedicada.

| Dimensão | Nota | Nota |
|---|---|---|
| Arquitetura | 7 | Camadas claras (router→service→model), Núcleo Único de IA bem desenhado; dívida em taxonomia duplicada e módulos não cortados |
| Backend | 7 | RBAC majoritariamente correto e recém-endurecido; 2 gaps pontuais identificados (P1, P2) |
| Frontend | 6 | Sem página órfã nem bypass de RBAC; débito visual real (12 CSS globais, `UI.tsx` de 1484 linhas) |
| Banco | 8 | Head único, sem drift, migrations disciplinadas, ledger de reservas consistente |
| Segurança | 7 | Sem achado explorável hoje; 2 gaps de RBAC (P0/P1) recém-descobertos por este próprio ciclo de correção incompleto |
| LGPD | 8 | Isolamento cliente-documento robusto e testado; sanitização de PII em vigor; 2FA desligado é risco aceito e documentado |
| IA/RAG | 6 | Gate de citação e HITL reais e não-cosméticos; cobertura de base de conhecimento ainda baixa; kill-switch com gap real (P0) |
| Testes | 7 | Cobertura extensa nas áreas críticas historicamente sensíveis; lacunas pontuais em routers de IA mais novos |
| DevOps/CI | 6 | Actions fora do controle da conta (não é falha do time); substituto self-hosted (Woodpecker) configurado corretamente mas jovem |
| Observabilidade | 5 | Sentry pronto, não ativado; sem item de backlog rastreando isso |
| Prontidão para produção | 6 | Sistema nunca operou ponta a ponta com caso real (conforme `plano-lancamento-v3.md`); esta rodada não muda esse fato |

## 8. Conclusão objetiva

```
AUDITORIA DE VERIFICAÇÃO CONCLUÍDA (não é auditoria forense do zero — ver seção 0)
Método: leitura estática de código-fonte, sem acesso a produção/banco/navegador
Commits analisados desde a auditoria anterior (21/08): 111 (47 tocando backend/app, frontend/src ou alembic)
Itens do backlog canônico reproduzidos/reverificados: 12
Itens aparentemente resolvidos com tabela desatualizada: 5 (V2-3.6, CL-C1, CL-C2, V2-6.1, V2-5.1)
Itens parcialmente resolvidos: 2 (V2-3.3, V2-3.5)
Achados novos: 21 (1 P0, 2 P1, 7 P2, 11 P3)
Áreas não verificáveis nesta rodada: 8 (listadas na seção 6, todas por falta de acesso a produção/ambiente vivo)
```

**Item que exige decisão humana, não técnica:** nenhum achado novo desta
rodada. Os dois já registrados no backlog canônico continuam de pé:
V2-4.3 (qual norma citar no lugar de "OAB Prov. 205/2021" — precisa de
advogado real) e V2-5.2/T5 (curadoria contínua da base de conhecimento).
