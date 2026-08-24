# Plano-Mestre EJC — Correção Total, Consolidação e Padronização

## Contexto

A simulação A0 (caso fictício, ambiente local) e as auditorias acumuladas provaram duas coisas ao mesmo tempo: **o núcleo determinístico do sistema funciona** (dossiê, linha do tempo, prazos reais vs estimativas) e **o sistema convive com 4 classes de inconsistência estrutural** que produzem os bugs visíveis um a um — a mesma tese com dois números, a jornada que marca "aprovado pelo advogado" sem advogado, contadores que mentem. Além disso: a cota do GitHub Actions está esgotada (nada roda, nem no runner self-hosted), 3 workflows estão `disabled_manually`, as migrations 127–147 estão mescladas mas **não estão em produção**, e o backlog da auditoria (33 itens, 8 CRÍTICOS) segue quase intocado.

Decisões do titular já tomadas para este plano:
1. **Incluir os cortes de módulo** do parecer arquitetural (34 → 10–12 módulos).
2. **Lançamento primeiro**: destravar o caminho do caso real antes da padronização pesada; padronização entra cirurgicamente onde o lançamento já força tocar.

Restrições de governança em vigor: WIP máximo 1 frente estrutural + 1 funcional (`docs/engineering/WIP_AND_RELEASE_POLICY.md`); todo PR vinculado a Issue `#NNN`; migration com reserva em `backend/alembic/MIGRATION_RESERVATIONS.md`; toda correção com teste de regressão; gate local `scripts/ci-local.sh` substitui o CI até a cota voltar; deploy só via `scripts/deploy_manual.sh` (PR #1259, após aprovação do titular); jamais enfraquecer HITL/citation gate/PII/kill-switch.

O status vivo de cada item deste plano é rastreado em **`docs/PLANO_MESTRE_STATUS.md`** (verificado por `scripts/status_check.sh`). Este documento descreve o desenho; não editar status aqui.

---

## Arquitetura do plano: duas trilhas paralelas

**Trilha E (executor)** nunca espera o titular, exceto no gate F4. **Trilha T (titular)** recebe uma pauta de decisões preparada com antecedência para gastar o mínimo de hora dele.

```
E:  F0 ──► F1 ──► F2 ──► F3 ──►(gate T4)──► F5 ──► F6
T:  T1 (PR#1259+deploy)  T2 (cota)  T3 (pauta de decisões)  T4 (Bloco 6+7+A0 real)  T5 (curadoria)
        └─destrava F0          └─destrava F6   └─destrava F2-A e F5    └─destrava F5
```

---

## TRILHA E — Fases do executor

### F0 — Esteira e Verdade Operacional (2–3 PRs, 1–2 sessões)

**Objetivo:** destravar código→produção sem Actions e criar a fonte única de status.

1. **Checklist-mestre** — `docs/PLANO_MESTRE_STATUS.md`: uma tabela, uma linha por item, status de enum fechado (`pendente / em-andamento / mesclado / em-prod / verificado`). Popular com: 33 itens do plano-correcao-v2, 7 blocos do plano-lancamento-v3, 4 classes A–D, cortes do Eixo 3, itens de infra. A distinção `mesclado` ≠ `em-prod` é obrigatória enquanto o deploy é manual (caso migration 147).
2. **Enforcement** — `scripts/status_check.sh` chamado por `ci-local.sh required`: valida IDs únicos, enum de status, PR preenchido para `mesclado+`. Sem o script, o checklist vira o 4º documento desatualizado.
3. **Banner nos docs legados** — 1 PR adiciona no topo de `plano-correcao-v2.md`, `plano-lancamento-v3.md` e `EVOLUCAO_ESTRATEGICA_EJC.md`: "status canônico em PLANO_MESTRE_STATUS.md" + corrige uma última vez a divergência interna ✅/🟡 das frentes 2, 11, 12. Nunca mais editar status neles. Regra de 1 linha no `DEFINITION_OF_DONE.md`: o PR que fecha um item flipa a linha no mesmo PR.
4. **Pauta de decisões do titular** (documento único, alimenta T3): canônico da Classe A, destino do `CaseLifecycleStatus` (11 valores), lista final de cortes, política da métrica "chance de êxito" (OAB art. 34).
5. **Ensaio do deploy manual** — `--dry-run` do `scripts/deploy_manual.sh`, backup verificado, downgrade testado das migrations mais recentes em staging local. O deploy real depende de T1.

**Gate de saída:** ci-local verde; checklist-mestre completo e validado pelo script; deploy manual executado (migrations 127–147 em produção) com smoke pós-deploy documentado.

### F1 — O Sistema Não Mente (6–8 PRs, 4–6 sessões)

**Objetivo:** eliminar toda saída falsa visível + destravar o pipeline da peça. É o "lançamento primeiro". Duas frentes simultâneas (respeita WIP 1+1):

**Frente funcional — captura DJEN (item 0.2, CRÍTICO):**
- Diagnosticar por que nunca capturou nada (fonte, credencial, OAB monitorada única). Depende parcialmente de T4 (cadastrar OABs dos 3 advogados) — preparar o código e a tela; a ativação final é do titular.
- Monitoramento passa a aferir **resultado** (capturou ≥ N publicações), não execução — usar o padrão já criado em `diario_oficial_service.py` (`execucoes_sem_resultado` + alerta ≥7).

**Frente estrutural — verdade dos números (itens 1.1–1.3 + bugs ativos das classes B/C/D):**
- `backend/app/routers/dossie_cliente.py:140` — `casos_ativos` conta `("ativo","triagem")`, valores que não existem pós-migration 126 → sempre 0. Corrigir usando `STATUS_ABERTOS` de `backend/app/core/status_caso.py` + teste de regressão. **Primeiro PR da fase.**
- Item 1.1 — dashboard "0 peças aguardando revisão" com 100% em rascunho: corrigir a query do contador; teste SQL-vs-API.
- Item 1.3 — filtro de status na listagem de casos (`frontend/src/pages/Casos.tsx` hoje não tem filtro nenhum): construir sobre `frontend/src/types/caseStatus.ts` (fonte canônica que já existe e só 4 arquivos importam). Corrige de passagem `status=ativo` vazio / `status=all` 500.
- Item 2.1 (CRÍTICO) + Classe D parcial — pipeline da peça: `validar` não grava `validacao_juridica.ai_log_id` → `/aprovar` e PDF bloqueados; **nenhuma peça foi protocolada na história do sistema**. Corrigir na mesma frente que a aprovação de honorários da Classe D (`fee_proposal_service.py:477` cria proposta já `status="aprovada"` — passa a nascer pendente com ato humano de aprovação), porque ambos mexem no mesmo travamento do orquestrador. Tocar `legal_case_orchestrator.py` **uma vez só nesta janela**.
- Item 1.4 — mensagem falsa "A equipe foi notificada".

**Gate de saída:** script de conferência (SQL direto vs API vs tela) passa para contadores de caso, peças e dossiê do cliente; teste E2E atravessa redação→validação (ai_log_id gravado)→aprovação→PDF; DJEN pronto para ativação (ou capturando, se T4 adiantar).

### F2 — Fundações Canônicas (9–12 PRs, 6–9 sessões)

**Objetivo:** 1 representação canônica por conceito. Ordem C → B → D → A (do mais barato ao mais arriscado). Cada classe fecha com: (a) fonte canônica documentada, (b) teste de paridade no ci-local, (c) grep-test que impede writer fora do caminho único.

**Classe C — saúde do caso (2 PRs, a mais barata):**
- `backend/app/services/case_health.py` devolve `classificacao` (limiar por score) e `saudavel` (= zero fatores) que discordam por construção; `saudavel` é lido efetivamente em **0** lugares do frontend. Deprecar e remover `saudavel` do contrato em 2 passos (campo de resposta, sem migration). `dossie_modulos.py:99` para de recalcular.
- Unificar limiares em módulo único (`backend/app/core/health_thresholds.py`) consumido por `case_health.py` **e** `visual_law_core.py::derivar_probabilidade` (hoje um 3º conjunto de limiares). Teste de paridade: mesma entrada → mesma classificação nas duas vias.

**Classe B — status de caso (2–3 PRs, restante):**
- Expurgar as 7 chaves fantasma (`novo`, `triagem`, `suspenso`…) do `STATUS_REGISTRY` em `frontend/src/components/UI.tsx` e o `LEGACY_STATUS_TONE`; migrar consumidores para `types/caseStatus.ts`.
- Guard-rail novo no padrão do `test_status_caso_paridade_frontend.py` existente: grep-test que reprova literal de status de caso fora da fonte canônica.
- Desarquivamento preserva estado anterior (hoje `TabResumo.tsx:234` força `"aberto"`): coluna `status_anterior` via migration **reservada**, ou derivação da trilha de auditoria se existir.
- `CaseLifecycleStatus` (11 valores em `domain_contracts.py`, não persistidos): **não implementar** — decisão T3 ou remover a declaração com nota. Armadilha de escopo conhecida.

**Classe D — jornada do orquestrador (2 PRs, restante — a parte de honorários já saiu na F1):**
- Princípio: **etapa concluída = evento verificável, nunca efeito colateral da criação**. Hoje 7 de 16 etapas nascem concluídas no segundo zero.
- "Documentos lidos" exige ≥1 documento processado (não apenas `descricao_fatos`).
- Ponte `case_checklists` → etapa `checklist_criado` (hoje são conceitos paralelos que não se enxergam).
- Golden test novo: fixa as 16 etapas por nome e ordem + cenário caso-recém-criado com lista explícita e justificada das etapas que podem nascer concluídas (meta: 2–3, não 7). Os testes atuais (`test_orquestrador.py`) não cobrem nada disso.

**Classe A — tese (3–4 PRs, a mais arriscada; exige decisão T3 antes do 1º PR):**
- Hipótese default (titular confirma em T3): `tese_caso_links` vira a única verdade do vínculo caso↔tese; `thesis_candidates` rebaixada a estágio de trabalho HITL que, **ao ser aprovada, materializa um link na mesma transação** — a ponte hoje ausente e o 1º exemplar do padrão "agregado transacional do Caso" do parecer.
- Ordem segura, nunca inverter: (1) service com write-path único (`aprovar_tese`/`tese_aprovada_do_caso`); (2) migration de backfill **reservada** (candidates aprovados sem link), idempotente com downgrade; (3) unificar leitores — `conversao_caso.py:175` e `legal_case_orchestrator.py:211` emitem hoje a MESMA chave `tese_aprovada` com fontes disjuntas; teste de paridade: as duas rotas respondem idêntico para o mesmo caso; (4) `cases.tese_principal` congelado como campo exibicional (não migrar os ~15 leitores agora); (5) remoção de `teses_juridicas_v4` e `teses_vitoriosas` fica para F5.

**Gate de saída:** 4 testes de paridade + grep-tests verdes no ci-local; `docs/ARQUITETURA_ATUAL.md` (ou seção no CLAUDE.md) nomeia o canônico de cada conceito.

### F3 — IA Confiável e Risco Regulatório (7–9 PRs, 5–7 sessões)

- **Item 2.2 (CRÍTICO)** — 0 de 47.359 chunks com embedding: tratar como **investigação antes de estimativa** (pipeline pode estar quebrado, não só desligado; há histórico em `RUNBOOK_MIGRACAO_EMBEDDING_1024.md`). Backfill vira script+runbook com execução longa fora do PR.
- **Item 2.3 (CRÍTICO)** — modelo local para dados pessoais: teste que prova que nenhum texto com PII sai para API externa (reforça `ai_gateway.py`, nunca o contorna).
- **Item 3.1 (CRÍTICO)** — generalizar "monitorar resultado, não execução" para todos os jobs, no padrão já aplicado ao DOU; alerta dispara em cenário sintético.
- **Item 4.2 (CRÍTICO)** + resto da Classe C — métrica "chance de êxito" (risco OAB art. 34, XXIX): reformular ou remover conforme decisão T3, no mesmo PR-frente da unificação de limiares se ainda aberta. Exceção imediata já prevista no plano v3: **confirmar que nenhum `/portal/*` serializa a métrica**.
- **Item 4.1 (CRÍTICO)** — remover conta `homolog.qa` superadmin de produção + impedir `qa/e2e/run_fictitious_smoke.py` de rodar contra produção.
- **Item 5.1** — expor as 15 calculadoras jurídicas (maior ganho rápido do backlog), se couber na fase.

**Gate de saída:** % de chunks com embedding ≥ meta definida; teste PII verde; alertas de resultado ativos; métrica de êxito resolvida com parecer registrado; homolog.qa eliminada.

### F4 — Pré-Operação e Primeiro Caso Real (gate do titular — capacidade reservada, 2–4 PRs de hotfix)

Corre no calendário do titular (T4): Bloco 6 (10 cadastros, com o executor preparando seeds e telas), Bloco 7 (caso real ponta a ponta) e **A0 com caso real** — a simulação local desta sessão respondeu a metade mecânica; a metade de valor ("quantos minutos economizei?", "abriria de novo?") só o caso real responde. O executor fica de prontidão para hotfixes.

**Gate (o mais importante do plano):** um advogado leva um caso real do início ao protocolo e considera **mais fácil que fora do sistema**. Este gate libera F5. Se o resultado invalidar prioridades, o custo afundado é mínimo por desenho — F5 (a fase mais volumosa e opinativa) está inteira atrás dele.

### F5 — Corte e Consolidação (12–17 PRs, 8–12 sessões — estimativa menos confiável, pode dobrar)

Pré-condições duras: gate F4 passado + lista de cortes assinada em T3.

- **Cortes** (1 PR por módulo, reversível via git): jurimetria/predição de êxito ("jurimetria com 8 casos é anedota"), `diplomacia-v3` (remover código — risco disciplinar), Victory Vault (+ `teses_vitoriosas`/`teses_juridicas_v4` da Classe A passo 5), radar de notícias/ConJur, módulo sociedade, skills de IA sem uso registrado em log. Critério por corte: "nenhuma tela viva referencia" verificado por grep + teste de rotas.
- **Rotas mortas**: das 453 rotas, 211 nunca são chamadas por tela — remoção em 2–3 PRs guiada por `test_rotas_registro_explicito.py`.
- **Higiene frontend** (`docs/consolidacao/MAPA_VERDADE_V1.md`): desmontar `UI.tsx` (1437 linhas) em `components/ui/*` (4–6 PRs — é o hotspot que bloqueia qualquer frente paralela, por isso só agora); consolidar os 8 CSS globais; eliminar dashboards duplicados.
- **Fronteira de agregado do Caso** (parecer §4.1): caso+peças+documentos+prazos+logs mudam juntos numa transação — fecha a classe recorrente "grava em 2 tabelas sem garantir as 2" (itens 3.3–3.6: exclusão sem cascata, conversão que perde fatos, vínculos ausentes).

**Gate de saída:** contagem rotas/routers/páginas antes-depois registrada; `ci-local full` verde; 34 → 10–12 módulos confirmado no moduleRegistry.

### F6 — Normalização de Infra (1–2 PRs, 1 sessão)

Após T2 (cota regularizada + 3 workflows reativados pelo titular): verificar paridade `ci-local` × workflows; 1 PR atravessa a esteira automática ponta a ponta; deploy manual rebaixado a contingência documentada; `auto-integracao.yml` volta a mesclar sozinho com gates verdes.

---

## TRILHA T — O que só o titular faz (pauta pronta em F0)

| # | Ação | Destrava | Custo estimado |
|---|---|---|---|
| T1 | Revisar/mesclar PR #1259 + autorizar 1º deploy manual | Gate F0 (migrations 127–147 em produção) | 30–60 min |
| T2 | Regularizar cota Actions + reativar `auto-integracao`, `continuity-ui-gates`, `architecture-inventory` | F6 | 15 min + faturamento |
| T3 | Sessão única de decisões: canônico da tese, destino do CaseLifecycleStatus, lista final de cortes, política da métrica de êxito | F2-Classe A e F5 | 1–2 h |
| T4 | Bloco 6 (10 cadastros: OABs DJEN, tabela OAB/MG, sócios, purga de teste…) → Bloco 7 → A0 real | F5 e o critério de lançamento | horas dele, calendário próprio |
| T5 | Onda C de curadoria (EJC Gold, Playbooks, Banco de Erros, massa do grafo) | frentes 3/6/7/9 da evolução estratégica | contínuo, ritmo próprio |

Se T4 atrasar, o executor não para: F3 e a **preparação** de F5 (inventário de corte, sem executar) continuam.

---

## Verificação (transversal, todo PR)

1. `scripts/ci-local.sh required` verde antes de todo push (inclui o novo `status_check.sh` a partir da F0).
2. Toda correção nasce com teste de regressão que falha no código anterior (provar via stash quando possível).
3. Item só vira `verificado` no checklist-mestre após conferência **em produção** pós-deploy (DoD: nada é pronto porque o código foi escrito).
4. Frentes que tocam auth/permissões/uploads/config acionam `security-auditor` antes de finalizar.
5. Migrations: `python -m alembic heads` + reserva antes de criar; autogenerate revisado à mão (30 tabelas raw-SQL); backfills idempotentes com downgrade.
6. Arquivos disputados (`legal_case_orchestrator.py`, `UI.tsx`, `dossie_cliente.py`) — frentes estritamente seriais, nunca 2 PRs abertos tocando o mesmo.

## Riscos declarados

1. **Deploy em lote de 21 migrations sem esteira** é o momento de maior risco de todo o plano — mitigado por backup verificado + ensaio + downgrade testado antes de T1.
2. **O canônico da Classe A é hipótese, não fato** — decisão de produto; por isso trava em T3.
3. **A0 real pode reordenar tudo** — previsto: F5 está atrás do gate justamente para isso.
4. **F5 pode dobrar de tamanho** (cauda longa de imports cruzados em 163 routers manuais) — é última e fatiável por desenho.
5. **2.2 (embeddings) pode ser pipeline quebrado, não desligado** — entra como investigação, não como estimativa.
6. **Checklist-mestre sem o script de enforcement vira o 4º documento desatualizado** — o script é a parte não negociável.

**Ordem de grandeza total: ~40–55 PRs.** Com WIP 1+1, o limite é calendário, não capacidade — os gargalos seriais são F2 e F5.

## Primeiro passo imediato ao aprovar

F0 inteira é executável agora, sem depender de ninguém: checklist-mestre + `status_check.sh` + banners nos docs legados + pauta de decisões do titular + ensaio `--dry-run` do deploy. Em paralelo, abrir as Issues das frentes da F1.
