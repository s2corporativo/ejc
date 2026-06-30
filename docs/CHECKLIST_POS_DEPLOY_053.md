# Checklist de verificação pós-deploy — EJC correções 053/054
**Data:** 28/06/2026 · Marque cada `[ ]` ao confirmar. Cada item aponta o achado da auditoria que valida.

> Ordem: **A → B → C → D → E**. Se algo falhar, vá direto para **F (Rollback)**.
> Tudo roda na VPS a partir de `/opt/ejc`. SSH: `ssh -i /c/Users/CLOVI/.ssh/ejc_deploy root@13.140.167.153`

---

## A. Pré-deploy (antes de mudar qualquer coisa)
- [ ] **A1.** Estou em `/opt/ejc` e os containers EJC estão de pé: `docker ps | grep -E 'ejc_backend|ejc_db|ejc_frontend'` (3 linhas).
- [ ] **A2.** O sistema-s2 NÃO será tocado: `docker ps | grep deployment-` existe e ficará intacto.
- [ ] **A3.** Extraí o zip corrigido num staging, ex.: `unzip ejc_project_CORRIGIDO_v6.6_*.zip -d /opt/ejc_corrigido`.
- [ ] **A4.** Espaço em disco ok: `df -h /` (< 85% usado).
- [ ] **A5.** Rodei o **DRY-RUN** e revisei a saída sem erros:
      `DRY_RUN=1 SRC=/opt/ejc_corrigido/ejc_project bash scripts/aplicar_correcoes_053.sh`

## B. Deploy + backup (o script faz o backup automático ANTES de tudo)
- [ ] **B1.** Executei sem dry-run: `SRC=/opt/ejc_corrigido/ejc_project bash scripts/aplicar_correcoes_053.sh`
- [ ] **B2.** O backup pré-mudança foi criado e NÃO está vazio: `ls -lh /opt/ejc/backups/pre_053_*.sql.gz` (Regra 10). **Anote o nome:** `________________`
- [ ] **B3.** O script terminou sem erro e imprimiu o comando de rollback.

## C. Banco — migration aplicada e schema reproduzível (valida P0-4 / Fase 0 e 4)
- [ ] **C1.** Head do Alembic = `054_victory_vault`:
      `docker compose exec backend sh -c 'cd /app && alembic current'`
- [ ] **C2.** As tabelas antes ausentes existem agora (esperado: todas listadas):
      ```
      docker exec -i ejc_db sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -tAc "
      SELECT tablename FROM pg_tables WHERE tablename IN
      (''caso_areas'',''bank_analyses'',''bank_transactions'',''bank_abusive_charges'',
       ''kanban_columns'',''areas'',''agenda_eventos'',''client_pending_items'',
       ''domain_events'',''office_contracts'',''office_expenses'',''partner_withdrawals'',
       ''teses_vitoriosas'',''modelos_documentos'') ORDER BY 1;"'
      ```
- [ ] **C3.** A view existe: `... "SELECT 1 FROM pg_views WHERE viewname=''vw_atividades'';"` retorna 1.
- [ ] **C4.** Colunas novas em `cases`: `... "SELECT column_name FROM information_schema.columns WHERE table_name=''cases'' AND column_name IN (''kanban_column'',''case_type'',''sync_pending'',''has_judicial_process'');"` retorna 4.

## D. Backend — saúde e rotas antes quebradas (valida P0-1/P0-2/P0-3 / Fases 1 e 4)
- [ ] **D1.** Health ok: `curl -s http://localhost:8000/api/health` → `{"status":"ok",...,"database":true}`
- [ ] **D2.** Obter token (login real):
      `TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/json' -d '{"email":"<seu_email>","password":"<sua_senha>"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')`
- [ ] **D3.** Rodei o smoke-test e **0 itens ✗**:
      `TOKEN="$TOKEN" bash scripts/smoke_test_053.sh`
- [ ] **D4.** (P0-1) As rotas de duplo-prefixo NÃO dão mais 404 — confirmado pelo smoke-test: DataJud, Despesas, Retiradas, Contratos, Kanban, Curadoria, Mediação.
- [ ] **D5.** (P0-2/P0-3) IA não dá 500 por método/import: Jurimetria preditiva, Intelligence-v3, Cérebro respondem (2xx).
- [ ] **D6.** (P1-1) Victory Vault SEM token = **401** (não 200):
      `curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/api/victory_vault/teses` → **401**
- [ ] **D7.** (Fase 4) Persistência: criar uma tese e confirmar que sobrevive:
      ```
      curl -s -X POST http://localhost:8000/api/victory_vault/teses -H "Authorization: Bearer $TOKEN" \
        -H 'Content-Type: application/json' \
        -d '{"titulo":"TESTE DEPLOY","ementa":"x","area_juridica":"Cível","data_vitoria":"2026-06-28"}'
      docker compose restart backend && sleep 5
      curl -s "http://localhost:8000/api/victory_vault/teses?query=TESTE%20DEPLOY" -H "Authorization: Bearer $TOKEN"
      ```
      A tese deve aparecer **após o restart** (antes se perdia). Depois apague-a se quiser.
- [ ] **D8.** Sem erros no log: `docker compose logs --tail=80 backend | grep -iE 'error|traceback'` (idealmente vazio).

## E. Frontend — build e UI (valida P2-2 / Fases 3 e 4c)
- [ ] **E1.** Build passou (rodado pelo script ou manual): `docker compose build frontend && docker compose up -d frontend` SEM erro de `tsc`/`vite`. ⚠️ Se o build falhar no `tsc`, me avise o erro — corrijo.
- [ ] **E2.** Login funciona em https://ejc.depaulateixeira.adv.br
- [ ] **E3.** Menu **Inteligência → "Victory Vault"** aparece e abre `/victory-vault`.
- [ ] **E4.** Aba **Acervo**: lista teses (deve mostrar pelo menos as de demonstração via auto-seed) sem erro no console (F12).
- [ ] **E5.** Aba **Veredito IA**: preencher tese + área + tribunais → "Analisar" retorna probabilidade/teses/sugestões (sem 404/401).
- [ ] **E6.** Aba **Escrita Assistida**: lista templates; gerar documento de um template retorna texto.
- [ ] **E7.** (P0-1) Módulos financeiros/processuais carregam sem 404 no console: **Processos (DataJud)**, **Despesas**, **Kanban** dentro de um caso, **Contratos**, **Retiradas de sócios**.
- [ ] **E8.** (cache) Atualização aparece sem hard-refresh (nginx serve `index.html` com `no-cache`).

## F. Rollback (somente se B–E falhar de forma bloqueante)
- [ ] **F1.** Restaurar banco do backup do B2:
      `gunzip -c /opt/ejc/backups/pre_053_<DATA>.sql.gz | docker exec -i ejc_db psql -U $POSTGRES_USER -d $POSTGRES_DB`
- [ ] **F2.** As migrations 053/054 são idempotentes e não destrutivas no upgrade; se necessário reverter só a feature do Vault: `alembic downgrade 053_reconcile_schema` (dropa só `teses_vitoriosas`/`modelos_documentos`/view).
- [ ] **F3.** Restaurar imagem/código anterior (se você fez rebuild) a partir do snapshot `/opt/ejc/backups/code_running_*.tar.gz`.
- [ ] **F4.** `docker compose restart backend frontend` e revalidar D1/E2.

## G. Encerramento (fix durável)
- [ ] **G1.** Tudo verde em C–E → **commitar o working tree** no git de `/opt/ejc` (resolve o risco "git HEAD ≠ imagem em produção"):
      `cd /opt/ejc && git add -A && git commit -m "fix: auditoria 28/06 — schema 053/054, rotas, IA, victory vault" && git tag v6.6-corrigido`
- [ ] **G2.** Confirmar `alembic current` == `054_victory_vault` e `md5sum` do `main.py` do container == do git.
- [ ] **G3.** Guardar este checklist preenchido + o nome do backup como registro da mudança.

---

### Critério de aceite final
Deploy é considerado **OK** quando: C1–C4 ✓, D1/D3/D6/D7 ✓, E2–E7 ✓, e nenhum erro novo em D8.
Qualquer ✗ em D/E → não commitar (G1) e investigar/rollback.
