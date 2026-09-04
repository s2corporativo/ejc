# Relatório — FASE 3B: Isolamento do RAG (EJC)

**Data:** 2026-06-29 · **Escopo:** fechar o vazamento cruzado de conhecimento entre clientes no RAG e parar a indexação de PII. Maior risco jurídico do laudo (LGPD + EOAB art. 25).
**Regra cumprida:** nada executado contra banco; nada apagado; sem novas funcionalidades. Migration aditiva + filtros + correção de PII.

---

## 1. Problema (laudo RAG-01 e RAG-02, CRÍTICOS)

- `knowledge_docs`/`knowledge_chunks` **sem `client_id`/`case_id`** → peças e precedentes internos de um cliente eram recuperáveis por qualquer usuário em consulta de **outro** cliente (vazamento cruzado).
- `case_intel.indexar_peca_rag` chamava `sanitizar_pii` **sem `nomes_proteger`** → nomes identificáveis (cliente, parte contrária) vetorizados na base **global**.

## 2. Solução aplicada

**Modelo de isolamento por categoria:**
- **Restrito** (escopo do cliente): `peca_interna`, `peca_escritorio`, `precedente_interno`.
- **Público** (global): legislação, súmulas, jurisprudência, doutrina.
- Filtro **fail-closed**: `AND (kd.categoria <> ALL(:restritas) OR kd.client_id = :escopo)`. Sem escopo de cliente, o conteúdo restrito é **excluído** — não vaza.

**Arquivos:**
| Arquivo | Mudança |
|---|---|
| `models/rag.py` | + colunas `client_id`/`case_id` (indexadas) em `KnowledgeDoc` |
| `alembic/versions/051_rag_isolation.py` | **NOVO**: ADD COLUMN idempotente + **backfill seguro** (`case_id` a partir de `extra->>'case_id'`; `client_id` via JOIN com `cases`) |
| `services/ingestion_service.py` | `upsert_documento` aceita e grava `client_id`/`case_id` |
| `services/case_intel.py` | **PII fix**: coleta nomes (cliente + parte contrária) e passa como `nomes_proteger`; popula `client_id`/`case_id` na peça indexada |
| `services/ai_service.py` | filtro fail-closed nos **3 caminhos** de busca (semântico, textual, `_fundir_lexical`); novo param `scope_client_id`; `analisar_caso` resolve e passa o escopo |
| `routers/rag.py` | filtro fail-closed na busca semântica direta do `/buscar` (endpoint geral → escopo vazio) |
| `routers/teses.py` | `motor_teses` resolve `client_id` do `case_id` e escopa os precedentes internos |

## 3. Cobertura (todos os caminhos que retornam conteúdo)

| Caminho | Status |
|---|---|
| `ai_service` semântico (pgvector) | ✅ filtrado |
| `ai_service` textual (ILIKE) | ✅ filtrado |
| `ai_service._fundir_lexical` (pg_trgm) | ✅ filtrado |
| `rag.py /buscar` semântico direto | ✅ filtrado (fail-closed) |
| `rag.py /buscar` fallback | ✅ via `buscar_contexto_rag` |
| `citation_check` | ✅ só categorias públicas (legislação/súmula) — sem risco |
| `rag.py stats_conhecimento` | apenas COUNT/agregação (não retorna conteúdo) — aceitável |

**Consumidores de precedentes internos** (`analisar_caso`, `motor_teses`): escopados pelo `client_id` do caso. Sem caso → fail-closed (não surge precedente de outro cliente).

## 4. Validação executada (sem banco)

- ✅ `py_compile` OK em todos os arquivos.
- ✅ Cadeia Alembic: `base → 048 → 049 → 050 → 051` (head).
- ✅ App completo sobe (`app.main:app`, **453 rotas**); modelo com `client_id`/`case_id`; `scope_client_id` na assinatura.
- ✅ Varredura: nenhum caminho de busca de **conteúdo** sem filtro de escopo.

## 5. Limitações / pendências honestas

- **Backfill depende do `extra->>'case_id'`:** peças indexadas que tenham esse metadado recebem `client_id`/`case_id` automaticamente. Peças antigas **sem** o metadado ficam com `client_id` NULL → **excluídas** da busca restrita (fail-closed, seguro), mas só voltam a ser recuperáveis após associação manual ou **re-indexação**.
- **PII já vetorizada:** o fix de `nomes_proteger` é **forward-only** (vale para indexações novas/atualizadas). Chunks antigos com nomes já gravados continuam no banco — agora **escopados ao dono** (sem vazamento cruzado), mas para *apagar* os nomes já vetorizados é preciso **re-indexar as peças** (endurecimento opcional).
- **Ordem de deploy:** a migration `051` deve ser aplicada **junto** com este código (as queries referenciam `kd.client_id`). Em produção, aplicar via a rota da Fase 2 (`alembic stamp` do estado atual e depois `alembic upgrade head` para rodar a 051), validando antes.
- **Categorias restritas** são uma lista explícita (`_RESTRICTED_CATS`). Se surgirem novas categorias derivadas de clientes, incluí-las nessa lista.

## 6. Estado das fases

- Fase 0 (segredos) ✅ · Fase 1 (404) ✅ · Fase 2 (banco/Alembic) ✅ · **Fase 3 (3A ownership + 3B RAG) ✅** — tudo **local**, pendente de deploy.
- Restante: **Fase 4** (consolidação de domínios duplicados — IA/honorários/dossiê) e **Fase 5** (higiene: remover `.venv-codex`/`generated`/órfãos; modelos ORM p/ tabelas SQL-cru; testes; re-indexação do RAG).
