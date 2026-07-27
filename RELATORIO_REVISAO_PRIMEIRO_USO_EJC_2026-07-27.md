# Revisão de primeiro uso — EJC sob a ótica do advogado detalhista

**Data:** 2026-07-27
**Método:** três auditorias paralelas somente-leitura (jornada UX no frontend, inventário de produto no backend, fluxo de IA/parecer ponta a ponta), cruzadas com o histórico recente (`PENTE_FINO_2026-07-25.md`, `RELATORIO_MELHORIA_GERAL_EJC_2026-07-22.md`, `docs/PLANO_SIMPLIFICACAO_EJC.md`). Todas as evidências citadas em `arquivo:linha`. Nada foi alterado além deste relatório.
**Pergunta respondida:** "Como um advogado detalhista que usasse o EJC pela primeira vez — cadastrar um caso, pedir um parecer à IA, usar cada módulo, ferramenta e área de atuação — o que melhorar, mesclar, excluir ou incluir?"

---

## 1. Diagnóstico em uma frase

**O EJC não sofre de falta de recursos — sofre de excesso de portas de entrada e de capacidades construídas que nunca foram ligadas à interface.** O advogado de primeira viagem encontra 3 chats de IA concorrentes, 27 abas no caso, 7 caminhos diferentes para "a IA analisa meu caso", e descobre que a IA **não lê os documentos que ele acabou de anexar** — precisa colar texto à mão. Enquanto isso, o caminho canônico e governado (`/ai/core/*`), o endpoint que monta o dossiê automaticamente (`ai.py:516`), a exportação CSV/PDF (`export.py`), o backup pela UI (`backup_admin.py`) e a checagem de conflito de interesses (`sumulas.py:99`) existem no backend **com zero consumidores**.

A consolidação de julho/2026 funcionou na navegação (36 redirects, Sala Jurídica unificada no PR #489, modos de produção ligados ao `peca_geracao.py`). O problema remanescente não é duplicação de páginas — é **duplicação de conceitos** e **código construído-e-desligado**.

## 2. Números da varredura

| Dimensão | Medição |
|---|---|
| Rotas staff ativas / itens de menu / redirects | 42 / 15 / 36 (+3 dinâmicos) — `moduleRegistry.tsx`, `canonicalRoutes.ts` |
| Rotas mortas navegáveis | 4 (`/legado/prazos|tarefas|intimacoes|suspensoes`) = 1.774 linhas duplicando `CentralAtividades` |
| Routers backend / linhas | 162 (+3 sub-routers) / ~44,4k linhas |
| Routers órfãos (sem nenhum consumidor no frontend) | ~25 (~3.000 linhas) |
| Routers com <80 linhas (candidatos a absorção) | 26 |
| Portas de entrada para "análise de caso por IA" | 7 telas, 4 pipelines paralelos de backend |
| Consumidores do núcleo canônico `/ai/core/*` no frontend | **0** |
| Telas sem estado vazio orientativo | 14 |
| Áreas de atuação anunciadas / com hub real | 24 / 14 (10 cards prometem e não entregam) |

---

## 3. A jornada do primeiro uso — onde dói

1. **Login → 2FA → troca de senha** são três telas isoladas sem "passo N de 3" (`App.tsx:87-103`); o fluxo de TOTP depende de string-matching frágil (`LoginModern.tsx:137` — `message.includes("TOTP obrigatório")`).
2. **Onboarding se auto-esconde**: o `OnboardingTour` recolhe a cada mudança de rota (`OnboardingTour.tsx:134-140`) — justamente quando o usuário segue a tarefa sugerida — e a conclusão das tarefas é 100% manual.
3. **RBAC silencioso**: `RouteGuards.tsx:35,44,58-60` fazem `<Navigate to="/">` sem mensagem. O advogado clica em Financeiro e é teleportado ao dashboard sem explicação.
4. **Caso com 27 abas** (`CasoDetalhe.tsx:88-118`); só a seção Estratégia tem 8 abas indistinguíveis para um novato (Teses / Teses sugeridas / Jurisprudência / Precedentes / Score / Índice de Risco / Dossiê / IA Defensiva). A Fase 1 do `PLANO_SIMPLIFICACAO_EJC.md` já endereça — segue pendente.
5. **Parecer da IA**: não existe botão "Solicitar parecer". O melhor produto do sistema (análise FIRAC do Raio-X, `raio_x_advogado_service.py:38-63`) está escondido atrás de um card condicional e **não pode ser salvo como documento do caso** — morre na tela.
6. **A IA não lê os autos**: `montar_dossie` (`case_context.py:87-280`) envia metadados e títulos, nunca `Document.ocr_text`; o RAG (`knowledge_chunks`) só indexa a base jurídica e o pós-mortem de encerramento (`cases.py:927`). Anexou 40 PDFs? A IA ignora todos.
7. **HITL/citation gate invisíveis**: a peça fica pendente e não há fila de revisão — os contadores de `GovernancaIA.tsx:691-695` são números sem link; o 409 do gate não é tratado em `IA.tsx:156-161` (o botão "Marcar revisado" falha em silêncio) e o override com justificativa é inalcançável pela UI.
8. **Ajuda desatualizada e órfã**: `/ajuda` é hidden e fora do catálogo; `guiaSistema.ts:165-181` ensina a "percorrer as 9 etapas da Jornada do Caso" — tela que hoje é só um redirect de 23 linhas (`JornadaCaso.tsx:22`). E a Ajuda não filtra por perfil: o estagiário lê manual de telas que lhe retornam redirect.
9. **Áreas de atuação com profundidade invisível**: `bancario` tem 5 painéis dedicados; `familia` tem 2 endpoints. Os cards do `RamosHub` parecem equivalentes, e nos 10 slugs sem hub o botão "Abrir ferramentas" simplesmente some sem explicação (`RamosHub.tsx:319-328`). Nos ramos `externo: true`, a lista nunca carrega e as estatísticas ficam zeradas como se estivessem quebradas (`RamoBase.tsx:885-888`).
10. **Portal do cliente**: sólido em dados e isolamento, mas o cliente não consegue trocar senha nem atualizar contato (nenhum link para `/trocar-senha`), não tem FAQ/glossário, não tem notificações e nenhuma tela diz **quem é o advogado responsável**.

---

## 4. MELHORAR (prioridade máxima)

| # | Ação | Evidência / base já existente |
|---|---|---|
| 1 | **Botão único "Solicitar parecer da IA" no cabeçalho do caso**, wizard de 3 passos (escopo → fontes → profundidade), chamando `/ai/core/analyze` | O endpoint canônico existe sem consumidor (`ai_core.py:140`); `/ai/casos/{id}/assistente` (`ai.py:516`) já monta o dossiê automaticamente e está órfão |
| 2 | **Salvar o parecer FIRAC como `LegalDoc` tipo `parecer`**, entrando na esteira de revisão/aprovação/PDF de `/pecas` | `legal_doc.py:16`; hoje o output morre na tela do Raio-X |
| 3 | **Fila de revisão HITL como tela de primeira classe** + tradução do 409 do citation gate para linguagem de advogado, com modal de override e justificativa | Backend devolve `bloqueantes[:10]` estruturado (`citation_gate.py:344`); `GET /ai/logs/{id}/citacoes` já existe (`ai.py:192`) |
| 4 | **Expor a análise automática de documento anexado**: card "A IA analisou este documento" na aba Documentos/Resumo | O trabalho já é feito e pago em background (`documents.py:454` → `AILog "auto-analise-doc"`) e hoje é enterrado num log |
| 5 | **RBAC com feedback**: trocar `<Navigate to="/">` silencioso por tela/toast "Seu perfil não tem acesso a este módulo" | `RouteGuards.tsx:35,44,58-60` |
| 6 | **Onboarding persistente com detecção real de conclusão** (ex.: `casos.length > 0`) e wizard "passo N de 3" no primeiro acesso | `OnboardingTour.tsx:20,134-140` |
| 7 | **Progressive disclosure no caso**: 5 âncoras canônicas + abas com dados; resto atrás de "Mais" | Fase 1 do plano de simplificação, pendente |
| 8 | **Ramos honestos**: badge de profundidade por área ("5 ferramentas · guia · calculadoras"), aviso explícito nos 10 slugs sem hub e nos ramos `externo` | `RamosHub.tsx:319-328`, `RamoBase.tsx:885-888` |
| 9 | **Ajuda**: corrigir verbete da Jornada, filtrar por `canRoleAccessPath`, incluir `/ajuda` no catálogo e no rodapé do sidebar | `guiaSistema.ts:165-181`, `Ajuda.tsx:171-183`, `Ferramentas.tsx:23-54` |
| 10 | **Erros de IA em linguagem humana**: aplicar `mensagemErroIA` onde nomes de env var vazam para o usuário | `AgenteIA.tsx:161-165`, `RaioXProcesso.tsx:1297-1300` expõem "(AI_AGENT_ENABLED)" |
| 11 | **Correções pontuais**: `/kanban` redireciona para o kanban de *atividades* mas `Kanban.tsx` é de *casos* (`moduleRegistry.tsx:904-907`); `RamosHub` navega pela rota legada `/ramos/:slug` (`RamosHub.tsx:46`); UUID digitado à mão no Agente IA (`AgenteIA.tsx:250-258` → usar o seletor de `IA.tsx:202-216`); estados vazios padronizados nas 14 telas sem `EmptyState` | — |

## 5. MESCLAR

**Frontend — conceitos, não só rotas:**
- **Uma porta de IA**: `SalaJuridica` como entrada conversacional única; "Pergunta rápida" (`AssistenteIA.tsx`) e "Analisar ou revisar" (`IA.tsx`) viram atalhos dentro dela; geração de minuta do `AssistenteIA` (`/ai/gerar-minuta`) é absorvida pelo `PecaGeneratorModal`.
- **Uma análise de caso**: `IA.tsx` (análise) + `AnaliseEstrategica.tsx` + `TabResumo.analisarIA` → uma superfície, com o output estruturado da Análise Estratégica rodando pelo orchestrator governado.
- **Três "Ferramentas" com três nomes**: `/ferramentas` → "Catálogo de módulos"; aba de IA → "Skills de IA"; aba do caso → "Ações do caso".

**Backend — meta realista 162 → ~110 routers:**
| Cluster | De → para | Evidência |
|---|---|---|
| Honorários | `fees` + `honorarios_calc` + `honorarios_oab` + `exito_rateio` → `/fees` com sub-recursos | 4 prefixos para o mesmo objeto de negócio |
| Geração de peça | `peca_geracao` + `peca_geracao_router` + `motor_peca` + `templates` → 1 (+ renomear `peca_geracao_router.py` → `document_templates.py`) | homonímia enganosa no mesmo diretório |
| Teses/jurisprudência | 8 routers, 5 endpoints de busca sobrepostos → 2 | `teses*`, `victory_vault_router`, `matriz_teses`, `curadoria_renomada`, `precedentes_jurisprudencia`, `jurisprudencia_*` |
| Defesas | `defesas_revisoes` + `_avancado` + `_pacote_seguro` → 1 | conflito conceitual em `/pacote` |
| Validação de citações | `ia_citacoes` + `validador_juridico` + `qualidade` + `/ai/citacoes/verificar` → 1 | 4 endpoints para "a citação existe?" |
| DataJud | 4 superfícies → 2 | `datajud`, `andamentos`, `datajud_intelligence` (sem prefixo!), `integracoes/datajud` |
| Pipelines de IA | `analise_estrategica`, `ai_service.analisar_caso`, `ai_skill_service` → passar pelo `orchestrator.run` | hoje 3 caminhos escapam do citation gate e do carimbo HITL |
| Micro-routers | 26 arquivos <80 linhas absorvidos por domínio; resolver colisão de prefixo `/system-modules` (`main.py:424,426`) | — |

## 6. EXCLUIR

| Alvo | Justificativa |
|---|---|
| Rotas e arquivos `/legado/prazos|tarefas|intimacoes|suspensoes` | 1.774 linhas, zero links internos; redirects canônicos já cobrem favoritos |
| ~25 routers órfãos (~3.000 linhas): `consumidor_monitor` (315), `jurisprudencia_externa` (242), `google_drive_knowledge` (205), `anexos`, `calculadoras`, `whatsapp` (morto — `integration_status.py:287` declara `configured=False` incondicional), `matriz_teses`, `car`, `case_intelligence`, `qualidade`, `prompts.py` (`/prompts-biblioteca`, duplicata de `prompts_juridicos`), `cerebro`, `curadoria_renomada`, `precedentes_jurisprudencia`, `radar_legislativo` (a tela usa `/intelligence-v3/radar/legislativo` — `RadarLegislativo.tsx:28`), `veredito_ia_router`, `architecture`, `advogado_estilo`, `victory_vault_router`, `kit_documental`, endpoints órfãos de `ai.py` (`/dual`, `/caso/{id}/estrategia`, `/teses-ocultas`, `/preparar-audiencia`, `/detectar-prazos`) | Zero consumidores. **Exceções — conectar à UI em vez de excluir:** `export.py` (CSV/PDF prontos), `backup_admin.py` (backup sem interface é risco), `/ai/casos/{id}/assistente` (base do parecer unificado) |
| Shims: `Dashboard.tsx` (2 linhas), `ConhecimentoGovernado.tsx` (11 linhas), `teses_v4.py`, `data_room_v4.py`, rota `caso-jornada` + verbete na Ajuda | Indireções sem função; a Ajuda ensina tela extinta |
| `DashboardIA.tsx` (aba "Estado da IA") | Redundante com `PainelProvedoresIA` e a aba visão de `GovernancaIA` |

## 7. INCLUIR

**P0 — risco jurídico direto:**
1. **RAG sobre os documentos do caso** — indexar `Document.ocr_text` em `knowledge_chunks` com escopo por caso. A infraestrutura completa existe (`rag.py:274`, `ingestion_service.py:250`, filtro fail-closed por cliente). Sem isso, "a IA analisa meu caso" é promessa não cumprida — a lacuna funcional mais grave do sistema.
2. **Suspensões processuais por tribunal** no cálculo de prazos — o próprio `deadline_calculator.py:36-38` declara a lacuna ("continuam a cargo do advogado"). Entrada manual existe (`/suspensoes/simular`); falta ingestão de portarias (TJMG/TRT3). Risco nº 1: preclusão.
3. **Backup operável pela UI** — `backup_admin.py` órfão + `BACKUP_ENABLED=False` por default = escritório rodando sem backup e sem saber.

**P1 — alto valor, base já existe (barato):**
4. **Conflito de interesses como gate** na abertura de caso e cadastro de cliente — `POST /casos/verificar-conflito` já existe, fundamentado no EOAB, enterrado no router "Súmulas" (`sumulas.py:99-111`, `conflito_interesses.py`).
5. **Parecer estruturado por área** — o catálogo de skills por ramo existe (`ejc_skill_catalog.py:78-115`); falta o produto "parecer" com seções fixas (consulta → fatos → questões → fundamentação → jurisprudência verificada → conclusão → ressalvas).
6. **Versionamento de documentos na API** — o schema já suporta (`document.py:43-47`: `versao`, `versao_grupo_id`); faltam as rotas `/versoes` e a UI. Ligar ao comparador que já existe (`TabFerramentas.tsx:179-202`) para diff minuta IA × versão revisada.
7. **Alerta "peça aprovada e não protocolada perto do prazo"** — o registro de protocolo manual já existe com gate e auditoria (`legal_docs.py:572-595`).
8. **Relatório gerencial único do escritório** — os dados existem espalhados em 7 routers (metade órfãos); `RELATORIO_DONO_ENABLED` está `False`.
9. **Portal do cliente**: aba "Meus dados" (senha/contato), FAQ/glossário jurídico, badge de notificações (reusar o polling do `Layout.tsx:135-146`), contato do advogado responsável no dashboard.
10. **Flag para o Diário Oficial** — hoje é o único crawler diário ligado por padrão sem flag (`scheduler.py:1240`), contra o padrão do repositório.

**P2 — lacunas de domínio:**
11. Custas e preparo recursal (nenhum router; `calculadoras.py` órfão não cobre).
12. Entidade **Audiência** (pauta, preposto, ata, resultado) — hoje só um endpoint de IA órfão.
13. Sucumbência, RPV/precatório e cumprimento de sentença (o `exito_rateio` cobre só o rateio interno).
14. Timesheet com ciclo completo (timer, taxa-hora, aprovação, WIP) — hoje é apontamento manual.
15. Visão de carga/capacidade por advogado (casos e prazos por responsável, alerta de sobrecarga).
16. Trilha única de comunicação por cliente (hoje partida entre mensagens, portal, atendimentos e notificações) — dever de informação, art. 8º do Código de Ética.

---

## 8. Ordem de ataque sugerida

1. **Semana 1 (colheita baixa, impacto alto):** correções pontuais do §4.11, RBAC com feedback, Ajuda corrigida, exclusão dos `/legado/*` e shims.
2. **Sprint de parecer:** botão único no caso → `/ai/core/analyze` → salvar como `LegalDoc` → fila HITL com citation gate traduzido (itens 4.1–4.4). É o que transforma o EJC de "sistema com IA" em "IA que entrega parecer".
3. **Sprint de confiança:** RAG dos documentos do caso + suspensões por tribunal + backup na UI + gate de conflito (P0/P1 do §7).
4. **Consolidação contínua:** merges do §5 e exclusões do §6, um cluster por PR, seguindo a regra do `PLANO_SIMPLIFICACAO_EJC.md`: **conectar, não criar**.

Este relatório complementa (não substitui) o plano de simplificação vigente: as Fases 1–3 dele seguem válidas; os itens acima que coincidem foram mantidos e referenciados, e os demais são achados novos desta varredura.
