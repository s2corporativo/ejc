# RELATÓRIO ETAPA 6 — AUDITORIA E CORREÇÃO DO BANCO DE DADOS

Data: 2026-07-02
Branch: `audit-ejc-graphify-etapa1`
Base: `RELATORIO_ETAPA_3_AUDITORIA_COMPLETA.md` (achados C3, C4, M8, M9, M10), `PLANO_ETAPA_4_CORRECAO_SEGURA_EJC.md` (Blocos 3 e 3b), grafo Graphify, e verificação direta contra o código/migrations reais.

## Resultado direto

Todas as alterações desta etapa são **declarativas/aditivas em nível de ORM** — zero DDL, zero migration nova, zero alteração de schema, zero risco a dados. Nenhum comando foi executado contra o banco de produção (que está apenas na VPS; não há Postgres/Docker local nesta máquina, ver "Limitações"). Validação feita por import, configuração de mappers e suíte de testes: **97 testes passam, 1 pula (depende de banco vivo), 1 continua bloqueado por libmagic no Windows (pré-existente, não relacionado)**.

## 1. Diagnóstico do banco (verificado, corrigindo a Etapa 3 onde necessário)

A auditoria da Etapa 3 estava majoritariamente correta, mas a verificação direta desta etapa **confirmou dois achados e refutou um**:

| Achado (Etapa 3) | Verificação nesta etapa | Veredito |
|---|---|---|
| C3 — tabela `processes` sem model ORM | Confirmado: `processes` (migrations 048/056/059) não estava em `Base.metadata` (66 tabelas vs. 67 reais) | **REAL — corrigido** |
| M9 — `clients.responsavel_id` com FK no banco mas não no model | Confirmado: migration `001_inicial.py:85` cria `responsavel_id` com `ForeignKey("users.id")`; o model dizia "sem FK constraint" (comentário factualmente errado) | **REAL — corrigido** |
| RAG (Etapa 3) — "falta índice em `knowledge_chunks.categoria`" | Refutado: `categoria` fica em `knowledge_docs` (não `knowledge_chunks`), e já tem índice desde `001_inicial.py:399` (`index=True`) | **FALSO POSITIVO — nenhuma ação** |
| C4 — drift model↔banco sem validação contínua | Confirmado e **ampliado**: além de `processes`, há **30 tabelas** criadas por migration sem model ORM (ver seção 5) | **REAL — guarda de teste criada** |

## 2. Alterações realizadas

Três mudanças, todas de baixo/zero risco:

### 2.1 Model ORM `Process` (resolve C3) — `backend/app/models/process.py` (novo)
- Model **declarativo** sobre a tabela `processes` já existente. Mapeia fielmente as 19 colunas reais (larguras conforme migrations 048/056/059 — atenção: `processes.tribunal/comarca/vara` são `varchar(160)`, mais largos que os campos homônimos legados em `cases`, que são `varchar(20/100)`).
- Relacionamentos: `case` (para `Case`, via `backref="processes"` — não precisou editar `case.py`) e auto-relacionamento `processo_principal`/`acessorios`.
- **Não gera DDL, não altera routers.** `routers/processes.py` e `services/processo_service.py` seguem em SQL cru (migração para ORM é trabalho futuro separado, como previsto no Bloco 3 do plano).
- Registrado em `backend/app/models/__init__.py` para o Alembic autogenerate e as checagens de drift enxergarem.

### 2.2 FK de `clients.responsavel_id` (resolve M9) — `backend/app/models/client.py`
- Adicionado `ForeignKey("users.id")` à coluna, alinhando o model à FK que **já existe no banco** desde a migration 001. Apenas informa o SQLAlchemy de uma constraint existente — **não gera migração nem DDL**.

### 2.3 Teste de sincronização de schema (Bloco 3b) — `backend/tests/test_schema_sync.py` (novo)
Guarda de regressão em duas camadas:
- **Camada estática (sempre roda, sem banco):** trava as regressões já corrigidas (`processes` em metadata, tabelas de negócio presentes, FK de `responsavel_id`) e faz cross-check entre tabelas criadas em migrations e models registrados. Esta camada **teria pego o drift de `processes`**.
- **Camada de banco vivo (só com `SCHEMA_CHECK_DATABASE_URL`):** compara `Base.metadata` com o schema real via inspector, nos dois sentidos. Sem banco, faz `pytest.skip` — nunca roda contra produção sem intenção explícita.

## 3. Migrations criadas

**Nenhuma.** Todas as tabelas, colunas, FKs e índices relevantes **já existem** no banco (migrations 001, 048, 055, 056, 059). As correções foram só de alinhamento model↔banco. Não sobrescrevi nem alterei nenhuma migration antiga. A cadeia Alembic permanece íntegra com head único `059_archiving_cases_processes` (validado por `test_alembic_cadeia_integra`).

## 4. Riscos eliminados

- **C3 (disaster recovery):** `processes` agora está em `Base.metadata` — visível ao Alembic autogenerate e às checagens de drift. Um erro de coluna no acesso SQL cru futuro pode ser cruzado com o model.
- **M9 (drift silencioso):** model e banco concordam sobre a FK de `responsavel_id`.
- **C4 (recorrência de drift):** o teste de schema passa a **acusar automaticamente** qualquer tabela nova de migration que não tenha model nem entrada consciente na allowlist — a governança que faltava.

## 5. Riscos remanescentes (documentados, não corrigidos nesta etapa)

- **30 tabelas sem model ORM** (inventário completo em `_SEM_MODEL_INTENCIONAL` no teste): `agenda_eventos, areas, case_ambiental, case_etiquetas, client_pending_items, document_access_log, domain_events, due_diligence_templates, etiquetas, inadimplencia_alerts, indice_risco_historico, jur_assuntos, jur_classes, jur_decisoes, jur_ingestao_logs, jur_modelos, jur_movimentos, jur_partes, jur_processos, jur_tribunais, kanban_columns, memoria_institucional, modelos_documentos, office_contracts, office_expenses, partner_withdrawals, portal_mensagens, pricing_rules, score_juridico, teses_vitoriosas`. São acessadas via SQL cru. Não são bug imediato, mas repetem o padrão de risco do C3. Modelá-las (priorizando as mais usadas) é candidato a bloco próprio — **não feito aqui para não misturar riscos**.
- **M8 — campos legados duplicados `cases` × `processes`** (`numero_processo`/`numero_cnj`, tribunal, comarca, vara, valor_causa): sincronização só por backfill único da migration 048. Resolver exige **migração de dados** com backup validado e decisão de arquitetura (remover legado vs. manter fallback) — fora do escopo aditivo desta etapa.
- **`cases.linked_judicial_case_id`**: campo órfão pós-048 (substituído por `processes`). Remoção é destrutiva — deixado para decisão futura.
- **Camada 2 do teste de schema** nunca rodou aqui (sem Postgres local). Precisa ser executada uma vez contra uma cópia de dev/CI para validação plena.

## 6. Comandos executados

```
# validação de import e mappers (venv backend com deps: .venv-codex)
.venv-codex/Scripts/python.exe -c "import app.models; configure_mappers(); ..."
  -> 67 tabelas em metadata (era 66), processes presente, mappers OK, FK OK

# suíte de testes (exclui teste bloqueado por libmagic no Windows)
.venv-codex/Scripts/python.exe -m pytest tests/ -k "not monta_com_rotas"
  -> 97 passed, 1 skipped (schema vs banco vivo), 1 deselected (libmagic)
```
Nenhum comando de banco (DDL/DML/migration/deploy) foi executado.

## 7. Testes de integridade

- `test_schema_sync.py::test_processes_tem_model_registrado` — **PASSA** (trava regressão C3).
- `test_schema_sync.py::test_tabelas_nucleo_presentes` — **PASSA**.
- `test_schema_sync.py::test_client_responsavel_id_tem_fk` — **PASSA** (trava regressão M9).
- `test_schema_sync.py::test_toda_tabela_de_migration_tem_model_ou_allowlist` — **PASSA** (guarda de drift futuro).
- `test_schema_sync.py::test_metadata_bate_com_banco_real` — **SKIP** (sem `SCHEMA_CHECK_DATABASE_URL`).
- `test_smoke.py::test_alembic_cadeia_integra` — **PASSA** (cadeia íntegra, head 059).
- Regressão global: **97 passed**, nenhuma falha nova.

## 8. Limitações desta etapa

- **Sem Postgres/Docker local:** o banco real está só na VPS. Não apliquei nada em produção e não pude rodar a Camada 2 do teste (comparação com banco vivo). As correções são todas ORM-only, seguras por construção, mas a validação contra o schema real deve ser feita quando houver um banco acessível.
- O `import app.main` completo trava localmente por `libmagic` ausente no Windows (problema pré-existente, documentado desde a auditoria do Codex) — por isso a validação usou `import app.models` + `configure_mappers()`, que exercita todos os mappers/relationships sem depender de `documents.py`.

## 9. Próximos passos

1. Rodar a Camada 2 do `test_schema_sync.py` (com `SCHEMA_CHECK_DATABASE_URL` apontando para cópia de dev do banco da VPS) para confirmar que `Base.metadata` bate com o schema real em produção.
2. Integrar `test_schema_sync.py` ao CI (`.github/workflows/ci.yml`) para tornar a checagem de drift contínua.
3. Bloco próprio (futuro): modelar as tabelas mais usadas entre as 30 sem ORM.
4. Bloco de dados (futuro, com backup): decidir e migrar os campos legados `cases`×`processes` (M8).

## Critério de aceite desta etapa

- Models e banco coerentes: **ATENDIDO** (`processes` e FK de `responsavel_id` alinhados; guarda de drift criada).
- Migrations seguras: **ATENDIDO** (nenhuma migration nova necessária; nenhuma antiga alterada).
- Sem alteração destrutiva: **ATENDIDO** (só mudanças ORM aditivas/declarativas).
- Banco preparado para módulos principais e arquivamento: **ATENDIDO** (model `Process` cobre inclusive `archived_at`/`archive_reason` da 059).
