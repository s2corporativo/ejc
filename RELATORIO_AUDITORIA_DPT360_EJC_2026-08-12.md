# Relatório de Auditoria — Módulo DPT Empresarial 360 (dpt360)

**Data**: 2026-08-12
**Escopo**: `backend/app/modules/dpt360/*`, `backend/app/services/ai/core/dpt360_protocol.py` e `dpt360_registry.py`, `frontend/src/pages/dpt360/*`, entradas `dpt360*` em `frontend/src/config/moduleRegistry.tsx`, testes `backend/tests/test_dpt360_*.py` e `frontend/src/pages/dpt360/model.test.ts`.
**Método**: auditoria estática (leitura de código, sem alterações) em quatro frentes paralelas — segurança, correção de backend, correção de frontend e cobertura de testes — seguida de execução da suíte de testes existente. Nenhum código foi modificado nesta auditoria.

## O que é o módulo

O DPT Empresarial 360 (`/api/dpt360`, frontend `/dpt360`) é o cockpit de inteligência jurídica empresarial do EJC: dashboard de portfólio, diagnóstico de prontidão por área, radar de publicações legislativas/jurisprudenciais com impacto por empresa, relatório executivo por cliente e uma fila de captação (intake) de oportunidades. Reaproveita as entidades já existentes (`clients`, `cases`, `deadlines`, `diario_oficial_alertas`) sem schema próprio. Acesso restrito a `superadmin/admin/socio/advogado`, marcado como `sensitive: true` no frontend.

## Resumo executivo

Não há achados críticos. A segurança do módulo está bem projetada: RBAC redundante (rota + núcleo de IA), escopo/ownership aplicado de forma fail-closed em todas as consultas, rate limiting efetivo nos endpoints de escrita/IA, e todo o fluxo de IA passa corretamente pelo `ai_gateway`/HITL/citation gate sem contornar a barreira compartilhada.

O que a auditoria encontrou de fato relevante são **dois problemas de correção silenciosa** — um relatório executivo que pode omitir dados sem avisar, e uma divergência de fuso horário que faz o cockpit classificar prazos de forma diferente da tela canônica de Prazos — mais uma **lacuna grande de testes de integração e de UI** que deixa esses dois problemas (e o fluxo de IA do módulo) sem cobertura automatizada.

## Achados priorizados

### Alto

**A1 — Relatório executivo pode omitir casos/prazos de uma empresa sem aviso.**
`backend/app/modules/dpt360/report_service.py:28-31` — `build_executive_report` reaproveita `build_dashboard(db, user)`, que é a visão paginada e global do escritório (`CASE_PAYLOAD_LIMIT=1000`, `DEADLINE_PAYLOAD_LIMIT=2000`, ordenada por todo o portfólio), só para depois filtrar por um `client_id`. O campo `dashboard.coverage` ("partial"/"complete") existe (`dashboard_service.py:360-384`) mas nunca é lido nem propagado ao relatório. Com mais de 1000 casos empresariais no total, uma empresa com casos mais antigos que o corte global gera relatório executivo incompleto sem qualquer nota.
*Recomendação*: `build_executive_report` deve consultar diretamente por `client_id` (sem o corte global do dashboard), ou propagar e expor `coverage` no payload do relatório.

**A2 (frontend) — Rascunho de IA pode ser atribuído visualmente à empresa errada.**
`frontend/src/pages/dpt360/DptIntelligence.tsx:130-149,184` — os seletores de "Empresa" e "Área de foco" não são desabilitados durante o carregamento (só o botão de gerar é). Se o usuário trocar a empresa selecionada enquanto uma geração de rascunho está em andamento, a resposta da empresa anterior é renderizada sob a seleção visual da nova empresa — e o painel de resultado não exibe a que empresa o rascunho pertence (diferente de `DptReports.tsx`, que exibe `report.empresa` explicitamente).
*Recomendação*: desabilitar os `<select>` durante `loading` e/ou exibir a empresa do `result` no cabeçalho do painel de resultado.

### Médio-Alto

**A3 — "Hoje" calculado em UTC diverge do resto do sistema de prazos.**
`dashboard_service.py:167-169` e `report_service.py:70` usam `datetime.now(timezone.utc).date()` para classificar prazo vencido/crítico/próximo, enquanto o resto do domínio de prazos usa fuso de Brasília (`scheduler.py:40`, `routers/deadlines.py:121`). Como Brasília é UTC−3 (sem horário de verão desde 2019), entre 21h e 23h59 no horário de Brasília o relógio UTC já virou o dia seguinte. Nessa janela, um prazo que vence **hoje** no Brasil (ainda com horas pela frente até a meia-noite local) já é classificado "vencido"/"crítico" no cockpit DPT — até três horas antes de a data realmente virar em Brasília. (Confirmado por simulação: às 21:00 BRT, um prazo com vencimento no dia corrente já cai em `overdue=True`; um prazo com vencimento no dia seguinte permanece `overdue=False`, nível "alto" — não "vencido"/"crítico" como uma leitura apressada do offset sugeriria.) Reproduz a classe de defeito "painéis que divergem entre si" já catalogada na auditoria externa (`docs/auditoria/README.md`).
*Recomendação*: usar o mesmo fuso (`America/Sao_Paulo`) em todo o módulo; cobrir com teste de fronteira às 21:00 BRT comparando prazo de hoje vs. amanhã.

### Médio

**A4 — Radar materializa portfólio inteiro sem limite, ao contrário do dashboard.**
`radar_service.py:84-90` carrega todas as empresas e casos visíveis sem teto, enquanto `dashboard_service.py:46-52` impõe `COMPANY_PAYLOAD_LIMIT`/`CASE_PAYLOAD_LIMIT` justamente para não materializar a carteira inteira. Como `router.py:41` chama `build_today_radar` a cada `GET /dpt360/dashboard`, a metade "radar" da mesma resposta viola o princípio que a metade "dashboard" segue.

**A5 — Resolução de escopo (visibilidade por usuário) repetida a cada carregamento do cockpit.**
`router.py:35-52` — um único `GET /dpt360/dashboard` dispara `build_dashboard` (que já roda as queries de visibilidade duas vezes internamente) seguido de `build_today_radar` (que roda as mesmas duas consultas de novo) — ~8 idas ao banco repetindo a mesma resolução de escopo por requisição. Oportunidade de simplificação: computar uma vez e injetar nos dois serviços.

**A6 — Índices ausentes nos filtros usados por todo o módulo (risco potencial, não medido).**
`Client.deleted_at`/`Client.tipo` (base de quase todo endpoint do DPT) e `DiarioOficialAlerta.created_at`/`.case_id` (usados por `radar_service.py` e `report_service.py`) não têm índice dedicado — só `data_publicacao`/`lido` existem na migration 022. Isso não foi confirmado com `EXPLAIN (ANALYZE, BUFFERS)` nesta auditoria, então não afirmo scan sequencial comprovado — é risco de plano ineficiente à medida que a tabela de alertas cresce (alimentada continuamente por job automático), afetando `/dpt360/dashboard`, `/radar/today` e `/reports/executive/*`.
*Recomendação*: validar com `EXPLAIN (ANALYZE, BUFFERS)` sobre dados representativos antes de decidir se o índice é necessário.

**A7 — Radar cobre só 5 das 12 áreas de negócio do dashboard.**
`radar_service.py:19-33` (`AREA_TERMS`/`AREA_CASE_ALIASES`) não tem entrada para `contratual`, `societario`, `bancario`, `agrario`, `agronegocio`, `empresarial` (presentes em `BUSINESS_AREAS`, `dashboard_service.py:24-37`). Empresa cujo único caso vinculado é de uma dessas áreas nunca aciona `impact_level` — `empresas_potencialmente_impactadas` fica estruturalmente incompleto para essas áreas, sem alerta da lacuna.

**A8 (frontend) — Tabela de portfólio mostra "Não avaliado" para toda empresa, sempre.**
`Dpt360Workspace.tsx:308-330` — a coluna "Saúde jurídica" é hardcoded, sem ler nenhum dado, mesmo quando o backend já calcula `classificacao` por área (usado na visão de detalhe via `CompanyLegalTwin`/`profile.health`). Parece bug/pendência, não decisão deliberada — se for intencional (agregado de portfólio ainda não implementado), precisa de nota explicativa como as demais telas do módulo já fazem.

**A9 (frontend) — Duplicação de padrão fetch/loading/error/seletor de empresa em 6 componentes**, e `traceText()` duplicada literalmente em `DptIntelligence.tsx:32-39` e `DptReports.tsx:7-13`. Oportunidade de extrair hook (`useDptFetch`/`useCompanySelector`) e util compartilhado.

**A10 (frontend) — `model.ts` é código morto.** Nenhum componente do módulo o importa; só `model.test.ts` o exercita, criando falsa sensação de cobertura sobre um caminho que a UI real não usa (a UI trabalha com os tipos pré-agregados de `api.ts`). Remover, ou religar se a duplicação do item A9 for endereçada por ele.

**A11 (segurança/LGPD) — PII de lead do intake é legível por endpoint irmão sem RBAC específico e sem log de leitura.**
`intake_service.py` grava `mensagem`/`contato`/`email`/`telefone` em texto plano em `DocumentIntakeBatch.resultado`, e a fila do DPT (`GET /dpt360/intake/opportunities`) filtra esses campos deliberadamente — mas o mesmo `batch_id` pode ser lido por inteiro via `GET /api/entrada-universal/{batch_id}` (`routers/entrada_universal.py:441-444`), cujo gate é só ownership/`is_gestao`, sem RBAC do DPT e sem log de leitura. Não é IDOR entre usuários (criação já é RBAC-gated), mas contradiz a minimização declarada no código e deixa leitura de PII de terceiro sem trilha — relevante para responsabilização LGPD (Lei nº 13.709/2018, texto oficial em planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm, em vigor integralmente desde 2020) quando a origem é o site público, notadamente os arts. 6º (princípios, inclusive minimização), 37 (registro das operações de tratamento) e 46 (medidas de segurança contra acesso não autorizado).
*Limite desta conclusão*: é evidência de auditoria estática sobre este endpoint específico. O fluxo de IA do módulo (`run_dpt_action`) e a sanitização de PII antes do `ai_gateway` **não foram validados em runtime** nesta auditoria — não há teste HTTP de integração nem teste próprio de `run_dpt_action` que confirme, mesmo mockado, que o contexto minimizado chega sanitizado ao orquestrador (ver gap #2 e #5 em "Cobertura de testes").
*Recomendação*: RBAC específico do DPT na leitura do intake e log de cada leitura são obrigatórios na remediação, não opcionais — junto de teste de regressão HTTP cobrindo isolamento, resposta minimizada e trilha de auditoria. Cifrar os campos de contato em repouso é defesa adicional; não substitui autorização e log de acesso.

### Baixo / Informativo

- **A12** — Endpoints `GET` do DPT não têm rate limiting (só os `POST` têm); `reports/executive` reconstrói o dashboard inteiro a cada chamada — custo desproporcional, não vazamento.
- **A13** — Rate limit em memória (`rate_limit.py`) só é correto com `--workers 1`; confirmar `RATE_LIMIT_REDIS_ENABLED=true` em produção multi-worker (limitação já documentada no `CLAUDE.md`, não introduzida pelo módulo).
- **A14** — `client_id` sem validação de formato UUID nos schemas/rotas; não explorável (queries parametrizadas, 404 uniforme), só nota de robustez.
- **A15** — Valor de enum morto: `origem: Literal[..., "acionejus"]` em `intake_schemas.py` sempre é rejeitado por `field_validator`, mas aparece como aceito no schema/OpenAPI.
- **A16** — `ensure_dpt360_registered` (`dpt360_registry.py:39-42`) depende implicitamente de ser síncrona (atômica no event loop) para não ter race condition; premissa não documentada.
- **A17 (frontend)** — Sinalização de prioridade só por cor (`Dpt360Workspace.tsx:184-192`), falha leve de acessibilidade (WCAG 1.4.1).
- **A18 (frontend)** — `useEffect` de fetch sem guarda de cleanup em `DptOpportunities.tsx` e em `Dpt360Workspace.tsx:519-529` (inofensivo no React 18, mas inconsistente com o padrão já usado em `CompanyLegalTwin`/`DptDiagnosis`/`DptRadar`). Adicionalmente, o botão "Atualizar" de `DptOpportunities.tsx:62-68` não desabilita durante `loading` e `load()` não descarta resposta obsoleta — cliques repetidos disparam requisições concorrentes e uma resposta antiga pode sobrescrever `items` depois de uma mais recente já ter chegado (`Dpt360Workspace` não tem esse caminho porque desabilita o botão equivalente durante o carregamento).
- **A19 (frontend)** — Drift visual: `Dpt360Workspace.tsx` usa `dark:bg-slate-950/40` onde as outras 10 telas do módulo usam `dark:bg-white/[0.03]`.

## Cobertura de testes

Suítes existentes executadas nesta auditoria — todas verdes. Execução local, não em CI (o CI do repositório estava indisponível por falha de cobrança/provisionamento de runner no GitHub nesta janela — ver PR, não relacionado à correção destes testes):
- Commit/ref auditado: `ffc9cbb4bb20054987009f58d2b7a7b4e1818811` (`main` no momento da auditoria).
- Backend: diretório `backend/`, venv Python 3.11 dedicado (`pip install -r requirements.txt`), comando `python -m pytest tests/test_dpt360_*.py -v` — **29 passed** (7 arquivos: dashboard, intake, radar, ai_protocol, security_hardening, company_profile, diagnostic_readiness).
- Frontend: diretório `frontend/`, `npm ci` (Node 22.22 conforme `ci.yml`), comando `npx vitest run src/pages/dpt360/` — **5 passed** (só `model.test.ts`).
- Saída bruta completa dos comandos não foi arquivada nesta auditoria (só o resumo final passed/failed) — reexecutar os comandos acima reproduz o resultado.

Gaps relevantes identificados (nenhum teste foi criado nesta auditoria):

1. **Nenhum teste de integração HTTP real** — `test_dpt360_security_hardening.py` inspeciona metadados de rota (`route.dependant`), não faz requisição via `TestClient`. Nunca foi exercitado: 404 real quando o serviço retorna `None`, 429 real de rate limit, serialização real do `response_model`.
2. **`run_dpt_action` (`intelligence_service.py:58`) — fluxo de IA do módulo — sem teste próprio.** `test_dpt360_ai_protocol.py` testa só os blocos de prompt, não a função que orquestra: `profile is None`, área inválida com fallback, `structured is None`, normalização de `citacoes`, nem confirmação (mesmo mockada) de que passa pelo `ai_gateway`/kill-switch/sanitização de PII.
3. **`build_executive_report` sem nenhum teste**, direto ou indireto — inclusive o achado A1 acima não teria sido pego pela suíte atual.
4. **Frontend: só `model.ts` (código morto, ver A10) tem teste.** Os 11 componentes `.tsx` (~2.600 linhas), incluindo o ponto de entrada `Dpt360Workspace.tsx` e a tela que dispara `/actions` (`DptIntelligence.tsx`), não têm nenhum teste.
5. Cobertura de PII é só estrutural (ausência de campo/log), sem teste de runtime confirmando que o contexto minimizado chega sanitizado ao `orchestrator`.

## Pontos positivos confirmados

- RBAC redundante e consistente: rota (`require_roles(DPT_ROLES)`) + núcleo de IA (`roles_permitidos=_allowed_dpt_roles()` + checagem no `orchestrator`), sem ampliação acidental via hierarquia de papéis.
- Escopo/ownership fail-closed em todas as consultas (`access_scope.py`, `_visible_company_query`/`_visible_business_cases_query`), com 404 uniforme (não 403) para `client_id` fora de escopo — evita enumeração.
- Toda chamada de IA passa exclusivamente por `orchestrator.run` → `ai_gateway.chat`, com sanitização de PII, kill-switch, HITL (`is_rascunho=True`) e citation gate — nenhum provider chamado direto.
- Isolamento do RAG entre clientes é fail-closed quando não há `case_id`/escopo definido.
- Rate limiting efetivo (chave por usuário, não por IP) nos dois endpoints de escrita/IA.
- Validação Pydantic robusta no intake (`Literal`, tamanhos, bloqueio de origem indevida, consentimento obrigatório quando aplicável); sem `dangerouslySetInnerHTML` no frontend, então sem XSS explorável pela superfície atual.
- Frontend não é a barreira de segurança: oculta UI por role, mas todo `client_id` é revalidado pelo backend.
- A única escrita em duas tabelas do módulo (`intake_service.py`, batch + audit log) está corretamente na mesma transação — não repete o padrão de gravação não-transacional citado no `CLAUDE.md`.

## Limitações desta auditoria

- Auditoria estática; não houve execução manual da UI no navegador para confirmar os achados de frontend (A2, A8, A17) visualmente — a leitura de código é consistente com o comportamento descrito, mas vale confirmação visual antes de corrigir.
- Não foi avaliado o comportamento sob carga real (volume de dados de produção) para A4/A6/A12 — os riscos de performance são projetados a partir da leitura do código, não medidos.
- Achados A1–A19 não foram corrigidos nesta tarefa (auditoria, não implementação); cada um deve virar tarefa própria conforme as regras de decisão do `CLAUDE.md` (achado fora do escopo original vira Issue nova).

## Próximos passos sugeridos

1. Corrigir A1 e A3 (relatório incompleto e divergência de fuso) — maior risco de decisão jurídica baseada em dado incorreto.
2. Corrigir A2 (race de seleção de empresa no rascunho de IA) — risco de atribuir conteúdo à empresa errada.
3. Avaliar A11 (LGPD) com o responsável por dados — decidir entre restringir o endpoint irmão ou cifrar os campos de contato do lead.
4. Fechar os gaps de teste de integração e de UI antes de qualquer nova funcionalidade no módulo, para não repetir o padrão "monitoramento afere execução, não resultado" em silêncio.
5. A4–A10 e A12–A19 são de menor risco; priorizar conforme capacidade do time.
