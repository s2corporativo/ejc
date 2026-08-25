# Atualização CuidarVet — decomposição segura da antiga PR #47

**Data:** 2026-08-25 BRT  
**Repositório:** `s2corporativo/cuidar-vet-plataforma`

## Contexto

A PR #47 (`audit/forensic-cuidar-vet-20260821`) acumulou **101 commits e 73 arquivos**, ficando incompatível com merge em bloco após a evolução da `main`. A estratégia canônica passou a ser extrair cada correção ainda válida para sucessoras pequenas, baseadas na `main` atual, sem cherry-pick cego e sem reescrever migrations históricas.

Nenhuma das sucessoras abaixo executou migration, importação, escrita de banco real ou deploy.

## Sucessoras extraídas

| PR | Domínio | Escopo | Estado |
|---|---|---:|---|
| #54 | migrations operacionais | remove DDL de runtime, formaliza módulos em `0027` | draft / gates pendentes |
| #56 | RBAC de rota | query/hash, alias `/prontuario`, decisão fail-closed | draft / gates pendentes |
| #57 | comércio/financeiro | tenant de tutor/catálogo + compare-and-set na baixa de conta | draft / gates pendentes |
| #58 | uploads | magic bytes/UTF-8 para clínico, importação e PDF fiscal | draft / gates pendentes |
| #59 | notificações | filtra alerta pela permissão do módulo de origem | draft / gates pendentes |
| #60 | superfície HTTP | headers, body genérico 5 MB, health/readiness DB | draft / gates pendentes |
| #61 | LLM | timeout, retries só transitórios, erro sanitizado | draft / gates pendentes |
| #62 | RBAC IA clínica | `clinical_ai.*` depende de `records.*` | draft / gates pendentes |

A PR #55 NuvemVet é uma frente separada, sucessora da antiga #49 e empilhada sobre #54 (`0028_nuvemvet_report_rows`).

## Achados confirmados ainda não extraídos

### P1 — validade de estoque

A `main` ainda aceita `openingExpiryDate` e `expiryDate` no passado tanto no estoque inicial do catálogo quanto em `stock.receive`. A auditoria antiga já tinha `assertStockExpiryNotPast`, com comparação por data civil da clínica para evitar erro de fuso. Deve ser recuperado sem sobrescrever o `operations.ts` atual, que recebeu mudanças posteriores do Compêndio.

### P1 — relações clínicas do NextGen

A branch antiga contém guards para assegurar coerência entre clínica/tutor/paciente e `appointmentId`/`clinicalRecordId`/ticket. O `nextGen.ts` atual ainda possui validações locais parciais. Como o arquivo é amplo e mudou em várias frentes, a extração deve ser feita separadamente, preferencialmente sobre a sucessora #57 que já introduz `scopeGuards.ts`.

### P1/P2 — dashboard por permissão de módulo

`operations.dashboard` exige `dashboard.view`, mas agrega agenda, tickets, estoque, retornos clínicos e faturamento. A auditoria antiga propunha ocultar consultas/valores de módulos para os quais o usuário não possui permissão específica. Exige reconciliação cuidadosa no `operations.ts` atual.

## Resíduos de menor prioridade

Ainda precisam ser classificados contra a `main`:

- workflows de atendimento/exames;
- regras FEFO/estoque além de validade;
- busca global;
- analytics do frontend;
- code splitting;
- navegação de alertas;
- verificações antigas de CI/journal que possam ter sido substituídas pelo `CLAUDE.md` e pela guarda atual de migrations.

## Regra de integração

Nenhuma sucessora deve sair de draft sem evidência no **SHA exato** conforme a governança atual do CuidarVet:

```text
pnpm check
pnpm test
pnpm build
```

Testes direcionados podem ser usados durante a iteração, mas não substituem o portão completo antes de merge. GitHub Actions/Woodpecker indisponível não aprova nem reprova o código por si só.

## Estado da #47

A #47 permanece aberta apenas como fonte forense até que os resíduos acima sejam classificados ou extraídos. **Não deve ser mesclada como unidade.** Quando cada bloco relevante tiver sucessora ou comprovação de que já foi absorvido/descartado, a #47 poderá ser fechada como supersedida.
