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

### 1-B. Segunda rodada (reverificação dos itens pendentes)

| Achado | Defeito confirmado no HEAD | Correção |
|---|---|---|
| **A-15** | `PATCH /ia-governanca/rag-curadoria/{id}`: `rag_status` com default `aprovado`, notas opcionais, ignorava quarentena, marcava `human_reviewed` e não gravava trilha. Um PATCH só com a confiança aprovava o documento. | Status explícito e notas obrigatórias; aprovar/recusar usa o helper canônico do `/revisar` (`_registrar_decisao_revisao`, que recusa aprovar sob quarentena); devolver à fila desfaz a revisão anterior; audit log, só com o tamanho das notas (LGPD). Nenhum consumidor no frontend chama o PATCH. |
| **A-12** | `disponivel` era aceito e exibido como estado bom, mas o gate só recupera `aprovado`. `legal_docs._fonte_juris_validada` aceitava `disponivel` como citação validada. | Removido do vocabulário de entrada; o painel mostra `pendente` quando não há decisão; `legal_docs` exige `aprovado`. |
| **A-14** | Confiança `bloqueada` (grafia variante) caía para `media` e o documento nascia aprovado. | Qualquer confiança iniciada por `bloque` é tratada como `bloqueado`. |
| **A-16** | Extração de PDF cortava em 200 mil caracteres em silêncio e devolvia `paginas` = total do PDF. | Retorno passa a ter `paginas_lidas` e `truncado`, e o corte é logado (só números). Gravar a flag em `extra.ocr` depende de `routers/rag.py`, que pertence a #1981/#1951. |
| **A-17** | O runbook mandava `alembic downgrade -1` para voltar a 768d e prometia "não há reindex". Hoje isso desfaz a migration mais recente (sem relação), e descer até a 096 destrói os vetores 1024d (a 145 removeu a coluna legada). | Seção "Reverter" reescrita: proibido usar downgrade; o caminho seguro é backup + migration nova expand/contract + restauração do dump em caso de perda. |

### 1-C. Terceira rodada ("conserte os achados")

| Achado | Correção | Evidência |
|---|---|---|
| **C-1** | `scripts/curadoria_vigencia_lote.py`: aplica em lote decisões de vigência **já tomadas por curador**. Cada linha exige fonte oficial HTTPS (`fonte_oficial`), data da conferência não futura e notas. O curador precisa ter papel de governança. A trilha é a mesma do painel (`curadoria:<id>`), mais a referência do lote e `audit_logs`. Roda em simulação por padrão e só aplica com confirmação digitada. Não afirma vigência sozinho e não mexe em `rag_status`. | db-level: a lei invisível ao gate passa a ser recuperada depois do lote; curador sem papel é recusado. |
| **A-2 (legado)** | `scripts/saneamento_destilacao_ia_legado.py`: os docs `ai_log_%` globais e aprovados voltam a `pendente`, com escopo do caso de origem quando ele existe. Exige responsável com papel, confirmação e audit log; o estado anterior fica em `saneamento_a2.antes`. | db-level: o legado sai da recuperação. |
| **A-21 / M-26** | Sigmoide no logit do cross-encoder antes do bônus jurídico; confiança bloqueada excluída na hidratação. | `rerank()` ponta a ponta: o bônus volta a mover a ordem e a relevância dominante continua vencendo. |
| **A-28** | Testes de `rerank()` ponta a ponta, no regime ligado e na exclusão. | idem |
| **A-25** | `fontes` passa a vir antes de `documento_ged`/`processo`; se o corte do teto atinge fontes, elas saem de `ctx.fontes` (gate e AILog não declaram o que o modelo não viu). | teto de 700 caracteres: as fontes declaradas são as que estão no texto. |
| **A-26** | Situação jurídica (⚠ quando duvidosa) no prompt do Núcleo Único. | — |
| **A-19** | As pernas trigram e FTS usam o mesmo pool da perna densa. | LIMIT capturado = pool denso. |
| **A-20** | `score` é sempre cosseno; lexical vira `score_lexical` + `score_origem`. | também no db-level do caminho denso. |
| **A-5** | `SET LOCAL hnsw.iterative_scan = strict_order` em savepoint (ativo no pgvector ≥ 0.8; aceito e ignorado no 0.6). | db-level do caminho denso no PG16 + pgvector 0.6. |
| **A-8** | O cabeçalho do Planalto entra no orçamento do chunk; chunk pré-montado acima da janela é recortado; truncamento no encoder gera aviso. | 200 artigos curtos → nenhum chunk acima de 1200. |
| **A-23** | Citação confirmada na base, mas ausente das fontes entregues ao modelo → alerta + revisão obrigatória (não bloqueia). | `validar()` com e sem a fonte no contexto. |
| **A-11** | A cobertura conta só documento com chunk e elegível em algum escopo legítimo. | — |
| **A-27** | O teste de precisão foi fixado no caminho textual, onde o piso foi calibrado. | — |
| **M-2** | Delimitador com token aleatório no conteúdo RAG em 6 pontos (legado `ai_service`, validador, peças, anexos, checklist, intake). | conteúdo hostil fica dentro de `[RÓTULO::token]`. |
| **M-5** | Chave de API irrestrita só consulta status do acervo público. | SQL capturado. |
| **M-8** | Os 6 ingestores do RAG batem ponto por resultado e entram no painel cruzados com a fonte. | `executar_ingestao` → `ing_<slug>` ok/erro. |
| **M-9** | Câmara/Senado contam `novos` só depois do commit. | lote com commit falho não conta. |
| **M-12** | NFC + remoção de NUL e de caracteres de controle (texto já normalizado não muda o hash). A junção de hífen foi recusada porque altera o texto verbatim. | — |
| **M-14** | O lookup do upsert usa `COALESCE(client_id,'')` e `vigente = true`, a expressão do índice único; o model deixa de declarar um b-tree inexistente. | `EXPLAIN`: Index Scan no índice único (antes, bitmap em `vigente`). |
| **M-18** | O pré-voo do deploy recusa `RAG_EXIGIR_APROVADO`/`RAG_SUMULAS_QUARENTENA` desligados. | — |

Reverificados e já resolvidos: M-3 (todas as chamadas propagam `scope_case_id`), M-4 (o comentário voltou a ser verdadeiro), M-6 (gate de router `_enforce_client_legal_doc_scope`), M-20 (painel paginado), M-21 (AILog pseudonimizado no model), M-23.

**Correção de leitura:** a falha intermitente de `test_probe_semantico_exercita_publico_cliente_e_caso_rowlevel` foi atribuída antes a "linhas residuais do run interrompido". A causa real era o meu teste db-level de A-6, que não apagava os documentos que criava. O teste de reindex de órfãos dava a eles o mesmo vetor sintético e o probe encontrava dois chunks empatados. A limpeza foi corrigida; com o banco sem resíduo, o probe passa sempre.

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

## 3. Ainda aberto — com motivo

| Achado | Por que não foi corrigido |
|---|---|
| **C-1 (execução)** | O mecanismo existe (§1-C), mas a planilha precisa vir de curador humano: não há prova automática de vigência (regra 7). |
| C-1 (agravante) | `proposicao_legislativa` cai no recorte `LIKE '%legisl%'`; tirá-la do gate a tornaria recuperável como fonte. É decisão de política, e hoje a falha é fechada. |
| **A-1, A-2 (rota), M-13, M-22, A-16 (flag em `extra.ocr`)** | Arquivo `routers/rag.py` / linha de `_RESTRICTED_CATS` pertencem aos PRs ativos #1981/#1951 (regra 10). |
| **A-4** | Trocar `similarity()` pelo operador `%` só compensa se o planner usar o GIN nesse limiar baixo; exige `EXPLAIN ANALYZE` no volume de produção. |
| **A-7** | O grafo HNSW guarda versões antigas por decisão de auditabilidade (068); compactar/`REINDEX` é operação de produção. |
| **A-10** | Dedup cross-chave pode descartar a cópia oficial aprovada em favor de uma duplicata pendente; o script `deduplicar_base_conhecimento.py` já trata o estoque com critério declarado. |
| **A-18 / A-22 / M-27** | Gold set de 75 casos humanos; sem ele, o limiar 0,55 não pode ser recalibrado com segurança. |
| **A-24** | Pertinência desligada por decisão documentada do titular. |
| **M-7** | `status_indexacao` não filtra a recuperação por desenho: a perna textual atende documento sem vetor. |
| **M-10 / M-24** | Otimizações de memória/sessão sem defeito funcional; medir antes. |
| **M-15 / M-16** | Exigem migration: drop de coluna órfã (destrutivo, com backup) e `NOT NULL` em `chave_origem` (precisa medir nulos em produção). |
| **M-17** | `docker-compose.yml` pertence ao PR ativo #1952 (regra 10). |
| **M-19** | O limiar de frescor vive em `knowledge_governance.py`, que pertence ao PR ativo #1954. |

## 4. Revisão do `security-auditor` (regra 8)

**Terceira rodada:** sem achados críticos ou altos. Não encontrou SQL interpolado com algo além da constante do módulo, contorno do delimitador ou transação abortada pelo savepoint. O M-5 não quebra integrador legítimo. Achados aplicados:
- **médio:** legado sem caso de origem continuava global e aprovável. Agora entra em quarentena, e o `/revisar` recusa aprová-lo sem confirmar a origem;
- **baixo:** curador/responsável inativo ou excluído era aceito. Agora é recusado;
- **baixo:** o título da destilação ia para o log (LGPD). Agora só o id;
- **baixo:** o pré-voo de deploy era contornável com aspas, `export`, espaços ou comentário. Agora o valor é normalizado e só verdadeiro canônico passa.

Residual aceito: a conferência de "fonte que entrou no prompt" usa os 120 primeiros caracteres. Uma fonte cortada com início idêntico ao de outra que sobreviveu continuaria declarada. Isso só torna o A-23 levemente mais permissivo; o erro oposto é fail-safe.


**Segunda rodada:** sem achados críticos, altos ou médios. Sem ciclo de import e sem consumidor de `disponivel`; RBAC e rate-limit da rota intactos; o log do OCR não carrega conteúdo. As três observações baixas foram aplicadas: zerar a revisão ao devolver à fila, tirar as notas do audit log e corrigir um comentário em `juris_import/ingest.py`.

**Primeira rodada:**

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

- Testes novos:
  - `tests/test_rag_pente_fino_20261003.py` (61 unitários + 3 db-level);
  - `tests/test_scripts_curadoria_saneamento_rag.py` (14 unitários + 4 db-level).
- Todos os testes de regressão desta rodada falham no código anterior; os únicos que passam são os controles declarados.
- Harness ajustado (sem mudar o que testam): `test_anexos_service.py`, `test_matriz_teses.py` e `test_rag_avaliacao_precisao_dblevel.py` (caminho textual fixado).
- Ledger de rotas: sem alteração.
