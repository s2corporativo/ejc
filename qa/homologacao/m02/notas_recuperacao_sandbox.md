# Recuperação pós-reset do sandbox (16/08/2026) — ESTADO ATUAL

## Ambiente reconstruído
- PostgreSQL 16 + pgvector + pg_trgm (extensões criadas no banco ejc); Redis rodando.
- User/banco: ejc/ejc; DATABASE_URL no .env local (gerado por prep_local_env.py).
- Backend deps instaladas (sudo pip3 install -r backend/requirements.txt).
- Migrations: fresh DB, alembic upgrade head = 142→143→144→145 OK (widening consolidado na 143 provado).
- uvicorn rodando porta 8000 (/api/health/ready 200).
- Branch atual: homologacao-m07-2026-08-16 (base = origin/homologacao-m06-clientes-2026-08-15, commit 22c8f675).

## Remoto
- Pushadas: homologacao-m04 (ec50b21a), m05 (7c516200), m06 (22c8f675). m04 contém correção M02 fc6dfb7d (com 144a SEPARADA).
- NÃO pushadas: m02 própria, m07, m08, m09, m10, m11. GH_TOKEN OK.

## Estado git local (arquivos modificados não commitados)
- M 143/144/145 (consolidados, cadeia 142→143→144→145), D 144a
- M scripts/check_migration_compatibility.py (human_reviewed_drop)
- M backend/tests/test_alembic_single_head.py, test_preliminares_fundacao_schema_140.py, test_rbac_matrix.py, test_rotas_registro_explicito.py
- M test_schema_dr_parity.py (HEAD_REVISION=145_drop_orphan_db_only_columns)
- A qa/homologacao/m02/notas_m11.md, notas_recuperacao_sandbox.md, scripts/inventory/m11_versionamento_tests.py, m03_seed_test_users.py (recriado), m07_casos_tests.py (em teste)

## QA resources no DB (fresh)
- 7 usuários QA seedados (senha <ver EJC_QA_PASSWORD>): admin U-c23b7d23, socio U-4ad52bdb, advogado 4701ecbf-cf9b-422f-b75a-b906814b8213, estagiario U-4e0ee2bb, financeiro U-d2de47b1, secretaria U-5b5689e3, cliente_externo U-5f166550 (client_id=9e6cd7cd linkado).
- Cliente QA: 9e6cd7cd-148c-49c9-95cb-d61de37fe520 (EJC_QA M06 PF, criado pelo m06_clientes_tests.py, restaurado após exclusão).
- Caso QA M06: 78676e06-50d4-4f3d-81bd-e040b1f78d76 ("M06 Caso de teste").

## Resultados M06 re-executado: 23/24 PASS
- FAIL: docs_portal_cliente_autenticado (403) — Causa: cliente_externo tinha client_id NULL no banco (seed não linkava); _exigir_cliente levanta 403. CORRIGIDO via UPDATE users SET client_id. Reexecutar o teste para confirmar.

## M07 bateria (scripts/inventory/m07_casos_tests.py) — 1ª rodada 10/15 PASS
Falhas e causas:
1. "criação 201" 422 CNJ: meu gerador de DV módulo 97 está ERRADO vs app (app usa validators_service.validar_cnj/normalizar_cnj — 20 dígitos após remover pontuação). Precisa usar o mesmo algoritmo do app.
2. "busca por texto" — case nunca criado (consequência do 1); o resultado "1 resultado" indica outro caso M06? Verificar.
3. "financeiro não cria caso" 422: mesmo problema de CNJ? Não — post do financeiro não tem numero_processo; 422 = campo inválido? DEBUG: criar caso via financeiro sem numero_processo → 422 inesperado (esperado 403 de RBAC). Verificar gate do router cases POST (talvez M04 gate equipe jurídica? financeiro deveria ser 403).
4. "cliente inexistente = vazio" FAIL: busca com client_id inexistente retornou 1+ resultado. Investigar filtro client_id no GET cases (talvez ignore client_id).
5. "criação duplicada permitida" 422: de novo o CNJ do TIT (sem numero_processo?). Meu POST de duplicada não envia numero_processo — mas 422... investigar.
6. Anti-phantom leitura, edição, stats, kanban OK. Movimento: sem output (não rodou por causa do caso None).
7. Arquivamento: não rodou.

## Detalhes técnicos case.py (validação CNJ)
- _validar_numero_processo_cnj: só valida strict se normalizar_cnj(v) tem 20 chars; senão aceita texto livre <=30 chars.
- CaseCreate campos: titulo, area (enum CaseArea validado), client_id, prioridade, proxima_acao, proxima_acao_prazo, numero_processo, tribunal, comarca, vara, parte_contraria, valor_causa, descricao_fatos, advogado_responsavel_id, tipo_acao_prescricao, data_fato_prescricao, case_type="judicial", extrajudicial_type, has_judicial_process=False, honorarios(opc).
- CaseUpdate: + status/fase/risco/tese_*/kanban_column/kanban_position.
- Rotas cases: GET /, GET /stats, POST /, GET /{id}, PATCH /{id}, POST /{id}/arquivar, POST /{id}/desarquivar, DELETE /{id}, POST /{id}/gerar-documentos, GET /{id}/movimentos, POST /{id}/movimentos, POST /{id}/sincronizar-processo, POST /{id}/encerrar, GET /{id}/teses-sugeridas, POST /{id}/analisar.
- case_partes: prefix /cases/{case_id}/partes — GET, POST (201), DELETE (204). NÃO tem PATCH na main/m06 (M08 criou).
- procuracoes: prefix /procuracoes — GET /, POST / (201), POST /{id}/minuta, POST /{id}/revogar.
- trash: POST /api/trash/{entidade}/{id}/restaurar.

## Plano
1. Corrigir gerador CNJ do m07 (usar algoritmo real: copiar de validators_service).
2. Investigar falhas 3/4/5 e corrigir bateria ou código (403 RBAC vs 422; filtro client_id).
3. M07 completo (>20 testes), commitar.
4. M08 (partes: autor/réu/terceiro/litisconsorte/representante/advogado/PF-PJ/vínculo/edição/remoção/duplicidade/integridade) — criar PATCH partes se não existir (M08 original criou).
5. M09 (procurações: cadastro/geração/outorgante/advogado/poderes/validade/vínculo/documento/download/assinatura/revogação/versionamento/auditoria).
6. M10 (documentos: upload/download/preview/metadados/tamanho/MIME/extensões/storage/URL/autorização/isolamento/exclusão/restauração + extensão dupla, MIME falso, SVG/HTML, executável, excessivo, path traversal).
7. M11: reexecutar m11_versionamento_tests.py (46/46) no ambiente novo — criar recursos QA (cliente+caso) para ele.
8. Commitar branches m07-m11 e push (GH_TOKEN OK).
9. M12 em diante (Andamentos: verificar rota /api/cases/{id}/andamentos ou similar; usar grep).

## Padrão de bateria (do m06/m11)
- tokens memoizados, sleep(18) antes de login, retry 429 sleep(45), X-Forwarded-For: 127.0.0.1
- multipart uploads: SEM Content-Type no header da sessão
- db(): psql -h localhost -U ejc -d ejc -t -A -c
- auditoria: tabela audit_logs, coluna registro_id
