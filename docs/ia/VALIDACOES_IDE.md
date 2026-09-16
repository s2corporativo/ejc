# Validacoes no IDE

As tarefas em `.vscode/tasks.json` foram criadas para o Antigravity executar comandos reais do EJC sem depender de producao.

## Tarefas principais

- `Verificar: Completo` -> roda frontend, backend e banco em sequencia
- `Verificar: Frontend` -> `cd frontend && npm run lint && npm test && npm run build`
- `Testar: Frontend` -> `cd frontend && npm test`
- `Build: Producao Frontend` -> `cd frontend && npm run build`
- `Verificar: Backend` -> `cd backend && ruff check app && pytest`
- `Testar: Backend` -> `cd backend && pytest`
- `Verificar: Banco e Migrations` -> `cd backend && python -m alembic heads && python -m alembic current`
- `Banco: Verificar Migrations Pendentes` -> `cd backend && python -m alembic heads`
- `Banco: Verificar Estado` -> `cd backend && python -m alembic current`
- `Verificar: Seguranca` -> `cd backend && gitleaks detect --no-git --redact && pip-audit -r requirements.txt`
- `CI: Simular Localmente` -> `bash scripts/ci-local.sh`
- `Rotas: Verificar Ledger` -> `python backend/scripts/ledger_rotas.py --verificar`

## Observacao

Validacao destrutiva, migration real ou teste contra producao continua proibido sem decisao humana e backup verificavel.
