# M32 — Jurimetria e Analytics

**Status: HOMOLOGADO** — 33/33 cenários executáveis PASS (100%), 0 FAIL, 0 N/A-PROVADO
**Commit:** homologação de 16/08/2026
**Bateria:** `scripts/inventory/m32_jurimetria_analytics_tests.py` (33 cenários, execução real contra servidor local na porta 8000)
**Data de execução:** 16/08/2026

## 1. Objetivo (PROMPT 32)

Provar por execução real que a jurimetria e o analytics do EJC: declaram o critério de inclusão da amostra (casos encerrados/arquivados com resultado registrado); calculam taxas de êxito com tratamento explícito de divisão por zero; exigem amostra mínima (n=5) antes de reportar taxas como estatisticamente defensáveis, com flag `amostra_suficiente` e aviso indicativo; separam taxa de êxito total/parcial de taxa de êxito com acordo; expõem as agregações por área, comarca e advogado com recálculo replicável em SQL direto; e mantêm escopo por usuário, RBAC e fail-closed.

## 2. Superfícies testadas

| Superfície | O que provou |
| --- | --- |
| `/api/analytics/jurimetria` | Critério declarado (só encerrados/arquivados com resultado); n=0 → taxa None, sem divisão por zero; dimensão inválida rejeitada com 422; agregações por área/comarca/advogado ordenadas por n; escopo advogado restrito ao usuário; escopo sócio alinhado à base global (API n == banco n em todas as rodadas); cliente externo bloqueado (403/404) |
| Recálculo SQL direto | 5 casos sintéticos criados/encerrados via API; taxa de êxito recalculada no banco bateu com a API em 3 rodadas (n=5 → 60,0%; n=21 → 52,4% quando a base continha pré-existentes; n=5 → 60,0% em base limpa); agregação por área validada contra SQL no mesmo grupo (tributário n=5 taxa 60,0%) |
| Amostra mínima | Grupo sintético com n=3: `amostra_suficiente=false` e taxa mantida como indicativa (êxito 33,3%, êxito+acordo 66,7% — distinção declarada); com n=5 ou mais, o flag é removido corretamente |
| `/api/analytics/funil`, `taskscore`, `rentabilidade`, `case-health` | Respondem sem erro com base mínima; ranking com 14 casos; caso inexistente → 404 fail-closed sem stack trace |
| `/api/jurimetria/*` | overview com `taxa_sucesso_denominador` explícito (denominador declarado — anti-ilusão estatística); por-area, desfechos, interno/stats, interno/benchmarks, cobertura-rag (proveniência do corpus); `ext/predicao/provimento` (deprecated) responde com controle de amostra/aviso; `analise-prospectiva` rejeita com 422 sem amostra; cliente externo bloqueado |
| `/api/dashboard/` e relatório mensal | Dashboard com as chaves declaradas (casos, prazos, financeiro, ambiental_criticas, clientes_ativos, pecas_aguardando_revisao, degradado); PDF mensal de 124 KB gerado; cliente externo bloqueado na exportação |

## 3. Metodologia da prova de replicabilidade

Para os testes de agregação, a bateria não comparou a API com um número fixo (que dependeria de dados voláteis), mas replicou no banco a mesma seleção do endpoint — `cases` encerrados/arquivados, não deletados, com `resultado IS NOT NULL` — e comparou n e taxa entre API e SQL. A correspondência foi exata (diferença < 0,01 p.p.) em todas as rodadas, incluindo rodadas com base pré-existente (n=21) e base limpa (n=5).

## 4. Correções na bateria (não no sistema)

Nenhum defeito foi encontrado no sistema. As iterações da bateria corrigiram apenas a instrumentação de teste:

1. **Limpeza de dados QA:** o helper `pgsql()` (asyncpg com engine por event loop) não refletia o commit do `DELETE` nas leituras subsequentes da bateria, deixando casos sintéticos residuais que enviesavam contagens em rodadas seguintes. A limpeza foi transferida para conexão psycopg2 síncrona com **soft-delete** (`deleted_at`), FK-safe (a FK `case_movimentos_case_id_fkey` impede hard-delete) e verificação dupla do residual — residual 0 confirmado por rodada.
2. **Área isolada para o teste de amostra mínima:** áreas `tributario`/`civil` contêm dados de módulos anteriores; o teste passou a usar a área `ambiental` (sem encerrados pré-existentes, verificado por SELECT antes da criação), garantindo n=3 exato no grupo isolado.
3. **Escopo sócio:** a validação de escopo passou a comparar API × banco no mesmo recorte (n encerrados com resultado), provando a fonte de dados independentemente do rótulo de escopo.

## 5. Observações e ressalvas

- A rota `ext/predicao/provimento` permanece marcada como **deprecated** no código e responde com controle de amostra e aviso — comportamento observado e aceito (não é defeito, é legado em desativação). Recomenda-se remover na consolidação de módulos internos/externos.
- O painel `degradado` do dashboard é populado corretamente; em produção com IA habilitada, a verificação de degradação de cada provedor passa a refletir o estado real.
- Ressalva transversal da campanha: `AI_ENABLED=false` no sandbox — análises preditivas do endpoint `ext/predicao/provimento` com resposta real do LLM não foram executadas; o comportamento foi provado nas camadas determinísticas que antecedem o provedor.
- Dados sintéticos: `EJC_QA_M32B_*`/`EJC_QA_M32C_*`/`EJC_QA_M32D_*` em área, com títulos identificáveis — todos soft-deletados ao fim (residuais: 0).

## 6. Checklist final

- [x] Backend inicia sem erro
- [x] Bateria compila e roda
- [x] Endpoints respondem (HTTP real)
- [x] Escopo/RBAC validado (cliente externo 403/404 em todas as superfícies)
- [x] Logs sem dado sensível
- [x] Banco sem drift
- [x] Dados QA removidos (soft-delete, residual 0)
- [x] Divisão por zero tratada (taxa None, n=0)
- [x] Amostra mínima aplicada (n<5 → insuficiente)
- [x] Replicabilidade API×SQL comprovada
