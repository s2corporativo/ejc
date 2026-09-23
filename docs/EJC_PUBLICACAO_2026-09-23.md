# EJC — Publicação 2026-09-23

**Data:** 23/09/2026
**Sessão:** Consolidação e release candidato único
**Status:** EM TESTE → homologação em VPS → produção

## TL;DR

| Item | Estado |
|---|---|
| Repositório consolidado | `release/ejc-publicacao-2026-09-23` baseada em `origin/main@16bdb03e` |
| VPS atual em produção | `0bb8c62d` (1 commit atrás de origin/main) |
| Versão alvo em produção | `1eb2492b` (cabeça da branch de release) |
| PRs abertas contra main | 0 funcionais — 3 draft de segurança/RAG foram fechadas e movidas para backlog |
| PRs incorporadas ao release | #1818 (assistente de casos), #1820 (auditor de licitações), #1822 (W8.2 IA assíncrona — já estava em main) |
| Migration pendente | Nenhuma nova (PRs adicionaram só código + testes). Head atual = `161_fee_estornos`. |
| Backend lint | OK (`ruff check app`) |
| Frontend build + testes | OK (814 testes, 152 arquivos) |
| Homologação em produção | Pendente — titular libera SSH |

## O que foi feito nesta sessão

### 1. Fotografia inicial
- `main` = `bb5b8ac9` no momento do início; avançou para `16bdb03e` (merge automático da #1822 W8.2 IA assíncrona).
- VPS rodando `0bb8c62d` — alinhada com origin/main a menos do merge recém-chegado.
- 6 PRs abertas contra main no início: 4 não-draft (novas funcionalidades) + 3 draft (segurança/RAG).
- 23 itens do plano-mestre em produção, 51 pendentes, status canônico em `docs/PLANO_MESTRE_STATUS.md`.

### 2. Decisões do titular (nesta sessão)

| Decisão | Resultado |
|---|---|
| Versão-alvo da publicação | **PUBLICAR o que está na main** com merges pontuais das 2 PRs pequenas funcionais |
| Acesso VPS | Liberado SSH + `.env` |
| PRs novas (#1818 + #1820) | **Homologar e mergear** antes da publicação |
| PRs segurança (#1816 + #1794 + #1751) | **Manter em draft, fechar sem merge** e mover para backlog |

### 3. Ações executadas

| # | Ação | SHA | Arquivos |
|---|---|---|---|
| 1 | Branch `release/ejc-publicacao-2026-09-23` a partir de `origin/main` | `16bdb03e` | — |
| 2 | Merge #1818 (assistente de casos + detector de prazos) | `2cc2a92b` | +123/-1 em 2 arquivos |
| 3 | Merge #1820 (auditor stateless de licitações) | `1eb2492b` | +125/-0 em 2 arquivos |
| 4 | Fechar #1816 (binding/auditoria plaintext) | — | mover para backlog |
| 5 | Fechar #1794 (pesquisa jurídica pública) | — | mover para backlog |
| 6 | Fechar #1751 (RAG hardening LGPD) | — | mover para backlog |

**Total adicionado:** 246 linhas em 4 arquivos. **Sem migrations novas** (a W8.2 já estava em main e não mexia em schema).

## PRs fechadas / movidas para backlog

- **#1816** `test(security): consolidar binding e auditoria plaintext` — manter em draft; ciclo futuro.
- **#1794** `feat: ativar pesquisa jurídica pública com gates de segurança` — manter em draft.
- **#1751** `fix(rag): hardening LGPD final sobre main consolidada` — manter em draft.

Justificativa unificada: a missão atual é **estabilizar e publicar**; incorporar hardening extra sem homologar aumenta superfície de regressão sem retorno operacional imediato.

## PRs incorporadas (resumo)

### #1822 — W8.2 IA assíncrona (já estava em main)
- 10 arquivos, +355/-2.
- `POST /ai/analisar-caso/async` + polling; **flag-gated, default OFF** (`IA_ANALISE_ASYNC_ENABLED=false`).
- Store em memória com TTL — substituir por Redis/Celery antes de ativar a flag em multi-worker.
- 6 testes pytest (idempotência, ownership, 422/404/409).

### #1818 — Assistente de casos
- 2 arquivos, +121/-1.
- `POST /assistente/cases/{id}/chat` (chat multi-turn contexto do caso, sanitizado PII).
- `POST /assistente/detectar-prazos` (Groq via ai_gateway).
- HITL: toda saída marcada como rascunho.

### #1820 — Auditor de propostas de licitações
- 2 arquivos, +125/-0.
- `POST /licitacao-auditoria/analyze-competitor-proposal` (upload PDF + análise via fitz/PyMuPDF).
- `GET /licitacao-auditoria/audit-report-template`.
- Análise determinística — revisão do advogado obrigatória.

## Pendências para a fase de homologação

1. **Homologar na VPS**:
   - `bash scripts/deploy_manual.sh --sha 1eb2492b --dry-run` (pré-voo sem mutação).
   - Conferir logs do pré-voo (workspace, /opt/ejc, ejc_db, sudo -n).
   - Se OK: `bash scripts/deploy_manual.sh --sha 1eb2492b` (deploy real).
   - Aguardar healthcheck (`/api/health`) retornar SHA `1eb2492b`.

2. **Smoke test** (manual ou via curl):
   - `GET /api/health` (200, SHA correto)
   - `POST /api/auth/login` com credencial real do `.env`
   - `GET /api/cases/` (lista não-vazia de casos ou vazio estruturado)
   - `GET /api/dashboard/` (números coerentes)
   - `POST /api/assistente/cases/{id}/chat` (sanitização HITL)
   - `POST /api/licitacao-auditoria/analyze-competitor-proposal` (se aplicável)
   - `POST /api/ai/analisar-caso` (síncrono, inalterado)

3. **Confirmar que dados persistidos**:
   - Cliente novo → Caso → Documento → fluxo mínimo ponta a ponta.

4. **Rollback preparado**:
   - Imagem anterior da VPS: já documentada em relatório anterior.
   - `deploy_vps_safe.sh` preserva backup.

## Próxima ação concreta

**Titular:** rodar o deploy manual dry-run e real na VPS, conforme `RUNBOOK_DEPLOY_MANUAL.md`:
```bash
cd /opt/ejc-deploy-src
git fetch origin && git checkout release/ejc-publicacao-2026-09-23
bash scripts/deploy_manual.sh --sha 1eb2492b --dry-run
bash scripts/deploy_manual.sh --sha 1eb2492b
```
Confirmar com `/api/health` retornando SHA `1eb2492b` e reportar.

## O que NÃO muda nesta publicação

- Política de IA canônica (`FD-IA-2024-01` etc.) — mantida.
- HIStórico de PRs já mergeadas — integralmente preservado em `origin/main`.
- Tags oficiais Git — esta publicação **não cria tag oficial** (decisão: a `release/` branch é o release candidato; tag só após smoke test pós-deploy confirmado).
- Issues de backlog — ficam como antes (plano-mestre é a fonte da verdade).
