# Plano de consolidação e correção para colocar o EJC em operação

**Data do levantamento:** 2026-08-06 · **Base:** `main` em `8b11007` (CI verde)
**Natureza deste documento:** plano de execução. Nenhuma correção foi aplicada aqui — este
documento registra o estado verificado, os nós que travam a operação e a ordem recomendada
de resolução. Complementa (não substitui) o `docs/auditoria/plano-lancamento-v3.md`, que
segue sendo o plano de produto; este cobre a **consolidação de PRs/migrations e a
prontidão operacional** que precisam acontecer antes ou em paralelo aos blocos do v3.

---

## 1. Estado verificado em 2026-08-06

Tudo abaixo foi conferido na data, direto no GitHub e no repositório — não é reprodução de
documento antigo.

### 1.1 A `main` está saudável, mas o deploy está quebrado

- **CI da `main`: verde.** No head `8b11007`, passam CI, EJC Release Gate, Continuity and
  UI Gates e Main Provenance Audit.
- **Deploy VPS: falhando por infraestrutura, não por código.** O run mais recente morreu no
  passo "Confirmar SHA e runtime de produção" com
  `fatal: detected dubious ownership in repository at '/opt/actions-runner/_work/ejc/ejc'`.
  É configuração de git no runner self-hosted (`safe.directory`) — correção de um comando,
  no VPS, por operador humano. **Efeito prático: a produção está um commit atrás da `main`**
  (rodando `1d877c8`, sem o fix de validação caso-cliente do #736).
- **Reconciliação já começou pelo método certo.** Os merges recentes #733 (Governança v2.1),
  #735 (timeline canônica) e #736 (validação caso-cliente) seguem o padrão "reintegrar o
  conteúdo sobre a `main` atual" em vez de rebasear PRs gigantes defasados. Este plano adota
  o mesmo método.

### 1.2 Migrations: head real e lacunas de numeração

- **Head real da `main`: `131_audit_logs_worm`** (cadeia ...126 → 127 → 130 → 131).
- **Os números 128 e 129 foram pulados** (reservados pelo PR #679 a partir de um head que
  não existe mais). A lacuna em si não quebra nada — a guarda de numeração exige
  monotonicidade, não continuidade — mas precisa ficar documentada como "queimada".
- **`MIGRATION_RESERVATIONS.md` está desatualizado:** registra `130_ejc_skills_uso` como
  "Reservada (a abrir)" e `131_audit_logs_worm` como "Em PR", mas **ambas já estão mescladas
  na `main`**.
- Divergência viva entre PRs (detalhe na §2.1): o #652 traz `132_case_parte_pii_encriptado`
  e o #679 traz `131_audit_logs_worm` (que **colide com a `main`**) mais `133`–`135`
  encadeadas numa cadeia que não existe.

### 1.3 Os 8 PRs substantivos abertos

| PR | Escopo | Estado | CI | Migrations | Risco de integração |
|---|---|---|---|---|---|
| #714 | Certificação H01–H15 (gate + runbook) | draft, `behind` | verde | — | **Nenhum** — zero sobreposição com qualquer outro PR |
| #642 | Gate de vigência normativa no RAG (#636) | draft, `behind` | verde | — | Baixo — 3 arquivos de config em comum com #679 |
| #703 | Guardrail decadência/prescrição (#554 itens 1–2) | pronto, `behind` | verde | — | Baixo — só `routers/ai.py` em comum com #652/#679 |
| #705 | Demonstrativo exige ferramenta + proveniência (#702) | pronto, `behind` | verde | — | Baixo — `peca_geracao.py` em comum com #706 (esperado) |
| #706 | RBAC allowlist EQUIPE_JURIDICA em 15 arquivos (#694) | pronto, `behind` | verde | — | Baixo — mas toca `core/security.py`; **exige security-auditor antes do merge** |
| #652 | Auditoria integral + 4 P0, 6 P1 (roteamento /v1, kill-switch, RBAC, LGPD/PII, PIX) | draft, **`dirty` (conflito)** | **2 checks vermelhos** | `132_case_parte_pii_encriptado` (com `DROP COLUMN` pós-backfill) | **Alto** — 61 arquivos, conflito com a base, backend + governança falhando |
| #679 | 15 correções de segurança/LGPD/integridade | draft, `behind` | **2 checks vermelhos** | `131` (colide com a `main`!), `133`, `134`, `135` | **Alto** — 137 arquivos, **42 em comum com o #652** (foi rebaseado assumindo o #652 mesclado, o que não ocorreu); backend + continuidade falhando; security-auditor não executado |
| #676 | Higienização geral (−23,6k linhas) | draft, **`dirty` (conflito)** | verde (no head antigo) | edita 4 migrations antigas (só imports mortos) | Médio — maior superfície (163 arquivos), conflita de leve com #679/#652/#705/#642 |

Além desses, há **15 PRs de dependência (dependabot + vite)** abertos — tratados na §3.6.

### 1.4 As issues referenciadas (estado real)

Das 19 issues levantadas, **18 estão abertas**; apenas a **#699 (WORM de audit_logs) está
fechada e entregue** (migration 131 na `main`). Classificação por natureza do desbloqueio:

- **Resolvem-se por merge dos PRs abertos:** #636 (→#642), #554 itens 1–2 (→#703),
  #702 (→#705), #694 (→#706), #715 (→#714), #651 (→#652) e o pacote do #679
  (#678, #573, #552, #559, #581, #580, #578).
- **Exigem trabalho técnico novo (nenhum PR aberto cobre):** #717 (prazos auditáveis +
  integridade documental — a Onda 3 inteira), #718 (governança RAG/IA — Onda 4),
  #701 (ligar o gate de gold sets), #584 (Sentry ausente vira alerta), #727 (build args de
  branding no Docker), #454 (remover NOPASSWD:ALL do runner).
- **Exigem ação administrativa/operacional do titular (não são código):** #250 (branch
  protection da `main`), #452 (runner offline/instável — inclui o `dubious ownership` do
  deploy), #587 (limpeza de resíduos fictícios em produção), #591 (redigir manuais).
- **Exigem dados/decisão do escritório antes de qualquer código:** #568 (sócios e
  participações), #569 (tabela OAB/MG oficial), #588 (curadoria de templates/prompts),
  #589 (decisão InfoSimples/NFS-e), #582 (política de retenção LGPD/legal hold).

---

## 2. Os quatro nós que travam a consolidação

### 2.1 Nó crítico: o par #652 × #679

É o problema número um e condiciona todo o resto:

- **42 arquivos em comum.** O #679 foi construído por cima do #652 como se ele já estivesse
  mesclado — 18 routers, `ai_gateway.py`, testes e a própria tabela de reservas aparecem nos
  dois diffs.
- **Cadeia de migrations incompatível.** O #679 carrega `131_audit_logs_worm` — que a `main`
  **já tem** por outro caminho (PR da issue #699) — e encadeia `133`–`135` numa sequência que
  pressupõe um `132` do #652 que ainda não existe na `main`. Integrar qualquer um dos dois
  sem reconstruir essa cadeia quebra o head único.
- **Ambos com CI vermelho** (backend/schema-RAG nos dois; governança no #652; continuidade
  no #679) e o #652 em conflito com a base.

**Consequência:** nenhum dos dois é mesclável hoje, e rebase mecânico não resolve — é
preciso desmontar e reintegrar (ver §3.3–§3.4).

### 2.2 Deploy e runner (o caminho até produção está interrompido)

Três problemas empilhados na mesma máquina: o `dubious ownership` que derrubou o último
deploy (correção trivial, mas manual), o histórico de runner offline (#452) e o
`NOPASSWD:ALL` que dá root a qualquer workflow (#454). Enquanto isso não for tratado,
**nenhum merge chega à produção de forma confiável** — e o próprio CI dos PRs depende desse
runner para os jobs self-hosted.

### 2.3 Bloqueios que só o titular resolve

Branch protection da `main` (#250) é ação de settings do GitHub; sócios (#568), tabela
OAB/MG (#569), curadoria de conteúdo (#588), InfoSimples/NFS-e (#589) e política LGPD
(#582) dependem de dados e decisões do escritório. Nenhuma sessão de código destrava isso —
o plano os isola numa trilha própria (§3.7) para que não mascarem o progresso técnico.

### 2.4 O que falta e ainda não tem PR: prazos auditáveis (#717)

A Onda 3 inteira — prova reproduzível do cálculo do prazo, origem da intimação, data da
ciência, calendário/feriados, regra aplicada, histórico de recálculo, dupla conferência com
conferente ≠ calculista, invalidação da conferência ao alterar o prazo, documento original
imutável, SHA-256, páginas usadas pela IA — **não está coberta por nenhum PR aberto**. É a
maior frente de trabalho novo do plano, e é o que define a regra operacional do piloto:
**até a #717 ser homologada, o EJC não pode ser a única agenda de prazos do escritório.**

---

## 3. Etapa 1 — Estabilização (congelar, consolidar, proteger)

**Pré-condição de método:** congelar funcionalidade nova. Só entram correção, consolidação
e os itens deste plano. Cada onda abaixo é uma frente sequencial; dentro da onda, os merges
são atos do titular (o executor prepara, o titular mescla).

### 3.1 Onda 0 — desobstruir o pipeline (1 ação manual + 1 PR pequeno)

1. **[Titular/operador, no VPS]** Corrigir o runner:
   `git config --global --add safe.directory /opt/actions-runner/_work/ejc/ejc` (no usuário
   que executa o job) e re-disparar o Deploy VPS para levar a produção ao head da `main`.
   Aproveitar a janela para o checklist de saúde da #452.
2. **[PR pequeno]** Atualizar `backend/alembic/MIGRATION_RESERVATIONS.md`: marcar 130 e 131
   como **Mescladas**, registrar 128/129 como **queimadas** (lacuna documentada), e reservar
   formalmente **132 → #652 (case_parte_pii)** e **133–135 → conteúdo do #679**. Isso trava
   a numeração antes de qualquer reintegração e evita terceira renumeração às cegas.

### 3.2 Onda 1 — mesclar os cinco PRs verdes (menor risco primeiro)

Ordem recomendada, com atualização de branch (`update branch`/rebase) + re-run de CI antes
de cada merge, um por vez:

1. **#714** (certificação H01–H15) — zero sobreposição com tudo; entrega o harness que a
   Etapa 3 vai usar. Promover de draft e mesclar primeiro.
2. **#706** (RBAC allowlist) — fecha vazamento ativo (`financeiro` gerando peça por IA).
   **Antes do merge: rodar o `security-auditor`** (o PR declara que não foi rodado, e toca
   `core/security.py` — regra crítica nº 3 do repositório).
3. **#705** (demonstrativo com proveniência) — rebase por cima do #706 (compartilham
   `peca_geracao.py`, conflito esperado e pequeno).
4. **#703** (guardrail decadência/prescrição) — juridicamente urgente (peça com CPC 487, II
   errado é risco real); sem migration, CI verde.
5. **#642** (gate de vigência do RAG) — CI verde. Atenção ao efeito colateral conhecido:
   legislação legada sem vigência verificada **some da recuperação** até a reingestão
   (§5.1) — comportamento fail-closed correto, mas precisa estar combinado com o titular.

Resultado da onda: 5 dos 8 PRs fora da fila, issues #715, #694, #702, #554 (parcial) e
#636 fechadas, sem tocar no nó crítico.

### 3.3 Onda 2 — reintegrar o #652 (fatiado, não rebaseado)

O #652 está em conflito, com 2 checks vermelhos, 61 arquivos e uma migration destrutiva
(`DROP COLUMN` pós-backfill). Rebase único é a opção frágil — depois da Onda 1 a base terá
mudado ainda mais. **Recomendação: fatiar, no padrão que já funcionou (#733/#735/#736):**

- **652-A — roteamento:** correção do prefixo `/v1` duplicado nos 8 routers + verificador
  de contrato de API. Sem migration, alto valor, baixo conflito.
- **652-B — hardening de IA:** kill-switch efetivo no `ai_gateway`, rate limit nas rotas de
  IA, RBAC de prompts/cofre (conferir o que o #706 já cobriu para não duplicar).
- **652-C — PII/LGPD:** migration `132_case_parte_pii_encriptado` + anonimização art. 17.
  **Único bloco com migration destrutiva**: exige backup comprovado antes do deploy que a
  aplicar, plano de rollback no corpo do PR e execução do backfill validada em staging
  primeiro (§4).
- **652-D — PIX e honorários:** correções de BR Code e cálculo.
- **Documentação da auditoria** (17 docs): pode vir junto de 652-A ou em PR próprio de docs.

Cada fatia nasce da `main` atual, com CI verde exigido, e o PR #652 original é fechado
quando a última fatia mesclar (com o registro do que foi descartado por já existir na main).

### 3.4 Onda 3 — reconstruir o #679 (reduzido ao que resta)

Depois das fatias do #652, o #679 encolhe muito: os 42 arquivos compartilhados saem, a
migration `131` (duplicada da main) morre, e as `133`–`135` são renumeradas a partir do head
então vigente. Reconstrução em 2–3 PRs temáticos a partir da `main`:

- **679-A — auth/sessão:** invalidação de access token pós-troca de senha
  (`password_changed_at` + migration renumerada), UUID malformado.
- **679-B — uploads e sanitização:** teto de upload pré-leitura nos ~9 routers, gate PII
  cartão/PIX, sanitizador de logs, SSRF/DNS-rebinding no import por URL, robots.txt.
- **679-C — integridade de dados:** conversão Sala→Caso sem perder fatos, `status=all` 500,
  índice de risco, AILog em cache_hit, retry 429/529 do gateway, backup offsite.

**Obrigatório: `security-auditor` em cada um** (todos tocam auth/uploads/config — e o #679
original declarou explicitamente que não passou por auditoria de segurança). O check de
"Continuidade" que falha no #679 atual precisa ser diagnosticado na reconstrução (`ci-triage`).

### 3.5 Onda 4 — #676 (higienização) por último

É o PR com a maior superfície (163 arquivos, −23,6k linhas) e o menor risco funcional. Vai
por último exatamente para não gerar conflito cosmético com as ondas anteriores. Requer:
rebase sobre a main pós-ondas, re-execução da unificação do helper de erro nos arquivos que
mudaram, e atenção aos 4 arquivos de migrations antigas editadas (decisão já assumida pelo
titular, manter o registro no PR).

### 3.6 Dependabot (15 PRs) — depois da estabilização, em lote

Nenhum deles bloqueia a operação. Manter congelados durante as ondas (evita ruído no CI) e
depois processar em 2 lotes: **backend** (atenção a `uvicorn` 0.29→0.52 e `langfuse` 2→4,
que são saltos de major/minor com risco de quebra; `pgvector` 0.3→0.5 idem) e **frontend**
(minors de baixo risco; `jsdom` 24→30 só afeta testes). Lote = branch única, CI completo,
smoke manual. A CVE relevante de `cryptography` já foi corrigida direto na `main`.

### 3.7 Trilha do titular (paralela, sem dependência de código)

Pode andar em paralelo a todas as ondas — nada aqui espera merge:

| Item | Ação | Referência |
|---|---|---|
| Branch protection da `main` | Configurar no GitHub: require PR + aprovação + checks nomeados + bloquear force push/bypass admin | #250 (P0) |
| Runner: recuperar e separar | `safe.directory` já na Onda 0; depois separar runner de CI (sem sudo) do de deploy e remover `NOPASSWD:ALL` | #452, #454 |
| Sócios e participações | Fornecer relação jurídica oficial (percentuais, vigência) | #568 |
| Tabela OAB/MG | Localizar publicação oficial (URL, ato, vigência) — sem fonte oficial, módulo permanece desativado | #569 |
| Curadoria de conteúdo | Escolher 3–5 fluxos prioritários e aprovar templates/checklists/prompts | #588 |
| InfoSimples/NFS-e | Decidir: contratar+homologar ou marcar indisponível | #589 |
| Política LGPD | Aprovar matriz de retenção/legal hold (pré-requisito de purga e da limpeza definitiva) | #582 → #587 |
| Gold sets | Definir com o executor as áreas críticas e validar casos pseudonimizados | #701 |

**Critério de saída da Etapa 1:** fila de PRs substantivos zerada, head de migrations único
e documentado, CI verde na `main`, produção no head certificado, branch `main` protegida.

---

## 4. Etapa 2 — Infraestrutura (staging, backup, monitoramento)

1. **Staging separado da produção.** Hoje o smoke E2E (`qa/e2e/run_fictitious_smoke.py`)
   roda **contra produção** — é a origem dos casos `HOMOLOG-FICTICIO-*` e da conta
   `homolog.qa` superadmin ativa em produção (armadilha confirmada da auditoria). Publicar
   staging (compose próprio ou VPS separado), validar DNS/HTTPS/health e **redirecionar o
   smoke para lá**; desativar `homolog.qa` de produção junto com a limpeza da #587.
2. **Backup/restore/rollback provados.** Usar o certificador do #714 (mesclado na Onda 1)
   como harness: restore em banco vazio, rollback de release, RPO/RTO piloto 24h/4h.
   Registrar evidência — o gate H01–H15 exige prova, não declaração.
3. **Monitoramento de resultado, não de execução.** Contratar/configurar Sentry (ou
   equivalente) + PR da #584 (ausência de coletor = alerta, não "ok"). Alertas de
   indisponibilidade externos (UptimeRobot ou similar) para `https://ejc.depaulateixeira.adv.br`.
   Regra da auditoria: heartbeat que não afere resultado (caso DJEN) não conta.
4. **Aplicar a migration 132 (PII)** em staging primeiro, com backfill validado e backup
   comprovado antes de produção — é a única migration destrutiva da fila.
5. **Rotação de segredos + manuais operacionais** (incidente, backup, atualização) — os
   runbooks existentes (`RUNBOOK_*.md`) cobrem parte; completar o que a #591 apontar como
   crítico.

---

## 5. Etapa 3 — Homologação (H01–H15) e as duas frentes técnicas restantes

A certificação H01–H15 (harness do #714) é o gate. Duas frentes técnicas precisam estar
prontas para ela passar de verdade:

### 5.1 IA/RAG confiável (fecha #636 na prática, encaminha #701 e #718)

- Com o #642 mesclado: **reingerir** os 1.375 documentos sem `legal_status` e **reindexar**
  os 47.359 trechos antes de reabilitar `EMBEDDINGS_ENABLED` — sem isso o gate de vigência
  fail-closed deixa a base de legislação praticamente vazia na recuperação.
- Gold sets (#701): curadoria por área com o titular, depois ligar `--min-recall-area` no
  CI. Métricas: citação, completude, vigência, alucinação — o maquinário já existe.
- Onda 4 (#718 — bases segregadas oficial/escritório/caso, autorização pré-busca vetorial,
  ciclo editorial, classificação de risco por ação): implementar **incremental, por flags,
  depois do piloto começar** — não é bloqueador do piloto limitado, porque o HITL
  obrigatório + citation gate + kill-switch (652-B) já garantem o modo "minuta sujeita à
  revisão humana". **Bloqueador do piloto é apenas: HITL ativo, vigência ativa (#642),
  guardrails (#703) e nenhum ato externo automático** (protocolo/comunicação — já é o
  desenho do sistema; verificar na homologação H10/H11).

### 5.2 Prazos e documentos auditáveis (#717 — trabalho novo, 3 PRs)

Frente de maior esforço técnico restante. Fatiar em três, com migrations reservadas na hora:

- **717-A — prova do cálculo:** persistir evento de origem (intimação), data da ciência,
  calendário/feriados usados, regra jurídica aplicada (com fonte oficial e vigência — regra
  obrigatória nº 5 do repositório), versão da regra e histórico de recálculo. Toda regra
  jurídica com teste.
- **717-B — dupla conferência:** conferência por segundo usuário obrigatória em prazo
  crítico, conferente ≠ calculista imposto no backend, e **invalidação automática da
  conferência quando qualquer insumo do prazo mudar**.
- **717-C — integridade documental:** SHA-256 na ingestão, original imutável (separado de
  OCR/derivados), identificação das páginas usadas pela IA, backfill dos documentos
  existentes.

**Regra operacional não negociável até a #717 estar homologada: o EJC não é a agenda única
de prazos — o controle paralelo do escritório continua.** Esta regra entra escrita na ata de
homologação e só sai com a certificação da 717-B.

### 5.3 Roteiro da homologação

Executar H01–H15 com todos os papéis (superadmin → cliente_externo), Portal com cliente
fictício **em staging**, validação de prazos/documentos/IA/financeiro, e emitir a ata com as
3 aprovações que o certificador exige (técnica, jurídica/LGPD, titular).

---

## 6. Etapa 4 — Piloto controlado

Só após ata de homologação:

- Apenas os 3 sócios; número reduzido de casos reais (sugestão: 3–5).
- **Conferência paralela de prazos** (regra da §5.2) — dupla no EJC + agenda antiga.
- IA em modo minuta: revisão integral de toda peça; nenhum protocolo automático; nenhuma
  comunicação externa automática (InfoSimples/NFS-e/WhatsApp permanecem OFF salvo decisão
  da #589 com homologação própria).
- Acompanhamento diário: erros (Sentry), backups (verificação de resultado, não de
  execução), e revisão semanal dos achados.
- **Critério de saída para produção plena:** período estável sem P0 **e** o critério da
  auditoria — um advogado leva um caso real do início ao protocolo e considera que foi mais
  fácil do que fazer fora do sistema.

---

## 7. Riscos e pontos de decisão do titular

| # | Decisão | Recomendação | Consequência de adiar |
|---|---|---|---|
| 1 | Fatiar #652 e #679 vs. rebase único | **Fatiar** (padrão #733–#736 já validado) | Rebase único de 61+137 arquivos sobre base móvel tende a reintroduzir conflito a cada merge da fila |
| 2 | Ordem da Onda 1 | #714 → #706 → #705 → #703 → #642 | Inverter aumenta o nº de rebases intermediários |
| 3 | Ativar `RAG_EXIGIR_VIGENCIA_VERIFICADA` antes da reingestão | Ativar (fail-closed) e programar reingestão imediata | Com a flag on e sem reingestão, a recuperação de legislação fica vazia; com a flag off, norma revogada pode fundamentar resposta |
| 4 | Migration 132 (destrutiva) | Staging + backup comprovado antes de produção | Perda irreversível de PII em claro sem backfill validado = incidente LGPD |
| 5 | Branch protection (#250) | Configurar já (Onda 0) | Todo o esforço de consolidação continua desprotegido contra push direto |
| 6 | Congelamento de features | Formalizar até o fim da Etapa 1 | Fila volta a crescer mais rápido do que esvazia |
| 7 | EJC como agenda de prazos | Vetado até homologar #717 | Perda de prazo real por sistema não certificado |

**Limitações deste levantamento:** estados de `mergeable_state` e CI são um retrato de
2026-08-06 e mudam a cada push/merge — reconferir antes de cada ato; a análise de
sobreposição foi feita por lista de arquivos (não por hunk), então pares com 1–3 arquivos em
comum podem mesclar sem conflito real; nenhum ambiente de produção foi acessado (o
diagnóstico do deploy vem exclusivamente dos logs do GitHub Actions).
