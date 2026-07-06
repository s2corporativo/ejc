# Relatório de Execução — Correção Total do Sistema EJC — 2026-07-06

_Execução do prompt "Correção Total do Sistema EJC" a partir de uma auditoria
funcional (black-box) de produção. Método obrigatório respeitado: **mapear e
reproduzir a causa no código-fonte antes de qualquer alteração** (a hipótese do
relatório de auditoria foi tratada como hipótese qualificada, não como
diagnóstico). Branch única: `claude/ejc-system-full-correction-xvfldl`; um commit
atômico por item; nenhum dado de produção tocado._

## 0. Método e evidência global

- **Investigação primeiro:** 20 investigadores paralelos mapearam cada achado
  contra o código atual (o EJC já passou por várias rodadas de auditoria — vários
  `RELATORIO_*.md` no repo — então nada foi presumido).
- **Backend:** suíte `pytest` completa em venv isolada → **835 passed, 43 skipped**
  (baseline era 828; +7 testes novos do item 1.1). Import de `app.main` OK.
  Teste de contrato rotas front↔back **verde**. Cadeia de migrations íntegra
  (head único `077`).
- **Frontend:** `tsc --noEmit` **limpo** e `vite build` **limpo**.
- **Não executado neste ambiente (sem Postgres/stack de app no sandbox):** E2E de
  runtime. Itens que exigem validação em staging antes de produção estão
  sinalizados abaixo (Rule 5/6): reprocessamento de embeddings (3.1), execução dos
  seeds (4.3/5.6), migration do Kanban (5.5) e o fluxo de upload da importação
  (4.2). Todos idempotentes; rodar fora do horário do escritório, com backup.

---

## BLOCO 1 — Rastreabilidade e conformidade (CRÍTICO)

| Campo | Conteúdo |
|---|---|
| **Item** | **1.1 — Log de auditoria sem usuário/módulo/IP** |
| Arquivos | `frontend/src/pages/Auditoria.tsx`; `backend/app/routers/audit.py`; `backend/app/models/audit_log.py`; `backend/app/core/request_context.py` (novo); `backend/app/main.py`; `backend/tests/test_auditoria_ip_contexto.py` (novo) |
| Diagnóstico real | Hipótese do relatório ("usuário/IP não são passados ao writer") **meio correta**. Causa A: o frontend lia **chaves erradas** do contrato de `GET /audit/` (`l.modulo`/`l.usuario_id`/`l.descricao` em vez de `entidade`/`user_id`/`detalhes`) — por isso ação+horário apareciam mas módulo/usuário não. O DB **já gravava** user_id/role/entidade. Causa B: só `auth.py` passava `ip=`; os ~40 demais writers gravavam `ip=NULL` (por isso só LOGIN tinha IP). |
| Correção | (A) Alinhadas as chaves no frontend + filtro passa `entidade`; endpoint enriquecido com `user_nome` (LEFT JOIN em users) para exibir o **nome**, não o UUID. (B) `ClientIPMiddleware` (puro-ASGI) captura o IP real (respeita X-Forwarded-For) num ContextVar; `criar_audit_log` usa como fallback quando `ip is None` — cobre todos os writers sem tocar nos call-sites. |
| Teste | pytest: 7 testes novos (fallback de IP, precedência de IP explícito, ausência de contexto, extração X-Forwarded-For/X-Real-IP/socket). Suíte completa verde. tsc limpo. |
| Status | **Concluído** |

| Campo | Conteúdo |
|---|---|
| **Item** | **1.2 — HITL em 0% no painel de Governança** |
| Arquivos | `backend/app/routers/ia_governanca.py`; `frontend/src/pages/GovernancaIA.tsx` |
| Diagnóstico real | O enforcement HITL **existe e é correto** (bloqueio por código em `legal_docs.py`: peça de IA não vira aprovada/final/protocolada sem `human_reviewed`). O 0% é **defeito de métrica**: `taxa_hitl_pct` media `AILog.status_hitl` (marcação manual de log), que nunca é atualizado — a revisão grava em `LegalDoc.human_reviewed`. |
| Correção | Adicionado `hitl_pecas_pct` = peças de IA revisadas / geradas (ligado ao controle imposto). O card do painel passa a exibir essa cobertura real; o ratio de log é mantido como `taxa_hitl_logs_pct` (diagnóstico). **Enforcement não alterado.** |
| Teste | Suíte de governança/HITL verde (56 testes na área). tsc limpo. |
| Status | **Concluído** — decisão de métrica aplicada com o default recomendado (cobertura de peças). Ver §Decisões. |

---

## BLOCO 2 — Estabilidade

| Item | Arquivo(s) | Diagnóstico real | Correção | Status |
|---|---|---|---|---|
| **2.1** tela branca `/sociedade` | `pages/Sociedade.tsx` | `GET /sociedade/distribuicao` retorna envelope `{items:[...]}`; o unwrap `?.data ?? data` guardava o **objeto** cru → `distrib.reduce` quebrava. Não dependia de "zero sócios". | Lê `.items` com guarda `Array.isArray` em todos os fallbacks. | **Concluído** (tsc/build limpos) |
| **2.2** erro `/diario-oficial` | `pages/DiarioOficial.tsx` | `GET /alertas` retorna `{items:[...]}`; guardava o objeto em `alertas` → `alertas.map` quebrava. Bônus: contador lia `res.data.count` sendo que a API devolve `{nao_lidos}`. | Guarda `Array.isArray` em `alertas`; corrige a chave do contador. | **Concluído** |
| **2.3** padrão sistêmico `.map/.reduce` | 25 arquivos (frontend) | 44+ pontos faziam `.map/.reduce` sobre resposta de API sem garantia de array (setter guardava resposta crua; guarda `.length` não protege não-array). | Normalização defensiva (`Array.isArray`) no setter ou na leitura de envelope — **46 pontos** hardenizados, sem alterar happy-path. Portal do cliente priorizado. | **Concluído** (tsc/build limpos) |
| **2.4** sem 404 | `pages/NotFound.tsx` (novo); `App.tsx` | Catch-all `path="*"` fazia `<Navigate to="/">` silencioso → Dashboard. | Página `NotFound` real; catch-all aponta para ela. | **Concluído** |

---

## BLOCO 3 — Base de Conhecimento / RAG

| Item | Arquivo(s) | Diagnóstico real | Correção | Status |
|---|---|---|---|---|
| **3.1** "100% sem vetor" | `backend/app/routers/rag.py` | **Não** era pipeline morto (provider local fastembed não exige chave). `GET /rag/docs` **omitia** `status_indexacao`; o badge recebia `undefined` → "Sem vetor" para todos os ~484 docs. | Endpoint passa a devolver `status_indexacao`/`tribunal`. **Ação de ops (staging/deploy):** rodar `scripts/reconciliar_status_rag.py` (idempotente) para corrigir rótulos defasados; só re-embeddar docs realmente sem chunk. | **Concluído (código)** — reprocessamento em lote pendente de execução em staging/deploy |
| **3.2** divergência Conhecimento×Curadoria | idem 3.1 | As duas telas liam fontes diferentes; Conhecimento nem recebia o campo de status. | Mesma correção de contrato unifica o estado exibido. | **Concluído** |
| **3.3** textos de RAG | `pages/AssistenteIA.tsx`, `AgenteIA.tsx`, `Conhecimento.tsx` | Textos prometiam resposta "com base no conhecimento do escritório" de forma incondicional. | Suavizados para "quando há documentos ingeridos/vetorizados". | **Concluído** |

---

## BLOCO 4 — Fluxo de Casos e Documentos

| Item | Arquivo(s) | Diagnóstico real | Correção | Status |
|---|---|---|---|---|
| **4.1** caso novo some no filtro | — | **Hipótese falsa contra o código.** O filtro "Ativos" (`cases.py`) exclui **só** `arquivado` — inclui `triagem`. Caso novo já aparece no default. | Nenhuma alteração necessária. | **Concluído (já correto)** |
| **4.2** doc da Importação IA não vincula | `components/ImportarDocumento.tsx`, `pages/Casos.tsx` | Confirmado: o PDF era analisado num tempfile e **descartado** (`os.unlink`), sem persistir nem vincular. | Retém o arquivo (`_arquivo_original`) e, após criar o caso, reenvia para `POST /documents/upload` com `case_id` (mesmo endpoint do upload manual — persiste, OCR, audit, vínculo). Best-effort. | **Concluído (código)** — validar upload real em staging |
| **4.3** classificação sem catálogo | `backend/seeds/seed_all.py` | `document_types_master` criada vazia (migration 062) e **nunca semeada** no bootstrap. Seed já existe e é idempotente. | `seed_all.main()` roda `redesign_seed.seed()` (via `asyncio.to_thread`, não-fatal). | **Concluído (código)** — seed roda no deploy |
| **4.4** doc não clicável | `pages/CasoDetalhe.tsx` | Linha do documento era `<div>` estático sem ação. | `onClick` baixa via `GET /documents/:id/download` (endpoint já validado), com cursor/hover. | **Concluído** |

---

## BLOCO 5 — Experiência e simplificação

| Item | Arquivo(s) | Correção | Status |
|---|---|---|---|
| **5.1** feedback "Verificar conflito" | `pages/Clientes.tsx` | Clique explícito emite toast (sucesso "nenhum conflito" / info campos insuficientes); conflitos reais seguem no Alert; onBlur silencioso. | **Concluído** |
| **5.2** blocos duplicados na Ficha | `pages/DossieCliente.tsx` | Removido bloco órfão (fora de aba) que renderizava Pendências/Contato/Financeiro uma 2ª vez. | **Concluído** |
| **5.5** Kanban sem colunas | `alembic/versions/077_seed_kanban_columns.py` (novo); `tests/test_smoke.py` | Migration idempotente semeia colunas por `legal_area`, com nomes **alinhados** ao sync coluna→status. | **Concluído (código)** — migration roda no deploy |
| **5.6** seletor de Ferramenta vazio | `backend/seeds/seed_all.py` | `ejc_skills` nascia vazia; `seed_all.main()` roda `skills_seed` + `skills_ferramentas_seed` (idempotentes). | **Concluído (código)** |
| **5.8** "Processos"→"Consulta DataJud (CNJ)" | `components/Layout.tsx` | Renomeado só o label (rota `/datajud` mantida). | **Concluído** |
| **5.10** "IA Jurídica" e "Radar de Poder" duplicados | `pages/Dashboard.tsx` | Atalho "Radar de Poder" aponta para `/radar-regulatorio` (diferencia); "IA Jurídica" segue em `/inteligencia`. | **Concluído** |
| **5.11** tema fora de escopo | `backend/app/routers/intelligence_v3.py`, `components/RadarLegislativo.tsx` | Removido `"veterinario"` das keywords e "medicamentos veterinários" da legenda (mantido `"medicamento"` por relevância ANVISA/tributária). | **Concluído** |

### Itens que dependiam de decisão do usuário — DECIDIDOS e implementados

| Item | Decisão do usuário | Correção | Status |
|---|---|---|---|
| **5.3** | Hub sem migrar dados | `KnowledgeHub` ganha cards de categoria (Base de Conhecimento, Biblioteca de Estratégias, Memória Institucional) que navegam para as fontes existentes; menu unifica numa única entrada "Conhecimento". Sem migração de dados. | **Concluído** |
| **5.4** | Unificar em abas c/ redirects | `/financeiro` (já um workspace com abas) passa a ler `?tab=`; `/honorarios`, `/despesas`, `/sociedade` redirecionam para a aba correspondente; itens de menu duplicados removidos. | **Concluído** |
| **5.7** | Criar tela de Configurações real | Nova tela `Configuracoes` (Aparência com seletor de tema funcional; Conta/segurança; Administração→Usuários p/ admin). Menu "Configurações"→`/configuracoes`; "Usuários" vira entrada própria. | **Concluído** |
| **5.9** | Adicionar ponto de entrada | Link "Portal do Cliente" no cabeçalho do Dossiê do Cliente abre `/portal` em nova aba (o portal já existe para contas `cliente_externo`). | **Concluído** |

---

## BLOCO 6 — Testes pendentes (não cobertos pela auditoria original)

Estes são **testes de validação**, a executar em staging (não são correções de
código): logout + login inválido; permissões por perfil (advogado/estagiário/
financeiro); Lixeira (exclusão lógica + restauração) em ambiente não produtivo;
responsividade mobile/tablet. Recomenda-se executá-los após o deploy dos Blocos
1–5 em staging.

---

## Decisões pendentes do usuário

| # | Item | Default aplicado (se houver) | Pergunta em aberto |
|---|---|---|---|
| 1.2 | Métrica HITL | Cobertura de peças de IA revisadas (recomendado; display-only, reversível) | Manter esse denominador ou usar o ratio de log? |
| 5.11 | Radar | Removido "veterinario"; mantido "medicamento" | Remover também "medicamento"? |
| 5.3 | Unificar conhecimento | **Decidido:** hub sem migrar dados → **implementado** | — |
| 5.4 | Unificar financeiro | **Decidido:** abas + redirects → **implementado** | — |
| 5.7 | Configurações/Usuários | **Decidido:** tela de config real → **implementado** | — |
| 5.9 | Portal do Cliente | **Decidido:** ponto de entrada → **implementado** | — |

---

## Rollback

Cada item é um commit atômico e independente → `git revert <sha>` reverte um item
sem afetar os demais. Migrations têm `downgrade` funcional. Nenhum dado de
produção foi tocado; os seeds e a migration 077 são idempotentes e aditivos.
