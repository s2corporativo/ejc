# AUDIT_FIXES — Correção da Auditoria Funcional EJC (01/07/2026)

Rastreamento da correção dos 24 bugs identificados na Auditoria Funcional EJC.
Ambiente: backend FastAPI · frontend React/TS/Tailwind · PostgreSQL (pgvector) · Docker · VPS `13.140.167.153`.

Legenda de status: ⬜ pendente · 🟡 em andamento · ✅ código pronto · 🚀 aplicado em produção · ⛔ bloqueado (requer confirmação)

## Convenções de segurança adotadas
- **Banco de produção**: todo script SQL/migração é escrito e versionado; a execução em produção só ocorre após **backup (`pg_dump`)** e é registrada aqui.
- **DELETE físico**: nunca executado sem confirmação dupla e explícita. Preferência por *soft delete*/inativação.
- **Git**: commits semânticos por grupo; push em `main` conforme autorizado.

---

## GRUPO 1 — CRÍTICOS
| ID | Descrição | Status | Notas |
|----|-----------|--------|-------|
| BUG-01 | Aba "Societária" — tela branca (crash React) + ErrorBoundary | ⬜ | frontend |
| BUG-02 | Sala de Guerra — `[object Object]` em Fatores de Risco | ⬜ | front+shape backend |
| BUG-03 | Título de caso com JSON bruto da IA (DPT-2026-0013) | ⬜ | backend + fix dado |
| BUG-04 | Base RAG — 5.009 documentos "sem_vetor" | ⬜ | script + rodar na VPS |
| BUG-05 | Botão WhatsApp redireciona para `/` | ⬜ | frontend/rota |

## GRUPO 2 — ALTOS
| ID | Descrição | Status | Notas |
|----|-----------|--------|-------|
| BUG-06 | Contagem inconsistente de casos | ⬜ | endpoint stats unificado |
| BUG-07 | Taxa de conversão = 10000% (div/0) | ⬜ | back+front |
| BUG-08 | HITL 0% — fluxo formal de aprovação de peças IA | ⬜ | migração + endpoints + UI |
| BUG-09 | Perfis duplicados "Clóvis José Soares" | ⬜ | dedup + unique constraint |
| BUG-10 | Gráfico de áreas omite caso Trabalhista | ⬜ | junto de BUG-06 |

## GRUPO 3 — MÉDIOS
| ID | Descrição | Status | Notas |
|----|-----------|--------|-------|
| BUG-11 | Sala de Guerra sem rota no menu lateral | ⬜ | sidebar |
| BUG-12 | Despesas recorrentes R$0,00 — validação | ⬜ | form |
| BUG-13 | Dados de teste em produção | ⬜ | script UPDATE (arquivar) |
| BUG-14 | Casos encerrados sem mensagem ao adicionar | ⬜ | frontend |
| BUG-15 | IA "Gerar teses" — loading infinito | ⬜ | timeout 30s |
| BUG-16 | Prazos não importam do DataJud | ⬜ | serviço sync |
| BUG-17 | Intimações sem status/timestamp de captura | ⬜ | endpoint + UI |

## GRUPO 4 — BAIXOS / UX
| ID | Descrição | Status | Notas |
|----|-----------|--------|-------|
| BUG-18 | Documento "ddd" | ⬜ | via BUG-13 |
| BUG-19 | "1 cadastrados" — concordância | ⬜ | frontend |
| BUG-20 | Nome de responsável truncado | ⬜ | tooltip |
| BUG-21 | Numeração de casos com lacunas — soft delete | ⬜ | migração + código |
| BUG-22 | Modelo IA com/sem prefixo "groq/" | ⬜ | logger |
| BUG-23 | Botões de ícone sem aria-label (Atividades) | ⬜ | a11y |
| BUG-24 | Clientes sem deep link | ⬜ | rota |

---

## Recon produção (read-only) — 2026-07-01
- **BUG-02**: `cases.risco_fatores` é `jsonb` e vem como objeto vazio `{}` → frontend faz `String({})` = `[object Object]`. Fix no render (tratar objeto/vazio).
- **BUG-03**: apenas `DPT-2026-0013` tem título com ```json bruto. Correção pontual de dado.
- **BUG-04**: **reclassificado**. `knowledge_docs`=5022; `status_indexacao`: pendente=4886, indexado=136. `knowledge_chunks`=17967, **0 embeddings nulos**; TODOS os 5022 docs já têm chunk embeddado. Ou seja, a vetorização já ocorreu — o flag `status_indexacao` é que ficou obsoleto. Fix real = reconciliar status (UPDATE barato) + corrigir pipeline para marcar `indexado`. **Não** re-embedar 5k docs.
- **BUG-06**: inconsistência vem de filtro `deleted_at` inconsistente. `cases`=14 linhas, 9 com `deleted_at IS NULL`. Status(todas): triagem=8, encerrado=6. Área(todas): civil=11, trabalhista=2, ambiental=1 (trabalhista existe → BUG-10 é filtro no gráfico).
- **BUG-09**: `users` **não tem coluna cpf**. Nome = `full_name`. Dois "Clóvis" com emails distintos: `f23aeeb8…` (clovis@) e `af6e457a…` (admin@). Merge é manual; unique só em `email`.
- **BUG-13/18**: casos de teste = `DPT-2026-0001..0010` e `0014` (11 casos); doc `ddd` id `743ea7cb…`. ⚠️ maioria dos casos é teste → arquivar exige confirmação explícita.
- **BUG-21**: `cases.deleted_at` já existe (soft-delete parcial). Reusar; adicionar só `excluido_motivo`/`excluido_por`.
- **BUG-12**: `office_expenses` com valor 0/null = 30 (contexto; fix é validação no form).

## Log de execução
- 2026-07-01 — Início. Ambiente mapeado; SSH VPS OK; DB produção = container `ejc_db` (pgvector pg16). Tracker criado.
- 2026-07-01 — Agentes de código (frontend + backend) despachados em paralelo. Recon read-only de produção concluído (acima). Backend agent corrigido quanto a BUG-04/09/21 via mensagem.
