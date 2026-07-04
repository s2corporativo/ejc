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

Em toda sessão neste repositório, use o agente `ejc` como PRIMEIRO ponto de contato para qualquer tarefa não trivial — ele já sabe orquestrar os demais agentes e skills abaixo. Não faça o trabalho inteiro na thread principal quando `ejc` (ou um especialista mais específico) puder ser acionado.

SEMPRE delegue trabalho ao agente especialista pertinente em vez de fazer tudo na thread principal. Tarefas que cruzam áreas devem acionar TODOS os agentes pertinentes (em paralelo quando independentes):

- `ejc` — orquestrador principal; ponto de entrada padrão para qualquer tarefa no repo.
- `backend-fastapi` — qualquer mudança em backend/app (endpoints, services, models, schemas, auth, RAG).
- `frontend-react` — qualquer mudança em frontend/src (páginas, componentes, stores, api client, estilos).
- `db-migrations` — schema, migrations Alembic, índices, seeds, pgvector.
- `security-auditor` — SEMPRE acione após mudanças em autenticação, permissões, uploads ou configuração (somente leitura, reporta achados). É o caminho canônico de revisão de segurança no EJC — não use a skill genérica `security-review` isolada, para não gerar relatórios duplicados/divergentes.
- `qa-tests` — escrever/rodar testes após mudanças de comportamento e diagnosticar falhas.
- `app-runner` — sobe e navega a stack (backend+frontend) para validar UI/UX no navegador.
- `ci-triage` — diagnostica falhas do CI (.github/workflows/ci.yml: pytest backend, validação schema/RAG com Postgres pgvector, typecheck+build frontend), lê logs e aplica a correção mínima.
- `code-reviewer` — skill `code-review`; revisa o diff atual em busca de bugs e simplificações.
- `verifier` — skill `verify`; exercita o fluxo alterado ponta a ponta antes de dar por concluído.
- `simplifier` — skill `simplify`; limpa reuso/eficiência/abstração depois que a feature já funciona.
- `researcher` — skill `deep-research`; pesquisa externa multi-fonte (nunca para entender o próprio código do EJC).

Fluxo padrão para uma feature: graphify query → `ejc` (ou agente(s) de implementação pertinente(s) diretamente) → `qa-tests` → `security-auditor` (se tocou área sensível) → `code-reviewer` → `verifier` → `simplifier`. Inclua a regra do graphify no prompt de todo subagente que explora código.
