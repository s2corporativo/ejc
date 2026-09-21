# Auditoria de itens parados, warnings e integração — EJC

**Data:** 21/09/2026
**Branch analisada:** `main`
**Commit de referência:** `58cfd5ad`
**Escopo:** pendências locais e do GitHub, backlog técnico formal, warnings da suíte, testes HTTP de endpoints e testes de integração dependentes de PostgreSQL.

## 1. Resumo executivo

A suíte unitária completa do backend está verde: **7.652 testes passaram, 457 foram pulados, 110 warnings foram registrados e 79 subtests passaram**. A suíte HTTP selecionada para saúde, rotas, contratos e smoke tests também está verde: **510 passaram e 2 foram pulados**, sem falhas de endpoint detectadas nessa camada.

A suíte DB-level, executada explicitamente com `RUN_DB_TESTS=1`, produziu **581 testes aprovados, 21 pulados, 350 falhas e 9 erros**. Essas falhas não constituem, neste ambiente, uma lista de 359 regressões independentes: a causa dominante foi `socket.gaierror: [Errno -2] Name or service not known`, porque o ambiente não possui Docker/PostgreSQL e o valor padrão de `DATABASE_URL` aponta para o hostname Docker `db`.

O GitHub contém **100 issues abertas** no recorte consultado, incluindo **12 P0, 22 P1, 12 P2, 14 de infraestrutura, 12 de segurança, 7 de RAG e apenas 1 marcada `em-andamento`**. Também existem **8 pull requests abertas**. O problema principal de governança não é somente código parado: é a ausência de um ciclo de reconciliação entre issues, PRs, backlog formal e evidências de execução.

## 2. Estado de trabalho local

O checkout não está limpo. Existem alterações locais iniciadas nesta sessão e ainda não publicadas:

| Estado | Arquivo | Destino recomendado |
|---|---|---|
| Modificado | `.woodpecker.yml` | manter em PR de CI, após revisão |
| Modificado | `backend/app/services/backup_service.py` | manter em PR de backup, após revisão operacional |
| Modificado | `backend/tests/test_backup_offsite.py` | manter junto do contrato de backup |
| Modificado | `backend/tests/test_backup_service.py` | manter junto do contrato de backup |
| Modificado | `docs/operacao/BACKUP_RUNTIME_RECOVERY_2026-08-17.md` | manter e atualizar no mesmo PR |
| Novo | `backend/tests/test_backup_offsite_contract.py` | manter; cobertura do manifesto/rclone |
| Novo | `scripts/tests/test_ai_architecture.py` | manter; gate contra bypass do AI Gateway |

**Ação:** não deixar esse conjunto indefinidamente no working tree. Criar uma branch/PR única de consolidação, executar Woodpecker, revisar a mudança de contrato do manifesto e então fazer merge; se a decisão for não entregar o backup/rclone agora, reverter os sete arquivos como um conjunto. Não fazer commit direto em `main` como mecanismo de arquivamento.

## 3. Pull requests abertas

| PR | Tema | Decisão planejada |
|---|---|---|
| #1784 | Consolidar métricas de jurimetria, teses, IC95 e histórico | **Manter** como PR principal; exigir testes estatísticos, migrações e contrato de interpretação antes do merge. |
| #1783 | Evidências de certificação, congelamento e sincronização do backlog | **Manter** se for o documento de reconciliação; após merge, atualizar issues duplicadas e fechar documentos superseded. |
| #1782 | Primeira cobertura do `/regulatorio` | **Manter e concluir**; o backlog registra o router como sem cobertura, portanto esta PR é diretamente necessária. |
| #1781 | Timeout nginx de IA para 300s | **Manter somente se** acompanhado de teste cronometrado e decisão explícita entre espera síncrona e job assíncrono. Não liberar aumento isolado de timeout sem limite de custo e observabilidade. |
| #1779 | Separar estatística real de prognóstico por IA | **Consolidar com #1784** se houver sobreposição; escolher uma PR canônica e fechar a outra como superseded. |
| #1778 | Roteamento Groq/Maritaca/Claude | **Manter**, mas exigir que o gateway canônico, a política de sigilo e a suíte de providers sejam os únicos caminhos de execução. |
| #1752 | PostgreSQL fase 2 | **Manter somente com ambiente DB-level verde**; caso a #1752 esteja superseded por commits posteriores, fechar com referência ao commit substituto. |
| #1751 | Hardening LGPD do RAG | **Manter e priorizar**; é dependência de segurança/escopo antes de ativação ampla do RAG. |

**Regra de fechamento:** nenhuma PR deve permanecer aberta sem um dos estados explícitos `pronta para merge`, `bloqueada por decisão/infraestrutura` ou `superseded por #N`. PR aberta sem próximo critério verificável deve virar issue de decisão ou ser fechada.

## 4. Backlog técnico formal — destino individual

A tabela abaixo reconcilia os 47 itens do arquivo `BACKLOG_LIMPEZA_2026-09-20.csv`. Itens já marcados como executados não devem continuar no backlog de implementação; devem ser encerrados após evidência e link para PR/commit.

| ID | Situação | Destino | Próximo passo objetivo |
|---|---|---|---|
| SEC-01 | Risco aceito | **Arquivar como decisão**, não excluir a evidência | Manter decisão do titular registrada; reabrir somente por novo pedido expresso. |
| SEC-02 | Executado | **Concluir/fechar** | Vincular evidência W5/PRs e remover da fila ativa. |
| SEC-03 | Não iniciado, P0 | **Concluir** | Implementar binding usuário↔arquivo em `trabalhista_liquidacao` e teste 403. |
| SEC-04 | Em execução | **Concluir** | Verificar PRs sucessoras #1732/#1737/#1735; fechar a issue após CI e merge das remanescentes. |
| SEC-05 | Executado | **Concluir/fechar** | Vincular os 7 testes de binding e remover da fila ativa. |
| OPS-01 | Executado | **Concluir/fechar** | Confirmar hit real do cache em tarefa segura; sem hit, abrir follow-up específico, não reabrir o item original. |
| OPS-02 | Não iniciado, P1 | **Concluir** | Unificar job DJEN ou comprovar deduplicação efetiva; adicionar telemetria de chamadas CNJ. |
| OPS-03 | Executado | **Concluir/fechar** | Registrar SSE como evolução separada, não como pendência deste item. |
| OPS-04 | Não iniciado, P1 | **Concluir** | Consolidar DataJud e mover cache/rate limit para Redis; executar dry-run de 48h. |
| OPS-05 | Executado | **Concluir/fechar** | Vincular testes de lote e retirar da fila ativa. |
| OPS-06 | Parcial | **Concluir** | Remover `_morning_brief`/`_alertar_honorarios` mortos ou documentar consumidores; não deixar “parcial” sem lista residual. |
| W8.2 | Não iniciado, P1 | **Concluir com decisão** | Escolher síncrono limitado ou job/polling; depois testar timeout real e custo. O PR #1781 só resolve o sintoma se houver limite operacional. |
| FE-01 | Não iniciado, P3 | **Excluir** | Confirmar 0 imports/rotas e remover página, redirect órfão e teste órfão em PR de limpeza. |
| FE-02 | Não iniciado, P3 | **Excluir** | Confirmar 0 consumidores e remover `DashboardAiChat.tsx`. |
| FE-03 | Não iniciado, P3 | **Excluir ou absorver** | Fazer busca de consumidores; se 0, excluir os 3 componentes e 3 testes; se houver função, absorver em Caso. |
| FE-04 | Executado | **Concluir/fechar** | Vincular PR #1754 e remover do backlog. |
| FE-05 | Não iniciado, P2 | **Concluir** | Lazy-load de `LoginModern`; validar login e bundle. Renomear somente se não quebrar telemetria/links. |
| FE-06 | Não iniciado, P2 | **Concluir** | Lazy-load de modais e `PortalLayout` com testes de carregamento. |
| FE-07 | Não iniciado, P2 | **Manter como decisão técnica** | Não fundir cegamente; preservar streaming raw-fetch e documentar por que não é duplicação simples. |
| FE-08 | Não iniciado, P2 | **Concluir** | Centralizar `GET /areas` em `lib/areas.ts` e migrar os 3 consumidores. |
| FE-09 | Executado | **Concluir/fechar** | Vincular PR #1764 e remover da fila. |
| FE-10 | Não iniciado, P2 | **Concluir** | Fundir os três módulos DPT360 sem alterar contratos públicos. |
| FE-11 | Não iniciado, P2 | **Concluir** | Migrar chamadas `/ai/*` para o service canônico; manter streaming onde necessário. |
| FE-12 | Não iniciado, P2 | **Consolidar** | Reduzir wrapper `GestaoDocumental` sem perder tabs/rotas. |
| FE-13 | Executado | **Concluir/fechar** | Vincular PR #1764 e retirar do backlog. |
| FE-14 | Não iniciado, P2 | **Consolidar** | Unificar `Sociedade`/`SociedadeWorkspace` após validar rota `/gestao-escritorio/sociedade`. |
| FE-15 | Não iniciado, P2 | **Excluir registro morto** | Remover componente não renderizado e corrigir comentário/redirect. |
| FE-16 | Não iniciado, P2 | **Decisão de produto** | Escolher RBAC, desativação ou absorção em Clientes; não implementar sem decisão. |
| BE-01 | Em execução, P2 | **Concluir** | Consolidar DataJud gradualmente, mantendo aliases por 90 dias e telemetria. |
| BE-02 | Em execução, P2 | **Concluir** | Finalizar consolidação dos routers de peças; preservar HITL, numeração e aliases. |
| BE-03 | Não iniciado, P2 | **Concluir** | Escolher família canônica de ingestão e migrar lexml/STJ/TJMG com testes. |
| BE-04 | Não iniciado, P1 | **Concluir primeiro** | Criar cobertura do router `/regulatorio`; PR #1782 é o candidato natural. |
| BE-05 | Não iniciado, P2 | **Concluir por matriz** | Classificar cada endpoint por papel; aplicar RBAC somente onde necessário e testar 401/403/200. |
| BE-06 | Não iniciado, P3 | **Excluir após prova** | Confirmar 0 consumidores e remover os 3 services e testes órfãos. |
| BE-07 | Não iniciado, P3 | **Investigar e decidir** | Dump/telemetria; somente depois criar migration de remoção ou ADR de retenção. |
| BE-08 | Não iniciado, P3 | **Arquivar com ADR ou ativar** | Como não há consumo runtime, decidir formalmente entre cutover e arquivamento. |
| BE-09 | Não iniciado, P3 | **Excluir após export** | Exportar dados, registrar retenção e remover `wiki_paginas`/código órfão somente após backup verificável. |
| BE-10 | Não iniciado, P2 | **Concluir** | Criar migrations/models para as 7 tabelas runtime; executar em staging e DB-level. |
| BE-11 | Não iniciado, P1 | **Concluir** | Medir plaintext legado; somente com contagem zero remover colunas e testar criptografia. |
| BE-12 | Não iniciado, P2 | **Consolidar** | Migrar leitura para `processo_service`, preservar compatibilidade e medir uso. |
| BE-13 | Não iniciado, P2 | **Concluir com reconciliação** | Backfill `fees`→`fee_payments`, conciliar valores e manter alias durante rollout. |
| BE-14 | Executado com flag de produção desligada | **Concluir operacionalmente** | Resolver W8.2, rodar eval/AILog diff e ativar `IA_MOTOR_CANONICO` somente após homologação. |
| BE-15 | Investigado | **Arquivar como veredito** | Manter `knowledge_docs` como canônico; fechar após runbook de dedup e evidência. |
| UI-01 | Não iniciado, P3 | **Excluir progressivamente** | Medir uso das 11 camadas e remover em waves com visual 375/768/1280. |
| UI-02 | Não iniciado, P3 | **Excluir após telemetria** | Aguardar 90 dias de `route_usage`; remover redirects sem uso e manter rollback documentado. |
| NAV-01 | Executado | **Concluir/fechar** | Vincular PR #1753 e evidência e2e. |
| LGPD-01 | Não iniciado, P1 | **Manter como controle recorrente** | Não é feature a “concluir”; criar checklist anual de ROPA/expurgo, evidência e owner. |

## 5. Issues abertas do GitHub — política de reconciliação

As 100 issues abertas não devem ser tratadas como uma única fila. Aplicar o seguinte destino:

| Grupo | Regra | Destino |
|---|---|---|
| P0 | Segurança, dados, CI ou governança que ainda têm risco reproduzível | **Manter e concluir primeiro**; cada item precisa de owner, PR, teste de aceitação e prazo. |
| P1 | Risco operacional/segurança relevante, mas sem bloqueio imediato | **Manter**, agrupando duplicatas por domínio e vinculando uma issue canônica. |
| P2 | Melhoria/consolidação | **Manter apenas se** houver owner e wave definida; os demais entram em backlog trimestral. |
| P3/chore/documentação | Limpeza ou decisão já superada | **Fechar/arquivar** com link para commit, PR, ADR ou item substituto. |
| `em-andamento` sem atividade | **Reclassificar** para `bloqueado`, `pronto` ou `não iniciado`; não deixar o rótulo representar apenas antiguidade. |
| Issue duplicada por PR ou wave executada | **Fechar como concluída/superseded** após evidência. |

### Issues prioritárias já identificadas no inventário

- **#1192:** runtime não-root; manter como iniciativa de infraestrutura própria, com janela e matriz de volumes/permissions.
- **#1187:** migration 145/drop de colunas; bloquear produção até a guarda de referência viva estar comprovada.
- **#1020:** cifragem streaming; manter como follow-up P1, porque o backup atual ainda cifra one-shot em memória.
- **#985:** governança RAG; manter P0 até todos os gates de revogação/autoaprovação/autoridade estarem cobertos por DB-level.
- **#988/#987:** operação e núcleo de IA; consolidar em uma roadmap única, evitando issues paralelas para provider, elegibilidade e ativação.
- **#1397/#1558/#1628:** CI e governança; consolidar em uma issue canônica de paridade Woodpecker/status required e fechar duplicatas.
- **#1351/#1353/#1354/#1356/#1360/#1361/#1362/#1363/#1369:** documentos; agrupar em uma wave GED com subitens, não oito filas independentes sem dependência explícita.
- **#1400/#1401/#1402/#1391/#1393/#1394/#1398/#1399:** segurança/LGPD; manter individualmente somente quando o teste de aceitação for distinto; caso contrário, consolidar em matriz de hardening.

## 6. Warnings não bloqueantes e correções recomendadas

| Warning | Causa | Correção recomendada | Prioridade |
|---|---|---|---|
| `StarletteDeprecationWarning`: `TestClient` com httpx | Incompatibilidade/depreciação na combinação FastAPI/Starlette/httpx | Avaliar a combinação suportada pelo FastAPI atual em venv limpo; atualizar `httpx`/Starlette conforme matriz oficial ou migrar testes para `httpx.AsyncClient`/transport ASGI. Não instalar `httpx2` sem validar compatibilidade e lock. | P1 técnico |
| `VAULT_MASTER_KEYS ausente` | Ambiente de testes gera chave Fernet efêmera | Definir uma chave exclusiva e determinística de teste antes dos imports da aplicação no `conftest.py`/CI; nunca reutilizar segredo de produção. Adicionar teste que falhe se a chave de produção entrar no ambiente de teste. | P1 segurança de teste |
| `PendingDeprecationWarning`: Sentry importa `multipart` | Caminho interno do Sentry ainda usa alias antigo; `python-multipart` está instalado | Atualizar Sentry SDK quando houver versão compatível; até lá, registrar como warning de dependência e evitar mascará-lo globalmente. | P2 dependência |
| FastEmbed: `multilingual-e5-large` mudou CLS para mean pooling | Mudança semântica do modelo/pooling altera embeddings e ordenação | Escolher formalmente mean pooling atual ou preservar CLS com versão/custom model. Registrar a decisão, fixar metadados de embedding e reindexar o corpus antes de mudar em produção; adicionar teste de dimensão/modelo/pooling. | P1 RAG |
| `SyntaxWarning` por escape inválido em docstring de `test_api_contract_extra.py` | Backslash em docstring não raw | Converter a docstring para `r"""..."""` ou escapar a barra; rodar `python -Wall -m py_compile` no CI. | P2 qualidade |
| `Sentry is attempting to send 4 pending events` ao fim do pytest | Eventos enviados durante testes; o processo aguarda flush/rede | Desabilitar DSN/env de Sentry nos testes unitários e configurar transporte no-op; manter um teste específico do wiring sem enviar eventos à rede. | P2 isolamento |
| 457 testes pulados | Gatilho `RUN_DB_TESTS`/`SCHEMA_CHECK_DATABASE_URL` sem banco vivo | Separar contagem `unit`, `http`, `db`; tornar o job DB obrigatório no Woodpecker, com serviço PostgreSQL pgvector, migrations e health check. Não contar skip como cobertura verde. | P0 CI |

## 7. Integração e endpoints

### 7.1 Testes HTTP sem banco

Comando executado:

```bash
pytest -q \
  tests/test_health.py \
  tests/test_routes_smoke.py \
  tests/test_smoke.py \
  tests/test_api_contract.py \
  tests/test_api_contract_extra.py \
  tests/test_api_rotas_depreciadas.py \
  tests/test_api_version_middleware.py \
  tests/test_auth_middleware_api_version.py \
  tests/test_fastapi_compat.py \
  tests/test_sala_raio_x_api_hardening.py \
  tests/test_whatsapp_router_runtime_gate.py
```

Resultado: **510 passed, 2 skipped, 6 warnings, exit code 0**. Não foram encontradas falhas nos endpoints cobertos por health, smoke, contratos de API, versionamento, compatibilidade, RBAC de middleware e gates dos routers incluídos.

### 7.2 Testes DB-level

Foram coletados **8.109 testes**, com **93 arquivos** referenciando `RUN_DB_TESTS`. A execução explícita foi:

```bash
RUN_DB_TESTS=1 pytest -q <arquivos que referenciam RUN_DB_TESTS>
```

Resultado: **581 passed, 21 skipped, 350 failed, 9 errors**.

A causa dominante é infraestrutura: o valor padrão de `DATABASE_URL` é `postgresql+asyncpg://ejc_user:ejc_pass@db:5432/ejc_db`, mas o sandbox não possui Docker, PostgreSQL ou resolução do hostname `db`. Portanto, os 350 failures não devem ser classificados como falhas de endpoint até a mesma seleção ser executada em um runner com PostgreSQL 16 + pgvector + migrations aplicadas.

### 7.3 Plano para fechar a integração

1. Provisionar job Woodpecker com PostgreSQL 16 + pgvector e health check.
2. Aplicar `alembic upgrade head` antes da suíte.
3. Executar primeiro migrations/schema e testes DB smoke.
4. Executar a seleção completa DB-level em paralelo controlado.
5. Separar no relatório `infra_error`, `test_failure`, `endpoint_failure` e `skip`.
6. Só abrir correções de endpoint após eliminar `socket.gaierror`/connection errors.
7. Repetir os testes de contrato HTTP contra o backend levantado, não apenas TestClient, incluindo `/api/health`, `/api/health/ready`, autenticação e rotas críticas.

## 8. Plano de execução por waves

### Wave 0 — desbloqueio e limpeza de estado

- Separar as alterações locais em PR de backup/CI.
- Fechar ou consolidar PRs duplicadas (#1779/#1784 e equivalentes).
- Provisionar DB-level no Woodpecker.
- Corrigir warnings de teste de baixo risco: docstring, chave de cofre de teste e Sentry no-op.
- Atualizar status das issues já executadas no backlog formal.

**Critério de saída:** working tree limpo em branch de trabalho, CI com unit + HTTP + DB jobs distinguíveis e nenhuma issue marcada `em-andamento` sem owner/próximo passo.

### Wave 1 — P0/P1 de segurança e dados

- SEC-03 e SEC-04.
- BE-04, BE-11.
- W8.2, #1187, #985 e PRs críticas relacionadas.
- Validar backup/restore antes de qualquer fusão destrutiva.

**Critério de saída:** RBAC/downloads cobertos, migrations perigosas guardadas, RAG governado e integração DB-level verde.

### Wave 2 — consolidação operacional

- OPS-02, OPS-04, OPS-06.
- BE-01, BE-02, BE-03, BE-10, BE-12, BE-13.
- Concluir o motor canônico de IA atrás de flag e registrar AILog/eval diff.

**Critério de saída:** uma fonte canônica por domínio, aliases temporários instrumentados, jobs sem duplicação e custo/latência medidos.

### Wave 3 — frontend e limpeza estrutural

- FE-01/02/03/05/06/08/10/11/12/14/15/16.
- UI-01/UI-02.
- BE-06/07/08/09/15.

**Critério de saída:** cada exclusão tem prova de zero consumidores, build/testes verdes e rollback documentado; nenhum código é removido somente por aparência de duplicidade.

### Wave 4 — reconciliação final

- Fechar issues executadas ou superseded.
- Atualizar backlog CSV e documentos de auditoria.
- Rodar unitária, HTTP, DB-level, migrations, frontend build e smoke real do serviço.
- Publicar uma matriz final de cobertura e riscos aceitos.

## 9. Decisões que não devem ser tomadas automaticamente

Não excluir tabelas, migrations, rotas, dados ou issues de segurança apenas porque parecem antigos. Exclusão definitiva exige evidência de zero consumidores, backup/restore verificável, owner e rollback. Riscos explicitamente aceitos pelo titular, como 2FA default desligado, devem ser arquivados como decisão — não reabertos indefinidamente como dívida de engenharia.

## 10. Conclusão

O código testável está saudável nas camadas unitária e HTTP simulada. O principal item realmente incompleto revelado pela execução é a **integração DB-level no ambiente correto**, não uma falha comprovada em 350 endpoints. O backlog contém itens executados que precisam ser fechados, itens parciais que precisam de critério residual e itens não iniciados que devem ser agrupados por waves. A prioridade imediata é restaurar o runner PostgreSQL/pgvector, reconciliar PRs/issues e corrigir os warnings de segurança e reprodutibilidade antes de iniciar novas consolidações.
