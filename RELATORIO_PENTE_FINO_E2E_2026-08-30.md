# Relatório — Pente fino ponta a ponta do EJC (dados fictícios) · 29–30/08/2026

Pedido do titular: "pente fino de ponta a ponta, verificar se tudo está funcionando, com dados fictícios — links, funções, módulos, APIs — e sugestões de melhoria, funcionalidades, rotas/fluxos e críticas".

**Suposição registrada** (CLAUDE.md, fluxo de trabalho): o pedido foi lido como *auditar, corrigir o que for pontual e de baixo risco, e registrar o resto como sugestão/Issue*. Correções maiores não entraram.

Entregas: PR [#1316](https://github.com/s2corporativo/ejc/pull/1316) (Closes #1315) com as correções + este relatório.

---

## 1. Veredito executivo

**O sistema está funcional de ponta a ponta.** Subiu do zero (144 migrations em PG16+pgvector limpo), toda a verificação oficial passou, o fluxo real de trabalho (cliente → caso → documento → prazo → ciência → inteligência → cleanup) roda inteiro via API com asserts de efeito, e as 47 rotas do registry + 38 redirects legados abrem no navegador sem tela branca, sem erro de página e sem 5xx.

O pente fino achou e corrigiu **3 defeitos reais de produto** (um 500 permanente, um 403 indevido ao papel mais alto, e chamadas do frontend presas em shims 308) e **1 defeito sistêmico de QA**: o harness E2E canônico tinha envelhecido em silêncio — 17 probes de módulo apontavam para rotas inexistentes com `404` dentro do `expected` (smoke que aceita 404 não afirma nada), a matriz RBAC derivada acusava divergência falsa, e os dados fictícios não passavam mais na validação atual da API. **Um harness que envelhece sem quebrar é a crítica central deste relatório** — as guardas adicionadas agora quebram quando isso voltar a acontecer.

---

## 2. Ambiente e método

Container remoto (sem Docker daemon — verificação local conforme CLAUDE.md): Python 3.11.15, Node 22.22.2, PostgreSQL 16.13 + pgvector 0.6.0 instalados no host, cluster efêmero via `initdb` na porta 5433 (paridade com `scripts/ci-local.sh`), extensões `vector`/`pg_trgm`/`pgcrypto`. App real de pé: uvicorn :8000 + Vite :5173 (proxy). Dados exclusivamente fictícios com marcador `E2E-FICTICIO` (admin seedado, 4 contas por papel via `POST /users/`, cliente/caso de navegação), cleanup confirmado pós-DELETE.

Respeitado o histórico de auditorias: nada do que `docs/PLANO_MESTRE_STATUS.md` marca como resolvido foi re-auditado sem reprodução; os 11 falsos positivos de `docs/auditoria/relatorios/parte-12-falsos-positivos.md` não foram repetidos (em especial: rotas "inexistentes" por prefixo `/v1/` e métricas de peças).

## 3. Matriz portão a portão (evidência — substitui o CI indisponível)

| Portão | Comando | Resultado |
|---|---|---|
| Migrations do zero | `alembic upgrade head` em PG16+pgvector limpo | ✅ 144 migrations, head único `153_legal_doc_client_id` |
| Lint backend | `ruff check app` | ✅ All checks passed |
| Suíte backend completa | `RUN_DB_TESTS=1 SCHEMA_CHECK_DATABASE_URL=... pytest --cov=app --cov-fail-under=65` | ✅ **6617 passed**, 23 skipped, cobertura **71,44%** (inclui os 62 `*_dblevel`) |
| Typecheck frontend | `npm run lint` (tsc --noEmit) | ✅ limpo |
| Testes frontend | `npm test` | ✅ 113 arquivos, **614 passed** (inclui guardas novas) |
| Build frontend | `npm run build` | ✅ OK |
| Gate P0 | `scripts/ci_guard.sh` | ✅ aprovado |
| Homologação estrutural | `run_homologacao.py --validate` | ✅ matriz H01–H15 íntegra |
| Smoke E2E fictício | `qa/e2e/run_fictitious_smoke.py` | ✅ **787/787 passed, 0 failed**, 6 asserts de efeito, RBAC 5 papéis |
| Jornada de caso | `qa/e2e/run_case_journey.py` | ✅ fluxo completo verde (10 asserts de efeito; 1 timeout transitório sob carga — §5, item 4) |
| Navegação por navegador | Playwright/Chromium, login real | ✅ **89 rotas** (47 STAFF + 38 legacy + portal/extras): 0 tela branca, 0 pageerror, 0 API 5xx |
| Homologação ao vivo | `run_homologacao.py` (EJC_HAS_AI=false) | ✅ **0 FALHA** (13 cenários BLOQUEADOS por capacidade ausente no ambiente local: conta de portal, IA externa, runbooks de ops — declarado, não silencioso) |
| Diagnóstico runtime | `/api/health/ready`, `/api/diagnostico/central`, `/api/architecture/{routes,semantic-audit}` | ✅ ready; 7 ok/1 alerta esperado (nenhum provedor IA em dev)/0 erro; 879 rotas, 0 duplicatas, 0 violações semânticas |

## 4. Defeitos encontrados e CORRIGIDOS (PR #1316)

1. **`GET /api/modulos/cofre/relatorio` → 500 em toda chamada** (`backend/app/routers/novos_modulos.py`). SQL cru referenciava `d.title`; a coluna de `documents` é `titulo` (`UndefinedColumnError`, traceback capturado). Nenhum teste executava esse SQL contra o schema real. Correção + teste dblevel que extrai o SQL de dentro da própria rota e o executa no Postgres migrado — qualquer coluna que voltar a divergir quebra o teste. Endpoint agora responde 200.
2. **`GET /api/ia-governanca/provedores` → 403 para superadmin**. `_require_gestao` listava só `("admin","socio")`, barrando o papel mais alto da hierarquia exatamente na rota que o próprio CLAUDE.md aponta como fonte de verdade sobre provedores de IA. O gate irmão `_require_admin_socio` do mesmo arquivo já incluía superadmin. Auditoria de segurança dedicada: **aprovado** (raio de efeito = 1 rota; só telemetria agregada, sem segredos/PII; nenhum papel abaixo do conjunto anterior ganhou acesso). Teste com negados derivados de `ROLE_LEVEL`. Verificado ao vivo: 200.
3. **Frontend consumindo shims 308** — `Honorarios.tsx` (`/honorarios-exito/{id}/rateio`) e `Kanban.tsx` (`/kanban-columns`): round-trip extra por gravação e `Location` fora do contrato `/api/v1`. Reapontados para os canônicos `/honorarios-oab/{id}/rateio` e `/kanban/columns`. Shims permanecem no ar (remoção é decisão guiada por `/api/architecture/uso-rotas`).
4. **Metadados `/api/v1` residuais** — 2 `backendPrefixes` no `moduleRegistry.tsx` e 6 `backend_prefixes` no `module_registry.py` (o mesmo resíduo que induziu a auditoria de jul/2026 a erro), mais `frontend_route` de `radar-regulatorio` apontando para alias de `LEGACY_REDIRECTS` em violação da docstring do próprio arquivo. Normalizados, com guarda de teste nos dois lados (antes nenhum teste validava esse metadado).
5. **Harness E2E canônico envelhecido** (`qa/e2e/`):
   - Matriz RBAC derivada ignorava gate de router via `router.dependencies.append(...)` e import renomeado de gate compartilhado → divergência falsa em `/jurimetria/ext/stats` (dizia "permitido" onde o app corretamente nega 403). Parser corrigido + 2 regressões.
   - Dados fictícios rejeitados pela API atual: e-mail `@example.test` (TLD reservado, recusado pelo `EmailStr` de `ClientCreate`) derrubava a cadeia cliente→caso→documento; caso sem `proxima_acao` (hoje obrigatório para caso aberto).
   - 17 probes de módulo em rotas inexistentes com `404` no `expected` + 7 com `404` desnecessário: **24 probes reapontados** para endpoints reais (todos verificados por chamada autenticada antes de entrar na matriz) com expectativa apertada — portal passa a exigir `403` (prova que a rota existe E que o confinamento de papel funciona).
   - Releitura de documento usava `GET /documents/{id}`, rota que não existe (405): efeito agora conferido pela lista do caso; confirmação de cleanup pelo download (404 pós soft-delete).
6. **Harness de homologação com a mesma deriva** (`qa/homologacao/`): o runner gerava e-mail `@example.test` em runtime (422 antes do handler — 4 cenários FALHA: login negativo virava 422 em vez de 401, cliente/caso não criavam, idempotência nunca era exercitada) e a matriz sondava o inexistente `/api/datajud/health`. Corrigidos runner e matriz (caso ganha `proxima_acao`; probe de resiliência DataJud reapontado para `/api/movimentos/recentes`). Reexecução: **0 FALHA**.

## 5. Achados registrados SEM correção (propostas de Issue)

1. **Não existe `GET /api/documents/{doc_id}`** (detalhe de documento) — só list/download/patch/delete. Qualquer consumidor que queira reler um documento precisa filtrar a lista. Sugestão: criar o endpoint de detalhe (protegido, com `verificar_acesso_caso`), ou documentar a ausência como decisão.
2. **`/diagnostico` com chaves React duplicadas** (`infosimples`, `indices_bcb` — warning no console): a lista de integrações renderiza `key` só pelo nome, que se repete entre grupos. Cosmético; fix de uma linha (`key` composto) quando alguém tocar a página.
3. **DPT360 de cliente não-enquadrado**: `/dpt360/empresas/{clientId}` dispara `GET /dpt360/companies/{id}` e `GET /dpt360/diagnostics/readiness/{id}` que respondem 404 para cliente fora do programa — a página trata, mas o console registra os 404. Sugestão: estado vazio explícito ("cliente não acompanhado no DPT360") sem disparar as chamadas, ou 200 com `enquadrado:false`.
4. **Worker único + operação síncrona pesada**: durante a classificação de documento (extração de texto/OCR) o event loop bloqueia — um `GET /documents/` que responde em 17 ms ocioso estourou timeout de 30 s duas vezes sob essa carga. Em produção (worker único por premissa), um upload grande congela o sistema inteiro para todos os usuários. Sugestão: mover extração/OCR para `run_in_executor`/tarefa de fundo (o repo já tem Celery opcional).
5. **Probes RBAC com 422**: ~8 rotas GET exigem query obrigatória (`/calculadoras/inss`, `/jurisprudencia-externa/buscar`, `/triagem/ficha`, ...) — o 422 prova autorização mas não exercita o handler. Sugestão: matriz com query mínima válida por rota.
6. **Papel `cliente_externo` sem cobertura E2E** (sem credencial). O confinamento é testado indiretamente (403 no portal para staff), mas a experiência do portal do cliente não é exercitada ponta a ponta. Sugestão: conta fictícia de cliente externo + jornada do portal no harness.

## 6. Pendências conhecidas re-observadas (sem edição do status canônico)

O flip de status é da PR que corrige (regra do plano mestre) — aqui apenas *proponho reverificação* do que segue aberto em `docs/PLANO_MESTRE_STATUS.md` e que este pente fino tangenciou: `AUD27-P0-1` (kill-switch `AI_ENABLED` × `/ai/core/*`), `AUD27-P1-1` (RBAC antigo em `POST /cases/` — observação: a rota exige `proxima_acao` e funcionou no fluxo, mas o gate não foi re-auditado aqui), `V2-1.5` (rotas 404 do bloco V3-B1), IDOR de agenda/`responsavel_id`/`protocolo_comprovante_doc_id` (residuais do pente de 18/07). Nenhum deles foi reproduzido nem descartado nesta sessão; seguem valendo como estão no status canônico.

## 7. Sugestões de melhoria e críticas (priorizadas)

**Críticas estruturais** (custo alto, retorno alto — decisões do titular):

1. **O catálogo de módulos é triplo e diverge**: `MODULE_REGISTRY` backend (34), `STAFF_ROUTES` frontend (47) e `fictitious_matrix.json` (34) não são chaveados entre si — 10 chaves só no backend, 23 só no frontend. Enquanto não houver um teste de paridade (ou uma fonte única gerada), o "mapa de módulos" sempre poderá mentir. É a mesma classe de defeito que o enum de status atacado no V3-B1.
2. **~354 de 763 rotas backend sem nenhum consumidor no frontend.** Parte é legítima (portal, webhooks, API pública), mas é superfície de manutenção, auditoria e ataque. A telemetria `/api/architecture/uso-rotas` existe exatamente para isso: sugiro um ciclo trimestral de poda — 90 dias sem uso → deprecia (308/`Deprecation`) → remove. Os shims 308 de ago/2026 entram na primeira leva.
3. **QA que aceita falha não é QA**: o padrão `expected=[200, 404]` deixou 17 módulos "verdes" com rotas mortas por semanas. A regra que este PR adota (probe aponta para rota real, expectativa exata, guarda de teste sobre o metadado) deveria ser requisito para qualquer probe novo.

**Melhorias de fluxo/UX** (custo médio):

4. **Seed de demonstração**: não existe seed de clientes/casos fictícios — só admin e catálogos. Um `seeds/seed_demo.py` (flag dev-only) preencheria o sistema para treinamento/homologação e serviria ao critério de lançamento ("advogado leva um caso real do início ao protocolo").
5. **Jornada guiada pós-login**: a navegação mostrou o sistema íntegro, mas com 47 entradas de menu o caminho "cliente novo → caso → prazo → peça" exige conhecer o sistema. A Entrada Única (`/entrada`) já é a porta certa — sugiro medí-la via `/uso-rotas` e considerar aposentar entradas redundantes do menu (a consolidação 34→10 do parecer arquitetural continua sendo a direção certa).
6. **Playwright versionado**: a navegação desta sessão (login real + 89 rotas + captura de console) foi feita com script ad-hoc; o `qa/e2e/README.md` já aponta Playwright como próxima evolução. Versionar essa suíte fecharia o único elo que o harness HTTP não cobre (tela branca/erro de console).

**Higiene** (custo baixo):

7. `auditoria_e2e/` está obsoleto (README cita `run_audit.sh` inexistente, credenciais placeholder, caminhos de sandbox antiga `/home/ubuntu`) e é redundante com `qa/e2e` — arquivar ou remover.
8. Os 2 achados cosméticos do §5 (chaves React, estado vazio DPT360).

## 8. Dados fictícios e LGPD

Tudo criado com marcador `E2E-FICTICIO`/e-mails `*.teste@ejc.adv.br`; cleanup do harness confirmado pós-DELETE (releitura 404). Permanecem no ambiente local desta sessão (descartável): admin fictício, 4 contas por papel, 1 cliente/caso de navegação e resíduos declarados pelo próprio relatório do smoke (`checks_nao_cobertos` listados em `qa/e2e/reports/e2e_fictitious_report.json`). Nenhum dado real foi usado; nada disso toca produção.

---

## Adendo (30/08, mesma sessão) — melhorias EXECUTADAS por ordem do titular

O titular mandou aplicar e executar todas as melhorias. Status por item, no próprio PR [#1316](https://github.com/s2corporativo/ejc/pull/1316):

| Item | Status |
|---|---|
| §5.1 `GET /documents/{id}` ausente | ✅ Implementado (detalhe protegido, shape da listagem, testes) |
| §5.2 Chaves React duplicadas em /diagnostico | ✅ Corrigido (key composta; payload real repete chave até no mesmo grupo) |
| §5.3 Estado vazio DPT360 | ✅ Implementado (`ClienteNaoAcompanhado`, 404 vira estado de negócio) |
| §5.4 OCR síncrono bloqueando o event loop | ✅ Corrigido (`asyncio.to_thread` em `documento_service.extrair_e_analisar`) |
| §5.5 Probes RBAC com 422 | ✅ Mapa `QUERY_MINIMA_POR_ROTA` (9 rotas conclusivas; 422 vira reprovação) |
| §5.6 Cobertura `cliente_externo` | ✅ Conta de portal fictícia via fluxo canônico `criar-acesso`; confinamento provado (200 no portal, 403 fora, 401 anônimo); homologação com capacidade `portal`: 9 PASS/0 FALHA |
| §7.1 Paridade de catálogo 34×47 | ✅ Teste estático de paridade (rotas válidas, sem alias legado, drift declarado em allowlist) |
| §7.3 Padrão de probes fiéis | ✅ Já aplicado no corpo do PR |
| §7.4 Seed de demonstração | ✅ `seeds/seed_demo.py` dev-only, idempotente, PII cifrada, aborta em produção |
| §7.6 Playwright versionado | ✅ `frontend/tests/navegacao-registry.mjs` (84 rotas, provado ao vivo) |
| §7.7 `auditoria_e2e/` obsoleto | ✅ Arquivado em `docs/arquivo/auditoria_e2e/` com nota |
| §7.2 Poda das ~354 rotas sem consumidor | ⏸️ NÃO executada de propósito: exige janela de telemetria de produção (`/uso-rotas`, 90 dias) — poda cega seria destrutiva. Mecanismo e critério ficam propostos |
| §7.5 Consolidação de menu 34→10 | ⏸️ NÃO executada: decisão arquitetural do titular com plano próprio (parecer arquitetural / V3) |

Review do PR (Codex, 4×P1): probe DataJud → capacidade explícita `datajud`; cleanup por rodada na homologação (validado: zero resíduo); probe de sociedade reapontado para as APIs reais da rota; remoção deste relatório **declinada com fundamento** (laudo de auditoria ≠ relatório de entrega; precedente `docs/arquivo/relatorios/RELATORIO_PENTE_FINO_EJC_2026-07-18.md`).
