# Hardening pós-design — 2026-08-06

## Rastreabilidade

- Base: `main` no commit `869762e9dc54794c8efd90e5b6fa36f016818e2e`.
- Design preservado: PR #726.
- Issues: #728 e #731.
- Pull request: #732.
- Branch: `codex/auditoria-hardening-pos-design-20260806`.

## Diagnóstico confirmado

A refatoração visual premium já havia sido integrada. Restavam duas lacunas objetivas:

1. a cobertura backend não era medida nem bloqueante no CI;
2. a auditoria Node bloqueava somente vulnerabilidades críticas, embora o lockfile apresentasse achados altos e moderados.

## Alterações executadas

- cobertura da aplicação backend medida por `pytest-cov`;
- piso inicial bloqueante de 65%;
- relatório XML e resumo de cobertura como artefatos do CI;
- `npm audit` elevado para o nível `high`;
- migração dos imports declarativos de `react-router-dom` para `react-router 8.3.0`;
- PostCSS atualizado para `8.5.25`;
- dependências transitivas corrigidas por regeneração controlada do lockfile, sem `--force`;
- Node alinhado em `22.22.0` no `package.json`, Dockerfile e workflows permanentes;
- executor temporário removido após concluir a validação e a publicação.

## Validação da migração frontend

A alteração foi produzida em fluxo com separação de privilégios:

- o job que executou o projeto tinha somente permissão de leitura;
- o manifesto dos arquivos permitidos foi calculado antes das mudanças;
- o lockfile foi regenerado sem `npm audit fix --force`;
- `npm ci`, Prettier, ESLint, Vitest, TypeScript/Vite e `npm audit --audit-level=high` foram aprovados antes da publicação;
- a auditoria retornou zero vulnerabilidades;
- um segundo job, sem executar o projeto, publicou apenas o artefato validado e conferido pelo manifesto.

## Segurança, LGPD e autenticação

- nenhuma migration;
- nenhuma alteração de tabela ou dado persistente;
- nenhuma regra jurídica alterada;
- nenhum segredo ou credencial incluído;
- autenticação e RBAC preservados;
- 2FA permanece disponível, mas não foi tornado obrigatório.

## Riscos residuais

- o piso de cobertura de 65% é inicial e deve crescer gradualmente, priorizando segurança, documentos, financeiro, prazos e IA jurídica;
- atualizações futuras do React Router devem repetir a regressão de navegação, portal e rotas protegidas;
- a implantação em produção somente poderá ser considerada concluída após workflow de deploy, backup e healthchecks reais.

## Rollback

Não há downgrade de banco. O rollback consiste em `git revert` do merge da PR #732, restaurando o pacote, lockfile, Dockerfile e workflows anteriores. O design da PR #726 permanece independente.

Caso haja implantação, a reversão deve ser feita pelo fluxo seguro de deploy, com backup prévio e validação de:

```text
/api/health
/api/health/ready
```
