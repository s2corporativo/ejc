## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

Automation (hooks em .claude/settings.json):
- SessionStart instala o graphify (`pip3 install graphifyy`) e gera `graphify-out/` automaticamente se estiverem ausentes — em ambientes novos (Claude Code web/remoto), apenas aguarde o hook concluir.
- PostToolUse (Write|Edit em arquivos de código) roda `graphify update .` automaticamente; não é preciso rodar manualmente dentro do Claude Code.

## Agentes do projeto (.claude/agents/)

SEMPRE delegue trabalho ao agente especialista pertinente em vez de fazer tudo na thread principal. Tarefas que cruzam áreas devem acionar TODOS os agentes pertinentes (em paralelo quando independentes):

- `backend-fastapi` — qualquer mudança em backend/app (endpoints, services, models, schemas, auth, RAG).
- `frontend-react` — qualquer mudança em frontend/src (páginas, componentes, stores, api client, estilos).
- `db-migrations` — schema, migrations Alembic, índices, seeds, pgvector.
- `security-auditor` — SEMPRE acione após mudanças em autenticação, permissões, uploads ou configuração (somente leitura, reporta achados).
- `qa-tests` — escrever/rodar testes após mudanças de comportamento e diagnosticar falhas.

Fluxo padrão para uma feature: graphify query → agente(s) de implementação pertinente(s) → qa-tests → security-auditor (se tocou área sensível). Inclua a regra do graphify no prompt de todo subagente que explora código.
