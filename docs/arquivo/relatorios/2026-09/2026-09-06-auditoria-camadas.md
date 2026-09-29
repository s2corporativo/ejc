# EJC — Auditoria por camadas: dados, backend, IA/LGPD, frontend, testes (2026-09-06)

Complemento da auditoria de infraestrutura do mesmo dia
(`2026-09-06-auditoria-infraestrutura.md`, achados `INF-*`). Este documento
cobre as demais camadas do sistema no commit `3c4f938` da `main`.

**Método.** Quatro varreduras somente-leitura em paralelo (backend, dados,
frontend, IA/LGPD), cada uma com obrigação de citar arquivo e linha, seguidas
de conferência por amostragem de todos os achados P1 e P2 no código. Onde a
conferência contradisse a varredura, o achado foi corrigido ou rebaixado, e
isso está registrado no próprio item. Sem acesso à VPS, ao banco ou ao
runtime; `alembic`, `pytest` e `node_modules` não estão instalados neste
ambiente, então nada foi executado — só lido.

**Classificação.** P0 = risco imediato a dado ou disponibilidade; P1 = alto,
corrigir no próximo ciclo; P2 = médio; P3 = higiene/dívida.

---

## 1. Resumo executivo

| Camada | P1 | P2 | P3 | Leitura |
|---|---|---|---|---|
| Dados (`DB-*`) | 1 | 4 | 9 | Schema disciplinado (head único, guarda anti-drop, WORM na auditoria, PII de cliente cifrada); lacunas em partes do processo, trilha de auditoria e constraints. |
| Backend (`BE-*`) | 1 | 3 | 10 | Autenticação, RBAC e ownership sólidos e testados; 2FA desligado por padrão em silêncio é o item mais grave. |
| IA/LGPD (`IA-*`) | 2 | 4 | 4 | Gateway único, barreira PII e HITL existem e são bons; aprovação HITL sem exigir advogado e isolamento RAG por lista de categorias são os furos. |
| Frontend (`FE-*`) | 0 | 3 | 8 | Roteamento, portal isolado e refresh corretos; token em `localStorage`, `document.write` sem sanitização e cliente sem timeout. |
| Testes/qualidade (`TQ-*`) | 0 | 1 | 2 | 640 arquivos de teste no backend e 138 no frontend; o que falta é ESLint no gate e um lockfile só. |

**Quatro P1**, todos corrigíveis sem migration destrutiva:

1. **BE-01** — 2FA só liga com `TWO_FACTOR_AUTH_ENABLED`, variável que não existe em `.env.example` nem no compose; `REQUIRE_2FA_ROLES` é letra morta.
2. **IA-02** — `PATCH /legal-docs/{id}/aprovar` aceita qualquer papel interno; a aprovação é o que libera o protocolo judicial.
3. **IA-04** — o isolamento do RAG entre clientes depende de uma lista de quatro categorias; documento de cliente ingerido em outra categoria fica recuperável para casos de outros clientes.
4. **DB-03** — `case_partes.cpf_cnpj`, `email`, `telefone` e o campo `cid` (dado de saúde) ficam em claro, e a anonimização LGPD não os alcança.

---

## 2. Camada de dados

### DB-03 — P1 — PII de partes e dado de saúde em claro; anonimização não os alcança

`backend/app/models/case_parte.py:20-23` (`cpf_cnpj String(18)`, `email`,
`telefone` em claro), `app/models/especializado.py:377` (`cid`),
`app/models/client.py:87-99` (contato/endereço do cliente em claro).
`app/services/client_anonimizacao.py:68-87` anula só colunas de `clients`
e não referencia `case_partes`. Contraste: `clients.cpf`/`cnpj` estão
cifrados com Fernet e índice cego HMAC (`client.py:79-84`, migration
`112_client_pii_drop_plaintext.py`). **Efeito.** Vazamento do banco expõe CPF
de partes adversas e testemunhas; após "esquecimento" (LGPD art. 18, VI)
sobra PII vinculada ao caso. **Correção.** Aplicar `pii_crypto` (enc + hash)
a `case_partes.cpf_cnpj` com migration expand + backfill + contract em passos
separados (padrão da 112); incluir `case_partes` e `cid` no fluxo de
anonimização; decidir por dado de saúde (LGPD art. 11) se ele precisa
existir nessa tabela.

### P2

| ID | Onde | Achado | Correção mínima |
|---|---|---|---|
| DB-04 | `document.py:34`, `deadline.py:68`, `case_parte.py:17`, `case.py:227` | 72 colunas `status/tipo/origem` em `String` livre; `CheckConstraint` só em `preliminar.py`/`saneamento.py`. Valor fora do vocabulário entra em silêncio. | `CHECK ... NOT VALID` + `VALIDATE CONSTRAINT` em migration separada para as colunas usadas em filtro. |
| DB-05 | `atendimento.py`, `case_parte.py`, `notification.py` (sem `deleted_at`) | 54 models com soft-delete, 77 sem. Caso soft-deletado mantém atendimentos/partes "vivos" em listagens. | Definir política por tabela; adicionar `deleted_at` onde a listagem filtra por caso vivo. |
| DB-06 | `app/routers/cases.py:841→849`, `:886→893` | Movimento é commitado, depois o audit log, depois segundo commit. Falha entre os dois deixa movimento sem trilha. (Confirmado.) | Um único `commit()` após o audit, como `fees.py:447-477`. |
| DB-07 | `app/routers/export.py:83,101,203` (só `/clientes.csv:69` audita); `data_room.py` (sem `criar_audit_log`); `dossie_estrategico.py:66,169` | Exportação de casos e honorários, mutações de data room e dossiê sem registro em `audit_logs`. 71 de 162 routers chamam `criar_audit_log`. (Confirmado em `export.py`.) | `criar_audit_log` nos três endpoints de export e nos mutadores de data room/dossiê. |

### P3

| ID | Onde | Achado | Correção mínima |
|---|---|---|---|
| DB-01 | `backend/alembic/MIGRATION_RESERVATIONS.md:52` | 157 marcada "Em PR (#1536)", mas `c94d520` (#1536) já está em `origin/main` (confirmado com `merge-base`). | Marcar como mesclada. |
| DB-02 | 66 colunas FK sem índice (recontagem própria por tabela+coluna, migrations e raw SQL incluídos; a varredura original citou `atendimentos.client_id`, que **tem** índice `ix_atendimentos_client` na migration 016 — achado corrigido e rebaixado) | A maioria são colunas de autoria (`created_by`, `aprovado_por`). Em caminho de negócio: `judicial_filings.process_id`, `evidence_links.prova_id/tese_id`, `thesis_candidates.issue_id/tese_banco_id`, `legal_chat_messages.user_id`, `diario_oficial_alertas.keyword_id`, `case_checklists.template_id`, `case_checklist_items.template_item_id`, `solicitacao_documento_itens.prova_id`, `document_hash_rescan_batches.caso_id/cliente_id`. | Migration expand-only com `create_index` só nessas; ignorar colunas de autoria. |
| DB-08 | `scripts/check_migration_compatibility.py` (allowlist) | FK/CHECK/índice comum aprovados como expand-only; validação varre a tabela sob lock. `155_indices_listagem_espinha.py:75-82` documenta. | Exigir `NOT VALID` para FK/CHECK ou `human_review` acima de limiar de linhas. |
| DB-09 | `alembic/versions/145_drop_orphan_db_only_columns.py:60-90` | Guarda com `assert` no import; `python -O` a desliga. Já aplicada — não editar. | Registrar padrão a não repetir. |
| DB-10 | `011_correcoes_auditoria.py:27-44` | `DELETE FROM clients` histórico sem guarda; `ALTER TYPE` fora de `autocommit_block`. Já aplicada. | Referência negativa; nada a editar. |
| DB-11 | `044_recover_head.py:17-22` | `upgrade`/`downgrade` vazios (040-044 perdidas); banco do zero depende de `053_reconcile_schema`. Mitigado por `test_schema_dr_parity.py`. | Documentar no ledger. |
| DB-12 | `009_rag_trgm_index.py:21` (único GIN trgm); `clients.py:420-421`, `cases.py:142-144` | ILIKE em `nome`, `titulo`, `numero_processo` sem índice trgm. | GIN `gin_trgm_ops` quando o volume justificar. |
| DB-13 | `backend/entrypoint.sh:48`; `seeds/seed_all.py:157-200` | Todo boot roda admin + document_types + seis seeds de skills + base jurídica + reembed guardado. Com schema atrasado, o seed pode derrubar o container. | Gate `RUN_SEEDS` ou seeds só no deploy. |
| DB-14 | `services/scheduler.py:479,485` | Só expurgo de telemetria e rascunhos; nenhum job de retenção de `clients/cases` para a política em `docs/DPT360_POLITICA_RETENCAO_LGPD.md`. | Job com monitoramento de resultado. |

### O que está correto na camada de dados

Head único `157_ajuizamento_judicial` (`tests/test_alembic_single_head.py`,
`test_migration_reservations_head.py:27-37`); PII de cliente cifrada + HMAC
(`client.py:79-84`, `112_*`); `audit_logs` WORM por triggers
(`131_audit_logs_worm.py:108-131`); pgvector coerente em 1024 dimensões com
HNSW cosine e rollback (`096_rag_embedding_1024.py:42-67`); índices parciais
de listagem em `cases`, `clients`, `documents`, `deadlines`, `fees`; zero
`DateTime` sem timezone; guarda anti-drop no autogenerate
(`alembic/env.py:112` + `tests/test_schema_sync.py:100-124`, 32 tabelas
raw-SQL na allowlist); seeds sem senha hardcoded e recusando produção
(`seed_all.py:14-19`, `seed_demo.py:17-24`); portal amarrado a
`cu.client_id` (`portal.py:32-45`); 93 arquivos `*_dblevel` sob
`RUN_DB_TESTS`.

---

## 3. Camada backend (aplicação)

### BE-01 — P1 — 2FA desligado por padrão, sem que nenhum arquivo de provisionamento saiba

`backend/app/core/two_factor_policy.py:26`:
`os.getenv("TWO_FACTOR_AUTH_ENABLED", "false")`; `:44` zera
`REQUIRE_2FA_ROLES` no import. A variável não aparece em `.env.example`
(0 ocorrências) nem em `docker-compose.yml` (0). `config.py:62` declara
`REQUIRE_2FA_ROLES = "superadmin,admin,socio,advogado,advogado_auxiliar"`,
que assim nunca vale. A docstring chama a flag de "temporária", sem prazo.
**Efeito.** Toda a superfície de 2FA (TOTP, `test_2fa_enforcement_hard.py`)
está inerte em produção a menos que alguém tenha colocado a variável à mão
no `.env` da VPS — não verificável daqui. Admin e sócio entram só com
senha. **Correção.** Documentar a flag em `.env.example`; em
`APP_ENV=production` exigir valor explícito (falhar no boot ou `ERROR` no
log) e registrar prazo de reativação; conferir na VPS
`docker exec ejc_backend sh -c 'echo $TWO_FACTOR_AUTH_ENABLED'`.

### P2

| ID | Onde | Achado | Correção mínima |
|---|---|---|---|
| BE-02 | `services/security_service.py:33-36`; `core/rate_limit.py:34` | Anti-brute-force e `@limiter.limit` em memória, por processo, zerados a cada restart. **Dívida aceita** (`docker-compose.yml:87-90`, `entrypoint.sh:52-58`). | `Limiter(storage_uri=REDIS_URL)` e contador de falhas no Redis quando `RATE_LIMIT_REDIS_ENABLED`. |
| BE-03 | `routers/auth.py:185,200-201` | `chave_em = f"em:{email}"` bloqueada em toda falha: terceiro tranca qualquer conta por 15 min com 5 senhas erradas, sem autenticar. (Confirmado.) | Bloqueio por e-mail com backoff progressivo ou par ip+e-mail; manter bloqueio por IP. |
| BE-04 | `services/scheduler.py:1396-1548` (42 `add_job`); único `asyncio.timeout` em `:1574` | Só `_reaplicar_overlay_cofre` tem timeout; 12 jobs batem heartbeat (`heartbeat_service.py:13-24`), 30 não têm sinal de resultado. Viola a regra "monitorar resultado, não execução". | Wrapper `_job_monitorado(nome, coro, timeout)` reaproveitando `_passo_de_boot`; heartbeat padrão. |

### P3

| ID | Onde | Achado | Correção mínima |
|---|---|---|---|
| BE-05 | `core/request_context.py:36-49` | Último salto de `X-Forwarded-For` é confiado sem checar o peer. Só explorável por quem alcança o uvicorn sem passar pelo Nginx (rede docker, processo local) — o risco residual está documentado em `entrypoint.sh:66-82`. Rebaixado de P2 para P3 por isso. | Honrar XFF só se `scope["client"][0]` estiver numa allowlist de proxies. |
| BE-06 | `core/auth_middleware.py:152`; `core/security.py:197` | `jwt.decode` sem `options={"require": ["exp","iat","sub"]}`. Só relevante com `SECRET_KEY` vazada. | Adicionar `require`. |
| BE-07 | `core/auth_middleware.py:167,232` | Isolamento do portal decidido pelo `role` do token (2 h de defasagem após rebaixamento). `require_roles` usa DB. | Revalidar no DB quando `role == cliente_externo`, ou aceitar e documentar. |
| BE-08 | `services/security_service.py:189`; `services/scheduler.py:1900` | E-mail em claro em `logger.info/warning`. | `user.id` ou `sanitize_log_value`. |
| BE-09 | `routers/documents.py:373-374`; `core/upload_guard.py:31` | `await file.read()` antes de comparar com `MAX_UPLOAD_MB`. Mitigado pelo `client_max_body_size` do Nginx. | Checar `Content-Length` e ler em chunks com teto. |
| BE-10 | `main.py:666-676` | Em produção sem `SENTRY_DSN`, 500 fica sem stack. **Dívida aceita** (comentário `:672-675`). | Exigir `SENTRY_DSN` em produção no validador. |
| BE-11 | `core/database.py:33`; `config.py:28` | `echo=settings.DEBUG` sem validação em produção: `DEBUG=true` despeja SQL com binds (PII) no log. (Confirmado.) | Recusar `DEBUG=True` em `_validar_seguranca_producao`. |
| BE-12 | `routers/cases.py:384,831-832,942,1014` | Mutações usam `_filtro_visibilidade` em vez de `verificar_acesso_caso` (`ownership.py:37`); semântica igual hoje, regra duplicada. | Reusar o gate canônico. |
| BE-13 | `requirements.txt` | `boto3`, `botocore`, `pdf2image`, `reportlab`, `validators`: zero importações em `app/`, `scripts/`, `alembic/` (confirmado); comentário do `fpdf2` diz "sem consumidores" mas `raio_x_export_service.py` importa. Versões antigas a verificar (sem afirmar CVE): `bcrypt 4.0.1`, `httpx 0.27.0`, `asyncpg 0.29.0`, `sqlalchemy 2.0.30`, `alembic 1.13.1`, `PyMuPDF 1.24.5`, `sentry-sdk 2.13.0`, `redis 5.0.7`, `pgvector 0.5.0`. | Remover os cinco; corrigir comentário; `pip-audit` em venv limpo (o Trivy do CI cobre parte). |
| BE-14 | `config.py:189,211,245` | `ANTHROPIC_ENABLED`, `AI_WEB_SEARCH_ENABLED`, `AI_EXTERNAL_PROVIDERS_ALLOWED` default `True`, contra a regra "integração externa: flag default OFF". Mitigado por `AI_REQUIRE_SANITIZATION_FOR_EXTERNAL` e `AI_REQUIRE_HITL`. | Decidir e documentar a exceção na governança. |

### O que está correto no backend

Ordem de middlewares e normalização de path antes do gate
(`main.py:385-406`, `auth_middleware.py:42-58`, testado); rotas públicas
todas justificadas e protegidas por outro mecanismo (`rag_public.py:57`
com `X-API-Key` + `compare_digest`; `evolution_webhook.py:22-34`
fail-closed; `data_room.py:64,641-651` por token SHA-256 com expiração;
docs/openapi desligados em produção `main.py:375-377`); boot resiliente
com `_passo_de_boot` + timeout e readiness 503 (`main.py:213-266,
624-663`); refresh com rotação, detecção de reuso e revogação em cascata
(`auth.py:355-442`), cookie `httpOnly/secure/samesite=lax`; bcrypt rounds
12; `require_roles_exact` fecha o vazamento hierárquico do `financeiro`
(`security.py:47-71`); ownership em documentos, prazos, portal, data rooms,
usuários; config de produção falha cedo (`config.py:1303-1420`); login e
upload em transação única com compensação (`auth.py:310-327`,
`documents.py:469-477`); MIME por magic bytes e nome `uuid4`; testes para
middleware, RBAC, IDOR, rate limit, reuso de refresh, brute force, 2FA,
upload guard e XFF. Sem evidência de commit em loop, listagem sem
paginação ou log de body/headers/token.

---

## 4. Camada de IA jurídica e LGPD

### IA-02 — P1 — Aprovação HITL de peça sem exigir papel de advogado

`backend/app/routers/legal_docs.py:774-779` — `PATCH /{doc_id}/aprovar`
depende só de `get_current_user` (confirmado); a única dependência do router
é `_enforce_client_legal_doc_scope`. `cliente_externo` é barrado pelo
middleware (`auth_middleware.py:213-224`), mas qualquer papel interno
(estagiário, financeiro, secretaria) marca `human_reviewed` e leva a peça a
`aprovada` — estado que libera o protocolo em
`ajuizamento/orquestrador.py:257`. Segundo ponto que grava `aprovada`:
`legal_docs.py:978-988`. **Efeito.** Ato privativo de advogado (Lei
8.906/1994, art. 1º, I) "revisado" por quem não é advogado; o HITL deixa de
ser garantia jurídica e vira só um clique. **Correção.** `require_roles`
com papéis que têm OAB nos dois pontos; gravar `aprovado_por` com número de
OAB; teste de matriz de papéis para `aprovar`.

### IA-04 — P1 — Isolamento do RAG entre clientes por lista fechada de categorias

`backend/app/services/ai_service.py:69-73` (confirmado):
`_RESTRICTED_CATS` = `peca_interna`, `peca_escritorio`,
`precedente_interno`, `comunicacao_processual`; o filtro é
`kd.categoria <> ALL(:restr_cats) OR kd.client_id = :scope_cli`. Documento
de cliente ingerido em **qualquer outra categoria** (a ingestão manual em
`routers/rag.py` aceita categoria livre) fica recuperável em consultas de
outros clientes. **Efeito.** Quebra de sigilo profissional (EOAB art. 7º,
II; LGPD art. 46) via contexto de IA, sem log que denuncie. **Correção.**
Filtro adicional independente de categoria:
`AND (kd.client_id IS NULL OR kd.client_id = :scope_cli)`; teste
`test_rag_isolation_dblevel.py` ampliado com documento de cliente em
categoria fora da lista.

### P2

| ID | Onde | Achado | Correção mínima |
|---|---|---|---|
| IA-01 | `config.py:138,1216-1256,1504-1506` (`@lru_cache get_settings`); `provider_registry.py:18-27` | Kill-switch (`AI_ENABLED`) cobre gateway, worker e scheduler — AUD27-P0-1 está fechado (confirmado). Mas só por env com settings cacheadas: desligar num incidente exige editar `.env` e reiniciar API **e** worker; sem endpoint nem trilha de quem acionou. | Flag runtime (Redis/tabela) lida em `_requisitos()`, endpoint `superadmin/socio` com AILog; env como piso. |
| IA-03 | `config.py:292` `CITACOES_POLITICA="bloquear"` (default correto), aceita `desligado`; `:299` `CITACOES_MODO_ESTRITO=False`; `citation_gate.py:219-225` | Gate pode ser desligado por configuração em produção; sem modo estrito, citação bem-formada ausente da base fica só "identificada" e chega ao revisor sem bloqueio. | Recusar `desligado` em `APP_ENV=production` (padrão do validador `:1431-1440`); exibir "ausente da base — conferir" na tela de aprovação. |
| IA-05 | `config.py:913` (`AI_BUDGET_ALERTA_BRL` só alerta), `:411` (custo por execução); `routers/ai_skills.py` com 0 `rate_limit`/`limiter` (confirmado; `ai.py` tem 19) | Sem teto diário por usuário; skills sem rate limit: token vazado ou uso legítimo intenso esgota orçamento externo ou monopoliza o Ollama. | `rate_limit` nos POSTs de skills; contador diário de `custo_estimado` por `user_id` no gateway. |
| IA-06 | `docs/ai/EJC_AI_SECURITY_LGPD_POLICY.md:27`; `ai_guard.py:18-35`; `grep -ri "encarregado\|DPO" docs/` vazio (confirmado) | Política diz que a sanitização aborta com 422 — o código não aborta desde 2026-07-06. Sem base legal por tarefa (LGPD art. 7º/11), sem tratamento de transferência internacional (art. 33: Anthropic/Groq são externos), sem encarregado (art. 41), sem registro de consentimento/termo no portal. | Atualizar a política; nomear encarregado; registrar aceite de termos no portal. |

### P3

| ID | Onde | Achado | Correção mínima |
|---|---|---|---|
| IA-07 | `ai_gateway.py:973-990,1063-1071` | Modo `MASCARAMENTO` chama `sanitizar_pii` sem `nomes_proteger` nem NER. Só alcançável por override `AI_SANITIZATION_MODE_MAP`. | Passar `entidades` + `detectar_nomes`, ou remover o modo. |
| IA-08 | `services/observability/langfuse_client.py:10-12` | Comentário diz que `sanitizar_pii` é passthrough; `sanitizer.py:147-190` aplica os padrões. | Corrigir comentário. |
| IA-09 | `services/scheduler.py:1217` `getattr(settings, "RETENCAO_IA_ANOS", 2)`; chave ausente em `Settings` (confirmado) | `.env` é ignorado; retenção fixa em 2 anos sem decisão registrada. | Declarar o campo; documentar o prazo (LGPD art. 6º, III). |
| IA-10 | `config.py:211` | `AI_WEB_SEARCH_ENABLED=True`: fatos do caso (pseudonimizados) saem a um terceiro adicional. | Default OFF ou desligar em `sigilo_reforcado`. |

### O que está correto na camada de IA

Gateway único (nenhum import de `app.services.providers` fora de
`ai_gateway.py`; dispatch fail-closed `:1103-1108`); barreira PII em fonte
única `_chamar_com_barreira` (`:386-428`) reutilizada por chat, tarefa e
agente, com reidratação local e mapa nunca persistido; pseudonimizador cobre
CPF, CNPJ, CNJ, RG, e-mail, telefone, CEP, cartão, PIX, OAB, endereço, data
de nascimento e nomes por NER (`services/ai/pseudonymizer.py:31-49,
116-141`); piso `LOCAL_COMPLETO` não rebaixável para crimes sexuais,
menores e `sigilo_reforcado` (`sanitization_policy.py:291-405`); timeouts
por provedor e deadline da cadeia; AILog pseudonimizado
(`models/ai_log.py:52,279`); Langfuse só metadados por padrão; RAG com
escopo no `WHERE`, `rag_status='aprovado'` obrigatório, ingestão nasce
`pendente`; anti-injeção por delimitador aleatório
(`services/ai/delimitador.py`); guardrails determinísticos pós-resposta;
`BASE_PROMPT` cobre não inventar fonte, sigilo EOAB art. 7º e rascunho
HITL (`system_prompts/base.py:16-48`); protocolo exige aprovação humana e
assinatura (`orquestrador.py:257,318`); direito de eliminação em
`POST /clients/{id}/esquecimento` (`clients.py:1153-1170`).

---

## 5. Camada frontend

### P2

| ID | Onde | Achado | Correção mínima |
|---|---|---|---|
| FE-01 | `src/components/AnaliseExtratos.tsx:115-118` (`window.open("")` + `document.write(data.html)`); `backend/app/services/bank_report.py:141,156` interpolam `dados.get('cidade')` sem `html.escape` | Janela `about:blank` herda a origem da SPA: script no HTML lê `localStorage` (token). Hoje o frontend manda só `{tipo}`, então é self-XSS; vira XSS real se algum chamador passar `dados` de terceiros. (Confirmado nos dois lados.) | Escapar `cidade` no backend; renderizar via `Blob` + `URL.createObjectURL` ou `<iframe sandbox>`. |
| FE-02 | `src/lib/api.ts:14,47,425`; `src/components/ErrorBoundary.tsx:46` | Access token em `localStorage` (`ejc_access`). Decisão documentada em `api.ts:1-4`, mitigada por CSP `script-src 'self'`; ainda assim qualquer XSS vira sequestro de sessão pelo tempo de vida do access. | Access só em memória, reidratado por `/api/auth/refresh` no bootstrap; `ErrorBoundary` usa `getAccessToken()`. |
| FE-03 | `src/lib/api.ts:10` (sem `timeout`); interceptor `:56-125` trata só 401/403; 0 ocorrências de `429` | Requisição a backend travado fica pendente indefinidamente; rate limit chega como erro genérico. (Confirmado.) | `timeout` padrão de 30 s com override para upload/IA; ramo 429 com toast e `Retry-After`. |

### P3

| ID | Onde | Achado | Correção mínima |
|---|---|---|---|
| FE-04 | `src/config/moduleRegistry.tsx:260-271` (`crm`, `sensitive: true`, sem `roles`), idem `assinaturas`, `workflow`, `checklists`, `datajud`, `diario-oficial`, `produtividade`, `casos`, `documentos` | Backend é a autoridade (403 vira toast), mas a página monta, dispara chamadas e o menu não esconde por papel. | Declarar `roles` espelhando o router, como `clientes` já faz. |
| FE-05 | `src/App.tsx:186-193` | `/ia-governanca/provedores` fora do registry; exceção documentada e coberta por `routeIntegrity.test.ts:102`. | Entrada `hidden` no registry. |
| FE-06 | `src/components/RouteGuards.tsx:58-60` | `RoleOnly` redireciona à home em silêncio. | `toast.info` antes do redirect. |
| FE-07 | `src/stores/caseContext.ts:26` (`ejc_caso_ativo` em `sessionStorage`); `api.ts:422-435` e `auth.ts:146-155` não o removem (confirmado) | Próximo login na mesma aba reidrata o caso do usuário anterior (id, título, número do processo, nome do cliente). | `sessionStorage.removeItem("ejc_caso_ativo")` nos dois logouts. |
| FE-08 | `src/stores/auth.ts:41-48` | `ejc_user` completo em `localStorage` (`email`, `phone`, `oab_number`, `djen_oab_*`). Removido no logout. | `partialize` para `id`, `full_name`, `role`, `permissions`, `avatar_url`. |
| FE-09 | `frontend/package.json:10` | `lint = tsc --noEmit`; ESLint só em `scripts/ci-local.sh:394` como extra; `no-explicit-any` em WARN. Regras de hooks não bloqueiam nada. | `lint = tsc && eslint` após zerar erros. |
| FE-10 | `vite.config.ts:10`; `public/sw.js:13-24` | Sem `manualChunks`; SW cacheia todo GET same-origin fora de `/api/` sem cap nem expiração, nome `ejc-v3` fixo (o Dockerfile o troca no build). Network-first limita a obsolescência. | `manualChunks` para `react`/`react-router`/`lucide-react`; SW restrito a `/assets/`, `/`, ícones, manifesto. |
| FE-11 | `src/pages/GestaoDocumental.tsx`, `LoginModern.tsx` (0 testes); `Clientes.tsx` 18 campos, 0 `aria-label` | Página central sem teste; indício de acessibilidade fraca em filtros só com `placeholder`. | Teste de renderização + estados vazio/erro; `aria-label` nos filtros. |

### O que está correto no frontend

`App.tsx:143-182` monta rotas do registry e `routeIntegrity.test.ts:92-158`
impede rota órfã, redirect morto e colisão; portal isolado por `Protected` +
`PortalOnly`/`StaffOnly` (`RouteGuards.tsx:31-47`); refresh com promessa
única compartilhada, retry único via `_retry`, exclusão das rotas de auth e
`logout()` em falha (`api.ts:30-122`), mesma semântica em `stream.ts`; única
instância axios; interceptor apara `/api/v1`, `/api`, `/v1`; sem
`dangerouslySetInnerHTML`; todos os `target="_blank"` com `rel`; `wa.me` só
com dígitos + `encodeURIComponent`; SW não cacheia `/api/`, registro
externalizado para a CSP; zero `console.log` fora de testes; `VITE_*` só
branding; 138 arquivos de teste (79 `.test.tsx`), nenhum `.skip`/`.todo`;
prefixos de API usados no frontend existem como routers no backend.

---

## 6. Camada de testes e qualidade

| ID | Sev. | Onde | Achado | Correção mínima |
|---|---|---|---|---|
| TQ-01 | P2 | `frontend/package-lock.json` **e** `frontend/pnpm-lock.yaml` coexistem (confirmado); `frontend/Dockerfile:5-7` e `.woodpecker.yml:50` usam `npm ci` | Dois lockfiles para o mesmo `package.json` divergem com o tempo; quem usa `pnpm` localmente testa árvore diferente da que vai para produção. | Remover `pnpm-lock.yaml` (ou o inverso e migrar Dockerfile/CI); adicionar ao `.gitignore` o que for descartado. |
| TQ-02 | P3 | `backend/tests`: 637 arquivos, 110 com `skipif` | Amostra indica gate `RUN_DB_TESTS` (`*_dblevel.py`), que o Woodpecker liga (`.woodpecker.yml:22`). Não é `xfail` de bug. | Nenhuma; registrar que o gate local sem Postgres pula 93 arquivos. |
| TQ-03 | P3 | `README.md` §"Gates automatizados" | Promete gold sets de IA, `pip-audit`, Prettier, ESLint, `npm audit` no CI; nenhum está em `.woodpecker.yml`. (Já em INF-16.) | Alinhar README ao Woodpecker ou acrescentar os passos. |

Não executado neste ambiente: `ruff`, `pytest`, `alembic heads`,
`npm run lint`, `npm test`, `npm run build`, `ledger_rotas.py --verificar`
(`fastapi`/`alembic`/`pytest`/`node_modules` ausentes). Os relatórios acima
são de leitura; a execução dos portões continua sendo obrigação de cada PR
de correção.

---

## 7. Não verificado (todas as camadas)

- Se `TWO_FACTOR_AUTH_ENABLED` está definido no `.env` da VPS (BE-01).
- Qual categoria e `client_id` a ingestão manual de `routers/rag.py:129,648`
  atribui (agrava ou mitiga IA-04).
- Conteúdo de `_enforce_client_legal_doc_scope` (pode mitigar IA-02
  parcialmente) e de `services/credential_registry.py` (leitura bloqueada
  pelo hook de governança).
- Planos de execução reais e volumetria (DB-02, DB-12).
- Idempotência de `092_rag_chave_origem_vigente.py:8,25` (`CREATE UNIQUE
  INDEX` sem `IF NOT EXISTS`).
- CVEs das versões listadas em BE-13.
- Se outro chamador envia `dados` a `/bank-analysis/{id}/documento` (FE-01).
- Acessibilidade em runtime e tamanho real do bundle.
- Aderência dos prompts ao texto do Provimento OAB 205/2021 (o item 5 do
  `BASE_PROMPT` trata do tema sem nomeá-lo).

---

## 8. Ordem sugerida de execução

1. **BE-01** — conferir na VPS hoje; PR pequeno: variável documentada +
   validação em produção.
2. **IA-02** — PR pequeno: `require_roles` nos dois pontos de aprovação +
   teste de matriz.
3. **IA-04** — PR pequeno: filtro por `client_id` + teste de isolamento.
4. **DB-03** — PR de banco em três passos (expand, backfill, contract) +
   anonimização.
5. **BE-03, FE-02, FE-03, DB-06, DB-07** — PRs independentes, cada um com
   teste de regressão.
6. **IA-01, IA-03, IA-05, IA-06, TQ-01** — próximo ciclo.
7. P3 — backlog, agrupados por arquivo.

Todos os itens estão na Issue #1551 junto com os `INF-*`.
