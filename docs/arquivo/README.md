# Arquivo histórico do EJC

> **ARQUIVADO/HISTÓRICO.** Todo o conteúdo abaixo (relatórios, planos, scripts
> legados, auditorias encerradas e evidência de execução) é **registro**, não
> procedimento: descreve o estado e as decisões da época em que foi escrito e
> não deve ser seguido como instrução atual. A regra de arquivamento é idade +
> sobreposição: um documento vai para cá quando existe um documento mais novo
> que o substitui, ou quando descreve uma execução concluída.
> Os procedimentos vivos são os `RUNBOOK_*.md` na raiz do repositório e os
> documentos em `docs/`.

- `relatorios/` — laudos e relatórios datados de auditoria, execução e correção
  (`2026-08/`, `2026-09/` = faturas mensais por mês).
- `planos/` — planos, prompts e pareceres de execução já concluídos ou substituídos
  (o plano mestre vigente é `docs/PLANO_MESTRE_STATUS.md`).
- `operacao/` — runbooks antigos de operação substituídos pelos da raiz.
- `scripts_legado/` — scripts de deploy/atualização fora de uso.
- `ci/` — workflows do GitHub Actions desativados em 31/08/2026 (o CI ativo é
  Woodpecker, `.woodpecker.yml`); mantidos como registro dos gates removidos.
- `auditoria_e2e/` — auditoria E2E encerrada (relatório referenciado em
  `relatorios/RELATORIO_PENTE_FINO_E2E_2026-08-30.md`).

O grafo arquitetural **não** é versionado: é regenerado por
`scripts/generate_architecture_inventory.py` (`graphify-out/` e
`docs/audit/inventory/*.csv|json` são ignorados pelo Git; veja `.gitignore`).
