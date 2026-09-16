# Auditoria profunda do RAG — EJC · 04/09/2026

**Escopo**: núcleo de recuperação aumentada (RAG) do EJC ponta a ponta — ingestão,
chunking, embeddings, schema/índices, gate de governança, isolamento multi‑tenant,
qualidade de recuperação e avaliação.

**Método**: leitura estática do código no HEAD `9495fce` da branch
`claude/rag-auditoria-profunda-9xl80u`. Cinco frentes paralelas + verificação
direta, pelo relator, de todo achado classificado CRÍTICO ou ALTO. Nenhum arquivo
de produção foi alterado; nenhum acesso a banco ou diretório de produção
(regra 9 do `CLAUDE.md`).

**Limite declarado**: sem banco de produção, nenhuma afirmação de VOLUME é feita.
Onde o impacto depende do estado dos dados, o relatório fornece o SQL de medição
em vez de estimar.

**Base de continuidade**: este relatório parte do
`RELATORIO_ANALISE_E2E_IA_2026-09-03.md` (§5.3, itens C1–C9) e registra
explicitamente o que já foi fechado desde então, o que permanece aberto e o que
é achado novo.

---

## 1. Veredito executivo

A engenharia do gate de recuperação é boa: `filtros_gate_rag()` é fonte única,
fail‑closed, aplicado às quatro pernas de busca; o isolamento por cliente é
fail‑closed e verificado a nível de banco; a barreira LGPD antes de provedor
externo não tem furo; não há injeção SQL; o versionamento tem unicidade
garantida por índice único parcial, com saneamento idempotente e downgrades que
não apagam linha.

O problema não está no gate. Está em **quem alimenta o gate**.

> **O gate de vigência exige quatro provas cumulativas que nenhum ingestor
> automático é capaz de produzir. Com os defaults de produção, todo o corpus de
> legislação do sistema está fora da recuperação.**

Isso reposiciona a leitura de todos os demais achados: o RAG do EJC não sofre de
excesso de conteúdo mal governado — sofre do inverso. O acervo jurídico entra,
é marcado "aprovado", aparece nos painéis como saudável, e não chega à IA.

Somam‑se a isso quatro classes de defeito:

1. **Recall e custo consumidos em silêncio** — HyDE ligado por engano (C‑2),
   perna lexical sem índice utilizável (A‑4), sub‑retorno do HNSW sob filtro
   (A‑5), fusão RRF que sobrepondera léxico (A‑19) e um limiar de similaridade
   inerte sob o modelo em uso (A‑22).
2. **Vazamento de contexto sigiloso** por um caminho não previsto (C‑2) e em
   sete serviços que não propagam o piso `LOCAL_COMPLETO` (A‑3).
3. **Números que não significam o que aparentam** — `score` heterogêneo exibido
   como percentual ao curador (A‑20), métricas de painel que contam o que a
   busca exclui (A‑11), e um gate de citações que confirma existência na base,
   não proveniência no contexto recuperado (A‑23).
4. **Ausência da régua** — o gold set exigido pelo próprio gate institucional
   nunca foi produzido (A‑18). Sem ele, nenhuma das correções acima pode ser
   medida, e nenhuma das flags ligadas "por decisão do titular" foi avaliada.

Um padrão atravessa quase todos: **o controle existe e está bem escrito; o que
falta é o mecanismo que o alimenta, ou a evidência de que ele funciona.**

---

## 2. Achados CRÍTICOS

### C‑1. Todo o corpus de legislação está invisível para a IA, por construção

**Evidência.** `_FILTRO_VIGENCIA_VERIFICADA_RAG` (`app/services/ai_service.py:183-192`)
exige, cumulativamente, para todo doc com `vigente=true` e categoria casando
`LIKE '%legisl%'`:

- `legal_status` canônico exatamente `vigente`;
- `legal_status_origem` não vazio;
- `legal_status_verificado_em` não vazio;
- `legal_status_inferido_em` **ausente**.

Ativo por default: `RAG_EXIGIR_VIGENCIA_VERIFICADA: bool = True`
(`app/core/config.py:782`).

Quem grava esses campos (grep exaustivo em `app/`, `scripts/`, `seeds/`):

| Produtor | O que grava |
|---|---|
| `ingestors/planalto.py:340-355` | `revogada` / `parcialmente_revogada` com `verificado_em`; **desfecho padrão** = `vigencia_nao_verificada` + `legal_status_inferido_em` |
| `ingestors/lexml.py:271-282` | só `revogada`, ou nada |
| `knowledge_autoapproval.py:66-67` | carimba `vigencia_nao_verificada` em **toda** categoria contendo `legisl` |
| `routers/rag_governance.py:265-268` | **único** produtor de `legal_status='vigente'` com proveniência — curadoria manual, um doc por vez |
| `scripts/ingestao_biblioteca_juridica.py:390` | via manifesto, campo opcional |

**Consequência.** CC, CPC, CLT, CDC, CF — tudo que o job semanal `ing_planalto`
(`scheduler.py:1336`) ingere — falha o gate por **dois** motivos independentes
(`legal_status ≠ 'vigente'` **e** `legal_status_inferido_em` presente). Nenhuma
consulta RAG recupera legislação até que um usuário de papel `socio`+ marque
diploma por diploma no painel.

**Agravante 1 — o recorte é mais largo do que "legislação".**
`lower(categoria) LIKE '%legisl%'` é substring. Alcança também
`referencia_legislativa` (LexML) e `proposicao_legislativa` (Câmara/Senado —
`ingestors/camara.py:61`, `senado.py:65`). Esses dois ingestores gravam
`rag_status='aprovado'` + `confianca='alta'` e **nenhum** campo de vigência; o
listener `knowledge_autoapproval.py:66-67` então lhes carimba o valor que os
bloqueia. Dois jobs diários ingerem indefinidamente material que nunca chega à
IA, e o painel de fontes reporta `sucesso / N novos`.

**Agravante 2 — a curadoria manual é impraticável.** O único caminho de correção
é `PATCH /rag/governanca/docs/{id}`, um doc por vez, e a lista do painel é fixa
em `page: 1, page_size: 100` ordenada por `created_at DESC`
(`frontend/src/components/KnowledgeGovernancePanel.tsx:256`, `routers/rag.py:400`),
sem paginação, sem busca e sem filtro por `legal_status`. Só os 100 documentos
mais recentes são alcançáveis. Não existe endpoint nem script de backfill.

**Agravante 3 — a "verificação" é autodeclaração.** `rag_governance.py:265-268`:
basta o campo `legal_status` aparecer no payload para o backend carimbar
`legal_status_origem=curadoria:<uid>`, `legal_status_verificado_em=now()` e
**apagar** `legal_status_inferido_em`. Não há exigência de link oficial, de
confronto com fonte, nem de notas. Um `<select>` converte "ninguém sabe" em
"proveniência positiva completa".

**Agravante 4 — promoção passiva de alias legado.** O painel envia
`legal_status: form.legal_status` em **toda** gravação, mesmo quando o curador
editou só a área (`KnowledgeGovernancePanel.tsx:320-336`). O formulário é
pré‑preenchido com `doc.situacao_juridica.code` (`:291`), derivado de
`inferir_situacao_juridica` (`knowledge_governance.py:215-234`), que aceita os
aliases legados `situacao_normativa` e `vigencia_status`. Resultado: um doc com
`extra.situacao_normativa='vigente'` (sem qualquer proveniência) vira
`legal_status='vigente'` com carimbo de curadoria ao primeiro "Salvar" de
qualquer campo — contradizendo frontalmente o comentário de `ai_service.py:152-153`
("aliases legados não bastam para afirmar vigência").

**Medição em produção** (não executada aqui; `scripts/relatorio_vigencia_legislacao.py`
já produz o relatório):

```sql
SELECT count(*) FILTER (WHERE lower(categoria) LIKE '%legisl%') AS legisl_total,
       count(*) FILTER (WHERE lower(categoria) LIKE '%legisl%'
              AND NOT (lower(btrim(extra->>'legal_status')) = 'vigente'
                   AND nullif(btrim(extra->>'legal_status_origem'),'') IS NOT NULL
                   AND nullif(btrim(extra->>'legal_status_verificado_em'),'') IS NOT NULL
                   AND nullif(btrim(extra->>'legal_status_inferido_em'),'') IS NULL)) AS invisivel
FROM knowledge_docs WHERE deleted_at IS NULL AND vigente = TRUE;
```

**Nota de método**: o gate está *certo*. Norma sem vigência comprovada não deve
fundamentar peça. O defeito é a ausência do produtor automático do outro lado —
o controle foi implantado sem o mecanismo que o alimenta.

---

### C‑2. HyDE ligado por padrão fura o sigilo reforçado e cobra por consulta

**Evidência.** `RAG_HYDE_ENABLED: bool = True` (`config.py:693`), enquanto
`ai_service.py:396-398` documenta "OFF por default" e lê com
`getattr(settings, "RAG_HYDE_ENABLED", False)`. A mesma divergência existe em
`RAG_FTS_ENABLED` (`config.py:703` = `True` × `ai_service.py:341` "OFF por
default").

Com embeddings ativos, **toda** chamada de `buscar_contexto_rag` executa
`_hyde_expandir` (`ai_service.py:486`), que chama o gateway
(`ai_service.py:401-410`) com `task_type="resumo"` e **sem `modo_sanitizacao`**.
O gateway então resolve por `modo_para_task("resumo")` =
`EXTERNO_PSEUDONIMIZADO` (`ai/sanitization_policy.py:135`), e
`TASK_ROUTING["resumo"]` (`ai_gateway.py:190-195`) termina em
`("anthropic", None)` — provedor externo, no desenho de produção com Ollama
desligado.

**Três consequências, em ordem de gravidade:**

1. **Vazamento de caso sigiloso (LGPD art. 11; ECA art. 143).** Em `analisar_caso`
   o `modo_sigilo` (LOCAL_COMPLETO) é calculado em `ai_service.py:743` e aplicado
   à chamada principal, mas o HyDE ocorre **dentro** de `buscar_contexto_rag` e
   não recebe esse parâmetro — a função não tem `db`, `case_id` nem
   `modo_sanitizacao` na assinatura. Fatos de um caso marcado `sigilo_reforcado`
   (crime sexual/menor) saem do VPS pseudonimizados, quando a decisão do titular
   de 18/08 exige que não saiam.
2. **Custo e latência não orçados.** Uma chamada paga por consulta RAG, em série
   antes da busca. `deep_research_service.py:172-178` faz até 6 consultas RAG
   sequenciais por pesquisa → 6 chamadas extras encadeadas, cada uma com a cadeia
   de fallback e seus timeouts.
3. **Cache de embedding de query anulado.** `_QUERY_CACHE`
   (`embedding_service.py:155-172`) chaveia pelo texto final; com HyDE o texto
   inclui uma hipótese gerada a `temperature=0.3` (`ai_service.py:409`), diferente
   a cada execução. Taxa de acerto: zero.

**Correção mínima**: alinhar os defaults ao que o código documenta (`False`) ou —
se HyDE for desejado — propagar `modo_sanitizacao` até `_hyde_expandir` e cachear
a hipótese por consulta normalizada.

---

### C‑3. ~~Encerrar caso com `alimentar_rag=True` (default) retorna 500~~ — ACHADO RETIRADO na revisão

**Evidência original (incorreta).** `routers/cases.py:1039-1053` chama
`upsert_documento` com `categoria="precedente_interno"` e **sem `client_id`**;
`ingestion_service.py:315-319` levantaria `ValueError` para categoria em
`_CATEGORIAS_RESTRITAS` sem `client_id`.

**Por que foi retirado.** No startup normal, `event_subscribers._install_ai_core_hardening()`
instala obrigatoriamente `_instalar_resolucao_escopo_rag()`, cujo wrapper reconhece
`precedente_interno` com chave `caso:<id>`, consulta o caso e injeta `client_id` e
`case_id` **antes** de chamar o `upsert_documento` original
(`backend/app/services/ai_core_hardening_patch.py:77-115`). Como `encerrar_caso` faz o
import local após esse patch, `alimentar_rag=True` não retorna 500 pelo motivo descrito —
o achado classificava como crítica uma regressão inexistente.

**Resta de valor.** Cobertura de teste: o único teste do fluxo passa
`alimentar_rag=False` (`tests/test_case_patch_arquivar_encerrar_gate_dblevel.py:345`).
Um teste de regressão com `alimentar_rag=True` (protegido pelo patch de hardening)
continua desejável como rede de proteção, mas não é correção de bug.

---

## 3. Achados ALTOS

### A‑1. `andamento_processual` só é categoria restrita por monkeypatch fail‑open

`ingestion_service._CATEGORIAS_RESTRITAS` tem **cinco** entradas, incluindo
`andamento_processual` (`ingestion_service.py:38-44`).
`ai_service._RESTRICTED_CATS` — a lista que governa a **recuperação** — tem
**quatro** (`ai_service.py:69-70`). A quinta é acrescentada só em runtime, por
`datajud_cognitive_patch._registrar_categoria_restrita` (`:148-151`), cujo
instalador é o **único** dos três que engole a exceção:

```python
# event_subscribers.py:63-70
except Exception as exc:
    logger.error("Feed cognitivo DataJud indisponível: %s", exc, exc_info=True)
```

Qualquer falha nesse patch (import, APScheduler indisponível) deixa o processo
de pé recuperando **andamentos processuais de todos os clientes como conhecimento
público** — movimentações com nomes de partes entrando no contexto de casos de
outros clientes. Sinal: um `logger.error` no boot.

**Contraste que confirma o padrão correto**: o hardening análogo
(`_install_ai_core_hardening`, `event_subscribers.py:48-61`) faz `raise` —
falha de patch impede boot inseguro. Este não.

**Correção**: declarar `"andamento_processual"` estaticamente em
`_RESTRICTED_CATS`, com teste comparando as duas listas.

### A‑2. `POST /rag/ingerir-ai-log/{log_id}` grava doc global auto‑aprovado, sem RBAC

`routers/rag.py:607-654`: só `Depends(get_current_user)` (sem `require_roles`),
`categoria` é string livre do payload (`:601-603`), grava
`extra={"rag_status": "aprovado", ...}` e **não propaga `client_id`/`case_id`** —
o documento nasce global e aprovado. Sem `criar_audit_log`, ao contrário das
rotas vizinhas `/seed` e `/ingest-fontes-oficiais` (`:519`, `:567`).

É o **único** caminho de ingestão que nasce `aprovado` por ação de usuário: PDF,
URL e API pública nascem `pendente` (`rag.py:129`, `rag_public.py:392`).

Cadeia: gerar output de IA → `PATCH /ai/logs/{id}/status` para `revisado`
(`routers/ai.py:315`, sobre log próprio) → `POST /rag/ingerir-ai-log/{id}` com
`categoria: "jurisprudencia"`. Resultado: (a) bypass da curadoria — o doc passa
`_FILTRO_GATE_RAG` e `_FILTRO_APROVADO_RAG`; (b) injeção de prompt persistente
para todos os usuários; (c) **vazamento cross‑tenant** — `AILog.resposta`
(`ai_service.py:956`) guarda a resposta já reidratada com nomes reais, e a
categoria escolhida não está em `_RESTRICTED_CATS`.

### A‑3. Piso `LOCAL_COMPLETO` não propagado em 7+ serviços que juntam caso + RAG

Grep por `modo_sanitizacao|sigilo` retorna **zero** ocorrências em
`peca_service.py:905-924`, `anexos_service.py:493-520`, `checklist_ia.py:72-90`,
`dossie_service.py:130-145`, `core/veredito_ia.py:185-200`,
`matriz_teses_service.py:252`, `deep_research_service.py:170-180`. Todos montam
fatos do caso + contexto RAG e chamam `gw_chat` sem informar o sigilo.

Também sem checagem, dentro do próprio `ai_service`: `resumir_documento`
(`:840-877`) e `extrair_prazos_ia` (`:893-944`) — os routers verificam ownership,
não sigilo.

Este é o mesmo defeito da Issue #1194, agora em sete módulos que ficaram de fora
daquela correção (que fechou `ai_service`, `ai_tools`, `orchestrator`,
`agent/loop`, `validador_juridico_service`, `ia_defensiva_service`,
`analise_estrategica`). Sugestão do relatório de 03/09 (§7 item 5) permanece
válida e agora tem a lista completa.

### A‑4. Perna lexical faz sequential scan em toda consulta RAG

`ai_service.py:316` filtra com `similarity(kc.conteudo, :q) > 0.05` — **função**,
não o operador `%`. O índice `ix_knowledge_chunks_conteudo_trgm`
(`gin_trgm_ops`, migration `011_correcoes_auditoria.py:65-68`) indexa `%`, `%>`,
`%>>` e padrões `LIKE`/`ILIKE`; **não** indexa `similarity(a,b) > constante`. O
predicado é não‑sargable: Seq Scan em `knowledge_chunks` com cálculo de trigram
linha a linha, seguido de `ORDER BY sim DESC` sem suporte de índice
(`ai_service.py:322`).

`_fundir_lexical` é chamada **incondicionalmente** sempre que a perna vetorial
devolve algo (`ai_service.py:535-540`). Toda consulta RAG paga esse scan.

**Agravante de qualidade, não só de custo.** `similarity()` normaliza pela união
de trigramas. Um chunk de ~1.800 chars contra uma consulta de 300 chars tem teto
de similaridade em torno de 0,14 — o ranking passa a premiar **chunk curto**, não
chunk relevante. O limiar `0,05` é 6× mais frouxo que o default de `pg_trgm`
(0,3), o que amplia o conjunto intermediário antes do `LIMIT`.

**Correção sem migration**: trocar por `kc.conteudo % :q` com
`SET LOCAL pg_trgm.similarity_threshold`, que passa a usar o GIN existente.

### A‑5. Sub‑retorno do HNSW sob gate estrito, com falha silenciosa

A query densa (`ai_service.py:498-514`) tem `ORDER BY kc.embedding <=> :vec
LIMIT :lim` com 9+ predicados, **todos em `kd`** — do outro lado do JOIN. O
índice HNSW cobre só `kc.embedding`. É post‑filtering clássico: o índice escolhe
os K vizinhos mais próximos do corpus **inteiro**, e os gates só depois derrubam
parte deles.

No HNSW do pgvector isso não se resolve continuando a varredura: a busca percorre
uma lista de candidatos limitada por `hnsw.ef_search`; esgotada a lista, o index
scan declara fim de resultados. `SET LOCAL hnsw.ef_search = 100`
(`ai_service.py:521`) eleva o teto de 40 para 100 — melhora real, e o comentário
diagnostica o problema corretamente —, mas **100 é um teto fixo, cego à
seletividade**. Com os gates de C‑1 ligados, a seletividade combinada pode ficar
abaixo de 1%: a expectativa é ~1 linha útil entre 100 candidatos, para um `LIMIT`
que pede 6 (ou mais, com reranker).

`hnsw.iterative_scan` (pgvector ≥ 0.8, default `off`), que faz o scan retomar
quando o filtro descarta demais, **não é definido em lugar nenhum** (grep: zero
ocorrências no repo).

**O modo de falha é o problema.** Retorno vazio cai no fallback textual
(`:542,546`) sem qualquer sinal de que o recall foi truncado pelo índice. Num
sistema jurídico, "o precedente existe mas o HNSW não o alcançou" e "não existe
precedente" produzem exatamente a mesma saída.

**Composição com A‑7**: soft‑delete e versões não‑vigentes deixam vetores no
grafo, e cada um consome uma das ~100 vagas de `ef_search`.

### A‑6. Cast `::boolean` pode zerar todas as pernas do RAG

`ai_service.py:136` e `:143` usam `COALESCE((kd.extra->>'conferido')::boolean, false)`
e `COALESCE((kd.extra->>'ficticio')::boolean, false)`. `->>` devolve sempre
`text`; booleano JSON real vira `'true'` e casta bem, mas qualquer valor não
conversível (`'sim'`, `'vigente'`, objeto) lança `ERROR 22P02` **em runtime**.

Como `filtros_gate_rag()` é interpolado nas **quatro** pernas (`:320`, `:368`,
`:511`, `:581`), o erro aborta a transação na perna vetorial; o `except` de `:543`
só loga um warning e segue para o fallback textual, que falha na transação já
abortada; o `except` de `:597` loga e retorna `[]` (`:599`). **Resultado: RAG
devolve zero fontes, com dois warnings e nenhum erro visível ao chamador.**

Hoje o risco é latente, não ativo: todos os writers localizados gravam `bool`
Python (`sumulas_ingestion.py:347`, `scripts/parse_biblia_ejc.py:130`,
`rag_governance.py:154-155,180-181`) e `IngestRequest` não expõe campo `extra`
(`routers/rag.py:80-88`). Mas nada no schema impede, e
`ingestion_service.py:343` faz `mesclado = {**anterior, **extra}` — merge cego.

**Contraste**: o resto do módulo já usa a forma defensiva —
`_SQL_SITUACAO_JURIDICA` (`:154-159`) e `_SQL_LEGAL_STATUS_CANONICO` (`:160-163`)
normalizam com `regexp_replace(lower(btrim(...)))` e comparam como texto, sem
cast. Os dois casts booleanos são a exceção destoante.

**Correção sem migration**:
`COALESCE(lower(btrim(kd.extra->>'ficticio')) IN ('true','t','1','yes'), false) = false`.

### A‑7. Soft‑delete e versões históricas deixam vetores vivos no grafo HNSW

`routers/rag.py:435` marca `deleted_at` e commita; nada toca `knowledge_chunks`.
Os chunks ficam na tabela com embeddings intactos e **presentes no grafo HNSW**.
O mesmo vale para o versionamento: `ingestion_service.py:405` marca
`vigente=False` e os chunks da versão antiga ficam indexados para sempre
(decisão deliberada, `068_rag_versionamento.py:56-59`).

**Correção preservada**: todas as pernas filtram `kd.deleted_at IS NULL` e
`kd.vigente` — não há vazamento de conteúdo excluído.
**Custo**: o grafo cresce com todo o histórico, e cada vetor inalcançável ocupa
uma vaga de `ef_search` (compõe com A‑5). Não há job de compactação/`REINDEX` no
repo.

### A‑8. Chunk pode exceder a janela do encoder, com truncamento silencioso

O único controle é por **caracteres**, não por tokens: `EMBEDDINGS_MAX_CHARS: int = 1800`
(`config.py:650`), com a premissa escrita em `config.py:645-650` ("e5‑large:
512 tokens ≈ 1.800 chars em pt‑BR"). Não existe tokenizer, `max_length` ou
contagem de tokens em nenhum ponto do repo.

Três problemas:

1. **`upsert_documento(chunks=...)` não aplica teto** (`ingestion_service.py:389-393`).
   O maior produtor por esse caminho é o Planalto, cujo `montar_chunks`
   (`ingestors/planalto.py:399-441`) limita o **corpo** a 1200 chars mas depois
   prefixa um header enumerando todos os artigos do grupo (`:421-424`). Simulação
   fiel da função com 200 artigos curtos consecutivos (padrão real de códigos):
   **1.934 chars**, acima do teto.
2. **O truncamento é invisível.** `_embed_sync` (`embedding_service.py:115-120`)
   não passa `max_length` nem checa comprimento; o fastembed trunca e retorna
   **um vetor por texto** — a guarda de contagem 1:1 (`:211-216`) não detecta
   nada. O doc vira `status_indexacao='indexado'` e o trecho perdido não aparece
   em log, métrica ou painel. *(Não reproduzido empiricamente: fastembed não
   instalado neste ambiente.)*
3. **O acervo legado nunca é re‑chunkado.** O teto anterior era 2.400 chars
   (`legal_chunker.py:24-27`). `reembedar_chunks_orfaos` só preenche
   `embedding IS NULL` sobre o `conteudo` existente (`:64-68,88-89`) — nunca
   recorta. O único rechunk existente é específico do Planalto (`planalto.py:481-500`).

### A‑9. Recusa e revisão humanas se perdem quando o conteúdo muda

Em `upsert_documento`, a preservação de `human_reviewed`, `curadoria` e
`rag_status='recusado'` existe **apenas** no atalho de conteúdo idêntico
(`ingestion_service.py:339-379`). No ramo de **nova versão** (`:405-432`),
`extra_nova_versao = dict(extra or {})` (`:417`) preserva somente
`_CAMPOS_VIGENCIA` (`:418-424`).

**Consequência**: um diploma que o curador **recusou** volta como
`rag_status='aprovado'` (vindo de `planalto.py:528`) no primeiro re‑feed em que o
texto compilado muda. E um doc aprovado tem seu **texto novo** entrando no RAG
sem que ninguém tenha visto o diff — apesar de `compare_versions`
(`knowledge_governance.py:673-748`) existir exatamente para isso.

**Assimetria incoerente**: o mesmo bloco `:418-424` transporta
`legal_status='vigente'` + `legal_status_verificado_em` para a versão nova, cujo
texto ninguém conferiu. A revisão humana se perde; a prova de vigência persiste.

### A‑10. Duplicação cross‑caminho não é prevenida

O dedup é por `(COALESCE(client_id,''), chave_origem)`, com índice único parcial
no banco (`109_rag_chave_origem_por_cliente.py:56-63`) — sólido para reingestão
da mesma chave. Mas `hash_conteudo` (SHA‑1 do conteúdo normalizado,
`ingestion_service.py:229-230`) **nunca é consultado cross‑chave**: só compara com
o próprio documento da mesma chave (`:340`).

O repo documenta o resultado medido em produção
(`scripts/deduplicar_base_conhecimento.py:10-21`): **CPC com 6 cópias, CLT com 4,
Código Civil com 4, CF com 4**, mais um "VADE MECUM 2026" repetindo tudo. A
remediação é um script manual que exige `--aplicar` no VPS; não roda no scheduler.

Fábrica de duplicatas adicional: `_chave_ingestao_manual` (`routers/rag.py:97-104`)
deriva a chave de `actor_id + categoria + tribunal + titulo + fonte`,
explicitamente "sem incluir o conteúdo". O mesmo PDF reenviado com título
diferente — ou pelo colega ao lado — vira documento novo.

**Impacto no contexto**: o mesmo artigo ocupa 6 das vagas do prompt, expulsando
jurisprudência e doutrina.

### A‑11. Métricas de saúde e cobertura contam o que a recuperação exclui

O item C3 do relatório de 03/09 foi **parcialmente** fechado:
`filtros_gate_rag()` é de fato importado, não duplicado, nas três superfícies
(`ai_service.py:321,367,510,580`; `knowledge_governance.py:33,38`;
`rag_coverage.py:62,66`). Mas o `WHERE` ao redor diverge, sempre no sentido de o
painel contar mais do que a busca devolve:

| Cláusula | Recuperação | `_ids_recuperaveis` | `rag_coverage._where` |
|---|---|---|---|
| escopo por cliente (`_FILTRO_ESCOPO_RAG`) | `ai_service.py:73,318` | **ausente** | **ausente** |
| existência de chunk | `JOIN knowledge_chunks` (`:314`) | **ausente** | `LEFT JOIN` (`:93`) |

Um `precedente_interno` aprovado entra em `retrievable_docs`
(`knowledge_governance.py:448`), em `usable_docs` (`:450`) e em
`rag_coverage.documentos` (`:80`), embora nunca seja recuperável numa consulta
global. O próprio código sabe disso — `test_document_retrieval` trata essas
categorias como caso especial (`:764-771`).

`usable_docs` corrige o caso de zero chunks (`:450`), mas `rag_coverage` não —
`GET /rag/governanca/cobertura` e `GET /rag/governanca/saude` divergem entre si
sobre o mesmo acervo.

O teste que sustenta a alegação de fonte única
(`tests/test_rag_metricas_gate_c3.py:24-36`) verifica apenas a presença literal
do fragmento; nada sobre escopo ou chunks.

### A‑12. Vocabulário `'disponivel'`: gravável, exibido como bom, excluído pelo gate

`_rag_status(extra, status_indexacao)` (`routers/ia_governanca.py:63-64`) **deriva**
`"disponivel"` para todo doc sem `rag_status` que esteja `status_indexacao='indexado'`,
e o painel o exibe assim (`:319-320,433,768`). O valor também é **aceito como
entrada** em `RagStatus` (`:36`) e `CuradoriaPatch` (`:69`).

Mas `_FILTRO_APROVADO_RAG` exige literalmente `'aprovado'` (`ai_service.py:126`),
e `'disponivel'` **não está** na blocklist de `_FILTRO_GATE_RAG` (`:122`).
Consequências: um curador que escolhe o rótulo que significa "disponível"
**retira** o documento da recuperação; o painel e a busca afirmam coisas opostas
sobre o mesmo doc; e se `RAG_EXIGIR_APROVADO` for desligado, o mesmo valor
**inverte de sentido** e passa a ser recuperável. Terceira superfície:
`routers/legal_docs.py:266` aceita `rag_status in ("aprovado","disponivel")`.

### A‑13. Blocklist do gate é sensível a caixa e espaço

`_FILTRO_GATE_RAG` (`ai_service.py:118-123`) compara
`COALESCE(kd.extra->>'rag_status','')` cru, sem `lower()` nem `btrim()` —
`'Bloqueado'`, `' recusado'`, `'Recusado'`, `'reprovada'` escapam da exclusão.
`_FILTRO_VIGENCIA_VERIFICADA_RAG` (`:160-163`) e `_FILTRO_REVOGADA_RAG` (`:167-169`)
normalizam corretamente. A assimetria é inócua com `RAG_EXIGIR_APROVADO=true`
(só `'aprovado'` exato passa); com a flag desligada, **todo bloqueio mal grafado
libera o documento**.

### A‑14. Fail‑open estreito na auto‑aprovação por erro de grafia

`knowledge_autoapproval.py:50-52` normaliza qualquer `confidence_level` fora de
`_CONFIANCAS_VALIDAS` para `"media"`; a guarda de bloqueio (`:94`) compara com
`"bloqueado"` exato. Um `'bloqueada'` ou `'Bloqueado'` em documento **sem
`rag_status` explícito** cai no `else` de `:99-101` e nasce `aprovado`.

Alcance real: só atinge docs sem status explícito (a precedência de `:93-97`
protege os demais). Mas é fail‑open no exato ponto que o módulo promete
fail‑closed — um erro de grafia num marcador **restritivo** produz o resultado
**permissivo**.

### A‑15. Porta paralela de aprovação sem notas e sem trilha

`PATCH /ia-governanca/rag-curadoria/{doc_id}` (`routers/ia_governanca.py:443-465`)
tem o mesmo piso de papel do `/revisar`, mas: `rag_status` com default
`"aprovado"` no schema (`:69`), `notas` opcional (`:70`), grava
`human_reviewed = True` (`:455`) e **não emite `criar_audit_log`**. Um `PATCH`
mandando só `{"confidence_level":"media"}` aprova o documento e o marca como
humanamente revisado.

O caminho canônico (`POST /rag/governanca/docs/{id}/revisar`) faz tudo certo:
notas obrigatórias (`rag_governance.py:92-93`), confiança na mesma transação
(`:97`), bloqueio de aprovação sob quarentena (`:171-178`), audit log (`:363-377`).

### A‑16. OCR trunca em 200 mil caracteres e reporta o total de páginas

`ocr_service.py:225-233`: ao passar de `MAX_OCR_CHARS = 200_000` (`:42`) o laço
faz `break` e o retorno traz `"texto": "\n".join(partes)[:MAX_OCR_CHARS]` com
`"paginas": total` — a contagem do PDF inteiro, não das páginas lidas. Nenhum
campo indica truncamento. `routers/rag.py:216-224` grava esses números em
`extra.ocr` como se o documento estivesse completo. Um processo de 400 páginas
entra pela metade, sem sinal.

### A‑17. Rollback documentado do embedding 1024 destrói os vetores

`RUNBOOK_MIGRACAO_EMBEDDING_1024.md:48-52` manda `alembic downgrade -1` e afirma
que "a coluna `embedding_legacy_768` é renomeada de volta para embedding; não há
reindex". Deixou de ser verdade quando `145_drop_orphan_db_only_columns.py:83,96`
dropou a coluna legacy. Hoje o downgrade até `096`: `145.downgrade()` recria
`embedding_legacy_768` **vazia** (`:101-103`), e `096.downgrade()` dropa a coluna
`embedding` populada de 1024d (`:52`) e renomeia a vazia para `embedding`
(`:53-63`). **Perda total dos embeddings, seguindo um runbook que promete o
oposto.**

### A‑18. Não há gold set — toda calibração é cega

`app/eval/run_eval.py` é um harness sólido: hit@k, precision@k, recall@k, MRR
determinísticos; gate de citações com `--full`; LLM‑as‑judge de groundedness com
`--judge`. O gate institucional exige **75 casos humanos reais**, 15 por área,
com curador identificado, fonte oficial HTTPS e conferência de vigência
(`app/eval/HUMAN_GOLD_SET_BACKLOG.md:9-19`).

O repo tem: `gold_set.example.jsonl` (3 linhas), `gold_set_pecas.example.jsonl`
(10), `gold_set_ia_candidatos.jsonl` (10, **geradas por IA** — que o próprio
documento declara não satisfazerem o gate, `:21`). **`gold_set.jsonl` não existe.**

E o workflow que rodaria o gate não existe mais: `.github/workflows/` foi
removido; o `.woodpecker.yml` roda `ruff`, `alembic upgrade head` e `pytest`, mas
nenhum eval de RAG.

`scripts/avaliar_rag_precisao.py` mede Hit@k/MRR **apenas sobre 27 súmulas**
(`:8-11`) — a única categoria imune ao gate de vigência. Ou seja: **o harness de
avaliação existente não detectaria C‑1.**

Consequência direta: `RAG_MIN_SIM=0.55`, o tamanho de chunk, a decisão de ligar
reranker, a fusão RRF — nada disso pode ser avaliado. Toda mudança de qualidade é
aposta.

### A‑19. A fusão RRF sobrepondera o léxico, por construção

`_fundir_lexical` (`ai_service.py:284-389`) usa RRF com `K=60` (`:291`). Com o
reranker desligado (default, `config.py:675`), `_n_pool = limite`
(`ai_service.py:468-469`) e as pernas entram assimétricas:

- perna densa: no máximo `limite` candidatos — 6 no default de
  `buscar_contexto_rag` (`:419`), 10 no Núcleo Único (`ai/core/context_builder.py:36,437`);
- perna trigram: `max(limite*3, 12)` (`:301`);
- perna FTS: `max(limite*3, 12)` (`:346`), **ligada por default** (`config.py:703`).

No default do Núcleo Único isso é **10 candidatos densos contra 30 + 30
lexicais**. Aritmética do RRF: o melhor hit denso vale `1/61 = 0,01639`; um chunk
**ausente** do resultado denso mas em 1º lugar nas **duas** pernas lexicais vale
`2/61 = 0,03279` — o dobro. E as duas pernas lexicais operam sobre a **mesma
coluna** `kc.conteudo` (`:312` e `:357`): o mesmo sinal léxico é contado duas
vezes.

Como a saída é truncada em `limite` (`:387`), acrescentar uma perna correlacionada
**pode** empurrar um hit denso relevante para fora do top‑k. Isso contradiz a
justificativa registrada em `tests/test_cadeia_provedores_qualidade.py:152-158`
("não há como piorar recall, só somar candidato"), que é o teste que documenta a
decisão de ligar HyDE+FTS. A decisão foi tomada sobre premissa aritmeticamente
falsa e sem medição (ver A‑18).

### A‑20. O `score` devolvido não é comparável entre pernas — e é consumido como se fosse

Quatro produtores, quatro escalas incompatíveis no mesmo campo:

| Origem | Linha | Escala |
|---|---|---|
| densa | `ai_service.py:532` — `round(1 - r.dist, 4)` | cosseno ∈ [0,1] |
| trigram | `ai_service.py:335` — `round(float(r.sim), 4)` | similaridade trigram ∈ (0,05; 1] |
| FTS | `ai_service.py:382` — `round(float(r.rank), 4)` | `ts_rank_cd` — rank não normalizado, tipicamente 0,0x |
| fallback textual | `ai_service.py:586-594` | **campo `score` inexistente** |

`meta[cid]` só é preenchido quando o chunk ainda não existe (`:329`, `:376`): um
chunk visto pelas duas pernas mantém o cosseno; um visto só pela lexical carrega
trigram. O único score comparável — `rrf` (`:388`) — não é consumido por ninguém.

Consumidores que tratam tudo como a mesma escala:

- `knowledge_governance.py:790` — `max()` sobre cosseno, trigram e `ts_rank_cd`
  misturados, com `or` que engole um `0.0` legítimo e cai no `rerank_score`
  (logit do cross‑encoder).
- `frontend/src/components/KnowledgeGovernancePanel.tsx:730-733` — renderiza
  `Math.round(retrieval.top_score * 100)}%` sob o rótulo **"Score máximo: N%"**.
  Um `ts_rank_cd` de 0,06 vira "6%" e um cosseno de 0,82 vira "82%" no mesmo
  widget — a tela em que o curador decide se o documento está bem indexado.
- `ai/agent/tools/leitura.py:62` — entrega o número ao **LLM**, sem unidade.
- `ai/core/audit_logger.py:65-67` — grava na trilha `fontes_rag`.

Atenuante: nenhum dos dois formatadores de prompt inclui o score
(`ai_service.py:602-635`, `context_builder.py:271-279`); só o caminho agêntico o vê.

### A‑21. Ligar o reranker desativa silenciosamente o ranking jurídico

`reranker.py` soma um bônus de governança a duas bases **de escalas
incompatíveis**, com a mesma constante:

- rerank **OFF** (`:381-382`): `base = 1.0 - (index/size)` ∈ [0,1] — o bônus
  jurídico é proporcional e move o item alguns lugares;
- rerank **ON** (`:423`): `governance_score = float(score) + bonus`, onde `score`
  é a saída **crua** do cross‑encoder (`:129`, sem sigmoide nem normalização em
  parte alguma do arquivo). Logits de `bge-reranker-base` vivem em ordem de
  grandeza de unidades a dezenas.

Contra um logit dessa magnitude, o bônus calibrado para [0,1] é ruído numérico.
Ligar o reranker — a ação que se toma justamente quando se quer *mais* precisão —
anula a penalidade de norma revogada (`:38`), a de confiança `bloqueado` (`:236`),
o peso de autoridade e a aderência de tribunal/área.

Achado adjacente: mesmo no regime OFF, `confianca="bloqueado"` vale −0,10
(`:236`) — o documento é **empurrado, não excluído**.

### A‑22. O limiar de similaridade 0,55 é inerte sob o modelo em uso

`_RAG_MIN_SIM_DEFAULT = 0.55` (`ai_service.py:229`) → `max_dist = 0,45`
(`:232-239`), aplicado em `:490,506`. O modelo é `intfloat/multilingual-e5-large`
(`config.py:634`).

Modelos E5 são treinados com perda contrastiva *in‑batch* com temperatura e
produzem cossenos comprimidos na faixa alta: pares não relacionados no mesmo
idioma ficam tipicamente em ~0,70–0,78 e pares relacionados em ~0,80–0,92.
**0,55 fica abaixo do piso de ruído do modelo** — na prática não exclui nada, e a
seleção efetiva é feita inteiramente pelo `ORDER BY ... LIMIT` (`:512-513`).

O comentário de `ai_service.py:223-225` — "evita que matches fracos/irrelevantes
entrem como 'fonte' e poluam o contexto da IA (risco de alucinação)" — descreve
uma proteção que, sob o modelo atual, não existe.

**Corolário**: o fallback textual ILIKE só dispara quando a perna densa volta
**vazia** (`:535,542,546`). Com limiar que nunca morde, esse caminho é código
morto sempre que exista ao menos um chunk com embedding.

**Evidência empírica no repo para o valor 0,55: nenhuma.** O valor antecede a
troca do modelo (coluna passou por 768d em `013` antes de 1024d/e5 em `096`) e o
único teste (`tests/test_rag_isolation.py:39-46`) assere apenas a aritmética
`1 − sim`. Corrigir para ~0,80–0,85 sem eval set seria trocar um chute por outro
— o que reforça A‑18 como pré‑requisito.

### A‑23. O gate de citações verifica existência na base, não proveniência no contexto

`verificar_citacoes(db, texto, *, consultar_datajud=False)`
(`citation_check.py:269-274`) **não recebe o conjunto recuperado**. As consultas
batem em `knowledge_docs` com `_filtros_gate_rag` (`citation_check.py:29-40`,
`:190-205`), ou seja, contra **toda a base curada**.

Consequência: uma súmula ou artigo que **existe na base mas nunca foi recuperado**
para aquela resposta passa como "confirmada". A propriedade que o system prompt
declara — "use APENAS as fontes fornecidas no contexto [FONTES]"
(`ai_service.py:32`) — não tem implementação de runtime. A única medição de
groundedness é o LLM‑as‑judge **offline** do harness (`app/eval/run_eval.py --judge`).

`sem_base_verificavel` (`ai/core/response_validator.py:167-173`) é a versão mais
fraca possível da propriedade: dispara só quando `exige_fonte` **e** `fontes`
vazio **e** zero citações confirmadas. Um único chunk recuperado, de qualquer
relevância, desliga o aviso.

**Ponderação honesta**: o pior caso — citação **fabricada** (súmula/artigo que não
existe) — **é** pego, e o `citation_gate` bloqueia de fato, falhando fechado
(`citation_gate.py:58-67,337-400`: valor inválido de política coage para
`bloquear`; exceção sob `bloquear` vira 503; override exige justificativa em
AuditLog). Some‑se o HITL obrigatório. O que falta é a camada de proveniência, e
ela é o que separa "a norma existe" de "a norma sustenta esta afirmação".

### A‑24. Pertinência desligada por padrão

`PERTINENCIA_ENABLED: bool = False` (`config.py:309`, `ai/pertinencia.py:186`), e
por decisão explícita o módulo não roda na geração (`pertinencia.py:49-58`). O
erro canônico descrito no próprio cabeçalho do módulo (`:10-13` — art. 373, I do
CPC citado para inversão do ônus da prova) não é pego por nada na configuração
default. Decisão documentada, mas é a lacuna que A‑23 deixa em aberto.

### A‑25. A seção de fontes é a primeira a ser cortada, e o gate não sabe

No Núcleo Único, `"fontes"` é a **última** entrada de `ORDEM_SECOES`
(`context_builder.py:43-46`); as seções são ordenadas e concatenadas, e o corte
total (`:466-469`) apara pelo **fim**. Quando o contexto passa de
`AI_CONTEXTO_MAX_CHARS = 60000` (`config.py:202`) — trivial com um documento GED
de `_MAX_DOC = 18000` (`context_builder.py:34`) mais dossiê —, as fontes RAG são
o primeiro conteúdo descartado.

Enquanto isso `ctx.fontes` permanece **íntegro** (`:449,455-463`) e é entregue
como está a `response_validator.validar(..., fontes=ctx.fontes)`
(`orchestrator.py:307`) e ao AILog (`:325`). **O gate e a trilha de auditoria
registram fontes que o modelo nunca viu.**

### A‑26. A situação jurídica da fonte não chega ao prompt no Núcleo Único

O reranker calcula rótulo e `warning` de situação jurídica (`reranker.py:203-213`).
Isso vira texto do prompt apenas em `ai_service._formatar_fontes`
(`:602-635`, com "⚠ {rotulo}" em `:623-628`) — o caminho **legado**. O Núcleo Único
usa `context_builder._formatar_fontes` (`:271-279`), que emite **somente** título,
categoria e trecho. No caminho orquestrado o modelo nunca sabe que uma fonte é
"Vigência não verificada", "Parcialmente revogada" ou "Suspensa".

### A‑27. A regressão de precisão mede o caminho errado

`tests/test_rag_avaliacao_precisao_dblevel.py:10-15` declara que o baseline
(Hit@5 = 47,6%, MRR = 0,202) foi observado no **caminho textual/ILIKE, com
embeddings desligados**. Mas `EMBEDDINGS_ENABLED` é `True` por default
(`config.py:620`) e `scripts/ci-local.sh` não sobrescreve — no portão local o
teste exercita o caminho **denso** contra um piso (30% / 0,12, `:79-84`)
calibrado para o textual. Com HyDE ligado (C‑2), o alvo ainda é móvel.

Some‑se que **Hit@5 = 47,6% em 21 perguntas sobre súmulas** — o corpus mais fácil
que existe na base, e o único imune ao gate de C‑1 — é um número ruim que ninguém
está tratando como alerta.

### A‑28. O ranking jurídico multifatorial não tem cobertura ponta a ponta

`tests/test_rag_ranking_juridico_multifatorial.py` chama apenas `reranker._enrich`
diretamente e assere sinal/ordem de entradas individuais de `governance_factors`.
**Nunca chama `rerank()`, nunca verifica que qualquer fator altera a ordem final,
e nunca exercita nenhum dos dois regimes de escala.** O teste de quarentena
(`:95-99`) é *string matching* sobre `inspect.getsource`. É precisamente por isso
que A‑21 passou despercebido.

---

## 4. Achados MÉDIOS

| # | Achado | Evidência |
|---|---|---|
| M‑1 | Controle de segurança de `GET /rag/docs` vive em monkeypatch de runtime, não no router: ler `rag.py:390-419` dá quadro falso (induziu um subagente ao erro nesta própria auditoria) | `ai_core_hardening_patch.py:118-212`, `event_subscribers.py:48-61`, `main.py:190,458` |
| M‑2 | Conteúdo RAG entra no prompt **sem** `delimitador` em vários caminhos: `_formatar_fontes` usa rótulo fixo `[FONTES]`; idem `peca_service.py:918-924`, `anexos_service.py:496-506`, `checklist_ia.py:82-88`, `intake.py:210-213`, `agent/loop.py:108-118` | `ai_service.py:602-635` × `ai/delimitador.py:53-73` |
| M‑3 | C4 residual: call sites com caso conhecido que não passam `scope_case_id` — intimação de outro processo do mesmo cliente entra no contexto | `ai.py:727,1051`, `ai_tools.py:151`, `ai_skills.py:122`, `teses.py:571,692`, `validador_juridico_service.py:526` |
| M‑4 | Comentário falso: `teses.py:699` diz "precedente interno restrito ao caso", mas `_CASE_SCOPED_CATS` cobre só `comunicacao_processual` | `ai_service.py:89` × `teses.py:699` |
| M‑5 | `GET /rag/knowledge-base/status` com chave sem `client_id` não filtra tenant: confirma existência, `doc_id` e `versao` de docs de qualquer cliente (não vaza conteúdo). `ApiKey` sem `expires_at` | `rag_public.py:159-160,477`; `models/api_key.py` |
| M‑6 | `POST /legal-docs/{id}/validar` deriva escopo RAG de `d.client_id` sem ownership quando a peça não tem `case_id` | `routers/legal_docs.py:484-496`, `:794-798` |
| M‑7 | `status_indexacao` não filtra recuperação: doc em `sem_embeddings`/`erro` conta como usável no gate e nas métricas | `models/rag.py:54`; zero ocorrências em `ai_service.py` |
| M‑8 | Os 8 jobs de ingestão RAG não batem ponto por resultado nem estão em `JOBS_MONITORADOS` — contraria a regra do `CLAUDE.md` | `scheduler.py:1791-1913` × `heartbeat_service.py:13-22` |
| M‑9 | Contadores incrementados antes do commit; `rollback` não os desfaz → `ja_produziu=True` e `execucoes_zeradas_consecutivas=0` mentem, cegando o detector de coletor morto | `camara.py:59-72`, `senado.py:63-78` × `ingestion_service.py:497-519` |
| M‑10 | `EMBEDDINGS_BATCH=16` limita o encode do ONNX, mas doc inteiro é materializado como lista de chunks e de vetores | `ingestion_service.py:400`, `reembedar_chunks_orfaos.py:88-89` |
| M‑11 | Chave legada `confianca='bloqueado'` é exibida como bloqueada mas **não** bloqueia: o gate lê só `confidence_level` | `ai_service.py:120` × `:245-247` |
| M‑12 | Normalização insuficiente para OCR: sem remoção de cabeçalho/rodapé/numeração de página, sem de‑hifenização, sem NFC, sem remoção de `\x00` | `ingestion_service.py:148-155` |
| M‑13 | `/ingest-url` colapsa **todo** whitespace inclusive `\n\n` → chunker perde fronteira de parágrafo | `routers/rag.py:271-274` |
| M‑14 | Drift ORM↔schema: `chave_origem index=True` no model sem b‑tree correspondente; índice atual é sobre `COALESCE(...)` e não casa com o lookup do upsert | `models/rag.py:49`; `109:56-63`; `ingestion_service.py:330-336` |
| M‑15 | Coluna órfã `knowledge_chunks.categoria` (DB‑only, nenhuma query a lê); invisível ao CI sem `SCHEMA_CHECK_DATABASE_URL` | `038:17-21`; `tests/test_schema_sync.py:12-16` |
| M‑16 | `chave_origem` sem `NOT NULL` — obrigatoriedade só em código | `006:31-32` × `ingestion_service.py:320-321` |
| M‑17 | `pgvector/pgvector:pg16` sem tag de versão: disponibilidade de `hnsw.iterative_scan` indeterminável a partir do repo | `docker-compose.yml:6` |
| M‑18 | Pré‑voo de deploy verifica 1 das 3 flags de gate, e só sob marker | `scripts/deploy_manual.sh:106-112` |
| M‑19 | `DATA_CONFERENCIA = "2026-07-18"` vs limiar de frescor de 14 dias para súmulas: corpus inteiro sinalizado `stale_source` e ainda recuperável | `sumulas_ingestion.py:31` × `knowledge_governance.py:255-256` |
| M‑20 | Painel de curadoria limitado a 100 docs, sem paginação/busca/filtro | `KnowledgeGovernancePanel.tsx:256` |
| M‑21 | `AILog.prompt_sanitizado` persiste o conteúdo do chunk em claro (o nome do campo promete o contrário) | `ai_service.py:954` |
| M‑22 | Ingestão manual gera duplicata por mudança de título ou de autor | `routers/rag.py:97-104` |
| M‑23 | Grounding ao vivo falha **aberta**: alerta sem setar `revisao_obrigatoria`, ao contrário da falha do `citation_check`, que fecha | `ai/core/response_validator.py:151-155` × `:86-93` |
| M‑24 | `_hidratar_governanca` abre `AsyncSessionLocal()` própria em **toda** busca RAG, mesmo com reranker OFF (`rerank()` é chamado incondicionalmente) | `reranker.py:164`; `ai_service.py:541,596` |
| M‑25 | ~~Gate de governança do reranker falha **aberta**~~ **RESOLVIDO** (`a9451cb`): o `except` de `_hidratar_governanca` não devolve mais os candidatos originais — `reranker.py:237-243` filtra com `_candidato_normativo` e mantém somente candidatos não normativos, fechando o fail‑open para legislação, normas, regulamentos e autoridades `oficial_normativa` | `reranker.py:237-243` |
| M‑26 | `confianca="bloqueado"` no reranker apenas rebaixa (−0,10), não exclui | `reranker.py:236` |
| M‑27 | `--smoke` do `run_eval` valida **formato**, não recuperação; `run_legal_smoke_tests` (5 perguntas) checa presença de termo em qualquer posição do top‑5, ignorando rank | `run_eval.py:393-433`; `knowledge_governance.py:802-827` |

---

## 5. Confirmado sólido (não re‑auditar sem reprodução)

- **Isolamento por cliente**: `_FILTRO_ESCOPO_RAG` (`ai_service.py:73`) é
  fail‑closed por semântica SQL — doc restrito com `client_id IS NULL` produz
  `NULL` na comparação e é excluído. Verificado a nível de banco em
  `tests/test_rag_isolation_dblevel.py:67`. Write path simétrico
  (`ingestion_service.py:315-319`, `routers/rag.py:118-123`).
- **Ausência de injeção SQL** nos caminhos de recuperação: toda entrada de
  usuário em bind param (`:q`, `:t{i}`, `:cats`, `:scope_cli`, `:scope_case`,
  `:vec`, `:lim`, `:max_dist`, `:incl_hist`); f‑strings interpolam apenas
  constantes de módulo e fragmentos derivados de booleans de `settings`.
- **Barreira LGPD antes de provedor externo**: `_chamar_com_barreira`
  (`ai_gateway.py:386-428`) com três passadas de pseudonimização (entidades, PII
  estrutural, NER local) e segunda barreira `validar_sem_pii_pseudonimizado`.
  `AI_REQUIRE_SANITIZATION_FOR_EXTERNAL=True` com guarda de boot
  (`config.py:1317-1324`).
- **`rag_public.py` não é anônimo**: ambos os endpoints exigem API key com
  escopo, `hmac.compare_digest`, rate limit pré‑auth por IP, SSRF com pin de IP,
  recusa cross‑tenant no payload, e **todo item ingerido nasce `pendente`**
  (`rag_public.py:392`) — integrador comprometido não planta conteúdo citável.
- **Soft‑delete**: `deleted_at IS NULL` presente nas quatro pernas de recuperação
  e nas consultas de verificação de citação.
- **RBAC de `rag_governance.py` e `google_drive_knowledge.py`**: 7/7 rotas com
  `require_roles`, piso efetivo `socio`.
- **Versionamento**: unicidade da versão vigente garantida por índice único
  parcial no banco, com saneamento idempotente antes de cada troca (`092`, `109`)
  e downgrades que nunca apagam linha. Escrita de nova versão é transacional.
- **Cadeia Alembic**: head único `155_indices_listagem_espinha`, coerente com
  `MIGRATION_RESERVATIONS.md:5`. Sem heads múltiplos, sem `down_revision` órfão.
- **Dimensão do vetor**: não há risco de coexistência 768/1024 — `vector(N)` tem
  typmod fixo e a coluna legacy foi removida em `145:96`. O risco remanescente é
  `embedding IS NULL` (recall), não inconsistência de tipo.
- **FK `knowledge_chunks.doc_id`** com `ON DELETE CASCADE` coerente com o ORM.
- **Índice FTS de expressão** casa exatamente com a query
  (`001:427-429` × `ai_service.py:362-363`).
- **Fluxo `POST /rag/governanca/docs/{id}/revisar`**: notas obrigatórias,
  confiança na mesma transação, bloqueio sob quarentena, audit log.
- **Quarentena de súmulas**: writer único e determinístico
  (`sumulas_ingestion.py:347`), chave estável, funcionando como projetado.

---

## 6. Correção da leitura anterior

O relatório de 03/09 (§5.3) fica assim atualizado:

| Item | Status hoje |
|---|---|
| C1 (seed sem vetor até o job horário) | **aberto** — não reexaminado nesta auditoria |
| C2 (doc sem governança nasce aprovado) | **parcialmente fechado** — a precedência de `knowledge_autoapproval.py:74-97` protege status explícito; resta o fail‑open de grafia (A‑14) |
| C3 (métricas contam o que o gate exclui) | **parcialmente fechado** — fragmento unificado; `WHERE` ao redor ainda diverge (A‑11) |
| C4 (`scope_case_id` em 5/37 call sites) | **majoritariamente fechado** — ~15 call sites propagam; 6 residuais (M‑3) |
| C5 (`legal_chunker` corta em 2.400) | **fechado no código novo, aberto no passivo** — teto agora é `min(2400, EMBEDDINGS_MAX_CHARS)`; chunks legados nunca re‑cortados (A‑8.3) |
| C6 (`rag_public` aceita `client_id` arbitrário) | **fechado** — `_validar_escopo_lote` (`rag_public.py:256-303`) recusa cross‑tenant |

---

## 7. Ordem de correção sugerida

**Onda 1 — desbloquear o RAG (sem isso, o resto é otimização de algo que não roda):**

1. **C‑1**: produtor automático de vigência. Duas opções não excludentes:
   (a) o Planalto passa a gravar `legal_status='vigente'` +
   `legal_status_verificado_em` **somente com verificação positiva rastreável** —
   declaração explícita de vigência no texto compilado na fonte oficial ou
   conferência curada e registrada; a ausência de marcador de revogação **não**
   constitui prova positiva (o contrato fail‑closed de `ingestors/planalto.py:315-355`,
   testado em `tests/test_planalto_vigencia_segura_p01.py:38-46`, trata silêncio
   como `vigencia_nao_verificada` porque o texto pode não declarar o estado
   jurídico do diploma — norma pode estar suspensa, parcialmente revogada ou
   desatualizada sem que o cabeçalho o indique); (b) script de backfill em lote
   com trilha de curadoria identificada, fonte oficial HTTPS e conferência de
   vigência, substituindo o clique a clique. Excluir `proposicao_legislativa` do
   recorte `%legisl%` — proposição não é norma vigente e o gate não deveria
   alcançá‑la por acidente de substring.
2. **C‑2**: `RAG_HYDE_ENABLED` e `RAG_FTS_ENABLED` alinhados ao que o código
   documenta, ou propagação de `modo_sanitizacao` até `_hyde_expandir`.
3. ~~**C‑3**~~: achado retirado na revisão — o hardening de
   `ai_core_hardening_patch.py` já resolve o escopo do `precedente_interno`;
   resta apenas o teste de regressão com `alimentar_rag=True` (baixa prioridade,
   rede de proteção — ver seção C‑3).

**Onda 2 — fechar o que é segurança:**

4. **A‑1**: `andamento_processual` estático em `_RESTRICTED_CATS`.
5. **A‑2**: `/rag/ingerir-ai-log` nasce `pendente`, com allowlist de categoria,
   `client_id`/`case_id` do log, `require_roles` e audit log.
6. **A‑3**: `modo_sanitizacao=await modo_sigilo_por_case_id(db, case_id)` nos sete
   serviços, com teste que varre `inspect.getsource` dos módulos que recebem
   `case_id` (padrão já usado em `tests/test_rag_isolation.py:160`).
7. **A‑6**: trocar os dois casts `::boolean` pela comparação textual.

**Onda 3 — recall e custo:**

8. **A‑4**: `kc.conteudo % :q` com `SET LOCAL pg_trgm.similarity_threshold`.
9. **A‑5**: `hnsw.iterative_scan` (após fixar a tag do pgvector, M‑17) ou índice
   parcial com as flags de gate desnormalizadas em `knowledge_chunks`.
10. **A‑10**: dedup por `hash_conteudo` cross‑chave no `upsert_documento`.
11. **A‑19**: igualar o pool das pernas antes da fusão (`_n_pool` como pool de
    **todas** as pernas, não só da densa) e decidir se FTS e trigram, que leem a
    mesma coluna, devem votar duas vezes.
12. **A‑21**: normalizar a saída do cross‑encoder (sigmoide) antes de somar o
    bônus, ou escalar o bônus ao regime — **antes** de qualquer avaliação de
    ligar o reranker.
13. **A‑25/A‑26**: mover `"fontes"` para antes de `"documento_ged"` em
    `ORDEM_SECOES` (ou truncar por seção), e emitir a situação jurídica no
    `_formatar_fontes` do Núcleo Único, como já faz o caminho legado.

**Ondas 1–3 dependem da 4 para serem avaliadas.** A ordem acima é de risco, não
de sequência: A‑18 pode e deve começar em paralelo, porque é a única que não
depende de nenhuma das outras.

**Onda 4 — a régua:**

14. **A‑18**: 75 casos humanos no gold set e `run_eval` (não `--smoke`) no
    `.woodpecker.yml`. Corrigir também A‑27, cujo piso está calibrado para um
    caminho de busca diferente do que o portão local executa.

---

## 8. Achados que viram Issue própria (fora do escopo desta auditoria)

- `cases.py:1039` (C‑3) — achado retirado na revisão (ver seção C‑3); sem issue própria.
- `camara.py`/`senado.py` (M‑9) é telemetria de ingestão.
- `ocr_service.py` (A‑16) afeta todo upload de documento, não só RAG.
- `RUNBOOK_MIGRACAO_EMBEDDING_1024.md` (A‑17) é correção de runbook.

---

## 9. Hipóteses levantadas e **descartadas** na verificação

Registradas para que não voltem em auditoria futura como achado novo.

- **"`GET /rag/docs` está sem RBAC e sem filtro de cliente."** Falso. O código do
  router (`routers/rag.py:390-419`) de fato não tem guarda, mas o callable é
  **substituído em runtime** por `_listar_docs_escopado`
  (`ai_core_hardening_patch.py:118-212`), instalado com `raise` em
  `event_subscribers.py:48-61` (import em `main.py:190`), antes do
  `include_router` em `main.py:458`. A listagem publicada aplica `is_gestao`,
  escopo por `client_id` e visibilidade por caso. O problema real é de
  auditabilidade, registrado como **M‑1** — a leitura do router induz ao erro, e
  induziu uma das frentes desta própria auditoria.

- **"O `try/except` do `SET LOCAL hnsw.ef_search` deixa a transação abortada e
  zera o RAG."** Falso. O PostgreSQL aceita qualquer parâmetro de **nome
  composto** (`prefixo.nome`) como *placeholder* de opção customizada quando o
  prefixo não é reservado por extensão carregada; e, com pgvector carregado — o
  que é certo, já que a coluna é `vector` —, `hnsw.ef_search` é GUC real desde a
  0.5.0. O `try/except` de `ai_service.py:520-523` é inócuo em ambos os casos.

- **"Existem chunks com embedding de dimensão antiga (768) convivendo com 1024."**
  Falso por construção. `vector(N)` tem typmod fixo: o servidor rejeita no INSERT
  qualquer vetor de dimensão diferente, e a coluna legada foi removida em
  `145_drop_orphan_db_only_columns.py:96`. O risco remanescente é
  `embedding IS NULL` (chunk órfão → perda de recall), não inconsistência de tipo.

- **"`rag_public` expõe o acervo sem autenticação."** Falso. O prefixo está no
  bypass do JWT (`core/auth_middleware.py:34`), mas ambos os endpoints exigem API
  key com escopo (`rag_public.py:308-318,454-464`), com comparação por
  `hmac.compare_digest`, rate limit pré‑auth por IP, SSRF com pin de IP e recusa
  cross‑tenant no payload. Nenhum endpoint devolve `conteudo`. Resta apenas o
  vazamento de **metadado** com chave sem `client_id` (**M‑5**).

- **"`veredito_ia.py` sofre da dívida C4 (intimação de outro caso)."** Falso na
  prática: não passa `scope_case_id`, mas restringe `categorias` a
  `["jurisprudencia","sumula_stf","sumula_stj","sumula_tst"]`
  (`core/veredito_ia.py:59,192`) — `comunicacao_processual` nunca entra. Fica de
  fora de **M‑3**.
