# Estado da correção das 10 falhas residuais (13/08/2026)

**Branch:** `consolidation/consolidacao-ux-20260812` · **PR #1115** · Commit `9dd93ca4` (10 correções committed, NÃO pushado ainda).

## Resumo
Corrigidos os 4 grupos (10 falhas): citation gate ×4 (testes realinhados ao P0.1 — artigo identificada bloqueia sempre; súmula só em modo estrito), prearm deploy ×3 (workflow deploy-vps.yml lia `.deployed_sha` obsoleto → corrigido para `.deploy_last_sha`; testes realinhados), OCR hook ×1 (hook centralizado em document_analysis_hook, OCR integral), lixeira ×1 (_FakeDB ganhou scalar/scalars). Commit 9dd93ca4 inclui requirements.txt (botocore==1.34.162, pin real: 1.34.165 nunca existiu no PyPI — necessário para pip install) e docs/consolidacao/DIAG_10_FALHAS_RESIDUAIS.md.

## Pendência atual (após bateria completa com 2 novas falhas)

Bateria completa: 2 failed, 5276 passed, 237 skipped, 79 subtests, 2min16s. As 2 novas falhas são colaterais da correção .deployed_sha→.deploy_last_sha:

1. `tests/test_deploy_vps_preflight.py::test_prearm_mutavel_reutiliza_mesmo_mutex_e_confere_sha_implantado` (linha 112) — JÁ CORRIGIDA no working tree (assertion atualizada para .deploy_last_sha).
2. `tests/test_deploy_vps_preflight.py::test_registro_de_sha_acontece_dentro_do_executor_bloqueado` (linhas 116-122) — lê DEPLOY_SCRIPT = `scripts/deploy_vps_safe.sh`, que GRAVA `.deployed_sha` (linhas 52, 322-323) e `deploy_workflow_transaction.sh` linha 68 tem `--exclude '.deployed_sha'`. **Precisa alinhar deploy_vps_safe.sh para .deploy_last_sha** (o workflow idempotência, linha 57, e o prearm corrigido, linha 253, leem .deploy_last_sha) + atualizar teste para .deploy_last_sha + possivelmente o exclude no deploy_workflow_transaction.sh.

## Após isso
- Commit (amend ou novo) → push → comentário no PR → reexecutar bateria completa → confirmar 0 falhas → relatório final.
- Frontend vitest: 549/549 PASS antes (manter; rodar de novo ao final se possível).
- Ambientes: /home/ubuntu/ejc cloned, PostgreSQL rodando (user ejc/db ejc, vector extension, 146 tabelas), .env recriado, deps instaladas. Comandos: `cd /home/ubuntu/ejc/backend && RUN_DB_TESTS=1 python3 ../scripts/env_run.py python3 -m pytest ... -q`; bateria completa: `python3 ../scripts/env_run.py python3 -m pytest -q > /tmp/pytest_full_v3.txt 2>&1`.
- PR #1115: https://github.com/s2corporativo/ejc/pull/1115 ; criar comentário de atualização via `gh pr comment 1115 --body "..."`.
