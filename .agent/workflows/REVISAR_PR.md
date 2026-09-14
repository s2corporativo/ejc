# Workflow - Revisar Pull Request

Use este fluxo para auditar PR antes de aprovar, corrigir ou mesclar.

## Verificações

1. Confirmar número, título, autor, branch de origem, branch de destino e objetivo declarado.
2. Ler o diff completo e identificar módulos afetados.
3. Verificar conflitos, checks, testes, impacto jurídico/LGPD, banco, segurança e deploy.
4. Procurar PRs concorrentes que alterem o mesmo contrato, módulo, rota, permissão ou migration.
5. Validar se o PR usa modelo de tarefa, critérios de aceite e rollback.
6. Classificar como pronto, pronto após correções, bloqueado, obsoleto, duplicado, deve ser dividido ou exige decisão humana.

## Saída

- Achados por severidade
- Comandos executados
- Evidência sanitizada
- Recomendação de merge ou correção
- Riscos residuais
