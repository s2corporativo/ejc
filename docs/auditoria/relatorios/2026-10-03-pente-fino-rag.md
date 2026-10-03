# Pente fino do RAG / base de conhecimento — 03/10/2026

**Base:** `main` @ `deeff79`. **Referência:** auditoria profunda de 04/09
(`2026-09-04-auditoria-profunda-rag.md`, achados C/A/M). **Método:** cada achado
foi reconferido contra o código atual; os itens corrigidos neste PR têm teste de
regressão que **falha no código antigo** (14 de 15 unitários e os 2 db-level
falham sem a correção; o 15º é controle). Ambiente: Linux, Python 3.11 em venv,
PostgreSQL 16 + pgvector 0.6.0 local, `alembic upgrade head` do zero
(`170_djen_remove_unicidade_global`). **Sem acesso a produção** (regra 9): nada
foi medido na VPS.

## 1. Corrigido neste PR

| Achado | Defeito confirmado no HEAD | Correção |
|---|---|---|
| **A-6** | `::boolean` em `ficticio`/`conferido`. **Reproduzido no Postgres:** um único doc com `ficticio: "sim"` faz a busca devolver **zero** fontes (22P02 aborta a transação; as pernas caem em `except` e retornam `[]`). | Comparação textual fail-closed: fictício só é "não fictício" com marcador ausente/falso inequívoco; súmula só sai da quarentena com verdadeiro inequívoco. |
| **A-3** | Piso `LOCAL_COMPLETO` não propagado em 5 serviços que juntam fatos do caso + RAG: `peca_service` (7 chamadas + autocrítica), `anexos_service` (2), `checklist_ia`, `dossie_service`, `matriz_teses_service`. Caso `sigilo_reforcado` saía pseudonimizado ao externo. | `modo_sanitizacao=await modo_sigilo_por_case_id(db, case_id)` em todas as chamadas; na esteira de peças também pela área (`rotulo_de_sigilo_reforcado`). Teste AST garante que toda chamada ao gateway nesses módulos informa o modo. |
| **A-9** | Nova versão de documento não preservava `rag_status='recusado'`: diploma rejeitado pelo curador voltava ao RAG no primeiro re-feed com texto alterado. | Recusa preservada no ramo de nova versão (o atalho "inalterado" já preservava), com a mesma normalização do gate. |
| **A-13 / M-11** | Blocklist sensível a caixa/espaço; `confianca='bloqueado'` (chave legada) exibido como bloqueio mas não bloqueava. Efeito só com `RAG_EXIGIR_APROVADO=false`. | `lower(btrim(...))` e chave legada incluída. Teste db-level parametrizado com a flag ligada e desligada. |

## 1-A. Deliberadamente fora deste PR (regra 10 — PR ativo nos mesmos arquivos)

| Achado | PR ativo que já o trata | Contribuição registrada |
|---|---|---|
| **A-2** — `POST /rag/ingerir-ai-log` global, `aprovado`, sem RBAC/trilha (confirmado no HEAD) | #1981 (pendente + escopo do caso + filtro de categoria) e #1951 (restrição à equipe jurídica) — ambos em `routers/rag.py` | O estoque legado criado pela rota antiga **não é revertido** por nenhum dos dois (ver §4.2). |
| **A-1** — `andamento_processual` estático em `_RESTRICTED_CATS` | #1951 edita a mesma linha (acrescenta `conhecimento_ia`) | Incluir `andamento_processual` na mesma edição. No runtime já é fail-closed no boot. |
| **M-13** — `/rag/ingest-url` colapsa `\n\n`; `DELETE /rag/docs/{id}` sem audit log | arquivo `routers/rag.py` pertence a #1981/#1951 | Aplicar após o merge deles. |

Sobreposição declarada: `ai_service.py` também é tocado por #1954 e #1951, e
`ingestion_service.py` por #1951 — **em hunks distintos** (sem conflito
textual). A correção A-6 foi mantida por ser o defeito confirmado de maior
impacto; se o titular aplicar a regra 10 por arquivo, ela deve migrar para um
desses PRs.

## 2. Já resolvido antes deste PR (reconferido)

- **C-2** (HyDE furando sigilo): `ai_core_hardening_patch._instalar_hyde_local_fail_closed` força `LOCAL_COMPLETO` em toda expansão; sem IA local a busca usa a consulta original.
- **A-1** no runtime da API/worker: o patch DataJud passou a falhar o boot (`event_subscribers`), e o worker Celery importa `event_subscribers`. Resta só a declaração estática (§1-A).
- **M-1** (listagem de docs escopada) e **M-25** (fail-open do reranker): resolvidos conforme o próprio relatório de 04/09.
- **M-23** (grounding fail-open): tratado em `149344f` ("grounding exige revisão").

## 3. Ainda aberto — exige medição em produção ou decisão do titular

| Achado | Situação | Por que não foi corrigido aqui |
|---|---|---|
| **C-1** | Legislação continua fora da recuperação até curadoria manual diploma a diploma (`PATCH /rag/governanca/docs/{id}`); nenhum ingestor produz `legal_status='vigente'` com proveniência. | Regra jurídica exige fonte oficial e verificação positiva (regra 7); ausência de marcador de revogação **não** é prova de vigência. Requer decisão: curadoria em lote com trilha identificada. Medição: `scripts/relatorio_vigencia_legislacao.py`. |
| C-1 (agravante) | `proposicao_legislativa` (Câmara/Senado) cai no recorte `LIKE '%legisl%'`. | Excluí-la do gate a tornaria recuperável como fonte; proposição não é norma — decisão de política. |
| **A-4** | Perna lexical usa `similarity() > 0.05` (não indexável). | Troca por `%` com limiar 0,05 só compensa se o planner usar o GIN nesse limiar; exige `EXPLAIN ANALYZE` no volume real. |
| **A-5 / M-17** | `hnsw.iterative_scan` não usado; imagem `pgvector/pgvector:pg16` sem tag de versão (local: 0.6.0, sem o recurso). | Depende de fixar a versão do pgvector em produção. |
| **A-7** | Vetores de docs excluídos/versões antigas permanecem no grafo HNSW. | Compactação/`REINDEX` é operação de produção. |
| **A-10 / M-22** | Sem dedup cross-chave por `hash_conteudo`; ingestão manual duplica por título/autor. | Mudança de semântica de ingestão; o relatório de 04/09 cita CPC ×6 em produção — medir antes. |
| **A-18 / A-27** | Não há gold set humano; `--smoke` mede formato. | Insumo humano (75 casos). Sem ele, A-19/A-21/A-22 (RRF, reranker, limiar 0,55) não podem ser calibrados com segurança — por isso não foram tocados. |
| **A-25** | `"fontes"` é a última seção de `ORDEM_SECOES` — a primeira a ser cortada. | Mudança de montagem de contexto; avaliar com o gold set. |
| A-8, A-11, A-12, A-14–A-17, A-19–A-24, A-26, A-28, M-2–M-10, M-12, M-14–M-16, M-18–M-22, M-24, M-26, M-27 | **Não reverificados** nesta rodada. | Fora do recorte de risco desta passada; seguem como registrados em 04/09. |

## 4. Revisão do `security-auditor` (regra 8)

Executada sobre o diff original (que ainda incluía A-2). Sem fail-open, SQL
sem interpolação de entrada, sem regressão de LGPD/HITL. Três achados:

1. **Corrigido:** a autocrítica da esteira de peças (`adversarial.criticar_peca`)
   não recebia o piso de sigilo — só aplicava `sigilo_reforcado` do caso, não o
   piso por área. Hoje só dispara com `PECAS_AUTOCRITICA_ENABLED=true`. Coberto pelo teste AST.
2. **Aberto — estoque legado de A-2 (requer ação em produção, com backup):** os
   documentos criados pela rota antiga continuam globais e `aprovado`; a rota nova
   cria um doc restrito ao lado e não reverte o anterior. Medição:

   ```sql
   SELECT count(*) FROM knowledge_docs
   WHERE deleted_at IS NULL AND chave_origem LIKE 'ai_log\_%'
     AND client_id IS NULL AND extra->>'origem' = 'ai_log_hitl'
     AND extra->>'rag_status' = 'aprovado';
   ```

   Saneamento proposto (decisão do titular, após backup): rebaixar esses docs a
   `pendente` com `requires_human_review=true`, ou atribuir o escopo do caso do
   `ai_logs.case_id` correspondente.
3. **Corrigido:** a comparação de `recusado` na ingestão passou a usar a mesma
   normalização do gate. (A observação sobre log sem `case_id` refere-se a A-2 —
   repassada aos PRs #1981/#1951.)

## 5. Verificação

- Testes novos: `tests/test_rag_pente_fino_20261003.py` (15 unitários + 2 db-level).
- Harness ajustado (sem mudar o que testam): `test_anexos_service.py` e
  `test_matriz_teses.py` (dublê de `modo_sigilo_por_case_id`).
- Ledger de rotas: sem alteração (nenhuma rota tocada).
