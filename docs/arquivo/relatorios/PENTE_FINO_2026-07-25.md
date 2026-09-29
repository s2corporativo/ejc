# Pente fino EJC — 2026-07-25

Varredura completa em cinco frentes: backend, frontend, suítes de teste/lint,
segurança e estado do repositório. Todas as evidências verificadas em
arquivo:linha; nada foi alterado além deste relatório.

## Resumo executivo

| Frente | Resultado |
|---|---|
| Testes backend | **3390 passed, 132 skipped, 0 failed** (ruff: 0 erros) |
| Testes frontend | **198 passed, 0 failed** (tsc: 0 erros; build OK; prettier OK) |
| Segurança | **0 críticos, 0 altos** — 2 médios, 4 baixos novos |
| Backend (código) | 1 P0, 11 P1, ~20 P2 |
| Frontend (código) | 2 P0, ~20 P1, ~25 P2 |
| Git | Working tree limpo, sem stash, sem branch órfã |

O sistema compila, testa e linta limpo. Os problemas reais são de **código
desconectado** (construído e nunca ligado), **resíduos de migração** e
**divergências de nomenclatura** — não de código quebrado.

## P0 — críticos

### 1. Migrations 040–043 não existem no repositório

`backend/alembic/versions/044_recover_head.py` é um stub `pass` que apenas
reconecta o grafo 039→044. O próprio docstring admite: as migrations foram
aplicadas direto no container e perdidas quando ele foi recriado. O schema
existe só no volume `pgdata` de produção.

**Consequência:** `alembic upgrade head` em banco limpo (disaster recovery,
staging novo, ambiente de teste) **não reconstrói o schema**.
`053_reconcile_schema.py` compensa parte, mas sem garantia de cobertura total.

**Ação:** gerar uma migration de reconciliação completa a partir do schema real
de produção (`pg_dump --schema-only` vs. metadata) e testar `upgrade head` em
banco vazio no CI — o job `db-validation` já existe e deveria pegar isso.

### 2. `lib/aiCore.ts` — o cliente do Núcleo Único de IA tem zero consumidores

`frontend/src/lib/aiCore.ts:88-135` exporta 10 funções (`aiChat`, `aiTask`,
`aiAnalyze`…) que chamam `/ai/core/*`. Nenhum arquivo do frontend as importa.
`docs/ai/EJC_AI_ENDPOINT_MIGRATION_MATRIX.md:19` afirma que "todo consumo novo
de IA passa por ele" — a arquitetura documentada não está ligada. Enquanto
isso, 3 call sites ainda usam o endpoint legado `/ai/analisar-caso`
(`IA.tsx:98`, `TabResumo.tsx:391`, `SalaAnaliseJuridica.tsx:277`).

> **Desfecho (2026-07-27):** o arquivo foi removido em 1befdf0 (nunca teve
> consumidor) e a matriz de migração foi corrigida. O descompasso de fundo
> permanece: o núcleo `/api/ai/core/*` continua sem consumidor no frontend —
> registrado como pendência com dono a definir em
> `docs/HIGIENIZACAO_BACKLOG_FRONTEND.md`.

### 3. `SalaAnaliseJuridica.tsx:277-285` — contexto serializado dentro do prompt

A Sala empacota título, cliente, relatório documental e 12 mensagens via
`JSON.stringify` **dentro de `descricao_fatos`**, e envia `case_id: null`.
É o antipadrão "prompt montado no frontend" que a matriz de migração já
corrigiu em outros endpoints. O PR #475 migra esta chamada — confirma a
urgência de mergeá-lo.

## P1 — backend (código desconectado e resíduos)

| Achado | Evidência | Nota |
|---|---|---|
| `core/sql_safe.py` — hardening anti-SQLi com **zero** uso em app/ e tests/ | `sql_safe.py:59-85` | O SQL dinâmico atual usa whitelists locais (auditadas como seguras), mas o helper central nunca foi adotado |
| `services/pncp_service.py` lê 3 settings **deletadas** do config (`PNCP_ENABLED`, `PNCP_BASE_URL`, `PNCP_TIMEOUT_SECONDS`) | `pncp_service.py:223,267,269,308`; `config.py:371` | `AttributeError` garantido se alguém religar. Remover service+router (resíduo de licitações) |
| `routers/pncp.py` nunca registrado | `pncp.py:27` | Idem — remover |
| `routers/google_drive_knowledge.py` — 7 endpoints de curadoria Drive nunca montados | `google_drive_knowledge.py:29` | Import só por side-effect com `# noqa: F401`; frontend não chama. Decidir: registrar ou remover |
| `services/rag_juridico.py` — endpoint vivo devolvendo **501 fixo** | `rag_juridico.py:55` via `routers/rag.py:374` | Rota que só retorna erro; remover ou implementar |
| `services/ai/agent/permissions.py` — docstring diz ser "a fachada consultada pelo loop e pelo router"; **ninguém importa** | `permissions.py:6`; `loop.py:171` chama o REGISTRY direto | Sem falha funcional de HITL, mas induz auditoria ao erro |
| `services/ai_core_hardening_patch.py` — "correções transitórias" viraram monkeypatch permanente de startup | `ai_core_hardening_patch.py:4`; instalado em `event_subscribers.py:135` | Internalizar no núcleo |
| Duas implementações paralelas de Google Drive | `services/google_drive.py` (184L) × `services/google_drive_service.py` (829L) | Consumidores disjuntos; consolidar |
| Nomes de query param de APIs externas não confirmados | `transparencia_service.py:218`, `routers/car.py:34` — `TODO(verificar-vps)` | Integração pode retornar vazio silenciosamente |
| `peca_workflow_service.py` + `schemas/peca_workflow.py` órfãos | Já conhecido — Fase 2 do plano | Confirma o plano |
| 7 routers montados por side-effect/monkeypatch | `event_subscribers.py`, `*_patch.py` | Falha silenciosa no `instalar()` derruba rotas sem erro de boot |

## P1 — frontend

| Achado | Evidência |
|---|---|
| 5 arquivos de UI órfãos: `KnowledgeHub.tsx`, `Biblioteca.tsx`, `MemoriaInstitucional.tsx`, `Wiki.tsx`, `AssistedWritingMode.tsx` | Removidos do registry na consolidação 2026-07, código ficou |
| Aba "IA do Cliente (Análise 360º)" é cartão "Em breve" navegável | `DossieCliente.tsx:1439-1449` |
| Fallback "Aba em desenvolvimento" no switch de abas do caso | `CasoDetalhe.tsx:1200` |
| 4 rotas `/legado/*` inalcançáveis por navegação (prazos, tarefas, intimações, suspensões) | `moduleRegistry.tsx:435-480`; redirects antigos vão para `/atividades`, nunca para `/legado/*` |
| Guia do Sistema instrui telas **deletadas** (Biblioteca, Memória, KnowledgeHub) e menus inexistentes | `content/guiaSistema.ts:426-474,613`; fora da cobertura do `internalLinks.test.ts` (rotas chegam por variável) |
| `payloadLegado` descarta metadados ricos da Entrada Universal | `lib/api.ts:225-236` |
| 3 nomenclaturas divergentes para o workspace do caso — a barra canônica, a página e o `CaseCommandDock` (que ainda acrescenta um 6º destino "Peças") | `CaseContextBar.tsx` × `CasoDetalhe.tsx` × `CaseCommandDock.tsx:176-206` |
| "Pesquisa e IA" × "Inteligência Jurídica" — 3 superfícies divergem e 2 docstrings afirmam o contrário do que o código faz | `moduleRegistry.tsx:577,1051`; `HelpButton.tsx:21-32`; `InteligenciaWorkspace.tsx:162` |
| 4 nomes para a rota `/atividades` ("Agenda e Prazos", "Agenda, Prazos e Tarefas", "Central de Atividades", "Central") | `moduleRegistry.tsx:414`; `Central.tsx:20`; `guiaSistema.ts:227` |
| 578 `any` explícitos; top: `Documentos.tsx` (27), `TabResumo.tsx` (25), `RamoBase.tsx` (24), `Dashboards.tsx` (24 — em props públicas) | typecheck passa, mas o contrato não protege |

## Segurança (2 médios, 4 baixos — 0 críticos/altos)

| Sev. | Achado | Evidência |
|---|---|---|
| MÉDIO | `rag.py` `ingerir_pdf`: `file.read()` sem teto no app, sem magic bytes antes do OCR (mitigado pelo nginx 50m) | `routers/rag.py:185` |
| MÉDIO | `bank_analysis.py` upload: `client_id` do form persistido **sem gate de visibilidade** — advogado pode vincular análise bancária a cliente fora da carteira | `routers/bank_analysis.py:90` |
| BAIXO | `defesas_revisoes.py` e `analise_bancaria.py`: leitura sem teto no app | `defesas_revisoes.py:207`; `analise_bancaria.py:119` |
| BAIXO | `bank_analysis.py`: valida só extensão, sem magic bytes | `bank_analysis.py:51-56` |
| BAIXO | `signatures.py`: sem `verificar_acesso_caso` no criar; listagem office-wide expõe `hash_completo` a qualquer staff | `signatures.py:46-118` |

Limpos: allowlist pública justificada endpoint a endpoint, segredos (nenhum
literal, nenhum `.env` versionado), SQL injection (30+ sites de `text(f...)`
auditados — só fragmentos server-side com bind params), CORS/boot-validation
sem regressão, IDOR nos 15 routers sensíveis fora os 2 acima.

## Pendências operacionais (issues abertas — fora do código)

15 issues abertas; as estruturais: #471/#472/#473 (P0 da conversão da Sala —
**resolvidas pelo PR #475, que está aberto aguardando merge**), #411 (2FA
temporariamente desativado em produção — no código o default obriga
gestão+advogados; é pendência de `.env` da VPS), #441/#378 (backup sem
comprovação íntegra + reautorizar Drive), #454 (runner com `NOPASSWD:ALL`),
#452 (runner offline), #250 (exigir CI gate na main).

## Achado menor de CI

`pytest-timeout` não está em `requirements.txt` — o flag `--timeout` falha sem
instalação manual. Incluir se o CI padronizar.

## Leitura recomendada dos resultados

1. **Mergear #475** — fecha 3 P0 de issue e o P0 nº 3 deste relatório.
2. **Migration de reconciliação** (P0 nº 1) + teste de `upgrade head` em banco
   vazio no CI.
3. **Faxina de órfãos** — um PR só de remoção: `pncp*`, `sql_safe` (ou adotar),
   `google_drive_knowledge` (ou registrar), páginas órfãs do frontend,
   `rag_juridico` 501. Reduz superfície e falso sinal de capacidade.
4. **Correções de segurança médias** — gate de `client_id` no `bank_analysis`
   e teto+magic no `ingerir_pdf`. Pequenas, valem PR próprio.
5. **Guia do Sistema e nomenclatura** — atualizar `guiaSistema.ts` e unificar
   os rótulos (entra natural na Fase 1 do plano de simplificação).
6. Os itens `peca_workflow` (Fase 2) e `sala_de_guerra_v3` (Fase 3) já estão
   no plano — este pente fino os confirma.
