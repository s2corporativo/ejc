# Plano-Mestre EJC — Status Canônico

Esta tabela é a **única** fonte de status de todo o backlog de correção, consolidação e
padronização do EJC. Nenhum outro documento é atualizado com status a partir de agora —
`docs/auditoria/plano-correcao-v2.md`, `docs/auditoria/plano-lancamento-v3.md` e
`docs/estrategia/EVOLUCAO_ESTRATEGICA_EJC.md` continuam valendo como *descrição* dos
achados, mas o campo "resolvido/pendente" vive só aqui.

Desenho completo (fases, trilha do titular, ordem de execução, riscos):
`docs/estrategia/PLANO_MESTRE_EJC.md`.

## Como este arquivo é mantido

- Formato de tabela, verificável por máquina (`scripts/status_check.sh`, chamado por
  `scripts/ci-local.sh required`).
- **O PR que fecha um item flipa a linha correspondente no mesmo PR** — nunca em PR
  separado, nunca só na descrição do PR. Regra espelhada em
  `docs/engineering/DEFINITION_OF_DONE.md`.
- Enum fechado de `status`: `pendente` → `em-andamento` → `mesclado` → `em-prod` →
  `verificado`. `mesclado` ≠ `em-prod`: o EJC roda deploy manual em lote enquanto a cota
  do Actions estiver esgotada (ver `RUNBOOK_DEPLOY_MANUAL.md`), então "está na `main`" não
  significa "está em produção". `verificado` só depois de conferência real pós-deploy —
  nunca marque um item como pronto só porque o código foi escrito.
- Todo item com `status` em `mesclado` ou mais avançado precisa de `PR` preenchido
  (`scripts/status_check.sh` reprova o contrário).
- `ID` é estável e nunca reaproveitado. Prefixos: `V2-` (achados de
  `plano-correcao-v2.md`), `V3-B` (blocos de `plano-lancamento-v3.md`), `CL-` (classes de
  inconsistência estrutural, Eixo 2), `CORTE-` (remoção de módulo, Eixo 3), `INFRA-`
  (esteira/deploy/processo).

## Tabela

| ID | Descrição | Fase | Issue | Status | PR | Data |
|---|---|---|---|---|---|---|
| INFRA-1 | Checklist-mestre (este arquivo) + `status_check.sh` no gate local | F0 | — | em-andamento | — | 2026-08-24 |
| INFRA-2 | Banner de descontinuação de status nos docs legados + correção final ✅/🟡 (frentes 2, 11, 12) | F0 | — | em-andamento | — | — |
| INFRA-3 | Pauta de decisões do titular (`docs/PAUTA_DECISOES_TITULAR.md`) | F0 | — | em-andamento | — | — |
| INFRA-4 | Ensaio `--dry-run` do deploy manual + backup/downgrade verificados em staging | F0 | — | pendente | — | — |
| INFRA-T1 | Titular: revisar/mesclar PR #1259 e autorizar 1º deploy manual (migrations 127–147) | F0 (gate) | #1258 | pendente | #1259 | — |
| INFRA-T2 | Titular: regularizar cota GitHub Actions + reativar `auto-integracao.yml`, `continuity-ui-gates.yml`, `architecture-inventory.yml` | F6 (gate) | — | pendente | — | — |
| V2-0.1 | Prazo vencendo hoje, sem ciência confirmada | F1 | — | pendente | — | — |
| V2-0.2 | Captura de intimações (DJEN) nunca capturou nada `[CRÍTICO]` | F1 | — | pendente | — | — |
| V2-1.1 | Dashboard "0 peças aguardando revisão" com 100% em rascunho `[CRÍTICO]` | F1 | — | pendente | — | — |
| V2-1.2 | Contador de casos ativos conta o arquivado (bug em `dossie_cliente.py:140`) | F1 | — | pendente | — | — |
| V2-1.3 | Filtro de status quebra o servidor ou retorna vazio | F1 | — | pendente | — | — |
| V2-1.4 | Mensagem falsa "A equipe foi notificada" | F1 | — | pendente | — | — |
| V2-1.5 | Rotas retornando 404 | F1 | — | pendente | — | — |
| V2-2.1 | Vínculo de validação (`ai_log_id`) que trava as peças antes do protocolo `[CRÍTICO]` | F1 | — | pendente | — | — |
| V2-2.2 | Embeddings desligados: 0 de 47.359 chunks indexados `[CRÍTICO]` | F3 | — | pendente | — | — |
| V2-2.3 | Modelo local para dados pessoais `[CRÍTICO]` | F3 | — | pendente | — | — |
| V2-2.4 | Consolidar aprovação da peça em um único ato | F1 | — | pendente | — | — |
| V2-3.1 | Monitorar resultado, não apenas execução (generalizar) `[CRÍTICO]` | F3 | — | pendente | — | — |
| V2-3.2 | Fontes de ingestão dormentes ou silenciosas | F3 | — | pendente | — | — |
| V2-3.3 | Exclusão de caso não cascateia | F5 | — | pendente | — | — |
| V2-3.4 | Vínculos ausentes entre registros relacionados | F5 | — | pendente | — | — |
| V2-3.5 | Padrão de gravação não transacional (agregado do Caso) | F5 | — | pendente | — | — |
| V2-3.6 | Conversão Sala Jurídica → Caso perde `descricao_fatos` | F5 | — | pendente | — | — |
| V2-4.1 | Conta `homolog.qa` com privilégio superadmin em produção `[CRÍTICO]` | F3 | — | pendente | — | — |
| V2-4.2 | Métrica de "chance de êxito" — risco OAB art. 34, XXIX `[CRÍTICO]` | F3 | — | pendente | — | — |
| V2-4.3 | Citação normativa incorreta na interface | F3 | — | pendente | — | — |
| V2-4.4 | Ausência de exclusão definitiva (LGPD) | F3 | — | pendente | — | — |
| V2-5.1 | Quinze calculadoras jurídicas sem interface `[ALTO — maior ganho rápido]` | F3 | — | pendente | — | — |
| V2-5.2 | Curadoria da base de conhecimento `[ALTO — trabalho contínuo]` | T5 | — | pendente | — | — |
| V2-5.3 | Higiene da base RAG | F3 | — | pendente | — | — |
| V2-5.4 | Erro jurídico recorrente nas skills (decadência, CPC art. 487, II) | — | — | **verificado** | #1015 | 2026-08-22 |
| V2-5.5 | Camada de IA da extração de documentos indisponível | F3 | — | pendente | — | — |
| V2-6.1 | Prefixo `/v1/` duplicado | F5 | — | pendente | — | — |
| V2-6.2 | Observabilidade | F5 | — | pendente | — | — |
| V2-6.3 | Painéis de diagnóstico divergentes | F5 | — | pendente | — | — |
| V2-6.4 | Superfície de API duplicada | F5 | — | pendente | — | — |
| V2-6.5 | Rotas órfãs e mapa incompleto (211 de 453 rotas nunca chamadas) | F5 | — | pendente | — | — |
| V2-6.6 | Taxonomia de áreas duplicada (4 manifestações) | F5 | — | pendente | — | — |
| V2-6.7 | Itens menores (9 subitens: acessibilidade, paletas, i18n, cadastros vazios etc.) | F5 | — | pendente | — | — |
| V3-B1 | Bloco 1 — Fazer o sistema dizer a verdade | F1 | — | em-andamento | — | — |
| V3-B2 | Bloco 2 — Desobstruir o caminho (pipeline da peça) | F1 | — | pendente | — | — |
| V3-B3 | Bloco 3 — Encurtar o caminho (redesenho: caso como espaço de trabalho) | F5 | — | pendente | — | — |
| V3-B4 | Bloco 4 — Enxugar (34 → 10–12 módulos) | F5 | — | pendente | — | — |
| V3-B5 | Bloco 5 — Não perder prazo (monitorar resultado, destravar DJEN) | F1 | — | pendente | — | — |
| V3-B6 | Bloco 6 — Preparar os dados da operação (10 cadastros pré-operação) | F4 | — | pendente | — | — |
| V3-B7 | Bloco 7 — O teste do primeiro caso real (critério de lançamento) | F4 | — | pendente | — | — |
| CL-A1 | Classe A passo 1 — write-path único (`aprovar_tese`/`tese_aprovada_do_caso`) | F2 | — | pendente | — | — |
| CL-A2 | Classe A passo 2 — migration de backfill (candidates aprovados sem link) | F2 | — | pendente | — | — |
| CL-A3 | Classe A passo 3 — unificar leitores (`conversao_caso.py`, `legal_case_orchestrator.py`) | F2 | — | pendente | — | — |
| CL-A4 | Classe A passo 4 — congelar `cases.tese_principal` como campo exibicional | F2 | — | pendente | — | — |
| CL-A5 | Classe A passo 5 — remover `teses_juridicas_v4` / `teses_vitoriosas` | F5 | — | pendente | — | — |
| CL-B1 | Classe B — expurgar chaves fantasma de `UI.tsx` (`STATUS_REGISTRY`/`LEGACY_STATUS_TONE`) | F2 | — | pendente | — | — |
| CL-B2 | Classe B — grep-test de paridade de status (impede literal fora da fonte canônica) | F2 | — | pendente | — | — |
| CL-B3 | Classe B — preservar estado ao desarquivar (`status_anterior`) | F2 | — | pendente | — | — |
| CL-C1 | Classe C — deprecar/remover campo `saudavel` do contrato de `case_health.py` | F2 | — | pendente | — | — |
| CL-C2 | Classe C — unificar limiares (`health_thresholds.py`, par com `visual_law_core.py`) | F2 | — | pendente | — | — |
| CL-D1 | Classe D — "Documentos lidos" exige documento processado, não só `descricao_fatos` | F2 | — | pendente | — | — |
| CL-D2 | Classe D — ponte `case_checklists` → etapa `checklist_criado` + golden test das 16 etapas | F2 | — | pendente | — | — |
| CORTE-1 | Cortar jurimetria / predição de êxito | F5 | — | pendente | — | — |
| CORTE-2 | Remover código de `diplomacia-v3` (risco disciplinar) | F5 | — | pendente | — | — |
| CORTE-3 | Cortar Victory Vault | F5 | — | pendente | — | — |
| CORTE-4 | Cortar radar de notícias / `/noticias` | F5 | — | pendente | — | — |
| CORTE-5 | Cortar módulo sociedade / retiradas de sócio | F5 | — | pendente | — | — |
| CORTE-6 | Arquivar skills de IA sem uso registrado em log | F5 | — | pendente | — | — |
| CORTE-7 | Desmontar `UI.tsx` (1437 linhas) em `components/ui/*` + consolidar 8 CSS globais | F5 | — | pendente | — | — |

## Placar por fase (derivado — não editar à mão, `status_check.sh` recalcula na saída)

Ver saída de `scripts/status_check.sh --resumo`.
