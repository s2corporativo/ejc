# CuidarVet — fechamento da PR forense #47 — 2026-08-25 BRT

## Decisão

A PR `s2corporativo/cuidar-vet-plataforma#47` foi fechada **sem merge** após classificação completa de seus 101 commits e 73 arquivos. A branch tornou-se uma composição transversal insegura para integração em bloco e permanece apenas como evidência histórica.

## Sucessoras canônicas

- #54 — formalização de schemas/migrations operacionais;
- #55 — NuvemVet reconciliado sobre a cadeia atual;
- #56 — RBAC de rota, normalização de query/hash e fail-closed;
- #57 — integridade multi-tenant de comércio e concorrência financeira;
- #58 — validação de assinatura real de uploads;
- #59 — RBAC de alertas na geração **e** na leitura;
- #60 — hardening HTTP, limites de payload e readiness do banco;
- #61 — governança de chamadas LLM (timeout, retries e erro exposto);
- #62 — dependência IA clínica → prontuário e carregamento do contexto de permissões sem exigir `dashboard.view`;
- #63 — escopo e máquinas de estado do NextGen, empilhada sobre #57 e a reconciliar com #62;
- #64 — impedir consumo de lotes vencidos em tickets e internação;
- #65 — impedir recebimento de lotes vencidos via Compras.

## Resíduos formalizados

### #66 — P1: `operations.ts`

Não foi portado automaticamente porque o arquivo atual divergiu do ancestral da auditoria com integrações posteriores do Compêndio veterinário. Deve ser reconciliado manualmente sobre a `main` atual:

1. bloquear lote vencido em estoque manual e estoque de abertura;
2. aplicar RBAC por módulo no dashboard agregado;
3. validar datas de vacinação (aplicação não posterior à validade; próxima dose posterior à aplicação).

### #67 — P2

Backlog funcional/CI separado: busca global, code splitting, navegação contextual de alertas, analytics opcional, relatório financeiro por período e hardening futuro de CI.

## Estado de validação

As PRs sucessoras permanecem draft enquanto não houver evidência local no SHA exato conforme `CLAUDE.md` (`pnpm check`, `pnpm test`, `pnpm build`, mais testes direcionados quando aplicável). O GitHub Actions continua sem ser considerado evidência por causa do `startup_failure` de conta/runner já diagnosticado.

Nenhuma migration, importação real, escrita em banco de produção ou deploy foi executada durante esta decomposição.
