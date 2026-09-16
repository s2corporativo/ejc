# Workflow - Inventário e diagnóstico

Use este fluxo antes de corrigir falhas amplas, revisar PRs existentes ou estabilizar o EJC.

## Entrada obrigatória

- Repositório e caminho local
- Branch-base pretendida
- Escopo do diagnóstico
- Ambiente afetado
- Evidência inicial
- Restrições conhecidas

## Passos

1. Confirmar remoto `origin`, branch atual, branch padrão e estado do Git.
2. Verificar alterações locais não commitadas e PRs abertos ou concorrentes.
3. Ler `docs/GOVERNANCA_IA.md`, `CLAUDE.md`, `AGENTS.md`, `.agent/rules/*.md`, `docs/ia/README.md` e `docs/ia/PROBLEMAS_CONHECIDOS.md`.
4. Mapear scripts, workflows, rotas, services, schemas, models, migrations, testes e mecanismo de deploy.
5. Identificar comandos reais para lint, testes, build, banco, segurança e CI.
6. Produzir tabela com item, evidência, risco e próxima ação.
7. Só depois iniciar correção em branch própria.

## Saída

- Inventário técnico resumido
- Problemas comprovados
- Riscos e bloqueios
- Comandos de validação disponíveis
- Próxima branch recomendada
