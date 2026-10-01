# Congelamento funcional do Financeiro

Vigência: 2026-10-01.
Término inicial: 2026-10-08.

O módulo Financeiro entra em período de estabilização operacional após a
padronização de ledger, governança, GED, conciliação, comissões e fechamento.

Durante este período são aceitas apenas alterações de:

- correção de defeitos observados em uso real;
- integridade e reconciliação de dados;
- segurança, sigilo e auditoria;
- desempenho, acessibilidade e responsividade;
- testes e observabilidade sem mudança de regra de negócio.

Não criar novas abas, entidades financeiras, estados, providers, cálculos ou
fluxos paralelos sem decisão explícita de produto e prova de que a capacidade
não cabe no modelo canônico existente.

Acompanhamento mínimo: fechamento mensal, conciliação, exceções, comprovantes
GED, comissões, distribuição societária, backup/restauração e regressão E2E.

## Gate executável

Durante a vigência, `scripts/ci_finance_feature_freeze.sh` bloqueia alterações
funcionais no núcleo Financeiro. São aceitos commits de correção, testes,
segurança, desempenho, acessibilidade, documentação e manutenção. Exceção
somente com `EJC_FINANCE_FREEZE_OVERRIDE=1`, que representa decisão explícita.

Edição de dados pelo usuário não é congelada: campos de negócio continuam
editáveis. Competência fechada exige justificativa e trilha de auditoria.
