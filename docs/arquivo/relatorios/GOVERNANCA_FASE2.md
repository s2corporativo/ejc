# Fase 2 — Ferramental de governança do EJC

Complementa `docs/GOVERNANCA_IA.md` (regras) com o que as **executa**: trava de CI,
proteção de branch, coleta de evidência e inventário do repositório. Sem estas peças,
a governança é declaratória — nada impede push direto, migration sem reserva ou PR sem Issue.

**Depende do PR #499** (`chore: governança ChatGPT + Claude Code`), que entrega a Fase 1:
`CLAUDE.md`, `AGENTS.md`, `docs/GOVERNANCA_IA.md`, `.github/pull_request_template.md`,
`backend/alembic/MIGRATION_RESERVATIONS.md` e a matriz de consolidação. As travas desta fase
citam esses documentos; aplicá-las antes do merge do #499 deixa referências apontando para
conteúdo ainda não versionado.

Verificado em 2026-07-29: o template de PR do #499 tem as mesmas seções do template em `main`,
então o check de descrição do `governanca.yml` continua válido depois do merge.

Executar **na ordem**. Cada item tem pré-requisito do anterior.

| Ordem | Item | Arquivo | Bloqueia |
|---|---|---|---|
| 1 | Travas de governança no CI | `.github/workflows/governanca.yml` | 2 |
| 2 | Proteção da branch `main` | `scripts/governanca/branch-protection.sh` | tudo |
| 3 | Levantamento de PRs P0 | `scripts/governanca/levantamento-pr-p0.sh` | 4 |
| 4 | Issue de consolidação + execução | `docs/ISSUE_E_PROMPT_CONSOLIDACAO_P0.md` | novas frentes |
| 5 | Inventário do repositório | `scripts/governanca/inventario-repo.sh` | — |
| 6 | Documentos de preenchimento humano | `docs/REGRAS_JURIDICAS.md`, `docs/FLUXO_CANONICO_EJC.md` | — |

---

## 1. Travas de governança no CI

`.github/workflows/governanca.yml` aplica cinco travas automáticas em cada PR:

- migration em `backend/alembic/versions/` sem atualizar `backend/alembic/MIGRATION_RESERVATIONS.md` no mesmo PR → falha
- segredo ou `.env` versionado → falha
- descrição de PR sem Issue vinculada, solução, testes, riscos residuais ou rollback → falha
- PR misturando governança (`CLAUDE.md`, `AGENTS.md`, `.claude/`, `docs/GOVERNANCA_IA.md`) com código funcional (`backend/app/`, `frontend/src/`) → falha
- PR originado de `main`/`master` → falha

A terceira trava (descrição do PR) tem uma exceção fechada: PR de manutenção automatizada de
dependências, aberto por autor de allowlist fechada (hoje só `dependabot[bot]`), é dispensado
de Issue vinculada e do preenchimento do template — as outras quatro travas continuam se
aplicando a esse PR sem exceção. Fundamentação, limite e a allowlist completa (que precisa
coincidir, nome por nome, com a do workflow) estão em **`docs/GOVERNANCA_IA.md`, seção 12** —
fonte canônica; este documento não duplica a regra, só aponta para onde ela vive. Ampliar a
allowlist é decisão de governança do titular, nunca deste (ou de qualquer outro) documento
operacional. `backend/tests/test_governanca_workflow.py` fixa o contrato entre as duas
allowlists.

Roda no runner self-hosted `ejc-vps`, como os demais workflows (`docs/RUNNER_SELFHOSTED.md`).
Complementa — não substitui — o `EJC Release Gate` (`scripts/ci_guard.sh`), que cobre
marcadores de merge, CORS wildcard e resíduos de release.

**O `ci.yml` não foi alterado.** O pacote original da Fase 2 trazia um `ci.yml` genérico
(`ubuntu-latest`, jobs `backend`/`frontend`, detecção de diretório ausente). Adotá-lo
substituiria o CI real do EJC, que é mais estrito: Postgres `pgvector/pgvector:pg16` de
serviço, `alembic upgrade head`, suíte completa com `RUN_DB_TESTS=1`, smoke dos gold sets
de eval e build do frontend, no runner self-hosted. A troca seria regressão de cobertura.
O que se aproveitou do `ci.yml` proposto — verificação de head único do Alembic — já existe
no repositório como teste (`backend/tests/test_alembic_single_head.py`).

## 2. Proteção da branch `main`

```bash
bash scripts/governanca/branch-protection.sh --contextos  # lista os checks reais reportados
bash scripts/governanca/branch-protection.sh --dry-run    # inspecionar o payload
bash scripts/governanca/branch-protection.sh              # aplicar
bash scripts/governanca/branch-protection.sh --verificar  # conferir
```

Exige `gh` autenticado com permissão de admin. A configuração anterior é salva em
`var/branch-protection-anterior.json` — `var/` já é ignorado, então o backup nunca entra
num commit por engano.

**Ato administrativo humano.** Nenhum agente executa este script sem autorização expressa
do titular (`CLAUDE.md`, regras 8 e 9).

**Risco a controlar:** o contexto exigido é o campo `name:` do job, não o id. Se um contexto
exigido nunca for reportado, nenhum PR será mesclável. Rode `--contextos` antes de aplicar.
Renomear um job em `.github/workflows/` obriga a reaplicar a proteção.

Contextos configurados, extraídos dos workflows em 2026-07-29:

| Workflow | Job | Contexto |
|---|---|---|
| `ci.yml` | `db-validation` | `Backend — suíte completa + schema/RAG (Postgres pgvector)` |
| `ci.yml` | `eval-smoke` | `Eval — smoke dos gold sets (offline, bloqueante)` |
| `ci.yml` | `frontend-build` | `Frontend — testes + typecheck + build` |
| `ejc-release-gate.yml` | `p0-guard` | `P0 guard — conflitos e segredos` |
| `governanca.yml` | `governanca` | `Governança — travas de PR` |

`eval-smoke` **entrou** na lista: verificado em 29/07, o job não tem `if:` nem
`continue-on-error`, então já roda em todo PR de qualquer forma. Exigi-lo não acrescenta
custo de execução — apenas torna a falha bloqueante, que é o que o próprio nome do job
declara. Deixá-lo de fora significaria aceitar merge com eval quebrado.

Ficaram **de fora** os gates `skipped` em PR por desenho (continuidade, provas de produção):
contexto que nunca é reportado impede todo merge.

## 3. Levantamento dos PRs P0

```bash
bash scripts/governanca/levantamento-pr-p0.sh                # usa 493 494 495 496 497
bash scripts/governanca/levantamento-pr-p0.sh 493 497 501    # PRs específicos
```

Somente leitura sobre o repositório. Gera `evidencias/` com diffs brutos e
`docs/MATRIZ_CONSOLIDACAO_P0_GERADA.md` com as seções 1 a 4 preenchidas por dado real:
inventário, migrations por PR, sobreposição par a par e teste de conflito contra `origin/main`.

As seções 5 e 6 — julgamento e ordem de integração — permanecem vazias por decisão.
Preenchê-las exige leitura do diff.

**`docs/MATRIZ_CONSOLIDACAO_P0.md` não é sobrescrita.** Ela contém o levantamento humano
de 2026-07-27 sobre os PRs 493–497. O script grava em arquivo distinto e recusa sobrescrever
destino existente sem `--forcar`.

Preserve `evidencias/` até o encerramento da consolidação: os diffs brutos são a prova de
que a análise não foi feita por inferência.

## 4. Consolidação

`docs/ISSUE_E_PROMPT_CONSOLIDACAO_P0.md` contém o corpo da Issue pronto para
`gh issue create` e o prompt operacional para o Claude Code, em modo de planejamento primeiro.

## 5. Inventário

```bash
bash scripts/governanca/inventario-repo.sh
```

Gera `docs/MAPA_DE_MODULOS.md`, `docs/MATRIZ_DE_ROTAS.md` e `docs/ARQUITETURA_ATUAL.md`
por leitura do código. A matriz de rotas cruza rotas declaradas no backend com chamadas do
frontend — chamada sem rota correspondente é defeito P1 e aparece na comparação das seções
1 e 3.

Os três arquivos entram versionados, gerados no commit `abcf2c46` (2026-07-29), com a data e o
commit de origem no cabeçalho de cada um. São **derivados**: regenere pelo script após alteração
estrutural em vez de editar as seções automáticas à mão. Só as seções `PREENCHIMENTO HUMANO`
se editam diretamente — e a regeração as reescreve vazias. Por isso o script copia a versão
anterior para `var/inventario-anterior/` antes de sobrescrever: recole dali o conteúdo humano.
`var/` já é ignorado, então essas cópias não poluem o diff.

Complementa o grafo do `graphify` (`graphify-out/`), que cobre o detalhe de chamada entre
símbolos; o inventário cobre estrutura e contrato de rota, que a revisão de PR cobra.

Seções marcadas `PREENCHIMENTO HUMANO` não são extraíveis e ficam vazias.

## 6. Documentos que exigem preenchimento humano

`docs/REGRAS_JURIDICAS.md` e `docs/FLUXO_CANONICO_EJC.md` entram como templates estruturados,
com as tabelas vazias.

Não podem ser gerados: o primeiro exige verificação de vigência por profissional habilitado
(`docs/GOVERNANCA_IA.md`, Seção 9; `CLAUDE.md`, regra 5); o segundo é decisão de produto.
Preenchimento por inferência produziria documentação falsa — e, no caso das regras jurídicas,
risco ao cliente.

O que era extraível do código já foi preenchido: a tabela de perfis do fluxo canônico reflete
`ROLE_LEVEL` em `backend/app/core/security.py`. Divergência entre essa tabela e o código é
defeito de revisão.

---

## Pendências deixadas por este pacote

| Pendência | Motivo | Quem resolve |
|---|---|---|
| Executar `branch-protection.sh` | Ato administrativo humano (`CLAUDE.md`, regras 8 e 9). Exige `gh` com permissão de admin, que o ambiente do executor não tem. | Titular |
| Preencher `docs/REGRAS_JURIDICAS.md` | Exige verificação de vigência por profissional habilitado | Titular (OAB) |
| Preencher `docs/FLUXO_CANONICO_EJC.md`, seções 2 a 4 | Decisão de produto | Titular |
| Seções `PREENCHIMENTO HUMANO` dos três inventários | Não extraíveis do código | Titular |
