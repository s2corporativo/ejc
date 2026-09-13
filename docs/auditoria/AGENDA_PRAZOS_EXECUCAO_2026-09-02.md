# Agenda e Prazos — execução segura 2026-09-02

Ordem obrigatória de integração:

1. #1343 — P0 cálculo/DataJud/ownership/status/reset de alertas.
2. #1344 — P1 DJEN/origens automatizadas.
3. #1345 — #968 e migration 156 auditável.
4. #1346 — #717 prova de cálculo e quatro olhos.
5. #1347 — #1342 Agenda temporal; ativação do banco somente após novo head Alembic confirmado.
6. H06 #381/#1209 com dados fictícios e aceite humano.
7. Paridade de SHA e somente então procedimento de produção.

Nenhum PR desta cadeia pode ser integrado por cima de CI vermelho. CodeRabbit marcado como sucesso em PR draft significa revisão pulada e não substitui revisão substancial. Nenhuma credencial deve ser adicionada à homologação.

## Rollback

P0/P1: revert funcional, sem migration.

Migration 156: preferir revert funcional preservando colunas/evidências; downgrade físico somente com backup/export e avaliação de perda dos novos dados auditáveis.

#717: revert do runtime preservando snapshots já persistidos.

Agenda temporal: enquanto o PR não possuir migration/ativação, rollback é simples revert do serviço/testes. A futura migration deve ser aditiva e manter compatibilidade com `data_evento`/`hora` durante transição.
