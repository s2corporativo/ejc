# Matriz de consolidação dos PRs P0 (493–497)

Levantamento executado em **2026-07-27**, sobre a `main` no commit `1befdf0` — base comum
dos cinco PRs. Nenhum PR foi mesclado, fechado ou alterado para produzir este documento.

**Premissa recusada.** A hipótese de que o #497 substituiria os demais **não se confirma**:
os conjuntos de arquivos são majoritariamente disjuntos e o #497 não contém as correções de
regra jurídica do #493/#495 nem as correções de fluxo do #494. O que existe é sobreposição
parcial, e ela é destrutiva onde acontece.

## 1. Metodologia

Tudo verificado por diff real, não por descrição de PR:

```bash
git fetch origin main <branches>
git diff --name-only origin/main...origin/<branch>     # arquivos por PR
git diff --stat        origin/main...origin/<branch>   # volume por arquivo
comm -12 <(sort A) <(sort B)                           # sobreposição de arquivos
git merge-tree --write-tree --name-only origin/<A> origin/<B>   # conflito textual real
```

Estado do CI conforme consulta em 2026-07-27T01:30Z (runner self-hosted `ejc-vps`; os
gates de release/continuidade são `skipped` em PR por desenho).

## 2. Quadro geral

| PR | Objetivo | Branch | Head | Commits | Arquivos | Migrations | Testes novos | CI (snapshot) |
|---|---|---|---|---|---|---|---|---|
| **[#493](https://github.com/s2corporativo/ejc/pull/493)** | Áreas de Atuação — bloqueio de risco (Onda 1) e correção jurídica das 57 ferramentas (Onda 2) | `claude/new-session-inxvz2` | `983e3c1` | 13 | 22 (+5.963/−753) | nenhuma | 4 backend + 5 frontend | 7 jobs **na fila** |
| **[#494](https://github.com/s2corporativo/ejc/pull/494)** | Fluxos e rotas — guardas de BPM, deep-link com contexto, lifecycle, gate de protocolo | `claude/analysis-70hy7z` | `e6b1669` | 8 | 33 (+1.254/−27) | nenhuma | 3 backend + 6 frontend + evidências | 7 jobs **na fila** |
| **[#495](https://github.com/s2corporativo/ejc/pull/495)** | Auditoria hard — regras jurídicas, 2FA fail-closed, Data Room, webhook, mass assignment | `claude/new-session-4tyz91` | `b06ab2f` | 4 | 19 (+950/−211) | **122_data_room_token_hash** | 3 backend | **7/7 verde** |
| **[#496](https://github.com/s2corporativo/ejc/pull/496)** | Segurança de IA — HITL não contornável, LGPD em log, RAG DataJud, gate de citações | `claude/new-session-h6j254` | `09a7a64` | 3 | 27 (+587/−284) | nenhuma | 5 backend atualizados | **7/7 verde** |
| **[#497](https://github.com/s2corporativo/ejc/pull/497)** | 34 bloqueadores das auditorias documental e não-cognitiva — portal, documentos, assinatura, financeiro, auditoria WORM, CI/deploy | `claude/new-session-bhbv06` | `36f4b52` | 7 | 67 (+4.086/−209) | **122→127** (6) | 13 backend | backend, eval e frontend **verdes**; gates de release `skipped` |

Contexto (fora do recorte pedido, mas na mesma fila): **#492** (dossiê do cliente e
simplificação, 38 arquivos), **#498** (UX da Sala Jurídica, 2 arquivos) e **#482**
(gate de consistência de documentação, 19 commits atrás da `main`).

## 3. Matriz de conflitos (verificada por `git merge-tree`)

| | 494 | 495 | 496 | 497 |
|---|---|---|---|---|
| **493** | limpo | **conflito** — 4 arquivos | **conflito** — 1 arquivo | limpo |
| **494** | — | limpo | limpo | **conflito** — 1 arquivo |
| **495** | | — | **conflito** — 4 arquivos | **conflito** — 5 arquivos + colisão de migration |
| **496** | | | — | limpo |

Detalhe dos arquivos em conflito:

- **493 × 495** — `backend/app/routers/ramos.py`, `backend/app/routers/peca_geracao.py`,
  `frontend/src/pages/ramos/RamoBase.tsx`, `frontend/src/pages/ramos/ramosConfig.ts`.
- **493 × 496** — `backend/app/routers/ramos.py`.
- **494 × 497** — `backend/app/routers/legal_docs.py`.
- **495 × 496** — `backend/app/routers/analise_bancaria.py`,
  `backend/app/routers/evolution_webhook.py`, `backend/app/routers/ramos.py`,
  `frontend/src/pages/ramos/RamoBase.tsx`.
- **495 × 497** — `backend/app/core/two_factor_policy.py` (**resolvido**: a frente de 2FA
  sai dos dois PRs, seção 4.3), `backend/app/models/data_room.py`,
  `backend/app/routers/data_room.py`, `backend/tests/test_alembic_single_head.py`,
  `backend/tests/test_schema_dr_parity.py`, além da colisão do número **122** entre
  migrations diferentes.

Observação sobre `test_alembic_single_head.py`: os dois PRs precisam editá-lo porque o head
canônico está **fixado à mão** naquele arquivo. Isso torna todo PR com migration um
conflito garantido com qualquer outro PR com migration. A guarda genérica adicionada em
`backend/tests/test_migration_numbering_guard.py` cobre os mesmos invariantes sem
identificador fixo — e detecta a colisão do 122, que nenhum teste atual detectava.

## 4. Duplicações substantivas — o que precisa de decisão

### 4.1 Gate do demonstrativo de calculadora — **três implementações incompatíveis**

O mesmo risco ("regra errada → resultado plausível → documento formal → uso externo") foi
resolvido três vezes, de três formas, todas em `POST /pecas/demonstrativo`:

| PR | Onde mora a regra | Como bloqueia | Escopo |
|---|---|---|---|
| #493 | `backend/app/services/homologacao_ferramentas.py` (matriz de **não** homologadas) | **422**, campo `ferramenta` **opcional** (bypass registrado em log quando ausente) | por ferramenta |
| #495 | `backend/app/core/homologacao_ferramentas.py` (registro fail-closed, ausente = não homologada) + endpoint `GET /pecas/ferramentas/homologacao` | **409**, campo `ferramenta_endpoint` **obrigatório** | por ferramenta |
| #496 | flag global `PECAS_DEMONSTRATIVO_CALCULADORA_ENABLED` em `config.py` | **403** para todo mundo | global |

Dois módulos com o mesmo nome em pacotes diferentes (`services/` e `core/`), dois contratos
de request e três códigos HTTP para o mesmo evento. **Só um pode ficar.**

Recomendação: **manter o desenho do #495** (fail-closed, campo obrigatório, endpoint de
consulta para a UI) alimentado pelo **conteúdo do #493** (que sabe, ferramenta a ferramenta,
o que já foi corrigido e o que segue selado), em `app/core/homologacao_ferramentas.py`.
A flag global do #496 vira o kill-switch de emergência acima desse registro, não o gate
primário. Decisão do titular, porque muda o comportamento visível ao advogado.

### 4.2 Data Room — dois desenhos **opostos** para o mesmo segredo

| PR | Migration | Desenho | Consequência |
|---|---|---|---|
| #495 | `122_data_room_token_hash` | Converte `data_room_links.token` **no lugar**: o valor em claro deixa de existir no banco | Resolve o vazamento em dump/backup; irreversível (`downgrade` no-op documentado) |
| #497 | `124_data_room_token_hash` | **Adiciona** `token_hash` e **mantém** `token` em claro "para compatibilidade retroativa" | O segredo continua no banco — o achado que motivou a correção **permanece aberto** |

Os dois não podem coexistir, e o do #497 não fecha o vetor. Recomendação: **adotar o
desenho do #495** (hash em repouso, sem texto em claro), implementado na cadeia de
migrations do #497 para não renumerar. Ou seja: o #497 fica dono da migration, com o
conteúdo do #495.

### 4.3 2FA — **decisão do titular: não implementar** (resolvido)

Os dois PRs alteraram `backend/app/core/two_factor_policy.py` por iniciativa própria, com
semânticas incompatíveis entre si:

- **#495**: padrão ligado em qualquer ambiente; só desliga com valor explicitamente falso.
- **#497**: padrão ligado apenas em produção (`APP_ENV=production`).

**Decisão do titular (2026-07-27): não implementar 2FA.** O comportamento atual permanece —
2FA desligado por padrão, kill-switch preservado. Registrada em `docs/GOVERNANCA_IA.md`,
seção 11 (decisões permanentes), para que nenhuma auditoria futura a reabra: o fail-open é
**risco aceito pelo titular**, não achado pendente.

Consequência para a consolidação, a ser aplicada **antes** do merge:

| PR | O que sai |
|---|---|
| #495 | `backend/app/core/two_factor_policy.py` e `backend/tests/test_two_factor_policy.py` (revertidos para a `main`) |
| #497 | `backend/app/core/two_factor_policy.py` e `backend/tests/test_two_factor_kill_switch.py` (revertidos para a `main`) |

Efeito colateral positivo: some um dos cinco arquivos em conflito entre #495 e #497.
O #496 já respeitava a decisão ("o 2FA não foi tocado (decisão do titular)") e não muda.

### 4.4 Webhook do WhatsApp (LGPD) — mesma correção, duas vezes

`backend/app/routers/evolution_webhook.py`, mesmo achado (telefone e conteúdo em log):

- **#495** — mascara o telefone (`***1234`), loga só o tamanho do texto e **remove o
  `?token=` da query string** (segredo em URL vaza em access log).
- **#496** — não loga telefone nem conteúdo, e sanitiza `\n`/`\r` do payload externo
  (impede forja de linha de log).

As duas metades são complementares e não estão em nenhum dos dois sozinho. Recomendação:
**unir** — remoção do `?token=` (#495) + supressão total de telefone/conteúdo e
sanitização anti-forja (#496).

### 4.5 `ramos.py` — contratos divergentes para as mesmas regras corrigidas

Ambos corrigem o mesmo conjunto de regras (CLT 775, CPP 798, JEC/Lei 9.099, Lei 11.101,
Lei 14.071, Lei 14.905, EAREsp 676.608, EAREsp 738.991), mas com **nomes de campo e
formatos de resposta diferentes**:

| Item | #493 | #495 |
|---|---|---|
| Marco da recuperação judicial | `data_deferimento` | `data_deferimento_processamento` |
| Metadados da regra | `fontes`, `vigencia_regra`, `versao_regra` (59 ocorrências) | `base_legal`, `base` (13 ocorrências) |
| Cobertura | 57 ferramentas, com teste de invariante que exige regra versionada | subconjunto das ferramentas auditadas |

O `frontend/src/pages/ramos/ramosConfig.ts` de cada PR acompanha o seu próprio contrato.
Mesclar os dois quebra o contrato dos dois. Recomendação: **#493 é a fonte da verdade** das
regras jurídicas das áreas (cobertura maior, metadados versionados, teste de invariante);
do #495 aproveita-se apenas o que o #493 não cobre, se a conferência jurídica apontar algo.

### 4.6 Migration 122 — colisão direta

`122_data_room_token_hash` (#495) e `122_documentos_publicacao_hash` (#497) declaram o mesmo
número e o mesmo `down_revision` (`121_sala_juridica_chat`). Quem entrar depois quebra o head
único. Registrado em `backend/alembic/MIGRATION_RESERVATIONS.md`; resolvido pela recomendação
4.2 (o #495 deixa de trazer migration).

Nenhum teste do repositório detectava essa colisão antes do merge. A guarda genérica
`backend/tests/test_migration_numbering_guard.py`, adicionada neste PR, detecta — verificado
contra a combinação real dos dois branches:

```
FALHOU  test_nenhum_numero_de_migration_e_reutilizado
        → número de migration reutilizado: {122: ['122_data_room_token_hash.py',
                                                  '122_documentos_publicacao_hash.py']}
FALHOU  test_existe_um_unico_head
        → o repositório tem 2 heads (['122_data_room_token_hash', '127_audit_log_worm'])
```

### 4.7 `analise_bancaria.py` e `legal_docs.py` — conflitos menores

- `analise_bancaria.py` (#495 × #496): ambos endurecem a mesma rota; conflito textual
  pequeno, resolução manual trivial na consolidação.
- `legal_docs.py` (#494 × #497): o #494 adiciona o gate de protocolo (18 linhas) e o #497
  reescreve o mesmo router com revisão imutável, legal hold e selo (199 linhas). São
  correções **diferentes e ambas necessárias** — precisam ser combinadas à mão, com atenção
  para que o gate de protocolo do #494 sobreviva à reescrita do #497.

## 5. Recomendação por PR

| PR | Recomendação | Justificativa | Condição |
|---|---|---|---|
| **#494** | **Manter — integrar primeiro** | Área própria (fluxos/BPM/rotas), sem migration, conflito único e pequeno; evidência manual anexada | Rebase sobre a `main`; nada a absorver |
| **#493** | **Manter — integrar em segundo** | Única fonte completa das regras jurídicas das 57 ferramentas, com fonte, vigência, versão e teste de invariante | Ceder o **desenho** do gate de homologação ao formato do #495 (4.1) |
| **#496** | **Manter — integrar em terceiro** | Frente de IA praticamente disjunta (HITL, sanitização, RAG, citação); CI verde; já respeitava a decisão de 2FA | Rebase; ceder o gate global (vira kill-switch) e unir a correção do webhook (4.4) |
| **#497** | **Manter — integrar por último, com correções** | Maior volume de bloqueadores e dono da cadeia de migrations 122→127 | **Remover a frente de 2FA** (4.3); **corrigir o Data Room** para o desenho do #495 (4.2); preservar o gate de protocolo do #494 em `legal_docs.py` (4.7) |
| **#495** | **Absorver parcialmente e fechar** | Todo o conteúdo restante tem dono melhor: regras jurídicas → #493; Data Room → #497 (com o desenho do #495); webhook → #496; gate de homologação → #493 com o desenho do #495. A frente de 2FA **não vai para lugar nenhum** — é descartada (4.3) | Fechar **somente depois** de a absorção estar mesclada e com os testes do #495 migrados |

**Ordem de integração:** `#494 → #493 → #496 → #497` (com o #495 absorvido no caminho).
A cada merge, o próximo PR rebaseia sobre a `main` atualizada e o CI roda no head novo —
CI verde em `1befdf0` não vale como prova depois do primeiro merge.

## 6. Correções exclusivas (não duplicadas em nenhum outro PR)

- **#493** — matriz/selo de homologação por ferramenta; `extra="forbid"` nos PATCH das 6
  áreas; EIRELI recusada em registro novo; rota canônica `/areas-de-atuacao/:slug`;
  demonstrativo que descartava valores aninhados e fundamentação; suspensão de fim de ano
  nos prazos processuais; mínimo existencial do superendividamento (25%).
- **#494** — merge de query/hash nos `LEGACY_REDIRECTS`; `ModuleLifecycleGate`; preview de
  extração recuperável após F5; guardas de ordem e de etapa obrigatória no BPM; 409 para
  caso encerrado; gate de protocolo com comprovante em Peças; TTL de 48h no rascunho de
  intake.
- **#495** — remoção do `?token=` da query do webhook; hash do token do Data Room em
  repouso; prescrição decenal do indébito (EAREsp 738.991) com `base_legal`.
- **#496** — fim do bypass de HITL por `aprovacoes_hash`; retomada com validação de
  usuário/caso/papel e token one-shot via `GETDEL`; `AI_AGENT_ENABLED` default `False`;
  piso `LOCAL_COMPLETO` para áreas sensíveis; DataJud entra no RAG como `pendente`;
  `_existe_artigo` restrito ao diploma citado; migração do modelo Groq depreciado.
- **#497** — publicação explícita no Portal (fail-closed); SHA-256 na ingestão de
  documentos; `malware_scan`; histórico imutável de peças + legal hold; ownership e rehash
  em assinatura; token HMAC para download temporário; CHECK de valores financeiros; trigger
  WORM em `audit_logs`; `.env` 0600, `RUN_MIGRATIONS` default 0, gate de CI em PR com guarda
  anti-fork.

## 7. Decisões tomadas (2026-07-27)

| # | Assunto | Decisão | Quem decidiu |
|---|---|---|---|
| 1 | **2FA** (4.3) | **Não implementar.** Comportamento atual mantido; a frente sai do #495 e do #497; fail-open é risco aceito e registrado em `docs/GOVERNANCA_IA.md`, seção 11 | Titular |
| 2 | **Gate de homologação** (4.1) | Desenho do **#495** (fail-closed, campo obrigatório, endpoint de consulta) com o conteúdo do **#493**; a flag do #496 vira kill-switch de emergência, não gate primário | Técnica — critério: fail-closed vence, e ferramenta nova nasce bloqueada |
| 3 | **Data Room** (4.2) | Desenho do **#495** (hash em repouso, sem token em claro no banco), implementado na cadeia de migrations do #497 para não renumerar | Técnica — critério: o desenho do #497 não fecha o vetor de LGPD que motivou a correção |
| 4 | **Webhook WhatsApp** (4.4) | **União** das duas metades: remoção do `?token=` da query (#495) + supressão de telefone/conteúdo e sanitização anti-forja (#496) | Técnica — as duas correções são complementares, não concorrentes |
| 5 | **`ramos.py`** (4.5) | **#493 é a fonte da verdade** das regras jurídicas; do #495 só entra o que o #493 não cobrir | Técnica — cobertura maior, metadados versionados, teste de invariante |
| 6 | **Ordem de integração** | `#494 → #493 → #496 → #497`, com o #495 absorvido no caminho | Técnica — menor bloqueio primeiro, migrations por último |

As decisões técnicas seguem o critério da governança (fail-closed vence em segurança;
evidência vence opinião) e ficam sujeitas a veto do titular a qualquer momento.

## 7.2 Execução das decisões (2026-07-27)

| Decisão | Estado | Onde |
|---|---|---|
| 2FA fora do #497 | **Aplicado** | `claude/new-session-bhbv06`, commit `e8dc949` — `two_factor_policy.py`, o teste do kill-switch e o bloco do `.env.example` voltaram ao estado da `main` |
| Data Room com hash em repouso | **Aplicado no #497** | mesmo commit — a migration 124 apaga o `token` em claro depois de popular o `token_hash`; `gerar_link` não persiste mais o segredo; `DataRoom.tsx` do #495 foi junto (sem ele a tela quebrava lendo `lk.token`) |
| Webhook com as duas metades | **Aplicado no #496** | `claude/new-session-h6j254`, commit `0406358` — cai o fallback `?token=`, com teste de regressão novo (6 casos) |
| Limpeza do #495 | **Não executada — registrada no PR** | a branch recebeu commits de outra sessão durante a consolidação; editá-la seria a colisão que a seção 5 proíbe. O que precisa sair está descrito em comentário no [#495](https://github.com/s2corporativo/ejc/pull/495) |

Consequência: a **colisão do número 122 continua aberta** até o #495 abrir mão da sua
migration. O `test_migration_numbering_guard.py` (PR #499) falha se as duas entrarem.

## 7.1 Pendências que ainda exigem decisão humana

1. **Conferência jurídica** das regras do #493 antes do merge: nenhuma das 57 ferramentas
   foi homologada por advogado responsável; o teste de invariante garante que a regra está
   *versionada*, não que está *correta*. **É o único bloqueio jurídico real da fila.**
2. **Autorização de merge** de cada PR, na ordem definida — ato humano, um de cada vez,
   com CI verde no head já rebaseado.
3. **Congelamento de novas frentes** até o fim da consolidação: o #498 (Sala Jurídica) e o
   #492 (dossiê/simplificação) tocam áreas já sob revisão e devem esperar.
4. **Proteção de branch da `main`** (bloqueio de push direto, review obrigatório) —
   configuração administrativa do GitHub, fora do alcance de qualquer PR.

## 8. Como esta matriz se mantém viva

Ela é um retrato de 2026-07-27 sobre `1befdf0`. Depois do primeiro merge, os números de
conflito mudam. Antes de cada integração, refaça a verificação:

```bash
git fetch origin main <branch>
git merge-tree --write-tree --name-only origin/main origin/<branch>
```

e atualize a seção 3 no mesmo PR que fizer a integração.
