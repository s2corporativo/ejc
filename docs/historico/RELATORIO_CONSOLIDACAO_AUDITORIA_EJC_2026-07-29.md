# Relatório de auditoria, consolidação e correção — EJC

**Data:** 2026-07-29
**Branch de trabalho:** `claude/ejc-audit-consolidation-e6xx16`
**Commit inicial:** `1befdf0` (= `origin/main`)
**Ambiente da auditoria:** container remoto, clone novo do repositório.

---

## A. Diagnóstico executivo

### Por que as alterações não aparecem no sistema

**Causa-raiz: o trabalho das sessões paralelas nunca chegou à `main`, e o deploy só publica a `main`.**

Não houve perda de trabalho, conflito silencioso, cache de navegador, service worker
antigo nem build desatualizado. O motivo é estrutural e está comprovado em duas
evidências independentes:

**Evidência 1 — o gatilho de deploy.** `.github/workflows/deploy-vps.yml:17-19`:

```yaml
  workflow_run:
    workflows: ["CI"]
    types: [completed]
    branches: [main]
```

O job só executa em `workflow_dispatch` com `github.ref_name == 'main'` ou após a
CI concluir com sucesso num **push à `main`** (linhas 30-35). Nenhum outro ref
dispara publicação.

**Evidência 2 — onde o trabalho está.** No momento da auditoria, `origin/main`
estava em `1befdf0` e havia **10 pull requests de sessões do Claude Code abertos**,
nenhum mergeado — sete deles criados nas últimas 24 horas:

| PR | Branch | Commits à frente da main | Arquivos |
|----|--------|-------------------------:|---------:|
| #496 | `claude/new-session-h6j254` | 8 | 35 |
| #493 | `claude/new-session-inxvz2` | 25 | 65 |
| #494 | `claude/analysis-70hy7z` | 9 | 35 |
| #495 | `claude/new-session-4tyz91` | 14 | 24 |
| #500 | `claude/analise-triagem-raio-x-juridica-jjusb3` | 12 | 34 |
| #497 | `claude/new-session-bhbv06` | 8 | 66 |
| #499 | `claude/execute-54wtju` | 4 | 12 |
| #501 | `claude/ejc-comprehensive-review-mmytyb` | 3 | 24 |
| #524 | `claude/vps-github-maintenance-5aghe9` | 3 | — |
| #525 | `claude/ejc-publish-updates-k12z4z` | 1 | 1 |

Todas as cinco correções citadas no pedido (gate por área do `run_eval.py`,
cleanup do `run_fictitious_smoke.py`, AI-019, piso de sigilo no `orchestrator.py`
e migração do modelo Groq no `deploy-vps.sh`) vivem **exclusivamente no PR #496**,
que nunca foi mergeado. Por isso nada disso está no ar.

**Hipóteses descartadas com evidência:** não há worktrees extras
(`git worktree list` → um só), não há stashes (`git stash list` → vazio), não há
submódulos, a árvore de trabalho está limpa e `HEAD == origin/main`. Não havia
nada não commitado a preservar.

### Um agravante encontrado durante a investigação

Mesmo depois de mergear, **não havia como verificar o que está publicado**.
`app_version()` (`backend/app/core/observability.py:41`) lê `GIT_SHA`, mas
**nenhum arquivo do repositório definia essa variável** — nem `docker-compose.yml`,
nem os scripts de deploy, nem os workflows. Em produção, `/api/health` respondia
sempre `"version": "dev"`. Isso torna impossível distinguir *"minha alteração não
foi publicada"* de *"minha alteração não funciona"* — que é exatamente a dúvida
do pedido. Corrigido (item C-6).

---

## B. Estado do Git

| Item | Valor |
|------|-------|
| Raiz real | `/home/user/ejc` |
| Remote | `s2corporativo/ejc` |
| Branch final | `claude/ejc-audit-consolidation-e6xx16` |
| Commit inicial | `1befdf0` |
| Worktrees | 1 (nenhum extra) |
| Stashes | nenhum |
| Submódulos | nenhum |
| Alterações não commitadas na entrada | nenhuma |
| Branches consolidadas | `claude/new-session-h6j254` (PR #496), sem conflito |
| Conflitos resolvidos | nenhum necessário no merge realizado |

Nenhum comando destrutivo foi usado: sem `reset --hard`, sem `clean -fd`, sem
`checkout -- .`, sem remoção de volumes ou de branches. As comparações entre PRs
foram feitas com `git merge-tree --write-tree`, que **não** toca a árvore de
trabalho.

---

## C. Bugs corrigidos

| ID | Sev. | Componente | Causa-raiz | Correção | Teste | Status |
|----|------|-----------|-----------|----------|-------|--------|
| C-1 | **CRÍTICA** | `ai/sanitization_policy.py` + `ai/core/orchestrator.py` | Piso de sigilo resolvia a área por lookup de chave **exata**; `domain` é campo livre e a UI é em português, então `"Família"`, `"Direito de Família"` e `"familia_analysis"` não batiam com `"familia"` e caíam no fallback externo | Canonização de acento/separadores/sufixo e consulta por palavra do rótulo composto, centralizada na política | `test_sigilo_piso_area.py` (60) | Corrigido |
| C-2 | **CRÍTICA** | `ai/core/orchestrator.py:205-224` | O piso estava dentro de `try/except Exception` que apenas logava — uma falha na política **rebaixava silenciosamente** para provedor externo | `try/except` removido; a política falha em vez de rebaixar | idem C-1 | Corrigido |
| C-3 | **ALTA** | `qa/e2e/run_fictitious_smoke.py` | `_cleanup` fora de `try/finally`: exceção no meio do fluxo abortava antes de limpar, deixando dados fictícios no staging e sem gravar o relatório | Cleanup e relatório movidos para o `finally` | `test_e2e_smoke_isolamento.py` (12) | Corrigido |
| C-4 | **ALTA** | `qa/e2e/run_fictitious_smoke.py` | Cleanup chamava `DELETE /api/cases/{id}` sem `motivo`; o router exige mínimo 5 caracteres e responde **422** — o caso nunca era removido e a suíte ficava vermelha por bug do próprio runner | `motivo` enviado na query | idem C-3 | Corrigido |
| C-5 | **ALTA** | `scripts/deploy-vps.sh` | A migração do modelo Groq depreciado foi adicionada a um **bootstrap manual**; o deploy real (`deploy-vps.yml` → `deploy_vps_safe.sh`) nunca chamava esse script, então a correção não alcançava a VPS | Extraída para `scripts/migrar_env_obsoletos.sh`, chamada pelos dois caminhos | `test_migrar_env_obsoletos.py` (16) | Corrigido |
| C-6 | **ALTA** | `main.py`, `docker-compose.yml`, `deploy_vps_safe.sh` | `GIT_SHA` era lido mas nunca definido: produção não informava qual commit executava | SHA injetado no container, exposto em `/api/health` e **conferido pelo deploy** antes de concluir | `test_health.py` (+3) | Corrigido |
| C-7 | **MÉDIA** | `qa/e2e/run_fictitious_smoke.py` | Dados fictícios idênticos a cada execução (mesmo CPF, mesmo nº de processo) forçavam 409 e o fallback "achar pelo marcador", fazendo uma execução operar sobre registro de outra | `RUN_ID` por execução, com CPF sintético válido e nº de processo próprios | idem C-3 | Corrigido |
| C-8 | **MÉDIA** | `qa/e2e/run_fictitious_smoke.py:163` | Redação do relatório só olhava o nível superior do JSON: a lista de clientes sob `data`, com **CPF decifrado**, ia inteira para o arquivo | Redação recursiva cobrindo CPF, CNPJ, e-mail e telefone | idem C-3 | Corrigido |
| C-9 | **MÉDIA** | `app/eval/run_eval.py` | `--smoke` imprimia "cobertura exigida atendida" mesmo sem nenhuma área exigida e sem nenhum gold set real; no CI isso era lido como aprovação da qualidade jurídica | Mensagem declara que valida apenas FORMATO | verificado por execução | Corrigido |
| C-10 | **CRÍTICA** | `scripts/deploy_vps_safe.sh:96` | `docker compose config >"/tmp/ejc_compose_config_*.txt"` gravava todos os valores interpolados — senha do Postgres, chaves de API, tokens — **em claro**, em arquivo world-readable de `/tmp` nunca removido, a cada deploy | `docker compose config --quiet` (correção do PR #497 adotada aqui) | `bash -n` + inspeção | Corrigido |

### Detalhe do C-1 — reprodução antes e depois

Executado com o orquestrador real e o gateway instrumentado
(`scratchpad/repro_ai019.py`), dados fictícios:

```
########## ANTES (código do PR #496) ##########
task_type    domain                -> gateway recebeu   modo resolvido
chat         Família               -> estrategia        externo_pseudonimizado   ← VAZA
chat         Direito de Família    -> estrategia        externo_pseudonimizado   ← VAZA

########## DEPOIS ##########
chat         Família               -> familia           local_completo
chat         Direito de Família    -> familia           local_completo
```

Impacto jurídico: conteúdo de caso de família, saúde, menores ou violência
doméstica sendo enviado a Anthropic/Groq contra a política declarada em
`sanitization_policy.py` — risco de LGPD (art. 33/46) e de sigilo profissional.
A área comum (`trabalhista`) permanece `externo_pseudonimizado`: o piso não
virou bloqueio geral.

---

## D. Arquivos alterados

| Arquivo | Finalidade | Alteração | Risco | Teste |
|---------|-----------|-----------|-------|-------|
| `backend/app/services/ai/sanitization_policy.py` | Política de sigilo por tarefa/área | `normalizar_rotulo()`, consulta por palavra, `rotulo_de_sigilo_reforcado()` | Baixo — só reforça sigilo; falso positivo exige IA local, nunca vaza | `test_sigilo_piso_area.py` |
| `backend/app/services/ai/core/orchestrator.py` | Núcleo único de IA | Piso delegado à política; `try/except` removido | Médio — passa a propagar erro de política (intencional) | idem |
| `qa/e2e/run_fictitious_smoke.py` | Runner E2E de homologação | `try/finally`, `motivo` no DELETE, `RUN_ID`, redação recursiva | Baixo — só afeta homologação | `test_e2e_smoke_isolamento.py` |
| `scripts/migrar_env_obsoletos.sh` | **Novo** — migra valores obsoletos do `.env` | Idempotente, backup 600, sem imprimir segredos, `--dry-run` | Médio — escreve no `.env` da VPS; mitigado por backup e por só tocar valores antigos conhecidos | `test_migrar_env_obsoletos.py` |
| `scripts/deploy_vps_safe.sh` | Deploy real | Chama a migração; exporta `GIT_SHA`; confere o commit publicado | Médio — nova trava pode abortar deploy (desejado) | `test_health.py`, `test_migrar_env_obsoletos.py` |
| `scripts/deploy-vps.sh` | Bootstrap manual | Bloco duplicado substituído pela chamada única | Baixo | idem |
| `docker-compose.yml` | Stack | `GIT_SHA` em `backend` e `worker` | Baixo | `test_health.py` |
| `backend/app/main.py` | Entrypoint | `/api/health` expõe `commit` | Baixo — SHA é dado público | `test_health.py` |
| `backend/app/eval/run_eval.py` | Harness de avaliação | Mensagem de sucesso honesta | Baixo | execução manual |

---

## E. Testes executados

| Comando | Resultado | Aprovados | Falhas | Observação |
|---------|-----------|----------:|-------:|------------|
| `pytest` (backend, antes) | OK | 3553 | 0 | linha de base após merge do #496 |
| `pytest` (backend, depois) | OK | 3584 | 0 | +31 testes novos; 128 skipped |
| `ruff check app` | OK | — | 0 | "All checks passed!" |
| `npm run lint` (tsc --noEmit) | OK | — | 0 | |
| `npm test` (vitest) | OK | 225 | 0 | 38 arquivos |
| `npm run build` | OK | — | 0 | build de produção concluído |
| `python -m app.eval.run_eval --smoke` | OK | — | 0 | formato válido; **cobertura jurídica zero** (ver H-1) |

**Validação de que os testes novos são regressões reais** — executados contra o
código anterior à correção:

- `test_sigilo_piso_area.py`: falha (o piso não era alcançado pelo rótulo livre).
- `test_e2e_smoke_isolamento.py`: **8 de 12 falham**. As 4 que passam são as
  invariantes de isolamento que o PR #496 já acertava — nenhum DELETE por filtro
  amplo e registro alheio preservado.
- `test_migrar_env_obsoletos.py`: falharia por inexistência do script.

---

## F. Banco e migrations

Auditoria feita por AST sobre os 116 arquivos de `backend/alembic/versions/`.

- **`main` tem head único:** `121_sala_juridica_chat`. Grafo íntegro: nenhuma
  revision duplicada, nenhum `down_revision` órfão.
- A divergência histórica 101/103 já está reconciliada por
  `104_merge_entrada_orquestrador` (revisão de merge com dois pais). Um parser
  por regex de linha única lê esse `down_revision` multilinha errado e reporta
  falsamente 3 heads — só a leitura por AST dá o resultado correto.
- **Colisão de numeração entre PRs abertos — CONFIRMADA:**
  - PR #493 adiciona `122_route_usage_metrics` (`down_revision = 121_sala_juridica_chat`);
  - PR #497 adiciona a cadeia `122_documentos_publicacao_hash` … `127_audit_log_worm`, também partindo de `121`.
  - Mergear os dois produz **duas heads** e `alembic upgrade head` passa a falhar
    com *"Multiple head revisions are present"*. Há também conflito textual em
    `backend/tests/test_alembic_single_head.py` (ambos editam a mesma linha).
- O `MIGRATION_RESERVATIONS.md` do PR #499 está **desatualizado**: registra
  `122_data_room_token_hash` como reservada pelo PR #495, mas o estado atual do
  #495 não contém migration alguma.
- **Atenção antes de aplicar:** `124_data_room_token_hash.py` (PR #497) é
  destrutiva de segredo — faz backfill de `token_hash` e depois `SET NULL` em
  `data_room_links.token`; o downgrade não recupera o token em claro. Exige
  backup comprovado (regra crítica 2 do `CLAUDE.md`) e decisão humana, porque
  duplica com desenho oposto o objetivo planejado no PR #495.

**Nenhuma migration foi criada, aplicada ou alterada nesta auditoria.**

---

## G. Deploy

Não foi possível publicar: este container não tem acesso à VPS (as credenciais
de `vps-tools/.env` não são versionadas, por desenho) nem ao runner
self-hosted `ejc-vps`. O que foi entregue é o caminho para que o próximo deploy
seja verificável:

- o deploy passa a exportar `GIT_SHA` antes do build;
- o SHA entra no container via `docker-compose.yml`;
- `/api/health` responde `"commit": "<sha>"`;
- **o deploy aborta** se o backend no ar declarar SHA diferente do construído —
  o que detecta container antigo em pé, imagem reaproveitada ou bind mount
  apontando para outro diretório;
- no primeiro deploy após esta mudança a imagem anterior ainda não expõe o
  campo: o script apenas avisa e segue; da segunda vez em diante a trava vale.

Para conferir manualmente depois de publicar:

```bash
curl -s https://ejc.depaulateixeira.adv.br/api/health | jq .commit
# deve ser idêntico ao commit mergeado na main
```

---

## H. Pendências reais

**H-1 — Gold set de avaliação jurídica vazio (prioridade ALTA).**
`backend/app/eval/` contém apenas `agent_scenarios.jsonl` e dois arquivos
`*.example.*`. Não há nenhum gold set real: a cobertura por área é **zero**. O
gate por área do PR #496 está tecnicamente correto, mas hoje é inerte — a CI roda
`run_eval --smoke` sem `--areas-obrigatorias` (`.github/workflows/ci.yml:177`) e
valida apenas JSON. Corrigi a mensagem para não afirmar aprovação que não existe,
mas **não** liguei o gate: sem casos reais ele deixaria a CI vermelha para todos
os PRs. Ação necessária: autoria de casos jurídicos reais por área
(penal, trabalhista, consumidor…), o que exige conhecimento do escritório.
Depois disso, ligar `--areas-obrigatorias` e `--min-casos-area` na CI.

**H-2 — Colisão de migrations entre PR #493 e PR #497 (prioridade ALTA).**
Detalhada em F. Bloqueia o merge dos dois na ordem atual. Ação: mergear #497
primeiro (cadeia 122–127 entra intacta), depois renumerar a migration do #493
para `128_route_usage_metrics` com `down_revision = 127_audit_log_worm`. Não criar
revisão de merge.

**Mitigação já aplicada:** o PR #499 foi consolidado nesta branch, o que traz a
guarda `test_migration_numbering_guard.py` para a `main` antes dos dois. Confirmei
empiricamente, num worktree descartável que mergeou #497 e #493 sobre esta
branch, que a guarda **reprova** a colisão:

```
FAILED test_nenhum_numero_de_migration_e_reutilizado
FAILED test_existe_um_unico_head
AssertionError: o repositório tem 2 heads de migration
  (['122_route_usage_metrics', '127_audit_log_worm'])
```

Com esta branch na `main` primeiro, a colisão aparece no CI do PR seguinte em vez
de quebrar `alembic upgrade head` em produção.

**H-3 — Deploy e validação da aplicação publicada NÃO executados.**
Sem acesso à VPS. Os itens 1-10 da seção 14 do pedido (checkout na VPS, rebuild,
janela anônima, versão do bundle, console limpo) permanecem **não validados**.

**H-4 — Achados do runner E2E não corrigidos (prioridade MÉDIA).**
A auditoria do runner levantou outros pontos que deixei documentados sem alterar,
por serem menores e fora do caminho crítico: 404 no cleanup é aceito como sucesso
sem releitura que prove a remoção; recursos criados fora dos três alvos
(movimento, POSTs futuros da matriz) não entram no cleanup; um `DELETE` adicionado
à matriz seria executado sem passar pela guarda de `criados_nesta_execucao`.

**H-5 — Nada foi executado contra banco real.** Os testes de banco exigem
`RUN_DB_TESTS=1` com Postgres/pgvector, indisponível aqui. 128 testes ficaram
skipped.

**H-6 — A guarda de numeração de migrations vive só no PR #499.**
`test_migration_numbering_guard.py` pegaria a colisão H-2, mas não está na `main`.
Como o #499 não toca `alembic/versions/`, é o merge de menor risco e deveria ir
primeiro, para que os PRs seguintes já rodem contra a guarda.

---

## Plano de consolidação dos PRs restantes

Conflitos **reais** medidos com `git merge-tree` (não apenas sobreposição de arquivos):

| Par | Arquivos em conflito |
|-----|---------------------|
| #493 × #495 | 5 — `ramos.py`, `analise_bancaria.py`, `peca_geracao.py`, `RamoBase.tsx`, `ramosConfig.ts` |
| #496 × #495 | 3 — `ramos.py`, `analise_bancaria.py`, `RamoBase.tsx` |
| #493 × #497 | 3 — `.gitignore`, `test_alembic_single_head.py`, `test_schema_dr_parity.py` |
| #496 × #493 | 2 — `ramos.py`, `analise_bancaria.py` |
| #496 × #500 | 1 — `citation_check.py` |
| #493 × #501 | 1 — `RamosHub.tsx` |
| #494 × #497 | 1 — `legal_docs.py` |
| #495 × #497 | 1 — `DataRoom.tsx` |

Arquivos mais disputados: `.env.example` e `RamoBase.tsx` (4 PRs cada),
`peca_geracao.py` (4), `ramos.py` e `ramosConfig.ts` (3).

**Ordem sugerida** — do menor para o maior risco, resolvendo conflito a cada passo
e rodando a suíte entre eles:

1. ~~**#499** (governança/docs)~~ — **já consolidado nesta branch.** A guarda de
   numeração de migrations entra junto com o #526.
2. **#526 (esta branch)** — consolida #496 + #499, corrige dez defeitos e
   instrumenta o deploy. Substitui o #496 e o #499 na fila.
3. **#494** (fluxos) — conflita só com #497, em um arquivo.
4. **#500** (triagem/IDOR) — resolver `citation_check.py` contra o #496.
5. **#497** (34 bloqueadores) — entra com a cadeia de migrations 122–127 intacta.
   Revisar a `124` (destrutiva de segredo) com backup antes.
6. **#493** (áreas) — renumerar a migration para `128` e resolver os conflitos de
   `ramos.py`/`RamoBase.tsx`/`ramosConfig.ts`, que são os mais pesados.
7. **#495** (P0 hard/VPS) — maior sobreposição com #493/#496; entra por último,
   já contra a base consolidada.
8. **#501** (UX) e os PRs de VPS/dependabot, por fim.

**Não execute merges em paralelo.** Metade dos conflitos está concentrada em
`ramos.py`, `RamoBase.tsx` e `ramosConfig.ts`; resolvê-los mais de uma vez em
frentes simultâneas é o que reintroduz regressão.

---

## I. Resultado final

```
Git e consolidação:   APROVADO COM RESSALVAS  (causa-raiz comprovada; #496
                      consolidado e testado; 9 PRs seguem pendentes, com plano
                      e conflitos mapeados)
Backend:              APROVADO                (3584 testes, ruff limpo)
Frontend:             APROVADO                (tsc limpo, 225 testes, build ok)
Banco:                APROVADO COM RESSALVAS  (main com head único e íntegro;
                      colisão 122 entre #493 e #497 documentada, não resolvida)
IA:                   APROVADO                (bypass crítico do piso de sigilo
                      fechado, com reprodução antes/depois)
RAG:                  NÃO VALIDADO            (sem gold set real e sem banco)
Segurança:            APROVADO COM RESSALVAS  (C-1, C-2 e C-8 corrigidos;
                      auditoria ampla de authz não foi refeita nesta sessão)
Testes:               APROVADO                (suíte completa verde nos dois lados)
Deploy:               NÃO VALIDADO            (sem acesso à VPS; instrumentação
                      de verificação entregue e testada)
Aplicação publicada:  NÃO VALIDADO            (depende do merge e do deploy)
```

Não há base para afirmar "100% corrigido". O que está comprovado: a razão de as
alterações não aparecerem, a correção de nove defeitos com teste de regressão
para cada um, e a suíte completa verde em backend e frontend. O que continua em
aberto está na seção H, com a ação necessária em cada caso.
