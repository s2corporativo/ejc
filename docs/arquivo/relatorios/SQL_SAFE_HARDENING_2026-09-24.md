# Hardening de SQL dinâmico — 2026-09-24

## Objetivo

Eliminar montagem manual de identificadores SQL nos pontos identificados pela
auditoria AUD27-P3-8 e impedir regressão, preservando RBAC, ownership, auditoria
e sem alteração de schema.

## Escopo

- `backend/app/core/sql_safe.py`
- `backend/app/routers/agenda_eventos.py`
- `backend/app/routers/pending_items.py`
- `backend/app/routers/bank_analysis.py`
- `backend/app/routers/memoria_institucional.py`
- `backend/app/routers/office_contracts.py`
- `backend/app/routers/despesas.py` (achado adicional da varredura)
- `backend/app/services/scheduler.py`
- `backend/app/services/saneamento/fusao.py` (exceção arquitetural validada por teste)

## Decisões

1. `sql_safe.py` falha fechado para tabela desconhecida.
2. Nomes de bind parameters são validados.
3. Campos gerenciados pelo sistema (`id`, `created_at`, `updated_at`,
   `deleted_at`) não podem entrar no SET genérico.
4. `IS NULL` e `IS NOT NULL` não geram bind inválido.
5. `IN`/`NOT IN` não são simulados pelo helper; exigem implementação
   explícita com bind expansível/ARRAY.
6. Listagens que só alternavam fragmentos internos passaram a consultas
   estáticas.
7. Scheduler usa mapa fechado de SELECT/UPDATE para as três flags de prazo.
8. `fusao.py` permanece fora de `sql_safe.py`: nomes são obtidos do
   `information_schema`/allowlist interna e passam por quoting integral em
   `_ident()`. Teste de regressão cobre escaping de aspas.

## LGPD e segurança

A alteração não expande dados acessíveis, não altera escopo de usuário e não
remove gates de ownership/RBAC. Valores de request continuam em bind
parameters. Logs e audit logs existentes foram preservados.

## Banco e migrations

Nenhuma migration. Nenhuma alteração de schema ou dado.

## Testes adicionados

- `backend/tests/test_sql_safe.py`: contrato unitário do helper.
- `backend/tests/test_sql_safe_usage.py`: gate de regressão dos consumidores e
  exceção documentada de `fusao.py`.

Os testes existentes de agenda, pending items, contratos/despesas e suíte
backend permanecem a prova de integração.

## Rollback

Reverter o PR integralmente. Como não há migration, rollback não exige
downgrade de banco nem restauração de dados.

## Critério de promoção

- Ruff verde.
- Pytest backend verde, incluindo testes com PostgreSQL.
- Gate Woodpecker `ci/woodpecker/pr/woodpecker` verde.
- Branch atualizada com a `main` no momento do merge.
- Sem bypass do Ruleset.
