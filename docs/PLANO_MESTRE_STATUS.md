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
  (esteira/deploy/processo), `AUD27-` (achados novos de
  `docs/auditoria/relatorios/2026-08-27-verificacao-e-novos-achados.md`), `VARR-`
  (achado da varredura de conferência dos pendentes, 2026-09-01 — prefixo próprio
  porque não vem de nenhum dos relatórios acima, e sim de reler o código à procura
  de status envelhecido).

## Tabela

| ID | Descrição | Fase | Issue | Status | PR | Data |
|---|---|---|---|---|---|---|
| INFRA-1 | Checklist-mestre (este arquivo) + `status_check.sh` no gate local | F0 | #1272 | em-andamento | #1259 | 2026-08-24 |
| INFRA-2 | Banner de descontinuação de status nos docs legados + correção final ✅/🟡 (frentes 2, 11, 12) | F0 | #1272 | em-andamento | #1259 | 2026-08-24 |
| INFRA-3 | Pauta de decisões do titular (`docs/PAUTA_DECISOES_TITULAR.md`) | F0 | #1272 | em-andamento | #1259 | 2026-08-24 |
| INFRA-4 | Ensaio `--dry-run` do deploy manual + backup/downgrade verificados em staging | F0 | — | pendente | — | — |
| INFRA-T1 | Titular: 1º deploy manual EXECUTADO em 2026-09-05 (`deploy_manual.sh --sha 094e3d8a…`, dry-run + real): backup cifrado offsite, migration 156 aplicada, `/api/health` confirma `094e3d8a`, post-deploy check OK. Achado: pré-voo exigia SHA completo (corrigido, `scripts/lib/sha_prefix.sh`) | F0 (gate) | #1258 | verificado | #1259 | 2026-09-05 |
| INFRA-T2 | Titular: regularizar cota GitHub Actions + reativar `auto-integracao.yml`, `continuity-ui-gates.yml`, `architecture-inventory.yml` | F6 (gate) | — | pendente | — | — |
| V2-0.1 | Prazo vencendo hoje, sem ciência confirmada | F1 | — | pendente | — | — |
| V2-0.2 | Captura DJEN — código verificado OK (por advogado, monitorado por resultado, autoatendimento de OAB); resta só cadastro real das OABs (ver V3-B6) | F1 | — | mesclado | #1015 | 2026-08-14 |
| V2-1.1 | Dashboard "0 peças aguardando revisão" com 100% em rascunho `[CRÍTICO]` | F1 | — | mesclado | #1015 | 2026-08-14 |
| V2-1.2 | Contador de casos ativos conta o arquivado (bug em `dossie_cliente.py:140`) | F1 | #1272 | em-andamento | #1259 | 2026-08-24 |
| V2-1.3 | Filtro de status quebra o servidor ou retorna vazio | F1 | #1272 | em-andamento | #1259 | 2026-08-24 |
| V2-1.4 | Mensagem falsa "A equipe foi notificada" | F1 | — | mesclado | #1015 | 2026-08-14 |
| V2-1.5 | Rotas retornando 404/307 — **as seis conferidas contra a tabela de rotas real; classificação CORRIGIDA em 01/09 após achado do Codex**: (a) **307 de barra final**, o conserto barato — `/procuracoes` e `/agenda-eventos` existem COM barra (`/api/procuracoes/`, `/api/agenda-eventos/`) e o redirect custa um round-trip por chamada; padronizar `redirect_slashes` ou o path no frontend. (b) **sem endpoint de coleção raiz** — `/workflow/` e `/anexos` têm 7 e 3 sub-rotas próprias mas nenhum `GET` de raiz, então o 404 está correto e quem chama a raiz é que erra. (c) **funcionalidade ausente** — só `/crm/leads` e `/assinaturas` não têm rota nenhuma registrada; não é rota quebrada, é módulo inexistente | F1 | — | pendente | — | 2026-09-01 |
| V2-2.1 | Vínculo de validação (`ai_log_id`) que trava as peças antes do protocolo `[CRÍTICO]` | F1 | — | mesclado | #1015 | 2026-08-14 |
| V2-2.2 | Embeddings 0/47.359 — investigado (2026-08-24): NÃO é pipeline quebrado; código (self-heal `reembed_rag_orfaos` + script idempotente) já mesclado desde #1015, default `EMBEDDINGS_ENABLED=true`; produção sobrescreve a flag para `false` no `.env` do VPS. Execução é ação do titular (T4 na pauta) `[CRÍTICO]`. **VERIFICADO em produção (2026-09-05, log do deploy)**: `.env` já com `EMBEDDINGS_ENABLED=true`; reparo da base → `chunks_sem_embedding_antes: 0, depois: 0`, 9.296 docs vigentes | F3 | — | verificado | #1015 | 2026-09-05 |
| V2-2.3 | Modelo local para dados pessoais — já resolvido (`sanitization_policy.py`, modo LOCAL_COMPLETO bloqueia provedor externo); 305 testes passam | F3 | — | mesclado | #1195 | 2026-08-18 |
| V2-2.4 | Consolidar aprovação da peça em um único ato | F1 | — | mesclado | #1153 | 2026-08-18 |
| V2-3.1 | Monitorar resultado, não apenas execução — já generalizado (`ingestao_saude.py`, não só DOU/DJEN) | F3 | — | mesclado | #1015 | 2026-08-14 |
| V2-3.2 | Falso-ausente (2026-08-24) — já resolvido: `ingestao_saude.py` classifica `nunca_produziu`/`parou_de_produzir` por RESULTADO (não confia no `status="sucesso"` do job), `executar_ingestao`/`conhecimento_ingest` garantem `ultimo_erro` nunca vazio (caso `anpd` citado no próprio código), slugs duplicados `juris_import_*` consolidados (migration 138); 27 testes passam | F3 | — | mesclado | #1015 | 2026-08-14 |
| V2-3.3 | CORRIGIDO — mesmo defeito que `AUD27-P3-10`, registrado em duplicidade sob dois IDs. Fechado pela mesma cascata de soft-delete | F5 | — | mesclado | #1316 | 2026-08-31 |
| V2-3.4 | Vínculos ausentes entre registros relacionados | F5 | — | pendente | — | — |
| V2-3.5 | Padrão de gravação não transacional (agregado do Caso) — classe de defeito com CINCO vínculos. **Um deles caiu**: `Caso.descricao_fatos` na conversão da Sala Jurídica (V2-3.6, #1238). Seguem quatro: `LegalDoc.validacao_juridica.ai_log_id`, `Caso.jurimetria`, cascata de peças na exclusão de caso, e `oab_number` × `djen_oab_numero` (AUD27-P3-9) | F5 | — | pendente | — | 2026-09-01 |
| V2-3.6 | Conversão Sala Jurídica → Caso perde `descricao_fatos`. **JÁ CORRIGIDO** pelo #1238 (`c1a060e`), achado do Codex na revisão desta varredura — eu não tinha examinado este item. Cadeia completa hoje: `SalaJuridica.tsx:564` preenche `convFatos` com o primeiro que existir entre `estado.resumo`, `workspace_texto` e `fatosDasMensagens(...)`, a linha 661 posta como `descricao`, e `legal_chat_service.py:941` grava em `descricao_fatos=`. O próprio código descreve o defeito no PASSADO ("a caixa abria VAZIA e o caso nascia com `descricao_fatos = NULL`") e há teste de regressão | F5 | — | mesclado | #1238 | 2026-09-01 |
| V2-4.1 | Código já pronto e testado (guard de produção em `run_fictitious_smoke.py`, script `purga_dados_homologacao.py` com desativação de conta); execução em produção é ação do titular (governança §9 me veda acesso) | F3 | — | mesclado | #1015 | 2026-08-14 |
| V2-4.2 | Métrica de "chance de êxito" — decisão D4 (Opção 1): removida da UI da Entrevista Inteligente; API mantém o campo, tipado com nota de não-reintrodução; confirmado que nenhuma rota `/portal/*` a serializa `[CRÍTICO]` | F3 | #1272 | em-andamento | #1259 | 2026-08-24 |
| V2-4.3 | Investigado (2026-08-24, decisão D5): "OAB Prov. 205/2021" citado como base do HITL em ~25 arquivos (prompts de IA + testes), confirmado incorreto (é sobre publicidade); substituição sugerida pela auditoria (CNJ 615/2025) também não se sustenta (regula o Judiciário, não a advocacia) — precisa de advogado real antes de aplicar | F3 | — | pendente | — | — |
| V2-4.4 | `POST /trash/{entidade}/{id}/purgar` — hard delete real, superadmin-only, motivo obrigatório, audit log WORM, sem cascata automática; revisado por security-auditor (RBAC/IDOR/PII ok; TOCTOU corrigido com `with_for_update`) | F3 | #1272 | em-andamento | #1259 | 2026-08-24 |
| V2-5.1 | Primeira leva (6 de ~50 descobertas — auditoria amostrou 15 em 3 áreas, achei o padrão em ~13 áreas): form-runner genérico (`CalculadorasJuridicas.tsx`) + config declarativa extensível, embutido em "Mais Ferramentas". Restante entra só como nova entrada na config `[ALTO — maior ganho rápido]` | F3 | #1272 | em-andamento | #1283 | 2026-08-24 |
| V2-5.2 | Curadoria da base de conhecimento `[ALTO — trabalho contínuo]` | T5 | — | pendente | — | — |
| V2-5.3 | Higiene é curadoria contínua (T5, titular). `[INVESTIGAR]` do hash de duplicidade fechado (2026-08-24): `hash_conteudo` é SHA-1 do conteúdo NORMALIZADO INTEIRO (`ingestion_service.py::normalizar`+`_sha1`), sem truncar — descarta "trecho insuficientemente específico"; colisão entre acórdãos com processo distinto só se explica por `conteudo` quase idêntico gravado pelo scraper STJ (stub/boilerplate), que só se confirma inspecionando os 3 documentos reais em produção (fora do meu acesso, governança §9) | F3/T5 | — | pendente | — | — |
| V2-5.4 | Erro jurídico recorrente nas skills (decadência, CPC art. 487, II) | — | — | **verificado** | #1015 | 2026-08-22 |
| V2-5.5 | Causa raiz achada: rejeição da `AIProviderPolicy` (cadeia vazia, ex. PII sem provider local elegível) acontece ANTES do gateway — invisível a `AILog` e `AIProviderMetric`, por isso telemetria mostrava "0 falhas". `orchestrator.run` agora registra o bloqueio (`registrar_bloqueio_politica`); alerta ao usuário deixou de ser genérico | F3 | #1272 | em-andamento | #1259 | 2026-08-24 |
| V2-6.1 | Prefixo `/v1/` duplicado | F5 | — | pendente | — | — |
| V2-6.2 | Observabilidade | F5 | — | pendente | — | — |
| V2-6.3 | Painéis de diagnóstico divergentes | F5 | — | pendente | — | — |
| V2-6.4 | Superfície de API duplicada | F5 | — | pendente | — | — |
| V2-6.5 | Rotas órfãs e mapa incompleto (211 de 453 rotas nunca chamadas) | F5 | — | pendente | — | — |
| V2-6.6 | Taxonomia de áreas duplicada (4 manifestações). **Refinado em 01/09**: os 5 módulos com lista local citados na origem são na verdade **6** — `components/PecaGeneratorModal.tsx:84` tem a sua, com apenas 8 áreas, contra 24 do `areaCatalog.ts` e 25 do enum do backend (`case.py`) e de `AREAS_CANONICAS`. É fallback usado só se `GET /pecas/meta` falhar, e nesse caso o advogado vê 8 áreas sem saber que a lista encolheu. Uma consolidação de catálogo resolve tudo isto de uma vez — por isso não vira item próprio (achado do Codex) | F5 | — | pendente | — | 2026-09-01 |
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
| CL-C1 | Classe C — deprecar/remover campo `saudavel` do contrato de `case_health.py`. **Já feito**: o campo saiu do contrato e o próprio código registra o porquê (`case_health.py:44-48` — *"Era lido em 0 lugares do frontend; removido do contrato em vez de consertado"*). O que resta com esse nome é o VALOR de `classificacao`, que é correto | F2 | — | mesclado | #1272 | 2026-09-01 |
| CL-C2 | Classe C — unificar limiares. **Resolvido por DECISÃO, no sentido inverso do enunciado**: `case_health.py:31-36` documenta que os limiares de saúde do caso (4 faixas) e os de probabilidade de êxito (`visual_law_core.py`, 3 faixas) respondem PERGUNTAS diferentes sobre o mesmo score — unificá-los seria a abstração errada. O único ponto único é a FONTE do score, que já é única. O `health_thresholds.py` do enunciado nunca existiu | F2 | — | mesclado | #1272 | 2026-09-01 |
| CL-D1 | Classe D — rótulo corrigido para "Base fática registrada" (a checagem aceitar descrição digitada é deliberada, não bug) | F2 | #1272 | em-andamento | #1259 | 2026-08-24 |
| CL-D2 | Classe D — golden test das 16 etapas + cenário caso-recém-criado documentado; ponte `case_checklists`→`checklist_criado` fica para depois (refinamento, não bug) | F2 | #1272 | em-andamento | #1259 | 2026-08-24 |
| CORTE-1 | Cortar jurimetria / predição de êxito | F5 | — | pendente | — | — |
| CORTE-2 | Remover código de `diplomacia-v3` (risco disciplinar) — `diplomacia_digital.py` virou `calculo_acordo.py` (só o VPL usado por visual_law); `gerar_dossie_pressao` e os pares `/diplomacia` do route_registry removidos | F5 | #1522 | em-prod | #1531 | 2026-09-05 |
| CORTE-3 | Cortar Victory Vault — `core/victory_vault.py`, schema e `data/mock_db` removidos; `veredito_ia` sem o passo; módulo/skill fora do catálogo. Tabelas `teses_vitoriosas`/`modelos_documentos` seguem no banco até migration de contração (regra 2) | F5 | #1522 | em-prod | #1531 | 2026-09-05 |
| CORTE-4 | Cortar radar de notícias / `/noticias` — router, página, card do Dashboard, guia, módulo e skill removidos | F5 | #1522 | em-prod | #1531 | 2026-09-05 |
| CORTE-5 | REENQUADRADO (2026-09-05): não cortar — `partner_withdrawals` é escrito por `honorarios_oab.py` e lido por `extratos.py`; cortar quebraria honorários. Sociedade saiu do menu (`hidden`), rota viva por deep-link | F5 | — | em-prod | #1531 | 2026-09-05 |
| CORTE-6 | Arquivar skills de IA sem uso registrado em log | F5 | — | pendente | — | — |
| CORTE-7 | Desmontar `UI.tsx` (1437 linhas) em `components/ui/*` + consolidar 8 CSS globais | F5 | — | pendente | — | — |
| AUD27-P0-1 | CORRIGIDO — `_requisitos()`, a fonte única de elegibilidade, checava as flags por provedor e a de externos mas **nunca `AI_ENABLED`**: com Ollama ligado, `/ai/core/*` gerava com a IA "desligada". O kill-switch global virou requisito de todo provedor; cadeia vazia falha antes de tocar rede, e `motivo_inelegivel` distingue kill-switch de chave ausente `[era CRÍTICO]` | F1 | — | mesclado | #1316 | 2026-08-31 |
| AUD27-P1-1 | CORRIGIDO — reproduzido: `POST /cases/` como `financeiro` devolvia 404 do handler, não 403; o gate deixava entrar e quem barrava era o sigilo do cliente. Migrado para `require_roles_exact` com allowlist exata (equipe jurídica + secretaria). Ver nota sobre `estagiario` abaixo da tabela | F1 | — | mesclado | #1316 | 2026-08-31 |
| AUD27-P1-2 | `ai_skills.py` (609 linhas, OCR/transcrição/skills) sem nenhum teste | F3 | — | pendente | — | 2026-08-27 |
| AUD27-P1-3 | Indexação do RAG sem teto de lote no encode — 10,1 GB de anon-rss medidos, disparou OOM-killer global na VPS em 27/08 `[INCIDENTE]` | F1 | #1308 | em-prod | #1309 | 2026-08-27 |
| AUD27-P1-4 | Containers do EJC sem `mem_limit` num host com 6 sistemas — um trabalho do EJC reiniciou o `verdelimp-erp` em 27/08 `[INCIDENTE]` | F1 | #1308 | em-prod | #1309 | 2026-08-27 |
| AUD27-P1-5 | Titular: religar `RAG_AUTO_REEMBED_ENABLED=true` no `.env` do VPS após o deploy da #1309 — **verificado em 2026-09-05**: `.env` do VPS já traz `RAG_AUTO_REEMBED_ENABLED=true` (linha 151) e o job rodou no deploy (`[reembedar] ok=0 erros=0`) | F1 (gate) | #1308 | verificado | #1309 | 2026-09-05 |
| AUD27-P1-6 | `secrets/` (credenciais OAuth do Google Drive), `backups/` e `data/` não estavam no `.gitignore` no checkout de produção — um `git add -A` publicaria credencial `[SEGURANÇA]` | F1 | #1310 | em-andamento | #1311 | 2026-08-27 |
| AUD27-P1-8 | Alerta de prazo do DJEN não depende de `DJEN_OABS_MONITORADAS`: a CAPTURA lê a env var (`ingestors/djen.py:204`), o ALERTA itera `users.djen_oab_numero` (`scheduler.py:1637`) — fontes diferentes, confirmado em 01/09. **A metade silenciosa já foi corrigida** pelos #1311/#1312: com 0 OABs elegíveis o job vira `erro` no heartbeat com `{"erros":{"nenhuma_oab_configurada":1}}` (`djen_service.py:194`), então a falha aparece no diagnóstico. Fica aberta a metade substantiva — se os cadastros dos advogados têm `djen_oab_numero` preenchido em PRODUÇÃO (vazio na auditoria de julho); é tarefa de cadastro, não de código, e só se confere no ar `[RISCO DE PRAZO]` | F4 | #1310 | pendente | — | 2026-09-01 |
| AUD27-P1-7 | Correção de risco de prazo (2ª OAB no DJEN) vivia só como edição manual no `/opt/ejc`, fora do Git — seria destruída pelo próximo `checkout --force` | F1 | #1310 | em-andamento | #1311 | 2026-08-27 |
| AUD27-P2-8 | RETIFICADO — **não é achado de segurança nem pendência de código**. O deploy de 27/08 16:31 provou o backup offsite FUNCIONANDO (`offsite_ok: true`, db 30,7 MB + uploads 15,1 MB cifrados e enviados via rclone, `auth_mode: service_account`, `credencial_dedicada: true`). O arquivo de 1 byte não é a credencial ativa — a ativa vem de `BACKUP_GOOGLE_DRIVE_*`. Resta só remover o arquivo morto, que está **na VPS e não no repositório** — logo é limpeza operacional do titular, fora do meu alcance (governança §9) | F5 | #1310 | pendente | — | 2026-08-27 |
| AUD27-P3-12 | `ingestors/djen.py:234` loga número CNJ de processo de terceiro em INFO a cada descarte; volume dobra com a 2ª OAB — avaliar DEBUG ou contagem por OAB (security-auditor B5, não bloqueante) | F5 | #1310 | pendente | — | 2026-08-27 |
| AUD27-P3-13 | Sem varredura de segredo no caminho de commit (`.githooks/` só tem `pre-push`) nem push protection confirmada no GitHub — `.gitignore` é barreira, não fronteira (security-auditor B6/C4) | F5 | #1310 | pendente | — | 2026-08-27 |
| AUD27-P2-9 | Checkout de produção divergia do container (`eb65e63e`, 14/08) — **resolvido pelo deploy de 2026-09-05**: ~100 arquivos soltos em `/opt/ejc` guardados em `git stash` (`pre-deploy-094e3d8a-2026-09-05-2050`), checkout = container = `094e3d8a` | F5 | #1310 | verificado | #1259 | 2026-09-05 |
| AUD27-P2-1 | CORRIGIDO — os contadores filtravam só o `deleted_at` da própria peça, nunca o do caso pai. `_peca_de_caso_vivo()` nos guardrails E no `/dashboard` (dois painéis do mesmo controle HITL com filtros diferentes dariam duas verdades). Peça avulsa segue contando | F1 | — | mesclado | #1316 | 2026-08-31 |
| AUD27-P2-2 | CORRIGIDO — reproduzido: `/qualidade/*` como `financeiro` devolvia 422 (corpo lido), não 403 — passava do gate. `require_roles_exact(EQUIPE_JURIDICA)` nos 3 endpoints | F1 | — | mesclado | #1316 | 2026-08-31 |
| AUD27-P2-3 | `cerebro.py` sem teste funcional (só existência de rota no snapshot OpenAPI) | F3 | — | pendente | — | 2026-08-27 |
| AUD27-P2-4 | Sentry (`SENTRY_DSN`) ativado em produção pelo titular em 27/08 14:32; log confirma `Sentry inicializado (environment=production)` — resta só conferência pós-deploy | F5 | — | mesclado | #1309 | 2026-08-27 |
| AUD27-P2-5 | `AREAS_FALLBACK` do frontend com 24 áreas, faltando `licitacoes` (enum backend tem 25) | F5 | — | pendente | — | 2026-08-27 |
| AUD27-P2-6 | 4ª manifestação de taxonomia de área (`areasWorkspace.ts::AREAS_CANONICAS`) diverge de `AREAS_FALLBACK` | F5 | — | pendente | — | 2026-08-27 |
| AUD27-P2-7 | Cobertura de RAG ainda insuficiente após lotes 001/002: ~21/29 áreas sem fonte; as 8 novas seguem `rag_status=pendente` | T5 | — | pendente | — | 2026-08-27 |
| AUD27-P2-10 | Base de conhecimento com o mesmo texto legal em 4-6 cópias (CPC 6x, CLT 4x, CC 4x, CF 4x) — duplicata ocupa as vagas do contexto do RAG e degrada a resposta; ferramenta pronta em `scripts/deduplicar_base_conhecimento.py` (rebaixa, não apaga), execução é ato do titular | F3 | #1313 | em-andamento | #1314 | 2026-08-27 |
| AUD27-P2-11 | Cópia do CPP com `categoria=peca_escritorio` (restrita por cliente) e `client_id` nulo — irrecuperável pela busca; há 4 cópias corretas, então o caminho é remover, não recategorizar | F3 | #1313 | pendente | — | 2026-08-27 |
| AUD27-P3-14 | Zumbis do host: 158 processos (`node`/`chromium`/`chrome_crashpad`) sob um único pai no container do **s2licit** (puppeteer-extra-stealth) — não é o EJC; raspagem travando em laço há 24h sugere coleta de editais quebrada | F5 | #1313 | pendente | — | 2026-08-27 |
| AUD27-P3-1 | REENQUADRADO em 01/09: o `b77ff4c` arquivou o Actions e `.github/workflows` **não existe mais**, então nada pode disparar sozinho — o risco imediato acabou. O latente permanece na cópia arquivada (`docs/arquivo/ci/github-actions-legacy/2026-08-31/`): restaurar a pasta traz os dois gatilhos armados junto. Desarmar na cópia, ou exigir desarme no procedimento de restauração | F6 (gate) | — | pendente | — | 2026-09-01 |
| AUD27-P3-2 | CORTE-2/CORTE-3: camada de router já cortada (12/08), services (`diplomacia_digital.py`, `victory_vault.py`) seguiam ativos — fechado com os cortes de 2026-09-05 (ver CORTE-2/3) | F5 | — | em-prod | #1531 | 2026-09-05 |
| AUD27-P3-3 | Aba morta inalcançável `"ia_cliente"` em `DossieCliente.tsx` | F5 | — | pendente | — | 2026-08-27 |
| AUD27-P3-4 | `components/Layout.tsx` (669 linhas) código morto, substituído por `LayoutReference.tsx`. **Já removido**: o arquivo não existe mais na árvore desde o `bbc6944`. Status obsoleto, não código — corrigido na varredura de 01/09 | F5 | — | mesclado | #1316 | 2026-09-01 |
| AUD27-P3-5 | `DashboardLegalTechPremium.tsx` (480 linhas) componente de demonstração morto. **Já removido** no `bbc6944`; nenhum arquivo com esse nome existe na árvore. Status obsoleto, não código — corrigido na varredura de 01/09 | F5 | — | mesclado | #1316 | 2026-09-01 |
| AUD27-P3-6 | CORTE-7 subestimado: CSS global são 12 arquivos/7815 linhas (o título do CORTE-7 diz 8) — reconferido em 01/09. `UI.tsx` está em **1400 linhas** (o item dizia 1484, e o CORTE-7 diz 1437): encolheu, mas segue muito acima do limiar que motivou o corte | F5 | — | pendente | — | 2026-09-01 |
| AUD27-P3-7 | Referências de migration desatualizadas em CL-A2 (diz 149, real 152) e CL-B3 (diz 148, real 151) | F2 | — | pendente | — | 2026-08-27 |
| AUD27-P3-8 | Padrão de `UPDATE` dinâmico via f-string com allowlist estática (seguro hoje, frágil a regressão) em 5+ routers | F5 | — | pendente | — | 2026-08-27 |
| AUD27-P3-9 | `oab_number`/`djen_oab_numero` sem reconciliação (subitem aberto de V2-3.5) | F5 | — | pendente | — | 2026-08-27 |
| AUD27-P3-10 | CORRIGIDO — provado no banco: caso excluído com peça em rascunho de `deleted_at` nulo, órfã viva. Exclusão passa a cascatear o soft-delete às peças não protocoladas, com os IDs na trilha; a protocolada segue bloqueando a exclusão com 422 | F5 | — | mesclado | #1316 | 2026-08-31 |
| AUD27-P3-11 | MEDIDO e corrigido **quanto à ordenação** — a hipótese errou o remédio: índice em `deleted_at` não muda nada (401ms → 380ms em 1M de linhas; o filtro casa com 96% das linhas). O custo era a ORDENAÇÃO: índice PARCIAL `(created_at DESC) WHERE deleted_at IS NULL` leva a listagem a 0,30ms e faz o tempo parar de crescer com a tabela. Aplicado a `cases`/`clients`/`documents`; `deadlines` fica de fora, medida como já coberta por `ix_deadlines_data_prazo`. A CONTAGEM do endpoint segue O(n) — resíduo em AUD27-P3-15 | F5 | — | mesclado | migration 155 | 2026-08-31 |
| AUD27-P3-15 | Listagens de `cases`/`clients`/`documents` fazem contagem EXATA sobre todo o conjunto vivo antes de paginar (`select(count()).select_from(q.subquery())`) — O(n) por definição, e medido como praticamente imune ao índice parcial da 155 (109,23 ms → 99,00 ms em 1M de linhas). Com a ordenação resolvida, é o que sobra limitando a resposta. Saídas: total estimado por `reltuples`, total sob demanda, ou paginação por cursor — todas mudam contrato de paginação/UX, logo decisão do titular | F5 | — | pendente | — | 2026-08-31 |
| VARR-1 | `ramos_vitrine.py:1146` mantém cópia **byte a byte** de `_LIMIARES_TAXA_MEDIA`, que outros seis routers de ramo importam de `ramos_comum.py:604`. Duas fontes para o mesmo limiar jurisprudencial (REsp 1.061.530/RS) — divergem no primeiro que alguém editar, e o valor sai em resposta de API (`limiares_classificacao`) | F5 | — | pendente | — | 2026-09-01 |

## Notas dos itens fechados em 31/08 (PR #1316)

### `AUD27-P1-1` — ponto de decisão do titular, ainda aberto

A allowlist exata de `POST /cases/` (`_PODE_CRIAR_CASO`) lista **`estagiario`
explicitamente**. Ele nunca esteve na lista original do M16: criava caso por
**acidente da hierarquia** — o piso da lista antiga era `secretaria` (nível 2) e o
estagiário está acima. Ao migrar para allowlist exata, a escolha foi **preservar o
acesso de quem hoje o exerce**, porque tirar permissão em uso é quebra de contrato e o
achado era `financeiro` entrando, não estagiário sobrando.

O efeito colateral é que uma permissão acidental virou permissão **deliberada e
escrita**. Se a intenção do escritório for que estagiário não abra caso sozinho, é uma
linha a remover — decisão do titular, não do implementador.

### Itens que já estavam corrigidos — status obsoleto, não código

Verificados empiricamente em 30-31/08, **sem alterar uma linha**. Ficam aqui para
ninguém refazer o trabalho; o flip de status cabe a quem os corrigiu, não a mim:

- **IDOR de agenda (3 residuais de 18/07)** — a listagem já escopa evento pessoal ao
  criador/responsável (secretaria não vê o do advogado); atribuir `responsavel_id` de
  terceiro já devolve 403; `protocolo_comprovante_doc_id` já valida existência, exclusão
  e pertencimento ao caso. Os testes que o relatório dava como ausentes **também já
  existem** (`test_agenda_eventos_gates_dblevel`, `test_legal_doc_protocolo`).
- **`AUD27-P1-8`** `[RISCO DE PRAZO]` — provado ao vivo que **não** há falha silenciosa:
  com 0 OABs elegíveis, o "ok" nominal do job vira `erro` no heartbeat, com
  `{"erros":{"nenhuma_oab_configurada":1}}` visível no diagnóstico (corrigido por #1310).

### Por que seis itens ficaram com status obsoleto por um dia

Os seis acima foram corrigidos e mesclados pelo #1316 em 31/08, mas seguiram marcados
`pendente` até serem virados neste PR. A causa foi um raciocínio mal aplicado: a regra
"o flip de status é da PR que corrige o item" vale para itens que **outra** PR
corrigiu — e foi estendida indevidamente aos que a própria #1316 corrigia. É a mesma
armadilha de status obsoleto que esta auditoria gastou tempo desfazendo: metade dos
itens que ela encontrou como "pendentes" já estava resolvida.

## Notas da varredura de conferência (01/09)

Varredura dos 57 itens marcados `pendente`, para separar o que ainda é real do que já
fora resolvido sem ninguém virar o status. **29 conferidos direto no código**; os outros
28 dependem de produção, telemetria ou decisão de produto e não se resolvem lendo o
repositório. Nenhuma linha de código de produção foi alterada aqui — só este arquivo.

### Por que este PR flipa status de itens que outras PRs corrigiram

A regra da seção "Como este arquivo é mantido" diz que o flip cabe à PR que fecha o
item, nunca a uma PR separada. Ela existe para impedir que quem corrige empurre o
registro para depois — **não** para congelar um status errado quando a PR que corrigiu
já foi mesclada há semanas e ninguém vai voltar. Aplicá-la ao pé da letra aqui
preservaria exatamente o vício que ela combate: foi assim que seis itens do #1316
ficaram obsoletos por um dia, e é o que a nota anterior já registra.

Cada linha virada aponta a PR que efetivamente corrigiu, para a rastreabilidade não se
perder: `AUD27-P3-4` e `AUD27-P3-5` → #1316 (`bbc6944`); `CL-C1` e `CL-C2` → #1272
(`aca9842`), localizadas por `git log -S` no código, não por memória.

### `mesclado`, não `verificado`

Os quatro itens virados foram para `mesclado`. `verificado` exigiria conferência
pós-deploy, e **nada disso está em produção**: o container em execução é de 14/08
(`AUD27-P2-9`), anterior às duas PRs. Marcar `verificado` seria repetir o erro que este
arquivo existe para evitar.

### Quatro enunciados reescritos, não virados

`INFRA-T1`, `AUD27-P3-1`, `V2-1.5` e `AUD27-P1-8` continuam abertos, mas descreviam
errado o que falta — o de `V2-1.5` agrupava três problemas distintos sob "404", e só um
dos seis casos tem conserto barato. Um item mal descrito custa mais caro que um item
fechado errado: alguém vai orçar o trabalho pela descrição.

### Dois achados que eu levantei e a própria conferência derrubou

Registrados porque o descarte é parte do resultado:

- **Dois testes para `Sociedade`** pareciam duplicata. Não são: `pages/Sociedade.test.ts`
  cobre deep links (13 linhas) e `pages/__tests__/Sociedade.test.tsx` é regressão de tela
  branca (68 linhas). Só a pasta é inconsistente — cosmético, não vira item.
- **`PecaGeneratorModal` como 4ª manifestação de taxonomia** estava errado: o `V2-6.6` já
  conta 5 módulos com lista local. Ele é um **sexto**, e virou `VARR-2` com esse
  enquadramento — não um achado inédito.

### Correções após a revisão do Codex (01/09)

A revisão automática deste PR apontou três defeitos P2 **na própria varredura**.
Conferi os três, os três procedem, e estão corrigidos acima. Ficam registrados
porque um erro dentro de um PR que se apresenta como "conferência" pesa mais que
um erro comum — ele entra no registro canônico com aparência de fato apurado.

**1. `/procuracoes` estava no balde errado — erro meu, e o pior dos três.**
Classifiquei como "nenhuma rota registrada" algo que tem três rotas e um
`GET /api/procuracoes/`. A causa foi trivial e instrutiva: busquei pela substring
`procuracao`, que **não ocorre** em `procuracoes`. O `grep` devolveu zero e eu li
zero como inexistência, em vez de suspeitar da busca. E o documento de origem
(`plano-correcao-v2.md`) já registrava `GET /procuracoes → 307` — contrariei a
evidência que estava na minha frente. Como o Codex observa, sendo este o backlog
canônico, a redação anterior mandaria alguém **reconstruir funcionalidade que já
existe**.

**2. `VARR-2` virou refinamento do `V2-6.6`, não item próprio.** Eu mesmo o
descrevi como "um sexto módulo" da mesma duplicação que o `V2-6.6` já rastreia:
uma única consolidação de catálogo resolve os dois. Dois IDs para um defeito
inflam a contagem e deixam os status divergirem depois.

**3. `V2-3.6` já estava corrigido** pelo #1238 — e eu **não tinha examinado este
item**. É o quinto status obsoleto desta rodada, e o único encontrado por outra
pessoa.

### A limitação real desta varredura

O achado 3 expõe o que estava fraco, e não é um item: é a **cobertura**. Conferi
29 dos 57 e a redação deu a entender que os 28 restantes eram inverificáveis por
código. **Não eram** — o `V2-3.6` estava entre eles e bastava ler três arquivos.

Então o número continua sem ser plenamente confiável, agora com uma estimativa
honesta: dos 29 conferidos, 5 estavam obsoletos (17%). Se a taxa se mantiver nos
28 não conferidos, ainda há uns 4 ou 5 itens resolvidos marcados como pendentes.
Fechar isso exige conferir os 28 restantes um a um — trabalho legítimo, mas que
não cabe neste PR.

## Placar por fase (derivado — não editar à mão, `status_check.sh` recalcula na saída)

Ver saída de `scripts/status_check.sh --resumo`.
