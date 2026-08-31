# MATRIZ DE ROTAS — EJC

> Gerado por `scripts/governanca/inventario-repo.sh` em 2026-08-30, commit `9fe3642d`.
> Divergencia entre backend e frontend nesta matriz e defeito P1.

## 1. Rotas declaradas no backend

| Metodo | Caminho | Arquivo |
|---|---|---|
| DELETE | `/admin-esp/{aid}` | `backend/app/routers/ramos_admin_esp.py:133` |
| DELETE | `/bancario/{bid}` | `backend/app/routers/ramos_bancario.py:131` |
| DELETE | `/civel/{cid}` | `backend/app/routers/ramos_civel.py:136` |
| DELETE | `/docs/{doc_id}` | `backend/app/routers/rag.py:415` |
| DELETE | `/drive/{file_id}` | `backend/app/routers/documents.py:1281` |
| DELETE | `/empresarial/{eid}` | `backend/app/routers/ramos_empresarial.py:139` |
| DELETE | `/keywords/{keyword_id}` | `backend/app/routers/diario_oficial.py:92` |
| DELETE | `/me/avatar` | `backend/app/routers/users.py:527` |
| DELETE | `/penal/{pid}` | `backend/app/routers/ramos_penal.py:124` |
| DELETE | `/push/subscriptions/{subscription_id}` | `backend/app/routers/notifications.py:272` |
| DELETE | `/settings/{module_key}` | `backend/app/routers/module_settings.py:139` |
| DELETE | `/socios/{socio_id}` | `backend/app/routers/sociedades_cliente.py:423` |
| DELETE | `/templates/{template_id}` | `backend/app/routers/checklists.py:180` |
| DELETE | `/templates/{template_id}` | `backend/app/routers/workflow.py:169` |
| DELETE | `/trabalhista-esp/{tid}` | `backend/app/routers/ramos_trabalhista_esp.py:126` |
| DELETE | `/{analise_id}` | `backend/app/routers/raio_x.py:744` |
| DELETE | `/{analysis_id}` | `backend/app/routers/bank_analysis.py:351` |
| DELETE | `/{area}` | `backend/app/routers/caso_areas.py:45` |
| DELETE | `/{atendimento_id}` | `backend/app/routers/atendimentos.py:1030` |
| DELETE | `/{case_id}/movimentos/{movimento_id}` | `backend/app/routers/cases.py:882` |
| DELETE | `/{case_id}` | `backend/app/routers/cases.py:640` |
| DELETE | `/{checklist_id}` | `backend/app/routers/checklists.py:456` |
| DELETE | `/{client_id}/pending-items/{item_id}` | `backend/app/routers/pending_items.py:265` |
| DELETE | `/{client_id}` | `backend/app/routers/clients.py:741` |
| DELETE | `/{contract_id}` | `backend/app/routers/office_contracts.py:133` |
| DELETE | `/{contrato_id}` | `backend/app/routers/contratos_societarios.py:341` |
| DELETE | `/{deadline_id}` | `backend/app/routers/deadlines.py:492` |
| DELETE | `/{despesa_id}` | `backend/app/routers/despesas.py:278` |
| DELETE | `/{doc_id}` | `backend/app/routers/documents.py:746` |
| DELETE | `/{doc_id}` | `backend/app/routers/legal_docs.py:1034` |
| DELETE | `/{entry_id}` | `backend/app/routers/timesheet.py:142` |
| DELETE | `/{env_id}` | `backend/app/routers/environmental.py:184` |
| DELETE | `/{etiqueta_id}` | `backend/app/routers/etiquetas.py:51` |
| DELETE | `/{evento_id}` | `backend/app/routers/agenda_eventos.py:241` |
| DELETE | `/{fee_id}` | `backend/app/routers/fees.py:288` |
| DELETE | `/{help_id}` | `backend/app/routers/module_help.py:130` |
| DELETE | `/{juri_id}` | `backend/app/routers/jurisprudencia_interna.py:177` |
| DELETE | `/{lancamento_id}` | `backend/app/routers/centro_custos.py:333` |
| DELETE | `/{mem_id}` | `backend/app/routers/memoria_institucional.py:171` |
| DELETE | `/{parte_id}` | `backend/app/routers/case_partes.py:131` |
| DELETE | `/{pid}` | `backend/app/routers/processes.py:195` |
| DELETE | `/{prompt_id}` | `backend/app/routers/prompts_juridicos.py:208` |
| DELETE | `/{prova_id}` | `backend/app/routers/provas.py:216` |
| DELETE | `/{provider_key}/{field_key}` | `backend/app/routers/credential_vault.py:382` |
| DELETE | `/{registro_id}` | `backend/app/routers/lgpd_registros.py:217` |
| DELETE | `/{room_id}/arquivos/{arquivo_id}` | `backend/app/routers/data_room.py:535` |
| DELETE | `/{room_id}/links/{link_id}` | `backend/app/routers/data_room.py:603` |
| DELETE | `/{room_id}` | `backend/app/routers/data_room.py:720` |
| DELETE | `/{sociedade_id}` | `backend/app/routers/sociedades_cliente.py:339` |
| DELETE | `/{suspensao_id}` | `backend/app/routers/suspensoes.py:116` |
| DELETE | `/{task_id}` | `backend/app/routers/tasks.py:180` |
| DELETE | `/{tese_id}` | `backend/app/routers/teses.py:395` |
| DELETE | `/{tpl_id}` | `backend/app/routers/templates.py:190` |
| DELETE | `/{user_id}` | `backend/app/routers/users.py:392` |
| DELETE | `/{withdrawal_id}` | `backend/app/routers/partner_withdrawals.py:175` |
| GET | `/` | `backend/app/routers/agenda_eventos.py:102` |
| GET | `/` | `backend/app/routers/audit.py:19` |
| GET | `/` | `backend/app/routers/bank_analysis.py:123` |
| GET | `/` | `backend/app/routers/cases.py:98` |
| GET | `/` | `backend/app/routers/clients.py:395` |
| GET | `/` | `backend/app/routers/dashboard.py:40` |
| GET | `/` | `backend/app/routers/deadlines.py:174` |
| GET | `/` | `backend/app/routers/documents.py:499` |
| GET | `/` | `backend/app/routers/environmental.py:74` |
| GET | `/` | `backend/app/routers/fees.py:72` |
| GET | `/` | `backend/app/routers/intimacoes.py:93` |
| GET | `/` | `backend/app/routers/legal_docs.py:335` |
| GET | `/` | `backend/app/routers/module_help.py:50` |
| GET | `/` | `backend/app/routers/notifications.py:64` |
| GET | `/` | `backend/app/routers/peca_geracao.py:342` |
| GET | `/` | `backend/app/routers/procuracoes.py:39` |
| GET | `/` | `backend/app/routers/raio_x.py:174` |
| GET | `/` | `backend/app/routers/signatures.py:138` |
| GET | `/` | `backend/app/routers/suspensoes.py:66` |
| GET | `/` | `backend/app/routers/tasks.py:45` |
| GET | `/` | `backend/app/routers/templates.py:67` |
| GET | `/` | `backend/app/routers/trash.py:87` |
| GET | `/` | `backend/app/routers/users.py:263` |
| GET | `/admin-esp/ferramentas/mandado-seguranca` | `backend/app/routers/ramos_vitrine.py:1388` |
| GET | `/admin-esp/ferramentas/reajuste-contrato-administrativo` | `backend/app/routers/ramos_ferramentas_complementares.py:395` |
| GET | `/admin-esp/ferramentas/recurso-multa-transito` | `backend/app/routers/ramos_admin_esp.py:233` |
| GET | `/admin-esp` | `backend/app/routers/ramos_admin_esp.py:96` |
| GET | `/advogado/{user_id}` | `backend/app/routers/extratos.py:46` |
| GET | `/agents` | `backend/app/routers/ai_core.py:205` |
| GET | `/alertas/nao-lidos/count` | `backend/app/routers/diario_oficial.py:166` |
| GET | `/alertas` | `backend/app/routers/diario_oficial.py:111` |
| GET | `/ambiental/ferramentas/auto-infracao-ambiental` | `backend/app/routers/ramos_ferramentas_complementares.py:874` |
| GET | `/ambiental/ferramentas/crimes-ambientais` | `backend/app/routers/ramos_ferramentas_complementares.py:955` |
| GET | `/ambiental/ferramentas/licenciamento` | `backend/app/routers/ramos_ferramentas_complementares.py:1075` |
| GET | `/ambiental/ferramentas/reserva-legal` | `backend/app/routers/ramos_ferramentas_complementares.py:1139` |
| GET | `/ambiental/ferramentas/tac-ambiental` | `backend/app/routers/ramos_ferramentas_complementares.py:1004` |
| GET | `/analise-vencedora/{caso_id}` | `backend/app/routers/curadoria_renomada.py:47` |
| GET | `/api/health/ready` | `backend/app/main.py:541` |
| GET | `/api/health` | `backend/app/main.py:518` |
| GET | `/audit` | `backend/app/routers/google_drive_knowledge.py:73` |
| GET | `/bancario/ferramentas/analise-juros` | `backend/app/routers/ramos_bancario.py:137` |
| GET | `/bancario/ferramentas/busca-apreensao` | `backend/app/routers/ramos_bancario.py:230` |
| GET | `/bancario/ferramentas/juros-abusivos` | `backend/app/routers/ramos_vitrine.py:1183` |
| GET | `/bancario/ferramentas/superendividamento` | `backend/app/routers/ramos_bancario.py:181` |
| GET | `/bancario/ferramentas/taxas-bacen` | `backend/app/routers/ramos_ferramentas_complementares.py:440` |
| GET | `/bancario` | `backend/app/routers/ramos_bancario.py:100` |
| GET | `/busca-avancada` | `backend/app/routers/teses.py:195` |
| GET | `/buscar/lexml` | `backend/app/routers/jurisprudencia_externa.py:55` |
| GET | `/buscar/tjmg` | `backend/app/routers/jurisprudencia_externa.py:70` |
| GET | `/buscar` | `backend/app/routers/jurisprudencia_externa.py:35` |
| GET | `/buscar` | `backend/app/routers/rag.py:350` |
| GET | `/buscar` | `backend/app/routers/sumulas.py:57` |
| GET | `/case-health/{case_id}` | `backend/app/routers/analytics.py:109` |
| GET | `/case-health` | `backend/app/routers/analytics.py:98` |
| GET | `/cases/{case_id}/provisionamento` | `backend/app/routers/honorarios_oab.py:482` |
| GET | `/cases/{case_id}/termo-consentimento-ia` | `backend/app/routers/compliance.py:134` |
| GET | `/cases/{case_id}/teto-etico` | `backend/app/routers/honorarios_oab.py:506` |
| GET | `/caso/{case_id}/resumo` | `backend/app/routers/centro_custos.py:179` |
| GET | `/casos.csv` | `backend/app/routers/export.py:67` |
| GET | `/casos/{case_id}.pdf` | `backend/app/routers/export.py:85` |
| GET | `/casos/{case_id}/alertas` | `backend/app/routers/visual_law.py:117` |
| GET | `/casos/{case_id}/matriz-risco` | `backend/app/routers/visual_law.py:87` |
| GET | `/casos/{case_id}/mensagens` | `backend/app/routers/portal.py:226` |
| GET | `/casos/{case_id}/proposta` | `backend/app/routers/honorarios_oab.py:412` |
| GET | `/casos/{case_id}/timeline` | `backend/app/routers/visual_law.py:46` |
| GET | `/casos/{case_id}` | `backend/app/routers/checklists.py:309` |
| GET | `/casos/{case_id}` | `backend/app/routers/portal.py:90` |
| GET | `/casos/{case_id}` | `backend/app/routers/teses.py:252` |
| GET | `/casos/{case_id}` | `backend/app/routers/timesheet.py:49` |
| GET | `/casos/{case_id}` | `backend/app/routers/workflow.py:188` |
| GET | `/chats` | `backend/app/routers/whatsapp.py:115` |
| GET | `/checklist` | `backend/app/routers/conversao_caso.py:247` |
| GET | `/civel/ferramentas/alimentos-calcular` | `backend/app/routers/ramos_civel.py:216` |
| GET | `/civel/ferramentas/calculo-dano-moral` | `backend/app/routers/ramos_ferramentas_complementares.py:122` |
| GET | `/civel/ferramentas/partilha-divorcio` | `backend/app/routers/ramos_ferramentas_complementares.py:234` |
| GET | `/civel/ferramentas/prazos-contestacao` | `backend/app/routers/ramos_civel.py:148` |
| GET | `/civel/ferramentas/prescricao-consumidor` | `backend/app/routers/ramos_ferramentas_complementares.py:57` |
| GET | `/civel/ferramentas/rescisao-locacao` | `backend/app/routers/ramos_ferramentas_complementares.py:266` |
| GET | `/civel/ferramentas/usucapiao-verificar` | `backend/app/routers/ramos_civel.py:267` |
| GET | `/civel` | `backend/app/routers/ramos_civel.py:103` |
| GET | `/clientes.csv` | `backend/app/routers/export.py:45` |
| GET | `/cobertura-mg-jec` | `backend/app/routers/jurimetria.py:743` |
| GET | `/cobertura-rag` | `backend/app/routers/jurimetria.py:732` |
| GET | `/cobertura` | `backend/app/routers/rag_governance.py:184` |
| GET | `/cofre/documentos/{document_id}/logs` | `backend/app/routers/novos_modulos.py:312` |
| GET | `/cofre/relatorio` | `backend/app/routers/novos_modulos.py:426` |
| GET | `/columns` | `backend/app/routers/kanban.py:44` |
| GET | `/companies/{client_id}` | `backend/app/modules/dpt360/router.py:75` |
| GET | `/consolidado` | `backend/app/routers/centro_custos.py:240` |
| GET | `/consolidado` | `backend/app/routers/financeiro_consolidado.py:44` |
| GET | `/consumidor/ferramentas/devolucao-dobro` | `backend/app/routers/ramos_vitrine.py:40` |
| GET | `/consumidor/ferramentas/negativacao-indevida` | `backend/app/routers/ramos_vitrine.py:1319` |
| GET | `/consumidor/ferramentas/prazos-cdc` | `backend/app/routers/ramos_vitrine.py:131` |
| GET | `/contextual/{case_id}` | `backend/app/routers/raio_x.py:255` |
| GET | `/contextual` | `backend/app/routers/ai_skills.py:223` |
| GET | `/contracts` | `backend/app/routers/architecture.py:59` |
| GET | `/custas-tjmg` | `backend/app/routers/calculadoras.py:153` |
| GET | `/dashboard` | `backend/app/modules/dpt360/router.py:42` |
| GET | `/dashboard` | `backend/app/routers/atendimentos.py:786` |
| GET | `/dashboard` | `backend/app/routers/ia_governanca.py:235` |
| GET | `/dashboard` | `backend/app/routers/ia_saude.py:136` |
| GET | `/desfechos` | `backend/app/routers/jurimetria.py:490` |
| GET | `/detalhado/{case_id}` | `backend/app/routers/extratos.py:19` |
| GET | `/diagnostico-sistema` | `backend/app/routers/module_help.py:65` |
| GET | `/digest-semanal` | `backend/app/routers/regulatorio.py:25` |
| GET | `/digital_lgpd/ferramentas/multa-lgpd` | `backend/app/routers/ramos_vitrine.py:467` |
| GET | `/digital_lgpd/ferramentas/prazos-lgpd` | `backend/app/routers/ramos_vitrine.py:509` |
| GET | `/distribuicao` | `backend/app/routers/gestao_societaria.py:260` |
| GET | `/docs/{doc_id}/comparar` | `backend/app/routers/rag_governance.py:377` |
| GET | `/docs/{doc_id}` | `backend/app/routers/rag_governance.py:193` |
| GET | `/docs` | `backend/app/routers/rag.py:383` |
| GET | `/documento-unico/{arquivo_id}/download` | `backend/app/routers/provas.py:666` |
| GET | `/documentos` | `backend/app/routers/portal.py:135` |
| GET | `/dossie/{case_id}` | `backend/app/routers/ai.py:91` |
| GET | `/drive/{file_id}/download` | `backend/app/routers/documents.py:1240` |
| GET | `/drive/{file_id}/link` | `backend/app/routers/documents.py:1215` |
| GET | `/due-diligence/templates` | `backend/app/routers/novos_modulos.py:257` |
| GET | `/empresa/{nome_empresa}` | `backend/app/routers/consumidor_monitor.py:167` |
| GET | `/empresarial/ferramentas/juros-mora` | `backend/app/routers/ramos_vitrine.py:930` |
| GET | `/empresarial/ferramentas/prazos-rj` | `backend/app/routers/ramos_empresarial.py:145` |
| GET | `/empresarial/ferramentas/verificar-cade` | `backend/app/routers/ramos_empresarial.py:223` |
| GET | `/empresarial/tipos` | `backend/app/routers/ramos_empresarial.py:103` |
| GET | `/empresarial` | `backend/app/routers/ramos_empresarial.py:114` |
| GET | `/empresas` | `backend/app/routers/consumidor_monitor.py:152` |
| GET | `/estado-operacional` | `backend/app/routers/ia_saude.py:212` |
| GET | `/expiring` | `backend/app/routers/office_contracts.py:46` |
| GET | `/export.csv` | `backend/app/routers/deadlines.py:218` |
| GET | `/export/csv` | `backend/app/routers/despesas.py:111` |
| GET | `/ext/benchmarks` | `backend/app/routers/jurimetria.py:561` |
| GET | `/ext/predicao/provimento` | `backend/app/routers/jurimetria.py:607` |
| GET | `/ext/stats` | `backend/app/routers/jurimetria.py:519` |
| GET | `/familia/ferramentas/debito-alimentos` | `backend/app/routers/ramos_vitrine.py:195` |
| GET | `/familia/ferramentas/itcmd-inventario` | `backend/app/routers/ramos_vitrine.py:650` |
| GET | `/files` | `backend/app/routers/google_drive_knowledge.py:53` |
| GET | `/financeiro` | `backend/app/routers/portal.py:162` |
| GET | `/fontes` | `backend/app/routers/ia_governanca.py:497` |
| GET | `/fontes` | `backend/app/routers/jurisprudencia_externa.py:210` |
| GET | `/funil` | `backend/app/routers/analytics.py:52` |
| GET | `/guardrails` | `backend/app/routers/ia_governanca.py:575` |
| GET | `/historico/{case_id}` | `backend/app/routers/ia_defensiva.py:98` |
| GET | `/honorarios.csv` | `backend/app/routers/export.py:187` |
| GET | `/imobiliario/ferramentas/distrato` | `backend/app/routers/ramos_vitrine.py:1214` |
| GET | `/imobiliario/ferramentas/prazos-despejo` | `backend/app/routers/ramos_vitrine.py:322` |
| GET | `/imobiliario/ferramentas/reajuste-aluguel` | `backend/app/routers/ramos_vitrine.py:271` |
| GET | `/impacto-regulatorio` | `backend/app/routers/teses.py:278` |
| GET | `/inadimplencia/alertas` | `backend/app/routers/novos_modulos.py:94` |
| GET | `/inss` | `backend/app/routers/calculadoras.py:80` |
| GET | `/integrations` | `backend/app/routers/system_modules.py:53` |
| GET | `/interno/analise-prospectiva` | `backend/app/routers/jurimetria.py:608` |
| GET | `/interno/benchmarks` | `backend/app/routers/jurimetria.py:562` |
| GET | `/interno/stats` | `backend/app/routers/jurimetria.py:520` |
| GET | `/irrf` | `backend/app/routers/calculadoras.py:89` |
| GET | `/itens` | `backend/app/routers/honorarios_oab.py:200` |
| GET | `/jurimetria` | `backend/app/routers/analytics.py:27` |
| GET | `/jurisprudencia-mg/geometria` | `backend/app/routers/ia_governanca.py:594` |
| GET | `/jurisprudencia-mg` | `backend/app/routers/ia_governanca.py:719` |
| GET | `/keywords` | `backend/app/routers/diario_oficial.py:63` |
| GET | `/list` | `backend/app/routers/ai_skills.py:260` |
| GET | `/logs/feedback/resumo` | `backend/app/routers/ai.py:380` |
| GET | `/logs/{log_id}/citacoes` | `backend/app/routers/ai.py:290` |
| GET | `/logs` | `backend/app/routers/ai.py:137` |
| GET | `/mapa` | `backend/app/routers/system_modules.py:41` |
| GET | `/matriz` | `backend/app/routers/provas.py:463` |
| GET | `/me/calendar-url` | `backend/app/routers/users.py:428` |
| GET | `/me/security` | `backend/app/routers/users.py:95` |
| GET | `/me/sessions` | `backend/app/routers/users.py:119` |
| GET | `/me/totp-qr` | `backend/app/routers/users.py:231` |
| GET | `/me/url` | `backend/app/routers/calendar_feed.py:102` |
| GET | `/me` | `backend/app/routers/advogado_estilo.py:21` |
| GET | `/me` | `backend/app/routers/users.py:89` |
| GET | `/memoria/{modalidade}` | `backend/app/routers/defesas_revisoes_avancado.py:485` |
| GET | `/mensagens/nao-lidas` | `backend/app/routers/portal.py:202` |
| GET | `/mensal` | `backend/app/routers/relatorio.py:27` |
| GET | `/meta` | `backend/app/routers/defesas_revisoes.py:242` |
| GET | `/meta` | `backend/app/routers/entrada_universal.py:282` |
| GET | `/meta` | `backend/app/routers/peca_geracao.py:76` |
| GET | `/meus-casos` | `backend/app/routers/portal.py:40` |
| GET | `/meus` | `backend/app/routers/atendimentos.py:724` |
| GET | `/modalidades` | `backend/app/routers/analise_bancaria.py:154` |
| GET | `/monitor-legislativo` | `backend/app/routers/rag.py:433` |
| GET | `/motor/async/{task_id}` | `backend/app/routers/teses.py:851` |
| GET | `/native-skills/coverage` | `backend/app/routers/ai_core.py:224` |
| GET | `/onboarding/{client_id}` | `backend/app/routers/analytics.py:81` |
| GET | `/onboarding` | `backend/app/routers/analytics.py:71` |
| GET | `/overview` | `backend/app/routers/jurimetria.py:69` |
| GET | `/painel-semanal` | `backend/app/routers/consumidor_monitor.py:278` |
| GET | `/parecer/{arquivo_id}/download` | `backend/app/routers/previdenciario_beneficio.py:230` |
| GET | `/peca/{arquivo_id}/download` | `backend/app/routers/ambiental_estrategia.py:237` |
| GET | `/penal/ferramentas/dosimetria` | `backend/app/routers/ramos_vitrine.py:724` |
| GET | `/penal/ferramentas/prazos-processuais` | `backend/app/routers/ramos_penal.py:130` |
| GET | `/penal/ferramentas/prescricao-penal` | `backend/app/routers/ramos_vitrine.py:702` |
| GET | `/penal/ferramentas/prescricao-punitiva` | `backend/app/routers/ramos_penal.py:262` |
| GET | `/penal/ferramentas/verificar-anpp` | `backend/app/routers/ramos_penal.py:184` |
| GET | `/penal` | `backend/app/routers/ramos_penal.py:96` |
| GET | `/perfis` | `backend/app/routers/ia_especializada.py:52` |
| GET | `/planilha/{arquivo_id}/download` | `backend/app/routers/trabalhista_liquidacao.py:335` |
| GET | `/por-advogado/{advogado_id}` | `backend/app/routers/atendimentos.py:751` |
| GET | `/por-area` | `backend/app/routers/jurimetria.py:134` |
| GET | `/por-magistrado` | `backend/app/routers/jurimetria.py:188` |
| GET | `/por-tese` | `backend/app/routers/jurimetria.py:303` |
| GET | `/por-tribunal` | `backend/app/routers/jurimetria.py:248` |
| GET | `/precificacao/calcular/{rule_id}` | `backend/app/routers/novos_modulos.py:48` |
| GET | `/precificacao/tabela` | `backend/app/routers/novos_modulos.py:37` |
| GET | `/preferences` | `backend/app/routers/notifications.py:150` |
| GET | `/prescricao/tipos` | `backend/app/routers/calculadoras.py:131` |
| GET | `/previdenciario/ferramentas/carencia` | `backend/app/routers/ramos_vitrine.py:583` |
| GET | `/previdenciario/ferramentas/prazos` | `backend/app/routers/ramos_vitrine.py:375` |
| GET | `/previdenciario/ferramentas/tempo-contribuicao` | `backend/app/routers/ramos_vitrine.py:551` |
| GET | `/produtividade` | `backend/app/routers/produtividade.py:28` |
| GET | `/prompts-sistema` | `backend/app/routers/ia_governanca.py:480` |
| GET | `/prompts` | `backend/app/routers/ia_governanca.py:463` |
| GET | `/provedores` | `backend/app/routers/ia_governanca.py:797` |
| GET | `/ptax` | `backend/app/routers/indices.py:83` |
| GET | `/push/subscriptions` | `backend/app/routers/notifications.py:252` |
| GET | `/push/vapid-key` | `backend/app/routers/notifications.py:244` |
| GET | `/qrcode` | `backend/app/routers/whatsapp.py:75` |
| GET | `/radar/legislativo` | `backend/app/routers/intelligence.py:18` |
| GET | `/radar/today` | `backend/app/modules/dpt360/router.py:112` |
| GET | `/radar` | `backend/app/routers/compliance.py:265` |
| GET | `/rag-curadoria` | `backend/app/routers/ia_governanca.py:376` |
| GET | `/ranking` | `backend/app/routers/teses.py:173` |
| GET | `/recentes` | `backend/app/routers/movimentos.py:15` |
| GET | `/regras-transicao` | `backend/app/routers/previdenciario_beneficio.py:81` |
| GET | `/relatorio-mensal` | `backend/app/routers/dashboard.py:225` |
| GET | `/relatorio/{arquivo_id}/download` | `backend/app/routers/tributario_fiscal.py:328` |
| GET | `/rentabilidade` | `backend/app/routers/analytics.py:61` |
| GET | `/reports/executive/{client_id}` | `backend/app/modules/dpt360/router.py:121` |
| GET | `/responsaveis` | `backend/app/routers/atendimentos.py:595` |
| GET | `/resumo` | `backend/app/routers/despesas.py:29` |
| GET | `/resumo` | `backend/app/routers/fees.py:121` |
| GET | `/ripd/{arquivo_id}/download` | `backend/app/routers/lgpd_registros.py:418` |
| GET | `/roi-por-area` | `backend/app/routers/produtividade.py:169` |
| GET | `/roteamento/preview` | `backend/app/routers/ai.py:557` |
| GET | `/routes` | `backend/app/routers/architecture.py:15` |
| GET | `/saude` | `backend/app/routers/rag_governance.py:175` |
| GET | `/semantic-audit` | `backend/app/routers/architecture.py:21` |
| GET | `/series` | `backend/app/routers/indices.py:58` |
| GET | `/settings` | `backend/app/routers/module_settings.py:58` |
| GET | `/skills` | `backend/app/routers/ai_core.py:218` |
| GET | `/socio/{user_id}` | `backend/app/routers/extratos.py:75` |
| GET | `/socios` | `backend/app/routers/gestao_societaria.py:94` |
| GET | `/solicitacoes-documentos` | `backend/app/routers/portal_documentos.py:64` |
| GET | `/solicitacoes-resumo` | `backend/app/routers/atendimentos.py:623` |
| GET | `/stats` | `backend/app/routers/atendimentos.py:818` |
| GET | `/stats` | `backend/app/routers/cases.py:163` |
| GET | `/stats` | `backend/app/routers/rag.py:35` |
| GET | `/stats` | `backend/app/routers/raio_x.py:138` |
| GET | `/status-captura` | `backend/app/routers/intimacoes.py:136` |
| GET | `/status` | `backend/app/routers/ai_core.py:230` |
| GET | `/status` | `backend/app/routers/ai_tools.py:58` |
| GET | `/status` | `backend/app/routers/backup_admin.py:100` |
| GET | `/status` | `backend/app/routers/cerebro.py:16` |
| GET | `/status` | `backend/app/routers/diario_oficial.py:47` |
| GET | `/status` | `backend/app/routers/google_drive_knowledge.py:31` |
| GET | `/status` | `backend/app/routers/ia_defensiva.py:50` |
| GET | `/status` | `backend/app/routers/infosimples_tjmg.py:66` |
| GET | `/status` | `backend/app/routers/nfse.py:355` |
| GET | `/status` | `backend/app/routers/rag.py:51` |
| GET | `/status` | `backend/app/routers/transparencia.py:46` |
| GET | `/status` | `backend/app/routers/validador_juridico.py:32` |
| GET | `/status` | `backend/app/routers/whatsapp.py:64` |
| GET | `/tabela` | `backend/app/routers/honorarios_oab.py:85` |
| GET | `/taskscore` | `backend/app/routers/analytics.py:43` |
| GET | `/taxa-juros` | `backend/app/routers/indices.py:65` |
| GET | `/taxa-media` | `backend/app/routers/analise_bancaria.py:181` |
| GET | `/templates` | `backend/app/routers/checklists.py:119` |
| GET | `/templates` | `backend/app/routers/workflow.py:112` |
| GET | `/tendencias` | `backend/app/routers/jurimetria.py:341` |
| GET | `/teses` | `backend/app/routers/cerebro.py:71` |
| GET | `/teses` | `backend/app/routers/curadoria_renomada.py:34` |
| GET | `/tipos-rescisao` | `backend/app/routers/calculadoras.py:59` |
| GET | `/tipos` | `backend/app/routers/documents.py:217` |
| GET | `/trabalhista-esp/ferramentas/deposito-recursal` | `backend/app/routers/ramos_trabalhista_esp.py:236` |
| GET | `/trabalhista-esp/ferramentas/horas-extras` | `backend/app/routers/ramos_vitrine.py:831` |
| GET | `/trabalhista-esp/ferramentas/prazos` | `backend/app/routers/ramos_trabalhista_esp.py:139` |
| GET | `/trabalhista-esp/ferramentas/prescricao-trabalhista` | `backend/app/routers/ramos_trabalhista_esp.py:183` |
| GET | `/trabalhista-esp/ferramentas/verbas-rescisorias` | `backend/app/routers/ramos_ferramentas_complementares.py:324` |
| GET | `/trabalhista-esp` | `backend/app/routers/ramos_trabalhista_esp.py:99` |
| GET | `/trabalhista/ferramentas/horas-extras` | `backend/app/routers/ramos_vitrine.py:895` |
| GET | `/transito/ferramentas/pontuacao-cnh` | `backend/app/routers/ramos_admin_esp.py:278` |
| GET | `/transito/ferramentas/prazos-recurso` | `backend/app/routers/ramos_admin_esp.py:254` |
| GET | `/transito/ferramentas/valor-multa` | `backend/app/routers/ramos_vitrine.py:1283` |
| GET | `/triagem-jec` | `backend/app/routers/consumidor_monitor.py:205` |
| GET | `/tribunais` | `backend/app/routers/suspensoes.py:60` |
| GET | `/tributario/ferramentas/auto-infracao-prazos` | `backend/app/routers/ramos_ferramentas_complementares.py:469` |
| GET | `/tributario/ferramentas/multa-mora` | `backend/app/routers/ramos_vitrine.py:1096` |
| GET | `/tributario/ferramentas/parcelamento` | `backend/app/routers/ramos_ferramentas_complementares.py:597` |
| GET | `/tributario/ferramentas/prescricao-decadencia` | `backend/app/routers/ramos_ferramentas_complementares.py:513` |
| GET | `/tributario/ferramentas/reforma-tributaria` | `backend/app/routers/ramos_ferramentas_complementares.py:820` |
| GET | `/tributario/ferramentas/regime-tributario` | `backend/app/routers/ramos_ferramentas_complementares.py:714` |
| GET | `/tributario/ferramentas/simples-nacional` | `backend/app/routers/ramos_ferramentas_complementares.py:660` |
| GET | `/uso-rotas` | `backend/app/routers/architecture.py:35` |
| GET | `/validar-cpf/{cpf}` | `backend/app/routers/utils.py:38` |
| GET | `/{analise_id}/conversao/preview` | `backend/app/routers/raio_x.py:685` |
| GET | `/{analise_id}/documentos/{documento_id}/download` | `backend/app/routers/raio_x.py:623` |
| GET | `/{analise_id}/exportar` | `backend/app/routers/raio_x.py:650` |
| GET | `/{analise_id}` | `backend/app/routers/raio_x.py:357` |
| GET | `/{analysis_id}/excel` | `backend/app/routers/bank_analysis.py:170` |
| GET | `/{analysis_id}` | `backend/app/routers/bank_analysis.py:147` |
| GET | `/{atendimento_id}/historico` | `backend/app/routers/atendimentos.py:875` |
| GET | `/{atendimento_id}` | `backend/app/routers/atendimentos.py:913` |
| GET | `/{batch_id}` | `backend/app/routers/entrada_universal.py:487` |
| GET | `/{case_id}/andamentos/status` | `backend/app/routers/andamentos.py:36` |
| GET | `/{case_id}/historico` | `backend/app/routers/dossie_estrategico.py:147` |
| GET | `/{case_id}/modulos` | `backend/app/routers/dossie_estrategico.py:128` |
| GET | `/{case_id}/movimentos` | `backend/app/routers/cases.py:783` |
| GET | `/{case_id}/teses-sugeridas` | `backend/app/routers/cases.py:1298` |
| GET | `/{case_id}/{dossie_id}/pdf` | `backend/app/routers/dossie_estrategico.py:214` |
| GET | `/{case_id}` | `backend/app/routers/cases.py:342` |
| GET | `/{case_id}` | `backend/app/routers/dossie_estrategico.py:90` |
| GET | `/{checklist_id}` | `backend/app/routers/checklists.py:335` |
| GET | `/{client_id}/dados-lgpd.json` | `backend/app/routers/clients.py:930` |
| GET | `/{client_id}/esquecimento/bloqueios` | `backend/app/routers/clients.py:989` |
| GET | `/{client_id}/pending-items` | `backend/app/routers/pending_items.py:167` |
| GET | `/{client_id}/relatorio-lgpd` | `backend/app/routers/clients.py:859` |
| GET | `/{client_id}/resumo` | `backend/app/routers/lgpd_registros.py:250` |
| GET | `/{client_id}` | `backend/app/routers/clients.py:593` |
| GET | `/{com_id}/prazo-sugerido` | `backend/app/routers/intimacoes.py:283` |
| GET | `/{contract_id}` | `backend/app/routers/office_contracts.py:90` |
| GET | `/{contrato_id}` | `backend/app/routers/contratos_societarios.py:244` |
| GET | `/{doc_id}/download` | `backend/app/routers/documents.py:650` |
| GET | `/{doc_id}/exportar-docx` | `backend/app/routers/legal_docs.py:1348` |
| GET | `/{doc_id}/jurisprudencia-check` | `backend/app/routers/legal_docs.py:629` |
| GET | `/{doc_id}/pdf-minuta` | `backend/app/routers/legal_docs.py:1117` |
| GET | `/{doc_id}/pdf` | `backend/app/routers/legal_docs.py:1170` |
| GET | `/{doc_id}/validacao` | `backend/app/routers/legal_docs.py:469` |
| GET | `/{doc_id}` | `backend/app/routers/documents.py:623` |
| GET | `/{doc_id}` | `backend/app/routers/legal_docs.py:448` |
| GET | `/{fee_id}/rateio` | `backend/app/routers/honorarios_oab.py:627` |
| GET | `/{indice}` | `backend/app/routers/indices.py:136` |
| GET | `/{juri_id}` | `backend/app/routers/jurisprudencia_interna.py:132` |
| GET | `/{mem_id}` | `backend/app/routers/memoria_institucional.py:124` |
| GET | `/{module_key:path}` | `backend/app/routers/module_help.py:82` |
| GET | `/{nota_id}/pdf` | `backend/app/routers/nfse.py:767` |
| GET | `/{nota_id}/xml` | `backend/app/routers/nfse.py:803` |
| GET | `/{nota_id}` | `backend/app/routers/nfse.py:740` |
| GET | `/{prompt_id}` | `backend/app/routers/prompts_juridicos.py:160` |
| GET | `/{provider_key}/{field_key}/historico` | `backend/app/routers/credential_vault.py:275` |
| GET | `/{room_id}` | `backend/app/routers/data_room.py:370` |
| GET | `/{session_id}/estado` | `backend/app/routers/legal_chat.py:190` |
| GET | `/{session_id}/exportar` | `backend/app/routers/legal_chat.py:380` |
| GET | `/{session_id}` | `backend/app/routers/legal_chat.py:113` |
| GET | `/{sig_id}/documento` | `backend/app/routers/signatures.py:208` |
| GET | `/{snapshot_id}` | `backend/app/routers/case_intelligence.py:77` |
| GET | `/{sociedade_id}` | `backend/app/routers/sociedades_cliente.py:273` |
| GET | `/{tese_id}/casos-candidatos` | `backend/app/routers/teses.py:412` |
| GET | `/{tese_id}` | `backend/app/routers/teses.py:359` |
| GET | `/{tpl_id}` | `backend/app/routers/templates.py:95` |
| GET | `/{user_id}/avatar` | `backend/app/routers/users.py:547` |
| PATCH | `/admin-esp/{aid}` | `backend/app/routers/ramos_admin_esp.py:127` |
| PATCH | `/alertas/{alerta_id}/marcar-lido` | `backend/app/routers/diario_oficial.py:148` |
| PATCH | `/bancario/{bid}` | `backend/app/routers/ramos_bancario.py:125` |
| PATCH | `/civel/{cid}` | `backend/app/routers/ramos_civel.py:130` |
| PATCH | `/cofre/documentos/{document_id}/sensibilidade` | `backend/app/routers/novos_modulos.py:395` |
| PATCH | `/docs/{doc_id}` | `backend/app/routers/rag_governance.py:205` |
| PATCH | `/empresarial/{eid}` | `backend/app/routers/ramos_empresarial.py:133` |
| PATCH | `/historico/{log_id}/status` | `backend/app/routers/ia_defensiva.py:146` |
| PATCH | `/inadimplencia/alertas/{alert_id}/resolver` | `backend/app/routers/novos_modulos.py:124` |
| PATCH | `/logs/{log_id}/hitl` | `backend/app/routers/ai.py:212` |
| PATCH | `/penal/{pid}` | `backend/app/routers/ramos_penal.py:118` |
| PATCH | `/rag-curadoria/{doc_id}` | `backend/app/routers/ia_governanca.py:435` |
| PATCH | `/socios/{socio_id}` | `backend/app/routers/gestao_societaria.py:141` |
| PATCH | `/socios/{socio_id}` | `backend/app/routers/sociedades_cliente.py:399` |
| PATCH | `/trabalhista-esp/{tid}` | `backend/app/routers/ramos_trabalhista_esp.py:120` |
| PATCH | `/{analise_id}` | `backend/app/routers/raio_x.py:369` |
| PATCH | `/{atendimento_id}` | `backend/app/routers/atendimentos.py:928` |
| PATCH | `/{case_id}/movimentos/{movimento_id}` | `backend/app/routers/cases.py:843` |
| PATCH | `/{case_id}/{dossie_id}/aprovar` | `backend/app/routers/dossie_estrategico.py:169` |
| PATCH | `/{case_id}` | `backend/app/routers/cases.py:363` |
| PATCH | `/{checklist_id}/itens/{item_id}/marcar` | `backend/app/routers/checklists.py:358` |
| PATCH | `/{client_id}/pending-items/{item_id}` | `backend/app/routers/pending_items.py:229` |
| PATCH | `/{client_id}` | `backend/app/routers/clients.py:669` |
| PATCH | `/{contract_id}` | `backend/app/routers/office_contracts.py:103` |
| PATCH | `/{contrato_id}` | `backend/app/routers/contratos_societarios.py:276` |
| PATCH | `/{deadline_id}/confirmar` | `backend/app/routers/deadlines.py:440` |
| PATCH | `/{deadline_id}` | `backend/app/routers/deadlines.py:369` |
| PATCH | `/{despesa_id}` | `backend/app/routers/despesas.py:229` |
| PATCH | `/{doc_id}/aprovar` | `backend/app/routers/legal_docs.py:681` |
| PATCH | `/{doc_id}/protocolo` | `backend/app/routers/legal_docs.py:921` |
| PATCH | `/{doc_id}/publicacao-portal` | `backend/app/routers/documents.py:912` |
| PATCH | `/{doc_id}` | `backend/app/routers/documents.py:807` |
| PATCH | `/{doc_id}` | `backend/app/routers/legal_docs.py:521` |
| PATCH | `/{env_id}` | `backend/app/routers/environmental.py:143` |
| PATCH | `/{evento_id}` | `backend/app/routers/agenda_eventos.py:176` |
| PATCH | `/{fee_id}` | `backend/app/routers/fees.py:191` |
| PATCH | `/{help_id}` | `backend/app/routers/module_help.py:111` |
| PATCH | `/{juri_id}` | `backend/app/routers/jurisprudencia_interna.py:153` |
| PATCH | `/{lancamento_id}` | `backend/app/routers/centro_custos.py:311` |
| PATCH | `/{mem_id}` | `backend/app/routers/memoria_institucional.py:141` |
| PATCH | `/{parte_id}` | `backend/app/routers/case_partes.py:153` |
| PATCH | `/{pid}` | `backend/app/routers/processes.py:79` |
| PATCH | `/{prompt_id}` | `backend/app/routers/prompts_juridicos.py:177` |
| PATCH | `/{prova_id}` | `backend/app/routers/provas.py:185` |
| PATCH | `/{registro_id}` | `backend/app/routers/lgpd_registros.py:196` |
| PATCH | `/{room_id}/arquivos/{arquivo_id}/publicacao` | `backend/app/routers/data_room.py:480` |
| PATCH | `/{session_id}/estado` | `backend/app/routers/legal_chat.py:169` |
| PATCH | `/{session_id}` | `backend/app/routers/legal_chat.py:133` |
| PATCH | `/{sociedade_id}` | `backend/app/routers/sociedades_cliente.py:315` |
| PATCH | `/{task_id}` | `backend/app/routers/tasks.py:120` |
| PATCH | `/{tese_id}` | `backend/app/routers/teses.py:375` |
| PATCH | `/{user_id}` | `backend/app/routers/users.py:321` |
| PATCH | `/{withdrawal_id}/approve` | `backend/app/routers/partner_withdrawals.py:94` |
| PATCH | `/{withdrawal_id}/pay` | `backend/app/routers/partner_withdrawals.py:147` |
| PATCH | `/{withdrawal_id}/reject` | `backend/app/routers/partner_withdrawals.py:123` |
| POST | `/` | `backend/app/routers/agenda_eventos.py:138` |
| POST | `/` | `backend/app/routers/cases.py:228` |
| POST | `/` | `backend/app/routers/clients.py:451` |
| POST | `/` | `backend/app/routers/deadlines.py:263` |
| POST | `/` | `backend/app/routers/environmental.py:100` |
| POST | `/` | `backend/app/routers/fees.py:152` |
| POST | `/` | `backend/app/routers/legal_docs.py:410` |
| POST | `/` | `backend/app/routers/module_help.py:98` |
| POST | `/` | `backend/app/routers/procuracoes.py:78` |
| POST | `/` | `backend/app/routers/raio_x.py:223` |
| POST | `/` | `backend/app/routers/signatures.py:50` |
| POST | `/` | `backend/app/routers/suspensoes.py:89` |
| POST | `/` | `backend/app/routers/tasks.py:86` |
| POST | `/` | `backend/app/routers/templates.py:114` |
| POST | `/` | `backend/app/routers/timesheet.py:75` |
| POST | `/` | `backend/app/routers/users.py:285` |
| POST | `/abusividade` | `backend/app/routers/analise_bancaria.py:254` |
| POST | `/admin-esp` | `backend/app/routers/ramos_admin_esp.py:103` |
| POST | `/adversarial` | `backend/app/routers/defesas_revisoes_avancado.py:221` |
| POST | `/agente/stream` | `backend/app/routers/ia_agente.py:35` |
| POST | `/alterar-senha` | `backend/app/routers/auth.py:532` |
| POST | `/analisar-caso` | `backend/app/routers/ai.py:58` |
| POST | `/analisar-contrato` | `backend/app/routers/ai.py:1062` |
| POST | `/analisar-decisao` | `backend/app/routers/defesas_revisoes_avancado.py:450` |
| POST | `/analisar-url` | `backend/app/routers/documento_ia.py:207` |
| POST | `/analisar-xml` | `backend/app/routers/tributario_fiscal.py:106` |
| POST | `/analisar` | `backend/app/routers/defesas_revisoes.py:259` |
| POST | `/analisar` | `backend/app/routers/documento_ia.py:106` |
| POST | `/analisar` | `backend/app/routers/entrada.py:48` |
| POST | `/analisar` | `backend/app/routers/ia_defensiva.py:176` |
| POST | `/analise-estrategica` | `backend/app/routers/cerebro.py:20` |
| POST | `/analise-impacto` | `backend/app/routers/intelligence.py:36` |
| POST | `/analise-prospectiva` | `backend/app/routers/jurimetria.py:386` |
| POST | `/analyze` | `backend/app/routers/ai_core.py:147` |
| POST | `/aplicar-acoes` | `backend/app/routers/documento_ia.py:284` |
| POST | `/atualizar-valor` | `backend/app/routers/indices.py:103` |
| POST | `/auditar-peca` | `backend/app/routers/ai.py:476` |
| POST | `/bancario` | `backend/app/routers/ramos_bancario.py:107` |
| POST | `/breakeven` | `backend/app/routers/visual_law.py:143` |
| POST | `/buscar` | `backend/app/routers/precedentes_jurisprudencia.py:36` |
| POST | `/calcular-especialidade` | `backend/app/routers/defesas_revisoes_avancado.py:287` |
| POST | `/calcular` | `backend/app/routers/deadlines.py:111` |
| POST | `/calcular` | `backend/app/routers/score_juridico.py:54` |
| POST | `/calcular` | `backend/app/routers/trabalhista_liquidacao.py:139` |
| POST | `/capturar-agora` | `backend/app/routers/intimacoes.py:466` |
| POST | `/cases/{case_id}/sync-prazos` | `backend/app/routers/datajud.py:109` |
| POST | `/cases/{case_id}/sync` | `backend/app/routers/datajud.py:67` |
| POST | `/caso/{case_id}/estrategia` | `backend/app/routers/ai.py:947` |
| POST | `/caso/{case_id}/faturar` | `backend/app/routers/timesheet.py:93` |
| POST | `/caso/{case_id}/gerar-ia` | `backend/app/routers/checklists.py:278` |
| POST | `/caso/{case_id}/visual-law` | `backend/app/routers/ai.py:905` |
| POST | `/casos/{case_id}/analise-completa` | `backend/app/routers/intake.py:361` |
| POST | `/casos/{case_id}/aplicar-padrao` | `backend/app/routers/workflow.py:276` |
| POST | `/casos/{case_id}/assistente` | `backend/app/routers/ai.py:631` |
| POST | `/casos/{case_id}/avancar` | `backend/app/routers/workflow.py:367` |
| POST | `/casos/{case_id}/concluir` | `backend/app/routers/workflow.py:468` |
| POST | `/casos/{case_id}/dual` | `backend/app/routers/ai.py:767` |
| POST | `/casos/{case_id}/iniciar` | `backend/app/routers/workflow.py:228` |
| POST | `/casos/{case_id}/mensagens` | `backend/app/routers/portal.py:252` |
| POST | `/casos/{case_id}/proposta/sugerir` | `backend/app/routers/honorarios_oab.py:361` |
| POST | `/casos/{case_id}/proposta` | `backend/app/routers/honorarios_oab.py:379` |
| POST | `/cet` | `backend/app/routers/analise_bancaria.py:219` |
| POST | `/chat` | `backend/app/routers/ai_core.py:109` |
| POST | `/checar-conflito` | `backend/app/routers/clients.py:235` |
| POST | `/citacoes/verificar` | `backend/app/routers/ai.py:35` |
| POST | `/civel` | `backend/app/routers/ramos_civel.py:110` |
| POST | `/cobranca` | `backend/app/routers/pix.py:61` |
| POST | `/cofre/documentos/{document_id}/registrar-acesso` | `backend/app/routers/novos_modulos.py:342` |
| POST | `/comparar-documentos` | `backend/app/routers/defesas_revisoes_avancado.py:190` |
| POST | `/consistencia` | `backend/app/routers/qualidade.py:74` |
| POST | `/contrato` | `backend/app/routers/analise_bancaria.py:117` |
| POST | `/correcao-monetaria` | `backend/app/routers/calculadoras.py:101` |
| POST | `/critica-adversarial` | `backend/app/routers/ia_adversarial.py:42` |
| POST | `/curadoria/apply` | `backend/app/routers/google_drive_knowledge.py:115` |
| POST | `/curadoria/preview` | `backend/app/routers/google_drive_knowledge.py:92` |
| POST | `/deep-research/juridica` | `backend/app/routers/peca_geracao.py:401` |
| POST | `/demonstrativo` | `backend/app/routers/peca_geracao.py:488` |
| POST | `/detectar-prazos` | `backend/app/routers/ai.py:1093` |
| POST | `/distribuicao/{dist_id}/aprovar` | `backend/app/routers/gestao_societaria.py:288` |
| POST | `/distribuicao` | `backend/app/routers/gestao_societaria.py:185` |
| POST | `/docs/{doc_id}/revisar` | `backend/app/routers/rag_governance.py:300` |
| POST | `/docs/{doc_id}/testar` | `backend/app/routers/rag_governance.py:359` |
| POST | `/documento-unico` | `backend/app/routers/provas.py:604` |
| POST | `/docx` | `backend/app/routers/export.py:155` |
| POST | `/drive/upload` | `backend/app/routers/documents.py:1064` |
| POST | `/due-diligence/template` | `backend/app/routers/sociedades_cliente.py:156` |
| POST | `/due-diligence/templates` | `backend/app/routers/novos_modulos.py:286` |
| POST | `/emitir` | `backend/app/routers/nfse.py:569` |
| POST | `/empresarial` | `backend/app/routers/ramos_empresarial.py:122` |
| POST | `/entrevista` | `backend/app/routers/triagem_entrevista.py:51` |
| POST | `/estimar` | `backend/app/routers/honorarios_oab.py:94` |
| POST | `/evolution` | `backend/app/routers/evolution_webhook.py:67` |
| POST | `/executar` | `backend/app/routers/ai_tools.py:73` |
| POST | `/executar` | `backend/app/routers/backup_admin.py:27` |
| POST | `/execute-doc` | `backend/app/routers/ai_skills.py:309` |
| POST | `/execute` | `backend/app/routers/ai_skills.py:269` |
| POST | `/ext/ingerir/datajud` | `backend/app/routers/jurimetria.py:712` |
| POST | `/ext/predicao/treinar` | `backend/app/routers/jurimetria.py:696` |
| POST | `/faq` | `backend/app/routers/conteudo.py:60` |
| POST | `/fontes/tjmg/coletar` | `backend/app/routers/ia_governanca.py:526` |
| POST | `/frontend-error` | `backend/app/routers/observabilidade.py:27` |
| POST | `/gateway/health` | `backend/app/routers/ai.py:548` |
| POST | `/generate` | `backend/app/routers/ai_core.py:167` |
| POST | `/gerar-minuta` | `backend/app/routers/ai.py:1266` |
| POST | `/gerar` | `backend/app/routers/anexos.py:108` |
| POST | `/gerar` | `backend/app/routers/peca_geracao.py:103` |
| POST | `/glossario` | `backend/app/routers/conteudo.py:79` |
| POST | `/importar-env` | `backend/app/routers/credential_vault.py:291` |
| POST | `/importar-lote` | `backend/app/routers/jurisprudencia_externa.py:154` |
| POST | `/importar` | `backend/app/routers/jurisprudencia_externa.py:84` |
| POST | `/inadimplencia/varrer` | `backend/app/routers/novos_modulos.py:109` |
| POST | `/ingerir-ai-log/{log_id}` | `backend/app/routers/rag.py:600` |
| POST | `/ingerir-seed` | `backend/app/routers/sumulas.py:29` |
| POST | `/ingest-pdf` | `backend/app/routers/rag.py:176` |
| POST | `/ingest-url` | `backend/app/routers/rag.py:223` |
| POST | `/ingest` | `backend/app/routers/rag.py:326` |
| POST | `/instanciar` | `backend/app/routers/checklists.py:199` |
| POST | `/itens/{item_id}/encerrar-vigencia` | `backend/app/routers/honorarios_oab.py:274` |
| POST | `/itens` | `backend/app/routers/honorarios_oab.py:220` |
| POST | `/jurisprudencia-mg/extrair-url` | `backend/app/routers/ia_governanca.py:681` |
| POST | `/jurisprudencia-mg` | `backend/app/routers/ia_governanca.py:618` |
| POST | `/jurisprudencia/pesquisa` | `backend/app/routers/cerebro.py:76` |
| POST | `/keywords` | `backend/app/routers/diario_oficial.py:78` |
| POST | `/ler-todas` | `backend/app/routers/notifications.py:212` |
| POST | `/login` | `backend/app/routers/auth.py:177` |
| POST | `/logout` | `backend/app/routers/auth.py:513` |
| POST | `/logs/{log_id}/feedback` | `backend/app/routers/ai.py:342` |
| POST | `/manual` | `backend/app/routers/nfse.py:402` |
| POST | `/me/avatar` | `backend/app/routers/users.py:498` |
| POST | `/me/sessions/revoke-others` | `backend/app/routers/users.py:154` |
| POST | `/me/sessions/{session_id}/revoke` | `backend/app/routers/users.py:191` |
| POST | `/messages` | `backend/app/routers/whatsapp.py:132` |
| POST | `/motor/async` | `backend/app/routers/teses.py:815` |
| POST | `/motor` | `backend/app/routers/teses.py:757` |
| POST | `/pacote` | `backend/app/routers/defesas_revisoes_pacote_seguro.py:175` |
| POST | `/parecer-pdf` | `backend/app/routers/previdenciario_beneficio.py:204` |
| POST | `/peca-conversao` | `backend/app/routers/ambiental_estrategia.py:213` |
| POST | `/penal` | `backend/app/routers/ramos_penal.py:103` |
| POST | `/persistir` | `backend/app/routers/defesas_revisoes_avancado.py:349` |
| POST | `/pesquisar` | `backend/app/routers/ai.py:1320` |
| POST | `/planilha-pdf` | `backend/app/routers/trabalhista_liquidacao.py:311` |
| POST | `/pre-preencher` | `backend/app/routers/ficha_triagem.py:97` |
| POST | `/precificacao/regras` | `backend/app/routers/novos_modulos.py:78` |
| POST | `/predicao-exito` | `backend/app/routers/jurimetria.py:385` |
| POST | `/preencher-minimo` | `backend/app/routers/module_help.py:74` |
| POST | `/preparar-audiencia` | `backend/app/routers/ai.py:526` |
| POST | `/prescricao` | `backend/app/routers/calculadoras.py:141` |
| POST | `/preview` | `backend/app/routers/anexos.py:75` |
| POST | `/processar` | `backend/app/routers/entrada_universal.py:367` |
| POST | `/propostas/{proposta_id}/aprovar` | `backend/app/routers/honorarios_oab.py:433` |
| POST | `/propostas/{proposta_id}/rejeitar` | `backend/app/routers/honorarios_oab.py:448` |
| POST | `/push/subscribe` | `backend/app/routers/notifications.py:303` |
| POST | `/razoes` | `backend/app/routers/anexos.py:131` |
| POST | `/recalcular` | `backend/app/routers/indice_risco.py:48` |
| POST | `/recuperar-senha` | `backend/app/routers/auth.py:631` |
| POST | `/redefinir-senha` | `backend/app/routers/auth.py:659` |
| POST | `/refresh` | `backend/app/routers/auth.py:343` |
| POST | `/reindex/{file_id}` | `backend/app/routers/google_drive_knowledge.py:181` |
| POST | `/relatorio-pdf` | `backend/app/routers/tributario_fiscal.py:302` |
| POST | `/report` | `backend/app/routers/ai_core.py:185` |
| POST | `/resolver` | `backend/app/routers/clients.py:99` |
| POST | `/resumir-documento` | `backend/app/routers/ai.py:117` |
| POST | `/resumir-texto` | `backend/app/routers/ai.py:1229` |
| POST | `/seed` | `backend/app/routers/rag.py:488` |
| POST | `/send` | `backend/app/routers/whatsapp.py:86` |
| POST | `/simular-adversario` | `backend/app/routers/qualidade.py:90` |
| POST | `/simular` | `backend/app/routers/ambiental_estrategia.py:90` |
| POST | `/simular` | `backend/app/routers/suspensoes.py:141` |
| POST | `/socios` | `backend/app/routers/gestao_societaria.py:113` |
| POST | `/solicitacoes-documentos/itens/{item_id}/upload` | `backend/app/routers/portal_documentos.py:125` |
| POST | `/sugerir-faltantes` | `backend/app/routers/provas.py:380` |
| POST | `/sugerir-ia` | `backend/app/routers/teses.py:528` |
| POST | `/sugerir-tipo` | `backend/app/routers/documents.py:248` |
| POST | `/sugestao-honorarios` | `backend/app/routers/ai.py:1385` |
| POST | `/sync` | `backend/app/routers/google_drive_knowledge.py:156` |
| POST | `/task` | `backend/app/routers/ai_core.py:127` |
| POST | `/templates` | `backend/app/routers/checklists.py:148` |
| POST | `/templates` | `backend/app/routers/workflow.py:140` |
| POST | `/teses-ocultas` | `backend/app/routers/ai.py:450` |
| POST | `/teses/sincronizar` | `backend/app/routers/curadoria_renomada.py:39` |
| POST | `/teses/{tese_id}/aprovar` | `backend/app/routers/matriz_teses.py:109` |
| POST | `/teses/{tese_id}/descartar` | `backend/app/routers/matriz_teses.py:121` |
| POST | `/testes-juridicos` | `backend/app/routers/rag_governance.py:390` |
| POST | `/totp/desativar` | `backend/app/routers/auth.py:802` |
| POST | `/totp/setup` | `backend/app/routers/auth.py:681` |
| POST | `/totp/verificar` | `backend/app/routers/auth.py:727` |
| POST | `/trabalhista-esp` | `backend/app/routers/ramos_trabalhista_esp.py:106` |
| POST | `/trabalhista/rescisao` | `backend/app/routers/calculadoras.py:65` |
| POST | `/traduzir-andamento` | `backend/app/routers/ai.py:1197` |
| POST | `/transcribe-media` | `backend/app/routers/ai_skills.py:460` |
| POST | `/upload` | `backend/app/routers/bank_analysis.py:38` |
| POST | `/upload` | `backend/app/routers/documents.py:315` |
| POST | `/validar-citacoes` | `backend/app/routers/ia_citacoes.py:28` |
| POST | `/validar` | `backend/app/routers/validador_juridico.py:50` |
| POST | `/verificar-citacoes` | `backend/app/routers/qualidade.py:67` |
| POST | `/verificar-conflito` | `backend/app/routers/clients.py:173` |
| POST | `/verificar-conflito` | `backend/app/routers/sumulas.py:100` |
| POST | `/viabilidade` | `backend/app/routers/defesas_revisoes_avancado.py:256` |
| POST | `/{analise_id}/arquivar` | `backend/app/routers/raio_x.py:712` |
| POST | `/{analise_id}/converter` | `backend/app/routers/raio_x.py:695` |
| POST | `/{analise_id}/descartar` | `backend/app/routers/raio_x.py:728` |
| POST | `/{analise_id}/reanalisar` | `backend/app/routers/raio_x.py:528` |
| POST | `/{analysis_id}/documento` | `backend/app/routers/bank_analysis.py:187` |
| POST | `/{analysis_id}/gerar-peca` | `backend/app/routers/bank_analysis.py:266` |
| POST | `/{batch_id}/preparar-pacote` | `backend/app/routers/entrada_universal.py:518` |
| POST | `/{batch_id}/vincular-caso` | `backend/app/routers/entrada_universal.py:610` |
| POST | `/{case_id}/analisar` | `backend/app/routers/cases.py:1408` |
| POST | `/{case_id}/aplicar-extracao` | `backend/app/routers/cases.py:1099` |
| POST | `/{case_id}/arquivar` | `backend/app/routers/cases.py:505` |
| POST | `/{case_id}/desarquivar` | `backend/app/routers/cases.py:544` |
| POST | `/{case_id}/encerrar` | `backend/app/routers/cases.py:973` |
| POST | `/{case_id}/gerar-documentos` | `backend/app/routers/cases.py:744` |
| POST | `/{case_id}/gerar` | `backend/app/routers/dossie_estrategico.py:66` |
| POST | `/{case_id}/movimentos` | `backend/app/routers/cases.py:808` |
| POST | `/{case_id}/reabrir` | `backend/app/routers/cases.py:586` |
| POST | `/{case_id}/sincronizar-processo` | `backend/app/routers/cases.py:916` |
| POST | `/{checklist_id}/itens` | `backend/app/routers/checklists.py:422` |
| POST | `/{client_id}/criar-acesso` | `backend/app/routers/clients.py:803` |
| POST | `/{client_id}/esquecimento` | `backend/app/routers/clients.py:1011` |
| POST | `/{client_id}/ia-analise` | `backend/app/routers/clients.py:611` |
| POST | `/{client_id}/pending-items` | `backend/app/routers/pending_items.py:185` |
| POST | `/{client_id}/ripd` | `backend/app/routers/lgpd_registros.py:374` |
| POST | `/{com_id}/aceitar-prazo` | `backend/app/routers/intimacoes.py:298` |
| POST | `/{com_id}/processar` | `backend/app/routers/intimacoes.py:229` |
| POST | `/{com_id}/recusar-prazo` | `backend/app/routers/intimacoes.py:428` |
| POST | `/{com_id}/sugerir-prazo` | `backend/app/routers/intimacoes.py:273` |
| POST | `/{contrato_id}/transicao` | `backend/app/routers/contratos_societarios.py:301` |
| POST | `/{deadline_id}/ciencia` | `backend/app/routers/deadlines.py:466` |
| POST | `/{doc_id}/conferir-e-assinar` | `backend/app/routers/legal_docs.py:740` |
| POST | `/{doc_id}/revisar` | `backend/app/routers/legal_docs.py:643` |
| POST | `/{doc_id}/validar` | `backend/app/routers/legal_docs.py:483` |
| POST | `/{entidade}/{registro_id}/purgar` | `backend/app/routers/trash.py:170` |
| POST | `/{entidade}/{registro_id}/restaurar` | `backend/app/routers/trash.py:128` |
| POST | `/{fee_id}/pagamentos` | `backend/app/routers/fees.py:230` |
| POST | `/{fee_id}/rateio` | `backend/app/routers/honorarios_oab.py:638` |
| POST | `/{juri_id}/classificar-ia` | `backend/app/routers/jurisprudencia_interna.py:197` |
| POST | `/{key_id}/revogar` | `backend/app/routers/api_keys.py:94` |
| POST | `/{nota_id}/cancelar` | `backend/app/routers/nfse.py:839` |
| POST | `/{notif_id}/ler` | `backend/app/routers/notifications.py:195` |
| POST | `/{perfil}` | `backend/app/routers/ia_especializada.py:67` |
| POST | `/{pid}/arquivar` | `backend/app/routers/processes.py:135` |
| POST | `/{pid}/desarquivar` | `backend/app/routers/processes.py:169` |
| POST | `/{pid}/principal` | `backend/app/routers/processes.py:109` |
| POST | `/{proc_id}/minuta` | `backend/app/routers/procuracoes.py:103` |
| POST | `/{proc_id}/revogar` | `backend/app/routers/procuracoes.py:160` |
| POST | `/{prompt_id}/executar` | `backend/app/routers/prompts_juridicos.py:228` |
| POST | `/{provider_key}/testar` | `backend/app/routers/credential_vault.py:314` |
| POST | `/{provider_key}/{field_key}` | `backend/app/routers/credential_vault.py:341` |
| POST | `/{rascunho_id}/criar-caso` | `backend/app/routers/entrada.py:101` |
| POST | `/{room_id}/arquivos` | `backend/app/routers/data_room.py:435` |
| POST | `/{room_id}/links` | `backend/app/routers/data_room.py:560` |
| POST | `/{session_id}/saida` | `backend/app/routers/legal_chat.py:419` |
| POST | `/{sig_id}/assinar` | `backend/app/routers/signatures.py:277` |
| POST | `/{sociedade_id}/eventos` | `backend/app/routers/sociedades_cliente.py:452` |
| POST | `/{sociedade_id}/socios` | `backend/app/routers/sociedades_cliente.py:356` |
| POST | `/{tese_id}/vincular-caso` | `backend/app/routers/teses.py:498` |
| POST | `/{tpl_id}/gerar` | `backend/app/routers/templates.py:130` |
| PUT | `/preferences` | `backend/app/routers/notifications.py:159` |

## 2. Registro de routers em main.py

```
334:app.include_router(agenda_eventos.router, prefix=API)
335:app.include_router(ai.router, prefix=API)
336:app.include_router(ai_core.router, prefix=API)
337:app.include_router(anexos.router, prefix=API)
338:app.include_router(ai_skills.router, prefix=API)
339:app.include_router(ai_tools.router, prefix=API)
340:app.include_router(analise_bancaria.router, prefix=API)
341:app.include_router(analytics.router, prefix=API)
342:app.include_router(andamentos.router, prefix=API)
343:app.include_router(areas.router, prefix=API)
344:app.include_router(atendimentos.router, prefix=API)
345:app.include_router(atividades.router, prefix=API)
346:app.include_router(audit.router, prefix=API)
347:app.include_router(auth.router, prefix=API)
348:app.include_router(backup_admin.router, prefix=API)
349:app.include_router(bank_analysis.router, prefix=API)
350:app.include_router(calculadoras.router, prefix=API)
351:app.include_router(calendar_feed.router, prefix=API)
352:app.include_router(case_intelligence.router, prefix=API)
353:app.include_router(case_partes.router, prefix=API)
354:app.include_router(cases.router, prefix=API)
355:app.include_router(caso_areas.router, prefix=API)
356:app.include_router(centro_custos.router, prefix=API)
357:app.include_router(cerebro.router, prefix=API)
358:app.include_router(checklists.router, prefix=API)
359:app.include_router(clients.router, prefix=API)
360:app.include_router(compliance.router, prefix=API)
361:app.include_router(consumidor_monitor.router, prefix=API)
362:app.include_router(conteudo.router, prefix=API)
363:app.include_router(contratos_societarios.router, prefix=API)
364:app.include_router(conversao_caso.router, prefix=API)
365:app.include_router(credential_vault.router, prefix=API)  # cofre de credenciais (superadmin)
366:app.include_router(curadoria_renomada.router, prefix=API)
367:app.include_router(dashboard.router, prefix=API)
368:app.include_router(dpt360_router, prefix=API)
369:app.include_router(data_room.router, prefix=API)
370:app.include_router(datajud.router, prefix=API)
371:app.include_router(deadlines.router, prefix=API)
372:app.include_router(despesas.router, prefix=API)
373:app.include_router(diario_oficial.router, prefix=API)
374:app.include_router(documento_ia.router, prefix=API)
375:app.include_router(raio_x.router, prefix=API)
376:app.include_router(legal_chat.router, prefix=API)
377:app.include_router(documents.router, prefix=API)
378:app.include_router(dossie_cliente.router, prefix=API)
379:app.include_router(dossie_estrategico.router, prefix=API)
380:app.include_router(environmental.router, prefix=API)
381:app.include_router(etiquetas.router, prefix=API)  # P3: prefixo canônico /etiquetas no router
382:app.include_router(etiquetas.casos_router, prefix=API)
383:app.include_router(evolution_webhook.router, prefix=API)
384:app.include_router(export.router, prefix=API)
385:app.include_router(extratos.router, prefix=API)
386:app.include_router(fees.router, prefix=API)
387:app.include_router(financeiro_consolidado.router, prefix=API)
388:app.include_router(gestao_societaria.router, prefix=API)
389:app.include_router(google_drive_knowledge.router, prefix=API)  # /api/rag/google-drive/* (curadoria da base, piso admin/socio)
390:app.include_router(ia_adversarial.router, prefix=API)
391:app.include_router(ia_agente.router, prefix=API)
392:app.include_router(ia_citacoes.router, prefix=API)
393:app.include_router(ia_defensiva.router, prefix=API)
394:app.include_router(ia_especializada.router, prefix=API)
395:app.include_router(ia_governanca.router, prefix=API)
396:app.include_router(ia_saude.router, prefix=API)
397:app.include_router(ia_saude.router_status, prefix=API)  # GET /api/ia/status
398:app.include_router(indice_risco.router, prefix=API)
399:app.include_router(indices.router, prefix=API)  # Índices oficiais BCB (SGS + Olinda) — Bloco 1 das APIs públicas
400:app.include_router(infosimples_receita.router, prefix=API)
401:app.include_router(infosimples_tjmg.router, prefix=API)
402:app.include_router(car.router, prefix=API)  # CAR/SICAR via Infosimples (consulta paga, reuso do conector)
403:app.include_router(transparencia.router, prefix=API)  # CGU sanções CEIS/CNEP/CEPIM — GATED (default off)
405:app.include_router(nfse.router, prefix=API)  # NFS-e (emissão fiscal GATED, homologação) — migração 085
406:app.include_router(intimacoes.router, prefix=API)
407:app.include_router(jurimetria.router, prefix=API)
408:app.include_router(juris_import.router, prefix=API)
409:app.include_router(jurisprudencia_externa.router, prefix=API)
410:app.include_router(jurisprudencia_interna.router, prefix=API)
411:app.include_router(kanban.router, prefix=API)  # P3: prefixo /kanban no router
412:app.include_router(kanban.casos_router, prefix=API)
413:app.include_router(kit_documental.router, prefix=API)  # POST /api/cases/{id}/kit-documental (P0.3)
414:app.include_router(legal_docs.router, prefix=API)
415:app.include_router(matriz_teses.router, prefix=API)  # FASE 3 Orquestrador — Matriz de Teses (migração 102)
416:app.include_router(orquestrador.router, prefix=API)  # FASE 5 Orquestrador — máquina de estados do caso
417:app.include_router(memoria_institucional.router, prefix=API)
418:app.include_router(honorarios_oab.router, prefix=API)  # frontend: /api/honorarios-oab/estimar (EstimadorHonorarios)
419:app.include_router(intake.router, prefix=API)  # frontend: /api/intake/casos/{id}/analise-completa (IntakeAnalise)
420:app.include_router(triagem_entrevista.router, prefix=API)  # frontend: /api/triagem/entrevista (EntrevistaInteligente — Jornada etapa 2)
421:app.include_router(entrada.router, prefix=API)  # Entrada Única (Bloco 3): /api/entrada/analisar + /api/entrada/{id}/criar-caso
422:app.include_router(ficha_triagem.router, prefix=API)  # frontend: /api/triagem/ficha (Ficha de Triagem pré-peça — gate de geração)
423:app.include_router(mensagens.router, prefix=API)
424:app.include_router(module_help.router, prefix=API)  # frontend: /api/module-help/* (HelpButton)
425:app.include_router(motor_peca.router, prefix=API)  # P1: Motor de Peça — /api/cases/{id}/motor-peca/*
426:app.include_router(movimentos.router, prefix=API)
427:app.include_router(noticias.router, prefix=API)
428:app.include_router(notifications.router, prefix=API)
429:app.include_router(novos_modulos.router, prefix=API)  # P3: prefixo /modulos no router
430:app.include_router(entrada_universal.router, prefix=API) # P3: registro explícito (antes: routers/__init__.py montava dentro de novos_modulos)
431:app.include_router(defesas_revisoes.router, prefix=API)
432:app.include_router(defesas_revisoes_pacote_seguro.router, prefix=API)
433:app.include_router(defesas_revisoes_avancado.router, prefix=API)
434:app.include_router(novos_modulos.casos_router, prefix=API)
435:app.include_router(observabilidade.router, prefix=API)
436:app.include_router(office_contracts.router, prefix=API)
437:app.include_router(partner_withdrawals.router, prefix=API)
438:app.include_router(peca_geracao.router, prefix=API)
439:app.include_router(pending_items.router, prefix=API)
440:app.include_router(pix.router, prefix=API)
441:app.include_router(portal.router, prefix=API)
442:app.include_router(portal_documentos.router, prefix=API)  # Portal: solicitações de documentos + upload (migration 084)
443:app.include_router(solicitacoes_documentos.router, prefix=API)  # advogado: solicitação de documentos ao cliente (migration 084)
444:app.include_router(processes.router, prefix=API)  # P3: prefixo /processes no router
445:app.include_router(processes.casos_router, prefix=API)
446:app.include_router(procuracoes.router, prefix=API)
447:app.include_router(produtividade.router, prefix=API)
448:app.include_router(prompts_juridicos.router, prefix=API)
449:app.include_router(qualidade.router, prefix=API)
450:app.include_router(rag.router, prefix=API)
451:app.include_router(rag_public.router, prefix=API)      # API pública (X-API-Key)
460:app.include_router(                       # antes: jurisprudencia_externa.include_router(...)
462:app.include_router(                       # antes: peca_geracao.include_router(...)
464:app.include_router(                       # antes: append em rag.router.routes (prefixo absoluto)
466:app.include_router(intelligence.router, prefix=API)  # Intelligence canônico (consolidação: intelligence_v3 → intelligence)
467:app.include_router(                       # P3: prefixo canônico /datajud/intelligence (antes: andamentos.include_router + /casos)
469:app.include_router(                       # P3: rotas de caso /{case_id}/andamentos/* mantidas sob /casos
471:app.include_router(api_keys_router.router, prefix=API) # admin de chaves (JWT admin)
472:app.include_router(regulatorio.router, prefix=API)
473:app.include_router(radar_legislativo.router, prefix=API)  # Câmara+Senado+ALMG
474:app.include_router(ramos.router, prefix=API)
475:app.include_router(previdenciario_beneficio.router, prefix=API)  # vertical Previdenciário — regras de transição EC 103/2019 + RMI
476:app.include_router(relatorio.router, prefix=API)
477:app.include_router(relatorio_cliente.router, prefix=API)
478:app.include_router(score_juridico.router, prefix=API)
479:app.include_router(search.router, prefix=API)
480:app.include_router(signatures.router, prefix=API)
481:app.include_router(sociedades_cliente.router, prefix=API)  # gestão societária de CLIENTES (vertical Empresarial)
482:app.include_router(provas.router, prefix=API)  # Gestão de Provas por caso + Documento Único de Anexos (Visual Law)
483:app.include_router(processo_eletronico.router, prefix=API)  # Processo Eletrônico MNI 2.2.2 (Issue #762, Fase A leitura)
484:app.include_router(lgpd_registros.router, prefix=API)  # vertical LGPD — ROPA (art. 37) por cliente + RIPD (art. 38)
485:app.include_router(sumulas.router, prefix=API)  # P3: prefixo /sumulas no router
486:app.include_router(sumulas.casos_router, prefix=API)
487:app.include_router(suspensoes.router, prefix=API)
488:app.include_router(system_modules.router, prefix=API)  # Mapa de Módulos — governança modular
489:app.include_router(diagnostico.router, prefix=API)  # Central Eletrônica de Diagnóstico
490:app.include_router(module_settings.router, prefix=API)  # Lifecycle auditável dos módulos
491:app.include_router(tributario_fiscal.router, prefix=API)  # vertical Tributário — XML fiscal + recuperação de créditos
492:app.include_router(trabalhista_liquidacao.router, prefix=API)  # vertical Trabalhista — liquidação de sentença (ADC 58 / Selic real BCB)
493:app.include_router(ambiental_estrategia.router, prefix=API)  # vertical Ambiental — simulador de estratégia do auto de infração
494:app.include_router(tasks.router, prefix=API)
495:app.include_router(templates.router, prefix=API)
496:app.include_router(teses.router, prefix=API)
497:app.include_router(timesheet.router, prefix=API)
498:app.include_router(trash.router, prefix=API)
499:app.include_router(users.router, prefix=API)
500:app.include_router(utils.router, prefix=API)
501:app.include_router(validador_juridico.router, prefix=API)
502:app.include_router(visual_law.router, prefix=API)
503:app.include_router(whatsapp.router, prefix=API)
504:app.include_router(workflow.router, prefix=API)
505:app.include_router(architecture.router, prefix=API)
508:app.include_router(integracoes.datajud_router, prefix=API)
509:app.include_router(integracoes.djen_router, prefix=API)
510:app.include_router(integracoes.brasilapi_router, prefix=API)
```

> Todos os routers do EJC sao registrados manualmente em `backend/app/main.py`
> sob o prefixo `API = "/api"`. Router nao registrado la nao existe em runtime.

## 3. Chamadas de API no frontend

| Caminho chamado | Arquivo |
|---|---|
| `/api/${slug}` | `frontend/src/pages/ramos/FichaEspecializada.reset.test.tsx:47` |
| `/api/agenda-eventos/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1096` |
| `/api/agenda-eventos/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1263` |
| `/api/agenda-eventos/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1326` |
| `/api/agenda-eventos/` | `frontend/src/components/ContextualAIAssistant.tsx:272` |
| `/api/agenda-eventos/` | `frontend/src/pages/AgendaDia.tsx:130` |
| `/api/agenda-eventos/` | `frontend/src/pages/CentralAtividades.tsx:973` |
| `/api/agenda-eventos/` | `frontend/src/pages/DashboardUltra.tsx:280` |
| `/api/agenda-eventos` | `frontend/src/config/moduleRegistry.tsx:456` |
| `/api/agenda-eventos` | `frontend/src/config/moduleRegistry.tsx:474` |
| `/api/ai/analisar-caso` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:443` |
| `/api/ai/analisar-caso` | `frontend/src/pages/IA.tsx:98` |
| `/api/ai/analisar-contrato` | `frontend/src/pages/CasoDetalhe/TabFerramentas.tsx:232` |
| `/api/ai/analisar-contrato` | `frontend/src/pages/CasoDetalhe/TabFerramentas.tsx:255` |
| `/api/ai/auditar-peca` | `frontend/src/pages/Pecas.tsx:635` |
| `/api/ai/core` | `frontend/src/config/moduleRegistry.tsx:569` |
| `/api/ai/dossie/${caseId}` | `frontend/src/pages/IA.tsx:83` |
| `/api/ai/gerar-minuta` | `frontend/src/pages/AssistenteIA.tsx:93` |
| `/api/ai/gerar-minuta` | `frontend/src/pages/ramos/RamoAnalise.tsx:305` |
| `/api/ai/logs/${id}/hitl` | `frontend/src/pages/IA.tsx:157` |
| `/api/ai/logs/${result.ai_log_id}/feedback` | `frontend/src/components/ContextualAIAssistant.tsx:290` |
| `/api/ai/logs/${result.ai_log_id}/hitl` | `frontend/src/components/ContextualAIAssistant.tsx:226` |
| `/api/ai/logs` | `frontend/src/pages/IA.tsx:58` |
| `/api/ai/pesquisar` | `frontend/src/pages/AssistenteIA.tsx:83` |
| `/api/ai/resumir-documento` | `frontend/src/pages/IA.tsx:119` |
| `/api/ai/resumir-texto` | `frontend/src/pages/AssistenteIA.tsx:85` |
| `/api/ai/skills/execute-doc` | `frontend/src/components/ContextualAIAssistant.tsx:197` |
| `/api/ai/skills/execute-doc` | `frontend/src/pages/FerramentasIA.tsx:261` |
| `/api/ai/skills/execute` | `frontend/src/components/ContextualAIAssistant.tsx:199` |
| `/api/ai/skills/execute` | `frontend/src/pages/FerramentasIA.tsx:264` |
| `/api/ai/skills/execute` | `frontend/src/pages/RaioXProcesso.tsx:771` |
| `/api/ai/skills/transcribe-media` | `frontend/src/pages/FerramentasIA.tsx:259` |
| `/api/ai/skills` | `frontend/src/config/moduleRegistry.tsx:353` |
| `/api/ai/skills` | `frontend/src/config/moduleRegistry.tsx:569` |
| `/api/ai/sugestao-honorarios` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:423` |
| `/api/ai/traduzir-andamento` | `frontend/src/pages/AssistenteIA.tsx:87` |
| `/api/ai` | `frontend/src/config/moduleRegistry.tsx:335` |
| `/api/ai` | `frontend/src/config/moduleRegistry.tsx:569` |
| `/api/ambiental/estrategia/peca-conversao` | `frontend/src/components/AmbientalEstrategia.tsx:255` |
| `/api/analise-bancaria/abusividade` | `frontend/src/components/RevisaoBancariaDeterministica.tsx:69` |
| `/api/analise-bancaria/cet` | `frontend/src/components/RevisaoBancariaDeterministica.tsx:110` |
| `/api/analise-bancaria/taxa-media` | `frontend/src/pages/ramos/RamoAnalise.tsx:92` |
| `/api/analytics/funil` | `frontend/src/pages/CentralRelacionamento.tsx:124` |
| `/api/analytics/produtividade/export-event` | `frontend/src/pages/Produtividade.tsx:146` |
| `/api/analytics` | `frontend/src/config/moduleRegistry.tsx:457` |
| `/api/api/v1/casos/${id}` | `frontend/src/lib/api.prefixo.test.ts:153` |
| `/api/atendimentos/${followUp.id}` | `frontend/src/pages/DossieCliente.tsx:672` |
| `/api/atendimentos/${item.id}` | `frontend/src/components/ClientServiceTimeline.tsx:400` |
| `/api/atendimentos/${item.id}` | `frontend/src/components/ClientServiceTimeline.tsx:425` |
| `/api/atendimentos/responsaveis` | `frontend/src/pages/DossieCliente.tsx:1119` |
| `/api/atendimentos` | `frontend/src/components/ClientServiceTimeline.tsx:368` |
| `/api/atendimentos` | `frontend/src/pages/DossieCliente.tsx:1098` |
| `/api/atividades` | `frontend/src/config/moduleRegistry.tsx:455` |
| `/api/atividades` | `frontend/src/config/moduleRegistry.tsx:474` |
| `/api/atividades` | `frontend/src/pages/AgendaDia.tsx:129` |
| `/api/atividades` | `frontend/src/pages/CentralAtividades.tsx:972` |
| `/api/atividades` | `frontend/src/pages/DashboardUltra.tsx:279` |
| `/api/audit` | `frontend/src/config/moduleRegistry.tsx:749` |
| `/api/auth/alterar-senha` | `frontend/src/pages/TrocarSenha.tsx:33` |
| `/api/auth/logout` | `frontend/src/lib/api.ts:424` |
| `/api/auth/recuperar-senha` | `frontend/src/pages/RecuperarSenha.tsx:10` |
| `/api/auth/redefinir-senha` | `frontend/src/pages/RedefinirSenha.tsx:26` |
| `/api/auth/refresh` | `frontend/src/lib/api.prefixo.test.ts:173` |
| `/api/auth/refresh` | `frontend/src/lib/api.ts:44` |
| `/api/auth/totp/desativar` | `frontend/src/components/AccountSecurity.tsx:130` |
| `/api/auth/totp/verificar` | `frontend/src/components/AccountSecurity.tsx:109` |
| `/api/bank-analysis/${analiseSel}/gerar-peca` | `frontend/src/components/BancarioForense.tsx:564` |
| `/api/bank-analysis/${res.analise.id}/excel` | `frontend/src/components/AnaliseExtratos.tsx:92` |
| `/api/bank-analysis/${res.analise.id}/gerar-peca` | `frontend/src/components/AnaliseExtratos.tsx:153` |
| `/api/bank-analysis/upload` | `frontend/src/components/AnaliseExtratos.tsx:79` |
| `/api/calendar/me/rotate` | `frontend/src/components/SecurityMenu.tsx:131` |
| `/api/calendar/me/url` | `frontend/src/components/SecurityMenu.tsx:115` |
| `/api/cases/${caseId}/analisar` | `frontend/src/components/AnaliseEstrategica.tsx:172` |
| `/api/cases/${caseId}/areas/${area.area}` | `frontend/src/components/CaseCommandDock.tsx:116` |
| `/api/cases/${caseId}/areas` | `frontend/src/components/CaseCommandDock.tsx:69` |
| `/api/cases/${caseId}/areas` | `frontend/src/components/CaseCommandDock.tsx:94` |
| `/api/cases/${caseId}/converter-judicial` | `frontend/src/components/ConversaoChecklist.tsx:89` |
| `/api/cases/${caseId}/documentos/${docId}/vincular` | `frontend/src/pages/CasoDetalhe/TabDocumentos.tsx:155` |
| `/api/cases/${caseId}/documentos/candidatos` | `frontend/src/pages/CasoDetalhe/TabDocumentos.tsx:129` |
| `/api/cases/${caseId}/etiquetas/${id}` | `frontend/src/pages/CasoDetalhe.tsx:475` |
| `/api/cases/${caseId}/etiquetas` | `frontend/src/pages/CasoDetalhe.tsx:469` |
| `/api/cases/${caseId}/etiquetas` | `frontend/src/pages/CasoDetalhe.tsx:486` |
| `/api/cases/${caseId}/indice-risco/recalcular` | `frontend/src/pages/CasoDetalhe/TabRisco.tsx:58` |
| `/api/cases/${caseId}/kanban` | `frontend/src/pages/Kanban.tsx:111` |
| `/api/cases/${caseId}/mensagens` | `frontend/src/pages/CasoDetalhe.tsx:377` |
| `/api/cases/${caseId}/motor-peca/analisar` | `frontend/src/components/DefesasRevisoesPanel.tsx:272` |
| `/api/cases/${caseId}/movimentos` | `frontend/src/pages/CasoDetalhe/TabTimeline.tsx:68` |
| `/api/cases/${caseId}/partes/${id}` | `frontend/src/pages/CasoDetalhe/TabPartes.tsx:51` |
| `/api/cases/${caseId}/partes` | `frontend/src/pages/CasoDetalhe/TabPartes.tsx:40` |
| `/api/cases/${caseId}/processes` | `frontend/src/pages/CasoDetalhe/TabProcessos.tsx:59` |
| `/api/cases/${caseId}/score-juridico/calcular` | `frontend/src/pages/CasoDetalhe/TabScore.tsx:29` |
| `/api/cases/${caseId}` | `frontend/src/pages/CasoDetalhe/CaseDocumentActions.tsx:86` |
| `/api/cases/${caso.id}/areas/${a}` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:160` |
| `/api/cases/${caso.id}/areas` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:153` |
| `/api/cases/${caso.id}/arquivar` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:333` |
| `/api/cases/${caso.id}/desarquivar` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:231` |
| `/api/cases/${caso.id}/desarquivar` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:345` |
| `/api/cases/${caso.id}/encerrar` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:393` |
| `/api/cases/${caso.id}/gerar-documentos` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:409` |
| `/api/cases/${caso.id}/movimentos` | `frontend/src/components/ContextualAIAssistant.tsx:248` |
| `/api/cases/${caso.id}/movimentos` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:461` |
| `/api/cases/${caso.id}/reabrir` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:237` |
| `/api/cases/${caso.id}/sincronizar-processo` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:501` |
| `/api/cases/${caso.id}` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:363` |
| `/api/cases/${caso.id}` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:479` |
| `/api/cases/${casoSelecionado}/movimentos` | `frontend/src/pages/ramos/RamoAnalise.tsx:284` |
| `/api/cases/${delCaso.id}` | `frontend/src/pages/Casos.tsx:486` |
| `/api/cases/${id}/desarquivar` | `frontend/src/pages/Casos.tsx:463` |
| `/api/cases/${id}` | `frontend/src/stores/caseContext.ts:64` |
| `/api/cases/${loteCaso}/documentos/${d.id}/vincular` | `frontend/src/pages/Documentos.tsx:589` |
| `/api/cases/` | `frontend/src/components/DefesasRevisoesPanel.tsx:163` |
| `/api/cases/` | `frontend/src/components/NovoCasoWizard.tsx:210` |
| `/api/cases/` | `frontend/src/components/__tests__/FlowEnhancements.test.ts:38` |
| `/api/cases/` | `frontend/src/pages/CadastroManual.tsx:601` |
| `/api/cases/` | `frontend/src/pages/Casos.tsx:633` |
| `/api/cases/` | `frontend/src/pages/Kanban.tsx:75` |
| `/api/cases/` | `frontend/src/pages/Pecas.tsx:500` |
| `/api/cases/` | `frontend/src/pages/ramos/RamoBase.tsx:541` |
| `/api/cases/stats` | `frontend/src/components/Dashboards.tsx:373` |
| `/api/cases` | `frontend/src/config/moduleRegistry.tsx:184` |
| `/api/cases` | `frontend/src/config/moduleRegistry.tsx:200` |
| `/api/cases` | `frontend/src/config/moduleRegistry.tsx:216` |
| `/api/cases` | `frontend/src/config/moduleRegistry.tsx:256` |
| `/api/cases` | `frontend/src/config/moduleRegistry.tsx:303` |
| `/api/cases` | `frontend/src/config/moduleRegistry.tsx:369` |
| `/api/cases` | `frontend/src/pages/SalaJuridica.tsx:766` |
| `/api/casos/${caseId}/provas/${atual.id}` | `frontend/src/components/ProvasCaso.tsx:417` |
| `/api/casos/${caseId}/provas/${editId}` | `frontend/src/components/ProvasCaso.tsx:370` |
| `/api/casos/${caseId}/provas/${excluirId}` | `frontend/src/components/ProvasCaso.tsx:397` |
| `/api/casos/${caseId}/provas/${outro.id}` | `frontend/src/components/ProvasCaso.tsx:420` |
| `/api/casos/${caseId}/provas/documento-unico` | `frontend/src/components/ProvasCaso.tsx:436` |
| `/api/casos/${caseId}/provas` | `frontend/src/components/ProvasCaso.tsx:376` |
| `/api/casos/${caseId}/solicitacoes-documentos` | `frontend/src/pages/CasoDetalhe/CaseDocumentActions.tsx:129` |
| `/api/casos/${caseId}/solicitacoes-documentos` | `frontend/src/pages/CasoDetalhe/CaseDocumentActions.tsx:88` |
| `/api/casos` | `frontend/src/lib/api.prefixo.test.ts:5` |
| `/api/checklists/${ckId}/itens/${itemId}/marcar` | `frontend/src/pages/CasoDetalhe.tsx:191` |
| `/api/checklists/caso/${caseId}/gerar-ia` | `frontend/src/pages/CasoDetalhe.tsx:179` |
| `/api/checklists/templates/${id}` | `frontend/src/pages/Checklists.tsx:70` |
| `/api/checklists/templates` | `frontend/src/pages/Checklists.tsx:51` |
| `/api/checklists` | `frontend/src/config/moduleRegistry.tsx:551` |
| `/api/clients/${clientId}/criar-acesso` | `frontend/src/pages/DossieCliente.tsx:1163` |
| `/api/clients/${clientId}/pending-items/${id}` | `frontend/src/pages/DossieCliente.tsx:347` |
| `/api/clients/${clientId}/pending-items/${pendenteExcluir}` | `frontend/src/pages/DossieCliente.tsx:365` |
| `/api/clients/${clientId}/pending-items` | `frontend/src/pages/DossieCliente.tsx:288` |
| `/api/clients/${clientId}/pending-items` | `frontend/src/pages/DossieCliente.tsx:320` |
| `/api/clients/${clientId}/relatorio-financeiro` | `frontend/src/pages/DossieCliente.tsx:807` |
| `/api/clients/${clientId}` | `frontend/src/pages/DossieCliente.tsx:1051` |
| `/api/clients/${clientId}` | `frontend/src/pages/DossieCliente.tsx:1118` |
| `/api/clients/${leadId}` | `frontend/src/pages/CRMLeads.tsx:157` |
| `/api/clients/1` | `frontend/src/lib/api.prefixo.test.ts:154` |
| `/api/clients/` | `frontend/src/components/NovoCasoWizard.tsx:122` |
| `/api/clients/` | `frontend/src/components/NovoCasoWizard.tsx:164` |
| `/api/clients/` | `frontend/src/pages/CRMLeads.tsx:111` |
| `/api/clients/` | `frontend/src/pages/CRMLeads.tsx:128` |
| `/api/clients/` | `frontend/src/pages/CadastroManual.tsx:486` |
| `/api/clients/` | `frontend/src/pages/CadastroManual.tsx:587` |
| `/api/clients/` | `frontend/src/pages/CentralRelacionamento.tsx:125` |
| `/api/clients/` | `frontend/src/pages/CentralRelacionamento.tsx:126` |
| `/api/clients/` | `frontend/src/pages/Clientes.tsx:130` |
| `/api/clients/` | `frontend/src/pages/DashboardUltra.tsx:281` |
| `/api/clients/resolver` | `frontend/src/pages/Casos.tsx:620` |
| `/api/clients/{client_id}/dossie` | `frontend/src/config/moduleRegistry.tsx:285` |
| `/api/clients` | `frontend/src/config/moduleRegistry.tsx:184` |
| `/api/clients` | `frontend/src/config/moduleRegistry.tsx:200` |
| `/api/clients` | `frontend/src/config/moduleRegistry.tsx:216` |
| `/api/clients` | `frontend/src/config/moduleRegistry.tsx:237` |
| `/api/clients` | `frontend/src/config/moduleRegistry.tsx:256` |
| `/api/clients` | `frontend/src/config/moduleRegistry.tsx:269` |
| `/api/clients` | `frontend/src/config/moduleRegistry.tsx:285` |
| `/api/clients` | `frontend/src/config/moduleRegistry.tsx:303` |
| `/api/clients` | `frontend/src/config/moduleRegistry.tsx:458` |
| `/api/clients` | `frontend/src/pages/SalaJuridica.tsx:639` |
| `/api/compliance/radar` | `frontend/src/config/moduleRegistry.tsx:647` |
| `/api/conhecimento/importar-jurisprudencia` | `frontend/src/pages/Conhecimento.tsx:619` |
| `/api/dashboard/` | `frontend/src/components/Dashboards.tsx:373` |
| `/api/dashboard/` | `frontend/src/components/DeadlineRiskStrip.tsx:132` |
| `/api/dashboard/` | `frontend/src/pages/DashboardUltra.tsx:278` |
| `/api/dashboard` | `frontend/src/config/moduleRegistry.tsx:166` |
| `/api/data-rooms/${aberta.id}/arquivos` | `frontend/src/pages/DataRoom.tsx:80` |
| `/api/data-rooms/${aberta.id}/links` | `frontend/src/pages/DataRoom.tsx:91` |
| `/api/data-rooms/${id}` | `frontend/src/pages/DataRoom.tsx:69` |
| `/api/data-rooms` | `frontend/src/config/moduleRegistry.tsx:492` |
| `/api/data-rooms` | `frontend/src/pages/DataRoom.tsx:62` |
| `/api/datajud/cases/${idCaso}/sync` | `frontend/src/pages/DataJudBusca.tsx:95` |
| `/api/datajud/process/${encodeURIComponent` | `frontend/src/pages/DataJudBusca.tsx:77` |
| `/api/datajud` | `frontend/src/config/moduleRegistry.tsx:617` |
| `/api/deadlines/${item.id}/ciencia` | `frontend/src/pages/CentralAtividades.tsx:1118` |
| `/api/deadlines/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1092` |
| `/api/deadlines/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1259` |
| `/api/deadlines/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1289` |
| `/api/deadlines/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1322` |
| `/api/deadlines/` | `frontend/src/components/DeadlineRiskStrip.tsx:46` |
| `/api/deadlines/` | `frontend/src/pages/CentralAtividades.tsx:1007` |
| `/api/deadlines/` | `frontend/src/pages/CentralAtividades.tsx:974` |
| `/api/deadlines/export.csv` | `frontend/src/pages/CentralAtividades.tsx:1214` |
| `/api/deadlines` | `frontend/src/config/moduleRegistry.tsx:184` |
| `/api/deadlines` | `frontend/src/config/moduleRegistry.tsx:200` |
| `/api/deadlines` | `frontend/src/config/moduleRegistry.tsx:216` |
| `/api/defesas-revisoes/analisar` | `frontend/src/components/DefesasRevisoesPanel.tsx:192` |
| `/api/defesas-revisoes/avancado/adversarial` | `frontend/src/components/DefesasRevisoesComplementos.tsx:148` |
| `/api/defesas-revisoes/avancado/analisar-decisao` | `frontend/src/components/DefesasRevisoesComplementos.tsx:232` |
| `/api/defesas-revisoes/avancado/comparar-documentos` | `frontend/src/components/DefesasRevisoesComplementos.tsx:168` |
| `/api/defesas-revisoes/avancado/memoria/${modalidade}` | `frontend/src/components/DefesasRevisoesComplementos.tsx:242` |
| `/api/defesas-revisoes/avancado/pacote` | `frontend/src/components/DefesasRevisoesComplementos.tsx:133` |
| `/api/defesas-revisoes/avancado/persistir` | `frontend/src/components/DefesasRevisoesComplementos.tsx:117` |
| `/api/defesas-revisoes/avancado/persistir` | `frontend/src/components/DefesasRevisoesPanel.tsx:238` |
| `/api/defesas-revisoes/avancado/viabilidade` | `frontend/src/components/DefesasRevisoesComplementos.tsx:215` |
| `/api/defesas-revisoes/meta` | `frontend/src/components/DefesasRevisoesPanel.tsx:162` |
| `/api/defesas-revisoes/meta` | `frontend/src/pages/DashboardUltra.tsx:283` |
| `/api/despesas/${editId}` | `frontend/src/pages/Despesas.tsx:190` |
| `/api/despesas/${id}` | `frontend/src/pages/Despesas.tsx:203` |
| `/api/despesas/${pendenteExcluir}` | `frontend/src/pages/Despesas.tsx:222` |
| `/api/despesas/export/csv` | `frontend/src/pages/Despesas.tsx:118` |
| `/api/despesas/export/csv` | `frontend/src/pages/FinanceiroDashboard.tsx:149` |
| `/api/despesas` | `frontend/src/config/moduleRegistry.tsx:678` |
| `/api/despesas` | `frontend/src/lib/api.prefixo.test.ts:170` |
| `/api/despesas` | `frontend/src/pages/Despesas.tsx:143` |
| `/api/despesas` | `frontend/src/pages/Despesas.tsx:192` |
| `/api/despesas` | `frontend/src/pages/DespesasRecorrentes.tsx:51` |
| `/api/despesas` | `frontend/src/pages/DespesasRecorrentes.tsx:76` |
| `/api/diagnostico/central` | `frontend/src/components/DeadlineRiskStrip.tsx:153` |
| `/api/diagnostico` | `frontend/src/config/moduleRegistry.tsx:735` |
| `/api/diagnostico` | `frontend/src/lib/api.prefixo.test.ts:172` |
| `/api/diario-oficial/alertas/${id}/marcar-lido` | `frontend/src/pages/DiarioOficial.tsx:108` |
| `/api/diario-oficial/alertas/nao-lidos/count` | `frontend/src/pages/DiarioOficial.tsx:51` |
| `/api/diario-oficial/alertas` | `frontend/src/pages/DiarioOficial.tsx:72` |
| `/api/diario-oficial/keywords/${id}` | `frontend/src/pages/DiarioOficial.tsx:138` |
| `/api/diario-oficial/keywords` | `frontend/src/pages/DiarioOficial.tsx:127` |
| `/api/diario-oficial/keywords` | `frontend/src/pages/DiarioOficial.tsx:86` |
| `/api/diario-oficial` | `frontend/src/config/moduleRegistry.tsx:631` |
| `/api/documentos-ia` | `frontend/src/config/moduleRegistry.tsx:353` |
| `/api/documentos-ia` | `frontend/src/config/moduleRegistry.tsx:493` |
| `/api/documents/${d.id}/download` | `frontend/src/pages/Documentos.tsx:360` |
| `/api/documents/${d.id}/download` | `frontend/src/pages/Documentos.tsx:388` |
| `/api/documents/${d.id}` | `frontend/src/pages/Documentos.tsx:458` |
| `/api/documents/${d.id}` | `frontend/src/pages/Documentos.tsx:481` |
| `/api/documents/${d.id}` | `frontend/src/pages/Documentos.tsx:560` |
| `/api/documents/${docId}/download` | `frontend/src/pages/CasoDetalhe/TabDocumentos.tsx:22` |
| `/api/documents/${docId}/download` | `frontend/src/pages/DossieCliente.tsx:1074` |
| `/api/documents/${editDoc.id}` | `frontend/src/pages/Documentos.tsx:541` |
| `/api/documents/upload` | `frontend/src/components/CaseCommandDock.tsx:142` |
| `/api/documents/upload` | `frontend/src/pages/CasoDetalhe/TabDocumentos.tsx:187` |
| `/api/documents/upload` | `frontend/src/pages/Casos.tsx:233` |
| `/api/documents/upload` | `frontend/src/pages/Documentos.tsx:329` |
| `/api/documents` | `frontend/src/config/moduleRegistry.tsx:491` |
| `/api/dossie/${caseId}/${dossie.id}/aprovar` | `frontend/src/components/DossieEstrategicoCaso.tsx:288` |
| `/api/dossie/${caseId}/${dossie.id}/pdf` | `frontend/src/components/DossieEstrategicoCaso.tsx:305` |
| `/api/dossie/${caseId}/gerar` | `frontend/src/components/DossieEstrategicoCaso.tsx:270` |
| `/api/empresarial/sociedades/${detalhe.id}/eventos` | `frontend/src/components/SociedadesCliente.tsx:315` |
| `/api/empresarial/sociedades/${detalhe.id}/socios` | `frontend/src/components/SociedadesCliente.tsx:276` |
| `/api/empresarial/sociedades/socios/${pendenteExcluir}` | `frontend/src/components/SociedadesCliente.tsx:294` |
| `/api/empresarial/sociedades` | `frontend/src/components/SociedadesCliente.tsx:242` |
| `/api/entrada-universal` | `frontend/src/config/moduleRegistry.tsx:237` |
| `/api/entrada/analisar` | `frontend/src/pages/EntradaUnica.tsx:215` |
| `/api/entrada` | `frontend/src/config/moduleRegistry.tsx:237` |
| `/api/environmental/` | `frontend/src/components/AmbientalAutos.tsx:99` |
| `/api/etiquetas` | `frontend/src/pages/CasoDetalhe.tsx:484` |
| `/api/extratos/detalhado/${caso.id}` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:60` |
| `/api/fees/${pagModal.id}/pagamentos` | `frontend/src/pages/Honorarios.tsx:161` |
| `/api/fees/` | `frontend/src/pages/Honorarios.tsx:118` |
| `/api/fees` | `frontend/src/config/moduleRegistry.tsx:677` |
| `/api/financeiro` | `frontend/src/config/moduleRegistry.tsx:676` |
| `/api/health` | `frontend/src/config/moduleRegistry.tsx:166` |
| `/api/honorarios-oab/${fee.id}/rateio` | `frontend/src/pages/Honorarios.tsx:133` |
| `/api/honorarios-oab/${rateioModal.fee.id}/rateio` | `frontend/src/pages/Honorarios.tsx:146` |
| `/api/honorarios-oab/estimar` | `frontend/src/components/EstimadorHonorarios.tsx:53` |
| `/api/ia-defensiva/analisar` | `frontend/src/pages/CasoDetalhe/IaDefensivaCaso.tsx:87` |
| `/api/ia-defensiva/historico/${caso.id}` | `frontend/src/pages/CasoDetalhe/IaDefensivaCaso.tsx:46` |
| `/api/ia-defensiva/historico/${logId}/status` | `frontend/src/pages/CasoDetalhe/IaDefensivaCaso.tsx:61` |
| `/api/ia-especializada/${perfil}` | `frontend/src/pages/AssistenteIA.tsx:89` |
| `/api/ia-governanca/dashboard` | `frontend/src/pages/GovernancaIA.tsx:86` |
| `/api/ia-governanca/fontes` | `frontend/src/pages/GovernancaIA.tsx:89` |
| `/api/ia-governanca/guardrails` | `frontend/src/pages/GovernancaIA.tsx:90` |
| `/api/ia-governanca/jurisprudencia-mg/geometria` | `frontend/src/pages/GovernancaIA.tsx:92` |
| `/api/ia-governanca/jurisprudencia-mg` | `frontend/src/pages/GovernancaIA.tsx:171` |
| `/api/ia-governanca/jurisprudencia-mg` | `frontend/src/pages/GovernancaIA.tsx:91` |
| `/api/ia-governanca/prompts` | `frontend/src/pages/GovernancaIA.tsx:88` |
| `/api/ia-governanca/provedores` | `frontend/src/pages/PainelProvedoresIA.tsx:179` |
| `/api/ia-governanca/rag-curadoria/${doc.id}` | `frontend/src/pages/GovernancaIA.tsx:129` |
| `/api/ia-governanca/rag-curadoria` | `frontend/src/pages/GovernancaIA.tsx:87` |
| `/api/ia-governanca` | `frontend/src/config/moduleRegistry.tsx:720` |
| `/api/ia/agente/stream` | `frontend/src/lib/api.prefixo.test.ts:171` |
| `/api/ia/agente/stream` | `frontend/src/pages/AgenteIA.tsx:147` |
| `/api/intimacoes/${item.id}/prazo-sugerido` | `frontend/src/pages/CentralAtividades.tsx:1147` |
| `/api/intimacoes/${item.id}/processar` | `frontend/src/pages/CentralAtividades.tsx:1098` |
| `/api/intimacoes/${item.id}/processar` | `frontend/src/pages/CentralAtividades.tsx:1331` |
| `/api/intimacoes/capturar-agora` | `frontend/src/pages/CentralAtividades.tsx:1162` |
| `/api/jurimetria/cobertura-mg-jec` | `frontend/src/pages/Jurimetria.tsx:144` |
| `/api/jurimetria/cobertura-rag` | `frontend/src/pages/Jurimetria.tsx:143` |
| `/api/jurimetria/overview` | `frontend/src/pages/Jurimetria.tsx:124` |
| `/api/jurimetria/por-area` | `frontend/src/pages/Jurimetria.tsx:125` |
| `/api/jurimetria/por-tese` | `frontend/src/pages/Jurimetria.tsx:127` |
| `/api/jurimetria/por-tribunal` | `frontend/src/pages/Jurimetria.tsx:126` |
| `/api/kanban/columns` | `frontend/src/pages/Kanban.tsx:70` |
| `/api/legal-docs/${aprovacao.doc.id}/conferir-e-assinar` | `frontend/src/pages/Pecas.tsx:363` |
| `/api/legal-docs/${doc.id}/exportar-docx` | `frontend/src/pages/Pecas.tsx:551` |
| `/api/legal-docs/${doc.id}/pdf-minuta` | `frontend/src/pages/Pecas.tsx:535` |
| `/api/legal-docs/${doc.id}/pdf` | `frontend/src/pages/Pecas.tsx:534` |
| `/api/legal-docs/${doc.id}/validar` | `frontend/src/pages/Pecas.tsx:202` |
| `/api/legal-docs/${doc.id}` | `frontend/src/pages/Pecas.tsx:415` |
| `/api/legal-docs/${doc.id}` | `frontend/src/pages/Pecas.tsx:439` |
| `/api/legal-docs/${doc.id}` | `frontend/src/pages/Pecas.tsx:598` |
| `/api/legal-docs/${id}` | `frontend/src/pages/Pecas.tsx:303` |
| `/api/legal-docs/${protocolo.doc.id}/protocolo` | `frontend/src/pages/Pecas.tsx:466` |
| `/api/legal-docs/${protocolo.doc.id}` | `frontend/src/pages/Pecas.tsx:477` |
| `/api/legal-docs/${revisao.doc.id}/revisar` | `frontend/src/pages/Pecas.tsx:313` |
| `/api/legal-docs/` | `frontend/src/pages/Pecas.tsx:286` |
| `/api/legal-docs` | `frontend/src/config/moduleRegistry.tsx:511` |
| `/api/lgpd/registros/${clientId}/ripd` | `frontend/src/components/LgpdRegistros.tsx:290` |
| `/api/lgpd/registros/${editId}` | `frontend/src/components/LgpdRegistros.tsx:250` |
| `/api/lgpd/registros/${r.id}` | `frontend/src/components/LgpdRegistros.tsx:275` |
| `/api/lgpd/registros` | `frontend/src/components/LgpdRegistros.tsx:253` |
| `/api/memoria-institucional/${id}` | `frontend/src/pages/CasoDetalhe/TabMemoria.tsx:60` |
| `/api/memoria-institucional` | `frontend/src/pages/CasoDetalhe/TabMemoria.tsx:46` |
| `/api/nfse/${n.id}/${kind}` | `frontend/src/pages/NotasFiscais.tsx:200` |
| `/api/nfse/manual/${cancelNota.id}/cancelar` | `frontend/src/pages/NotasFiscais.tsx:224` |
| `/api/nfse/manual` | `frontend/src/pages/NotasFiscais.tsx:183` |
| `/api/nfse` | `frontend/src/config/moduleRegistry.tsx:679` |
| `/api/noticias` | `frontend/src/pages/DashboardUltra.tsx:282` |
| `/api/noticias` | `frontend/src/pages/Noticias.tsx:15` |
| `/api/notifications/push/subscribe` | `frontend/src/components/NotificationPreferences.tsx:257` |
| `/api/notifications/push/subscribe` | `frontend/src/components/SecurityMenu.tsx:91` |
| `/api/notifications/push/subscriptions/${deviceId}` | `frontend/src/components/NotificationPreferences.tsx:277` |
| `/api/notifications/push/vapid-key` | `frontend/src/components/NotificationPreferences.tsx:234` |
| `/api/notifications/push/vapid-key` | `frontend/src/components/SecurityMenu.tsx:78` |
| `/api/notifications` | `frontend/src/config/moduleRegistry.tsx:459` |
| `/api/observabilidade/frontend-error` | `frontend/src/components/ErrorBoundary.tsx:39` |
| `/api/office-contracts/${editing.id}` | `frontend/src/pages/OfficeContracts.tsx:163` |
| `/api/office-contracts/${pendenteExcluir}` | `frontend/src/pages/OfficeContracts.tsx:183` |
| `/api/office-contracts/expiring` | `frontend/src/pages/OfficeContracts.tsx:102` |
| `/api/office-contracts` | `frontend/src/pages/OfficeContracts.tsx:165` |
| `/api/office-contracts` | `frontend/src/pages/OfficeContracts.tsx:99` |
| `/api/ok` | `frontend/src/lib/api.test.ts:79` |
| `/api/partner-withdrawals/${id}/${action}` | `frontend/src/pages/Sociedade.tsx:228` |
| `/api/partner-withdrawals` | `frontend/src/pages/Sociedade.tsx:125` |
| `/api/partner-withdrawals` | `frontend/src/pages/Sociedade.tsx:202` |
| `/api/pecas/demonstrativo` | `frontend/src/pages/ramos/RamoFerramenta.tsx:250` |
| `/api/pecas/gerar` | `frontend/src/components/PecaGeneratorModal.tsx:600` |
| `/api/pix/cobranca` | `frontend/src/pages/Honorarios.tsx:181` |
| `/api/portal/casos/${caseId}/mensagens` | `frontend/src/pages/portal/PortalCasoDetalhe.tsx:25` |
| `/api/portal/casos/${selectedId}/mensagens` | `frontend/src/pages/portal/PortalMensagens.tsx:59` |
| `/api/portal/casos/${selectedId}/mensagens` | `frontend/src/pages/portal/PortalMensagens.tsx:79` |
| `/api/portal/documentos` | `frontend/src/pages/portal/PortalDocumentos.tsx:74` |
| `/api/portal/financeiro` | `frontend/src/pages/portal/PortalDashboard.tsx:56` |
| `/api/portal/mensagens/nao-lidas` | `frontend/src/pages/portal/PortalDashboard.tsx:60` |
| `/api/portal/meus-casos` | `frontend/src/pages/portal/PortalDashboard.tsx:55` |
| `/api/portal/meus-casos` | `frontend/src/pages/portal/PortalMensagens.tsx:48` |
| `/api/portal/solicitacoes-documentos` | `frontend/src/pages/portal/PortalDashboard.tsx:57` |
| `/api/portal/solicitacoes-documentos` | `frontend/src/pages/portal/PortalDocumentos.tsx:73` |
| `/api/previdenciario/ferramentas/parecer-pdf` | `frontend/src/components/PrevidenciarioSimulacao.tsx:260` |
| `/api/processes/${arqPid}/arquivar` | `frontend/src/pages/CasoDetalhe/TabProcessos.tsx:89` |
| `/api/processes/${pid}/desarquivar` | `frontend/src/pages/CasoDetalhe/TabProcessos.tsx:104` |
| `/api/processes/${pid}` | `frontend/src/pages/CasoDetalhe/TabProcessos.tsx:75` |
| `/api/processes` | `frontend/src/config/moduleRegistry.tsx:369` |
| `/api/prompts-juridicos/${id}` | `frontend/src/pages/Prompts.tsx:74` |
| `/api/prompts-juridicos` | `frontend/src/pages/Prompts.tsx:56` |
| `/api/protegido` | `frontend/src/lib/api.test.ts:50` |
| `/api/protegido` | `frontend/src/lib/api.test.ts:62` |
| `/api/qualquer-endpoint` | `frontend/src/lib/api.test.ts:35` |
| `/api/rag/buscar` | `frontend/src/pages/CasoDetalhe/TabIndicadoresJuridicos.tsx:54` |
| `/api/rag/buscar` | `frontend/src/pages/Conhecimento.tsx:821` |
| `/api/rag/docs/${id}` | `frontend/src/pages/Conhecimento.tsx:837` |
| `/api/rag/docs` | `frontend/src/components/KnowledgeGovernancePanel.tsx:248` |
| `/api/rag/governanca/cobertura` | `frontend/src/components/KnowledgeGovernancePanel.tsx:247` |
| `/api/rag/governanca/saude` | `frontend/src/components/KnowledgeGovernancePanel.tsx:246` |
| `/api/rag/governanca/testes-juridicos` | `frontend/src/components/KnowledgeGovernancePanel.tsx:393` |
| `/api/rag/ingest-pdf` | `frontend/src/pages/Conhecimento.tsx:376` |
| `/api/rag/ingest-url` | `frontend/src/pages/Conhecimento.tsx:391` |
| `/api/rag/ingest` | `frontend/src/pages/Conhecimento.tsx:176` |
| `/api/rag/monitor-legislativo` | `frontend/src/pages/Noticias.tsx:16` |
| `/api/raio-x/${selected.id}/${mode}` | `frontend/src/pages/RaioXProcesso.tsx:919` |
| `/api/raio-x/${selected.id}/converter` | `frontend/src/pages/RaioXProcesso.tsx:883` |
| `/api/raio-x/${selected.id}/exportar` | `frontend/src/pages/RaioXProcesso.tsx:661` |
| `/api/raio-x/` | `frontend/src/pages/RaioXProcesso.tsx:388` |
| `/api/raio-x/stats` | `frontend/src/pages/RaioXProcesso.tsx:389` |
| `/api/raio-x` | `frontend/src/config/moduleRegistry.tsx:353` |
| `/api/regulatorio` | `frontend/src/config/moduleRegistry.tsx:647` |
| `/api/relatorio/mensal` | `frontend/src/pages/FinanceiroDashboard.tsx:135` |
| `/api/sala-juridica/${ativa.id}/converter` | `frontend/src/pages/SalaJuridica.tsx:654` |
| `/api/sala-juridica/${ativa.id}/exportar` | `frontend/src/pages/SalaJuridica.tsx:718` |
| `/api/sala-juridica/${ativa.id}/saida` | `frontend/src/pages/SalaJuridica.tsx:538` |
| `/api/sala-juridica/${s.id}` | `frontend/src/pages/SalaJuridica.tsx:528` |
| `/api/sala-juridica/${sessao.id}` | `frontend/src/pages/SalaJuridica.tsx:440` |
| `/api/sala-juridica/${sessaoId}/mensagens` | `frontend/src/pages/SalaJuridica.tsx:486` |
| `/api/sala-juridica/${sessaoId}` | `frontend/src/pages/SalaJuridica.tsx:418` |
| `/api/sala-juridica` | `frontend/src/config/moduleRegistry.tsx:335` |
| `/api/signatures/${id}/assinar` | `frontend/src/pages/Assinaturas.tsx:168` |
| `/api/signatures/${s.id}/assinar` | `frontend/src/pages/portal/PortalAssinaturas.tsx:61` |
| `/api/signatures/` | `frontend/src/pages/Assinaturas.tsx:146` |
| `/api/signatures/` | `frontend/src/pages/Assinaturas.tsx:87` |
| `/api/signatures/` | `frontend/src/pages/CasoDetalhe/CaseDocumentActions.tsx:168` |
| `/api/signatures/` | `frontend/src/pages/portal/PortalDashboard.tsx:58` |
| `/api/signatures` | `frontend/src/config/moduleRegistry.tsx:524` |
| `/api/sociedade/distribuicao` | `frontend/src/pages/Sociedade.tsx:123` |
| `/api/sociedade/distribuicao` | `frontend/src/pages/Sociedade.tsx:178` |
| `/api/sociedade/socios` | `frontend/src/pages/Sociedade.tsx:122` |
| `/api/sociedade/socios` | `frontend/src/pages/Sociedade.tsx:156` |
| `/api/suspensoes/${excluirSuspensao.id}` | `frontend/src/pages/CentralAtividades.tsx:1181` |
| `/api/suspensoes/` | `frontend/src/pages/CentralAtividades/acoesLegadas.tsx:251` |
| `/api/suspensoes/simular` | `frontend/src/pages/CentralAtividades/acoesLegadas.tsx:370` |
| `/api/system-modules/settings/${selectedKey}` | `frontend/src/components/ModuleLifecycleSettings.tsx:177` |
| `/api/system-modules` | `frontend/src/config/moduleRegistry.tsx:763` |
| `/api/tasks/${excluir.id}` | `frontend/src/pages/CentralAtividades.tsx:1196` |
| `/api/tasks/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1094` |
| `/api/tasks/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1261` |
| `/api/tasks/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1293` |
| `/api/tasks/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1317` |
| `/api/templates/${tplSel}/gerar` | `frontend/src/pages/Pecas.tsx:518` |
| `/api/templates/` | `frontend/src/pages/Pecas.tsx:499` |
| `/api/templates` | `frontend/src/config/moduleRegistry.tsx:511` |
| `/api/teses/motor/async/${task_id}` | `frontend/src/components/MotorTeses.tsx:82` |
| `/api/teses/motor/async` | `frontend/src/components/MotorTeses.tsx:60` |
| `/api/teses` | `frontend/src/config/moduleRegistry.tsx:585` |
| `/api/teste/stream` | `frontend/src/lib/stream.test.ts:36` |
| `/api/timesheet` | `frontend/src/pages/CasoDetalhe/TabTimeline.tsx:93` |
| `/api/trabalhista/liquidacao/planilha-pdf` | `frontend/src/components/LiquidacaoTrabalhista.tsx:320` |
| `/api/trash/${ent}/${id}/restaurar` | `frontend/src/pages/Lixeira.tsx:70` |
| `/api/trash` | `frontend/src/config/moduleRegistry.tsx:792` |
| `/api/triagem/ficha/pre-preencher` | `frontend/src/components/FichaTriagem.tsx:196` |
| `/api/triagem/ficha` | `frontend/src/components/FichaTriagem.tsx:217` |
| `/api/triagem` | `frontend/src/config/moduleRegistry.tsx:409` |
| `/api/tributario/fiscal/relatorio-pdf` | `frontend/src/components/TributarioFiscal.tsx:221` |
| `/api/users/${u.id}` | `frontend/src/pages/Usuarios.tsx:63` |
| `/api/users/${user.id}` | `frontend/src/components/SecurityMenu.tsx:103` |
| `/api/users/` | `frontend/src/pages/Sociedade.tsx:124` |
| `/api/users/` | `frontend/src/pages/Usuarios.tsx:49` |
| `/api/users/me/avatar` | `frontend/src/components/SecurityMenu.tsx:45` |
| `/api/users/me/avatar` | `frontend/src/components/SecurityMenu.tsx:65` |
| `/api/users/me/sessions/${sessionId}/revoke` | `frontend/src/components/AccountSecurity.tsx:146` |
| `/api/users/me/sessions/revoke-others` | `frontend/src/components/AccountSecurity.tsx:161` |
| `/api/users/me/totp-qr` | `frontend/src/components/AccountSecurity.tsx:90` |
| `/api/users` | `frontend/src/config/moduleRegistry.tsx:778` |
| `/api/utils/cep/${cep}` | `frontend/src/pages/Clientes.tsx:440` |
| `/api/v1/` | `frontend/src/lib/api.prefixo.test.ts:56` |
| `/api/v1/` | `frontend/src/lib/api.prefixo.test.ts:7` |
| `/api/v1/` | `frontend/src/lib/api.ts:21` |
| `/api/v1/cases/` | `frontend/src/components/__tests__/FlowEnhancements.test.ts:31` |
| `/api/v1/casos/${id}` | `frontend/src/lib/api.prefixo.test.ts:153` |
| `/api/v1/despesas` | `frontend/src/lib/api.prefixo.test.ts:152` |
| `/api/v1/itens` | `frontend/src/lib/api.prefixo.test.ts:158` |
| `/api/v1/itens` | `frontend/src/lib/api.prefixo.test.ts:162` |
| `/api/v1/itens` | `frontend/src/lib/api.prefixo.test.ts:49` |
| `/api/v1/tasks/` | `frontend/src/components/__tests__/FlowEnhancements.test.ts:80` |
| `/api/v1/v1/despesas` | `frontend/src/lib/api.prefixo.test.ts:10` |
| `/api/v1` | `frontend/src/lib/api.prefixo.test.ts:4` |
| `/api/v1` | `frontend/src/lib/api.ts:21` |
| `/api/v1` | `frontend/src/lib/api.ts:9` |
| `/api/validador-juridico/validar` | `frontend/src/pages/IA.tsx:135` |
| `/api/workflow/templates/${id}` | `frontend/src/pages/Workflow.tsx:93` |
| `/api/workflow/templates` | `frontend/src/pages/Workflow.tsx:67` |
| `/api/workflow` | `frontend/src/config/moduleRegistry.tsx:537` |

## 4. Verificacao de divergencia — PREENCHIMENTO HUMANO

| Rota chamada pelo frontend | Existe no backend? | Metodo confere? | Contrato confere? | Acao |
|---|---|---|---|---|
| | | | | |

> Comparar as secoes 1 e 3. Chamada sem rota correspondente e defeito P1.
> Rota sem consumidor e candidata a remocao — confirmar antes.
> Rotas com parametro de caminho aparecem parametrizadas de um lado
> (`/casos/{caso_id}`) e interpoladas do outro (`/casos/${id}`): a
> comparacao e por forma normalizada, nao textual.

## 5. Controle de acesso por rota — PREENCHIMENTO HUMANO

| Rota | Autenticacao | RBAC (perfis) | Isolamento por escritorio | Testado |
|---|---|---|---|---|
| | | | | |

> Rota sem autenticacao declarada ou sem filtro de tenant e defeito P0.
> No EJC a autenticacao e imposta pelo `AuthMiddleware`; a autorizacao
> por perfil vem de `require_roles()`/`require_admin`. Endpoint publico
> e excecao explicita e precisa de justificativa registrada.
