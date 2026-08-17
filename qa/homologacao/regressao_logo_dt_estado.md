# Estado — Regressão pós-logomarca DT (16/08/2026, ~00:25 UTC)

## RODADA 3 (pós-logo DT) — CONCLUÍDA
- M03-M36: 35/35 HOMOLOGADO (exit 0), exceto M23 na 1ª passada
- M23 falha isolada: "ai/dossie" 403 (caso sem acesso do advogado QA) —
  MESMO padrão de carteira já corrigido em M16/M34. CORRIGIDA em
  m23_ia_central_tests.py (seleção por carteira do advogado QA via
  advogado_responsavel_id). Rerun individual: **34/34 PASS, 0 FAIL**.
- Runner: scripts/inventory/regressao_completa.py (v2, em /tmp/regressao3.log)
- Falta: commitar m23 fix + atualizar REGRESSAO_COMPLETA_FINAL.md + push.
- M22 passou (runner usa... verificar se foi o wrapper lowmem; resultado log
  regressao_m22.log)
- Logo DT não afeta APIs (asset estático) — nenhuma falha relacionada.
- Servidor uvicorn saudável no fim da rodada.

## Ambiente pronto
- Memória livre: 1,45 GB (vite/tsc mortos, caches dropados)
- Repo atualizado: b9137aa5 (logomarca DT integrada + revisão auth.py)
- Uvicorn UP (health 200), earlyoom ativo
- Runner completo existe: `scripts/inventory/regressao_completa.py`
  (v2: usa env_shell.sh, aguarda saúde/restart uvicorn antes de cada bateria,
  retry em ConnectionError)
- Logs por módulo em `qa/homologacao/` (m03..m36 .log)
- Runner: `cd /home/ubuntu/ejc_repo && nohup python3 -u scripts/inventory/regressao_completa.py > /tmp/regressao3.log 2>&1 &`
- Último report: REGRESSAO_COMPLETA_FINAL.md (34/34 OK na passada anterior)
- Cuidados conhecidos: m22 precisa de lowmem (wrapper
  scripts/inventory/run_m22_lowmem.sh — DESABILITA EMBEDDINGS durante o m22 e
  restaura depois; runner v2 chama m22 via esse wrapper? VERIFICAR no código
  do runner; na passada anterior o runner falhou no m22 e corrigi m22 depois
  manualmente — o runner atual deve usar o wrapper; se não, m22 vai crashar
  de novo e corrige-se na rodada)
- Baterias fixadas na regressão anterior: m05 (retry login), m08 (idempotente
  dedup), m16 (carteira advogado + conflitos), m17 (tok() com retry), m22
  (busca_rag wrapper), m30 (fallback taxa_minima), m31 (case_health dinâmico),
  m35 (traceback no finally), m16/m17/m31 reruns feitos manualmente.
- Resultado esperado: 34/34 PASS, logo DT não afeta APIs (asset estático).
