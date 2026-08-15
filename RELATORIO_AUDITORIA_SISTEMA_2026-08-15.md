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

_Resultados da rodada desta auditoria (ambiente da sessão, não CI):_

<!-- QA_RESULTS -->

## 8. Recomendações priorizadas

1. **[IMEDIATO] Verificar se a ingestão rodou em produção** e, em caso positivo, quarentenar: o PR #1143 já traz script idempotente de quarentena dos 24 `canonical_ids` (dry-run primeiro). Enquanto estiverem `aprovado`, jurisprudência não confirmada fundamenta peças de clientes reais. *(Exige decisão/execução do titular — agente não acessa produção.)*
2. **[IMEDIATO] Restaurar branch protection da `main`** — o PR #1140 está pronto (`mergeable_state: clean`) e fail-closed; precisa de revisão independente + execução do bootstrap autorizado.
3. **[CURTO PRAZO] Religar o CI**: resolver a causa do `startup_failure` (cota/spending limit de minutos GitHub-hosted — conferir em Settings → Billing; alternativa: devolver validações de PR ao runner self-hosted com isolamento, como era pós-`9c5113d`). Sem CI verde na `main`, o `deploy-vps.yml` (backup/health/rollback) nunca dispara.
4. **[CURTO PRAZO] Reativar `governanca.yml` e demais gates** desligados em 13/08, e revisar/integrar o PR #1143 (hardening + `rag_status=pendente` obrigatório na ingestão + quarentena).
5. **[CURTO PRAZO] Corrigir o lote na fonte**: `gerado_por_IA: true` nos 24, confirmar ou remover cada bloco `NAO_CONFIRMADO`, corrigir Tema 1046→466/STJ + Súmula 479, `score_autoridade` do ambiental/07, e retificar `RELATORIO_AUDITORIA_LOTE_PILOTO.md` (o #1143 já cobre a maior parte).
6. **[MÉDIO PRAZO] Fechar o desvio de processo**: remover do `GUIA_EXECUCAO_PRODUCAO.md` as instruções de checkout/export de `.env` na VPS; tratar "merge local na VPS" como exceção registrada, não como procedimento; testes de regressão para os dois scripts.
7. **[HIGIENE] Excluir os ~50 workflows temporários** (`tmp-*`, `*-temp`, `_apply-*`, `format-*`) já desligados.

## 9. Riscos residuais e limitações

- **Não foi possível confirmar se a ingestão rodou em produção** (sem acesso ao banco de produção, por regra). A prioridade nº 1 depende dessa verificação humana.
- A causa exata do `startup_failure` (cota de minutos vs. outra restrição de billing) não é visível pela API com as credenciais da sessão — os sintomas (0 jobs, qualquer SHA, só em `ubuntu-latest`, `deploy-staging` self-hosted também sem jobs via `workflow_run`) apontam para billing/limite, mas a confirmação está em Settings → Billing do GitHub.
- A pilha GED (`#1133`/`#1134`) não foi inspecionada linha a linha nesta rodada; recomenda-se rodada dedicada de security-auditor se não houver evidência anexada nos PRs.
- Itens deste relatório que geram trabalho novo devem virar Issues próprias (regra 7); este relatório não corrige nada por si.
