# Auditoria de consolidação total do EJC — 02/09/2026

> Baseline auditada: `main@802c8edd39dd30fc18a4396b6013ff3317fd0e15`.
>
> Finalidade: consolidar o EJC após as ondas recentes de alteração, sem confundir código escrito/mesclado com sistema homologado ou pronto para produção.

## 1. Veredito executivo

**NÃO APROVAR ainda o EJC como consolidado/pronto para uso pleno em produção.**

A limpeza estrutural pesada da árvore já ocorreu na `main` (remoção de shims 308, páginas legadas paralelas e milhares de linhas residuais), e existe uma arquitetura de navegação canônica. O bloqueio atual é de **integração e validação**, não de quantidade bruta de código legado.

Bloqueadores confirmados nesta rodada:

1. **P0 — CI canônico indisponível/vermelho:** `ci/woodpecker/push/woodpecker = failure` no SHA atual da `main`; a Issue #1295 permanece aberta. Sem execução real no SHA exato, nenhum PR estrutural deve ser chamado de aprovado.
2. **P0 — colisão Alembic de três migrations 156:** #1333 (`156_case_despesas_processuais`), #1345 (`156_prazos_auditaveis_regime`) e #1368 (`156_documentos_governanca_outbox`). Integração simultânea criaria heads concorrentes ou exigiria merge migration não planejada.
3. **P1 — inventário/matriz de rotas desatualizado:** `docs/MATRIZ_DE_ROTAS.md` foi gerado em 30/08/2026 sobre `9fe3642d`, antes da limpeza pesada e das alterações de 01–02/09. Deve ser regenerado na `main` consolidada.
4. **P1 — várias frentes funcionais ainda estão empilhadas fora da `main`:** Casos, Atividades/Prazos, Documentos, Peças, Financeiro e RAG ainda têm PRs canônicos abertos.
5. **P2 — taxonomia de áreas divergente:** a `main` tinha 24 áreas no fallback frontend e 25 no `CaseArea` backend; `licitacoes` faltava no fallback. Correção preparada nesta branch com teste de paridade integral.
6. **P2 — backlog canônico contém itens envelhecidos/falsos pendentes:** exemplos comprovados nesta rodada são `ia_cliente` e o antigo diagnóstico de callers `/v1/` duplicados.

## 2. Arquitetura canônica hoje

### 2.1 Frontend

A navegação central é declarativa em `frontend/src/config/moduleRegistry.tsx` e os destinos principais são definidos em `frontend/src/config/canonicalRoutes.ts`.

Rotas canônicas de primeiro nível registradas:

- `/` — Início;
- `/clientes` — Clientes;
- `/casos` — Casos;
- `/atividades` — Agenda, prazos, tarefas, intimações e suspensões;
- `/documentos` — Documentos;
- `/pecas` — Peças;
- `/inteligencia` — Pesquisa & IA;
- `/areas-de-atuacao` — Áreas de Atuação;
- `/financeiro` — Financeiro;
- `/configuracoes` — Configurações.

Redirecionamentos canônicos de compatibilidade:

- `/prazos` → `/atividades?tipo=prazo`;
- `/tarefas` → `/atividades?tipo=tarefa`;
- `/intimacoes` → `/atividades?tipo=intimacao`;
- `/suspensoes` → `/atividades?tipo=suspensao`;
- `/knowledge-hub` → `/inteligencia?tab=conhecimento`;
- `/ramos` → `/areas-de-atuacao`.

O `moduleRegistry` ainda registra rotas operacionais/avançadas como DPT Empresarial 360, Entrada Jurídica, CRM, Agenda, diagnóstico, ferramentas e subrotas ocultas, com metadados de roles, sensibilidade, uso de IA e prefixes backend.

### 2.2 Backend

O backend continua organizado por routers FastAPI e contratos de autorização. A auditoria não encontrou fundamento para uma nova reescrita de roteamento global; o risco maior está hoje no alinhamento entre branches e na ausência do CI executável.

A regra de consolidação permanece:

`router -> schema -> service -> model/database -> audit/log`

Mudanças de autorização não devem confiar apenas no frontend.

### 2.3 Banco/Alembic

A fila de migrations precisa ser serial. Há três PRs reservando o prefixo 156 sobre a mesma linha histórica:

| Frente | PR | Migration |
|---|---:|---|
| Casos/despesas processuais | #1333 | `156_case_despesas_processuais` |
| Atividades/Prazos/DJEN | #1345 | `156_prazos_auditaveis_regime` |
| Documentos/governança | #1368 | `156_documentos_governanca_outbox` |

Regra obrigatória: a primeira migration aprovada mantém o próximo número válido; as demais devem ser rebaseadas e renumeradas sequencialmente, com `down_revision`, ledger, single-head, upgrade/downgrade e drift revalidados.

### 2.4 IA/RAG

O desenho correto continua sendo RAG rastreável + revisão humana, não geração autônoma. PRs #1382/#1383 tratam resíduos de governança e aprovação jurídica explícita. A promoção dessas mudanças exige CI real e teste integrado com fonte/citação/HITL.

## 3. Mapa dos fluxos críticos ponta a ponta

### Fluxo A — acesso e autorização

`Login -> sessão/auth -> Dashboard -> rota protegida -> RBAC backend -> auditoria`

Gates obrigatórios:

- login e refresh;
- sessão expirada;
- rota permitida por papel;
- 403 backend quando papel não autorizado;
- ausência de dado sensível em logs;
- navegação direta por URL, não apenas clique de menu.

### Fluxo B — entrada, cliente e caso

`Entrada Jurídica -> localizar/criar cliente -> conflito -> criar caso -> ficha/dossiê -> workspace do caso`

A `main` já usa `/entrada` como porta canônica e mantém `/casos/novo` como compatibilidade oculta. A consolidação do workspace de Caso está concentrada no PR #1380, que substitui branches anteriores da mesma frente.

### Fluxo C — caso -> atividades/prazos

`Caso -> atividade/intimação -> prazo -> regime/contagem -> revisão -> agenda -> lembrete -> conclusão/auditoria`

A stack atual é serial e depende da reconciliação Alembic:

`#1343 -> #1344 -> #1345 -> #1346 -> #1347 -> #1371`.

Não promover filhos antes da migration base estar reconciliada.

### Fluxo D — caso -> documentos -> RAG

`Upload -> validação -> armazenamento -> extração/OCR quando aplicável -> metadados -> vínculo com cliente/caso -> indexação -> recuperação -> fonte/citação -> descarte/retensão/auditoria`

Stack atual:

`#1357 -> #1368 -> #1377 -> #1379`.

O #1368 é um dos três candidatos a 156 e bloqueia a promoção ordenada dos filhos.

### Fluxo E — caso -> peça

`Caso/ficha -> catálogo jurídico -> modo de produção -> pesquisa/fundamentos -> geração de minuta -> verificação de citações -> alertas/resíduos -> HITL -> aprovação humana -> documento`

PR canônico: #1376; #1384 é filho empilhado.

A #1376 já remove o fallback jurídico local de `PecaGeneratorModal` e bloqueia a geração se o catálogo canônico estiver indisponível, evitando taxonomia silenciosamente desatualizada.

### Fluxo F — financeiro

`Cliente/caso -> contrato/honorário -> cobrança/recebimento -> despesa -> conciliação/registro -> relatório/portal -> auditoria`

PR canônico: #1378, que substitui a frente anterior #1364. A migration de despesas processuais está em #1333 e participa da colisão 156.

### Fluxo G — portal do cliente

`Autenticação portal -> leitura de dados permitidos -> documentos/assinatura -> financeiro/comunicação -> auditoria`

A `main` de 02/09 já contém correção específica permitindo leitura antes da assinatura no fluxo afetado. Revalidar no E2E final com perfis reais/fictícios e sem extrapolar escopo RBAC.

### Fluxo H — administração/governança

`Usuário/configuração -> autorização administrativa -> alteração -> trilha de auditoria -> efeito nos módulos`

Inclui usuários, configurações, IA, auditoria, LGPD, diagnóstico e integrações. Mudanças de permissão devem ser tratadas com mínimo privilégio; #1381 é uma frente isolada de RBAC para análise bancária.

## 4. Ligações, rotas e links

### 4.1 Controles que já existem

Foram identificados no repositório controles específicos para impedir regressão de navegação/contrato:

- `frontend/src/config/moduleRegistry.test.ts`;
- `frontend/src/config/routeIntegrity.test.ts`;
- `frontend/src/config/internalLinks.test.ts`;
- `backend/tests/test_module_registry_paridade_frontend.py`;
- `frontend/tests/navegacao-registry.mjs`;
- `qa/e2e/rbac_matrix.py`;
- `frontend/src/lib/api.prefixo.test.ts`.

O teste de prefixo percorre `frontend/src` e exige que chamadas pelo cliente `api` não escrevam `/api/v1/`, `/api/` ou `/v1/` no path. O interceptor preserva essas formas apenas como compatibilidade transitória.

### 4.2 O que precisa ser refeito após a integração

1. regenerar `docs/MATRIZ_DE_ROTAS.md` no SHA consolidado;
2. comparar rotas backend x `backendPrefixes` x callers reais;
3. classificar cada divergência em: pública intencional, webhook/feed, administrativa, órfã real ou endpoint sem UI por desenho;
4. executar navegação registry para todas as rotas protegidas;
5. executar matriz RBAC por papel;
6. varrer links internos, botões, tabs, query strings e redirects legados;
7. validar 404/403/422/5xx e páginas vazias;
8. repetir após cada merge que altere superfície de rota.

## 5. Limpeza pesada — estado real

### Já consolidado

- remoção da grande onda de shims 308;
- consolidação de quatro páginas legadas paralelas;
- navegação declarativa central;
- redirects canônicos para áreas/atividades/conhecimento;
- guarda contra callers `api` com prefixo duplicado;
- `ia_cliente` está efetivamente roteada/renderizada por papel, portanto o backlog que a descreve como aba morta está envelhecido.

### Resíduos reais confirmados

1. **Taxonomia frontend/backend:** faltava `licitacoes` no fallback geral — corrigido nesta branch; teste ampliado para comparar integralmente `AREAS_FALLBACK` e `CaseArea`.
2. **Duplicação bancária em Áreas de Atuação:** `ramos_vitrine.py` ainda duplica `_LIMIARES_TAXA_MEDIA`, `_COMPARABILIDADE_REQUISITOS` e `_classificar_taxa_vs_media` que já existem em `ramos_comum.py`. Não remover sem teste focal dos endpoints bancários; consolidar em PR isolado depois do CI.
3. **Matriz de rotas antiga:** precisa ser regenerada, não editada manualmente.
4. **Backlog com status antigo:** sanear somente após prova no código/testes; não implementar novamente item já resolvido.
5. **PRs temporários/superados:** encerrar somente depois de confirmar sucessor e ausência de diff exclusivo. #1374 está explicitamente marcado como técnico/temporário e não deve ser mesclado.

### Não remover agora

- redirects legados canônicos enquanto houver links históricos/externos;
- interceptor transitório de prefixos antes da navegação/E2E final;
- componentes mantidos como parte de wrappers consolidados sem comprovar ausência de import;
- endpoints sem caller frontend quando forem API administrativa, feed, integração, webhook ou uso deliberadamente headless.

## 6. Dependências de integração

Frentes canônicas observadas nesta rodada:

| Domínio | PR/stack canônica | Observação |
|---|---|---|
| Casos | #1380 | substitui #1370/#1372; revalidar sobre `main` final |
| Atividades/Prazos | #1343 -> #1344 -> #1345 -> #1346 -> #1347 -> #1371 | migration 156 em #1345 |
| Documentos | #1357 -> #1368 -> #1377 -> #1379 | migration 156 em #1368 |
| Peças | #1376 -> #1384 | catálogo/HITL; sem promover filho antes do pai |
| Financeiro | #1333 + #1378 | migration 156 em #1333; #1378 substitui #1364 |
| RAG/governança | #1382/#1383 | exigir fonte/citação/HITL e CI real |
| RBAC análise bancária | #1381 | mínimo privilégio; isolada |
| CI | #1295 / infra correlata | bloqueador P0 externo ao código funcional |

## 7. Ordem segura de consolidação

### Fase 0 — congelar expansão estrutural

Até o baseline ficar verde, não abrir novas implementações paralelas para os mesmos módulos. Bugs críticos podem ser corrigidos em PR pequeno e isolado.

### Fase 1 — recuperar o CI P0

No ambiente do Woodpecker, preservar segredos/volumes e corrigir a relação server/agent sem destruir estado. Critério: jobs reais alocados e concluídos no SHA exato.

### Fase 2 — baseline da `main`

Executar, no mínimo:

- backend testes obrigatórios;
- frontend typecheck;
- Vitest;
- build;
- `scripts/ci-local.sh required`;
- single-head Alembic;
- `alembic current`/`upgrade head` em PostgreSQL de teste;
- route integrity/internal links;
- navegação registry;
- RBAC matrix.

### Fase 3 — reconciliar Alembic

Escolher a primeira migration 156 com base na prioridade operacional e prontidão do PR. Após cada merge:

1. rebase da próxima stack;
2. próximo prefixo livre;
3. corrigir `down_revision` e ledger;
4. single-head;
5. upgrade/downgrade;
6. drift/autogenerate;
7. testes do domínio.

### Fase 4 — integrar uma frente por vez

Depois de cada merge:

- rebase da próxima;
- executar gates novamente;
- não confiar no verde de SHA antigo;
- atualizar #909 e status canônico.

### Fase 5 — regenerar o mapa total

Somente com a árvore final:

- inventário de arquivos;
- matriz frontend/backend;
- rotas e redirects;
- módulos e dependências;
- migrations;
- variáveis de ambiente sem valores secretos;
- integrações;
- jobs/filas;
- índices/RAG;
- testes e cobertura operacional.

### Fase 6 — homologação funcional integrada

Executar casos fictícios ponta a ponta:

1. login por cada papel;
2. cliente novo e existente;
3. conflito de cliente/caso;
4. caso completo;
5. prazo/intimação;
6. documento e vínculo;
7. RAG com citação rastreável;
8. peça com HITL;
9. financeiro;
10. portal;
11. lixeira/restore quando aplicável;
12. auditoria e logs sem dado sensível.

### Fase 7 — staging/deploy controlado

Antes de produção:

- backup;
- `docker compose config`;
- build backend/frontend;
- migrations controladas;
- health/ready;
- smoke;
- logs;
- rollback documentado.

## 8. Segurança/LGPD

Gates obrigatórios para a consolidação:

- nenhum segredo em repositório/log;
- autenticação e RBAC no backend;
- menor privilégio;
- dados de cliente/caso apenas no escopo necessário;
- trilha de auditoria para ações jurídicas, documentais, financeiras e administrativas;
- RAG com origem da fonte;
- IA com revisão humana em decisão/peça/estratégia;
- nenhuma saída de IA tratada como prova ou parecer autônomo;
- logs sem CPF, senha, token, conteúdo integral sigiloso ou credenciais.

## 9. Rollback

- nenhuma alteração desta rodada deve ser aplicada diretamente em produção;
- cada frente permanece em branch/PR independente ou stack declarada;
- migration exige `downgrade` testado, salvo impossibilidade documentada;
- deploy usa SHA explícito;
- falha de health/ready ou smoke bloqueia promoção;
- reverter o PR específico é preferível a correção improvisada em produção.

## 10. Definition of Done — “EJC pronto para uso”

O EJC só pode ser marcado como consolidado quando todos os itens abaixo estiverem comprovados no SHA que será publicado:

- [ ] CI canônico executa e fica verde no SHA exato;
- [ ] backend inicia sem erro;
- [ ] frontend compila;
- [ ] single-head Alembic;
- [ ] migrations aplicam e têm rollback testado;
- [ ] matriz de rotas regenerada no SHA final;
- [ ] nenhuma rota órfã real P0/P1 sem decisão;
- [ ] links internos e redirects testados;
- [ ] navegação registry verde;
- [ ] matriz RBAC verde;
- [ ] endpoints críticos respondem sem 5xx;
- [ ] fluxos Cliente -> Caso -> Atividade -> Documento -> Peça -> Financeiro -> Portal testados;
- [ ] RAG com fonte/citação e fail-safe;
- [ ] revisão humana obrigatória preservada;
- [ ] logs sem dado sensível;
- [ ] banco sem drift;
- [ ] nenhum segredo versionado;
- [ ] backup e rollback comprovados;
- [ ] staging aprovado;
- [ ] health/ready pós-deploy verdes;
- [ ] smoke de produção aprovado;
- [ ] `docs/PLANO_MESTRE_STATUS.md` reconciliado com o código final.

## 11. Alterações feitas nesta branch de auditoria

1. `frontend/src/lib/areaCatalog.ts`: adicionada a área `licitacoes`, existente no `CaseArea` backend e ausente no fallback frontend.
2. `frontend/src/pages/ramos/taxonomiaAreas.test.ts`: adicionada trava de paridade integral entre `AREAS_FALLBACK` e `CaseArea`.
3. Este relatório de consolidação.

Nenhuma mudança de produção, migration, autenticação, RBAC ou dado foi aplicada nesta branch.
