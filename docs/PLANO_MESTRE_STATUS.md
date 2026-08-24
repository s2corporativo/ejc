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
| INFRA-1 | Checklist-mestre (este arquivo) + `status_check.sh` no gate local | F0 | #1272 | em-andamento | #1259 | 2026-08-24 |
| INFRA-2 | Banner de descontinuação de status nos docs legados + correção final ✅/🟡 (frentes 2, 11, 12) | F0 | #1272 | em-andamento | #1259 | 2026-08-24 |
| INFRA-3 | Pauta de decisões do titular (`docs/PAUTA_DECISOES_TITULAR.md`) | F0 | #1272 | em-andamento | #1259 | 2026-08-24 |
| INFRA-4 | Ensaio `--dry-run` do deploy manual + backup/downgrade verificados em staging | F0 | — | pendente | — | — |
| INFRA-T1 | Titular: revisar/mesclar PR #1259 e autorizar 1º deploy manual (migrations 127–147) | F0 (gate) | #1258 | pendente | #1259 | — |
| INFRA-T2 | Titular: regularizar cota GitHub Actions + reativar `auto-integracao.yml`, `continuity-ui-gates.yml`, `architecture-inventory.yml` | F6 (gate) | — | pendente | — | — |
| V2-0.1 | Prazo vencendo hoje, sem ciência confirmada | F1 | — | pendente | — | — |
| V2-0.2 | Captura DJEN — código verificado OK (por advogado, monitorado por resultado, autoatendimento de OAB); resta só cadastro real das OABs (ver V3-B6) | F1 | — | mesclado | #1015 | 2026-08-14 |
| V2-1.1 | Dashboard "0 peças aguardando revisão" com 100% em rascunho `[CRÍTICO]` | F1 | — | mesclado | #1015 | 2026-08-14 |
| V2-1.2 | Contador de casos ativos conta o arquivado (bug em `dossie_cliente.py:140`) | F1 | #1272 | em-andamento | #1259 | 2026-08-24 |
| V2-1.3 | Filtro de status quebra o servidor ou retorna vazio | F1 | #1272 | em-andamento | #1259 | 2026-08-24 |
| V2-1.4 | Mensagem falsa "A equipe foi notificada" | F1 | — | mesclado | #1015 | 2026-08-14 |
| V2-1.5 | Rotas retornando 404 | F1 | — | pendente | — | — |
| V2-2.1 | Vínculo de validação (`ai_log_id`) que trava as peças antes do protocolo `[CRÍTICO]` | F1 | — | mesclado | #1015 | 2026-08-14 |
| V2-2.2 | Embeddings 0/47.359 — investigado (2026-08-24): NÃO é pipeline quebrado; código (self-heal `reembed_rag_orfaos` + script idempotente) já mesclado desde #1015, default `EMBEDDINGS_ENABLED=true`; produção sobrescreve a flag para `false` no `.env` do VPS. Execução é ação do titular (T4 na pauta) `[CRÍTICO]` | F3 | — | mesclado | #1015 | 2026-08-14 |
| V2-2.3 | Modelo local para dados pessoais — já resolvido (`sanitization_policy.py`, modo LOCAL_COMPLETO bloqueia provedor externo); 305 testes passam | F3 | — | mesclado | #1195 | 2026-08-18 |
| V2-2.4 | Consolidar aprovação da peça em um único ato | F1 | — | mesclado | #1153 | 2026-08-18 |
| V2-3.1 | Monitorar resultado, não apenas execução — já generalizado (`ingestao_saude.py`, não só DOU/DJEN) | F3 | — | mesclado | #1015 | 2026-08-14 |
| V2-3.2 | Falso-ausente (2026-08-24) — já resolvido: `ingestao_saude.py` classifica `nunca_produziu`/`parou_de_produzir` por RESULTADO (não confia no `status="sucesso"` do job), `executar_ingestao`/`conhecimento_ingest` garantem `ultimo_erro` nunca vazio (caso `anpd` citado no próprio código), slugs duplicados `juris_import_*` consolidados (migration 138); 27 testes passam | F3 | — | mesclado | #1015 | 2026-08-14 |
| V2-3.3 | Exclusão de caso não cascateia | F5 | — | pendente | — | — |
| V2-3.4 | Vínculos ausentes entre registros relacionados | F5 | — | pendente | — | — |
| V2-3.5 | Padrão de gravação não transacional (agregado do Caso) | F5 | — | pendente | — | — |
| V2-3.6 | Conversão Sala Jurídica → Caso perde `descricao_fatos` | F5 | — | pendente | — | — |
| V2-4.1 | Código já pronto e testado (guard de produção em `run_fictitious_smoke.py`, script `purga_dados_homologacao.py` com desativação de conta); execução em produção é ação do titular (governança §9 me veda acesso) | F3 | — | mesclado | #1015 | 2026-08-14 |
| V2-4.2 | Métrica de "chance de êxito" — decisão D4 (Opção 1): removida da UI da Entrevista Inteligente; API mantém o campo, tipado com nota de não-reintrodução; confirmado que nenhuma rota `/portal/*` a serializa `[CRÍTICO]` | F3 | #1272 | em-andamento | #1259 | 2026-08-24 |
| V2-4.3 | Investigado (2026-08-24, decisão D5): "OAB Prov. 205/2021" citado como base do HITL em ~25 arquivos (prompts de IA + testes), confirmado incorreto (é sobre publicidade); substituição sugerida pela auditoria (CNJ 615/2025) também não se sustenta (regula o Judiciário, não a advocacia) — precisa de advogado real antes de aplicar | F3 | — | pendente | — | — |
| V2-4.4 | `POST /trash/{entidade}/{id}/purgar` — hard delete real, superadmin-only, motivo obrigatório, audit log WORM, sem cascata automática; revisado por security-auditor (RBAC/IDOR/PII ok; TOCTOU corrigido com `with_for_update`) | F3 | #1272 | em-andamento | #1259 | 2026-08-24 |
| V2-5.1 | Quinze calculadoras jurídicas sem interface `[ALTO — maior ganho rápido]` | F3 | — | pendente | — | — |
| V2-5.2 | Curadoria da base de conhecimento `[ALTO — trabalho contínuo]` | T5 | — | pendente | — | — |
| V2-5.3 | Higiene é curadoria contínua (T5, titular). `[INVESTIGAR]` do hash de duplicidade fechado (2026-08-24): `hash_conteudo` é SHA-1 do conteúdo NORMALIZADO INTEIRO (`ingestion_service.py::normalizar`+`_sha1`), sem truncar — descarta "trecho insuficientemente específico"; colisão entre acórdãos com processo distinto só se explica por `conteudo` quase idêntico gravado pelo scraper STJ (stub/boilerplate), que só se confirma inspecionando os 3 documentos reais em produção (fora do meu acesso, governança §9) | F3/T5 | — | pendente | — | — |
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
| V3-B5 | Bloco 5 — Não perder prazo — código pronto e testado; resta cadastro de OAB (V3-B6, T4) | F1 | — | mesclado | #1015 | 2026-08-14 |
| V3-B6 | Bloco 6 — Preparar os dados da operação (10 cadastros pré-operação) | F4 | — | pendente | — | — |
| V3-B7 | Bloco 7 — O teste do primeiro caso real (critério de lançamento) | F4 | — | pendente | — | — |
| CL-A1 | Classe A passo 1 — write-path único (`vincular_tese_ao_caso`, usado por `/vincular-caso` e `aprovar_tese`) | F2 | #1272 | em-andamento | #1259 | 2026-08-24 |
| CL-A2 | Classe A passo 2 — coluna `tese_banco_id` (migration 149); SEM backfill retroativo (mapeamento só existia em memória, não é reconstruível com confiança) | F2 | #1272 | em-andamento | #1259 | 2026-08-24 |
| CL-A3 | Classe A passo 3 — ponte na aprovação materializa `tese_caso_links`; os dois leitores concordam no caminho comum (tese do Banco) — testado | F2 | #1272 | em-andamento | #1259 | 2026-08-24 |
| CL-A4 | Classe A passo 4 — já é campo exibicional de fato (só a triagem escreve; nenhum novo writer adicionado) — nenhuma ação necessária | F2 | #1272 | verificado | #1259 | 2026-08-24 |
| CL-A5 | Classe A passo 5 — remover `teses_juridicas_v4` / `teses_vitoriosas` | F5 | — | pendente | — | — |
| CL-B1 | Classe B — correção do plano: `STATUS_REGISTRY` é multiuso (peças, honorários, clientes, prazos) — chaves não são "fantasma", servem outros domínios; nenhuma ação | F2 | #1272 | verificado | #1259 | 2026-08-24 |
| CL-B2 | Classe B — guard-rail de paridade já existe (`test_status_caso_paridade_frontend.py`) | F2 | #1272 | verificado | #1259 | 2026-08-24 |
| CL-B3 | Classe B — preservar estado real ao desarquivar/reabrir (`status_anterior`, migration 148, endpoint `/reabrir`) | F2 | #1272 | em-andamento | #1259 | 2026-08-24 |
| CL-C1 | Classe C — deprecar/remover campo `saudavel` do contrato de `case_health.py` | F2 | — | pendente | — | — |
| CL-C2 | Classe C — unificar limiares (`health_thresholds.py`, par com `visual_law_core.py`) | F2 | — | pendente | — | — |
| CL-D1 | Classe D — rótulo corrigido para "Base fática registrada" (a checagem aceitar descrição digitada é deliberada, não bug) | F2 | #1272 | em-andamento | #1259 | 2026-08-24 |
| CL-D2 | Classe D — golden test das 16 etapas + cenário caso-recém-criado documentado; ponte `case_checklists`→`checklist_criado` fica para depois (refinamento, não bug) | F2 | #1272 | em-andamento | #1259 | 2026-08-24 |
| CORTE-1 | Cortar jurimetria / predição de êxito | F5 | — | pendente | — | — |
| CORTE-2 | Remover código de `diplomacia-v3` (risco disciplinar) | F5 | — | pendente | — | — |
| CORTE-3 | Cortar Victory Vault | F5 | — | pendente | — | — |
| CORTE-4 | Cortar radar de notícias / `/noticias` | F5 | — | pendente | — | — |
| CORTE-5 | Cortar módulo sociedade / retiradas de sócio | F5 | — | pendente | — | — |
| CORTE-6 | Arquivar skills de IA sem uso registrado em log | F5 | — | pendente | — | — |
| CORTE-7 | Desmontar `UI.tsx` (1437 linhas) em `components/ui/*` + consolidar 8 CSS globais | F5 | — | pendente | — | — |

## Placar por fase (derivado — não editar à mão, `status_check.sh` recalcula na saída)

Ver saída de `scripts/status_check.sh --resumo`.
