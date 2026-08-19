# Investigação — "Falha ao excluir caso no EJC" (2026-08-19)

## Contexto
Dr. Clovis reportou "Falha ao excluir caso no ejc". Sem mensagem de erro detalhada.
Branch: main (commit 74240aa6). Sandbox: PostgreSQL 16 local (user/db ejc, ext vector),
Redis, uvicorn porta 8000 rodando em background (log /tmp/uvicorn.log),
`.env` local do repo com chaves Fernet geradas + DATABASE_URL/DATABASE_URL_SYNC
apontando localhost, APP_ENV=development. Usuários QA via
`scripts/inventory/m03_seed_test_users.py` (senha EjcQa2026!SenhaForte).

## Descoberta central (provas executadas)
O fluxo de exclusão de caso (DELETE /api/v1/cases/{id}) está FUNCIONANDO
corretamente na main atual:

1. Bateria scripts/inventory/bateria_exclusao_lixeira.py: 25 PASS / 0 FAIL
   - C1 exclusão com motivo 200; C2 motivo ausente/curto 422; C3 dupla exclusão 404;
     C4 prazo pendente bloqueia 422 + pendências; C5 honorário pendente bloqueia;
     C6 peça protocolada bloqueia (N/A no sandbox — validação jurídica de IA exige
     AI_ENABLED; comportamento esperado); C7 honorário pago não bloqueia;
     C8 prazo concluído não bloqueia; C9 /trash?entidade=cases lista;
     C10 POST /trash/cases/{id}/restaurar 200; C11 restaurado volta à lista;
     C12 arquivar/desarquivar; C13 advogado 403, sócio 200; C14 audit log registra DELETE.
2. Bateria bateria_exclusao_caso.py: body JSON, data bytes e query string
   todos 200.
3. pytest backend tests/test_case_*: 23 passed.
4. Frontend tsc --noEmit: OK.
5. Frontend: api.delete(`/cases/${id}`, {data:{motivo}}) em Casos.tsx:479 e
   TabResumo.tsx:360 — correto (FastAPI aceita body em DELETE; verificado).

## Pontos conhecidos da UI (potenciais causas da falha percebida)
- Exclusão exige papel admin/sócio (frontend Casos.tsx:486, TabResumo.tsx:323).
- Motivo ≥ 5 caracteres exigido; sem motivo o backend responde 422 com texto:
  "Informe o motivo da exclusão (mínimo 5 caracteres) — body {...} ou query ?motivo=".
- Caso com prazo pendente / honorário pendente ou atrasado / peça protocolada:
  422 com {"mensagem": "Caso possui pendências — use arquivamento (POST /cases/{id}/arquivar)", "pendencias": [...]}
  → o toast mostra a mensagem, e o usuário pode interpretar como "falha ao excluir".
- Arquivamento é a alternativa recomendada quando há pendências.

## Ambiente sandbox (para reproduzir de novo)
- Iniciar: sudo pg_ctlcluster 16 main start; redis; uvicorn via
  scripts/inventory/env_shell.sh; migrations via alembic (backend dir).
- Correções feitas no checkout local para testar (NÃO commitar como correção de bug):
  - backend/app/core/config.py: DATABASE_URL_SYNC default → localhost:5432/ejc
    (apenas p/ ambiente local, não afeta produção que usa .env).
- Bateria salva em scripts/inventory/bateria_exclusao_lixeira.py e
  bateria_exclusao_caso.py (idempotentes, dados EJC_QA_*).

## Pendências
- Dr. Clovis não informou mensagem de erro/código exato → investigação sem
  reprodução direta da falha específica; relatório deve pedir essa info para
  diagnóstico definitivo (422 pendências vs. 403 permissão vs. falha real).
