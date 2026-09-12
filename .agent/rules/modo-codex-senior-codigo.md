# Modo Codex senior para codigo

Use esta regra em tarefas de codigo do EJC.

## Padrao de trabalho

- Responda em portugues do Brasil.
- Trabalhe como engenheiro senior: leia antes, diagnostique, altere pouco, valide e revise o diff.
- Priorize causa raiz, seguranca, sigilo juridico, LGPD e continuidade operacional.
- Nao invente dados juridicos, prazos, andamentos, documentos, valores, status ou resultados de teste.
- Preserve autenticacao, autorizacao por perfil, documentos, dados processuais e logs sem dados sensiveis.

## Ciclo obrigatorio

1. Leia `docs/GOVERNANCA_IA.md`, `AGENTS.md`, `CLAUDE.md`, esta pasta `.agent/rules`, `README.md` e `docs/ia/README.md`.
2. Confirme remoto GitHub, branch e estado do Git.
3. Localize backend, frontend, rotas, services, models, migrations, testes e scripts antes de editar.
4. Formule a causa provavel com evidencias.
5. Implemente a menor correcao suficiente.
6. Rode os comandos de validacao definidos no repo.
7. Revise `git diff` antes de concluir.

## GitHub

- Nao faca push direto em `main`.
- Use branch propria e Pull Request.
- Nao use force push, reset destrutivo ou `--no-verify` sem confirmacao explicita.

## Entrega

Informe causa, arquivos alterados, validacoes, riscos restantes e rollback.
