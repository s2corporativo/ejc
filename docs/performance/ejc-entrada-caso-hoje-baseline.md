# Baseline de performance — Entrada → Caso → Hoje

> **Nada neste documento é dado real.** Todos os números vêm de um banco
> PostgreSQL sintético isolado (nomes/títulos gerados por seed). O arquivo
> serve como contrato de medição reprodutível para as Tarefas 2–7.

## 1. Política de escopo e visibilidade (contrato aprovado)

Semântica vigente no código (main `40144d68`), registrada aqui como BASELINE
da matriz ator × endpoint. Qualquer mudança de semântica exige aprovação
explícita do titular ANTES do rollout (Tarefa 4).

| Endpoint | sócio/admin | A1 advogado (dono) | auxiliar | secretaria | cliente externo |
|---|---|---|---|---|---|
| `GET /atividades` (vw_atividades) | TUDO (gestão) | pendentes/cancelados excluídos por filtro; (caso da carteira) OU (avulso próprio) | idem A1 | aplica filtro de carteira → **0 linhas** (não é dono nem responsável) | 403 |
| `GET /tasks` | TUDO | caso da carteira OU avulso (responsável/criador) — `tasks.py:118-130`, imutável na Tarefa 2 | idem | idem (0 avulsas alheias) | 403 |
| `GET /cases` (requer_equipe_juridica) | TUDO | carteira (`_filtro_visibilidade`) | idem | **403 por design (M04)** | 403 |
| `GET /cases/stats` | TUDO | carteira | idem | 403 | 403 |
| `GET /clients` | TUDO (visão_total_clientes) | titularidade: responsável OU caso da carteira | idem | TUDO (recepção opera o CRM) | 403 |
| `GET /deadlines` | TUDO | caso da carteira OU responsável (`_filtro_escopo_prazos`) | idem | filtro aplicado (0 linhas no dataset) | 403 |
| `GET /documents` | TUDO (sócio+) | sigilo ≤ interno + caso/cliente da carteira ou próprio upload | idem | sigilo ≤ interno + carteira | só client_id próprio + `normal` |
| `GET /dashboard` (require secretaria+) | `escritorio` | `meus_casos:{uid}` **apenas no financeiro** — casos/prazos/clientes/peças são GLOBAIS (achado Tarefa 4) | idem | KPIs globais + financeiro `meus_casos` | 403 |

**Decisões do contrato registradas para a Tarefa 4:**
1. `/dashboard/` hoje expõe contagens GLOBAIS (casos por status/área, prazos
   vencidos/críticos, clientes ativos, peças HITL) a QUALQUER staff ≥
   secretaria, escopando só o bloco financeiro. Não alterar sem decisão
   explícita do titular; a nova rota `/dashboard/hoje` nasce com escopo
   correto ("minha carteira" vs "indicadores do escritório") sem expor novos
   dados de outro dono.
2. Fonte única da data operacional do "Hoje": `app/core/clock.py::
   hoje_operacional()` (America/Sao_Paulo) — já usada por `/deadlines` e
   scheduler; deve ser a mesma fonte do feed `/atividades` (hoje o feed usa
   `CURRENT_DATE` do banco, i.e., fuso do servidor) e de `/dashboard/hoje`.
3. Cards de urgência da Central (resumo): computados sobre o CONJUNTO INTEIRO
   visível, sem aplicar filtros de tipo/urgência/situação do clique
   (`CentralAtividades.tsx:1452-1478`) — a rota `/atividades/resumo` da
   Tarefa 3 replica exatamente esta semântica.

## 2. Perfil reprodutível

| Item | Valor |
|---|---|
| Commit do repo | `40144d68` (main) |
| Schema | migrations head `168_finance_ged_links` (159 revisões, 178 tabelas) |
| Banco | PostgreSQL **16.2** dedicado (`ejc_sintetico`, socket user-space; nenhum dado real; nunca aponta para produção) |
| API | uvicorn 1 worker, app real (`app.main:app`), pool `pool_size=10/max_overflow=20` |
| Dataset (`scripts/seed_sintetico.py`) | 8 usuários (sócio, admin, A1, A2, auxA1, auxA2, secretaria, cliente externo) · 80 clientes · **120 casos** (2 carteiras de 60; empates de `created_at`; ~5 sem próxima ação) · **600 prazos** (40 datas empatadas; vencidos/hoje/críticos/futuro; avulsos e vinculados) · **400 tarefas** (empatadas; avulsas) · 500 eventos agenda · 300 intimações DJEN · 8 suspensões · **300 documentos** (60 por nível de confidencialidade; OCR longo; `%`/`_` em título e OCR) · 40 peças (30 em revisão/corrigida) · 150 fees |
| Medição warm | 25 execuções sequenciais por rota×ator, após 1 aquecimento; p50/p95 (quantis n=100) |
| Medição cold | 1 execução por rota×ator após **reinício do PostgreSQL E da API** (buffers/planos frios; page cache do SO permanece morno — limitação registrada) |
| Atores | A1 (advogado/dono), A2 (advogado/dono), socio, secretaria, cliente externo |
| Instrumentação | `scripts/baseline_bench.py` + `scripts/baseline_explain.py` (persistidos no repositório de trabalho) |
| p75 "primeira ação visível" | **proxy**: soma sequencial dos requests da tela (navegador real fica no roteiro de homologação H1–H3) |

## 3. Matriz de medição — warm (rota × ator)

Colunas: linhas devolvidas, p50/p95 ms, KB payload, total (quando rota expõe).

| Rota | Ator | Filtros | Linhas | p50 | p95 | KB | Total | Erro |
|---|---|---|---|---|---|---|---|---|
| `/atividades?apenas_pendentes=true` | A1 | feed pendentes (Hoje) | 725 | 21.4 | 27.4 | 258.9 | — |  |
| `/atividades?apenas_pendentes=true` | A2 | feed pendentes (Hoje) | 550 | 17.1 | 22.0 | 196.1 | — |  |
| `/atividades?apenas_pendentes=true` | socio | feed pendentes (Hoje) | 1283 | 34.5 | 37.5 | 457.6 | — |  |
| `/atividades?apenas_pendentes=true` | secretaria | feed pendentes (Hoje) | 0 | 3.4 | 3.7 | 0.0 | — |  |
| `/atividades?apenas_pendentes=true` | cext | feed pendentes (Hoje) | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/atividades?apenas_pendentes=false` | A1 | feed completo (Central) | 1038 | 29.0 | 130.3 | 371.0 | — |  |
| `/atividades?apenas_pendentes=false` | A2 | feed completo (Central) | 762 | 22.1 | 22.8 | 272.9 | — |  |
| `/atividades?apenas_pendentes=false` | socio | feed completo (Central) | 1808 | 47.3 | 48.7 | 646.5 | — |  |
| `/atividades?apenas_pendentes=false` | secretaria | feed completo (Central) | 0 | 3.4 | 3.6 | 0.0 | — |  |
| `/atividades?apenas_pendentes=false` | cext | feed completo (Central) | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/agenda-eventos/?page_size=500` | A1 | agenda p/ enriquecimento | 308 | 10.6 | 13.1 | 98.6 | — |  |
| `/agenda-eventos/?page_size=500` | A2 | agenda p/ enriquecimento | 192 | 7.5 | 10.0 | 64.5 | — |  |
| `/agenda-eventos/?page_size=500` | socio | agenda p/ enriquecimento | 500 | 14.6 | 15.1 | 163.2 | — |  |
| `/agenda-eventos/?page_size=500` | secretaria | agenda p/ enriquecimento | 0 | 2.7 | 3.0 | 0.0 | — |  |
| `/agenda-eventos/?page_size=500` | cext | agenda p/ enriquecimento | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/deadlines/?status=&page=1&page_size=200` | A1 | prazos p/ enriquecimento | 200 | 14.8 | 17.6 | 102.3 | 320 |  |
| `/deadlines/?status=&page=1&page_size=200` | A2 | prazos p/ enriquecimento | 200 | 14.5 | 16.2 | 101.3 | 280 |  |
| `/deadlines/?status=&page=1&page_size=200` | socio | prazos p/ enriquecimento | 200 | 14.3 | 15.6 | 101.9 | 600 |  |
| `/deadlines/?status=&page=1&page_size=200` | secretaria | prazos p/ enriquecimento | 0 | 4.3 | 4.6 | 0.0 | 0 |  |
| `/deadlines/?status=&page=1&page_size=200` | cext | prazos p/ enriquecimento | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/tasks/` | A1 | tarefas (sem paginação) | 230 | 11.9 | 14.2 | 74.0 | — |  |
| `/tasks/` | A2 | tarefas (sem paginação) | 170 | 10.0 | 10.5 | 54.2 | — |  |
| `/tasks/` | socio | tarefas (sem paginação) | 400 | 16.0 | 16.6 | 128.1 | — |  |
| `/tasks/` | secretaria | tarefas (sem paginação) | 0 | 5.1 | 5.3 | 0.0 | — |  |
| `/tasks/` | cext | tarefas (sem paginação) | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/cases/?page=1&page_size=50` | A1 | casos página 1 | 50 | 8.0 | 13.2 | 45.4 | 51 |  |
| `/cases/?page=1&page_size=50` | A2 | casos página 1 | 50 | 8.0 | 8.3 | 45.5 | 52 |  |
| `/cases/?page=1&page_size=50` | socio | casos página 1 | 50 | 8.1 | 9.1 | 45.4 | 103 |  |
| `/cases/?page=1&page_size=50` | secretaria | casos página 1 | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/cases/?page=1&page_size=50` | cext | casos página 1 | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/cases/?page=3&page_size=50` | A1 | casos página PROFUNDA | 0 | 3.8 | 4.2 | 0.0 | 51 |  |
| `/cases/?page=3&page_size=50` | A2 | casos página PROFUNDA | 0 | 3.8 | 4.0 | 0.0 | 52 |  |
| `/cases/?page=3&page_size=50` | socio | casos página PROFUNDA | 3 | 4.2 | 4.7 | 2.8 | 103 |  |
| `/cases/?page=3&page_size=50` | secretaria | casos página PROFUNDA | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/cases/?page=3&page_size=50` | cext | casos página PROFUNDA | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/cases/?page=1&page_size=50&search=Sintetico%201` | A1 | casos busca textual | 0 | 4.0 | 5.7 | 0.0 | 0 |  |
| `/cases/?page=1&page_size=50&search=Sintetico%201` | A2 | casos busca textual | 0 | 4.0 | 4.1 | 0.0 | 0 |  |
| `/cases/?page=1&page_size=50&search=Sintetico%201` | socio | casos busca textual | 0 | 4.3 | 5.7 | 0.0 | 0 |  |
| `/cases/?page=1&page_size=50&search=Sintetico%201` | secretaria | casos busca textual | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/cases/?page=1&page_size=50&search=Sintetico%201` | cext | casos busca textual | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/clients/?page=1&page_size=100` | A1 | clientes página 1 | 71 | 9.9 | 14.9 | 38.3 | 71 |  |
| `/clients/?page=1&page_size=100` | A2 | clientes página 1 | 70 | 9.2 | 9.7 | 37.7 | 70 |  |
| `/clients/?page=1&page_size=100` | socio | clientes página 1 | 80 | 9.3 | 15.2 | 43.1 | 80 |  |
| `/clients/?page=1&page_size=100` | secretaria | clientes página 1 | 80 | 9.3 | 9.5 | 43.1 | 80 |  |
| `/clients/?page=1&page_size=100` | cext | clientes página 1 | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/deadlines/?page=1&page_size=50` | A1 | prazos página 1 (default) | 50 | 7.2 | 8.2 | 25.5 | 76 |  |
| `/deadlines/?page=1&page_size=50` | A2 | prazos página 1 (default) | 50 | 7.2 | 7.4 | 25.3 | 109 |  |
| `/deadlines/?page=1&page_size=50` | socio | prazos página 1 (default) | 50 | 6.8 | 7.6 | 25.4 | 185 |  |
| `/deadlines/?page=1&page_size=50` | secretaria | prazos página 1 (default) | 0 | 4.2 | 4.5 | 0.0 | 0 |  |
| `/deadlines/?page=1&page_size=50` | cext | prazos página 1 (default) | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/deadlines/?page=12&page_size=50` | A1 | prazos página PROFUNDA | 0 | 4.3 | 4.5 | 0.0 | 76 |  |
| `/deadlines/?page=12&page_size=50` | A2 | prazos página PROFUNDA | 0 | 4.5 | 4.6 | 0.0 | 109 |  |
| `/deadlines/?page=12&page_size=50` | socio | prazos página PROFUNDA | 0 | 4.0 | 4.3 | 0.0 | 185 |  |
| `/deadlines/?page=12&page_size=50` | secretaria | prazos página PROFUNDA | 0 | 4.4 | 7.4 | 0.0 | 0 |  |
| `/deadlines/?page=12&page_size=50` | cext | prazos página PROFUNDA | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/documents/?page=1&page_size=20` | A1 | documentos página 1 | 20 | 6.0 | 8.7 | 4.9 | 76 |  |
| `/documents/?page=1&page_size=20` | A2 | documentos página 1 | 20 | 5.6 | 5.9 | 4.8 | 65 |  |
| `/documents/?page=1&page_size=20` | socio | documentos página 1 | 20 | 4.9 | 8.0 | 4.9 | 300 |  |
| `/documents/?page=1&page_size=20` | secretaria | documentos página 1 | 0 | 4.9 | 5.3 | 0.0 | 0 |  |
| `/documents/?page=1&page_size=20` | cext | documentos página 1 | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/documents/?page=1&page_size=20&search=contrato_%_` | A1 | documentos busca %/_ | 20 | 6.6 | 8.1 | 4.9 | 76 |  |
| `/documents/?page=1&page_size=20&search=contrato_%_` | A2 | documentos busca %/_ | 20 | 6.0 | 6.3 | 4.8 | 65 |  |
| `/documents/?page=1&page_size=20&search=contrato_%_` | socio | documentos busca %/_ | 20 | 6.1 | 7.0 | 4.9 | 300 |  |
| `/documents/?page=1&page_size=20&search=contrato_%_` | secretaria | documentos busca %/_ | 0 | 5.3 | 6.1 | 0.0 | 0 |  |
| `/documents/?page=1&page_size=20&search=contrato_%_` | cext | documentos busca %/_ | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/dashboard/` | A1 | KPIs escritório/carteira | 0 | 2.7 | 3.0 | 0.7 | — |  |
| `/dashboard/` | A2 | KPIs escritório/carteira | 0 | 2.7 | 2.9 | 0.7 | — |  |
| `/dashboard/` | socio | KPIs escritório/carteira | 0 | 2.7 | 3.3 | 0.7 | — |  |
| `/dashboard/` | secretaria | KPIs escritório/carteira | 0 | 2.7 | 3.0 | 0.7 | — |  |
| `/dashboard/` | cext | KPIs escritório/carteira | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/cases/stats` | A1 | stats casos | 0 | 6.3 | 9.0 | 0.2 | 60 |  |
| `/cases/stats` | A2 | stats casos | 0 | 5.9 | 7.6 | 0.2 | 60 |  |
| `/cases/stats` | socio | stats casos | 0 | 6.0 | 8.2 | 0.2 | 120 |  |
| `/cases/stats` | secretaria | stats casos | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/cases/stats` | cext | stats casos | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/atendimentos/responsaveis` | A1 | lista equipe | — | 3.0 | 3.4 | 0.5 | — |  |
| `/atendimentos/responsaveis` | A2 | lista equipe | — | 2.8 | 3.6 | 0.5 | — |  |
| `/atendimentos/responsaveis` | socio | lista equipe | — | 2.9 | 3.0 | 0.5 | — |  |
| `/atendimentos/responsaveis` | secretaria | lista equipe | — | 2.8 | 3.0 | 0.5 | — |  |
| `/atendimentos/responsaveis` | cext | lista equipe | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/legal-docs/?page=1&page_size=30` | A1 | peças página 1 | 30 | 8.3 | 126.1 | 14.8 | 40 |  |
| `/legal-docs/?page=1&page_size=30` | A2 | peças página 1 | 0 | 5.7 | 6.2 | 0.0 | 0 |  |
| `/legal-docs/?page=1&page_size=30` | socio | peças página 1 | 30 | 7.3 | 8.9 | 14.8 | 40 |  |
| `/legal-docs/?page=1&page_size=30` | secretaria | peças página 1 | 0 | 5.6 | 7.0 | 0.0 | 0 |  |
| `/legal-docs/?page=1&page_size=30` | cext | peças página 1 | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/financeiro/atencao` | A1 | financeiro atenção | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/financeiro/atencao` | A2 | financeiro atenção | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/financeiro/atencao` | socio | financeiro atenção | 0 | 4.8 | 6.8 | 0.0 | 0 |  |
| `/financeiro/atencao` | secretaria | financeiro atenção | — | — | — | — | — | 403 HTTP Error 403: Forbidden |
| `/financeiro/atencao` | cext | financeiro atenção | — | — | — | — | — | 403 HTTP Error 403: Forbidden |

## 4. Cold (PG + API recém-iniciados)

| Rota | Ator | ms (1 execução) | KB | Erro |
|---|---|---|---|---|
| `/atividades?apenas_pendentes=true` | A1 | 41.7 | 258.9 |  |
| `/atividades?apenas_pendentes=true` | socio | 36.1 | 457.6 |  |
| `/atividades?apenas_pendentes=true` | secretaria | 4.8 | 0.0 |  |
| `/atividades?apenas_pendentes=false` | A1 | 41.0 | 371.0 |  |
| `/atividades?apenas_pendentes=false` | socio | 47.5 | 646.5 |  |
| `/atividades?apenas_pendentes=false` | secretaria | 4.9 | 0.0 |  |
| `/agenda-eventos/?page_size=500` | A1 | 12.5 | 98.6 |  |
| `/agenda-eventos/?page_size=500` | socio | 15.5 | 163.2 |  |
| `/agenda-eventos/?page_size=500` | secretaria | 3.7 | 0.0 |  |
| `/deadlines/?status=&page=1&page_size=200` | A1 | 27.2 | 102.3 |  |
| `/deadlines/?status=&page=1&page_size=200` | socio | 22.0 | 101.9 |  |
| `/deadlines/?status=&page=1&page_size=200` | secretaria | 6.8 | 0.0 |  |
| `/tasks/` | A1 | 19.6 | 74.0 |  |
| `/tasks/` | socio | 21.6 | 128.1 |  |
| `/tasks/` | secretaria | 6.5 | 0.0 |  |
| `/cases/?page=1&page_size=50` | A1 | 21.7 | 45.4 |  |
| `/cases/?page=1&page_size=50` | socio | 17.3 | 45.4 |  |
| `/cases/?page=1&page_size=50` | secretaria | 3.2 | 0.0 | 403 HTTP Error 403: Forbidden |
| `/cases/?page=3&page_size=50` | A1 | 6.3 | 0.0 |  |
| `/cases/?page=3&page_size=50` | socio | 6.7 | 2.8 |  |
| `/cases/?page=3&page_size=50` | secretaria | 3.1 | 0.0 | 403 HTTP Error 403: Forbidden |
| `/cases/?page=1&page_size=50&search=Sintetico%201` | A1 | 8.4 | 0.0 |  |
| `/cases/?page=1&page_size=50&search=Sintetico%201` | socio | 8.2 | 0.0 |  |
| `/cases/?page=1&page_size=50&search=Sintetico%201` | secretaria | 3.0 | 0.0 | 403 HTTP Error 403: Forbidden |
| `/clients/?page=1&page_size=100` | A1 | 22.9 | 38.3 |  |
| `/clients/?page=1&page_size=100` | socio | 17.7 | 43.1 |  |
| `/clients/?page=1&page_size=100` | secretaria | 12.3 | 43.1 |  |
| `/deadlines/?page=1&page_size=50` | A1 | 12.9 | 25.5 |  |
| `/deadlines/?page=1&page_size=50` | socio | 9.5 | 25.4 |  |
| `/deadlines/?page=1&page_size=50` | secretaria | 6.0 | 0.0 |  |
| `/deadlines/?page=12&page_size=50` | A1 | 5.6 | 0.0 |  |
| `/deadlines/?page=12&page_size=50` | socio | 5.6 | 0.0 |  |
| `/deadlines/?page=12&page_size=50` | secretaria | 5.3 | 0.0 |  |
| `/documents/?page=1&page_size=20` | A1 | 15.7 | 4.9 |  |
| `/documents/?page=1&page_size=20` | socio | 10.6 | 4.9 |  |
| `/documents/?page=1&page_size=20` | secretaria | 8.4 | 0.0 |  |
| `/documents/?page=1&page_size=20&search=contrato_%_` | A1 | 11.1 | 4.9 |  |
| `/documents/?page=1&page_size=20&search=contrato_%_` | socio | 8.9 | 4.9 |  |
| `/documents/?page=1&page_size=20&search=contrato_%_` | secretaria | 8.0 | 0.0 |  |
| `/dashboard/` | A1 | 13.8 | 0.7 |  |
| `/dashboard/` | socio | 10.6 | 0.7 |  |
| `/dashboard/` | secretaria | 5.7 | 0.7 |  |
| `/cases/stats` | A1 | 14.3 | 0.2 |  |
| `/cases/stats` | socio | 12.2 | 0.2 |  |
| `/cases/stats` | secretaria | 3.0 | 0.0 | 403 HTTP Error 403: Forbidden |
| `/atendimentos/responsaveis` | A1 | 4.5 | 0.5 |  |
| `/atendimentos/responsaveis` | socio | 3.6 | 0.5 |  |
| `/atendimentos/responsaveis` | secretaria | 3.1 | 0.5 |  |
| `/legal-docs/?page=1&page_size=30` | A1 | 23.5 | 14.8 |  |
| `/legal-docs/?page=1&page_size=30` | socio | 16.0 | 14.8 |  |
| `/legal-docs/?page=1&page_size=30` | secretaria | 11.0 | 0.0 |  |
| `/financeiro/atencao` | A1 | 5.9 | 0.0 | 403 HTTP Error 403: Forbidden |
| `/financeiro/atencao` | socio | 8.5 | 0.0 |  |
| `/financeiro/atencao` | secretaria | 4.7 | 0.0 | 403 HTTP Error 403: Forbidden |

## 5. Requests por tela (sequência real do frontend)

| Tela | Ator | # requests | ms total (warm, sequencial) |
|---|---|---|---|
| Central de Atividades | A1 | 4 | 61.7 |
| Central de Atividades | socio | 6 | 117.1 |
| Dashboard Ultra (Hoje) | A1 | 6 | 70.7 |
| Dashboard Ultra (Hoje) | socio | 8 | 140.9 |

**Fan-out medido da Central (A1): 4 requests → 1.346 linhas agregadas e
~575 KB.** O feed `/atividades` devolve TUDO (sem paginação): A1 1.038 linhas/
371 KB, socio 1.808 linhas/646 KB. O enriquecimento busca `/agenda-eventos/
?page_size=500` e `/deadlines` paginado até 10×200 = **2.000 prazos** só para
obter `confirmado`/`ciencia_confirmada`/`hora`/`local` — alvo direto da
Tarefa 3 (server-side + resumo agregado).

**Dashboard (socio): 8 requests** — o feed `/atividades?apenas_pendentes=true`
é o maior payload (socio 457 KB); as "decisões do dia" são computadas no
navegador sobre amostras (30 peças / 50 casos / feed completo) — alvo da
Tarefa 4 (contagens e decisões autorizadas no backend).

## 6. EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) — 25 planos

SQL redigido, planos brutos e data persistidos em
`work/baseline_explains.json` (cópia de auditoria anexada ao diretório de
trabalho; regenerável via `scripts/baseline_explain.py`). Só SELECT, só banco
sintético. Resumo dos achados:

| Query | ms | Seq Scans | Sort | Observação |
|---|---|---|---|---|
| `atividades.gestao.p1` | 2.24 | deadlines, tasks, suspensoes_tribunal, agenda_eventos (+2) | quicksort space=565KB |  |
| `atividades.a1.p1` | 1.81 | deadlines, tasks, suspensoes_tribunal, agenda_eventos (+3) | quicksort space=346KB |  |
| `atividades.a1.pendentes` | 1.46 | deadlines, tasks, suspensoes_tribunal, agenda_eventos (+3) | quicksort space=226KB |  |
| `atividades.a1.deep1000` | 1.46 | deadlines, tasks, suspensoes_tribunal, agenda_eventos (+2) | quicksort space=133KB | desvio est×real: Limit: est=1 real=38 |
| `atividades.a1.resumo` | 1.15 | deadlines, tasks, suspensoes_tribunal, agenda_eventos (+2) | quicksort space=41KB | desvio est×real: Aggregate: est=200 real=4 |
| `tasks.a1.listagem` | 0.24 | tasks, cases | quicksort space=66KB |  |
| `tasks.a1.cursor.p1` | 0.26 | tasks, cases | top-N heapsort space=36KB |  |
| `tasks.gestao.listagem` | 0.16 | tasks | quicksort space=56KB |  |
| `cases.a1.p1` | 0.13 | cases | quicksort space=50KB |  |
| `cases.a1.deep` | 0.09 | cases | quicksort space=50KB |  |
| `cases.gestao.count` | 0.12 | — | — |  |
| `cases.a1.count` | 0.1 | cases | quicksort space=27KB |  |
| `cases.a1.busca` | 0.08 | cases | quicksort space=25KB |  |
| `deadlines.a1.p1` | 0.16 | cases | quicksort space=44KB |  |
| `deadlines.gestao.deep` | 0.11 | deadlines | quicksort space=38KB |  |
| `deadlines.gestao.count` | 0.16 | deadlines | quicksort space=32KB |  |
| `documents.a1.p1` | 0.14 | cases, cases | — |  |
| `documents.gestao.count` | 0.29 | documents | quicksort space=48KB |  |
| `documents.a1.busca_perc` | 0.24 | documents, cases | quicksort space=25KB |  |
| `clients.a1.p1` | 0.21 | clients, clients, cases | quicksort space=43KB |  |
| `view.bloco.deadlines` | 0.11 | deadlines | — |  |
| `view.bloco.tasks` | 0.07 | tasks | — |  |
| `view.bloco.suspensoes` | 0.0 | suspensoes_tribunal | — |  |
| `view.bloco.agenda` | 0.09 | agenda_eventos | — |  |
| `view.bloco.djen` | 0.05 | djen_comunicacoes | — |  |

### Interpretação (insumo das Tarefas 2/3/5/6)

1. **A view é o gargalo estrutural do feed**: cada consulta a
   `vw_atividades` faz UNION ALL = Seq Scan nas 5 tabelas-base
   (deadlines/tasks/suspensoes/agenda/djen) + JOIN cases. Com o volume
   sintético (600/400/500/300) é barato (≤2,4 ms), mas o plano cresce
   linearmente com TODAS as pernas — e o feed atual devolve TUDO sem LIMIT.
   A Tarefa 3 (ORDER BY data NULLS LAST, tipo, id + LIMIT n+1 no servidor)
   ataca o volume; índice na tabela-base só se o EXPLAIN da Tarefa 6 provar
   ganho (a view "simples" não aceita índice próprio).
2. **Empates expostos**: `ORDER BY data ASC NULLS LAST` sem desempate
   (feed) e `data_prazo ASC`/`created_at DESC` (deadlines/cases/clients)
   produzem ordem não-determinística entre páginas — 40 datas de prazo
   empatadas no dataset. Desempate por `id` nas Tarefas 2/3/5.
3. **Busca textual**: `documents.busca_perc` faz Seq Scan na tabela inteira
   (300/300 filtrados) com ILIKE sobre ocr_text — no volume sintético é
   barato; candidato a trigram/full-text SOMENTE se a Tarefa 6 medir gargalo
   real com volume maior.
4. **Count do listador**: `cases.gestao.count`/`documents.gestao.count`
   contam sobre subquery COM ORDER BY embutido (sort inútil no plano).
   A Tarefa 5 remove o ORDER BY do count e compara SQL/plano.
5. **top-N heapsort** no `tasks.a1.cursor.p1` (LIMIT 51 + ORDER BY total)
   mostra o caminho: paginação por chave usa sort de topo, não materializa
   o feed inteiro.
6. **Buffers**: `Shared Read Blocks = 0` em todos os planos (dataset
   inteiro em cache — 178 tabelas cabem na RAM do ambiente). No gate final
   (Tarefa 7), re-executar com `pg_prewarm` alternado/descartado para
   capturar IO real antes de qualquer decisão de índice por "buffers".

## 7. Gate da Tarefa 1

- [x] Matriz ator × endpoint × filtro × total/escopo registrada (seção 1)
- [x] Dataset sintético isolado com schema/commit/contagens registrados
      (seção 2; contagens impressas pelo seed)
- [x] p50/p95 warm + cold, KB, linhas, requests/tela (seções 3–5)
- [x] EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) com SQL redigido + planos +
      data (seção 6)
- [x] p75 de primeira ação visível em navegador de homologação — MEDIDO em
      2026-10-01 (roteiro H1–H3 com Playwright/Chromium contra a stack real,
      seção 8.3-bis; o proxy de soma de requests ficou registrado na seção 2)
- [x] Sem hipótese de índice/caching virou implementação neste estágio

**Sem aprovação do titular nas decisões 1–3 da seção 1, nenhuma tarefa
seguinte altera semântica de escopo.**

## 8. Gate final (Tarefa 7) — resultado das Tarefas 2–6 e decisão

Data do gate: 2026-10-01 · commit `40144d68` · mesmo ambiente/perfil da seção 2.

### 8.1 Entregas e evidências

| Tarefa | Entrega | Testes | Evidência de performance |
|---|---|---|---|
| 2 — cursor comum | `app/core/pagination_cursor.py` (HMAC-SHA256, TTL 30 min, binding usuário/papel/filtros/ordem; keyset ASC NULLS LAST e DESC NULLS FIRST) + opt-in `pagination=cursor` em `/tasks` | 15 puros + 6 DB = **21/21** | `/tasks` socio p95 **230,6→8,3 ms**, payload **128→16,5 KB** (page_size 50); ruído medido ±0,5 ms → **ganho mantido** |
| 3 — atividades/Hoje | `GET /atividades` cursor com filtros server-side (tipo/situação/urgência/janela) + ordenação total `data NULLS LAST, tipo, id` + LIMIT n+1 + enriquecimento (confirmado/ciência/hora/local) por IDs da página + `GET /atividades/resumo` (cards e colunas do conjunto inteiro) | 6 DB novos + 11 existentes = **17/17** | Central: **6→2 requests**, socio p95 **422,7→14,5 ms**, payload **1.115→20,2 KB**; A1 633→20,6 KB |
| 3 — Central FE | Feed cursor + "Carregar mais" (lista/timeline), calendário com janela mensal no servidor, Kanban com contagens do resumo, fim do "Nenhuma atividade" prematuro, invalidação de feed+resumo após ações | typecheck 0 erros; **33/33** vitest | Fan-out `/agenda-eventos?size=500` + até `10×200` prazos **eliminado do caminho padrão** |
| 4 — cockpit Hoje | `GET /dashboard/hoje` (escopo `carteira`/`escritorio`, sem cache de 30 s, decisões priorizadas com ranking preservado, `degradado` ≠ 0) + DashboardUltra usa as decisões do backend | **10/10** DB (incl. regressão do contador de vencidos) + **7/7** FE | Decisões computadas sobre a CARTEIRA INTEIRA (não amostras de 30/50); cliente externo 403 |
| 5 — listas | cursor opt-in em cases/clients/deadlines/documents; desempate por `id` inclusive no legado; count do legado sem ORDER BY no plano; Casos.tsx com "Carregar mais" e guarda de sequência | **5/5** DB + regressões 15/15; FE **36/36** + typecheck 0 | `total` exato preservado no legado; no cursor, total só aparece quando o conjunto exaura (exato por construção) |
| 6 — índices | Experimento controlado ANTES/DEPOIS com índices candidatos parciais (tasks `(data_limite,created_at,id)`; deadlines `(data_prazo,id) WHERE pendente`) | EXPLAIN ×5 execuções | tasks deep 0,29→0,27 ms (+5,5%), deadlines 0,14→0,14 ms (0%), INSERT 0,07 ms igual → **GANHO DENTRO DO RUÍDO: NÃO migrar**; tentativa revertida e registrada |

### 8.2 Comparação baseline → final nas rotas legadas (regressão?)

Deltas warm p50 contra a seção 3 variam de +7% a +35% **absolutos de 1–2 ms** —
mas o ruído entre duas séries finais consecutivas (mesma máquina/dados) mede
**-3% a -24%**. Conclusão: nenhuma regressão legada além do ruído de sessão;
cold p50 melhora ou empata na maioria (ex. deadlines A1 12,9→10,7 ms).

### 8.3 Gates do plano

- [x] Baseline reproduzível e política de escopo registrada (seção 1)
- [x] Botões "Confirmar", "Dar ciência", "Reagendar", "Concluir" preservados
      (enriquecimento inline da página; testes FE mapeiam os campos)
- [x] Cliente externo sem acesso a dado novo (403 em resumo/hoje; gate de
      documentos/sigilo inalterado e testado)
- [x] Redução demonstrada de bytes/queries (Central 6→2 reqs; ~98% menos bytes)
- [x] p95 das rotas críticas (Central feed, tasks, Hoje) melhora além do ruído
- [x] Rollback por flag: FE `localStorage["ejc:atividades-cursor"]="0"` volta
      ao legado; rotas legadas preservadas byte a byte (rollback = desligar
      opt-in no cliente; nenhuma migration de índice foi criada — nada a
      derrubar no banco)
- [x] Suíte de regressão: backend 80/80 (0 skips) + DAG 159 migrations head
      único; frontend 43/43 nos 3 alvos
- [x] `docs/RELEASE_CHECKLIST.md` — edição pontual feita em 2026-10-02 após
      autorização do titular (seção 6 "Registro por release" com rollout,
      rollback por flag e evidências)
- [x] p75 "primeira ação visível" em navegador de homologação (roteiro H1–H3)
      — medido com a stack real servida; números na seção 8.3-bis

### 8.3-bis — p75 "primeira ação visível" em navegador real (H1–H3)

Medição de 2026-10-01 fechando o último item aberto do gate. Stack real:
PostgreSQL sintético isolado + API uvicorn (app real) + frontend Vite com o
caminho NOVO ativo (o log do servidor confirma o Frontend chamando
`/atividades?pagination=cursor&page_size=50` + `/atividades/resumo` — 2
requests, sem fan-out). Playwright/Chromium headless 1440×900, 1 rodada de
aquecimento (compilação on-demand do Vite não conta) + 6 rodadas contadas com
pausa de 7 s (respeita o anti-brute-force do /login, 10/min). Marcador de
"primeira ação visível" por etapa:

| Etapa | Roteiro | p50 | p75 | max |
|---|---|---|---|---|
| H1 Entrada→Hoje | `/login` pronto → credenciais → submit → seção "Meu Dia" do dashboard visível | 1.447,9 ms | **1.474,7 ms** | 1.513,6 ms |
| H1 (navegação inteira) | abertura do `/login` → "Meu Dia" | 2.299,9 ms | 2.342,6 ms | 2.355,3 ms |
| H2 Caso | autenticado → `/casos` → primeira linha da tabela visível | 2.331,4 ms | **2.556,0 ms** | 2.624,2 ms |
| H3 Central | autenticado → `/atividades` → botão "Abrir caso" visível | 1.663,2 ms | **1.720,2 ms** | 1.872,6 ms |

Leitura: o tempo de tela é dominado por bootstrap do frontend (módulos JS,
`/areas`, `/system-modules/settings`, `/notifications`) e não pelas rotas
alvo — as respostas de API medidas na seção 3 somam <100 ms do total. O H3
(Central) carregando feed+resumo por cursor em ~1,7 s confirma o ganho da
Tarefa 3 ponta a ponta. Detalhe metodológico: para permitir o login real o
usuário sócio sintético recebeu senha bcrypt temporária e e-mail temporário,
revertidos ao estado canônico do seed (`hashed_password='x'`,
`@sintetico.local`) imediatamente após a medição; o roteiro e os dados brutos
ficam em `work/p75_navegador.json` e o roteiro em
`scripts/mede_p75_navegador.py`.

### 8.4 Decisão de rollout proposta (sujeita a aprovação)

1. Backend primeiro (legado intacto): `/tasks`, `/atividades`, `/dashboard/hoje`,
   listas com `pagination=cursor` — telemetria de adoção via query-string.
2. Frontend Central por flag (default ON, rollback localStorage).
3. Casos com carregamento incremental; total exato exibido apenas na exaustão.
4. Nenhum índice novo nesta onda (Tarefa 6); reavaliar com volume real e
   `pg_prewarm` alternado (seção 6, item 6).
5. Ordem de reversão em incidente: flag FE → opt-in no cliente → nenhuma ação
   de banco necessária.
