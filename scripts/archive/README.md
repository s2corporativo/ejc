# Geradores históricos

`apply_architecture_refactor_wave1.py.gz` preserva byte a byte o gerador da base
`049fd6c` (SHA-256 descomprimido
`49d7b7ee17d6daa9c3ebde2682b83886e696910c1d9c87879a9f5b56c42e9edd`).
Pode ser lido com `gzip -dc scripts/archive/apply_architecture_refactor_wave1.py.gz`.

O entrypoint `scripts/apply_architecture_refactor_wave1.py` mantém os imports e
argumentos históricos, inclusive `--check`, e carrega essa única fonte congelada.
As implementações atuais pertencem aos seus módulos no backend/frontend; o
arquivo arquivado não deve ser atualizado junto com eles.

O gerador é histórico e escreve arquivos. Seu `--check` original também aplica
transformações antes de verificar o Git e pode falhar por divergência legítima
da arquitetura atual. Reproduções desse fluxo exigem uma cópia descartável;
nenhuma aplicação foi executada na árvore compartilhada nesta correção.
O uso conhecido no CI está arquivado em
`docs/arquivo/ci/github-actions-legacy/2026-08-31/architecture-refactor-wave1.yml`.
