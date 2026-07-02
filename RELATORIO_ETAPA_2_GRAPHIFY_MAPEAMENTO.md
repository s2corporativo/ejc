# RELATORIO ETAPA 2 - GRAPHIFY E MAPEAMENTO ARQUITETURAL

Data: 2026-07-02  
Repositorio: `C:\Users\User\EJC`  
Branch: `audit-ejc-graphify-etapa1`  
Escopo: instalacao/validacao segura do Graphify, execucao na raiz do EJC, leitura do grafo e interpretacao tecnica.  
Regra desta etapa: nenhuma correcao funcional aplicada.

## 1. Resultado direto

Graphify foi validado e executado com sucesso no ambiente de desenvolvimento isolado.

- Runtime usado: `C:\Users\User\EJC\backend\.venv-codex\Scripts\python.exe`
- CLI usada: `C:\Users\User\EJC\backend\.venv-codex\Scripts\graphify.exe`
- Versao: `graphify 0.9.5`
- Saida: `C:\Users\User\EJC\graphify-out`
- Pasta `graphify-out/`: ignorada por Git, regeneravel, sem necessidade de versionamento.
- Nao houve exposicao de credenciais, tokens, chaves ou dados reais.
- Nao foi executado build, deploy, seed, migracao, SQL, backup ou restore.

Comando executado:

```powershell
$env:PYTHONHASHSEED='0'
$env:GRAPHIFY_MAX_WORKERS='1'
& 'C:\Users\User\EJC\backend\.venv-codex\Scripts\graphify.exe' update 'C:\Users\User\EJC' --force
```

Arquivos gerados/atualizados:

- `graphify-out/graph.html`
- `graphify-out/graph.json`
- `graphify-out/GRAPH_REPORT.md`
- `graphify-out/manifest.json`
- `graphify-out/.graphify_labels.json`
- `graphify-out/cache/`

Observacao: o Graphify avisou que a skill local esta em `0.9.4` enquanto o pacote esta em `0.9.5`. Nao atualizei a skill nesta etapa para evitar alteracao fora do escopo.

## 2. Resumo do grafo

Fonte primaria: `graphify-out/GRAPH_REPORT.md` e `graphify-out/graph.json`.

- Arquivos analisados: 553
- Nos: 4300
- Arestas: 8249
- Comunidades: 410
- Hyperedges: 3
- Commit base informado pelo grafo: `043156c632d73daa4f359080eb631d738ebb98ea`
- Origem dos nos: 4204 extraidos por AST; 96 sem origem AST direta.
- Tipos de nos: 3325 code, 642 rationale, 267 document, 59 concept, 7 image.
- Relacoes mais frequentes: `contains`, `references`, `calls`, `uses`, `rationale_for`, `imports_from`, `imports`, `inherits`.

Diagnostico do multigrafo:

- Endpoints ausentes no grafo: 0
- Dangling endpoints: 0
- Self loops: 0
- Duplicatas exatas de aresta: 0
- Arestas colapsadas por endpoint: 0

Leitura: o grafo esta estruturalmente consistente. Os riscos encontrados abaixo sao riscos de arquitetura, integracao e excesso de superficie, nao falha interna do arquivo `graph.json`.

## 3. Arquivos criticos do sistema

Hubs de maior grau no grafo:

- `frontend/src/App.tsx`: centraliza rotas e lazy loading.
- `frontend/src/lib/api.ts`: cliente HTTP central.
- `frontend/src/components/UI.tsx`: componentes base compartilhados.
- `frontend/src/pages/CasoDetalhe.tsx`: pagina mais acoplada do frontend; concentra muitas chamadas API.
- `frontend/src/pages/Casos.tsx`: fluxo principal de casos.
- `frontend/src/pages/ramos/RamoBase.tsx` e `ramosConfig.ts`: hub dos ramos juridicos.
- `backend/app/main.py`: registro de routers e health check.
- `backend/app/core/database.py`: base SQLAlchemy e sessao.
- `backend/app/core/security.py` e `auth_middleware.py`: seguranca e autenticacao.
- `backend/app/models/user.py`: usuario e refresh token.
- `backend/app/models/case.py`: caso e movimentos.
- `backend/app/routers/ramos.py`: maior router, com 63 endpoints.
- `backend/app/routers/cases.py`: 18 endpoints.
- `backend/app/routers/ai.py`: 15 endpoints.
- `backend/app/routers/rag.py`: 11 endpoints.
- `backend/app/routers/legal_docs.py`: 11 endpoints.
- `backend/app/services/ai_gateway.py`: gateway de IA.
- `backend/app/services/ai_service.py`: servicos legados/alto nivel de IA.
- `backend/app/services/peca_service.py`: pipeline SSE de peca juridica.
- `backend/app/services/embedding_service.py`: geracao de embeddings.
- `backend/app/services/rag_juridico.py`: classe RAG juridico.
- `backend/app/services/documento_service.py`: servico documental.
- `backend/app/services/deadline_calculator.py`: regras de prazos.

## 4. Mapa dos modulos

### Nucleo tecnico

- `backend/app/core`: configuracao, banco, seguranca, ownership, rate limit, notificacoes, templates, IA core.
- `backend/app/main.py`: inclui 100+ routers sob `/api`.
- `docker-compose.yml`: Postgres, backend e frontend.

### Operacao juridica principal

- Clientes: `clients`, `client.py`, `Clientes.tsx`, `DossieCliente.tsx`.
- Casos/processos: `cases`, `processes`, `case_partes`, `caso_areas`, `CasoDetalhe.tsx`, `Casos.tsx`.
- Prazos/tarefas/agenda: `deadlines`, `tasks`, `agenda_eventos`, `calendar_feed`, `Prazos.tsx`, `Tarefas.tsx`, `Agenda.tsx`.
- Documentos/pecas: `documents`, `documento_ia`, `legal_docs`, `peca_geracao`, `templates`, `signatures`, `Pecas.tsx`, `GestaoDocumental.tsx`.
- Honorarios/financeiro: `fees`, `honorarios_calc`, `honorarios_oab`, `financeiro_consolidado`, `despesas`, `partner_withdrawals`.

### Inteligencia/IA/RAG

- IA geral: `ai.py`, `ai_tools.py`, `ia_extra.py`, `ia_especializada.py`, `ai_gateway.py`, `ai_service.py`.
- IA defensiva/governanca/saude: `ia_defensiva.py`, `ia_governanca.py`, `ia_saude.py`.
- RAG: `rag.py`, `rag_juridico.py`, `embedding_service.py`, `ingestion_service.py`, `KnowledgeDoc`, `KnowledgeChunk`.
- Pecas com IA: `peca_service.py`, `legal_docs.py`, `PecaGeneratorModal.tsx`, `Pecas.tsx`.

### Governanca, auditoria e qualidade

- `audit`, `audit_log.py`, `qualidade`, `validador_juridico`, `ia_governanca`, `security_service`, `sanitizer`.

### Portal externo

- Backend: `portal`, `mensagens`, `signatures`.
- Frontend: `PortalLayout.tsx`, `pages/portal/*`.

## 5. Mapa das rotas

### Frontend

- Rotas frontend identificadas em `App.tsx`: 71.
- Principais areas: login, portal, dashboard, clientes, casos, prazos, documentos, pecas, honorarios, IA, conhecimento, auditoria, usuarios, financeiro, ramos, agenda, checklists, diario oficial, sociedade, portal do cliente.
- Paginas frontend analisadas: 70 em `frontend/src/pages`.
- Componentes frontend analisados: 44 em `frontend/src/components`.

Rotas frontend com slug sem backend literal aparente por heuristica:

- `/tarefas`
- `/central-relacionamento`
- `/knowledge-hub`
- `/biblioteca`
- `/ajuda`
- `/noticias`
- `/conteudo-juridico`
- `/inteligencia`
- `/ferramentas-ia`
- `/victory-vault`
- `/radar-regulatorio`
- `/assistente-ia`
- `/assinaturas`
- `/ramos`
- `/atividades`
- `/financeiro-dashboard`
- `/despesas-recorrentes`
- `/crm-leads`
- `/conhecimento`
- `/usuarios`
- `/lixeira`

Leitura: parte dessas rotas pode consumir endpoints com outro nome ou funcionar como hub visual. Devem ser validadas antes de qualquer exclusao.

### Backend

- Routers backend em `backend/app/routers`: 115 arquivos.
- Endpoints decorados identificados: 502.
- Routers com maior numero de endpoints:
  - `ramos.py`: 63
  - `cases.py`: 18
  - `ai.py`: 15
  - `novos_modulos.py`: 14
  - `clients.py`: 11
  - `legal_docs.py`: 11
  - `rag.py`: 11
  - `checklists.py`: 10
  - `ia_governanca.py`: 10
  - `auth.py`: 9

Endpoints backend sem literal evidente no frontend: 133. Principais grupos:

- `novos_modulos.py`: 12
- `ai.py`: 8
- `calculadoras.py`: 8
- `analytics.py`: 7
- `jurisprudencia_externa.py`: 6
- `whatsapp.py`: 5
- `cerebro.py`: 4
- `consumidor_monitor.py`: 4
- `documents.py`: 4
- `environmental.py`: 4
- `export.py`: 4
- `workflow.py`: 4

Leitura: muitos desses endpoints parecem API administrativa, recurso futuro ou integracao externa. O risco e a ausencia de uma matriz oficial "tela -> endpoint -> permissao -> status".

## 6. Componentes frontend e chamadas API

Chamadas API detectadas no frontend: 259.

Arquivos com mais chamadas:

- `CasoDetalhe.tsx`: 37
- `Pecas.tsx`: 13
- `GovernancaIA.tsx`: 10
- `IA.tsx`: 8
- `Jurimetria.tsx`: 8
- `Sociedade.tsx`: 8
- `Clientes.tsx`: 6
- `DiarioOficial.tsx`: 6
- `Honorarios.tsx`: 6
- `Tarefas.tsx`: 6

Chamadas frontend sem prefixo backend aparente:

- `AnaliseExtratos.tsx`: `/v1/bank-analysis/upload`
- `AnaliseExtratos.tsx`: `/v1/bank-analysis/${id}/excel`
- `AnaliseExtratos.tsx`: `/v1/bank-analysis/${id}/documento`
- `CasoDetalhe.tsx`: `/extratos/casos/${caso.id}`
- `CentralAtividades.tsx`: `/atividades`
- `FinanceiroDashboard.tsx`: `/v1/financeiro/consolidado`
- `FinanceiroDashboard.tsx`: `/v1/relatorio/mensal`
- `Honorarios.tsx`: `/v1/honorarios-exito/${fee.id}/rateio`
- `Honorarios.tsx`: `/v1/honorarios-exito/${fee.id}/rateio`
- `Noticias.tsx`: `/noticias?limit=30...`

Possivel causa: divergencia de prefixo (`/v1` no frontend versus rota backend sem `/v1` ou vice-versa), endpoints renomeados, ou chamadas antigas remanescentes.

Paginas sem chamada API direta detectada:

- `Ajuda.tsx`
- `Auditoria.tsx`
- `ConteudoJuridico.tsx`
- `DashboardIA.tsx`
- `FinanceiroWorkspace.tsx`
- `GestaoDocumental.tsx`
- `InteligenciaWorkspace.tsx`
- `Produtividade.tsx`
- `RamosHub.tsx`
- `VictoryVault.tsx`
- `Whatsapp.tsx`
- `portal/PortalCasos.tsx`
- `portal/PortalFinanceiro.tsx`

Leitura: algumas sao hubs, wrappers ou paginas informativas; outras podem depender de componentes filhos. Nao classificar como erro sem teste de tela.

## 7. Mapa dos servicos backend

Servicos centrais:

- `ai_gateway.py`: normalizacao de task type, nivel de inteligencia, escolha de provider, chamada a provider e registro de log.
- `ai_service.py`: busca contexto RAG, formatacao de fontes, analise de caso, resumo, auditoria de peca, audiencia, contrato.
- `case_intel.py`: triagem de caso, aprendizado de encerramento, indexacao de peca no RAG.
- `peca_service.py`: pipeline SSE em 7 etapas para geracao de pecas.
- `documento_service.py`: servicos documentais e geracao/formatacao.
- `deadline_calculator.py`: calculo de prazos e feriados/suspensoes.
- `embedding_service.py`: provider local/http e geracao de embeddings.
- `ingestion_service.py`: upsert de documentos e chunks para conhecimento.
- `security_service.py` e `sanitizer.py`: sanitizacao e protecao.
- `scheduler.py`: rotinas agendadas.

Arquitetura observada: existem servicos maduros e tambem rotas com logica propria. A proxima etapa deve evitar refatorar servicos centrais antes de mapear contratos de resposta.

## 8. Mapa do banco de dados

ORM: SQLAlchemy async.  
Migracoes: Alembic com 55 arquivos.

Modelos identificados:

- Usuarios/autenticacao: `User`, `RefreshToken`, `PasswordResetToken`, `UserKnownIP`.
- Clientes/casos: `Client`, `Case`, `CaseMovimento`, `CaseParte`, `CasoArea`.
- Prazos/tarefas: `Deadline`, `Task`, `Feriado`, `SuspensaoTribunal`.
- Documentos/pecas: `Document`, `LegalDoc`, `DocTemplate`, `SignatureRequest`.
- Financeiro: `Fee`, `FeePayment`, `CentroCusto`, `Socio`, `DistribuicaoLucro`, `TimeEntry`.
- RAG/IA: `KnowledgeDoc`, `KnowledgeChunk`, `AILog`, `EjcSkill`, `PromptJuridico`.
- Governanca: `AuditLog`, `WorkflowTemplate`, `CaseWorkflow`, `WorkflowHistorico`.
- Modulos especificos: `BankAnalysis`, `DataRoom`, `DossieEstrategico`, `EnvironmentalCase`, `JurisprudenciaInterna`, `Tese`, `WikiPagina`, `Atendimento`.

Ultimas migracoes:

- `045_p1_resumo_ia.py`
- `046_wiki.py`
- `047_dedup_cases.py`
- `048_processes.py`
- `049_totp_2fa.py`
- `050_novos_modulos.py`
- `051_ejc_skills.py`
- `052_workflow_tables.py`
- `053_reconcile_schema.py`
- `054_victory_vault.py`
- `055_rag_isolation.py`
- `056_processes_is_principal.py`
- `057_deadline_datajud.py`
- `058_users_email_unique.py`
- `059_archiving_cases_processes.py`

Risco: a sequencia de migracoes mostra crescimento intenso e recente. Qualquer alteracao estrutural deve comecar por `alembic heads/current/history` em ambiente seguro, sem rodar upgrade direto em producao.

## 9. Mapa das integracoes de IA

Provedores:

- Groq: `providers/groq_provider.py`
- Ollama: `providers/ollama_provider.py`
- Anthropic: `providers/anthropic_provider.py`

Gateway:

- `ai_gateway.py` e o ponto recomendado de concentracao.
- Frontend principal: `IA.tsx`, `AgenteIA.tsx`, `AssistenteIA.tsx`, `FerramentasIA.tsx`, `GovernancaIA.tsx`, `DashboardIA.tsx`, `CasoDetalhe.tsx`, `Pecas.tsx`.

Fluxos:

- `ai_tools.py`: `/ai/status` e `/ai/executar`.
- `ai.py`: analise de caso, dossie, resumo, logs, HITL, audiencia, contrato, estrategia.
- `ia_extra.py`: pesquisar, resumir texto, traduzir andamento, gerar minuta, sugestao de honorarios.
- `ia_defensiva.py`: historico, status e analise defensiva.
- `ia_governanca.py`: dashboard, curadoria, fontes, guardrails, importacao jurisprudencial.
- `legal_docs.py` + `peca_service.py`: pecas juridicas com validacao/HITL.

Risco: existem muitos pontos de entrada de IA. Mesmo com gateway central, a superficie de rotas e telas favorece divergencias de payload, nomenclatura de tarefa e duplicacao de experiencia.

## 10. Mapa do RAG

Nucleo RAG:

- Modelos: `KnowledgeDoc`, `KnowledgeChunk`, `FonteIngestao`.
- Router: `backend/app/routers/rag.py`.
- Servicos: `rag_juridico.py`, `embedding_service.py`, `ingestion_service.py`, `ai_service.buscar_contexto_rag`.
- Ingestores: `services/ingestors/stj.py`, `planalto.py`, `senado.py`, `camara.py`.

Endpoints principais:

- `/rag/status`
- `/rag/indexacao`
- `/rag/ingerir`
- `/rag/buscar`
- `/rag/match-casos`
- `/rag/docs`
- `/rag/monitor-legislativo`
- `/rag/ingerir-ai-log/{log_id}`

Risco: o grafo mostra RAG como modulo ativo estruturalmente, mas a ativacao semantica depende de configuracao (`EMBEDDINGS_ENABLED`, provider local/http, runtime). Nao assumir busca semantica operacional sem validar ambiente.

## 11. Arquivos orfaos ou desconectados

Nos com grau zero no grafo: 80. Amostra relevante:

- `backend/app/**/__init__.py`: provavelmente normal, arquivos de pacote.
- `backend/conftest.py`: suporte de teste.
- `frontend/postcss.config.js`, `tailwind.config.js`, `vite.config.ts`: configuracao, natural aparecer isolada.
- `frontend/public/sw.js`, `sw-register.js`: service worker, fora da malha TS principal.
- `frontend/src/qrcode.d.ts`: declaracao de tipo.
- `deploy-seguranca.ps1`, `scripts/gen_vapid.py`: scripts utilitarios.
- Documentos antigos de auditoria e README: aparecem como nos documentais isolados.

Modulos/paginas com integracao aparente fraca:

- `Ajuda.tsx`, `Auditoria.tsx`, `ConteudoJuridico.tsx`, `DashboardIA.tsx`, `Whatsapp.tsx`, `VictoryVault.tsx`.
- Backends API-only ou pouco consumidos: `novos_modulos.py`, `calculadoras.py`, `cerebro.py`, `consumidor_monitor.py`, `environmental.py`, `workflow.py`.

## 12. Duplicidades e sobreposicoes

Duplicidades arquiteturais provaveis:

- Data room: `data_room.py`, `data_room_v4.py`, `DataRoom.tsx`, alem de redirecionamento `/data-room -> /documentos`.
- Teses: `teses.py`, `teses_v4.py`, `MotorTeses.tsx`, `Biblioteca.tsx`, `Conhecimento.tsx`.
- Sala de guerra: `sala_de_guerra.py`, `sala_de_guerra_v3.py`, `SalaDeGuerra.tsx`.
- Pecas: `legal_docs.py`, `peca_geracao.py`, `peca_geracao_router.py`, `PecaGeneratorModal.tsx`, `Pecas.tsx`.
- IA: `ai.py`, `ai_tools.py`, `ia_extra.py`, `ia_especializada.py`, `ia_defensiva.py`, `ia_governanca.py`, `ia_saude.py`.
- Login: `Login.tsx` e `LoginModern.tsx`; `App.tsx` usa `LoginModern`.
- Dashboard: `Dashboard.tsx`, `DashboardIA.tsx`, `DashboardModernLuxury.tsx`, `Dashboards.tsx`.
- Guias juridicos: varios componentes `Guia*.tsx` com funcoes repetidas `Sec`, `Tab`, `Flow`, `CHECKLIST`, `ITEMS`.

Duplicidades de simbolos relevantes:

- `_pode_editar` aparece em 10 routers.
- `_is_staff` aparece em 6 routers.
- `atualizar` aparece em 10 routers.
- `listar_templates` aparece em 4 routers.
- `listar_teses` aparece em 4 routers.
- `health` aparece em backend principal e providers.

Leitura: nem toda duplicidade e erro. Mas ha padroes claros de copy/paste funcional e evolucao paralela por camadas.

## 13. Inconsistencias identificadas

### Prefixos divergentes

- Frontend chama `/v1/bank-analysis/*`; backend identificado expoe `/bank-analysis/*`.
- Frontend chama `/v1/financeiro/consolidado`; backend identificado expoe `/financeiro/consolidado`.
- Frontend chama `/v1/honorarios-exito/*`; backend identificado expoe `/honorarios-exito/*`.
- Frontend chama `/extratos/casos/{id}`; backend identificado expoe `/extratos/detalhado/{case_id}`, `/extratos/advogado/{user_id}`, `/extratos/socio/{user_id}`.
- Frontend chama `/noticias?limit=...`; o backend tem router `noticias.py`, mas a heuristica nao encontrou literal equivalente; precisa inspecao pontual.

### Modulos ainda com licitacao

- Frontend: rota `/licitacao-auditoria`, pagina `LicitacaoAuditoria.tsx`, componente `GuiaLicitacoes.tsx`.
- Backend: `licitacao_auditoria.py`, `core/licitacao_auditor.py`.

Leitura: isso conflita com a diretriz de MVP sem licitacao, mas nao foi corrigido nesta etapa.

### Muitos endpoints sem tela clara

Existe grande bloco de endpoints potencialmente API-only/futuros: `novos_modulos`, `calculadoras`, `analytics`, `cerebro`, `consumidor_monitor`, `environmental`, `workflow`, `export`.

Leitura: risco de bloat e de rotas vivas sem dono de produto.

## 14. Dependencias criticas

- PostgreSQL + pgvector: base de dados e RAG.
- SQLAlchemy/Alembic: schema e migracoes.
- FastAPI/Uvicorn: API.
- JWT/passlib/bcrypt/python-jose/PyJWT: autenticacao.
- React/Vite/TypeScript/Tailwind: frontend.
- Axios/Zustand/react-router-dom: chamadas API, estado e navegacao.
- Groq/Ollama/Anthropic providers: IA.
- LangChain/fastembed/httpx: RAG/embeddings/integracoes.
- PyMuPDF, pypdf, pdfplumber, python-docx, pandas/openpyxl: documentos.
- Docker Compose/Nginx: deploy local/producao.
- `vps-tools`: acesso operacional a VPS; sensivel por natureza.

## 15. Areas com maior risco de quebra

- `CasoDetalhe.tsx`: 37 chamadas API, integra casos, partes, processos, score, indice de risco, RAG, mensagens, etiquetas, IA defensiva e memoria.
- `ramos.py`: 63 endpoints em um unico router.
- IA/RAG: muitos routers e servicos, alta chance de contrato divergente.
- Banco/migracoes: 55 migracoes, com mudancas recentes ate `059`.
- Documentos/pecas: varias rotas e servicos paralelos.
- Financeiro/honorarios: prefixos `/v1` divergentes no frontend.
- Data room/gestao documental: coexistencia de versoes e redirecionamentos.
- Licitacao: modulo proibido no MVP ainda esta no grafo.
- Arquivos sensiveis/operacionais: `vps-tools/.env`, scripts SQL, artefatos `.tgz`.

## 16. Sinais de contaminacao por multiplas IAs/alteracoes paralelas

Sinais objetivos no grafo e na arvore:

- Sufixos/versionamentos paralelos: `data_room_v4`, `teses_v4`, `sala_de_guerra_v3`, `intelligence_v3`.
- Multiplicacao de routers de IA com responsabilidades sobrepostas.
- Rotas com prefixo misto: `/v1/...`, `/api/v1/...` e rotas sem `/v1`.
- Componentes antigos e modernos coexistindo (`Login.tsx` e `LoginModern.tsx`; varios dashboards).
- Pasta `_QUARENTENA` com residuos e artefatos preservados.
- Muitos relatorios tecnicos anteriores e arquivos de auditoria na raiz.
- `CLAUDE.md` e hooks de Graphify/Claude indicam historico de uso por agentes diferentes.
- Modulo de licitacao permanece apesar de diretriz de remocao do MVP.
- Repeticao de funcoes utilitarias simples em muitas paginas/componentes.

Leitura: o projeto parece ter evoluido por acumulacao incremental, com varias frentes simultaneas. A estrategia segura e estabilizar contratos e donos de modulo antes de refatorar.

## 17. Riscos de refatoracao

- Refatorar por nome pode quebrar rotas usadas indiretamente por componentes filhos.
- Remover endpoint "sem frontend" pode quebrar automacoes, webhooks, scripts ou portal.
- Consolidar IA sem matriz de payload pode quebrar fluxos HITL e logs.
- Mexer em migracoes antigas pode quebrar producao.
- Remover licitacao exige decidir se e exclusao real, hide de UI ou quarentena tecnica.
- Alterar `api.ts` ou prefixos globais pode corrigir um modulo e quebrar outro.
- `CasoDetalhe.tsx` deve ser tratado como area critica: qualquer mudanca pede testes dirigidos.

## 18. Recomendacoes objetivas para a proxima etapa

1. Criar uma matriz `frontend route -> page -> API calls -> backend router -> status` para as 71 rotas.
2. Validar primeiro as 10 chamadas frontend sem backend aparente, pois sao candidatas fortes a erro real.
3. Classificar os 133 endpoints sem frontend em quatro grupos: usado por tela, API-only, futuro/desativado, remover/quarentenar.
4. Fazer uma etapa especifica para licitacao: decidir remocao, ocultacao ou quarentena, sem misturar com outros ajustes.
5. Congelar contratos de IA/RAG antes de qualquer consolidacao: request, response, HITL, logs e custos.
6. Auditar migracoes Alembic em ambiente seguro antes de qualquer mudanca de schema.
7. Evitar refatoracao ampla; corrigir por lotes pequenos e verificaveis.

## 19. Criterio de aceite

- Graphify executado: atendido.
- Arquivos de saida gerados: atendido em `graphify-out/`.
- Arquitetura analisada: atendido.
- Relatorio tecnico entregue: atendido neste arquivo.
- Nenhuma correcao aplicada: atendido.
