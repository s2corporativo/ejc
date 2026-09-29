# Diagnóstico das 10 falhas residuais (13/08/2026) — pós-reset do sandbox

Ambiente reconstituído: clone da branch `consolidation/consolidacao-ux-20260812` (a6d07cb1), PostgreSQL 16 + pgvector, usuário ejc, DB ejc com 146 tabelas (alembic 0→140), .env recriado (DATABASE_URL + DATABASE_URL_SYNC), pip deps instaladas (com botocore==1.34.162, pin corrigido), npm install frontend ok, scripts/env_run.py recriado.

## Grupo 1 — test_citation_gate_hardening.py (4 falhas)

Contrato final do código (`app/services/citation_gate.py`, P0.1 `7e0b3b38`): **artigo bloqueia SEMPRE** quando `identificada` (linha 110, sem guarda `modo_estrito`) — artigo só é aprovado com confirmação positiva na base legislativa. Flag `CITACOES_MODO_ESTRITO` continua governando SÓ súmulas (linha 129).

- `test_avaliar_bloqueantes_modo_estrito_off_ignora_sumula_artigo_ausentes` (linha 251): espera [] em OFF com {identificada sumula, identificada artigo}. Esperado: artigo bloqueia sempre → corrigir teste para aceitar artigo bloqueante em ambos os modos, súmula só em ON.
- `test_avaliar_bloqueantes_modo_estrito_on_bloqueia_sumula_artigo_ausentes` (linha 260): espera 'modo estrito' no motivo do artigo — mas o motivo do artigo (linha 112) NÃO menciona modo estrito. Corrigir: permitir motivo genérico para artigo + 'modo estrito' para súmula.
- `test_validar_citacoes_estrito_off_artigo_ausente_nao_bloqueia` (linha 315): E2E — artigo ausente em OFF NÃO deve bloquear no teste, mas o código bloqueia sempre. Corrigir teste para esperar bloqueio do artigo (não da sumula) e sem 'modo estrito'.
- `test_validar_citacoes_estrito_off_sumula_ausente_nao_bloqueia` (linha 296): E2E com TEXTO_SUMULA_PLAUSIVEL_AUSENTE — sumula 500 STJ (dentro da faixa ≤676), _DBVazio → status 'identificada' (linha 526 verificador). Em OFF não bloqueia → deve passar. VERIFICAR se é esta que falha — o erro real foi do artigo (relatorio mostra 'art. 999 CDC'). O OFF-sumula provavelmente passa (falha reportada era o artigo); a 4ª falha é `test_validar_citacoes_estrito_on_artigo_ausente_bloqueia` (linha 323): espera `b.tipo == "artigo" and 'modo estrito' in b.motivo` — motivo do artigo não tem 'modo estrito' → corrigir asserção (aceitar artigo sem 'modo estrito').

Correção comum: nos 4 testes, artigo `identificada` é sempre bloqueante (motivo sem 'modo estrito'); súmula `identificada` bloqueia só em ON com 'modo estrito' no motivo.

## Grupo 2 — test_rag_vigencia_prearm_workflow.py (3 falhas)

Workflow `.github/workflows/deploy-vps.yml` mudou; testes são brittle text-matching:
- `test_preflight_pos_ativacao_ocorre_antes_de_tocar_producao` (linha 65): espera índice `.rag_vigencia_activated_v1` DEPOIS do passo "Confirmar SHA..."; no workflow real, o marker `activated_marker` aparece DENTRO do passo preflight (linha 83: `activated_marker="$APP_DIR/data/.rag_vigencia_activated_v1"`) e o trecho indexado '.rag_vigencia_activated_v1' após inicio_passo é o `if sudo test -f "$activated_marker"`. VERIFICAR ordem real dos índices. Erro anterior: `AssertionError: assert 'ela pode até estar parcial' in ...`?? Não — teste 172. Linha 73: `assert inicio_passo < indice_marker < indice_sync < indice_deploy < indice_prearm` — verificar ordem real: preflight → sync (170) → deploy (178/185?) → prearm (191). A ordem real no workflow: `Confirmar SHA e runtime de produção` (69) → `Classificar migrations pendentes` (115) → `Anexar decisão de migration` (160) → `Sincronizar e implantar sob mutex host-level` (170) → `Verificação local e pública pós-deploy` (178) → `Smoke test pós-deploy` (185) → `Pré-armar gate` (191) → `Resumo` (334) → `Registrar SHA implantado` (369).
- `test_interrupcao_antes_da_flag_remove_backup_sem_restaurar_copia_parcial` (linha 161): espera string `"ela pode até estar parcial"` na função `finalizar()` — workflow real não tem essa frase (backup rollback é "restaurando .env a partir do backup 0600"). Corrigir asserção para o texto real OU é prova de comportamento ausente no código.
- `test_prearm_usa_o_mesmo_target_sha_registrado_pelo_deploy` (linha 243): espera `'printf \'%s\\n\' "$TARGET_SHA" | sudo tee /opt/ejc/.deployed_sha'` — workflow real registra em `/opt/ejc/.deploy_last_sha` (printf sem \n) no passo "Registrar SHA implantado" (linha 373). E teste linha 248: `'printf \'%s\\n\' "$TARGET_SHA" | sudo tee "$marker"'` — workflow real usa exatamente isso (linha 281/329). O erro é no indice_registro. Decisão: workflow mudou .deployed_sha → .deploy_last_sha mas o prearm AINDA lê `sudo cat "$APP_DIR/.deployed_sha"` (linha 252) — INCONSISTÊNCIA REAL no workflow (deploy grava .deploy_last_sha, prearm lê .deployed_sha → prearm SEMPRE falha na produção). Corrigir o workflow para ler .deploy_last_sha (com fallback) E atualizar teste.

## Grupo 3 — test_documents_*_ocr_full_hook.py (2 falhas)

- `test_event_subscriber_patch_usa_ocr_completo` (linha 14 do arquivo): espera `'documents_router._analisar_doc_bg = _analisar_doc_bg_sem_corte'` no source de event_subscribers — código não tem mais esse patch. O hook de OCR completo mudou de implementação. Verificar app/services/event_subscribers.py e app/routers/documents.py (_analisar_doc_bg) para saber a implementação atual.

## Grupo 4 — test_bloco6_lixeira_restore.py (1 falha)

- `test_listar_retorna_soft_deleted`: router trash.py `listar()` usa `await db.scalar(...)` mas o teste injeta `_FakeDB` sem método `scalar`. Router mudou (usa scalar), teste legacy. Corrigir o fake do teste adicionando `scalar()`.

## Status

- 10 falhas → 4 grupos; correções cirúrgicas com validação por bateria.
- Comandos de execução: `cd /home/ubuntu/ejc/backend && RUN_DB_TESTS=1 python3 ../scripts/env_run.py python3 -m pytest <arquivos> -q`
