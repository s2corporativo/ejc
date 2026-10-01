# MATRIZ DE ROTAS — EJC

> Gerado por `scripts/governanca/inventario-repo.sh` em 2026-10-01, commit `54c7fc4e`.
> Divergencia entre backend e frontend nesta matriz e defeito P1.

## 1. Rotas declaradas no backend

| Metodo | Caminho | Arquivo |
|---|---|---|
| DELETE | `/admin-esp/{aid}` | `backend/app/routers/ramos_admin_esp.py:133` |
| DELETE | `/bancario/{bid}` | `backend/app/routers/ramos_bancario.py:131` |
| DELETE | `/civel/{cid}` | `backend/app/routers/ramos_civel.py:136` |
| DELETE | `/comissoes/regras/{rule_id}` | `backend/app/routers/financeiro/comissoes.py:1049` |
| DELETE | `/docs/{doc_id}` | `backend/app/routers/rag.py:410` |
| DELETE | `/drive/{file_id}` | `backend/app/routers/documents.py:1326` |
| DELETE | `/empresarial/{eid}` | `backend/app/routers/ramos_empresarial.py:139` |
| DELETE | `/keywords/{keyword_id}` | `backend/app/routers/diario_oficial.py:92` |
| DELETE | `/penal/{pid}` | `backend/app/routers/ramos_penal.py:124` |
| DELETE | `/push/subscriptions/{subscription_id}` | `backend/app/routers/notifications.py:272` |
| DELETE | `/settings/{module_key}` | `backend/app/routers/module_settings.py:139` |
| DELETE | `/socios/{socio_id}` | `backend/app/routers/sociedades_cliente.py:418` |
| DELETE | `/templates/{template_id}` | `backend/app/routers/checklists.py:185` |
| DELETE | `/templates/{template_id}` | `backend/app/routers/workflow.py:169` |
| DELETE | `/trabalhista-esp/{tid}` | `backend/app/routers/ramos_trabalhista_esp.py:126` |
| DELETE | `/{analise_id}` | `backend/app/routers/raio_x.py:744` |
| DELETE | `/{analysis_id}` | `backend/app/routers/bank_analysis.py:381` |
| DELETE | `/{area}` | `backend/app/routers/caso_areas.py:45` |
| DELETE | `/{atendimento_id}` | `backend/app/routers/atendimentos.py:1085` |
| DELETE | `/{case_id}/movimentos/{movimento_id}` | `backend/app/routers/cases.py:1064` |
| DELETE | `/{case_id}` | `backend/app/routers/cases.py:816` |
| DELETE | `/{checklist_id}` | `backend/app/routers/checklists.py:462` |
| DELETE | `/{client_id}/pending-items/{item_id}` | `backend/app/routers/pending_items.py:291` |
| DELETE | `/{client_id}` | `backend/app/routers/clients.py:935` |
| DELETE | `/{contract_id}` | `backend/app/routers/office_contracts.py:274` |
| DELETE | `/{contrato_id}` | `backend/app/routers/contratos_societarios.py:341` |
| DELETE | `/{deadline_id}` | `backend/app/routers/deadlines.py:641` |
| DELETE | `/{despesa_id}` | `backend/app/routers/despesas.py:625` |
| DELETE | `/{doc_id}` | `backend/app/routers/documents.py:800` |
| DELETE | `/{doc_id}` | `backend/app/routers/legal_docs.py:1158` |
| DELETE | `/{entry_id}` | `backend/app/routers/despesas_processuais.py:258` |
| DELETE | `/{entry_id}` | `backend/app/routers/timesheet.py:142` |
| DELETE | `/{env_id}` | `backend/app/routers/environmental.py:184` |
| DELETE | `/{etiqueta_id}` | `backend/app/routers/etiquetas.py:51` |
| DELETE | `/{evento_id}` | `backend/app/routers/agenda_eventos.py:258` |
| DELETE | `/{fee_id}` | `backend/app/routers/fees.py:813` |
| DELETE | `/{help_id}` | `backend/app/routers/module_help.py:130` |
| DELETE | `/{juri_id}` | `backend/app/routers/jurisprudencia_interna.py:177` |
| DELETE | `/{lancamento_id}` | `backend/app/routers/centro_custos.py:397` |
| DELETE | `/{mem_id}` | `backend/app/routers/memoria_institucional.py:259` |
| DELETE | `/{parte_id}` | `backend/app/routers/case_partes.py:233` |
| DELETE | `/{pid}` | `backend/app/routers/processes.py:223` |
| DELETE | `/{prompt_id}` | `backend/app/routers/prompts_juridicos.py:232` |
| DELETE | `/{prova_id}` | `backend/app/routers/provas.py:216` |
| DELETE | `/{provider_key}/{field_key}` | `backend/app/routers/credential_vault.py:386` |
| DELETE | `/{registro_id}` | `backend/app/routers/lgpd_registros.py:217` |
| DELETE | `/{room_id}/arquivos/{arquivo_id}` | `backend/app/routers/data_room.py:535` |
| DELETE | `/{room_id}/links/{link_id}` | `backend/app/routers/data_room.py:603` |
| DELETE | `/{room_id}` | `backend/app/routers/data_room.py:793` |
| DELETE | `/{sociedade_id}` | `backend/app/routers/sociedades_cliente.py:332` |
| DELETE | `/{suspensao_id}` | `backend/app/routers/suspensoes.py:116` |
| DELETE | `/{task_id}` | `backend/app/routers/tasks.py:299` |
| DELETE | `/{tese_id}` | `backend/app/routers/teses.py:395` |
| DELETE | `/{tpl_id}` | `backend/app/routers/templates.py:234` |
| DELETE | `/{user_id}` | `backend/app/routers/users.py:573` |
| DELETE | `/{withdrawal_id}` | `backend/app/routers/partner_withdrawals.py:328` |
| GET | `/` | `backend/app/routers/agenda_eventos.py:103` |
| GET | `/` | `backend/app/routers/audit.py:19` |
| GET | `/` | `backend/app/routers/bank_analysis.py:142` |
| GET | `/` | `backend/app/routers/cases.py:123` |
| GET | `/` | `backend/app/routers/clients.py:414` |
| GET | `/` | `backend/app/routers/dashboard.py:40` |
| GET | `/` | `backend/app/routers/deadlines.py:269` |
| GET | `/` | `backend/app/routers/documents.py:505` |
| GET | `/` | `backend/app/routers/environmental.py:74` |
| GET | `/` | `backend/app/routers/fees.py:101` |
| GET | `/` | `backend/app/routers/intimacoes.py:87` |
| GET | `/` | `backend/app/routers/legal_docs.py:355` |
| GET | `/` | `backend/app/routers/module_help.py:50` |
| GET | `/` | `backend/app/routers/notifications.py:64` |
| GET | `/` | `backend/app/routers/peca_geracao.py:355` |
| GET | `/` | `backend/app/routers/procuracoes.py:39` |
| GET | `/` | `backend/app/routers/raio_x.py:174` |
| GET | `/` | `backend/app/routers/signatures.py:162` |
| GET | `/` | `backend/app/routers/suspensoes.py:66` |
| GET | `/` | `backend/app/routers/tasks.py:110` |
| GET | `/` | `backend/app/routers/templates.py:112` |
| GET | `/` | `backend/app/routers/trash.py:113` |
| GET | `/` | `backend/app/routers/users.py:341` |
| GET | `/admin-esp/ferramentas/mandado-seguranca` | `backend/app/routers/ramos_vitrine.py:1348` |
| GET | `/admin-esp/ferramentas/reajuste-contrato-administrativo` | `backend/app/routers/ramos_ferramentas_complementares.py:395` |
| GET | `/admin-esp/ferramentas/recurso-multa-transito` | `backend/app/routers/ramos_admin_esp.py:233` |
| GET | `/admin-esp` | `backend/app/routers/ramos_admin_esp.py:96` |
| GET | `/advogado/{user_id}` | `backend/app/routers/extratos.py:46` |
| GET | `/agents` | `backend/app/routers/ai_core.py:213` |
| GET | `/alertas-inteligentes` | `backend/app/routers/atividades.py:450` |
| GET | `/alertas/nao-lidos/count` | `backend/app/routers/diario_oficial.py:166` |
| GET | `/alertas` | `backend/app/routers/diario_oficial.py:111` |
| GET | `/ambiental/ferramentas/auto-infracao-ambiental` | `backend/app/routers/ramos_ferramentas_complementares.py:874` |
| GET | `/ambiental/ferramentas/crimes-ambientais` | `backend/app/routers/ramos_ferramentas_complementares.py:955` |
| GET | `/ambiental/ferramentas/licenciamento` | `backend/app/routers/ramos_ferramentas_complementares.py:1075` |
| GET | `/ambiental/ferramentas/reserva-legal` | `backend/app/routers/ramos_ferramentas_complementares.py:1139` |
| GET | `/ambiental/ferramentas/tac-ambiental` | `backend/app/routers/ramos_ferramentas_complementares.py:1004` |
| GET | `/analisar-caso/async/{task_id}` | `backend/app/routers/ai.py:202` |
| GET | `/api/health/ready` | `backend/app/main.py:622` |
| GET | `/api/health` | `backend/app/main.py:599` |
| GET | `/aprovacoes` | `backend/app/routers/financeiro/governanca.py:106` |
| GET | `/atencao` | `backend/app/routers/financeiro/dashboard.py:240` |
| GET | `/audit-report-template` | `backend/app/routers/licitacao_auditoria.py:38` |
| GET | `/audit` | `backend/app/routers/google_drive_knowledge.py:73` |
| GET | `/bancario/ferramentas/analise-juros` | `backend/app/routers/ramos_bancario.py:137` |
| GET | `/bancario/ferramentas/busca-apreensao` | `backend/app/routers/ramos_bancario.py:230` |
| GET | `/bancario/ferramentas/juros-abusivos` | `backend/app/routers/ramos_vitrine.py:1143` |
| GET | `/bancario/ferramentas/superendividamento` | `backend/app/routers/ramos_bancario.py:181` |
| GET | `/bancario/ferramentas/taxas-bacen` | `backend/app/routers/ramos_ferramentas_complementares.py:440` |
| GET | `/bancario` | `backend/app/routers/ramos_bancario.py:100` |
| GET | `/baseline-referencia` | `backend/app/routers/financeiro/governanca.py:367` |
| GET | `/busca-avancada` | `backend/app/routers/teses.py:195` |
| GET | `/buscar` | `backend/app/routers/rag.py:342` |
| GET | `/buscar` | `backend/app/routers/sumulas.py:57` |
| GET | `/capacidades` | `backend/app/routers/ajuizamento.py:82` |
| GET | `/case-health/{case_id}` | `backend/app/routers/analytics.py:110` |
| GET | `/case-health` | `backend/app/routers/analytics.py:99` |
| GET | `/cases/{case_id}/provisionamento` | `backend/app/routers/honorarios_oab.py:476` |
| GET | `/cases/{case_id}/termo-consentimento-ia` | `backend/app/routers/compliance.py:134` |
| GET | `/cases/{case_id}/teto-etico` | `backend/app/routers/honorarios_oab.py:500` |
| GET | `/caso/{case_id}/resumo` | `backend/app/routers/centro_custos.py:216` |
| GET | `/casos.csv` | `backend/app/routers/export.py:175` |
| GET | `/casos/{case_id}.pdf` | `backend/app/routers/export.py:202` |
| GET | `/casos/{case_id}/alertas` | `backend/app/routers/visual_law.py:117` |
| GET | `/casos/{case_id}/matriz-risco` | `backend/app/routers/visual_law.py:87` |
| GET | `/casos/{case_id}/mensagens` | `backend/app/routers/portal.py:249` |
| GET | `/casos/{case_id}/proposta` | `backend/app/routers/honorarios_oab.py:407` |
| GET | `/casos/{case_id}/timeline` | `backend/app/routers/visual_law.py:46` |
| GET | `/casos/{case_id}` | `backend/app/routers/checklists.py:314` |
| GET | `/casos/{case_id}` | `backend/app/routers/despesas_processuais.py:96` |
| GET | `/casos/{case_id}` | `backend/app/routers/portal.py:85` |
| GET | `/casos/{case_id}` | `backend/app/routers/teses.py:252` |
| GET | `/casos/{case_id}` | `backend/app/routers/timesheet.py:49` |
| GET | `/casos/{case_id}` | `backend/app/routers/workflow.py:188` |
| GET | `/chats` | `backend/app/routers/whatsapp.py:132` |
| GET | `/checklist` | `backend/app/routers/conversao_caso.py:250` |
| GET | `/civel/ferramentas/alimentos-calcular` | `backend/app/routers/ramos_civel.py:216` |
| GET | `/civel/ferramentas/calculo-dano-moral` | `backend/app/routers/ramos_ferramentas_complementares.py:122` |
| GET | `/civel/ferramentas/partilha-divorcio` | `backend/app/routers/ramos_ferramentas_complementares.py:234` |
| GET | `/civel/ferramentas/prazos-contestacao` | `backend/app/routers/ramos_civel.py:148` |
| GET | `/civel/ferramentas/prescricao-consumidor` | `backend/app/routers/ramos_ferramentas_complementares.py:57` |
| GET | `/civel/ferramentas/rescisao-locacao` | `backend/app/routers/ramos_ferramentas_complementares.py:266` |
| GET | `/civel/ferramentas/usucapiao-verificar` | `backend/app/routers/ramos_civel.py:267` |
| GET | `/civel` | `backend/app/routers/ramos_civel.py:103` |
| GET | `/cobertura-mg-jec` | `backend/app/routers/jurimetria.py:799` |
| GET | `/cobertura-rag` | `backend/app/routers/jurimetria.py:788` |
| GET | `/cobertura` | `backend/app/routers/rag_governance.py:210` |
| GET | `/cofre/documentos/{document_id}/logs` | `backend/app/routers/novos_modulos.py:315` |
| GET | `/cofre/relatorio` | `backend/app/routers/novos_modulos.py:429` |
| GET | `/columns` | `backend/app/routers/kanban.py:44` |
| GET | `/comissoes/conferencia` | `backend/app/routers/financeiro/comissoes.py:536` |
| GET | `/comissoes/extrato-mensal` | `backend/app/routers/financeiro/comissoes.py:546` |
| GET | `/comissoes/fechamentos/{competencia}` | `backend/app/routers/financeiro/comissoes.py:573` |
| GET | `/comissoes/opcoes` | `backend/app/routers/financeiro/comissoes.py:1079` |
| GET | `/comissoes/previsao` | `backend/app/routers/financeiro/comissoes.py:384` |
| GET | `/comissoes/regras` | `backend/app/routers/financeiro/comissoes.py:933` |
| GET | `/comissoes` | `backend/app/routers/financeiro/comissoes.py:37` |
| GET | `/companies/{client_id}` | `backend/app/modules/dpt360/router.py:78` |
| GET | `/conciliacao/{analysis_id}` | `backend/app/routers/financeiro/governanca.py:726` |
| GET | `/consolidado` | `backend/app/routers/centro_custos.py:277` |
| GET | `/consolidado` | `backend/app/routers/financeiro/dashboard.py:27` |
| GET | `/consumidor/ferramentas/devolucao-dobro` | `backend/app/routers/ramos_vitrine.py:41` |
| GET | `/consumidor/ferramentas/negativacao-indevida` | `backend/app/routers/ramos_vitrine.py:1279` |
| GET | `/consumidor/ferramentas/prazos-cdc` | `backend/app/routers/ramos_vitrine.py:132` |
| GET | `/contextual/{case_id}` | `backend/app/routers/raio_x.py:255` |
| GET | `/contextual` | `backend/app/routers/ai_skills.py:227` |
| GET | `/contracts` | `backend/app/routers/architecture.py:59` |
| GET | `/custas-tjmg` | `backend/app/routers/calculadoras.py:153` |
| GET | `/dashboard` | `backend/app/modules/dpt360/router.py:45` |
| GET | `/dashboard` | `backend/app/routers/atendimentos.py:820` |
| GET | `/dashboard` | `backend/app/routers/ia_governanca.py:248` |
| GET | `/dashboard` | `backend/app/routers/ia_saude.py:137` |
| GET | `/demonstrativo` | `backend/app/routers/financeiro/dashboard.py:407` |
| GET | `/desfechos` | `backend/app/routers/jurimetria.py:493` |
| GET | `/detalhado/{case_id}` | `backend/app/routers/extratos.py:19` |
| GET | `/diagnostico-sistema` | `backend/app/routers/module_help.py:65` |
| GET | `/digest-semanal` | `backend/app/routers/regulatorio.py:25` |
| GET | `/digital_lgpd/ferramentas/multa-lgpd` | `backend/app/routers/ramos_vitrine.py:468` |
| GET | `/digital_lgpd/ferramentas/prazos-lgpd` | `backend/app/routers/ramos_vitrine.py:510` |
| GET | `/distribuicao-disponivel` | `backend/app/routers/financeiro/governanca.py:331` |
| GET | `/distribuicao` | `backend/app/routers/gestao_societaria.py:372` |
| GET | `/divergencias` | `backend/app/routers/saneamento.py:652` |
| GET | `/docs/{doc_id}/comparar` | `backend/app/routers/rag_governance.py:409` |
| GET | `/docs/{doc_id}` | `backend/app/routers/rag_governance.py:219` |
| GET | `/docs` | `backend/app/routers/rag.py:378` |
| GET | `/documento-unico/{arquivo_id}/download` | `backend/app/routers/provas.py:678` |
| GET | `/documentos` | `backend/app/routers/portal.py:130` |
| GET | `/dossie/{case_id}` | `backend/app/routers/ai.py:217` |
| GET | `/drive/{file_id}/download` | `backend/app/routers/documents.py:1284` |
| GET | `/drive/{file_id}/link` | `backend/app/routers/documents.py:1258` |
| GET | `/due-diligence/templates` | `backend/app/routers/novos_modulos.py:257` |
| GET | `/duplicatas` | `backend/app/routers/saneamento.py:430` |
| GET | `/empresa/{nome_empresa}` | `backend/app/routers/consumidor_monitor.py:167` |
| GET | `/empresarial/ferramentas/juros-mora` | `backend/app/routers/ramos_vitrine.py:931` |
| GET | `/empresarial/ferramentas/prazos-rj` | `backend/app/routers/ramos_empresarial.py:145` |
| GET | `/empresarial/ferramentas/verificar-cade` | `backend/app/routers/ramos_empresarial.py:223` |
| GET | `/empresarial/tipos` | `backend/app/routers/ramos_empresarial.py:103` |
| GET | `/empresarial` | `backend/app/routers/ramos_empresarial.py:114` |
| GET | `/empresas` | `backend/app/routers/consumidor_monitor.py:152` |
| GET | `/estado-operacional` | `backend/app/routers/ia_saude.py:213` |
| GET | `/excecoes` | `backend/app/routers/financeiro/governanca.py:485` |
| GET | `/excecoes` | `backend/app/routers/saneamento.py:394` |
| GET | `/expiring` | `backend/app/routers/office_contracts.py:130` |
| GET | `/export.csv` | `backend/app/routers/deadlines.py:353` |
| GET | `/export/csv` | `backend/app/routers/despesas.py:262` |
| GET | `/ext/benchmarks` | `backend/app/routers/jurimetria.py:564` |
| GET | `/ext/predicao/provimento` | `backend/app/routers/jurimetria.py:610` |
| GET | `/ext/stats` | `backend/app/routers/jurimetria.py:522` |
| GET | `/familia/ferramentas/debito-alimentos` | `backend/app/routers/ramos_vitrine.py:196` |
| GET | `/familia/ferramentas/itcmd-inventario` | `backend/app/routers/ramos_vitrine.py:651` |
| GET | `/fechamento-inteligente` | `backend/app/routers/financeiro/fechamento.py:25` |
| GET | `/fechamentos/{competencia}` | `backend/app/routers/financeiro/governanca.py:343` |
| GET | `/files` | `backend/app/routers/google_drive_knowledge.py:53` |
| GET | `/filings/{filing_id}/transicoes` | `backend/app/routers/ajuizamento.py:342` |
| GET | `/filings/{filing_id}` | `backend/app/routers/ajuizamento.py:207` |
| GET | `/filings` | `backend/app/routers/ajuizamento.py:174` |
| GET | `/financeiro` | `backend/app/routers/portal.py:154` |
| GET | `/fontes` | `backend/app/routers/ia_governanca.py:513` |
| GET | `/funil` | `backend/app/routers/analytics.py:56` |
| GET | `/guardrails` | `backend/app/routers/ia_governanca.py:593` |
| GET | `/historico/{case_id}` | `backend/app/routers/ia_defensiva.py:98` |
| GET | `/hoje` | `backend/app/routers/dashboard.py:225` |
| GET | `/honorarios.csv` | `backend/app/routers/export.py:312` |
| GET | `/imobiliario/ferramentas/distrato` | `backend/app/routers/ramos_vitrine.py:1174` |
| GET | `/imobiliario/ferramentas/prazos-despejo` | `backend/app/routers/ramos_vitrine.py:323` |
| GET | `/imobiliario/ferramentas/reajuste-aluguel` | `backend/app/routers/ramos_vitrine.py:272` |
| GET | `/impacto-regulatorio` | `backend/app/routers/teses.py:278` |
| GET | `/inadimplencia/alertas` | `backend/app/routers/novos_modulos.py:94` |
| GET | `/indicativos` | `backend/app/routers/saneamento.py:548` |
| GET | `/inss` | `backend/app/routers/calculadoras.py:80` |
| GET | `/integrations` | `backend/app/routers/system_modules.py:86` |
| GET | `/integridade` | `backend/app/routers/saneamento.py:158` |
| GET | `/interno/analise-prospectiva` | `backend/app/routers/jurimetria.py:611` |
| GET | `/interno/benchmarks` | `backend/app/routers/jurimetria.py:565` |
| GET | `/interno/stats` | `backend/app/routers/jurimetria.py:523` |
| GET | `/irrf` | `backend/app/routers/calculadoras.py:89` |
| GET | `/itens` | `backend/app/routers/honorarios_oab.py:201` |
| GET | `/jurimetria` | `backend/app/routers/analytics.py:31` |
| GET | `/jurisprudencia-mg/geometria` | `backend/app/routers/ia_governanca.py:611` |
| GET | `/jurisprudencia-mg` | `backend/app/routers/ia_governanca.py:740` |
| GET | `/keywords` | `backend/app/routers/diario_oficial.py:63` |
| GET | `/list` | `backend/app/routers/ai_skills.py:264` |
| GET | `/logs/feedback/resumo` | `backend/app/routers/ai.py:543` |
| GET | `/logs/{log_id}/citacoes` | `backend/app/routers/ai.py:441` |
| GET | `/logs` | `backend/app/routers/ai.py:288` |
| GET | `/mapa` | `backend/app/routers/system_modules.py:48` |
| GET | `/matriz` | `backend/app/routers/provas.py:475` |
| GET | `/me/security` | `backend/app/routers/users.py:158` |
| GET | `/me/sessions` | `backend/app/routers/users.py:182` |
| GET | `/me/url` | `backend/app/routers/calendar_feed.py:102` |
| GET | `/me` | `backend/app/routers/advogado_estilo.py:21` |
| GET | `/memoria/{modalidade}` | `backend/app/routers/defesas_revisoes_avancado.py:577` |
| GET | `/mensagens/nao-lidas` | `backend/app/routers/portal.py:231` |
| GET | `/mensal/{mes}/pacote` | `backend/app/routers/relatorio.py:244` |
| GET | `/mensal` | `backend/app/routers/relatorio.py:26` |
| GET | `/meta` | `backend/app/routers/defesas_revisoes.py:242` |
| GET | `/meta` | `backend/app/routers/entrada_universal.py:295` |
| GET | `/meta` | `backend/app/routers/peca_geracao.py:76` |
| GET | `/meus-casos` | `backend/app/routers/portal.py:39` |
| GET | `/meus` | `backend/app/routers/atendimentos.py:758` |
| GET | `/modalidades` | `backend/app/routers/analise_bancaria.py:168` |
| GET | `/monitor-legislativo` | `backend/app/routers/rag.py:428` |
| GET | `/motor/async/{task_id}` | `backend/app/routers/teses.py:879` |
| GET | `/native-skills/coverage` | `backend/app/routers/ai_core.py:232` |
| GET | `/onboarding/{client_id}` | `backend/app/routers/analytics.py:85` |
| GET | `/onboarding` | `backend/app/routers/analytics.py:75` |
| GET | `/operacional` | `backend/app/routers/financeiro/dashboard.py:525` |
| GET | `/overview` | `backend/app/routers/jurimetria.py:69` |
| GET | `/painel-semanal` | `backend/app/routers/consumidor_monitor.py:278` |
| GET | `/parecer/{arquivo_id}/download` | `backend/app/routers/previdenciario_beneficio.py:232` |
| GET | `/peca/{arquivo_id}/download` | `backend/app/routers/ambiental_estrategia.py:239` |
| GET | `/penal/ferramentas/dosimetria` | `backend/app/routers/ramos_vitrine.py:725` |
| GET | `/penal/ferramentas/prazos-processuais` | `backend/app/routers/ramos_penal.py:130` |
| GET | `/penal/ferramentas/prescricao-penal` | `backend/app/routers/ramos_vitrine.py:703` |
| GET | `/penal/ferramentas/prescricao-punitiva` | `backend/app/routers/ramos_penal.py:262` |
| GET | `/penal/ferramentas/verificar-anpp` | `backend/app/routers/ramos_penal.py:184` |
| GET | `/penal` | `backend/app/routers/ramos_penal.py:96` |
| GET | `/perfis` | `backend/app/routers/ajuizamento.py:103` |
| GET | `/perfis` | `backend/app/routers/ia_especializada.py:52` |
| GET | `/planilha/{arquivo_id}/download` | `backend/app/routers/trabalhista_liquidacao.py:337` |
| GET | `/politica` | `backend/app/routers/financeiro/governanca.py:31` |
| GET | `/por-advogado/{advogado_id}` | `backend/app/routers/atendimentos.py:785` |
| GET | `/por-area` | `backend/app/routers/jurimetria.py:134` |
| GET | `/por-magistrado` | `backend/app/routers/jurimetria.py:188` |
| GET | `/por-tese` | `backend/app/routers/jurimetria.py:303` |
| GET | `/por-tribunal` | `backend/app/routers/jurimetria.py:248` |
| GET | `/precificacao/calcular/{rule_id}` | `backend/app/routers/novos_modulos.py:48` |
| GET | `/precificacao/tabela` | `backend/app/routers/novos_modulos.py:37` |
| GET | `/preferences` | `backend/app/routers/notifications.py:150` |
| GET | `/prescricao/tipos` | `backend/app/routers/calculadoras.py:131` |
| GET | `/previdenciario/ferramentas/carencia` | `backend/app/routers/ramos_vitrine.py:584` |
| GET | `/previdenciario/ferramentas/prazos` | `backend/app/routers/ramos_vitrine.py:376` |
| GET | `/previdenciario/ferramentas/tempo-contribuicao` | `backend/app/routers/ramos_vitrine.py:552` |
| GET | `/produtividade` | `backend/app/routers/produtividade.py:28` |
| GET | `/prompts-sistema` | `backend/app/routers/ia_governanca.py:497` |
| GET | `/prompts` | `backend/app/routers/ia_governanca.py:481` |
| GET | `/protocolos` | `backend/app/routers/ajuizamento.py:362` |
| GET | `/provedores` | `backend/app/routers/ia_governanca.py:818` |
| GET | `/ptax` | `backend/app/routers/indices.py:83` |
| GET | `/push/subscriptions` | `backend/app/routers/notifications.py:252` |
| GET | `/push/vapid-key` | `backend/app/routers/notifications.py:244` |
| GET | `/qrcode` | `backend/app/routers/whatsapp.py:97` |
| GET | `/radar/legislativo` | `backend/app/routers/intelligence.py:21` |
| GET | `/radar/today` | `backend/app/modules/dpt360/router.py:115` |
| GET | `/radar` | `backend/app/routers/compliance.py:265` |
| GET | `/rag-curadoria` | `backend/app/routers/ia_governanca.py:393` |
| GET | `/ranking` | `backend/app/routers/teses.py:173` |
| GET | `/recentes` | `backend/app/routers/movimentos.py:15` |
| GET | `/regras-transicao` | `backend/app/routers/previdenciario_beneficio.py:81` |
| GET | `/relatorio-mensal` | `backend/app/routers/dashboard.py:468` |
| GET | `/rentabilidade` | `backend/app/routers/analytics.py:65` |
| GET | `/rentabilidade` | `backend/app/routers/financeiro/governanca.py:162` |
| GET | `/reports/executive/{client_id}` | `backend/app/modules/dpt360/router.py:124` |
| GET | `/responsaveis` | `backend/app/routers/atendimentos.py:629` |
| GET | `/resumo` | `backend/app/routers/atividades.py:361` |
| GET | `/resumo` | `backend/app/routers/despesas.py:147` |
| GET | `/resumo` | `backend/app/routers/fees.py:149` |
| GET | `/ripd/{arquivo_id}/download` | `backend/app/routers/lgpd_registros.py:418` |
| GET | `/roi-por-area` | `backend/app/routers/produtividade.py:169` |
| GET | `/roteamento/preview` | `backend/app/routers/ai.py:720` |
| GET | `/routes` | `backend/app/routers/architecture.py:15` |
| GET | `/saude` | `backend/app/routers/rag_governance.py:201` |
| GET | `/semantic-audit` | `backend/app/routers/architecture.py:21` |
| GET | `/series` | `backend/app/routers/indices.py:58` |
| GET | `/settings` | `backend/app/routers/module_settings.py:58` |
| GET | `/skills` | `backend/app/routers/ai_core.py:226` |
| GET | `/socio/{user_id}` | `backend/app/routers/extratos.py:75` |
| GET | `/socios` | `backend/app/routers/gestao_societaria.py:138` |
| GET | `/solicitacoes-documentos` | `backend/app/routers/portal_documentos.py:64` |
| GET | `/solicitacoes-resumo` | `backend/app/routers/atendimentos.py:657` |
| GET | `/stats` | `backend/app/routers/atendimentos.py:852` |
| GET | `/stats` | `backend/app/routers/cases.py:276` |
| GET | `/stats` | `backend/app/routers/rag.py:36` |
| GET | `/stats` | `backend/app/routers/raio_x.py:138` |
| GET | `/status-captura` | `backend/app/routers/intimacoes.py:134` |
| GET | `/status` | `backend/app/routers/ai_core.py:238` |
| GET | `/status` | `backend/app/routers/ai_tools.py:86` |
| GET | `/status` | `backend/app/routers/backup_admin.py:100` |
| GET | `/status` | `backend/app/routers/cerebro.py:17` |
| GET | `/status` | `backend/app/routers/diario_oficial.py:47` |
| GET | `/status` | `backend/app/routers/google_drive_knowledge.py:31` |
| GET | `/status` | `backend/app/routers/ia_defensiva.py:50` |
| GET | `/status` | `backend/app/routers/infosimples_tjmg.py:66` |
| GET | `/status` | `backend/app/routers/nfse.py:355` |
| GET | `/status` | `backend/app/routers/rag.py:52` |
| GET | `/status` | `backend/app/routers/transparencia.py:46` |
| GET | `/status` | `backend/app/routers/validador_juridico.py:32` |
| GET | `/status` | `backend/app/routers/whatsapp.py:85` |
| GET | `/tabela` | `backend/app/routers/honorarios_oab.py:91` |
| GET | `/taskscore` | `backend/app/routers/analytics.py:47` |
| GET | `/taxa-juros` | `backend/app/routers/indices.py:65` |
| GET | `/taxa-media` | `backend/app/routers/analise_bancaria.py:195` |
| GET | `/templates` | `backend/app/routers/checklists.py:124` |
| GET | `/templates` | `backend/app/routers/workflow.py:112` |
| GET | `/tendencias` | `backend/app/routers/jurimetria.py:341` |
| GET | `/teses` | `backend/app/routers/cerebro.py:72` |
| GET | `/tipos-rescisao` | `backend/app/routers/calculadoras.py:59` |
| GET | `/tipos` | `backend/app/routers/documents.py:231` |
| GET | `/tpu/cobertura` | `backend/app/routers/saneamento.py:760` |
| GET | `/tpu/{tipo}` | `backend/app/routers/ajuizamento.py:141` |
| GET | `/trabalhista-esp/ferramentas/deposito-recursal` | `backend/app/routers/ramos_trabalhista_esp.py:236` |
| GET | `/trabalhista-esp/ferramentas/horas-extras` | `backend/app/routers/ramos_vitrine.py:832` |
| GET | `/trabalhista-esp/ferramentas/prazos` | `backend/app/routers/ramos_trabalhista_esp.py:139` |
| GET | `/trabalhista-esp/ferramentas/prescricao-trabalhista` | `backend/app/routers/ramos_trabalhista_esp.py:183` |
| GET | `/trabalhista-esp/ferramentas/verbas-rescisorias` | `backend/app/routers/ramos_ferramentas_complementares.py:324` |
| GET | `/trabalhista-esp` | `backend/app/routers/ramos_trabalhista_esp.py:99` |
| GET | `/trabalhista/ferramentas/horas-extras` | `backend/app/routers/ramos_vitrine.py:896` |
| GET | `/transito/ferramentas/pontuacao-cnh` | `backend/app/routers/ramos_admin_esp.py:278` |
| GET | `/transito/ferramentas/prazos-recurso` | `backend/app/routers/ramos_admin_esp.py:254` |
| GET | `/transito/ferramentas/valor-multa` | `backend/app/routers/ramos_vitrine.py:1243` |
| GET | `/triagem-jec` | `backend/app/routers/consumidor_monitor.py:205` |
| GET | `/tribunais/desfechos` | `backend/app/routers/jurimetria.py:748` |
| GET | `/tribunais/status` | `backend/app/routers/jurimetria.py:740` |
| GET | `/tribunais` | `backend/app/routers/suspensoes.py:60` |
| GET | `/tributario/ferramentas/auto-infracao-prazos` | `backend/app/routers/ramos_ferramentas_complementares.py:469` |
| GET | `/tributario/ferramentas/multa-mora` | `backend/app/routers/ramos_vitrine.py:1097` |
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
| GET | `/{analysis_id}/excel` | `backend/app/routers/bank_analysis.py:204` |
| GET | `/{analysis_id}` | `backend/app/routers/bank_analysis.py:182` |
| GET | `/{atendimento_id}/historico` | `backend/app/routers/atendimentos.py:909` |
| GET | `/{atendimento_id}` | `backend/app/routers/atendimentos.py:947` |
| GET | `/{batch_id}` | `backend/app/routers/entrada_universal.py:519` |
| GET | `/{case_id}/andamentos/status` | `backend/app/routers/andamentos.py:36` |
| GET | `/{case_id}/encerrar/diagnostico` | `backend/app/routers/cases.py:1390` |
| GET | `/{case_id}/financeiro/resumo` | `backend/app/routers/cases.py:1162` |
| GET | `/{case_id}/historico` | `backend/app/routers/dossie_estrategico.py:147` |
| GET | `/{case_id}/modulos` | `backend/app/routers/dossie_estrategico.py:128` |
| GET | `/{case_id}/movimentos` | `backend/app/routers/cases.py:962` |
| GET | `/{case_id}/teses-sugeridas` | `backend/app/routers/cases.py:1935` |
| GET | `/{case_id}/{dossie_id}/pdf` | `backend/app/routers/dossie_estrategico.py:214` |
| GET | `/{case_id}` | `backend/app/routers/cases.py:469` |
| GET | `/{case_id}` | `backend/app/routers/dossie_estrategico.py:90` |
| GET | `/{checklist_id}` | `backend/app/routers/checklists.py:340` |
| GET | `/{client_id}/dados-lgpd.json` | `backend/app/routers/clients.py:1122` |
| GET | `/{client_id}/esquecimento/bloqueios` | `backend/app/routers/clients.py:1182` |
| GET | `/{client_id}/pending-items` | `backend/app/routers/pending_items.py:168` |
| GET | `/{client_id}/relatorio-lgpd` | `backend/app/routers/clients.py:1050` |
| GET | `/{client_id}/resumo` | `backend/app/routers/lgpd_registros.py:250` |
| GET | `/{client_id}` | `backend/app/routers/clients.py:720` |
| GET | `/{com_id}/prazo-sugerido` | `backend/app/routers/intimacoes.py:265` |
| GET | `/{contract_id}` | `backend/app/routers/office_contracts.py:212` |
| GET | `/{contrato_id}` | `backend/app/routers/contratos_societarios.py:244` |
| GET | `/{doc_id}/download` | `backend/app/routers/documents.py:703` |
| GET | `/{doc_id}/exportar-docx` | `backend/app/routers/legal_docs.py:1523` |
| GET | `/{doc_id}/jurisprudencia-check` | `backend/app/routers/legal_docs.py:660` |
| GET | `/{doc_id}/pdf-minuta` | `backend/app/routers/legal_docs.py:1292` |
| GET | `/{doc_id}/pdf` | `backend/app/routers/legal_docs.py:1345` |
| GET | `/{doc_id}/validacao` | `backend/app/routers/legal_docs.py:489` |
| GET | `/{doc_id}` | `backend/app/routers/documents.py:676` |
| GET | `/{doc_id}` | `backend/app/routers/legal_docs.py:468` |
| GET | `/{fee_id}/estornos` | `backend/app/routers/fees.py:780` |
| GET | `/{fee_id}/pagamentos` | `backend/app/routers/fees.py:418` |
| GET | `/{fee_id}/rateio` | `backend/app/routers/honorarios_oab.py:610` |
| GET | `/{indice}` | `backend/app/routers/indices.py:136` |
| GET | `/{juri_id}` | `backend/app/routers/jurisprudencia_interna.py:132` |
| GET | `/{mem_id}` | `backend/app/routers/memoria_institucional.py:198` |
| GET | `/{module_key:path}` | `backend/app/routers/module_help.py:82` |
| GET | `/{nota_id}/pdf` | `backend/app/routers/nfse.py:767` |
| GET | `/{nota_id}/xml` | `backend/app/routers/nfse.py:803` |
| GET | `/{nota_id}` | `backend/app/routers/nfse.py:740` |
| GET | `/{pid}/proveniencia` | `backend/app/routers/processes.py:126` |
| GET | `/{prompt_id}` | `backend/app/routers/prompts_juridicos.py:180` |
| GET | `/{provider_key}/{field_key}/historico` | `backend/app/routers/credential_vault.py:279` |
| GET | `/{room_id}` | `backend/app/routers/data_room.py:370` |
| GET | `/{session_id}/estado` | `backend/app/routers/legal_chat.py:191` |
| GET | `/{session_id}/exportar` | `backend/app/routers/legal_chat.py:412` |
| GET | `/{session_id}` | `backend/app/routers/legal_chat.py:114` |
| GET | `/{sig_id}/documento` | `backend/app/routers/signatures.py:244` |
| GET | `/{snapshot_id}` | `backend/app/routers/case_intelligence.py:77` |
| GET | `/{sociedade_id}` | `backend/app/routers/sociedades_cliente.py:266` |
| GET | `/{tese_id}/casos-candidatos` | `backend/app/routers/teses.py:412` |
| GET | `/{tese_id}` | `backend/app/routers/teses.py:359` |
| GET | `/{tpl_id}` | `backend/app/routers/templates.py:140` |
| PATCH | `/admin-esp/{aid}` | `backend/app/routers/ramos_admin_esp.py:127` |
| PATCH | `/alertas/{alerta_id}/marcar-lido` | `backend/app/routers/diario_oficial.py:148` |
| PATCH | `/alertas/{source_type}/{source_id}` | `backend/app/routers/atividades.py:461` |
| PATCH | `/bancario/{bid}` | `backend/app/routers/ramos_bancario.py:125` |
| PATCH | `/civel/{cid}` | `backend/app/routers/ramos_civel.py:130` |
| PATCH | `/cofre/documentos/{document_id}/sensibilidade` | `backend/app/routers/novos_modulos.py:398` |
| PATCH | `/comissoes/regras/{rule_id}` | `backend/app/routers/financeiro/comissoes.py:1001` |
| PATCH | `/docs/{doc_id}` | `backend/app/routers/rag_governance.py:231` |
| PATCH | `/empresarial/{eid}` | `backend/app/routers/ramos_empresarial.py:133` |
| PATCH | `/filings/{filing_id}` | `backend/app/routers/ajuizamento.py:213` |
| PATCH | `/historico/{log_id}/status` | `backend/app/routers/ia_defensiva.py:146` |
| PATCH | `/inadimplencia/alertas/{alert_id}/resolver` | `backend/app/routers/novos_modulos.py:124` |
| PATCH | `/logs/{log_id}/hitl` | `backend/app/routers/ai.py:363` |
| PATCH | `/penal/{pid}` | `backend/app/routers/ramos_penal.py:118` |
| PATCH | `/perfis/{perfil_id}` | `backend/app/routers/ajuizamento.py:122` |
| PATCH | `/politica` | `backend/app/routers/financeiro/governanca.py:51` |
| PATCH | `/socios/{socio_id}` | `backend/app/routers/gestao_societaria.py:198` |
| PATCH | `/socios/{socio_id}` | `backend/app/routers/sociedades_cliente.py:394` |
| PATCH | `/trabalhista-esp/{tid}` | `backend/app/routers/ramos_trabalhista_esp.py:120` |
| PATCH | `/{analise_id}` | `backend/app/routers/raio_x.py:369` |
| PATCH | `/{atendimento_id}` | `backend/app/routers/atendimentos.py:962` |
| PATCH | `/{case_id}/movimentos/{movimento_id}` | `backend/app/routers/cases.py:1024` |
| PATCH | `/{case_id}/{dossie_id}/aprovar` | `backend/app/routers/dossie_estrategico.py:169` |
| PATCH | `/{case_id}` | `backend/app/routers/cases.py:496` |
| PATCH | `/{checklist_id}/itens/{item_id}/marcar` | `backend/app/routers/checklists.py:363` |
| PATCH | `/{client_id}/pending-items/{item_id}` | `backend/app/routers/pending_items.py:246` |
| PATCH | `/{client_id}` | `backend/app/routers/clients.py:848` |
| PATCH | `/{contract_id}` | `backend/app/routers/office_contracts.py:224` |
| PATCH | `/{contrato_id}` | `backend/app/routers/contratos_societarios.py:276` |
| PATCH | `/{deadline_id}/confirmar` | `backend/app/routers/deadlines.py:589` |
| PATCH | `/{deadline_id}` | `backend/app/routers/deadlines.py:516` |
| PATCH | `/{despesa_id}` | `backend/app/routers/despesas.py:488` |
| PATCH | `/{doc_id}/aprovar` | `backend/app/routers/legal_docs.py:774` |
| PATCH | `/{doc_id}/protocolo` | `backend/app/routers/legal_docs.py:1045` |
| PATCH | `/{doc_id}/publicacao-portal` | `backend/app/routers/documents.py:952` |
| PATCH | `/{doc_id}` | `backend/app/routers/documents.py:847` |
| PATCH | `/{doc_id}` | `backend/app/routers/legal_docs.py:541` |
| PATCH | `/{env_id}` | `backend/app/routers/environmental.py:143` |
| PATCH | `/{evento_id}` | `backend/app/routers/agenda_eventos.py:189` |
| PATCH | `/{fee_id}` | `backend/app/routers/fees.py:314` |
| PATCH | `/{help_id}` | `backend/app/routers/module_help.py:111` |
| PATCH | `/{juri_id}` | `backend/app/routers/jurisprudencia_interna.py:153` |
| PATCH | `/{lancamento_id}` | `backend/app/routers/centro_custos.py:348` |
| PATCH | `/{mem_id}` | `backend/app/routers/memoria_institucional.py:207` |
| PATCH | `/{parte_id}` | `backend/app/routers/case_partes.py:259` |
| PATCH | `/{pid}` | `backend/app/routers/processes.py:88` |
| PATCH | `/{prompt_id}` | `backend/app/routers/prompts_juridicos.py:200` |
| PATCH | `/{prova_id}` | `backend/app/routers/provas.py:185` |
| PATCH | `/{registro_id}` | `backend/app/routers/lgpd_registros.py:196` |
| PATCH | `/{room_id}/arquivos/{arquivo_id}/publicacao` | `backend/app/routers/data_room.py:480` |
| PATCH | `/{session_id}/estado` | `backend/app/routers/legal_chat.py:170` |
| PATCH | `/{session_id}` | `backend/app/routers/legal_chat.py:134` |
| PATCH | `/{sociedade_id}` | `backend/app/routers/sociedades_cliente.py:308` |
| PATCH | `/{task_id}` | `backend/app/routers/tasks.py:228` |
| PATCH | `/{tese_id}` | `backend/app/routers/teses.py:375` |
| PATCH | `/{withdrawal_id}/approve` | `backend/app/routers/partner_withdrawals.py:172` |
| PATCH | `/{withdrawal_id}/pay` | `backend/app/routers/partner_withdrawals.py:262` |
| PATCH | `/{withdrawal_id}/reject` | `backend/app/routers/partner_withdrawals.py:217` |
| POST | `/` | `backend/app/routers/agenda_eventos.py:151` |
| POST | `/` | `backend/app/routers/cases.py:341` |
| POST | `/` | `backend/app/routers/clients.py:499` |
| POST | `/` | `backend/app/routers/deadlines.py:400` |
| POST | `/` | `backend/app/routers/environmental.py:100` |
| POST | `/` | `backend/app/routers/fees.py:249` |
| POST | `/` | `backend/app/routers/legal_docs.py:430` |
| POST | `/` | `backend/app/routers/module_help.py:98` |
| POST | `/` | `backend/app/routers/procuracoes.py:78` |
| POST | `/` | `backend/app/routers/raio_x.py:223` |
| POST | `/` | `backend/app/routers/signatures.py:74` |
| POST | `/` | `backend/app/routers/suspensoes.py:89` |
| POST | `/` | `backend/app/routers/tasks.py:192` |
| POST | `/` | `backend/app/routers/templates.py:159` |
| POST | `/` | `backend/app/routers/timesheet.py:75` |
| POST | `/` | `backend/app/routers/users.py:363` |
| POST | `/abusividade` | `backend/app/routers/analise_bancaria.py:268` |
| POST | `/admin-esp` | `backend/app/routers/ramos_admin_esp.py:103` |
| POST | `/adversarial` | `backend/app/routers/defesas_revisoes_avancado.py:263` |
| POST | `/agente/stream` | `backend/app/routers/ia_agente.py:35` |
| POST | `/alterar-senha` | `backend/app/routers/auth.py:533` |
| POST | `/analisar-caso/async` | `backend/app/routers/ai.py:166` |
| POST | `/analisar-caso` | `backend/app/routers/ai.py:83` |
| POST | `/analisar-contrato` | `backend/app/routers/ai.py:1259` |
| POST | `/analisar-decisao` | `backend/app/routers/defesas_revisoes_avancado.py:535` |
| POST | `/analisar` | `backend/app/routers/defesas_revisoes.py:259` |
| POST | `/analisar` | `backend/app/routers/entrada.py:53` |
| POST | `/analisar` | `backend/app/routers/ia_capacidades.py:86` |
| POST | `/analisar` | `backend/app/routers/ia_defensiva.py:176` |
| POST | `/analise-estrategica` | `backend/app/routers/cerebro.py:21` |
| POST | `/analise-impacto` | `backend/app/routers/intelligence.py:39` |
| POST | `/analise-prospectiva` | `backend/app/routers/jurimetria.py:386` |
| POST | `/analyze` | `backend/app/routers/ai_core.py:155` |
| POST | `/aprovacoes/{approval_id}/aprovar` | `backend/app/routers/financeiro/governanca.py:133` |
| POST | `/atualizar-valor` | `backend/app/routers/indices.py:103` |
| POST | `/auditar-peca` | `backend/app/routers/ai.py:639` |
| POST | `/bancario` | `backend/app/routers/ramos_bancario.py:107` |
| POST | `/breakeven` | `backend/app/routers/visual_law.py:143` |
| POST | `/buscar` | `backend/app/routers/precedentes_jurisprudencia.py:36` |
| POST | `/calcular-especialidade` | `backend/app/routers/defesas_revisoes_avancado.py:336` |
| POST | `/calcular` | `backend/app/routers/deadlines.py:204` |
| POST | `/calcular` | `backend/app/routers/score_juridico.py:54` |
| POST | `/calcular` | `backend/app/routers/trabalhista_liquidacao.py:139` |
| POST | `/capturar-agora` | `backend/app/routers/intimacoes.py:434` |
| POST | `/cases/{case_id}/sync-prazos` | `backend/app/routers/datajud.py:125` |
| POST | `/cases/{case_id}/sync` | `backend/app/routers/datajud.py:82` |
| POST | `/caso/{case_id}/estrategia` | `backend/app/routers/ai.py:1132` |
| POST | `/caso/{case_id}/faturar` | `backend/app/routers/timesheet.py:93` |
| POST | `/caso/{case_id}/gerar-ia` | `backend/app/routers/checklists.py:283` |
| POST | `/caso/{case_id}/visual-law` | `backend/app/routers/ai.py:1090` |
| POST | `/casos/{case_id}/analise-completa` | `backend/app/routers/intake.py:364` |
| POST | `/casos/{case_id}/aplicar-padrao` | `backend/app/routers/workflow.py:276` |
| POST | `/casos/{case_id}/assistente` | `backend/app/routers/ai.py:794` |
| POST | `/casos/{case_id}/avancar` | `backend/app/routers/workflow.py:367` |
| POST | `/casos/{case_id}/concluir` | `backend/app/routers/workflow.py:468` |
| POST | `/casos/{case_id}/dual` | `backend/app/routers/ai.py:942` |
| POST | `/casos/{case_id}/iniciar` | `backend/app/routers/workflow.py:228` |
| POST | `/casos/{case_id}/mensagens` | `backend/app/routers/portal.py:274` |
| POST | `/casos/{case_id}/proposta/sugerir` | `backend/app/routers/honorarios_oab.py:356` |
| POST | `/casos/{case_id}/proposta` | `backend/app/routers/honorarios_oab.py:374` |
| POST | `/cet` | `backend/app/routers/analise_bancaria.py:233` |
| POST | `/chat` | `backend/app/routers/ai_core.py:117` |
| POST | `/checar-conflito` | `backend/app/routers/clients.py:243` |
| POST | `/citacoes/verificar` | `backend/app/routers/ai.py:57` |
| POST | `/civel` | `backend/app/routers/ramos_civel.py:110` |
| POST | `/cobranca` | `backend/app/routers/pix.py:94` |
| POST | `/cofre/documentos/{document_id}/registrar-acesso` | `backend/app/routers/novos_modulos.py:345` |
| POST | `/comissoes/fechamentos` | `backend/app/routers/financeiro/comissoes.py:597` |
| POST | `/comissoes/lotes-pagamento` | `backend/app/routers/financeiro/comissoes.py:668` |
| POST | `/comissoes/regras` | `backend/app/routers/financeiro/comissoes.py:960` |
| POST | `/comissoes/{allocation_id}/ajustes` | `backend/app/routers/financeiro/comissoes.py:347` |
| POST | `/comissoes/{allocation_id}/enviar-aprovacao` | `backend/app/routers/financeiro/comissoes.py:272` |
| POST | `/comparar-documentos` | `backend/app/routers/defesas_revisoes_avancado.py:206` |
| POST | `/conciliacao/confirmar` | `backend/app/routers/financeiro/governanca.py:883` |
| POST | `/consistencia` | `backend/app/routers/qualidade.py:74` |
| POST | `/contrato` | `backend/app/routers/analise_bancaria.py:131` |
| POST | `/conversar` | `backend/app/routers/ia_capacidades.py:119` |
| POST | `/correcao-monetaria` | `backend/app/routers/calculadoras.py:101` |
| POST | `/critica-adversarial` | `backend/app/routers/ia_adversarial.py:42` |
| POST | `/curadoria/apply` | `backend/app/routers/google_drive_knowledge.py:115` |
| POST | `/curadoria/preview` | `backend/app/routers/google_drive_knowledge.py:92` |
| POST | `/deep-research/juridica` | `backend/app/routers/peca_geracao.py:414` |
| POST | `/demonstrativo` | `backend/app/routers/peca_geracao.py:501` |
| POST | `/detectar-prazos` | `backend/app/routers/ai.py:1290` |
| POST | `/distribuicao/{dist_id}/aprovar` | `backend/app/routers/gestao_societaria.py:404` |
| POST | `/distribuicao` | `backend/app/routers/gestao_societaria.py:259` |
| POST | `/divergencias/{divergencia_id}/aplicar` | `backend/app/routers/saneamento.py:690` |
| POST | `/docs/{doc_id}/revisar` | `backend/app/routers/rag_governance.py:326` |
| POST | `/docs/{doc_id}/testar` | `backend/app/routers/rag_governance.py:391` |
| POST | `/documento-unico` | `backend/app/routers/provas.py:616` |
| POST | `/docx` | `backend/app/routers/export.py:280` |
| POST | `/drive/upload` | `backend/app/routers/documents.py:1105` |
| POST | `/due-diligence/template` | `backend/app/routers/sociedades_cliente.py:147` |
| POST | `/due-diligence/templates` | `backend/app/routers/novos_modulos.py:289` |
| POST | `/duplicatas/{plano_id}/aplicar` | `backend/app/routers/saneamento.py:460` |
| POST | `/emitir` | `backend/app/routers/nfse.py:569` |
| POST | `/empresarial` | `backend/app/routers/ramos_empresarial.py:122` |
| POST | `/entrevista` | `backend/app/routers/triagem_entrevista.py:52` |
| POST | `/estimar` | `backend/app/routers/honorarios_oab.py:100` |
| POST | `/evolution` | `backend/app/routers/evolution_webhook.py:72` |
| POST | `/executar` | `backend/app/routers/ai_tools.py:111` |
| POST | `/executar` | `backend/app/routers/backup_admin.py:27` |
| POST | `/execute-doc` | `backend/app/routers/ai_skills.py:329` |
| POST | `/execute` | `backend/app/routers/ai_skills.py:288` |
| POST | `/ext/ingerir/datajud` | `backend/app/routers/jurimetria.py:715` |
| POST | `/ext/predicao/treinar` | `backend/app/routers/jurimetria.py:699` |
| POST | `/extrair` | `backend/app/routers/ia_capacidades.py:130` |
| POST | `/faq` | `backend/app/routers/conteudo.py:60` |
| POST | `/fechamentos` | `backend/app/routers/financeiro/governanca.py:397` |
| POST | `/filings/{filing_id}/aprovar` | `backend/app/routers/ajuizamento.py:243` |
| POST | `/filings/{filing_id}/assinar` | `backend/app/routers/ajuizamento.py:260` |
| POST | `/filings/{filing_id}/cancelar` | `backend/app/routers/ajuizamento.py:329` |
| POST | `/filings/{filing_id}/confirmar-manual` | `backend/app/routers/ajuizamento.py:297` |
| POST | `/filings/{filing_id}/protocolar` | `backend/app/routers/ajuizamento.py:277` |
| POST | `/filings/{filing_id}/sincronizar` | `backend/app/routers/ajuizamento.py:312` |
| POST | `/filings/{filing_id}/validar` | `backend/app/routers/ajuizamento.py:228` |
| POST | `/filings` | `backend/app/routers/ajuizamento.py:192` |
| POST | `/frontend-error` | `backend/app/routers/observabilidade.py:27` |
| POST | `/gateway/health` | `backend/app/routers/ai.py:711` |
| POST | `/generate` | `backend/app/routers/ai_core.py:175` |
| POST | `/gerar-minuta` | `backend/app/routers/ai.py:1473` |
| POST | `/gerar` | `backend/app/routers/anexos.py:108` |
| POST | `/gerar` | `backend/app/routers/peca_geracao.py:116` |
| POST | `/glossario` | `backend/app/routers/conteudo.py:79` |
| POST | `/importar-env` | `backend/app/routers/credential_vault.py:295` |
| POST | `/inadimplencia/varrer` | `backend/app/routers/novos_modulos.py:109` |
| POST | `/indicativos/{indicativo_id}/decidir` | `backend/app/routers/saneamento.py:580` |
| POST | `/ingerir-ai-log/{log_id}` | `backend/app/routers/rag.py:595` |
| POST | `/ingerir-seed` | `backend/app/routers/sumulas.py:29` |
| POST | `/ingest-pdf` | `backend/app/routers/rag.py:184` |
| POST | `/ingest-url` | `backend/app/routers/rag.py:231` |
| POST | `/ingest` | `backend/app/routers/rag.py:318` |
| POST | `/instanciar` | `backend/app/routers/checklists.py:204` |
| POST | `/itens/{item_id}/encerrar-vigencia` | `backend/app/routers/honorarios_oab.py:274` |
| POST | `/itens` | `backend/app/routers/honorarios_oab.py:221` |
| POST | `/keywords` | `backend/app/routers/diario_oficial.py:78` |
| POST | `/ler-todas` | `backend/app/routers/notifications.py:212` |
| POST | `/login` | `backend/app/routers/auth.py:177` |
| POST | `/logout` | `backend/app/routers/auth.py:513` |
| POST | `/logs/{log_id}/feedback` | `backend/app/routers/ai.py:505` |
| POST | `/manual` | `backend/app/routers/nfse.py:402` |
| POST | `/messages` | `backend/app/routers/whatsapp.py:150` |
| POST | `/motor/async` | `backend/app/routers/teses.py:843` |
| POST | `/motor` | `backend/app/routers/teses.py:785` |
| POST | `/pacote` | `backend/app/routers/defesas_revisoes_avancado.py:774` |
| POST | `/parecer-pdf` | `backend/app/routers/previdenciario_beneficio.py:204` |
| POST | `/peca-conversao` | `backend/app/routers/ambiental_estrategia.py:213` |
| POST | `/penal` | `backend/app/routers/ramos_penal.py:103` |
| POST | `/perfis` | `backend/app/routers/ajuizamento.py:108` |
| POST | `/persistir` | `backend/app/routers/defesas_revisoes_avancado.py:400` |
| POST | `/pesquisar` | `backend/app/routers/ai.py:1561` |
| POST | `/planilha-pdf` | `backend/app/routers/trabalhista_liquidacao.py:311` |
| POST | `/pre-preencher` | `backend/app/routers/ficha_triagem.py:97` |
| POST | `/precificacao/regras` | `backend/app/routers/novos_modulos.py:78` |
| POST | `/predicao-exito` | `backend/app/routers/jurimetria.py:385` |
| POST | `/preencher-minimo` | `backend/app/routers/module_help.py:74` |
| POST | `/preparar-audiencia` | `backend/app/routers/ai.py:689` |
| POST | `/prescricao` | `backend/app/routers/calculadoras.py:141` |
| POST | `/preview` | `backend/app/routers/anexos.py:75` |
| POST | `/processar` | `backend/app/routers/entrada_universal.py:384` |
| POST | `/propostas/{proposta_id}/aprovar` | `backend/app/routers/honorarios_oab.py:428` |
| POST | `/propostas/{proposta_id}/rejeitar` | `backend/app/routers/honorarios_oab.py:443` |
| POST | `/push/subscribe` | `backend/app/routers/notifications.py:303` |
| POST | `/razoes` | `backend/app/routers/anexos.py:131` |
| POST | `/recalcular` | `backend/app/routers/indice_risco.py:48` |
| POST | `/recorrentes/gerar` | `backend/app/routers/despesas.py:317` |
| POST | `/recuperar-senha` | `backend/app/routers/auth.py:632` |
| POST | `/redefinir-senha` | `backend/app/routers/auth.py:660` |
| POST | `/redigir` | `backend/app/routers/ia_capacidades.py:97` |
| POST | `/refresh` | `backend/app/routers/auth.py:343` |
| POST | `/reindex/{file_id}` | `backend/app/routers/google_drive_knowledge.py:181` |
| POST | `/report` | `backend/app/routers/ai_core.py:193` |
| POST | `/resolver` | `backend/app/routers/clients.py:103` |
| POST | `/resumir-documento` | `backend/app/routers/ai.py:243` |
| POST | `/resumir-texto` | `backend/app/routers/ai.py:1426` |
| POST | `/resumir` | `backend/app/routers/ia_capacidades.py:108` |
| POST | `/seed` | `backend/app/routers/rag.py:483` |
| POST | `/send` | `backend/app/routers/whatsapp.py:109` |
| POST | `/simular-adversario` | `backend/app/routers/qualidade.py:90` |
| POST | `/simular` | `backend/app/routers/ambiental_estrategia.py:90` |
| POST | `/simular` | `backend/app/routers/suspensoes.py:141` |
| POST | `/socios` | `backend/app/routers/gestao_societaria.py:157` |
| POST | `/solicitacoes-documentos/itens/{item_id}/upload` | `backend/app/routers/portal_documentos.py:125` |
| POST | `/sugerir-faltantes` | `backend/app/routers/provas.py:380` |
| POST | `/sugerir-ia` | `backend/app/routers/teses.py:528` |
| POST | `/sugerir-tipo` | `backend/app/routers/documents.py:262` |
| POST | `/sugestao-honorarios` | `backend/app/routers/ai.py:1636` |
| POST | `/sync` | `backend/app/routers/google_drive_knowledge.py:156` |
| POST | `/task` | `backend/app/routers/ai_core.py:135` |
| POST | `/templates` | `backend/app/routers/checklists.py:153` |
| POST | `/templates` | `backend/app/routers/workflow.py:140` |
| POST | `/teses-ocultas` | `backend/app/routers/ai.py:613` |
| POST | `/teses/{tese_id}/aprovar` | `backend/app/routers/matriz_teses.py:109` |
| POST | `/teses/{tese_id}/descartar` | `backend/app/routers/matriz_teses.py:121` |
| POST | `/testes-juridicos` | `backend/app/routers/rag_governance.py:422` |
| POST | `/totp/desativar` | `backend/app/routers/auth.py:803` |
| POST | `/totp/setup` | `backend/app/routers/auth.py:682` |
| POST | `/totp/verificar` | `backend/app/routers/auth.py:728` |
| POST | `/tpu/importar` | `backend/app/routers/ajuizamento.py:163` |
| POST | `/tpu/sincronizar` | `backend/app/routers/ajuizamento.py:151` |
| POST | `/trabalhista-esp` | `backend/app/routers/ramos_trabalhista_esp.py:106` |
| POST | `/trabalhista/rescisao` | `backend/app/routers/calculadoras.py:65` |
| POST | `/traduzir-andamento` | `backend/app/routers/ai.py:1394` |
| POST | `/transcribe-media` | `backend/app/routers/ai_skills.py:481` |
| POST | `/upload` | `backend/app/routers/bank_analysis.py:39` |
| POST | `/upload` | `backend/app/routers/documents.py:330` |
| POST | `/validar-citacoes` | `backend/app/routers/ia_citacoes.py:28` |
| POST | `/validar` | `backend/app/routers/validador_juridico.py:50` |
| POST | `/varredura` | `backend/app/routers/saneamento.py:776` |
| POST | `/verificar-citacoes` | `backend/app/routers/qualidade.py:67` |
| POST | `/verificar-conflito` | `backend/app/routers/clients.py:181` |
| POST | `/verificar-conflito` | `backend/app/routers/sumulas.py:103` |
| POST | `/viabilidade` | `backend/app/routers/defesas_revisoes_avancado.py:305` |
| POST | `/{analise_id}/arquivar` | `backend/app/routers/raio_x.py:712` |
| POST | `/{analise_id}/converter` | `backend/app/routers/raio_x.py:695` |
| POST | `/{analise_id}/descartar` | `backend/app/routers/raio_x.py:728` |
| POST | `/{analise_id}/reanalisar` | `backend/app/routers/raio_x.py:528` |
| POST | `/{analysis_id}/documento` | `backend/app/routers/bank_analysis.py:221` |
| POST | `/{analysis_id}/gerar-peca` | `backend/app/routers/bank_analysis.py:304` |
| POST | `/{batch_id}/preparar-pacote` | `backend/app/routers/entrada_universal.py:550` |
| POST | `/{batch_id}/vincular-caso` | `backend/app/routers/entrada_universal.py:643` |
| POST | `/{case_id}/analisar` | `backend/app/routers/cases.py:2045` |
| POST | `/{case_id}/aplicar-extracao` | `backend/app/routers/cases.py:1732` |
| POST | `/{case_id}/arquivar` | `backend/app/routers/cases.py:678` |
| POST | `/{case_id}/desarquivar` | `backend/app/routers/cases.py:718` |
| POST | `/{case_id}/encerrar-simples` | `backend/app/routers/cases.py:1257` |
| POST | `/{case_id}/encerrar` | `backend/app/routers/cases.py:1414` |
| POST | `/{case_id}/financeiro/recebimentos` | `backend/app/routers/cases.py:1179` |
| POST | `/{case_id}/gerar-documentos` | `backend/app/routers/cases.py:923` |
| POST | `/{case_id}/gerar` | `backend/app/routers/dossie_estrategico.py:66` |
| POST | `/{case_id}/movimentos` | `backend/app/routers/cases.py:988` |
| POST | `/{case_id}/reabrir` | `backend/app/routers/cases.py:761` |
| POST | `/{case_id}/sincronizar-processo` | `backend/app/routers/cases.py:1099` |
| POST | `/{checklist_id}/itens` | `backend/app/routers/checklists.py:428` |
| POST | `/{client_id}/criar-acesso` | `backend/app/routers/clients.py:998` |
| POST | `/{client_id}/esquecimento` | `backend/app/routers/clients.py:1205` |
| POST | `/{client_id}/pending-items` | `backend/app/routers/pending_items.py:202` |
| POST | `/{client_id}/ripd` | `backend/app/routers/lgpd_registros.py:374` |
| POST | `/{com_id}/aceitar-prazo` | `backend/app/routers/intimacoes.py:278` |
| POST | `/{com_id}/processar` | `backend/app/routers/intimacoes.py:211` |
| POST | `/{com_id}/recusar-prazo` | `backend/app/routers/intimacoes.py:396` |
| POST | `/{com_id}/sugerir-prazo` | `backend/app/routers/intimacoes.py:255` |
| POST | `/{contrato_id}/transicao` | `backend/app/routers/contratos_societarios.py:301` |
| POST | `/{deadline_id}/ciencia` | `backend/app/routers/deadlines.py:615` |
| POST | `/{doc_id}/conferir-e-assinar` | `backend/app/routers/legal_docs.py:864` |
| POST | `/{doc_id}/revisar` | `backend/app/routers/legal_docs.py:674` |
| POST | `/{doc_id}/validar` | `backend/app/routers/legal_docs.py:503` |
| POST | `/{entidade}/{registro_id}/purgar` | `backend/app/routers/trash.py:226` |
| POST | `/{entidade}/{registro_id}/restaurar` | `backend/app/routers/trash.py:154` |
| POST | `/{fee_id}/pagamentos/{payment_id}/estorno` | `backend/app/routers/fees.py:627` |
| POST | `/{fee_id}/pagamentos` | `backend/app/routers/fees.py:493` |
| POST | `/{fee_id}/rateio` | `backend/app/routers/honorarios_oab.py:621` |
| POST | `/{juri_id}/classificar-ia` | `backend/app/routers/jurisprudencia_interna.py:197` |
| POST | `/{key_id}/revogar` | `backend/app/routers/api_keys.py:94` |
| POST | `/{nota_id}/cancelar` | `backend/app/routers/nfse.py:839` |
| POST | `/{notif_id}/ler` | `backend/app/routers/notifications.py:195` |
| POST | `/{perfil}` | `backend/app/routers/ia_especializada.py:67` |
| POST | `/{pid}/arquivar` | `backend/app/routers/processes.py:163` |
| POST | `/{pid}/desarquivar` | `backend/app/routers/processes.py:197` |
| POST | `/{pid}/principal` | `backend/app/routers/processes.py:137` |
| POST | `/{proc_id}/minuta` | `backend/app/routers/procuracoes.py:103` |
| POST | `/{proc_id}/revogar` | `backend/app/routers/procuracoes.py:160` |
| POST | `/{prompt_id}/executar` | `backend/app/routers/prompts_juridicos.py:252` |
| POST | `/{provider_key}/testar` | `backend/app/routers/credential_vault.py:318` |
| POST | `/{provider_key}/{field_key}` | `backend/app/routers/credential_vault.py:345` |
| POST | `/{rascunho_id}/criar-caso` | `backend/app/routers/entrada.py:141` |
| POST | `/{room_id}/arquivos` | `backend/app/routers/data_room.py:435` |
| POST | `/{room_id}/links` | `backend/app/routers/data_room.py:560` |
| POST | `/{session_id}/proxima-acao/confirmar` | `backend/app/routers/legal_chat.py:210` |
| POST | `/{session_id}/saida` | `backend/app/routers/legal_chat.py:451` |
| POST | `/{sig_id}/assinar` | `backend/app/routers/signatures.py:346` |
| POST | `/{sig_id}/documento-visualizado` | `backend/app/routers/signatures.py:302` |
| POST | `/{sociedade_id}/eventos` | `backend/app/routers/sociedades_cliente.py:448` |
| POST | `/{sociedade_id}/socios` | `backend/app/routers/sociedades_cliente.py:349` |
| POST | `/{tese_id}/vincular-caso` | `backend/app/routers/teses.py:498` |
| POST | `/{tpl_id}/gerar` | `backend/app/routers/templates.py:182` |
| PUT | `/preferences` | `backend/app/routers/notifications.py:159` |

## 2. Registro de routers em main.py

```
410:app.include_router(agenda_eventos.router, prefix=API)
411:app.include_router(ai.router, prefix=API)
412:app.include_router(ai_core.router, prefix=API)
413:app.include_router(anexos.router, prefix=API)
414:app.include_router(ai_skills.router, prefix=API)
415:app.include_router(ai_tools.router, prefix=API)
416:app.include_router(analise_bancaria.router, prefix=API)
417:app.include_router(analytics.router, prefix=API)
418:app.include_router(andamentos.router, prefix=API)
419:app.include_router(areas.router, prefix=API)
420:app.include_router(atendimentos.router, prefix=API)
421:app.include_router(atividades.router, prefix=API)
422:app.include_router(audit.router, prefix=API)
423:app.include_router(auth.router, prefix=API)
424:app.include_router(backup_admin.router, prefix=API)
425:app.include_router(bank_analysis.router, prefix=API)
426:app.include_router(calculadoras.router, prefix=API)
427:app.include_router(calendar_feed.router, prefix=API)
428:app.include_router(case_intelligence.router, prefix=API)
429:app.include_router(case_partes.router, prefix=API)
430:app.include_router(cases.router, prefix=API)
431:app.include_router(caso_areas.router, prefix=API)
432:app.include_router(centro_custos.router, prefix=API, dependencies=[Depends(require_financeiro_enabled)])
433:app.include_router(cerebro.router, prefix=API)
434:app.include_router(checklists.router, prefix=API)
435:app.include_router(clients.router, prefix=API)
436:app.include_router(compliance.router, prefix=API)
437:app.include_router(consumidor_monitor.router, prefix=API)
438:app.include_router(conteudo.router, prefix=API)
439:app.include_router(contratos_societarios.router, prefix=API)
440:app.include_router(conversao_caso.router, prefix=API)
441:app.include_router(credential_vault.router, prefix=API)  # cofre de credenciais (superadmin)
442:app.include_router(dashboard.router, prefix=API)
443:app.include_router(dpt360_router, prefix=API)
444:app.include_router(data_room.router, prefix=API)
445:app.include_router(datajud.router, prefix=API)
446:app.include_router(deadlines.router, prefix=API)
447:app.include_router(despesas.router, prefix=API, dependencies=[Depends(require_financeiro_enabled)])
450:app.include_router(despesas_processuais.router, prefix=API, dependencies=[Depends(require_financeiro_enabled)])
451:app.include_router(diario_oficial.router, prefix=API)
452:app.include_router(raio_x.router, prefix=API)
453:app.include_router(legal_chat.router, prefix=API)
454:app.include_router(documents.router, prefix=API)
455:app.include_router(dossie_cliente.router, prefix=API)
456:app.include_router(dossie_estrategico.router, prefix=API)
457:app.include_router(environmental.router, prefix=API)
458:app.include_router(etiquetas.router, prefix=API)  # P3: prefixo canônico /etiquetas no router
459:app.include_router(etiquetas.casos_router, prefix=API)
460:app.include_router(evolution_webhook.router, prefix=API)
461:app.include_router(export.router, prefix=API)
462:app.include_router(extratos.router, prefix=API, dependencies=[Depends(require_financeiro_enabled)])
463:app.include_router(fees.router, prefix=API, dependencies=[Depends(require_financeiro_enabled)])
464:app.include_router(financeiro_consolidado.router, prefix=API, dependencies=[Depends(require_financeiro_enabled)])
465:app.include_router(gestao_societaria.router, prefix=API, dependencies=[Depends(require_financeiro_enabled)])
466:app.include_router(google_drive_knowledge.router, prefix=API)  # /api/rag/google-drive/* (curadoria da base, piso admin/socio)
467:app.include_router(ia_adversarial.router, prefix=API)
468:app.include_router(ia_agente.router, prefix=API)
471:app.include_router(ia_capacidades.router, prefix=API)
472:app.include_router(manus.router, prefix=API)  # Manus — Raciocínio Profundo explícito
473:app.include_router(ia_citacoes.router, prefix=API)
474:app.include_router(ia_defensiva.router, prefix=API)
475:app.include_router(ia_especializada.router, prefix=API)
476:app.include_router(ia_governanca.router, prefix=API)
477:app.include_router(ia_saude.router, prefix=API)
478:app.include_router(ia_saude.router_status, prefix=API)  # GET /api/ia/status
479:app.include_router(indice_risco.router, prefix=API)
480:app.include_router(indices.router, prefix=API)  # Índices oficiais BCB (SGS + Olinda) — Bloco 1 das APIs públicas
481:app.include_router(infosimples_receita.router, prefix=API)
482:app.include_router(infosimples_tjmg.router, prefix=API)
483:app.include_router(car.router, prefix=API)  # CAR/SICAR via Infosimples (consulta paga, reuso do conector)
484:app.include_router(transparencia.router, prefix=API)  # CGU sanções CEIS/CNEP/CEPIM — GATED (default off)
486:app.include_router(nfse.router, prefix=API)  # NFS-e (emissão fiscal GATED, homologação) — migração 085
487:app.include_router(intimacoes.router, prefix=API)
488:app.include_router(jurimetria.router, prefix=API)
489:app.include_router(licitacao_auditoria.router, prefix=API)  # auditoria preliminar de propostas (PDF)
490:app.include_router(juris_import.router, prefix=API)
491:app.include_router(jurisprudencia_interna.router, prefix=API)
492:app.include_router(kanban.router, prefix=API)  # P3: prefixo /kanban no router
493:app.include_router(kanban.casos_router, prefix=API)
494:app.include_router(kit_documental.router, prefix=API)  # POST /api/cases/{id}/kit-documental (P0.3)
495:app.include_router(legal_docs.router, prefix=API)
496:app.include_router(matriz_teses.router, prefix=API)  # FASE 3 Orquestrador — Matriz de Teses (migração 102)
497:app.include_router(orquestrador.router, prefix=API)  # FASE 5 Orquestrador — máquina de estados do caso
498:app.include_router(memoria_institucional.router, prefix=API)
499:app.include_router(honorarios_oab.router, prefix=API)  # frontend: /api/honorarios-oab/estimar (EstimadorHonorarios)
500:app.include_router(intake.router, prefix=API)  # frontend: /api/intake/casos/{id}/analise-completa (IntakeAnalise)
501:app.include_router(triagem_entrevista.router, prefix=API)  # frontend: /api/triagem/entrevista (EntrevistaInteligente — Jornada etapa 2)
502:app.include_router(entrada.router, prefix=API)  # Entrada Única (Bloco 3): /api/entrada/analisar + /api/entrada/{id}/criar-caso
503:app.include_router(ficha_triagem.router, prefix=API)  # frontend: /api/triagem/ficha (Ficha de Triagem pré-peça — gate de geração)
504:app.include_router(mensagens.router, prefix=API)
505:app.include_router(module_help.router, prefix=API)  # frontend: /api/module-help/* (HelpButton)
506:app.include_router(motor_peca.router, prefix=API)  # P1: Motor de Peça — /api/cases/{id}/motor-peca/*
507:app.include_router(movimentos.router, prefix=API)
508:app.include_router(saneamento.router, prefix=API)  # PROMPT 1: saneamento de base processual
509:app.include_router(notifications.router, prefix=API)
510:app.include_router(novos_modulos.router, prefix=API)  # P3: prefixo /modulos no router
511:app.include_router(entrada_universal.router, prefix=API) # P3: registro explícito (antes: routers/__init__.py montava dentro de novos_modulos)
512:app.include_router(defesas_revisoes.router, prefix=API)
513:app.include_router(defesas_revisoes_avancado.router, prefix=API)
514:app.include_router(novos_modulos.casos_router, prefix=API)
515:app.include_router(observabilidade.router, prefix=API)
516:app.include_router(office_contracts.router, prefix=API)
517:app.include_router(partner_withdrawals.router, prefix=API, dependencies=[Depends(require_financeiro_enabled)])
518:app.include_router(peca_geracao.router, prefix=API)
519:app.include_router(pending_items.router, prefix=API)
520:app.include_router(pix.router, prefix=API, dependencies=[Depends(require_financeiro_enabled)])
521:app.include_router(portal.router, prefix=API)
522:app.include_router(portal_documentos.router, prefix=API)  # Portal: solicitações de documentos + upload (migration 084)
523:app.include_router(solicitacoes_documentos.router, prefix=API)  # advogado: solicitação de documentos ao cliente (migration 084)
524:app.include_router(processes.router, prefix=API)  # P3: prefixo /processes no router
525:app.include_router(processes.casos_router, prefix=API)
526:app.include_router(procuracoes.router, prefix=API)
527:app.include_router(produtividade.router, prefix=API)
528:app.include_router(prompts_juridicos.router, prefix=API)
529:app.include_router(qualidade.router, prefix=API)
530:app.include_router(rag.router, prefix=API)
531:app.include_router(rag_public.router, prefix=API)      # API pública (X-API-Key)
540:app.include_router(                       # antes: jurisprudencia_externa.include_router(...)
542:app.include_router(                       # antes: peca_geracao.include_router(...)
544:app.include_router(                       # antes: append em rag.router.routes (prefixo absoluto)
546:app.include_router(intelligence.router, prefix=API)  # Intelligence canônico (consolidação: intelligence_v3 → intelligence)
547:app.include_router(                       # P3: prefixo canônico /datajud/intelligence (antes: andamentos.include_router + /casos)
549:app.include_router(                       # P3: rotas de caso /{case_id}/andamentos/* mantidas sob /casos
551:app.include_router(api_keys_router.router, prefix=API) # admin de chaves (JWT admin)
552:app.include_router(regulatorio.router, prefix=API)
553:app.include_router(radar_legislativo.router, prefix=API)  # Câmara+Senado+ALMG
554:app.include_router(ramos.router, prefix=API)
555:app.include_router(previdenciario_beneficio.router, prefix=API)  # vertical Previdenciário — regras de transição EC 103/2019 + RMI
556:app.include_router(relatorio.router, prefix=API)
557:app.include_router(relatorio_cliente.router, prefix=API)
558:app.include_router(score_juridico.router, prefix=API)
559:app.include_router(search.router, prefix=API)
560:app.include_router(signatures.router, prefix=API)
561:app.include_router(sociedades_cliente.router, prefix=API)  # gestão societária de CLIENTES (vertical Empresarial)
562:app.include_router(provas.router, prefix=API)  # Gestão de Provas por caso + Documento Único de Anexos (Visual Law)
563:app.include_router(processo_eletronico.router, prefix=API)  # Processo Eletrônico MNI 2.2.2 (Issue #762, Fase A leitura)
564:app.include_router(ajuizamento.router, prefix=API)  # Núcleo de ajuizamento e integração judicial (PDPJ/PJe-MNI/eproc/DataJud)
565:app.include_router(lgpd_registros.router, prefix=API)  # vertical LGPD — ROPA (art. 37) por cliente + RIPD (art. 38)
566:app.include_router(sumulas.router, prefix=API)  # P3: prefixo /sumulas no router
567:app.include_router(sumulas.casos_router, prefix=API)
568:app.include_router(suspensoes.router, prefix=API)
569:app.include_router(system_modules.router, prefix=API)  # Mapa de Módulos — governança modular
570:app.include_router(diagnostico.router, prefix=API)  # Central Eletrônica de Diagnóstico
571:app.include_router(module_settings.router, prefix=API)  # Lifecycle auditável dos módulos
572:app.include_router(tributario_fiscal.router, prefix=API)  # vertical Tributário — XML fiscal + recuperação de créditos
573:app.include_router(trabalhista_liquidacao.router, prefix=API)  # vertical Trabalhista — liquidação de sentença (ADC 58 / Selic real BCB)
574:app.include_router(ambiental_estrategia.router, prefix=API)  # vertical Ambiental — simulador de estratégia do auto de infração
575:app.include_router(tasks.router, prefix=API)
576:app.include_router(templates.router, prefix=API)
577:app.include_router(teses.router, prefix=API)
578:app.include_router(timesheet.router, prefix=API)
579:app.include_router(trash.router, prefix=API)
580:app.include_router(users.router, prefix=API)
581:app.include_router(utils.router, prefix=API)
582:app.include_router(validador_juridico.router, prefix=API)
583:app.include_router(visual_law.router, prefix=API)
584:app.include_router(whatsapp.router, prefix=API)
585:app.include_router(workflow.router, prefix=API)
586:app.include_router(architecture.router, prefix=API)
589:app.include_router(integracoes.datajud_router, prefix=API)
590:app.include_router(integracoes.djen_router, prefix=API)
591:app.include_router(integracoes.brasilapi_router, prefix=API)
```

> Todos os routers do EJC sao registrados manualmente em `backend/app/main.py`
> sob o prefixo `API = "/api"`. Router nao registrado la nao existe em runtime.

## 3. Chamadas de API no frontend

| Caminho chamado | Arquivo |
|---|---|
| `/api/${slug}` | `frontend/src/pages/ramos/FichaEspecializada.reset.test.tsx:47` |
| `/api/admin-esp` | `frontend/src/config/moduleRegistry.tsx:570` |
| `/api/agenda-eventos/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1304` |
| `/api/agenda-eventos/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1471` |
| `/api/agenda-eventos/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1534` |
| `/api/agenda-eventos/` | `frontend/src/components/ContextualAIAssistant.tsx:250` |
| `/api/agenda-eventos/` | `frontend/src/pages/AgendaDia.tsx:130` |
| `/api/agenda-eventos/` | `frontend/src/pages/CentralAtividades.tsx:1138` |
| `/api/agenda-eventos` | `frontend/src/config/moduleRegistry.tsx:590` |
| `/api/agenda-eventos` | `frontend/src/config/moduleRegistry.tsx:608` |
| `/api/ai/analisar-caso` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:609` |
| `/api/ai/analisar-caso` | `frontend/src/pages/IA.tsx:96` |
| `/api/ai/analisar-contrato` | `frontend/src/pages/CasoDetalhe/TabFerramentas.tsx:233` |
| `/api/ai/analisar-contrato` | `frontend/src/pages/CasoDetalhe/TabFerramentas.tsx:256` |
| `/api/ai/auditar-peca` | `frontend/src/pages/Pecas.tsx:535` |
| `/api/ai/core` | `frontend/src/config/moduleRegistry.tsx:703` |
| `/api/ai/dossie/${caseId}` | `frontend/src/pages/IA.tsx:81` |
| `/api/ai/gerar-minuta` | `frontend/src/pages/ramos/RamoAnalise.tsx:305` |
| `/api/ai/logs/${id}/hitl` | `frontend/src/components/OverrideCitacoesDialog.tsx:220` |
| `/api/ai/logs/${id}/hitl` | `frontend/src/pages/IA.tsx:169` |
| `/api/ai/logs/${result.ai_log_id}/feedback` | `frontend/src/components/ContextualAIAssistant.tsx:268` |
| `/api/ai/logs/${result.ai_log_id}/hitl` | `frontend/src/components/ContextualAIAssistant.tsx:204` |
| `/api/ai/logs` | `frontend/src/pages/IA.tsx:56` |
| `/api/ai/resumir-documento` | `frontend/src/pages/IA.tsx:117` |
| `/api/ai/skills` | `frontend/src/config/moduleRegistry.tsx:430` |
| `/api/ai/skills` | `frontend/src/config/moduleRegistry.tsx:704` |
| `/api/ai/skills` | `frontend/src/pages/InteligenciaWorkspace.contract.test.ts:97` |
| `/api/ai/sugestao-honorarios` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:589` |
| `/api/ai` | `frontend/src/config/moduleRegistry.tsx:412` |
| `/api/ai` | `frontend/src/config/moduleRegistry.tsx:702` |
| `/api/ai` | `frontend/src/pages/InteligenciaWorkspace.contract.test.ts:96` |
| `/api/ajuizamento/filings/${atual.id}/validar` | `frontend/src/pages/Ajuizamento.tsx:277` |
| `/api/ajuizamento/filings/${filing.id}/aprovar` | `frontend/src/pages/Ajuizamento.tsx:294` |
| `/api/ajuizamento/filings/${filing.id}/protocolar` | `frontend/src/pages/Ajuizamento.tsx:340` |
| `/api/ajuizamento/filings/${filing.id}/sincronizar` | `frontend/src/pages/Ajuizamento.tsx:378` |
| `/api/ajuizamento/filings/${filing.id}` | `frontend/src/pages/Ajuizamento.tsx:257` |
| `/api/ajuizamento/filings/${id}` | `frontend/src/pages/Ajuizamento.tsx:225` |
| `/api/ajuizamento/filings` | `frontend/src/pages/Ajuizamento.tsx:258` |
| `/api/ajuizamento/perfis/${p.id}` | `frontend/src/pages/AjuizamentoPerfis.tsx:103` |
| `/api/ajuizamento/perfis` | `frontend/src/config/moduleRegistry.tsx:502` |
| `/api/ajuizamento/perfis` | `frontend/src/pages/AjuizamentoPerfis.tsx:60` |
| `/api/ajuizamento/perfis` | `frontend/src/pages/AjuizamentoPerfis.tsx:80` |
| `/api/ajuizamento` | `frontend/src/config/moduleRegistry.tsx:486` |
| `/api/ambiental/estrategia/peca-conversao` | `frontend/src/components/AmbientalEstrategia.tsx:255` |
| `/api/analise-bancaria/abusividade` | `frontend/src/components/RevisaoBancariaDeterministica.tsx:69` |
| `/api/analise-bancaria/cet` | `frontend/src/components/RevisaoBancariaDeterministica.tsx:110` |
| `/api/analise-bancaria/taxa-media` | `frontend/src/pages/ramos/RamoAnalise.tsx:92` |
| `/api/analytics/funil` | `frontend/src/pages/CentralRelacionamento.tsx:124` |
| `/api/analytics/produtividade/export-event` | `frontend/src/pages/Produtividade.tsx:137` |
| `/api/analytics` | `frontend/src/config/moduleRegistry.tsx:591` |
| `/api/api/v1/casos/${id}` | `frontend/src/lib/api.prefixo.test.ts:153` |
| `/api/atendimentos/${followUp.id}` | `frontend/src/pages/DossieCliente.tsx:666` |
| `/api/atendimentos/${item.id}` | `frontend/src/components/ClientServiceTimeline.tsx:400` |
| `/api/atendimentos/${item.id}` | `frontend/src/components/ClientServiceTimeline.tsx:425` |
| `/api/atendimentos/responsaveis` | `frontend/src/pages/DossieCliente.tsx:1126` |
| `/api/atendimentos` | `frontend/src/components/ClientServiceTimeline.tsx:368` |
| `/api/atendimentos` | `frontend/src/pages/DossieCliente.tsx:1105` |
| `/api/atividades/resumo` | `frontend/src/pages/CentralAtividades.tsx:1106` |
| `/api/atividades` | `frontend/src/config/moduleRegistry.tsx:589` |
| `/api/atividades` | `frontend/src/config/moduleRegistry.tsx:608` |
| `/api/atividades` | `frontend/src/pages/AgendaDia.tsx:129` |
| `/api/atividades` | `frontend/src/pages/CentralAtividades.tsx:1105` |
| `/api/atividades` | `frontend/src/pages/CentralAtividades.tsx:1137` |
| `/api/atividades` | `frontend/src/pages/CentralAtividades.tsx:1248` |
| `/api/atividades` | `frontend/src/pages/DashboardUltra.tsx:265` |
| `/api/audit` | `frontend/src/config/moduleRegistry.tsx:906` |
| `/api/auth/alterar-senha` | `frontend/src/pages/TrocarSenha.tsx:33` |
| `/api/auth/logout` | `frontend/src/lib/api.ts:397` |
| `/api/auth/recuperar-senha` | `frontend/src/pages/RecuperarSenha.tsx:12` |
| `/api/auth/redefinir-senha` | `frontend/src/pages/RedefinirSenha.tsx:26` |
| `/api/auth/refresh` | `frontend/src/lib/api.prefixo.test.ts:173` |
| `/api/auth/refresh` | `frontend/src/lib/api.ts:60` |
| `/api/auth/totp/desativar` | `frontend/src/components/AccountSecurity.tsx:130` |
| `/api/auth/totp/verificar` | `frontend/src/components/AccountSecurity.tsx:109` |
| `/api/bank-analysis/${analiseSel}/gerar-peca` | `frontend/src/components/BancarioForense.tsx:564` |
| `/api/bank-analysis/${res.analise.id}/excel` | `frontend/src/components/AnaliseExtratos.tsx:94` |
| `/api/bank-analysis/${res.analise.id}/gerar-peca` | `frontend/src/components/AnaliseExtratos.tsx:162` |
| `/api/bank-analysis/upload` | `frontend/src/components/AnaliseExtratos.tsx:80` |
| `/api/bank-analysis/upload` | `frontend/src/pages/FinanceiroDashboard.tsx:419` |
| `/api/calendar/me/rotate` | `frontend/src/components/SecurityMenu.tsx:195` |
| `/api/calendar/me/url` | `frontend/src/components/SecurityMenu.tsx:179` |
| `/api/cases/${caseId}/analisar` | `frontend/src/components/AnaliseEstrategica.tsx:172` |
| `/api/cases/${caseId}/areas/${area.area}` | `frontend/src/components/CaseCommandDock.tsx:117` |
| `/api/cases/${caseId}/areas` | `frontend/src/components/CaseCommandDock.tsx:70` |
| `/api/cases/${caseId}/areas` | `frontend/src/components/CaseCommandDock.tsx:95` |
| `/api/cases/${caseId}/converter-judicial` | `frontend/src/components/ConversaoChecklist.tsx:89` |
| `/api/cases/${caseId}/documentos/${docId}/vincular` | `frontend/src/pages/CasoDetalhe/TabDocumentos.tsx:155` |
| `/api/cases/${caseId}/documentos/candidatos` | `frontend/src/pages/CasoDetalhe/TabDocumentos.tsx:129` |
| `/api/cases/${caseId}/etiquetas/${id}` | `frontend/src/pages/CasoDetalhe.tsx:506` |
| `/api/cases/${caseId}/etiquetas` | `frontend/src/pages/CasoDetalhe.tsx:497` |
| `/api/cases/${caseId}/etiquetas` | `frontend/src/pages/CasoDetalhe.tsx:518` |
| `/api/cases/${caseId}/indice-risco/recalcular` | `frontend/src/pages/CasoDetalhe/TabRisco.tsx:58` |
| `/api/cases/${caseId}/indice-risco` | `frontend/src/pages/CasoDetalhe/TabRisco.tsx:11` |
| `/api/cases/${caseId}/kanban` | `frontend/src/pages/Kanban.tsx:111` |
| `/api/cases/${caseId}/mensagens` | `frontend/src/pages/CasoDetalhe.tsx:404` |
| `/api/cases/${caseId}/motor-peca/analisar` | `frontend/src/components/DefesasRevisoesPanel.tsx:272` |
| `/api/cases/${caseId}/motor-peca/analisar` | `frontend/src/pages/EntradaUnica/DossieJuridico.tsx:165` |
| `/api/cases/${caseId}/motor-peca/gerar` | `frontend/src/pages/EntradaUnica/DossieJuridico.tsx:192` |
| `/api/cases/${caseId}/movimentos` | `frontend/src/pages/CasoDetalhe/TabTimeline.tsx:142` |
| `/api/cases/${caseId}/partes/${id}` | `frontend/src/pages/CasoDetalhe/TabPartes.tsx:53` |
| `/api/cases/${caseId}/partes` | `frontend/src/pages/CasoDetalhe/TabPartes.tsx:11` |
| `/api/cases/${caseId}/partes` | `frontend/src/pages/CasoDetalhe/TabPartes.tsx:41` |
| `/api/cases/${caseId}/processes` | `frontend/src/pages/CasoDetalhe/TabProcessos.tsx:85` |
| `/api/cases/${caseId}/score-juridico/calcular` | `frontend/src/pages/CasoDetalhe/TabScore.tsx:31` |
| `/api/cases/${caseId}/score-juridico` | `frontend/src/pages/CasoDetalhe/TabScore.tsx:12` |
| `/api/cases/${caseId}` | `frontend/src/pages/CasoDetalhe/CaseDocumentActions.tsx:86` |
| `/api/cases/${caso.id}/areas/${a}` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:185` |
| `/api/cases/${caso.id}/areas` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:178` |
| `/api/cases/${caso.id}/arquivar` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:374` |
| `/api/cases/${caso.id}/desarquivar` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:256` |
| `/api/cases/${caso.id}/desarquivar` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:386` |
| `/api/cases/${caso.id}/encerrar-simples` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:443` |
| `/api/cases/${caso.id}/encerrar` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:511` |
| `/api/cases/${caso.id}/financeiro/resumo` | `frontend/src/pages/CasoDetalhe/TabFinanceiroCaso.tsx:57` |
| `/api/cases/${caso.id}/gerar-documentos` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:575` |
| `/api/cases/${caso.id}/movimentos` | `frontend/src/components/ContextualAIAssistant.tsx:226` |
| `/api/cases/${caso.id}/movimentos` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:627` |
| `/api/cases/${caso.id}/reabrir` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:262` |
| `/api/cases/${caso.id}/sincronizar-processo` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:667` |
| `/api/cases/${caso.id}` | `frontend/src/pages/CasoDetalhe/TabFinanceiroCaso.tsx:85` |
| `/api/cases/${caso.id}` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:404` |
| `/api/cases/${caso.id}` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:645` |
| `/api/cases/${casoSelecionado}/movimentos` | `frontend/src/pages/ramos/RamoAnalise.tsx:284` |
| `/api/cases/${delCaso.id}` | `frontend/src/pages/Casos.tsx:340` |
| `/api/cases/${encodeURIComponent` | `frontend/src/pages/ramos/RamoBase.tsx:592` |
| `/api/cases/${encodeURIComponent` | `frontend/src/pages/ramos/RamoBase.tsx:593` |
| `/api/cases/${id}/desarquivar` | `frontend/src/pages/Casos.tsx:317` |
| `/api/cases/${id}/partes` | `frontend/src/lib/useCarregar.ts:56` |
| `/api/cases/${id}/partes` | `frontend/src/pages/Ajuizamento.tsx:194` |
| `/api/cases/${id}` | `frontend/src/pages/Ajuizamento.tsx:193` |
| `/api/cases/${id}` | `frontend/src/stores/caseContext.ts:88` |
| `/api/cases/${loteCaso}/documentos/${d.id}/vincular` | `frontend/src/pages/Documentos.tsx:589` |
| `/api/cases/` | `frontend/src/components/DefesasRevisoesPanel.tsx:163` |
| `/api/cases/` | `frontend/src/components/NovoCasoWizard.tsx:210` |
| `/api/cases/` | `frontend/src/components/__tests__/FlowEnhancements.test.ts:38` |
| `/api/cases/` | `frontend/src/pages/CadastroManual.tsx:602` |
| `/api/cases/` | `frontend/src/pages/Casos.tsx:270` |
| `/api/cases/` | `frontend/src/pages/Casos.tsx:487` |
| `/api/cases/` | `frontend/src/pages/DashboardUltra.tsx:266` |
| `/api/cases/` | `frontend/src/pages/Kanban.tsx:75` |
| `/api/cases/` | `frontend/src/pages/Pecas.tsx:391` |
| `/api/cases/` | `frontend/src/pages/SalaJuridica.tsx:862` |
| `/api/cases/` | `frontend/src/pages/ramos/RamoBase.tsx:628` |
| `/api/cases/stats` | `frontend/src/components/Dashboards.tsx:381` |
| `/api/cases` | `frontend/src/config/moduleRegistry.tsx:293` |
| `/api/cases` | `frontend/src/config/moduleRegistry.tsx:333` |
| `/api/cases` | `frontend/src/config/moduleRegistry.tsx:380` |
| `/api/cases` | `frontend/src/config/moduleRegistry.tsx:446` |
| `/api/cases` | `frontend/src/config/moduleRegistry.tsx:570` |
| `/api/casos/${caseId}/provas/${atual.id}` | `frontend/src/components/ProvasCaso.tsx:433` |
| `/api/casos/${caseId}/provas/${editId}` | `frontend/src/components/ProvasCaso.tsx:386` |
| `/api/casos/${caseId}/provas/${excluirId}` | `frontend/src/components/ProvasCaso.tsx:413` |
| `/api/casos/${caseId}/provas/${outro.id}` | `frontend/src/components/ProvasCaso.tsx:436` |
| `/api/casos/${caseId}/provas/documento-unico` | `frontend/src/components/ProvasCaso.tsx:452` |
| `/api/casos/${caseId}/provas` | `frontend/src/components/ProvasCaso.tsx:392` |
| `/api/casos/${caseId}/solicitacoes-documentos` | `frontend/src/pages/CasoDetalhe/CaseDocumentActions.tsx:129` |
| `/api/casos/${caseId}/solicitacoes-documentos` | `frontend/src/pages/CasoDetalhe/CaseDocumentActions.tsx:88` |
| `/api/casos` | `frontend/src/lib/api.prefixo.test.ts:5` |
| `/api/checklists/${ckId}/itens/${itemId}/marcar` | `frontend/src/pages/CasoDetalhe.tsx:218` |
| `/api/checklists/caso/${caseId}/gerar-ia` | `frontend/src/pages/CasoDetalhe.tsx:206` |
| `/api/checklists/templates/${id}` | `frontend/src/pages/Checklists.tsx:70` |
| `/api/checklists/templates` | `frontend/src/pages/Checklists.tsx:51` |
| `/api/checklists` | `frontend/src/config/moduleRegistry.tsx:681` |
| `/api/clients/${alvo.id}/gerar-documentos` | `frontend/src/pages/Clientes.tsx:249` |
| `/api/clients/${clientId}/criar-acesso` | `frontend/src/pages/DossieCliente.tsx:1176` |
| `/api/clients/${clientId}/pending-items/${id}` | `frontend/src/pages/DossieCliente.tsx:341` |
| `/api/clients/${clientId}/pending-items/${pendenteExcluir}` | `frontend/src/pages/DossieCliente.tsx:359` |
| `/api/clients/${clientId}/pending-items` | `frontend/src/pages/DossieCliente.tsx:284` |
| `/api/clients/${clientId}/pending-items` | `frontend/src/pages/DossieCliente.tsx:316` |
| `/api/clients/${clientId}/relatorio-financeiro` | `frontend/src/pages/DossieCliente.tsx:801` |
| `/api/clients/${clientId}` | `frontend/src/pages/DossieCliente.tsx:1058` |
| `/api/clients/${clientId}` | `frontend/src/pages/DossieCliente.tsx:1125` |
| `/api/clients/${leadId}` | `frontend/src/pages/CRMLeads.tsx:157` |
| `/api/clients/1` | `frontend/src/lib/api.prefixo.test.ts:154` |
| `/api/clients/` | `frontend/src/components/NovoCasoWizard.tsx:122` |
| `/api/clients/` | `frontend/src/components/NovoCasoWizard.tsx:164` |
| `/api/clients/` | `frontend/src/pages/CRMLeads.tsx:111` |
| `/api/clients/` | `frontend/src/pages/CRMLeads.tsx:128` |
| `/api/clients/` | `frontend/src/pages/CadastroManual.tsx:490` |
| `/api/clients/` | `frontend/src/pages/CadastroManual.tsx:588` |
| `/api/clients/` | `frontend/src/pages/CentralRelacionamento.tsx:125` |
| `/api/clients/` | `frontend/src/pages/CentralRelacionamento.tsx:126` |
| `/api/clients/` | `frontend/src/pages/SalaJuridica.tsx:733` |
| `/api/clients/resolver` | `frontend/src/pages/Casos.tsx:474` |
| `/api/clients/{client_id}/dossie` | `frontend/src/config/moduleRegistry.tsx:362` |
| `/api/clients` | `frontend/src/config/moduleRegistry.tsx:293` |
| `/api/clients` | `frontend/src/config/moduleRegistry.tsx:314` |
| `/api/clients` | `frontend/src/config/moduleRegistry.tsx:333` |
| `/api/clients` | `frontend/src/config/moduleRegistry.tsx:346` |
| `/api/clients` | `frontend/src/config/moduleRegistry.tsx:362` |
| `/api/clients` | `frontend/src/config/moduleRegistry.tsx:380` |
| `/api/clients` | `frontend/src/config/moduleRegistry.tsx:592` |
| `/api/compliance/radar` | `frontend/src/config/moduleRegistry.tsx:787` |
| `/api/conhecimento/importar-jurisprudencia` | `frontend/src/pages/Conhecimento.tsx:611` |
| `/api/conhecimento` | `frontend/src/config/moduleRegistry.tsx:707` |
| `/api/conhecimento` | `frontend/src/pages/InteligenciaWorkspace.contract.test.ts:100` |
| `/api/dashboard/` | `frontend/src/components/Dashboards.tsx:381` |
| `/api/dashboard/` | `frontend/src/pages/DashboardUltra.tsx:264` |
| `/api/dashboard/hoje` | `frontend/src/pages/DashboardUltra.tsx:278` |
| `/api/dashboard` | `frontend/src/config/moduleRegistry.tsx:267` |
| `/api/data-rooms/${aberta.id}/arquivos` | `frontend/src/pages/DataRoom.tsx:104` |
| `/api/data-rooms/${aberta.id}/links` | `frontend/src/pages/DataRoom.tsx:122` |
| `/api/data-rooms/${id}` | `frontend/src/pages/DataRoom.tsx:88` |
| `/api/data-rooms/acesso/` | `frontend/src/pages/DataRoom.tsx:126` |
| `/api/data-rooms` | `frontend/src/config/moduleRegistry.tsx:624` |
| `/api/data-rooms` | `frontend/src/pages/DataRoom.tsx:80` |
| `/api/datajud/cases/${idCaso}/sync` | `frontend/src/pages/DataJudBusca.tsx:95` |
| `/api/datajud/process/${encodeURIComponent` | `frontend/src/pages/DataJudBusca.tsx:77` |
| `/api/datajud` | `frontend/src/config/moduleRegistry.tsx:754` |
| `/api/deadlines/${item.id}/ciencia` | `frontend/src/pages/CentralAtividades.tsx:1326` |
| `/api/deadlines/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1300` |
| `/api/deadlines/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1467` |
| `/api/deadlines/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1497` |
| `/api/deadlines/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1530` |
| `/api/deadlines/` | `frontend/src/components/CommandPalette.tsx:634` |
| `/api/deadlines/` | `frontend/src/pages/CentralAtividades.tsx:1139` |
| `/api/deadlines/` | `frontend/src/pages/CentralAtividades.tsx:1172` |
| `/api/deadlines/calcular` | `frontend/src/pages/CentralAtividades/acoesLegadas.contract.test.ts:18` |
| `/api/deadlines/calcular` | `frontend/src/pages/CentralAtividades/acoesLegadas.tsx:425` |
| `/api/deadlines/export.csv` | `frontend/src/pages/CentralAtividades.tsx:1422` |
| `/api/deadlines` | `frontend/src/config/moduleRegistry.tsx:293` |
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
| `/api/despesas-processuais/` | `frontend/src/pages/CasoDetalhe/TabTimeline.tsx:199` |
| `/api/despesas/${editId}` | `frontend/src/pages/Despesas.tsx:224` |
| `/api/despesas/${id}` | `frontend/src/pages/Despesas.tsx:242` |
| `/api/despesas/${pendenteExcluir}` | `frontend/src/pages/Despesas.tsx:266` |
| `/api/despesas/export/csv` | `frontend/src/pages/Despesas.tsx:109` |
| `/api/despesas/recorrentes/gerar` | `frontend/src/pages/DespesasRecorrentes.tsx:61` |
| `/api/despesas` | `frontend/src/config/moduleRegistry.tsx:807` |
| `/api/despesas` | `frontend/src/lib/api.prefixo.test.ts:170` |
| `/api/despesas` | `frontend/src/pages/Despesas.tsx:134` |
| `/api/despesas` | `frontend/src/pages/Despesas.tsx:225` |
| `/api/despesas` | `frontend/src/pages/DespesasRecorrentes.tsx:36` |
| `/api/diagnostico` | `frontend/src/config/moduleRegistry.tsx:892` |
| `/api/diagnostico` | `frontend/src/lib/api.prefixo.test.ts:172` |
| `/api/diario-oficial/alertas/${id}/marcar-lido` | `frontend/src/pages/DiarioOficial.tsx:108` |
| `/api/diario-oficial/alertas/nao-lidos/count` | `frontend/src/pages/DiarioOficial.tsx:51` |
| `/api/diario-oficial/alertas` | `frontend/src/pages/DiarioOficial.tsx:72` |
| `/api/diario-oficial/keywords/${id}` | `frontend/src/pages/DiarioOficial.tsx:138` |
| `/api/diario-oficial/keywords` | `frontend/src/pages/DiarioOficial.tsx:127` |
| `/api/diario-oficial/keywords` | `frontend/src/pages/DiarioOficial.tsx:86` |
| `/api/diario-oficial` | `frontend/src/config/moduleRegistry.tsx:768` |
| `/api/documents/${d.id}/download` | `frontend/src/pages/Documentos.tsx:360` |
| `/api/documents/${d.id}/download` | `frontend/src/pages/Documentos.tsx:388` |
| `/api/documents/${d.id}` | `frontend/src/pages/Documentos.tsx:458` |
| `/api/documents/${d.id}` | `frontend/src/pages/Documentos.tsx:481` |
| `/api/documents/${d.id}` | `frontend/src/pages/Documentos.tsx:560` |
| `/api/documents/${docId}/download` | `frontend/src/pages/CasoDetalhe/TabDocumentos.tsx:22` |
| `/api/documents/${docId}/download` | `frontend/src/pages/DossieCliente.tsx:1081` |
| `/api/documents/${editDoc.id}` | `frontend/src/pages/Documentos.tsx:541` |
| `/api/documents/` | `frontend/src/components/CaseIntegrityIndicator.tsx:48` |
| `/api/documents/` | `frontend/src/components/Dashboards.tsx:535` |
| `/api/documents/` | `frontend/src/components/ProvasCaso.tsx:241` |
| `/api/documents/` | `frontend/src/pages/DashboardUltra.tsx:267` |
| `/api/documents/upload` | `frontend/src/components/CaseCommandDock.tsx:143` |
| `/api/documents/upload` | `frontend/src/pages/CasoDetalhe/TabDocumentos.tsx:187` |
| `/api/documents/upload` | `frontend/src/pages/Comissoes.tsx:324` |
| `/api/documents/upload` | `frontend/src/pages/Documentos.tsx:329` |
| `/api/documents/upload` | `frontend/src/pages/casos/casosIntake.ts:46` |
| `/api/documents` | `frontend/src/config/moduleRegistry.tsx:624` |
| `/api/dossie/${caseId}/${dossie.id}/aprovar` | `frontend/src/components/DossieEstrategicoCaso.tsx:288` |
| `/api/dossie/${caseId}/${dossie.id}/pdf` | `frontend/src/components/DossieEstrategicoCaso.tsx:305` |
| `/api/dossie/${caseId}/gerar` | `frontend/src/components/DossieEstrategicoCaso.tsx:270` |
| `/api/empresarial/sociedades/${detalhe.id}/eventos` | `frontend/src/components/SociedadesCliente.tsx:315` |
| `/api/empresarial/sociedades/${detalhe.id}/socios` | `frontend/src/components/SociedadesCliente.tsx:276` |
| `/api/empresarial/sociedades/socios/${pendenteExcluir}` | `frontend/src/components/SociedadesCliente.tsx:294` |
| `/api/empresarial/sociedades` | `frontend/src/components/SociedadesCliente.tsx:242` |
| `/api/entrada-universal` | `frontend/src/config/moduleRegistry.tsx:314` |
| `/api/entrada/${proposta.rascunhoId}/vincular-processo` | `frontend/src/pages/EntradaUnica/Confirmacao.tsx:192` |
| `/api/entrada/analisar` | `frontend/src/pages/EntradaUnica.tsx:207` |
| `/api/entrada/analisar` | `frontend/src/pages/EntradaUnica/DossieJuridico.tsx:117` |
| `/api/entrada` | `frontend/src/config/moduleRegistry.tsx:314` |
| `/api/environmental/` | `frontend/src/components/AmbientalAutos.tsx:99` |
| `/api/etiquetas` | `frontend/src/pages/CasoDetalhe.tsx:516` |
| `/api/extratos/detalhado/${caso.id}` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:85` |
| `/api/fees/${editFeeId}` | `frontend/src/pages/Honorarios.tsx:208` |
| `/api/fees/${fee.id}/pagamentos` | `frontend/src/pages/Honorarios.tsx:253` |
| `/api/fees/${fee.id}/pagamentos` | `frontend/src/pages/Honorarios.tsx:264` |
| `/api/fees/${fee.id}/pagamentos` | `frontend/src/pages/Honorarios.tsx:337` |
| `/api/fees/${fee.id}/pagamentos` | `frontend/src/pages/Honorarios.tsx:372` |
| `/api/fees/${pagModal.id}/pagamentos` | `frontend/src/pages/Honorarios.tsx:278` |
| `/api/fees/` | `frontend/src/components/CaseIntegrityIndicator.tsx:47` |
| `/api/fees/` | `frontend/src/pages/CasoDetalhe/TabFinanceiroCaso.tsx:58` |
| `/api/fees/` | `frontend/src/pages/Honorarios.tsx:195` |
| `/api/fees` | `frontend/src/config/moduleRegistry.tsx:806` |
| `/api/financeiro/aprovacoes/${id}/aprovar` | `frontend/src/pages/FinanceiroDashboard.tsx:405` |
| `/api/financeiro/aprovacoes` | `frontend/src/pages/FinanceiroDashboard.tsx:227` |
| `/api/financeiro/atencao` | `frontend/src/pages/DashboardUltra.tsx:276` |
| `/api/financeiro/atencao` | `frontend/src/pages/FinanceiroDashboard.tsx:219` |
| `/api/financeiro/comissoes/${ajusteRow.id}/ajustes` | `frontend/src/pages/Comissoes.tsx:374` |
| `/api/financeiro/comissoes/${row.id}/enviar-aprovacao` | `frontend/src/pages/Comissoes.tsx:282` |
| `/api/financeiro/comissoes/extrato-mensal` | `frontend/src/pages/Comissoes.tsx:401` |
| `/api/financeiro/comissoes/fechamentos` | `frontend/src/pages/Comissoes.tsx:416` |
| `/api/financeiro/comissoes/lotes-pagamento` | `frontend/src/pages/Comissoes.tsx:334` |
| `/api/financeiro/comissoes/opcoes` | `frontend/src/pages/Comissoes.tsx:222` |
| `/api/financeiro/comissoes/regras/${editRuleId}` | `frontend/src/pages/Comissoes.tsx:469` |
| `/api/financeiro/comissoes/regras/${rule.id}` | `frontend/src/pages/Comissoes.tsx:500` |
| `/api/financeiro/comissoes/regras` | `frontend/src/pages/Comissoes.tsx:221` |
| `/api/financeiro/comissoes/regras` | `frontend/src/pages/Comissoes.tsx:475` |
| `/api/financeiro/conciliacao/${analysisId}` | `frontend/src/pages/FinanceiroDashboard.tsx:422` |
| `/api/financeiro/conciliacao/${analysisId}` | `frontend/src/pages/FinanceiroDashboard.tsx:441` |
| `/api/financeiro/conciliacao/confirmar` | `frontend/src/pages/FinanceiroDashboard.tsx:434` |
| `/api/financeiro/consolidado` | `frontend/src/pages/FinanceiroDashboard.tsx:218` |
| `/api/financeiro/distribuicao-disponivel` | `frontend/src/pages/FinanceiroDashboard.tsx:223` |
| `/api/financeiro/excecoes` | `frontend/src/pages/FinanceiroDashboard.tsx:221` |
| `/api/financeiro/fechamento-inteligente` | `frontend/src/pages/FinanceiroDashboard.tsx:335` |
| `/api/financeiro/fechamentos/${competencia}` | `frontend/src/pages/FinanceiroDashboard.tsx:222` |
| `/api/financeiro/fechamentos` | `frontend/src/pages/FinanceiroDashboard.tsx:367` |
| `/api/financeiro/politica` | `frontend/src/pages/FinanceiroDashboard.tsx:226` |
| `/api/financeiro/politica` | `frontend/src/pages/FinanceiroDashboard.tsx:392` |
| `/api/financeiro/rentabilidade` | `frontend/src/pages/FinanceiroDashboard.tsx:220` |
| `/api/financeiro` | `frontend/src/config/moduleRegistry.tsx:805` |
| `/api/health` | `frontend/src/config/moduleRegistry.tsx:267` |
| `/api/honorarios-oab/${fee.id}/rateio` | `frontend/src/pages/Honorarios.tsx:226` |
| `/api/honorarios-oab/${rateioModal.fee.id}/rateio` | `frontend/src/pages/Honorarios.tsx:239` |
| `/api/honorarios-oab/estimar` | `frontend/src/components/EstimadorHonorarios.tsx:54` |
| `/api/honorarios-oab` | `frontend/src/config/moduleRegistry.tsx:708` |
| `/api/honorarios-oab` | `frontend/src/pages/InteligenciaWorkspace.contract.test.ts:101` |
| `/api/ia-defensiva/analisar` | `frontend/src/pages/CasoDetalhe/IaDefensivaCaso.tsx:98` |
| `/api/ia-defensiva/historico/${caso.id}` | `frontend/src/pages/CasoDetalhe/IaDefensivaCaso.tsx:48` |
| `/api/ia-defensiva/historico/${logId}/status` | `frontend/src/pages/CasoDetalhe/IaDefensivaCaso.tsx:67` |
| `/api/ia-governanca/dashboard` | `frontend/src/pages/GovernancaIA.tsx:104` |
| `/api/ia-governanca/fontes` | `frontend/src/pages/GovernancaIA.tsx:111` |
| `/api/ia-governanca/guardrails` | `frontend/src/pages/GovernancaIA.tsx:112` |
| `/api/ia-governanca/jurisprudencia-mg/geometria` | `frontend/src/pages/GovernancaIA.tsx:114` |
| `/api/ia-governanca/jurisprudencia-mg` | `frontend/src/pages/GovernancaIA.tsx:113` |
| `/api/ia-governanca/jurisprudencia-mg` | `frontend/src/pages/GovernancaIA.tsx:183` |
| `/api/ia-governanca/prompts` | `frontend/src/pages/GovernancaIA.tsx:110` |
| `/api/ia-governanca/provedores` | `frontend/src/pages/PainelProvedoresIA.tsx:205` |
| `/api/ia-governanca/rag-curadoria` | `frontend/src/pages/GovernancaIA.tsx:106` |
| `/api/ia-governanca` | `frontend/src/config/moduleRegistry.tsx:710` |
| `/api/ia-governanca` | `frontend/src/config/moduleRegistry.tsx:874` |
| `/api/ia-governanca` | `frontend/src/pages/InteligenciaWorkspace.contract.test.ts:103` |
| `/api/ia-saude/dashboard` | `frontend/src/pages/DashboardIA.tsx:12` |
| `/api/ia-saude` | `frontend/src/config/moduleRegistry.tsx:709` |
| `/api/ia-saude` | `frontend/src/pages/InteligenciaWorkspace.contract.test.ts:102` |
| `/api/ia/agente/stream` | `frontend/src/lib/api.prefixo.test.ts:171` |
| `/api/ia/agente/stream` | `frontend/src/pages/AgenteIA.tsx:150` |
| `/api/ia/analisar` | `frontend/src/pages/AssistenteIA.tsx:185` |
| `/api/ia/conversar` | `frontend/src/pages/AssistenteIA.tsx:172` |
| `/api/ia/conversar` | `frontend/src/pages/AssistenteIA.tsx:180` |
| `/api/ia/redigir` | `frontend/src/pages/AssistenteIA.tsx:191` |
| `/api/ia/resumir` | `frontend/src/pages/AssistenteIA.tsx:178` |
| `/api/ia` | `frontend/src/config/moduleRegistry.tsx:701` |
| `/api/ia` | `frontend/src/pages/InteligenciaWorkspace.contract.test.ts:95` |
| `/api/integracoes/` | `frontend/src/lib/tributarioFontesOficiais.ts:28` |
| `/api/intimacoes/${item.id}/prazo-sugerido` | `frontend/src/pages/CentralAtividades.tsx:1355` |
| `/api/intimacoes/${item.id}/processar` | `frontend/src/pages/CentralAtividades.tsx:1306` |
| `/api/intimacoes/${item.id}/processar` | `frontend/src/pages/CentralAtividades.tsx:1539` |
| `/api/intimacoes/` | `frontend/src/pages/CasoDetalhe/TabIntimacoes.tsx:56` |
| `/api/intimacoes/capturar-agora` | `frontend/src/pages/CentralAtividades.tsx:1370` |
| `/api/jurimetria/cobertura-mg-jec` | `frontend/src/pages/Jurimetria.tsx:178` |
| `/api/jurimetria/cobertura-rag` | `frontend/src/pages/Jurimetria.tsx:177` |
| `/api/jurimetria/overview` | `frontend/src/pages/InteligenciaWorkspace.contract.test.ts:73` |
| `/api/jurimetria/overview` | `frontend/src/pages/Jurimetria.tsx:134` |
| `/api/jurimetria/por-area` | `frontend/src/pages/InteligenciaWorkspace.contract.test.ts:74` |
| `/api/jurimetria/por-area` | `frontend/src/pages/Jurimetria.tsx:136` |
| `/api/jurimetria/por-tese` | `frontend/src/pages/InteligenciaWorkspace.contract.test.ts:76` |
| `/api/jurimetria/por-tese` | `frontend/src/pages/Jurimetria.tsx:138` |
| `/api/jurimetria/por-tribunal` | `frontend/src/pages/InteligenciaWorkspace.contract.test.ts:75` |
| `/api/jurimetria/por-tribunal` | `frontend/src/pages/Jurimetria.tsx:137` |
| `/api/jurimetria` | `frontend/src/config/moduleRegistry.tsx:705` |
| `/api/jurimetria` | `frontend/src/pages/InteligenciaWorkspace.contract.test.ts:98` |
| `/api/kanban/columns` | `frontend/src/pages/Kanban.tsx:70` |
| `/api/legal-docs/${doc.id}/exportar-docx` | `frontend/src/pages/Pecas.tsx:438` |
| `/api/legal-docs/${doc.id}/pdf-minuta` | `frontend/src/pages/Pecas.tsx:422` |
| `/api/legal-docs/${doc.id}/pdf` | `frontend/src/pages/Pecas.tsx:421` |
| `/api/legal-docs/${doc.id}` | `frontend/src/pages/Pecas.tsx:327` |
| `/api/legal-docs/${doc.id}` | `frontend/src/pages/Pecas.tsx:342` |
| `/api/legal-docs/${doc.id}` | `frontend/src/pages/Pecas.tsx:477` |
| `/api/legal-docs/${id}` | `frontend/src/pages/Pecas.tsx:178` |
| `/api/legal-docs/${peca.id}/pdf-minuta` | `frontend/src/pages/Clientes.tsx:265` |
| `/api/legal-docs/${protocolo.doc.id}/protocolo` | `frontend/src/pages/Pecas.tsx:370` |
| `/api/legal-docs/${protocolo.doc.id}` | `frontend/src/pages/Pecas.tsx:371` |
| `/api/legal-docs/${revisao.doc.id}/conferir-e-assinar` | `frontend/src/pages/Pecas.tsx:284` |
| `/api/legal-docs/${revisao.doc.id}/revisar` | `frontend/src/pages/Pecas.tsx:243` |
| `/api/legal-docs/${view.id}` | `frontend/src/pages/Pecas.tsx:214` |
| `/api/legal-docs/${view.id}` | `frontend/src/pages/Pecas.workspace.contract.test.ts:25` |
| `/api/legal-docs/` | `frontend/src/pages/DashboardUltra.tsx:274` |
| `/api/legal-docs/` | `frontend/src/pages/Pecas.tsx:161` |
| `/api/legal-docs` | `frontend/src/config/moduleRegistry.tsx:641` |
| `/api/lgpd/registros/${clientId}/ripd` | `frontend/src/components/LgpdRegistros.tsx:290` |
| `/api/lgpd/registros/${editId}` | `frontend/src/components/LgpdRegistros.tsx:250` |
| `/api/lgpd/registros/${r.id}` | `frontend/src/components/LgpdRegistros.tsx:275` |
| `/api/lgpd/registros` | `frontend/src/components/LgpdRegistros.tsx:253` |
| `/api/manus/deep-reasoning` | `frontend/src/pages/AssistenteIA.tsx:163` |
| `/api/memoria-institucional/${id}` | `frontend/src/pages/CasoDetalhe/TabMemoria.tsx:66` |
| `/api/memoria-institucional` | `frontend/src/pages/CasoDetalhe/TabMemoria.tsx:48` |
| `/api/nfse/${n.id}/${kind}` | `frontend/src/pages/NotasFiscais.tsx:217` |
| `/api/nfse/manual/${cancelNota.id}/cancelar` | `frontend/src/pages/NotasFiscais.tsx:241` |
| `/api/nfse/manual` | `frontend/src/pages/NotasFiscais.tsx:200` |
| `/api/nfse` | `frontend/src/config/moduleRegistry.tsx:808` |
| `/api/notifications/push/subscribe` | `frontend/src/components/NotificationPreferences.tsx:257` |
| `/api/notifications/push/subscribe` | `frontend/src/components/SecurityMenu.tsx:134` |
| `/api/notifications/push/subscriptions/${deviceId}` | `frontend/src/components/NotificationPreferences.tsx:277` |
| `/api/notifications/push/vapid-key` | `frontend/src/components/NotificationPreferences.tsx:234` |
| `/api/notifications/push/vapid-key` | `frontend/src/components/SecurityMenu.tsx:121` |
| `/api/notifications` | `frontend/src/config/moduleRegistry.tsx:593` |
| `/api/observabilidade/frontend-error` | `frontend/src/components/ErrorBoundary.tsx:49` |
| `/api/office-contracts/${editing.id}` | `frontend/src/pages/OfficeContracts.tsx:163` |
| `/api/office-contracts/${pendenteExcluir}` | `frontend/src/pages/OfficeContracts.tsx:183` |
| `/api/office-contracts/expiring` | `frontend/src/pages/OfficeContracts.tsx:102` |
| `/api/office-contracts` | `frontend/src/pages/OfficeContracts.tsx:165` |
| `/api/office-contracts` | `frontend/src/pages/OfficeContracts.tsx:99` |
| `/api/ok` | `frontend/src/lib/api.test.ts:79` |
| `/api/partner-withdrawals/${id}/${action}` | `frontend/src/pages/Sociedade.tsx:229` |
| `/api/partner-withdrawals/${row.withdrawal_id}/approve` | `frontend/src/pages/Comissoes.tsx:285` |
| `/api/partner-withdrawals` | `frontend/src/config/moduleRegistry.tsx:830` |
| `/api/partner-withdrawals` | `frontend/src/pages/Sociedade.tsx:126` |
| `/api/partner-withdrawals` | `frontend/src/pages/Sociedade.tsx:203` |
| `/api/pecas/demonstrativo` | `frontend/src/pages/ramos/RamoFerramenta.tsx:282` |
| `/api/pecas/gerar` | `frontend/src/components/CaseCommandDock.pecas.contract.test.ts:18` |
| `/api/pecas/gerar` | `frontend/src/components/PecaGeneratorModal.tsx:348` |
| `/api/pix/cobranca` | `frontend/src/pages/Honorarios.tsx:384` |
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
| `/api/processes/${arqPid}/arquivar` | `frontend/src/pages/CasoDetalhe/TabProcessos.tsx:115` |
| `/api/processes/${pid}/desarquivar` | `frontend/src/pages/CasoDetalhe/TabProcessos.tsx:130` |
| `/api/processes/${pid}/proveniencia` | `frontend/src/pages/CasoDetalhe/TabProcessos.tsx:147` |
| `/api/processes/${pid}` | `frontend/src/pages/CasoDetalhe/TabProcessos.tsx:101` |
| `/api/processes` | `frontend/src/config/moduleRegistry.tsx:446` |
| `/api/procuracoes/` | `frontend/src/components/CaseIntegrityIndicator.tsx:45` |
| `/api/prompts-juridicos/${id}` | `frontend/src/pages/Prompts.tsx:85` |
| `/api/prompts-juridicos` | `frontend/src/pages/Prompts.tsx:33` |
| `/api/prompts-juridicos` | `frontend/src/pages/Prompts.tsx:62` |
| `/api/protegido` | `frontend/src/lib/api.test.ts:50` |
| `/api/protegido` | `frontend/src/lib/api.test.ts:62` |
| `/api/qualquer-endpoint` | `frontend/src/lib/api.test.ts:35` |
| `/api/rag/buscar` | `frontend/src/pages/CasoDetalhe/TabIndicadoresJuridicos.tsx:51` |
| `/api/rag/docs/${id}` | `frontend/src/pages/Conhecimento.tsx:826` |
| `/api/rag/docs` | `frontend/src/components/KnowledgeGovernancePanel.tsx:259` |
| `/api/rag/governanca/cobertura` | `frontend/src/components/KnowledgeGovernancePanel.tsx:258` |
| `/api/rag/governanca/docs/${args.docId}/revisar` | `frontend/src/components/RevisaoConhecimentoDialog.tsx:93` |
| `/api/rag/governanca/saude` | `frontend/src/components/KnowledgeGovernancePanel.tsx:257` |
| `/api/rag/governanca/testes-juridicos` | `frontend/src/components/KnowledgeGovernancePanel.tsx:402` |
| `/api/rag/ingest-pdf` | `frontend/src/pages/Conhecimento.tsx:370` |
| `/api/rag/ingest-url` | `frontend/src/pages/Conhecimento.tsx:385` |
| `/api/rag/ingest` | `frontend/src/pages/Conhecimento.tsx:170` |
| `/api/rag` | `frontend/src/config/moduleRegistry.tsx:706` |
| `/api/rag` | `frontend/src/pages/InteligenciaWorkspace.contract.test.ts:99` |
| `/api/raio-x/${selected.id}/${mode}` | `frontend/src/pages/RaioXProcesso.tsx:910` |
| `/api/raio-x/${selected.id}/converter` | `frontend/src/pages/RaioXProcesso.tsx:874` |
| `/api/raio-x/${selected.id}/exportar` | `frontend/src/pages/RaioXProcesso.tsx:652` |
| `/api/raio-x/` | `frontend/src/pages/RaioXProcesso.tsx:384` |
| `/api/raio-x/stats` | `frontend/src/pages/RaioXProcesso.tsx:385` |
| `/api/raio-x` | `frontend/src/config/moduleRegistry.tsx:430` |
| `/api/regulatorio` | `frontend/src/config/moduleRegistry.tsx:787` |
| `/api/relatorio/mensal` | `frontend/src/pages/FinanceiroDashboard.tsx:306` |
| `/api/sala-juridica/${ativa.id}/converter` | `frontend/src/pages/SalaJuridica.tsx:748` |
| `/api/sala-juridica/${ativa.id}/exportar` | `frontend/src/pages/SalaJuridica.tsx:813` |
| `/api/sala-juridica/${ativa.id}/saida` | `frontend/src/pages/SalaJuridica.tsx:629` |
| `/api/sala-juridica/${s.id}` | `frontend/src/pages/SalaJuridica.tsx:619` |
| `/api/sala-juridica/${sessao.id}` | `frontend/src/pages/SalaJuridica.tsx:531` |
| `/api/sala-juridica/${sessaoId}/mensagens` | `frontend/src/pages/SalaJuridica.tsx:577` |
| `/api/sala-juridica/${sessaoId}` | `frontend/src/pages/SalaJuridica.tsx:509` |
| `/api/sala-juridica` | `frontend/src/config/moduleRegistry.tsx:412` |
| `/api/saneamento/divergencias/${item.id}/aplicar` | `frontend/src/pages/RadarIntegridade.tsx:99` |
| `/api/saneamento/divergencias` | `frontend/src/pages/RadarIntegridade.tsx:64` |
| `/api/saneamento/integridade` | `frontend/src/pages/DashboardUltra.tsx:272` |
| `/api/saneamento/integridade` | `frontend/src/pages/RadarIntegridade.tsx:63` |
| `/api/signatures/${id}/assinar` | `frontend/src/pages/Assinaturas.tsx:168` |
| `/api/signatures/${s.id}/assinar` | `frontend/src/pages/portal/PortalAssinaturas.tsx:231` |
| `/api/signatures/${s.id}/documento` | `frontend/src/pages/portal/PortalAssinaturas.tsx:146` |
| `/api/signatures/` | `frontend/src/pages/Assinaturas.tsx:146` |
| `/api/signatures/` | `frontend/src/pages/Assinaturas.tsx:87` |
| `/api/signatures/` | `frontend/src/pages/CasoDetalhe/CaseDocumentActions.tsx:168` |
| `/api/signatures/` | `frontend/src/pages/portal/PortalDashboard.tsx:58` |
| `/api/signatures` | `frontend/src/config/moduleRegistry.tsx:654` |
| `/api/sociedade/distribuicao` | `frontend/src/pages/Sociedade.tsx:124` |
| `/api/sociedade/distribuicao` | `frontend/src/pages/Sociedade.tsx:179` |
| `/api/sociedade/socios` | `frontend/src/pages/Sociedade.tsx:123` |
| `/api/sociedade/socios` | `frontend/src/pages/Sociedade.tsx:157` |
| `/api/sociedade` | `frontend/src/config/moduleRegistry.tsx:830` |
| `/api/suspensoes/${excluirSuspensao.id}` | `frontend/src/pages/CentralAtividades.tsx:1389` |
| `/api/suspensoes/` | `frontend/src/pages/CentralAtividades/acoesLegadas.tsx:272` |
| `/api/suspensoes/simular` | `frontend/src/pages/CentralAtividades/acoesLegadas.contract.test.ts:19` |
| `/api/system-modules/settings/${selectedKey}` | `frontend/src/components/ModuleLifecycleSettings.tsx:177` |
| `/api/system-modules` | `frontend/src/config/moduleRegistry.tsx:920` |
| `/api/tasks/${excluir.id}` | `frontend/src/pages/CentralAtividades.tsx:1404` |
| `/api/tasks/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1302` |
| `/api/tasks/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1469` |
| `/api/tasks/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1501` |
| `/api/tasks/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1525` |
| `/api/tasks/` | `frontend/src/pages/DashboardUltra.tsx:270` |
| `/api/templates/${tplSel}/gerar` | `frontend/src/pages/Pecas.tsx:408` |
| `/api/templates/` | `frontend/src/pages/Pecas.tsx:390` |
| `/api/templates` | `frontend/src/config/moduleRegistry.tsx:641` |
| `/api/teses/motor/async/${task_id}` | `frontend/src/components/MotorTeses.tsx:105` |
| `/api/teses` | `frontend/src/config/moduleRegistry.tsx:725` |
| `/api/teste/stream` | `frontend/src/lib/stream.test.ts:36` |
| `/api/timesheet/` | `frontend/src/pages/CasoDetalhe/TabTimeline.tsx:168` |
| `/api/trabalhista/liquidacao/planilha-pdf` | `frontend/src/components/LiquidacaoTrabalhista.tsx:320` |
| `/api/trash/${ent}/${id}/restaurar` | `frontend/src/pages/Lixeira.tsx:70` |
| `/api/trash` | `frontend/src/config/moduleRegistry.tsx:951` |
| `/api/triagem/ficha/pre-preencher` | `frontend/src/components/FichaTriagem.tsx:196` |
| `/api/triagem/ficha` | `frontend/src/components/FichaTriagem.tsx:217` |
| `/api/triagem` | `frontend/src/config/moduleRegistry.tsx:518` |
| `/api/tributario/fiscal/relatorio-pdf` | `frontend/src/components/TributarioFiscal.tsx:231` |
| `/api/tributario/fiscal` | `frontend/src/config/moduleRegistry.tsx:570` |
| `/api/tributario/fiscal` | `frontend/src/config/tributarioWorkspace.test.ts:35` |
| `/api/users/${editando.id}` | `frontend/src/pages/Usuarios.tsx:148` |
| `/api/users/${u.id}` | `frontend/src/pages/Usuarios.tsx:163` |
| `/api/users/${user.id}` | `frontend/src/components/SecurityMenu.tsx:155` |
| `/api/users/` | `frontend/src/pages/Sociedade.tsx:125` |
| `/api/users/` | `frontend/src/pages/Usuarios.tsx:98` |
| `/api/users/me/avatar` | `frontend/src/components/SecurityMenu.tsx:78` |
| `/api/users/me/avatar` | `frontend/src/components/SecurityMenu.tsx:98` |
| `/api/users/me/sessions/${sessionId}/revoke` | `frontend/src/components/AccountSecurity.tsx:146` |
| `/api/users/me/sessions/revoke-others` | `frontend/src/components/AccountSecurity.tsx:161` |
| `/api/users/me/totp-qr` | `frontend/src/components/AccountSecurity.tsx:90` |
| `/api/users` | `frontend/src/config/moduleRegistry.tsx:937` |
| `/api/utils/cep/${cep}` | `frontend/src/pages/Clientes.tsx:686` |
| `/api/v1/` | `frontend/src/lib/api.prefixo.test.ts:56` |
| `/api/v1/` | `frontend/src/lib/api.prefixo.test.ts:7` |
| `/api/v1/` | `frontend/src/lib/api.ts:37` |
| `/api/v1/cases/` | `frontend/src/components/__tests__/FlowEnhancements.test.ts:31` |
| `/api/v1/casos/${id}` | `frontend/src/lib/api.prefixo.test.ts:153` |
| `/api/v1/despesas` | `frontend/src/lib/api.prefixo.test.ts:152` |
| `/api/v1/itens` | `frontend/src/lib/api.prefixo.test.ts:158` |
| `/api/v1/itens` | `frontend/src/lib/api.prefixo.test.ts:162` |
| `/api/v1/itens` | `frontend/src/lib/api.prefixo.test.ts:49` |
| `/api/v1/tasks/` | `frontend/src/components/__tests__/FlowEnhancements.test.ts:80` |
| `/api/v1/v1/despesas` | `frontend/src/lib/api.prefixo.test.ts:10` |
| `/api/v1` | `frontend/src/lib/api.prefixo.test.ts:4` |
| `/api/v1` | `frontend/src/lib/api.ts:37` |
| `/api/v1` | `frontend/src/lib/api.ts:9` |
| `/api/validador-juridico/validar` | `frontend/src/pages/IA.tsx:133` |
| `/api/workflow/templates/${id}` | `frontend/src/pages/Workflow.tsx:95` |
| `/api/workflow/templates` | `frontend/src/pages/Workflow.tsx:68` |
| `/api/workflow` | `frontend/src/config/moduleRegistry.tsx:667` |

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
