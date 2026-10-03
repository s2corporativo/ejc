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

## Verificações locais de redundância e cutover

```bash
# A partir da raiz; somente stdlib, sem executar os fontes analisados:
python scripts/check_redundancias.py
# Comparação com outro commit explícito (ex.: base de uma revisão):
python scripts/check_redundancias.py --base-ref <commit>
```

O guard compara blocos literais de 12 linhas substanciais em `backend/app`,
`frontend/src`, os scripts de backend/frontend e `scripts` com o commit
imutável pós-consolidação `1fd771af`.
Repetições preexistentes são contadas, não homologadas; novas ocorrências
reprovam mesmo dentro do mesmo arquivo. Inclui arquivos novos não ignorados;
aliases por symlink são preservados. Não detecta equivalência semântica,
blocos menores ou cópias com identificadores alterados. Complementa o
inventário de arquitetura existente. A saída contém hashes/localizações,
nunca trechos de código. Exit codes: `0` sem aumento, `1` novas cópias,
`2` erro de referência/leitura/tokenização. Não atualizar a base apenas para
ocultar achados; a revisão deve justificar a exceção/consolidação.

Benchmark, bloqueios e retirada futura dos espelhos:
[`PRELIMINARES_CUTOVER_171.md`](PRELIMINARES_CUTOVER_171.md).

## Observacao

Validacao destrutiva, migration real ou teste contra producao continua proibido sem decisao humana e backup verificavel.
