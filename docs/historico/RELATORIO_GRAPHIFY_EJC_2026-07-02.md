# RELATORIO GRAPHIFY EJC - 2026-07-02

## Resultado

Graphify esta funcional no repositorio `C:\Users\User\EJC` e o EJC esta mapeado em grafo local.

Artefatos principais:
- `graphify-out/graph.html` - grafo interativo
- `graphify-out/graph.json` - grafo bruto
- `graphify-out/GRAPH_REPORT.md` - relatorio gerado pelo Graphify
- `graphify-out/manifest.json` - manifesto da extracao

Resumo atual do grafo:
- 550 arquivos analisados
- 4256 nos
- 8198 arestas
- 408 comunidades
- 79% EXTRACTED
- 21% INFERRED
- 0% AMBIGUOUS
- Diagnostico multigraph: 0 endpoints ausentes, 0 endpoints pendentes, 0 duplicatas exatas, 0 colapsos por par de endpoints

## Runtime Graphify

Instalacao local:
- Python: `backend/.venv-codex/Scripts/python.exe`
- CLI: `backend/.venv-codex/Scripts/graphify.exe`
- Pacote: `graphifyy==0.9.5`

Hooks instalados:
- `.git/hooks/post-commit`
- `.git/hooks/post-checkout`

Ambos os hooks foram reinstalados e apontam para:

```text
C:\Users\User\EJC\backend\.venv-codex\Scripts\python.exe
```

O marcador `graphify-out/.graphify_python` tambem foi ajustado para o mesmo runtime local.

## Comandos de manutencao

Regenerar grafo de codigo:

```powershell
& 'C:\Users\User\EJC\backend\.venv-codex\Scripts\graphify.exe' update 'C:\Users\User\EJC' --force
```

Validar hooks:

```powershell
& 'C:\Users\User\EJC\backend\.venv-codex\Scripts\graphify.exe' hook status
```

Diagnosticar integridade do grafo:

```powershell
& 'C:\Users\User\EJC\backend\.venv-codex\Scripts\graphify.exe' diagnose multigraph --graph 'C:\Users\User\EJC\graphify-out\graph.json'
```

Abrir grafo interativo:

```powershell
Start-Process 'C:\Users\User\EJC\graphify-out\graph.html'
```

## Mapa macro do sistema

Backend:
- FastAPI em `backend/app/main.py`
- Routers em `backend/app/routers`
- Models SQLAlchemy em `backend/app/models`
- Schemas Pydantic em `backend/app/schemas`
- Services em `backend/app/services`
- Modulos especializados em `backend/app/modules`
- Migrations Alembic em `backend/alembic/versions`

Frontend:
- React Router em `frontend/src/App.tsx`
- Paginas em `frontend/src/pages`
- Componentes em `frontend/src/components`
- Cliente API em `frontend/src/lib/api.ts`
- Tipos em `frontend/src/types/index.ts`

Banco:
- 40 arquivos de model
- 55 migrations Alembic
- Tabelas centrais identificadas: users, clients, cases, processes, deadlines, tasks, documents, legal_docs, fees, audit_logs, rag_documents/knowledge_docs, ai_logs e tabelas satelites por modulo

IA/RAG:
- Routers principais: `ai.py`, `rag.py`, `ia_governanca.py`, `ia_defensiva.py`, `ia_extra.py`, `ia_especializada.py`, `ai_skills.py`, `ai_tools.py`, `documento_ia.py`
- Services principais: `ai_gateway.py`, `ai_service.py`, `embedding_service.py`, `ingestion_service.py`, `rag_juridico.py`, `case_context.py`, `documento_service.py`, `analise_estrategica.py`, `citation_check.py`
- Providers: `providers/ollama_provider.py`, `providers/groq_provider.py`, `providers/anthropic_provider.py`

Casos e processos:
- Caso canonico: `backend/app/models/case.py`
- Router de casos: `backend/app/routers/cases.py`
- Processo independente 1:N: `backend/app/routers/processes.py`
- Conversao judicial: `backend/app/routers/conversao_caso.py`
- Contexto do caso para IA/RAG: `backend/app/services/case_context.py`

## Mapa de rotas frontend

Rotas publicas:
- `/login`
- `/recuperar-senha`
- `/redefinir-senha`

Portal do cliente:
- `/portal/casos`
- `/portal/casos/:id`
- `/portal/financeiro`
- `/portal/assinaturas`
- `/portal/mensagens`

Operacional interno:
- `/`
- `/clientes`
- `/clientes/:clientId`
- `/casos`
- `/casos/:id`
- `/prazos`
- `/suspensoes`
- `/tarefas`
- `/intimacoes`
- `/documentos`
- `/pecas`
- `/jurimetria`
- `/knowledge-hub`
- `/biblioteca`
- `/memoria`
- `/produtividade`
- `/ajuda`
- `/noticias`
- `/conteudo-juridico`
- `/wiki`
- `/inteligencia`
- `/ferramentas-ia`
- `/victory-vault`
- `/licitacao-auditoria`
- `/radar-regulatorio`
- `/kanban`
- `/agenda`
- `/assistente-ia`
- `/checklists`
- `/prompts`
- `/diario-oficial`
- `/assinaturas`
- `/workflow`
- `/sociedade`
- `/ramos`
- `/ramos/:slug`
- `/office-contracts`
- `/atividades`
- `/financeiro`
- `/despesas`
- `/datajud`
- `/crm-leads`
- `/whatsapp`

## Observacoes tecnicas

- O grafo atual e completo para codigo fonte e estrutura AST do EJC.
- A etapa de extracao semantica com LLM externo nao foi reexecutada porque nao ha chave configurada nesta sessao e nao foi exposta nenhuma credencial.
- Existe cache semantico local em `graphify-out/cache/semantic`, mas o relatorio final usado como fonte nesta auditoria e o `GRAPH_REPORT.md` atual, regenerado em 2026-07-02 as 09:58.
- `graphify-out/` esta ignorado no Git por ser artefato regeneravel.

## Proximo passo recomendado

Usar `graphify-out/GRAPH_REPORT.md` como fonte primaria para continuar a auditoria incremental: rotas quebradas, duplicacoes, funcoes orfas, lacunas IA/RAG, inconsistencias frontend/backend/banco e testes funcionais com dados ficticios.
