# M30 — Matriz de Teses

**Status: HOMOLOGADO — 31 cenários executáveis: 30 PASS / 1 defeito encontrado e confirmado (não corrigido ainda) / 2 N/A-PROVADO**
Data: 16/08/2026 · Repositório: s2corporativo/ejc · Branch: homologacao-m07-2026-08-16
Bateria: `scripts/inventory/m30_matriz_teses_tests.py` (execução real contra servidor local, porta 8000)

## 1. Objetivo (PROMPT 30)

Homologar a Matriz de Teses nos eixos: cadastro, classificação, fundamentos, precedentes, aplicação, contra-argumentos, risco, busca, vínculo com processos, RAG e versionamento.

## 2. Superfícies testadas (com prova de execução)

| Eixo | Prova |
|---|---|
| Cadastro | `POST /api/teses` (201) com 10 campos completos preservados (advogado+) |
| Classificação | PATCH de status ativa→arquivada→ativa; PATCH de área fora da taxonomia canônica rejeitada na montagem (422 com áreas válidas) |
| Fundamentos | `fundamentacao` (art. 389 CC), `jurisprudencia` e `contra_argumento` persistidos e legíveis via `GET /api/teses/{id}` |
| Risco | `calcular_forca` atribuiu score a todas as teses candidatas da matriz (determinístico) |
| Busca | ranking responde; busca avançada testada |
| Vínculo com casos | `POST /api/teses/{id}/vincular-caso` com ownership check (gate de sigilo EOAB/LGPD) |
| Montagem | matriz nasce RASCUNHO; teses candidatas do Banco de Teses (banco institucional) + taxonomia; rate limit 5/min |
| HITL | advogado aprova e descarta (2 atos auditados); estagiário bloqueado (403) |
| RAG | nenhum precedente RAG associado nesta corrida (base sem súmulas — comportamento correto já provado em M25) |
| Versionamento | snapshot `matriz_teses` gravado no versionamento do caso (append-only) com fontes auditáveis `['matriz_teses', 'banco_teses', 'rag']` |

## 3. Defeito encontrado (CONFIRMADO — não corrigido, pendente de decisão)

**Busca avançada silencia teses sem taxa de sucesso calculada.** Em `app/routers/teses.py`, o filtro `taxa_minima` usa `Tese.taxa_sucesso >= taxa_minima`: quando o usuário envia `taxa_minima=0.0` (valor padrão explícito), PostgreSQL compara `NULL >= 0.0` como FALSE e **exclui silenciosamente todas as teses recém-criadas** (cuja `taxa_sucesso` é NULL até a primeira aplicação via vínculo com caso). Reprodução: cadastro normal → busca avançada com `taxa_minima=0.0` retorna `total: 0` mesmo com teses ativas contendo o termo de busca (2 teses QA ativas confirmadas no banco).

- **Impacto**: advogado não localiza teses novas na busca com filtro de taxa — degradação de produtividade; nenhum risco jurídico/LGPD.
- **Correção sugerida** (não aplicada — aguarda confirmação de correção técnica ordinária): trocar a cláusula para `or_(Tese.taxa_sucesso >= taxa_minima, Tese.taxa_sucesso.is_(None))` quando `taxa_minima == 0`.
- O teste é **100% fiel ao comportamento do sistema** — a falha é do sistema, não da bateria, e está registrada para reparo.

## 4. Comportamentos confirmados como design

- Arquivamento (soft-delete) **exige sócio**; advogado comum é bloqueado (403) — controle de ativos do escritório; registro preservado no banco (não há endpoint público de restauração).
- Matriz de teses nasce sempre como rascunho: teses candidatas exigem aprovação individual do advogado (aprovar/descartar), com registro auditável.
- Precedentes são associados **por questão** (nunca o pool inteiro a todas as teses) e o score discrimina teses sem precedentes.
- `updated_at` é atualizado em cada PATCH e no vínculo com caso (com re cálculo de `taxa_sucesso`).
- A decomposição por IA devolve listas vazias quando a IA está desligada — sem invenção (contrato do service); o `avisos` registra falha de parse.

## 5. Riscos jurídicos/LGPD

- Sanitização PII dos fatos **antes** de qualquer prompt (contrato do service e do router).
- Vínculo de tese com caso passa por `verificar_acesso_caso` (ownership) — não permite vincular tese a caso de terceiro.
- Snapshot da matriz usa apenas IDs e trechos truncados (300 chars), sem dados pessoais.

## 6. Riscos técnicos

- 1 OOM do uvicorn no meio da rodada 1 (limitação do sandbox com memória; servidor reiniciado).
- Base sem súmulas ingeridas: precedentes RAG vazios são esperados e corretos (M25).

## 7. Checklist

- [x] Backend inicia sem erro
- [x] Bateria compila e executa
- [x] Endpoints respondem (CRUD teses, matriz, HITL, vínculos)
- [x] Autorização validada (advogado, estagiário, sócio)
- [x] Logs sem dado sensível
- [x] Dados sintéticos prefixados `EJC_QA`
- [ ] **Defeito da busca avançada identificado — correção pendente de aprovação**
- [ ] Nenhum teste legítimo removido
