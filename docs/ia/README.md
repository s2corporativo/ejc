# IA para desenvolvimento - EJC

Este documento orienta agentes como Antigravity, Codex e Claude ao corrigir ou evoluir o EJC. Ele nao substitui a governanca canonica.

## Precedencia

1. `docs/GOVERNANCA_IA.md`
2. `CLAUDE.md`
3. `AGENTS.md`
4. `.agent/rules/*.md`
5. `docs/FLUXO_DE_DESENVOLVIMENTO.md`
6. `docs/CRITERIOS_DE_ACEITE.md`
7. Este arquivo

Se houver divergencia, siga a governanca canonica e registre a harmonizacao no PR.

## Sistema

O EJC e um sistema juridico full-stack para casos/processos, clientes, prazos, documentos, financeiro, portal do cliente e nucleo de IA juridica. A stack principal e FastAPI, React/TypeScript, PostgreSQL, pgvector, Redis/Celery e Docker Compose.

## Fluxo para agentes

1. Confirme repositorio, remoto, branch e estado do Git.
2. Verifique PRs concorrentes antes de editar arquivos.
3. Leia as instrucoes canonicas do projeto.
4. Localize backend, frontend, rotas, services, models, migrations, testes e scripts existentes.
5. Identifique causa raiz antes de editar.
6. Faca a menor alteracao suficiente.
7. Revise `git diff`.
8. Rode a validacao proporcional ao diff.
9. Use Issue, branch e Pull Request; nao faca push direto em `main`.

## Comandos de verificacao

| Mudanca | Comando |
|---|---|
| Documentacao/comentarios | Sem portao tecnico; declare `docs-only` no PR |
| Apenas frontend | `cd frontend && npm run lint && npm test && npm run build` |
| Backend sem banco/models/services/routers compartilhados | `cd backend && ruff check app && pytest <area alterada>` |
| Backend antes do push, quando aplicavel | `cd backend && pytest` |
| Banco, models, migrations ou seeds | Backend + `alembic upgrade head` em PostgreSQL 16 com pgvector local |
| Cruza backend e frontend | Rode os portoes de ambos |

## Protecoes

- Nao acessar `/opt/ejc` nem banco de producao.
- Nao versionar segredo, credencial, token, senha, PII ou documento real de cliente.
- Nao enfraquecer RBAC, HITL, gate de citacoes, sanitizacao de PII, isolamento de dados ou kill-switch de IA.
- Toda chamada de IA passa pelo gateway institucional.
- Migration destrutiva exige backup, teste de restauracao e decisao humana registrada.
- Nao apresentar hipotese juridica ou tecnica como fato sem evidencia.

## Entrega esperada

O template de PR e a evidencia local sao o relatorio da entrega. Informe causa, escopo, arquivos alterados, validacoes, impacto juridico/LGPD, riscos residuais e rollback.
