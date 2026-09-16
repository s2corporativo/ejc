# Workflow - Preparar correção segura

Use este fluxo para bug, regressão, falha de CI ou ajuste funcional do EJC.

## Passos

1. Escolher o modelo adequado em `docs/ia/tarefas/`.
2. Reproduzir ou confirmar a falha com evidência.
3. Registrar problema em `docs/ia/PROBLEMAS_CONHECIDOS.md` quando for recorrente, crítico ou ainda não resolvido.
4. Localizar implementação existente e todos os chamadores.
5. Implementar a menor alteração suficiente.
6. Criar ou ajustar teste quando tecnicamente possível.
7. Executar tarefa do IDE compatível com o risco da alteração.
8. Revisar diff e remover alterações acidentais.
9. Preparar PR com evidência, risco residual, impacto jurídico/LGPD e rollback.

## Validações comuns

- Docs-only: declarar sem portão técnico.
- Frontend: `Verificar: Frontend`.
- Backend: `Verificar: Backend`.
- Banco/Alembic: `Verificar: Banco e Migrations`.
- Segurança: `Verificar: Seguranca`.
- CI: `CI: Simular Localmente`.
