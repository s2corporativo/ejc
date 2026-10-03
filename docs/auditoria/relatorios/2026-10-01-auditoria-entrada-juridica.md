# Auditoria — Entrada Jurídica (módulo e ramificações)

- Data: 2026-10-01 · Base: `40144d6` (branch `claude/blissful-darwin-nr2i2v`)
- Método: leitura estática de código. **Nada foi executado** (sem testes, sem banco, sem navegador). Achados são afirmações sobre o código lido; os marcados "a reproduzir" exigem teste antes de correção.

## 1. Escopo e mapa

| Camada | Arquivos lidos |
|---|---|
| Routers | `routers/entrada.py`, `routers/entrada_universal.py` (+ `entrada_universal_vinculo`, só pela matriz de rotas) |
| Services | `entrada_service.py`, `entrada_juridica_service.py`, `entrada_expurgo_service.py` |
| Schemas | `schemas/entrada.py` |
| Jobs/config | `scheduler.job_expurgo_entrada_unica`, `ENTRADA_EXPURGO_*` |
| Frontend | `pages/EntradaUnica.tsx`, `EntradaUnica/{rascunhoStorage,types,DossieJuridico}`, registro em `moduleRegistry.tsx` |
| Infra | `nginx/ejc.conf` |
| Ramificações (só RBAC/entrada) | `routers/intake.py`, `triagem_entrevista.py`, `ficha_triagem.py` |

**Não lidos em profundidade** (declarar lacuna): `Confirmacao.tsx` (924 l.), `TelaEnvio.tsx`, `CadastroManual.tsx` (1339 l.), `entrada_universal_service.py`, `document_intelligence`, corpo de `intake.py`/`triagem_entrevista_service`/`ficha_triagem_service`, `entrada_universal_vinculo`, testes.

Fluxo: `/entrada` → `POST /entrada/analisar` (rascunho = `DocumentIntakeBatch`) → `POST /entrada/{id}/criar-caso` (uma transação) → `POST /entrada/analisar?case_id=` (dossiê + snapshot HITL) → Motor de Peça. Em paralelo, `/entrada-universal/*` (lote avulso/por caso) e `vincular-processo`.

## 2. Pontos conformes (verificados no código)

- RBAC: `/entrada/*` exige piso advogado; `/entrada-universal/*` exige equipe jurídica; rate limit em todas as rotas.
- Criação de caso atômica, com lock pessimista no rascunho (idempotência), gates de servidor de conflito (EOAB) e duplicidade, responsável validado, `documentos_ids ⊆ batch`, recusa de documento de outro cliente/caso, auditoria `ENTRADA_UNICA_CRIAR_CASO`.
- Carteira protegida colapsa sem vazar id (`pode_ver_cliente`/`pode_ver_caso_resumido`).
- HITL: toda saída de IA marcada `requer_confirmacao_humana`; snapshot nasce `congelado=False`; payload do snapshot sanitizado (PII).
- Prompt de documento delimita `<DOCUMENT_DATA>` como dado não confiável.
- Expurgo real bloqueado (fail-closed) e desligado por padrão.
- `GET /entrada-universal/{id}` audita leitura de PII por terceiros (LGPD art. 37).

## 3. Achados

Severidade: **A** alta · **M** média · **B** baixa. "Conf." = grau de certeza após a leitura.

| # | Sev | Conf. | Achado | Evidência |
|---|---|---|---|---|
| F1 | A | Alta (a reproduzir) | **CNJ descartado silenciosamente quando o advogado confirma "processo novo".** Em `provavel_correspondencia` + `processo_novo_confirmado=true` o 409 é liberado, mas o processo só é criado se `status_reconciliacao == "novo_processo"`. O caso nasce sem o CNJ que o próprio advogado declarou novo. Nenhum teste referencia `processo_novo_confirmado`. | `entrada_service.py` l.925-936 e l.1073 |
| F2 | A | Alta | **Reconciliação de CNJ é um snapshot da análise; não é reavaliada na criação** (TOCTOU). Entre `analisar` e `criar-caso`, outro usuário pode cadastrar o mesmo CNJ; o lock é só do rascunho. Duplicidade de processo/caso depende de unicidade no banco (não verificada). | `entrada_service.py` l.910-936 |
| F3 | M | Alta | **Limite de upload incoerente:** a UI e `/meta` anunciam 120 MB por lote (`MAX_BYTES_LOTE`), mas o nginx limita o corpo a **50 MB** (`client_max_body_size 50m`). Lotes de 50–120 MB falham com 413 do nginx (HTML, sem mensagem útil), antes do backend. | `nginx/ejc.conf` l.56; `entrada_universal_service.py` l.18-20; `types.ts` l.131 |
| F4 | M | Alta | **Contrato 60 vs 40:** o lote aceita até 60 documentos (`MAX_ARQUIVOS`) e a UI pré-seleciona todos (`selecionado = Boolean(documentId)`), mas `documentos_ids` no schema tem `max_length=40` → 422 em `criar-caso` com 41–60 documentos. | `schemas/entrada.py` l.67; `entrada_universal_service.py` l.18; `types.ts` l.279 |
| F5 | M | Alta | **`POST /entrada/analisar?case_id=` ignora `files`/`texto` sem aviso.** Quem envia arquivos junto com `case_id` recebe dossiê, e os arquivos são descartados silenciosamente. | `routers/entrada.py` l.63-66 |
| F6 | M | Alta | **Vazamento de mensagem interna:** `/entrada-universal/processar` devolve `str(exc)[:180]` no 500 e grava `str(exc)[:300]` em `extraction_meta` (pode conter caminho/PII do nome do arquivo). `/entrada/analisar` já usa mensagem genérica — inconsistência. Idem `str(exc)[:160]` no dossiê. | `entrada_universal.py` l.373 e l.488; `entrada_juridica_service.py` l.477, 504 |
| F7 | M | Média (latente) | **Expurgo pode apagar documento ainda em uso por rascunho mais novo.** Itens duplicados de outro lote apontam para o mesmo `document_id` (dedup por SHA). O expurgo só confere `case_id/client_id` do Document, não se outro `DocumentIntakeItem` (não vencido) o referencia. Hoje inerte (hard delete bloqueado, flag OFF) — corrigir **antes** de liberar #1359. | `entrada_universal.py` l.335-344; `entrada_expurgo_service.py` l.146-160 |
| F8 | M | Média (latente) | **Expurgo não distingue rascunho da Entrada Única de lote avulso de `/entrada-universal/processar`** (ambos `case_id IS NULL`, status `concluido`). O docstring promete só rascunhos de `entrada_unica`; o filtro exclui apenas `dpt360_oportunidade`. Lotes `processando` travados (crash) nunca são expurgados. | `entrada_expurgo_service.py` l.101-117 |
| F9 | M | Alta | **Lotes pré-caso criam Documents órfãos** (`case_id`/`client_id` nulos, confidencialidade `normal` fixa). Quem os enxerga e a política do GED para esse estado não foram verificados; confidencialidade forçada em `normal` independe do conteúdo. A verificar: `document_access_policy`. | `entrada_service.py` l.493-495; `entrada_universal.py` l.197-201 |
| F10 | B | Alta | **`vincular_lote_ao_caso` rehasheia do disco todos os documentos do caso** (`_sha256_arquivo` por arquivo) quando `Document.sha256` já existe (Achado 30). Custo O(N) de I/O por vínculo. | `entrada_universal.py` l.679-684 |
| F11 | B | Alta | **Leitura integral do upload antes do limite:** `await uploaded.read()` precede a checagem de 25 MB/arquivo; o teto efetivo é o do nginx (50 MB) × workers. Sem checagem prévia por `Content-Length`/streaming. | `entrada_universal.py` l.317-327; `entrada_universal_service.py` l.177 |
| F12 | B | Alta | **Status "protocolado" direto, sem `status_transicao`:** `vincular_processo` e `criar-caso` setam `caso.status = protocolado` à mão, contornando a máquina de transição usada em outros pontos (`avancar_status_por_evento`). Coerência de regra de negócio a confirmar com o titular (CNJ detectado ≠ protocolo comprovado). | `entrada_service.py` l.828-833, l.1083 |
| F13 | B | Alta | **Acoplamento de camada:** service de dossiê importa função privada de router (`intake_router._buscar_teses`); `entrada_service` importa privados de `entrada_universal` (`_analisar_ia`, `ingerir_arquivos_lote`). Dificulta teste e evolução. | `entrada_juridica_service.py` l.322-323; `entrada_service.py` l.490-505 |
| F14 | B | Alta | **Dossiê dispara 2+ chamadas de IA e cria snapshot a cada abertura** (`carregar` no `useEffect`, sem guarda). Remontagem (StrictMode em dev, retorno à aba) gera snapshots/versões e consome o limite de 6/min. | `DossieJuridico.tsx` l.128-130; `entrada_juridica_service.py` l.541 |
| F15 | B | Alta | **Cliente fixado por `client_id` na URL é só frontend:** `/entrada/analisar` não recebe o cliente, então conflito/duplicidade/reconciliação da análise são calculados sem ele (os gates do `criar-caso` ainda protegem). | `EntradaUnica.tsx` l.223-232; `entrada.py` |
| F16 | B | Alta | **Rascunho completo (fatos, dados extraídos) em `sessionStorage`.** Mitigado (some com a aba; decisão documentada), mas permanece legível por XSS e em máquina compartilhada. | `rascunhoStorage.ts` |
| F17 | B | Média | **Documento duplicado já vinculado a outro caso bloqueia `criar-caso` (422)** se vier pré-selecionado; a UI não alerta antes. | `entrada_service.py` l.1177-1180 |
| F18 | B | Média | **Rotas `entrada-universal` sem `requer_equipe_juridica` em `GET /{id}`, `preparar-pacote`, `vincular-caso`** (dependem só de ownership do lote/caso). Sem exploração identificada, mas é defesa em profundidade ausente e diverge de `/meta` e `/processar`. | `entrada_universal.py` l.520, 552, 645 |

### Ramificações (superficial)

- `intake`, `triagem/entrevista`, `triagem/ficha`: RBAC presente (piso advogado / equipe jurídica) e rate limit. Corpo dos services **não auditado**.
- Duplicidade de prefixo `/entrada-universal` (dois routers) já registrada no baseline M01; sem conflito de rota identificado.
- `CadastroManual` (perfis sem IA): **não auditado** — é a porta de secretaria/estagiário; prioridade na próxima rodada.

## 4. Plano de melhoria, correção e consolidação

Premissas: PRs pequenos, um por frente; correção de bug entra com teste de regressão (CLAUDE.md §7); migrations só se F2 exigir índice único (reservar número em `MIGRATION_RESERVATIONS.md`). Nenhuma alteração toca HITL, gate de citações, sanitização, kill-switch ou RBAC para baixo.

### Fase 0 — Confirmar (sem código de produção, ~0,5 dia)
1. Reproduzir **F1** (teste de service: `provavel_correspondencia` + `processo_novo_confirmado`) e **F4** (payload com 41 `documentos_ids`).
2. Verificar no banco/model se há unicidade de CNJ (F2) e a política de GED para Document órfão (F9). Resultado define se F2 exige migration.
3. Decisão do titular: F12 (semântica de "protocolado") e política de retenção (#1359) para F7/F8.

### Fase 1 — Correções de integridade (prioridade alta)
| Item | Ação | Teste de regressão |
|---|---|---|
| F1 | Criar o processo também quando `provavel_correspondencia` + `processo_novo_confirmado` (usar `numero_cnj` do rascunho validado). | service: caso nasce com processo e proveniência |
| F2 | Reavaliar `reconciliar_processo_entrada` dentro de `criar_caso_do_rascunho` (sob o lock); se o status piorar, 409 com candidatos. Índice único parcial por CNJ **somente** se Fase 0 mostrar ausência (migration + `alembic upgrade head` do zero). | service: CNJ cadastrado entre análise e criação → 409 |
| F4 | Alinhar limites: `documentos_ids` ≤ `MAX_ARQUIVOS` (constante única) ou UI limitar seleção. | schema: 60 aceitos; 61 → 422 |
| F6 | Mensagem genérica no 500 e em `extraction_meta`; detalhe só em log técnico sem filename. | router: corpo sem `str(exc)` |

### Fase 2 — Coerência e UX do contrato
| Item | Ação |
|---|---|
| F3 | Elevar `client_max_body_size` apenas nas locations `/api(/v1)/entrada*` **ou** reduzir `MAX_BYTES_LOTE`/`/meta` para o limite real; fazer `/meta` refletir o menor valor efetivo. Mudança de nginx passa pela esteira (deploy não manual). |
| F5 | Com `case_id`, rejeitar (422) se vierem `files`/`texto`, ou documentar explicitamente na resposta. |
| F14 | Guarda de re-execução no `useEffect` (ref/abort) e/ou reutilizar snapshot recente não aprovado em vez de criar novo a cada abertura. |
| F15 | Aceitar `client_id` opcional em `/entrada/analisar` (com `obter_cliente_autorizado`) para que conflito/duplicados/reconciliação usem o cliente fixado. |
| F17 | Marcar na proposta documentos já vinculados a outro caso e desmarcá-los por padrão. |

### Fase 3 — Pré-requisitos do expurgo (antes de liberar hard delete)
- F7: excluir do expurgo qualquer Document referenciado por item de outro batch não expurgável.
- F8: restringir o filtro a batches com `resultado ? 'entrada_unica'`; tratar `processando` antigo (marcar `erro` por timeout).
- Testes: batch A (vencido) e batch B (recente) compartilhando `document_id` → nada é apagado; lote avulso do `/processar` → fora do escopo.
- Só então discutir #1359 com o titular.

### Fase 4 — Consolidação estrutural
- F13: extrair `ingerir_arquivos_lote`, `_analisar_ia`, `_buscar_teses` para services dedicados; routers voltam a ser finos.
- F10: usar `Document.sha256` no vínculo.
- F11: validar `Content-Length`/tamanho por arquivo antes de ler em memória.
- F18: `requer_equipe_juridica` nas três rotas restantes, com teste de 403.
- Unificar os dois routers `/entrada-universal` ou documentar a divisão no ledger de rotas.
- F12: após decisão do titular, passar por `status_transicao`.

### Fase 5 — Lacunas de auditoria (próxima rodada)
`CadastroManual`, `Confirmacao.tsx`, `TelaEnvio.tsx`, `entrada_universal_service` (OCR/ZIP: zip-bomb, path traversal, `MAX_BYTES_ZIP_DESCOMPACTADO`), `entrada_universal_vinculo`, `document_intelligence`, services de triagem/ficha/intake, cobertura de testes do módulo. Recomenda-se acionar `security-auditor` (uploads/RBAC) antes de finalizar a Fase 2-3, conforme CLAUDE.md §8.

### Portões de verificação por fase
- Backend (F1, F2, F4, F5, F6, F7, F8, F10, F11, F13, F18): `ruff check app` + pytest da área + suíte completa uma vez antes do push; F2 com migration: `alembic upgrade head` do zero em PostgreSQL 16 + pgvector.
- Frontend (F14, F15, F17): `npm run lint && npm test && npm run build`.
- Nginx (F3): validar `nginx -t` e deploy pela esteira/`RUNBOOK_DEPLOY_MANUAL.md`.

## 5. Limitações desta auditoria
Análise estática; sem execução, sem acesso a produção (CLAUDE.md, regra 9) e sem leitura de ~40% do código do módulo (lista na seção 1). Os achados F1, F2, F9 e F14 têm consequências que dependem de comportamento em runtime/banco e devem ser reproduzidos antes de qualquer correção.
