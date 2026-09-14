# Prompt mestre - corrigir sistemas no GitHub

Use esta regra quando eu pedir ao Antigravity para corrigir o EJC ou qualquer outro sistema GitHub aberto neste IDE.

## Idioma

- Responda em portugues do Brasil.
- Use postura tecnica, conservadora e objetiva.
- Pergunte antes quando houver ambiguidade relevante ou risco juridico, operacional ou de dados.

## Fluxo obrigatorio

1. Identifique o repositorio alvo pelo nome, pasta aberta ou remoto GitHub.
2. Confirme caminho local, remoto `origin`, branch atual e estado do Git.
3. Leia `docs/GOVERNANCA_IA.md`, `AGENTS.md`, `CLAUDE.md`, `.agent/rules/*.md`, `.agents/rules/*.md`, `README.md` e `docs/ia/README.md` quando existirem, com prioridade para o Contrato de Execucao Permanente.
4. Consulte `docs/ia/PROBLEMAS_CONHECIDOS.md` e escolha o modelo adequado em `docs/ia/tarefas/`.
5. Pesquise backend, frontend, rotas, services, models, migrations, scripts e workflows existentes antes de alterar.
6. Corrija a causa do defeito com a menor mudanca suficiente.
7. Rode a validacao definida no repositorio ou a tarefa equivalente em `.vscode/tasks.json`.

## GitHub

- Nao faca push direto em `main` ou `master`.
- Use branch propria e Pull Request.
- Nao use force push, `git reset --hard`, `git commit --no-verify` ou comandos destrutivos sem confirmacao explicita.
- Se usar `gh`, verifique `gh auth status` antes de operacoes GitHub. Se nao estiver autenticado, reporte e pare.

## Protecoes do EJC

- Preserve sigilo, LGPD, dados de clientes, dados processuais, documentos e perfis de acesso.
- Nao invente dados juridicos, datas, andamentos, valores, prazos ou resultados de teste.
- Se a alteracao envolver banco, migrations, seed, autenticacao ou documentos, trate como mudanca de alto risco e valide de forma especifica.

## Entrega

Informe modelo de tarefa usado, causa, arquivos alterados, testes/validacoes, riscos restantes e rollback quando aplicavel.
