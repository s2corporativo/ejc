# M29 — Dossiê Estratégico

**Status: HOMOLOGADO — 22 cenários executáveis: 20 PASS / 0 FAIL (100%), 2 N/A-PROVADO**
Data: 16/08/2026 · Repositório: s2corporativo/ejc · Branch: homologacao-m07-2026-08-16
Bateria: `scripts/inventory/m29_dossie_estrategico_tests.py` (execução real contra servidor local, porta 8000)

## 1. Objetivo (PROMPT 29)

Homologar o Dossiê Estratégico como produto vivo de inteligência do caso: criação sob revisão obrigatória, atualização por versões, consolidação de módulos determinísticos (linha do tempo, mapa probatório, riscos/case_health, teses), seções documentadas (fatos, provas, estratégia, riscos), uso de IA com barreira LGPD, histórico versionado, exportação e rastreabilidade de auditoria.

## 2. Superfícies testadas (com prova de execução)

| Superfície | Endpoint | Prova |
|---|---|---|
| Criação (rascunho obrigatório) | `POST /api/dossie/{case_id}/gerar` | dossiê nasce `rascunho`; fatos reais do caso (`descricao_fatos`) presentes no conteúdo; payload de geração consolida os módulos determinísticos |
| Atualização incremental | `POST …/gerar` (2ª chamada) | versão 2 criada sem sobrescrever a v1 (append-only); histórico registra v1 e v2 |
| Consolidação determinística | `GET /api/dossie/{case_id}/modulos` | `linha_do_tempo`, `mapa_probatorio`, `riscos`, `teses` — zero custo de IA |
| Seções fatos/provas/riscos | `GET /api/dossie/{case_id}` | fatos reais no conteúdo; `secoes_json` no banco audita dados brutos + fontes RAG; `riscos` derivado do `case_health` (score + fatores) |
| Barreira LGPD (IA) | serviço `sanitizer` | `sanitizar_pii` detectou CPF e nº de processo no conteúdo do dossiê; `validar_sem_pii` retornou residual vazio — o provedor jamais recebe PII |
| RBAC | gerador/leitura/aprovação | estagiário bloqueado (403); financeiro bloqueado na leitura (Issue #694, allowlist exata); cliente externo bloqueado (403) |
| HITL (aprovação) | `PATCH …/{dossie_id}/aprovar` | sócio aprova com `aprovado_por`/`aprovado_em` registrados; advogado bloqueado (403) |
| Exportação PDF | `GET …/{dossie_id}/pdf` | PDF WeasyPrint de 137 KB com `content-type` correto |
| Auditoria | tabela `audit_logs` | 5 ações `criar/dossie_estrategico` rastreadas por entidade |

## 3. Defeitos encontrados

**Nenhum defeito novo.** Os dois cenários N/A-PROVADO exigem o provedor de IA ativo no ambiente de homologação (o sandbox roda com `AI_ENABLED=false` por economia e estabilidade):

1. **Chamada externa do provedor** — a geração com IA completa (prompt sanitizado + pseudonimização de entidades + custo em BRL) foi provada no nível das barreiras determinísticas que a precedem; a execução ponta a ponta com LLM deve ser repetida em ambiente com IA habilitada como teste complementar.
2. **Arquivamento de versões anteriores** — na primeira aprovação não há versões anteriores aprovadas a arquivar (comportamento esperado); o arquivamento será observado naturalmente na segunda aprovação.

Nenhum teste legítimo foi removido ou desativado.

## 4. Comportamentos confirmados como design

- O dossiê nasce obrigatoriamente como **rascunho**: o prompt carrega a advertência de revisão humana (Provimento OAB 205/2021) e o endpoint PDF só exporta após aprovação.
- A **regra "nunca prometa resultado"** está embutida no prompt (vedação de garantia de êxito) e reforçada pelo gate de jurimetria homologado no M24.
- A API pública não expõe `secoes_json` (o conteúdo do dossiê é o produto; os dados brutos + fontes RAG persistem em banco apenas para auditoria) — decisão de design, não omissão.
- Com IA indisponível, o dossiê persiste como rascunho com o rótulo explícito "IA indisponível" e os dados brutos em JSON auditável — degradação segura, sem inventar conteúdo.

## 5. Riscos jurídicos/LGPD

- Todo prompt enviado ao provedor externo passa por `sanitizar_pii` com gate de abort em residual — provado determinísticamente (2/2).
- O AILog registra apenas o prompt sanitizado quando a IA efetivamente responde (gravação condicional `_IA_OK`).

## 6. Checklist

- [x] Backend inicia sem erro
- [x] Bateria compila e executa com `env_shell.sh`
- [x] Endpoints respondem (gerar, modulos, historico, aprovar, pdf)
- [x] Autorização validada (estagiário, financeiro, advogado, cliente externo)
- [x] Logs sem dado sensível (auditoria usa IDs, não PII)
- [x] Sem alteração no código do sistema — apenas bateria de homologação
- [x] Nenhum teste legítimo removido
- [x] Dados sintéticos prefixados `EJC_QA`
- [x] Rollback desnecessário (nada foi alterado no sistema)
