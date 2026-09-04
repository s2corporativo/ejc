# GitHub Actions arquivados — 2026-08-31

Este diretório preserva os workflows anteriormente ativos em `.github/workflows/` para auditoria, rollback e eventual migração controlada.

## Motivo da desativação

O repositório apresentava execuções sintéticas com `path: BuildFailed`, `conclusion: startup_failure`, zero jobs e workflow fantasma `332799264`. O problema ocorria antes da criação de qualquer job e persistiu após a remoção dos workflows legados/duplicados, portanto não era uma falha de teste ou de runner.

O CI oficial do EJC permanece definido em `.woodpecker.yml` e executado pelo Woodpecker self-hosted. Os arquivos abaixo não devem retornar para `.github/workflows/` sem uma reativação deliberada do GitHub Actions e um teste mínimo que prove que o registro fantasma foi eliminado.

## Conteúdo

Foram arquivados tanto workflows operacionais quanto workflows históricos/temporários, preservando exatamente os blobs Git existentes. Entre os históricos já identificados estavam as ondas de refatoração de arquitetura, o inventário de arquitetura e o Frontend CI duplicado.

## Critério para reativação futura

1. Confirmar no GitHub que o workflow fantasma `BuildFailed` deixou de ser gerado.
2. Restaurar apenas um workflow mínimo e manual.
3. Confirmar criação de job real e ausência de `startup_failure` sintético.
4. Migrar de volta somente os workflows ainda necessários, um a um.
5. Não reativar workflows temporários ligados a branches inexistentes.

Enquanto esses critérios não forem satisfeitos, `.github/workflows/` deve permanecer vazio/ausente e o Woodpecker deve ser a esteira oficial de CI.
