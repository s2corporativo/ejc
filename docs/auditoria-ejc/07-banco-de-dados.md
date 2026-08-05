# 07 — Banco de dados e migrations (Fase 7)

> **Limitação declarada (no momento do diagnóstico):** não havia PostgreSQL na sessão e o
> `alembic` não estava instalado. A cadeia foi reconstruída por *parsing* de
> `revision`/`down_revision` dos 121 arquivos.
>
> **Atualização.** Ambas as limitações foram levantadas depois: `python -m alembic heads` roda, e
> a migration **127** (P1-5) foi exercitada contra um **PostgreSQL 16 real e descartável** —
> upgrade, conferência linha a linha do backfill (CPF formatado, CNPJ cru, documento-lixo e NULL),
> reexecução idempotente e downgrade. O head passou de `126_case_status_quatro_estados` para
> **`127_case_parte_pii_encriptado`**. O que segue indisponível localmente é o **pgvector**, então
> `alembic upgrade head` completo continua sendo verificado só no CI.

## 1. Cadeia Alembic — SAUDÁVEL

**Head no diagnóstico: `126_case_status_quatro_estados`.** Head atual, após o P1-5 deste PR: **`127_case_parte_pii_encriptado`** — 122 migrations. Nenhum número escrito em documento é confiável; confirme com `cd backend && python -m alembic heads`.

| Verificação | Resultado |
|---|---|
| Arquivos / revisões únicas | 121 / 121 |
| **Heads** | **1** |
| Roots | 1 — `001_inicial` |
| `down_revision` quebrado | nenhum |
| Revisões de merge | 1 — `104_merge_entrada_orquestrador` |
| Branch points | 1 — `100` → duas `101` |
| Prefixo numérico duplicado | 1 — `101` (legado, na allowlist) |
| Números ausentes | 40, 41, 42, 43, 80, 95 |
| Migrations sem `downgrade()` | nenhuma |

O branch histórico está **explicitamente na allowlist** da guarda
(`backend/tests/test_migration_numbering_guard.py:34,37`) — caso novo reprova. Nada a fazer.

> ### 🟠 1.2 — P2. Migrations 040-043 não existem no repositório
>
> `backend/alembic/versions/044_recover_head.py:17-22` é um stub `pass`/`pass` cuja docstring diz:
> *"As migrations 040-044 foram aplicadas diretamente no container e perdidas do host… Este stub
> apenas reconecta o grafo do Alembic 039 → 044"*.
>
> **Consequência:** um banco novo criado por `alembic upgrade head` **não é bit-a-bit igual ao de
> produção** — o DDL de 040-043 só existe no volume `pgdata` da VPS.
> **Mitigação real e parcial:** `053_reconcile_schema.py:107-114` recria idempotentemente as
> colunas/tabelas que faltavam (`sync_pending`, `case_type`, `kanban_column`, `kanban_columns`,
> `areas`, `agenda_eventos`), e o CI roda `alembic upgrade head` verde contra Postgres limpo.
> **[NÃO CONFIRMADO]** que a reconciliação seja completa — só um `pg_dump --schema-only`
> comparativo (produção × fresh) fecha isso.

**Higiene (P3):** números 080 e 095 são reservas queimadas, sem impacto (a cadeia liga por
`revision`, não por número). **36 arquivos têm nome ≠ ID de revisão** — as 28 migrations de 011 a
038 usam hash, e 8 modernas encurtam o nome (ex.: `109_rag_chave_origem_por_cliente.py` declara
`revision = "109_rag_scope_cliente"`). Custo de navegação, não de integridade. **Seis
`downgrade()` no-op**, todos justificados no corpo (Postgres não remove valor de enum; migration
de dados; merge; consolidação).

**`MIGRATION_RESERVATIONS.md` — coerente, com dois cabeçalhos envelhecidos (P3):** a linha 5 ainda
diz *"Head da main em 2026-07-30: `123_legal_doc_ai_log_vinculo`"*, contradizendo a própria tabela;
e a docstring de `126:38` diz `Revises: 124_…` enquanto `:44` declara
`down_revision = "125_fonte_execucoes_zeradas"`.

## 2. Models × migrations × raw SQL

**Correção de premissa do escopo:** `env.py` **não** tem lista de ~30 tabelas. A exclusão é
**derivada dinamicamente** (`backend/alembic/env.py:73-74`):

```python
if type_ == "table":
    return name in target_metadata.tables
```

Toda tabela ausente de `Base.metadata` é ignorada pelo autogenerate, sem enumerar nada. A **única
lista literal** em `env.py` é `_COLUNAS_VIVAS_FORA_DO_ORM` (`:39-52`) — **12 colunas** (o
comentário na linha 29 diz "~13"): `documents` (5), `cases` (4 de índice de risco), `teses`,
`knowledge_chunks.categoria`, `checklist_templates.tipo_demanda`.

A lista das **30 tabelas raw-SQL** mora em `backend/tests/test_schema_sync.py:100-121`
(`_SEM_MODEL_INTENCIONAL`, 32 entradas com `peca_codigo_contador` e `alembic_version`).

### Resultado do cruzamento

| Verificação | Resultado |
|---|---|
| Tabelas em model sem `create_table` | **ZERO** |
| Tabelas criadas por migration sem model, fora da allowlist | **ZERO** |
| Tabelas na allowlist não criadas por migration | **ZERO** |
| Tabelas na allowlist que na verdade têm model | **ZERO** |
| **Divergência model × migration nos models centrais** | **NENHUMA** |

Verificado coluna a coluna em `cases`, `clients`, `users`, `deadlines`, `documents`, `legal_docs`,
`fees`, `knowledge_chunks`, `processes`, `ai_logs`, `audit_logs` — incluindo colunas adicionadas
por `op.execute` com concatenação implícita. **O par model↔migration está melhor do que a
documentação sugere.**

**P3 — 2.1:** dois models vivem dentro de routers, não em `app/models/`: `dataroom_salas`
(`routers/data_room_v4.py:29`) e `teses_juridicas_v4` (`routers/teses_v4.py:27`). São legados
mantidos como origem do backfill da `114`. Como `env.py:12` importa só `app.models`, ficam fora do
`Base.metadata` — protegidos pela guarda **por acidente feliz, não por desenho**.

## 3. Integridade

**P2 — 3.1. 27 colunas de FK/lookup sem índice.** Sem `index=True` no model, sem `index=True`
inline no `create_table`, sem `CREATE INDEX` em nenhum `upgrade()`. As mais caras:

| Tabela.coluna | Por quê importa |
|---|---|
| `contratos_societarios.case_id`, `.client_id`, `.documento_id` | filtro de listagem canônico |
| `diario_oficial_keywords.case_id`, `diario_oficial_alertas.case_id`, `.keyword_id` | consulta por caso |
| `evidence_links.prova_id`, `.tese_id`, `thesis_candidates.issue_id` | junção da matriz de teses |
| `documents.versao_anterior_id`, `knowledge_docs.versao_anterior_id` | FK auto-referente |
| `clients.email`, `case_partes.email`, `wiki_paginas.slug` | lookup por chave natural |

`case_id`/`client_id` são o filtro de listagem do EJC — seq scan aqui cresce com a base inteira.

**P2 — 3.2. 11 colunas `*_id` sem FK, com relação lógica real:**
`cases.linked_judicial_case_id`, `djen_comunicacoes.prazo_deadline_id`,
`fee_payments.comprovante_doc_id`, **`legal_docs.protocolo_comprovante_doc_id`**,
`procuracoes.document_id`, `bank_abusive_charges.transaction_id`, `api_keys.client_id`,
`documents.versao_grupo_id`, `document_intake_items.duplicate_of_document_id`,
`notas_fiscais_servico.provider_id`.
**O mais sensível é o comprovante de protocolo** — é prova de tempestividade, e pode apontar para
linha que sumiu sem o banco reclamar.
*(`knowledge_docs.client_id`/`case_id` também não têm FK, mas é **decisão explícita e justificada**
em `models/rag.py:41-46` — escopos sintéticos precisam ser aceitos. Não conte como defeito.)*

**P2 — 3.3. `processes.numero_cnj` sem unicidade nem índice** (`048_processes.py:23`). O mesmo
número CNJ pode ser cadastrado em N casos, e a busca por número faz seq scan. Existe apenas
`uq_processes_principal_per_case`. É o ponto por onde duplicata de processo entra sem barreira.

**P3 — 3.4. Enums alinhados, sem divergência.** `126_case_status_quatro_estados.py` é tecnicamente
correto: desvio por `text` para evitar coexistência de dois enums, índice parcial derrubado antes
e recriado depois no vocabulário novo (`:60-71`), `downgrade()` funcional (lossy e declarado).
`CaseStatus` (`models/case.py:40-53`) bate exatamente com `_NOVOS` (`126:52`).

> **A armadilha "vocabulário de status inconsistente" do `CLAUDE.md` está RESOLVIDA.** Não há mais
> literal de status antigo em query. `backend/app/core/status_caso.py` é agora a fonte única, e o
> próprio arquivo documenta por que existe (antes havia **cinco** definições incompatíveis de
> "caso ativo", e o Dashboard contava `arquivado` como ativo). Resíduo P3: `core/domain_contracts.py`
> define um vocabulário paralelo (`CaseLifecycleStatus`) que **não é persistido** — unificação é
> decisão de produto.

**P3 — 3.5, positivo.** Os índices parciais estão bem-feitos e declarados nos dois lados:
`uq_users_email_active`, `uq_cases_numero_interno_active`, `ux_clients_cpf_hash`/`cnpj_hash` com
predicado corrigido em `079` para excluir soft-deleted.

## 4. Multi-tenant e isolamento

> ### 🟠 4.1 — P2. Não existe coluna de tenant em lugar nenhum
>
> Varredura dos 103 `__tablename__`: **zero** ocorrências de `escritorio_id`, `tenant_id` ou
> `office_id`. **O EJC é mono-tenant por construção.** Se um segundo escritório entrar, o
> isolamento nasce do zero.

O isolamento real é de dois tipos, **ambos na camada de aplicação**:

1. **Portal do cliente** — `users.client_id` (`models/user.py:47`, FK indexada). É o único vínculo
   que separa `cliente_externo`. Nenhuma constraint impede leitura de linha de outro cliente.
2. **Escopo por caso** — `cases.advogado_responsavel_id` / `advogado_auxiliar_id`
   (`models/case.py:134-136`) e `clients.responsavel_id`.

**Ambos os campos de responsável são `nullable=True`.** Não há `NOT NULL`, CHECK nem RLS: **um
caso pode existir sem dono**, e o banco não sabe a quem cada linha pertence.
**Leitura para a análise de IDOR: toda autorização é decidida em Python; o Postgres não oferece
segunda linha de defesa.**

**Cobertura de coluna de escopo:** **77 tabelas têm** (todas as de conteúdo jurídico). **26 não
têm.** As que importam para IDOR são as **filhas que só herdam escopo pelo pai** e portanto só
podem ser autorizadas via JOIN:

`data_room_arquivos`, `data_room_acesso_logs`, `bank_transactions`, `bank_abusive_charges`,
`document_intake_items`, `solicitacao_documento_itens`, `case_checklist_items`,
`contrato_historico`, `fee_payments`, `fee_cobranca_envios`, `workflow_etapas`,
**`knowledge_chunks`**.

> **Um endpoint que busque qualquer uma dessas por ID próprio sem JOIN até o caso/cliente é IDOR
> direto.** As outras 14 são globais legítimas (`feriados`, `ejc_skills`, `tabela_oab_honorarios`…).

**P2 — 4.2. `knowledge_chunks` não carrega escopo** (`models/rag.py:80-96`): só `doc_id`.
`client_id`/`case_id`/`base_rag` ficam em `knowledge_docs`. **O isolamento do RAG depende
inteiramente do JOIN estar presente em toda query de retrieval** — inclusive na vetorial, onde é
mais fácil esquecer. Hoje está (ver `06-ia-rag-grafo-juridico.md` §5); é invariante a proteger.

## 5. LGPD

### Cifrado em repouso (`services/pii_crypto.py`)

| Coluna | Mecanismo |
|---|---|
| `clients.cpf_enc` / `cnpj_enc` | Fernet |
| `clients.cpf_hash` / `cnpj_hash` | HMAC-SHA256 (índice cego, único parcial) |
| `users.totp_secret` | Fernet (migration 086) |
| `socios_sociedade.documento_enc` / `_hash` / `_mascarado` | Fernet + HMAC + máscara |
| `integration_credentials.valor_encrypted` | `vault_crypto` |
| `api_keys.chave_hash`, `password_reset_tokens.token_hash`, `data_room_links.token_hash` | hash |

O cutover foi completo: `112_client_pii_drop_plaintext.py` **dropou** `clients.cpf`/`cnpj` em
texto puro. **Não há CPF de cliente em claro no banco.**

> ### 🔴 5.1 — P1. `case_partes` é o furo de LGPD do schema
>
> `backend/app/models/case_parte.py:20` — **`cpf_cnpj = Column(String(18))` em texto puro**, ao
> lado de `nome`, `email`, `telefone`, `representante_legal`. É a **única** tabela onde CPF/CNPJ de
> pessoa natural persiste em claro depois do cutover da `112`.
>
> **Pior:** tem `client_id` FK (`:27`) — ou seja, **o próprio cliente frequentemente é uma
> `case_parte`**, e o mesmo CPF que foi cifrado em `clients` está legível ao lado. Verificado por
> mim, por leitura dos dois models.

**Em claro, além dessa:** `clients.nome`, `data_nascimento`, `email`, endereço completo;
`empresarial_cases.cnpj_empresa`; `trabalhista_cases.salario_base`; e — **alta gravidade por
conteúdo** — `cases.descricao_fatos`, `tese_principal`, `pontos_fracos`, `observacoes`: texto
livre que carrega fato sensível de cliente, sem cifra e sem classificação.

> ### 🔴 5.2 — P1. A anonimização do art. 17 está incompleta
>
> `backend/app/services/client_anonimizacao.py:81-104` sobrescreve **exclusivamente** colunas de
> `clients` e desativa o login do portal (`:107-112`). Confirmei por leitura dos imports: o módulo
> importa **apenas `Client` e `User`** (`:19,21`) — **`CaseParte` não é sequer importado**.
>
> **Não toca em:** `case_partes.nome`/`cpf_cnpj`/`email`/`telefone` (mesmo com `client_id`
> apontando para o titular); `sociedades_cliente`/`socios_sociedade`; `users.email`/`full_name`
> (só `is_active = False`); `cases.descricao_fatos` e demais campos livres;
> `audit_logs.dados_antes`/`dados_depois` (JSONB), que preservam snapshots pré-anonimização.
>
> **Depois de "anonimizar", o CPF e o nome do titular continuam recuperáveis por consulta a
> `case_partes`. Isso descaracteriza o atendimento ao direito ao esquecimento.**

**P2 — 5.3. `audit_logs` é "imutável" só por comentário.** O cabeçalho do model diz *"IMUTÁVEL —
nunca editar/deletar registros (LGPD art. 37)"* (`models/audit_log.py:2`), mas **nenhuma migration
cria trigger, RULE, REVOKE ou RLS**. Confirmei: busca por
`CREATE RULE|CREATE TRIGGER|REVOKE|ROW LEVEL SECURITY` nas 121 migrations retorna **um único
arquivo** (`123_legal_doc_ai_log_vinculo.py`), e o trigger dele é de invalidação de validação de
peça, não WORM. A reserva `127_audit_log_worm` consta como **Revogada** — o WORM foi planejado e
nunca implementado. **Qualquer papel com acesso ao banco apaga a trilha.**

**P2 — 5.4. Soft-delete cobre 38 de 103 tabelas.** Não têm `deleted_at` — e portanto somem sem
rastro: `case_partes`, `case_movimentos`, `fee_payments`, `fee_proposals`,
`document_intake_items`, `data_room_arquivos`, `data_room_acesso_logs`, `legal_chat_messages`,
`notas_fiscais_servico`, `fichas_triagem`, entre 65. Combinado com os `ondelete="CASCADE"` de
`case_partes.case_id`, `caso_areas`, `centro_custos`, `case_checklists`, `dossies_estrategicos`:
**um hard delete de caso apaga partes processuais e financeiro-satélite em cascata**, sem registro
além do `audit_log` — que, pelo 5.3, também é apagável.

## 6. Seeds e a conta de homologação

**P3 — 6.1. `seed_all.py` está correto.** Idempotente de verdade (`:71-78`, retorno antecipado);
**sem senha previsível** (`:64-68`: usa `ADMIN_PASSWORD` ou gera `secrets.token_urlsafe(16)`);
cria com `must_change_password=True` (`:87`); valida `ADMIN_EMAIL` com o mesmo `EmailStr` do login
(`:38-53`); seeds subsequentes best-effort, nunca derrubam o boot.

> ### 🔴 6.2 — P1 (operacional). A conta `homolog.qa` NÃO é criada por nada neste repositório
>
> **Isto corrige o `CLAUDE.md:265`.** Verificado por mim e, de forma independente, pela auditoria
> de segurança (`12-seguranca-lgpd.md` §8):
>
> 1. `grep -rn "homolog.qa"` em todo o código (`.py`, `.json`, `.ts`) → **zero ocorrências**.
>    A string só aparece em `docs/auditoria/*` e no próprio `CLAUDE.md`.
> 2. O runner apontado pelo `CLAUDE.md` **não é o culpado**: `qa/e2e/run_fictitious_smoke.py` usa
>    o marcador `E2E-FICTICIO` (`:50`), não `HOMOLOG-FICTICIO`.
> 3. Quem gera `HOMOLOG-FICTICIO` é **outro** arquivo: `qa/homologacao/run_homologacao.py:177`.
> 4. **Nenhum dos dois cria usuário.** O único e-mail `homolog.*` gerado é
>    `homolog.{suffix}@example.test` (`run_homologacao.py:184`) e é campo de **`cliente_pf`**, não
>    de `users`. Não há `POST /api/users` em nenhuma matriz.
> 5. Ambos exigem `EJC_BASE_URL` por env e **abortam contra produção** salvo opt-in explícito.
>
> **Conclusão:** se a conta superadmin `homolog.qa` existir em produção, ela é **dado legado**,
> criada por versão anterior ou à mão. **O risco é real e permanece** (superadmin fictício com
> sigilo profissional atrás), mas **a correção é operacional — desativar/rebaixar no banco — e não
> mudança de código.** A guarda de ambiente já está implementada nos dois runners.
> **[NÃO CONFIRMADO]** se a conta ainda existe — exige consulta ao banco de produção, vedada pela
> regra 9.

## 7. Prioridades

| # | Achado | P |
|---|---|---|
| 5.2 | Anonimização não cobre `case_partes`, `users`, `sociedades_cliente`, campos livres | **P1** |
| 5.1 | `case_partes.cpf_cnpj` em texto puro | **P1** |
| 6.2 | Superadmin `homolog.qa` legado em produção (operacional) + `CLAUDE.md:265` incorreto | **P1** |
| 1.2 | Migrations 040-043 inexistentes; paridade prod × fresh não verificável | P2 |
| 3.1 | 27 FKs/lookups sem índice | P2 |
| 3.2 | 11 colunas `*_id` sem FK (destaque: comprovante de protocolo) | P2 |
| 3.3 | `processes.numero_cnj` sem UNIQUE nem índice | P2 |
| 4.1 | Zero tenant; responsáveis nullable; sem RLS | P2 |
| 4.2 | `knowledge_chunks` sem escopo próprio | P2 |
| 5.3 | `audit_logs` sem WORM real | P2 |
| 5.4 | Soft-delete em 38/103; CASCADE apaga partes sem rastro | P2 |
| 1.1, 1.3-1.5, 2.1, 3.4, 3.5, 6.1 | Higiene, allowlists, nomenclatura — conhecidos ou justificados | P3 |

## 8. Como validar quando houver Postgres

```bash
cd backend && python -m alembic upgrade head        # deve chegar a 126_case_status_quatro_estados
python -m alembic downgrade 125_fonte_execucoes_zeradas && python -m alembic upgrade head
pytest tests/test_migration_numbering_guard.py tests/test_alembic_single_head.py tests/test_schema_sync.py
```

O `downgrade`/`upgrade` da 126 exercita o único caminho realmente arriscado (troca do tipo
`casestatus`). A camada 2 de `test_schema_sync.py` exige `pgvector/pgvector:pg16` com `pg_trgm`.
