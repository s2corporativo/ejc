# RELATÓRIO — Auditoria do sistema após alterações via Manus (15/08/2026)

**Solicitante:** titular (via chat) · **Issue:** #1147 · **Branch:** `claude/system-audit-ra49fg`
**Escopo:** estado do sistema após as alterações feitas com o Manus AI (13–15/08) — pipeline CI/CD e governança, scripts e conteúdo da biblioteca jurídica, saúde do código (testes/lint/build/migrations) e segurança das áreas sensíveis tocadas recentemente.
**Método:** análise do histórico git da `main`, API do GitHub (workflows, runs, PRs, branch protection via evidência do #1140), leitura integral dos arquivos citados, subagentes `security-auditor` e `qa-tests` com verificação em primeira mão dos achados críticos. Sem acesso ao banco/diretório de produção (governança §9).

---

## 1. Sumário executivo

O que o Manus produziu (lote piloto da biblioteca jurídica + scripts de ingestão/monitoramento) tem **defeitos graves de qualidade de fonte e de desenho de ingestão**, e entrou na `main` **por fora de toda a esteira de governança** — que está, hoje, inoperante em três camadas ao mesmo tempo:

1. **Branch protection da `main`: inexistente** (`protected=false`, sem required checks — evidência no próprio PR #1140).
2. **CI morto desde ~12–13/08**: toda execução em runner GitHub-hosted termina em `startup_failure` com 0 jobs (25 execuções recentes na `main`, todas agrupadas no placeholder "BuildFailed"); PRs abertos têm **zero check runs**.
3. **Workflows de governança desligados manualmente em 13/08 ~01:20 UTC**: `governanca.yml` (trava de PR sem Issue), `auto-integracao.yml` (merge automático), `continuity-ui-gates.yml`, `rag-production-activation.yml`, `producao-prova-continuidade.yml`, `release-certification.yml`, entre outros — ~70 dos 88 workflows estão `disabled_manually`.

Com os gates apagados, o trabalho passou a entrar por **commit direto e "merge local na VPS"** (`6a07e21`, `02e9d77`, commits do Manus AI) — sem CI, sem review, sem security-auditor, sem teste. O risco mais concreto: **se a ingestão do lote foi executada em produção, jurisprudência não confirmada está fundamentando a IA jurídica de todos os clientes como conteúdo "aprovado"** (ver achados A1/A2). O PR #1143, que corrige e quarentena o lote, existe — mas está em **draft, não integrado**.

## 2. O que o Manus alterou (mapeamento)

| Commit | Autor | Conteúdo | Como entrou |
|---|---|---|---|
| `4e67469` | Manus AI | Lote piloto: 24 temas em `docs/biblioteca_juridica/` + `backend/scripts/ingestao_biblioteca_juridica.py` + relatório de "homologação" | PR #1139, **merge local na VPS** (`6a07e21`) |
| `be28fb8` | Manus AI | `GUIA_EXECUCAO_PRODUCAO.md` | commit direto na `main` |
| `ac7f2e1` | Manus AI | `backend/scripts/monitor_ingestao.py` + guia | commit direto na `main` |
| `b7b351a` | Manus AI | `RUNBOOK_DEPLOY_VPS.md` (correção do runner) | commit direto na `main` |
| `02e9d77` | titular | Correções nos dois scripts (paths, `db.commit()`, parse do docker stats) | commit direto na `main` |

## 3. Achados — CRÍTICOS

### A1. Base RAG global sujeita a ingestão auto-aprovada, sem HITL
`backend/scripts/ingestao_biblioteca_juridica.py:189-199` chama `upsert_documento(..., client_id=None, confianca="alta")` **sem** gravar `requires_human_review`/`rag_status` no `extra`. O listener `app/services/knowledge_autoapproval.py` (ramo `else`, linhas ~99-100) aplica `rag_status="aprovado"` a qualquer documento sem essa flag — verificado em primeira mão. Resultado: os 24 documentos nascem **aprovados** e passam pelo regime estrito `RAG_EXIGIR_APROVADO=True` (`app/core/config.py:641`), alimentando a base pública (`client_id=NULL`) usada por todos os clientes. Agravante: o `citation_gate` valida citações contra essa mesma base — um julgado inventado ingerido passa a "confirmar" a si próprio na geração de peças. Isso contorna, na prática, o HITL que a governança proíbe enfraquecer (regra 13).

### A2. Conteúdo do lote: jurisprudência não confirmada com metadados que declaram o contrário
Verificado em primeira mão nos arquivos da `main`:
- **15 dos 24 documentos** contêm blocos `NAO_CONFIRMADO` (processo, relator, data ou fonte não confirmados);
- `consumidor_bancario/14_*.md` (JUR-CONS-000016) traz **URLs oficiais marcadas "(Simulado…)"** e a própria seção de divergências admite que a atribuição do Tema 1046/STJ está **errada**;
- os **24 arquivos** declaram `gerado_por_IA: false` — falso: o conteúdo é produção do Manus AI (commit `4e67469`), e esse é exatamente o campo que a curadoria usaria para exigir revisão redobrada;
- todos declaram `origem_conteudo: fonte_oficial` e 23/24 `nivel_confiaca: ALTA`;
- `RELATORIO_AUDITORIA_LOTE_PILOTO.md` na `main` afirma "documentos em quarentena: 0" e "nenhum dado essencial não verificável persistiu" — desmentido pelos próprios arquivos do lote.
Viola a regra 5 ("toda regra jurídica precisa de fonte oficial, vigência e teste"). O PR #1143 (draft) reconhece tudo isso, revoga o relatório e traz quarentena — **mas não foi integrado**.

### A3. Esteira de CI/CD e governança inoperante
- `main` **sem branch protection** (`protected=false`, sem required checks — contexto documentado no PR #1140, aberto e parado);
- CI (`ci.yml`) em `startup_failure` com 0 jobs em **todas** as execuções desde ~12/08, inclusive `workflow_dispatch` — padrão consistente com **cota/limite de gasto de minutos GitHub-hosted esgotado** (o próprio `ci.yml` anota "spending limit $0"; a migração para runner self-hosted em `9c5113d` foi motivada por "zero consumo GitHub"; o #1119 devolveu as validações de PR para `ubuntu-latest`, e desde então nada roda);
- PRs abertos (#1140, #1143) com **zero check runs** — `mergeable_state: clean` ali significa apenas "sem conflito", não gate verde;
- `deploy-vps.yml` dispara via `workflow_run` após CI verde na `main` → **com o CI morto, o deploy automatizado (backup → health → rollback) não roda**; produção só é atualizada por ação manual na VPS, sem as salvaguardas da esteira;
- workflows de governança desligados manualmente em 13/08 (~01:20 UTC): `governanca.yml`, `auto-integracao.yml`, `continuity-ui-gates.yml`, `rag-production-activation.yml`, `release-certification.yml`, `producao-prova-continuidade.yml`, `main-provenance.yml`, `architecture-inventory.yml`.

## 4. Achados — ALTOS

### A4. Script de ingestão executa mesmo reprovado na própria validação
`ingestao_biblioteca_juridica.py:150-163`: os erros de `validar()` são apenas impressos; com `--execute` a ingestão prossegue com chaves ausentes, IDs duplicados ou jurisprudência órfã. A heurística anti-alucinação (linhas 51-52, 109-112) só detecta processo **sem** tribunal — o padrão real do lote é o inverso (tribunal citado com dados `NAO_CONFIRMADO`), que passa limpo.

### A5. Caminho de entrada sem CI virou prática
`6a07e21` ("merge local na VPS") e quatro commits diretos na `main` em 48h. O `GUIA_EXECUCAO_PRODUCAO.md` (§2) institucionaliza o desvio: manda fazer `git checkout` de branch na VPS de produção e `export $(grep -v '^#' .env | xargs)` (despeja segredos de produção no ambiente do shell). Contraria as regras 1, 9 e o fluxo Issue→PR→gates.

## 5. Achados — MÉDIOS e BAIXOS

| Sev. | Achado | Evidência |
|---|---|---|
| MÉDIO | Nenhum teste para os dois scripts novos (regra 6) | `grep` em `backend/tests` sem ocorrências |
| MÉDIO | Categoria fixa: toda `jurisprudencia_estruturada` vira `jurisprudencia_stj`, mesmo STF/TCU/TST | `ingestao_biblioteca_juridica.py:41-43` |
| BAIXO | `monitor_ingestao.py:72` — `IndexError` com saída vazia do `docker stats` (o `if not linha` da linha seguinte nunca é alcançado) | leitura do arquivo |
| BAIXO | Caminhos hardcoded do sandbox do Manus (`/home/ubuntu/...`, `/lote_piloto`) e `sys.path` autodetectado (em host com `/app` alheio importaria código de fora do repo) | `ingestao_biblioteca_juridica.py:146,168` |
| BAIXO | Exceção por documento engolida com `print` e exit code 0 — ingestão parcial parece sucesso | `ingestao_biblioteca_juridica.py:202-203` |
| BAIXO | `score_autoridade: 10` em `ambiental/07_*.md` (demais: 90-100; provável dígito perdido) — o reranker usa esse score | front-matter do arquivo |
| BAIXO | ~70 workflows `disabled_manually` acumulados (dezenas de "temp/format/patch" descartáveis) — higiene e superfície de confusão | `list_workflows` (88 no total) |
| INFO | `data_pesquisa` em formatos mistos; front-matter fechando com `false---` sem quebra (tolerado pelo regex do script, não por parsers YAML padrão) | arquivos do lote |

## 6. O que está OK (verificado)

- **Cadeia de migrations íntegra**: head único `142_document_hash_rescan` (a 104 é merge legítimo de 101+103); numeração e reservas coerentes.
- **Assinatura do script compatível**: `upsert_documento` existe em `app/services/ingestion_service.py:285` com os kwargs usados; `yaml.safe_load` correto; `subprocess` sem `shell=True` no monitor.
- **Mudanças sensíveis recentes da esteira normal preservam RBAC/ownership** (verificação do security-auditor): `fb0ba1a` (publicação no portal com piso `advogado+`/`socio+`, tipos `interno`/`segredo_justica` nunca publicáveis, audit log), `d1159db` (Sala Jurídica/Raio-X com gate de equipe jurídica + ownership), `da624b0` (portal usa a política canônica de extensões + magic bytes).
- **Sem segredos versionados** desde 10/08 — apenas `.env.example` com placeholders.
- **Correções do titular (`02e9d77`) são reais**: `db.commit()` faltava (a ingestão silenciosamente não persistia), parse do docker stats via JSON.

## 7. Saúde do código (testes, lint, build)

_Resultados da rodada desta auditoria (ambiente da sessão em `180fa77`, não CI; ambiente sem Postgres → 265 skips `*_dblevel` por design):_

| Verificação | Resultado |
|---|---|
| pytest backend | **5 failed** / 5.563 passed / 265 skipped (+79 subtests) — e **1 erro de coleta** (abaixo) |
| ruff (0.6.9, config do repo) | 0 violações |
| `npm ci` | **FALHA** — lockfile dessincronizado |
| `npm run lint` (tsc --noEmit) | 0 erros |
| vitest | **3 failed** / 558 passed (561) |
| `npm run build` (tsc + vite) | OK (7,46s) |

**Detalhe das falhas (todas determinísticas, de código — não de ambiente):**

1. **Erro de coleta que quebra `pytest` local sem banco** — `backend/tests/test_document_rescan_integracao_dblevel.py:23` usa `pytest.skip(...)` a nível de módulo sem `allow_module_level=True`; com o `pytest==9.0.3` pinado, a suíte inteira morre em `Interrupted: 1 error during collection`. Os outros 70 arquivos `*_dblevel` usam `pytest.mark.skipif` (padrão correto); só este destoa. O CI não enxerga porque define `RUN_DB_TESTS=1`. *(Entrou com a fiação do rescan SHA-256, #1144.)*
2. **2 falhas de recesso/prazo administrativo** — `tests/test_deadlines_recesso_art220.py`: prazo administrativo calcula `2025-12-30` onde o teste espera `2026-01-14`. A área é exatamente a do commit mais recente da `main` (`180fa77`, PRZ-03/#1146, "recesso não afeta prazos não judiciais") — regressão ou teste desatualizado que o CI morto deixou passar.
3. **Drift de política de conteúdo** — `tests/test_document_content_policy.py:58`: extensão `.md` existe só em `routers/documents.py` (`EXTENSOES_PERMITIDAS`), fora da política canônica — paridade quebrada.
4. **2 falhas de registro de rotas** — `tests/test_rotas_registro_explicito.py`: `POST /api/teses/motor/async` e `GET /api/teses/motor/async/{task_id}` (motor de teses assíncrono, #1132) não foram declaradas em `ADICOES_INTENCIONAIS`; contagem 851 ≠ 849.
5. **Lockfile do frontend dessincronizado** — `40723ce` (#1137) alterou `frontend/package.json` para `"globals": "^17.9.0"` **sem regenerar** `package-lock.json` (preso em 17.7.0). `npm ci` falha → **o job `frontend-build` do CI quebraria aqui assim que o CI voltar**.
6. **3 falhas de vitest** — `src/stores/cadastroManual.test.ts:130` (mensagem de 422 agora prefixa o campo: `"area: Área inválida"` vs `"Área inválida"` esperado) e `src/pages/CasoDetalhe/TabDocumentos.contexto.test.tsx` (2 testes: botões "Solicitar ao cliente" e "Solicitar assinatura" não existem mais no DOM do componente atual).

**Leitura conjunta:** as 8-9 quebras acima são recentes e coincidem com a janela em que o CI parou de rodar (12–15/08) — é o custo direto do achado A3: sem gates, regressões entram na `main` sem serem vistas. Nenhuma foi corrigida nesta auditoria (fora de escopo; viram Issues próprias).

## 8. Recomendações priorizadas

1. **[IMEDIATO] Verificar se a ingestão rodou em produção** e, em caso positivo, quarentenar: o PR #1143 já traz script idempotente de quarentena dos 24 `canonical_ids` (dry-run primeiro). Enquanto estiverem `aprovado`, jurisprudência não confirmada fundamenta peças de clientes reais. *(Exige decisão/execução do titular — agente não acessa produção.)*
2. **[IMEDIATO] Restaurar branch protection da `main`** — o PR #1140 está pronto (`mergeable_state: clean`) e fail-closed; precisa de revisão independente + execução do bootstrap autorizado.
3. **[CURTO PRAZO] Religar o CI**: resolver a causa do `startup_failure` (cota/spending limit de minutos GitHub-hosted — conferir em Settings → Billing; alternativa: devolver validações de PR ao runner self-hosted com isolamento, como era pós-`9c5113d`). Sem CI verde na `main`, o `deploy-vps.yml` (backup/health/rollback) nunca dispara.
4. **[CURTO PRAZO] Reativar `governanca.yml` e demais gates** desligados em 13/08, e revisar/integrar o PR #1143 (hardening + `rag_status=pendente` obrigatório na ingestão + quarentena).
5. **[CURTO PRAZO] Corrigir o lote na fonte**: `gerado_por_IA: true` nos 24, confirmar ou remover cada bloco `NAO_CONFIRMADO`, corrigir Tema 1046→466/STJ + Súmula 479, `score_autoridade` do ambiental/07, e retificar `RELATORIO_AUDITORIA_LOTE_PILOTO.md` (o #1143 já cobre a maior parte).
6. **[MÉDIO PRAZO] Fechar o desvio de processo**: remover do `GUIA_EXECUCAO_PRODUCAO.md` as instruções de checkout/export de `.env` na VPS; tratar "merge local na VPS" como exceção registrada, não como procedimento; testes de regressão para os dois scripts.
7. **[HIGIENE] Excluir os ~50 workflows temporários** (`tmp-*`, `*-temp`, `_apply-*`, `format-*`) já desligados.

## 9. Adendo — decisões do titular e correções aplicadas (15/08, mesma sessão)

Após a entrega do relatório, o titular decidiu por chat: **(a)** o GitHub deve operar 100% na
cota gratuita (o consumo pago estava alto — confirma a causa do achado A3); **(b)** os
documentos do lote foram encomendados ao Manus **como simulações para servir de modelo** — a
correção não é apagar, é etiquetar. Com essa autorização, esta sessão aplicou no mesmo PR:

1. **CI de volta ao runner self-hosted `ejc-vps`** (reversão do #1119, restaurando a
   abordagem do `9c5113d`): `ci.yml` (3 jobs), `ejc-release-gate.yml`, `governanca.yml`,
   `continuity-ui-gates.yml` e o job `validar` do `backup-gdrive-activation.yml`.
   Controles compensatórios mantidos/garantidos: Postgres efêmero isolado (porta 55432,
   credenciais próprias, limpeza ao final), nenhum job de PR usa `environment: production`,
   e o repositório não aceita fork externo. O contrato foi **reescrito, não removido**:
   `backend/tests/test_self_hosted_runner_isolation.py` agora guarda a nova política e os
   controles compensatórios (7 testes).
2. **Reclassificação de 23/24 documentos do lote como modelo simulado**: front-matter
   corrigido (`origem_conteudo: modelo_simulado`, `gerado_por_IA: true`,
   `tipo_camada: modelo_peca` → categoria `modelo_documento_juridico`, fora do circuito de
   jurisprudência; `nivel_confiaca: BAIXA`) + banner "MODELO SIMULADO — NÃO CITAR COMO
   JURISPRUDÊNCIA" no corpo. Regressão: `backend/tests/test_biblioteca_juridica_metadados_modelo.py`.
   O arquivo `consumidor_bancario/14_*` **não** foi tocado — pertence ao PR ativo #1143
   (regra 4), que já o corrige e quarentena.
3. Dry-run do script de ingestão validado sobre os arquivos reclassificados (23×
   `modelo_documento_juridico`); testes-meta de workflows (37) e os 10 novos passam.

**Parecer de segurança sobre a reversão de runner** (rodada dedicada do `security-auditor`
sobre o diff de CI): os controles de YAML são reais (Postgres efêmero verificado, nenhum
`secrets.*` referenciado por job de validação, `permissions: contents: read` em todos), e a
trava de fork — que era só política — foi **fechada em código nesta sessão**: todos os 8 jobs
de validação agora têm `if` que bloqueia execução de PR vindo de fork, guardado por teste novo
no contrato. **Permanece um risco residual de host que só o titular resolve na VPS**: o runner
`ghrunner` está no grupo `docker` e tem `sudo NOPASSWD:ALL`
(`scripts/setup-selfhosted-runner.sh:109-114`) — com isso, um step de PR malicioso poderia
alcançar containers de produção ou ler `/opt/ejc/.env` (chaves PII/JWT). Mitigação recomendada:
remover `NOPASSWD:ALL` (os jobs de validação não usam `sudo`), avaliar tirar o runner do grupo
`docker` (exige daemon dedicado/rootless para o Postgres efêmero) e conferir em Settings →
Actions → General que "Fork pull request workflows" exige aprovação. Enquanto isso não for
feito, a operação na cota gratuita implica aceite explícito desse risco.

**Pendências que continuam com o titular:** reativar na interface do GitHub os workflows
`disabled_manually` (`governanca.yml`, `auto-integracao.yml`, `continuity-ui-gates.yml` etc. —
API desta sessão não reativa); confirmar que o runner `ejc-vps` está ativo na VPS
(`sudo systemctl status 'actions.runner.*'`); integrar #1140 (branch protection — atualizar os
cinco contexts exigidos se necessário) e #1143 (quarentena); executar a quarentena em produção
se a ingestão tiver rodado.

## 10. Riscos residuais e limitações

- **Não foi possível confirmar se a ingestão rodou em produção** (sem acesso ao banco de produção, por regra). A prioridade nº 1 depende dessa verificação humana.
- A causa exata do `startup_failure` (cota de minutos vs. outra restrição de billing) não é visível pela API com as credenciais da sessão — os sintomas (0 jobs, qualquer SHA, só em `ubuntu-latest`, `deploy-staging` self-hosted também sem jobs via `workflow_run`) apontam para billing/limite, mas a confirmação está em Settings → Billing do GitHub.
- A pilha GED (`#1133`/`#1134`) não foi inspecionada linha a linha nesta rodada; recomenda-se rodada dedicada de security-auditor se não houver evidência anexada nos PRs.
- Itens deste relatório que geram trabalho novo devem virar Issues próprias (regra 7); este relatório não corrige nada por si.
