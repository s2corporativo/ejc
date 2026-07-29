# MATRIZ DE ROTAS — EJC

> Gerado por `scripts/governanca/inventario-repo.sh` em 2026-07-29, commit `abcf2c46`.
> Divergencia entre backend e frontend nesta matriz e defeito P1.

## 1. Rotas declaradas no backend

| Metodo | Caminho | Arquivo |
|---|---|---|
| DELETE | `/admin-esp/{aid}` | `backend/app/routers/ramos.py:1355` |
| DELETE | `/bancario/{bid}` | `backend/app/routers/ramos.py:3242` |
| DELETE | `/cases/{case_id}/etiquetas/{etiqueta_id}` | `backend/app/routers/etiquetas.py:90` |
| DELETE | `/civel/{cid}` | `backend/app/routers/ramos.py:671` |
| DELETE | `/docs/{doc_id}` | `backend/app/routers/rag.py:412` |
| DELETE | `/drive/{file_id}` | `backend/app/routers/documents.py:1070` |
| DELETE | `/empresarial/{eid}` | `backend/app/routers/ramos.py:438` |
| DELETE | `/etiquetas/{etiqueta_id}` | `backend/app/routers/etiquetas.py:50` |
| DELETE | `/keywords/{keyword_id}` | `backend/app/routers/diario_oficial.py:78` |
| DELETE | `/me/avatar` | `backend/app/routers/users.py:499` |
| DELETE | `/penal/{pid}` | `backend/app/routers/ramos.py:929` |
| DELETE | `/processes/{pid}` | `backend/app/routers/processes.py:194` |
| DELETE | `/push/subscriptions/{subscription_id}` | `backend/app/routers/notifications.py:198` |
| DELETE | `/settings/{module_key}` | `backend/app/routers/module_settings.py:139` |
| DELETE | `/socios/{socio_id}` | `backend/app/routers/sociedades_cliente.py:423` |
| DELETE | `/templates/{template_id}` | `backend/app/routers/checklists.py:180` |
| DELETE | `/templates/{template_id}` | `backend/app/routers/workflow.py:169` |
| DELETE | `/trabalhista-esp/{tid}` | `backend/app/routers/ramos.py:1142` |
| DELETE | `/{analise_id}` | `backend/app/routers/raio_x.py:735` |
| DELETE | `/{analysis_id}` | `backend/app/routers/bank_analysis.py:351` |
| DELETE | `/{area}` | `backend/app/routers/caso_areas.py:45` |
| DELETE | `/{atendimento_id}` | `backend/app/routers/atendimentos.py:1030` |
| DELETE | `/{case_id}` | `backend/app/routers/cases.py:588` |
| DELETE | `/{checklist_id}` | `backend/app/routers/checklists.py:456` |
| DELETE | `/{client_id}/pending-items/{item_id}` | `backend/app/routers/pending_items.py:111` |
| DELETE | `/{client_id}` | `backend/app/routers/clients.py:676` |
| DELETE | `/{contract_id}` | `backend/app/routers/office_contracts.py:133` |
| DELETE | `/{contrato_id}` | `backend/app/routers/contratos_societarios.py:341` |
| DELETE | `/{deadline_id}` | `backend/app/routers/deadlines.py:341` |
| DELETE | `/{despesa_id}` | `backend/app/routers/despesas.py:243` |
| DELETE | `/{doc_id}` | `backend/app/routers/documents.py:656` |
| DELETE | `/{doc_id}` | `backend/app/routers/legal_docs.py:694` |
| DELETE | `/{entry_id}` | `backend/app/routers/timesheet.py:142` |
| DELETE | `/{env_id}` | `backend/app/routers/environmental.py:184` |
| DELETE | `/{evento_id}` | `backend/app/routers/agenda_eventos.py:241` |
| DELETE | `/{fee_id}` | `backend/app/routers/fees.py:283` |
| DELETE | `/{help_id}` | `backend/app/routers/module_help.py:130` |
| DELETE | `/{juri_id}` | `backend/app/routers/jurisprudencia_interna.py:175` |
| DELETE | `/{lancamento_id}` | `backend/app/routers/centro_custos.py:301` |
| DELETE | `/{mem_id}` | `backend/app/routers/memoria_institucional.py:171` |
| DELETE | `/{parte_id}` | `backend/app/routers/case_partes.py:87` |
| DELETE | `/{prompt_id}` | `backend/app/routers/prompts_juridicos.py:207` |
| DELETE | `/{prova_id}` | `backend/app/routers/provas.py:216` |
| DELETE | `/{provider_key}/{field_key}` | `backend/app/routers/credential_vault.py:382` |
| DELETE | `/{registro_id}` | `backend/app/routers/lgpd_registros.py:217` |
| DELETE | `/{room_id}/arquivos/{arquivo_id}` | `backend/app/routers/data_room.py:431` |
| DELETE | `/{room_id}/links/{link_id}` | `backend/app/routers/data_room.py:506` |
| DELETE | `/{room_id}` | `backend/app/routers/data_room.py:626` |
| DELETE | `/{sociedade_id}` | `backend/app/routers/sociedades_cliente.py:339` |
| DELETE | `/{suspensao_id}` | `backend/app/routers/suspensoes.py:116` |
| DELETE | `/{task_id}` | `backend/app/routers/tasks.py:180` |
| DELETE | `/{tese_id}` | `backend/app/routers/teses.py:311` |
| DELETE | `/{tpl_id}` | `backend/app/routers/templates.py:181` |
| DELETE | `/{user_id}` | `backend/app/routers/users.py:379` |
| DELETE | `/{withdrawal_id}` | `backend/app/routers/partner_withdrawals.py:175` |
| GET | `/` | `backend/app/routers/agenda_eventos.py:102` |
| GET | `/` | `backend/app/routers/audit.py:19` |
| GET | `/` | `backend/app/routers/bank_analysis.py:123` |
| GET | `/` | `backend/app/routers/cases.py:80` |
| GET | `/` | `backend/app/routers/clients.py:400` |
| GET | `/` | `backend/app/routers/dashboard.py:37` |
| GET | `/` | `backend/app/routers/deadlines.py:89` |
| GET | `/` | `backend/app/routers/documents.py:472` |
| GET | `/` | `backend/app/routers/environmental.py:74` |
| GET | `/` | `backend/app/routers/fees.py:72` |
| GET | `/` | `backend/app/routers/intimacoes.py:160` |
| GET | `/` | `backend/app/routers/legal_docs.py:278` |
| GET | `/` | `backend/app/routers/module_help.py:50` |
| GET | `/` | `backend/app/routers/notifications.py:38` |
| GET | `/` | `backend/app/routers/peca_geracao.py:342` |
| GET | `/` | `backend/app/routers/peca_geracao_router.py:21` |
| GET | `/` | `backend/app/routers/procuracoes.py:39` |
| GET | `/` | `backend/app/routers/prompts.py:49` |
| GET | `/` | `backend/app/routers/raio_x.py:137` |
| GET | `/` | `backend/app/routers/search.py:82` |
| GET | `/` | `backend/app/routers/signatures.py:121` |
| GET | `/` | `backend/app/routers/suspensoes.py:66` |
| GET | `/` | `backend/app/routers/tasks.py:45` |
| GET | `/` | `backend/app/routers/templates.py:67` |
| GET | `/` | `backend/app/routers/trash.py:39` |
| GET | `/` | `backend/app/routers/users.py:261` |
| GET | `/admin-esp/ferramentas/mandado-seguranca` | `backend/app/routers/ramos.py:3145` |
| GET | `/admin-esp/ferramentas/reajuste-contrato-administrativo` | `backend/app/routers/ramos.py:3729` |
| GET | `/admin-esp/ferramentas/recurso-multa-transito` | `backend/app/routers/ramos.py:1455` |
| GET | `/admin-esp` | `backend/app/routers/ramos.py:1321` |
| GET | `/advogado/{user_id}` | `backend/app/routers/extratos.py:46` |
| GET | `/agents` | `backend/app/routers/ai_core.py:190` |
| GET | `/alertas/nao-lidos/count` | `backend/app/routers/diario_oficial.py:152` |
| GET | `/alertas` | `backend/app/routers/diario_oficial.py:97` |
| GET | `/ambiental/ferramentas/auto-infracao-ambiental` | `backend/app/routers/ramos.py:4198` |
| GET | `/ambiental/ferramentas/crimes-ambientais` | `backend/app/routers/ramos.py:4279` |
| GET | `/ambiental/ferramentas/licenciamento` | `backend/app/routers/ramos.py:4399` |
| GET | `/ambiental/ferramentas/reserva-legal` | `backend/app/routers/ramos.py:4463` |
| GET | `/ambiental/ferramentas/tac-ambiental` | `backend/app/routers/ramos.py:4328` |
| GET | `/analise-vencedora/{caso_id}` | `backend/app/routers/curadoria_renomada.py:47` |
| GET | `/api/health/ready` | `backend/app/main.py:511` |
| GET | `/api/health` | `backend/app/main.py:488` |
| GET | `/audit` | `backend/app/routers/google_drive_knowledge.py:73` |
| GET | `/bancario/ferramentas/analise-juros` | `backend/app/routers/ramos.py:3248` |
| GET | `/bancario/ferramentas/busca-apreensao` | `backend/app/routers/ramos.py:3341` |
| GET | `/bancario/ferramentas/juros-abusivos` | `backend/app/routers/ramos.py:2940` |
| GET | `/bancario/ferramentas/superendividamento` | `backend/app/routers/ramos.py:3292` |
| GET | `/bancario/ferramentas/taxas-bacen` | `backend/app/routers/ramos.py:3774` |
| GET | `/bancario` | `backend/app/routers/ramos.py:3211` |
| GET | `/busca-avancada` | `backend/app/routers/teses.py:192` |
| GET | `/buscar/lexml` | `backend/app/routers/jurisprudencia_externa.py:53` |
| GET | `/buscar/tjmg` | `backend/app/routers/jurisprudencia_externa.py:68` |
| GET | `/buscar` | `backend/app/routers/jurisprudencia_externa.py:33` |
| GET | `/buscar` | `backend/app/routers/rag.py:347` |
| GET | `/case-health/{case_id}` | `backend/app/routers/analytics.py:109` |
| GET | `/case-health` | `backend/app/routers/analytics.py:98` |
| GET | `/cases/{case_id}/etiquetas` | `backend/app/routers/etiquetas.py:59` |
| GET | `/cases/{case_id}/processes` | `backend/app/routers/processes.py:37` |
| GET | `/cases/{case_id}/provisionamento` | `backend/app/routers/honorarios_calc.py:43` |
| GET | `/cases/{case_id}/termo-consentimento-ia` | `backend/app/routers/compliance.py:134` |
| GET | `/cases/{case_id}/teto-etico` | `backend/app/routers/honorarios_calc.py:67` |
| GET | `/caso/{case_id}/resumo` | `backend/app/routers/centro_custos.py:147` |
| GET | `/casos.csv` | `backend/app/routers/export.py:63` |
| GET | `/casos/{case_id}.pdf` | `backend/app/routers/export.py:81` |
| GET | `/casos/{case_id}/alertas` | `backend/app/routers/visual_law.py:117` |
| GET | `/casos/{case_id}/ambiental` | `backend/app/routers/novos_modulos.py:164` |
| GET | `/casos/{case_id}/matriz-risco` | `backend/app/routers/visual_law.py:87` |
| GET | `/casos/{case_id}/mensagens` | `backend/app/routers/portal.py:208` |
| GET | `/casos/{case_id}/proposta` | `backend/app/routers/honorarios_oab.py:406` |
| GET | `/casos/{case_id}/timeline` | `backend/app/routers/visual_law.py:46` |
| GET | `/casos/{case_id}` | `backend/app/routers/checklists.py:309` |
| GET | `/casos/{case_id}` | `backend/app/routers/portal.py:80` |
| GET | `/casos/{case_id}` | `backend/app/routers/teses.py:249` |
| GET | `/casos/{case_id}` | `backend/app/routers/timesheet.py:49` |
| GET | `/casos/{case_id}` | `backend/app/routers/workflow.py:188` |
| GET | `/chats` | `backend/app/routers/whatsapp.py:115` |
| GET | `/checklist` | `backend/app/routers/conversao_caso.py:247` |
| GET | `/civel/ferramentas/alimentos-calcular` | `backend/app/routers/ramos.py:751` |
| GET | `/civel/ferramentas/calculo-dano-moral` | `backend/app/routers/ramos.py:3456` |
| GET | `/civel/ferramentas/partilha-divorcio` | `backend/app/routers/ramos.py:3568` |
| GET | `/civel/ferramentas/prazos-contestacao` | `backend/app/routers/ramos.py:683` |
| GET | `/civel/ferramentas/prescricao-consumidor` | `backend/app/routers/ramos.py:3391` |
| GET | `/civel/ferramentas/rescisao-locacao` | `backend/app/routers/ramos.py:3600` |
| GET | `/civel/ferramentas/usucapiao-verificar` | `backend/app/routers/ramos.py:802` |
| GET | `/civel` | `backend/app/routers/ramos.py:638` |
| GET | `/clientes.csv` | `backend/app/routers/export.py:45` |
| GET | `/cobertura` | `backend/app/routers/rag_governance.py:89` |
| GET | `/cofre/documentos/{document_id}/logs` | `backend/app/routers/novos_modulos.py:310` |
| GET | `/cofre/relatorio` | `backend/app/routers/novos_modulos.py:424` |
| GET | `/consolidado` | `backend/app/routers/centro_custos.py:208` |
| GET | `/consolidado` | `backend/app/routers/financeiro_consolidado.py:44` |
| GET | `/consumidor/ferramentas/devolucao-dobro` | `backend/app/routers/ramos.py:1764` |
| GET | `/consumidor/ferramentas/negativacao-indevida` | `backend/app/routers/ramos.py:3076` |
| GET | `/consumidor/ferramentas/prazos-cdc` | `backend/app/routers/ramos.py:1855` |
| GET | `/contextual/{case_id}` | `backend/app/routers/raio_x.py:220` |
| GET | `/contextual` | `backend/app/routers/ai_skills.py:223` |
| GET | `/contracts` | `backend/app/routers/architecture.py:45` |
| GET | `/custas-tjmg` | `backend/app/routers/calculadoras.py:153` |
| GET | `/dashboard` | `backend/app/routers/atendimentos.py:786` |
| GET | `/dashboard` | `backend/app/routers/ia_governanca.py:227` |
| GET | `/dashboard` | `backend/app/routers/ia_saude.py:44` |
| GET | `/desfechos` | `backend/app/routers/jurimetria_extra.py:60` |
| GET | `/detalhado/{case_id}` | `backend/app/routers/extratos.py:19` |
| GET | `/diagnostico-sistema` | `backend/app/routers/module_help.py:65` |
| GET | `/digest-semanal` | `backend/app/routers/regulatorio.py:25` |
| GET | `/digital_lgpd/ferramentas/multa-lgpd` | `backend/app/routers/ramos.py:2191` |
| GET | `/digital_lgpd/ferramentas/prazos-lgpd` | `backend/app/routers/ramos.py:2233` |
| GET | `/distribuicao` | `backend/app/routers/gestao_societaria.py:206` |
| GET | `/docs/{doc_id}/comparar` | `backend/app/routers/rag_governance.py:243` |
| GET | `/docs/{doc_id}` | `backend/app/routers/rag_governance.py:98` |
| GET | `/docs` | `backend/app/routers/rag.py:380` |
| GET | `/documento-unico/{arquivo_id}/download` | `backend/app/routers/provas.py:666` |
| GET | `/documentos` | `backend/app/routers/portal.py:123` |
| GET | `/dossie/{case_id}` | `backend/app/routers/ai.py:78` |
| GET | `/drive/{file_id}/download` | `backend/app/routers/documents.py:1024` |
| GET | `/drive/{file_id}/link` | `backend/app/routers/documents.py:995` |
| GET | `/due-diligence/templates` | `backend/app/routers/novos_modulos.py:256` |
| GET | `/empresa/{nome_empresa}` | `backend/app/routers/consumidor_monitor.py:165` |
| GET | `/empresarial/ferramentas/juros-mora` | `backend/app/routers/ramos.py:2687` |
| GET | `/empresarial/ferramentas/prazos-rj` | `backend/app/routers/ramos.py:444` |
| GET | `/empresarial/ferramentas/verificar-cade` | `backend/app/routers/ramos.py:522` |
| GET | `/empresarial/tipos` | `backend/app/routers/ramos.py:402` |
| GET | `/empresarial` | `backend/app/routers/ramos.py:413` |
| GET | `/empresas` | `backend/app/routers/consumidor_monitor.py:150` |
| GET | `/estado-operacional` | `backend/app/routers/ia_saude.py:85` |
| GET | `/etiquetas` | `backend/app/routers/etiquetas.py:31` |
| GET | `/expiring` | `backend/app/routers/office_contracts.py:46` |
| GET | `/export.csv` | `backend/app/routers/deadlines.py:136` |
| GET | `/export/csv` | `backend/app/routers/despesas.py:109` |
| GET | `/ext/benchmarks` | `backend/app/routers/jurimetria_extra.py:86` |
| GET | `/ext/predicao/provimento` | `backend/app/routers/jurimetria_extra.py:107` |
| GET | `/ext/stats` | `backend/app/routers/jurimetria_extra.py:75` |
| GET | `/familia/ferramentas/debito-alimentos` | `backend/app/routers/ramos.py:1919` |
| GET | `/familia/ferramentas/itcmd-inventario` | `backend/app/routers/ramos.py:2374` |
| GET | `/files` | `backend/app/routers/google_drive_knowledge.py:53` |
| GET | `/financeiro` | `backend/app/routers/portal.py:144` |
| GET | `/fontes` | `backend/app/routers/ia_governanca.py:472` |
| GET | `/fontes` | `backend/app/routers/jurisprudencia_externa.py:208` |
| GET | `/funil` | `backend/app/routers/analytics.py:52` |
| GET | `/guardrails` | `backend/app/routers/ia_governanca.py:518` |
| GET | `/historico/{case_id}` | `backend/app/routers/ia_defensiva.py:97` |
| GET | `/honorarios.csv` | `backend/app/routers/export.py:183` |
| GET | `/imobiliario/ferramentas/distrato` | `backend/app/routers/ramos.py:2971` |
| GET | `/imobiliario/ferramentas/prazos-despejo` | `backend/app/routers/ramos.py:2046` |
| GET | `/imobiliario/ferramentas/reajuste-aluguel` | `backend/app/routers/ramos.py:1995` |
| GET | `/inadimplencia/alertas` | `backend/app/routers/novos_modulos.py:93` |
| GET | `/inss` | `backend/app/routers/calculadoras.py:80` |
| GET | `/integrations` | `backend/app/routers/system_modules.py:53` |
| GET | `/irrf` | `backend/app/routers/calculadoras.py:89` |
| GET | `/itens` | `backend/app/routers/honorarios_oab.py:194` |
| GET | `/jurimetria` | `backend/app/routers/analytics.py:27` |
| GET | `/jurisprudencia-mg/geometria` | `backend/app/routers/ia_governanca.py:536` |
| GET | `/jurisprudencia-mg` | `backend/app/routers/ia_governanca.py:661` |
| GET | `/kanban-columns` | `backend/app/routers/kanban.py:43` |
| GET | `/keywords` | `backend/app/routers/diario_oficial.py:49` |
| GET | `/list` | `backend/app/routers/ai_skills.py:260` |
| GET | `/logs/feedback/resumo` | `backend/app/routers/ai.py:280` |
| GET | `/logs/{log_id}/citacoes` | `backend/app/routers/ai.py:190` |
| GET | `/logs` | `backend/app/routers/ai.py:118` |
| GET | `/mapa` | `backend/app/routers/system_modules.py:41` |
| GET | `/matriz` | `backend/app/routers/provas.py:463` |
| GET | `/me/calendar-url` | `backend/app/routers/users.py:416` |
| GET | `/me/security` | `backend/app/routers/users.py:93` |
| GET | `/me/sessions` | `backend/app/routers/users.py:117` |
| GET | `/me/totp-qr` | `backend/app/routers/users.py:229` |
| GET | `/me/url` | `backend/app/routers/calendar_feed.py:102` |
| GET | `/me` | `backend/app/routers/advogado_estilo.py:19` |
| GET | `/me` | `backend/app/routers/users.py:87` |
| GET | `/memoria/{modalidade}` | `backend/app/routers/defesas_revisoes_avancado.py:485` |
| GET | `/mensagens/nao-lidas` | `backend/app/routers/portal.py:184` |
| GET | `/mensal` | `backend/app/routers/relatorio.py:21` |
| GET | `/meta` | `backend/app/routers/defesas_revisoes.py:242` |
| GET | `/meta` | `backend/app/routers/entrada_universal.py:173` |
| GET | `/meta` | `backend/app/routers/peca_geracao.py:75` |
| GET | `/meus-casos` | `backend/app/routers/portal.py:33` |
| GET | `/meus` | `backend/app/routers/atendimentos.py:724` |
| GET | `/modalidades` | `backend/app/routers/analise_bancaria.py:154` |
| GET | `/monitor-legislativo` | `backend/app/routers/rag.py:430` |
| GET | `/native-skills/coverage` | `backend/app/routers/ai_core.py:209` |
| GET | `/onboarding/{client_id}` | `backend/app/routers/analytics.py:81` |
| GET | `/onboarding` | `backend/app/routers/analytics.py:71` |
| GET | `/overview` | `backend/app/routers/jurimetria.py:28` |
| GET | `/painel-semanal` | `backend/app/routers/consumidor_monitor.py:276` |
| GET | `/parecer/{arquivo_id}/download` | `backend/app/routers/previdenciario_beneficio.py:230` |
| GET | `/peca/{arquivo_id}/download` | `backend/app/routers/ambiental_estrategia.py:237` |
| GET | `/penal/ferramentas/dosimetria` | `backend/app/routers/ramos.py:2481` |
| GET | `/penal/ferramentas/prazos-processuais` | `backend/app/routers/ramos.py:935` |
| GET | `/penal/ferramentas/prescricao-penal` | `backend/app/routers/ramos.py:2426` |
| GET | `/penal/ferramentas/prescricao-punitiva` | `backend/app/routers/ramos.py:1067` |
| GET | `/penal/ferramentas/verificar-anpp` | `backend/app/routers/ramos.py:989` |
| GET | `/penal` | `backend/app/routers/ramos.py:901` |
| GET | `/perfis` | `backend/app/routers/ia_especializada.py:50` |
| GET | `/planilha/{arquivo_id}/download` | `backend/app/routers/trabalhista_liquidacao.py:335` |
| GET | `/por-advogado/{advogado_id}` | `backend/app/routers/atendimentos.py:751` |
| GET | `/por-area` | `backend/app/routers/jurimetria.py:79` |
| GET | `/por-magistrado` | `backend/app/routers/jurimetria.py:116` |
| GET | `/por-tese` | `backend/app/routers/jurimetria.py:195` |
| GET | `/por-tribunal` | `backend/app/routers/jurimetria.py:157` |
| GET | `/precificacao/calcular/{rule_id}` | `backend/app/routers/novos_modulos.py:47` |
| GET | `/precificacao/tabela` | `backend/app/routers/novos_modulos.py:36` |
| GET | `/preferences` | `backend/app/routers/notifications.py:77` |
| GET | `/prescricao/tipos` | `backend/app/routers/calculadoras.py:131` |
| GET | `/previdenciario/ferramentas/carencia` | `backend/app/routers/ramos.py:2307` |
| GET | `/previdenciario/ferramentas/prazos` | `backend/app/routers/ramos.py:2099` |
| GET | `/previdenciario/ferramentas/tempo-contribuicao` | `backend/app/routers/ramos.py:2275` |
| GET | `/produtividade` | `backend/app/routers/produtividade.py:24` |
| GET | `/prompts` | `backend/app/routers/ia_governanca.py:455` |
| GET | `/provedores` | `backend/app/routers/ia_provider_metrics.py:51` |
| GET | `/ptax` | `backend/app/routers/indices.py:83` |
| GET | `/push/subscriptions` | `backend/app/routers/notifications.py:178` |
| GET | `/push/vapid-key` | `backend/app/routers/notifications.py:170` |
| GET | `/qrcode` | `backend/app/routers/whatsapp.py:75` |
| GET | `/radar/legislativo` | `backend/app/routers/intelligence_v3.py:18` |
| GET | `/radar` | `backend/app/routers/compliance.py:265` |
| GET | `/rag-curadoria` | `backend/app/routers/ia_governanca.py:368` |
| GET | `/ranking` | `backend/app/routers/teses.py:170` |
| GET | `/recentes` | `backend/app/routers/movimentos.py:15` |
| GET | `/regras-transicao` | `backend/app/routers/previdenciario_beneficio.py:81` |
| GET | `/relatorio-mensal` | `backend/app/routers/dashboard.py:194` |
| GET | `/relatorio/{arquivo_id}/download` | `backend/app/routers/tributario_fiscal.py:328` |
| GET | `/rentabilidade` | `backend/app/routers/analytics.py:61` |
| GET | `/responsaveis` | `backend/app/routers/atendimentos.py:595` |
| GET | `/resumo` | `backend/app/routers/despesas.py:27` |
| GET | `/resumo` | `backend/app/routers/fees.py:121` |
| GET | `/ripd/{arquivo_id}/download` | `backend/app/routers/lgpd_registros.py:418` |
| GET | `/roi-por-area` | `backend/app/routers/produtividade.py:91` |
| GET | `/roteamento/preview` | `backend/app/routers/ai.py:440` |
| GET | `/routes` | `backend/app/routers/architecture.py:15` |
| GET | `/saude` | `backend/app/routers/rag_governance.py:80` |
| GET | `/series` | `backend/app/routers/indices.py:58` |
| GET | `/settings` | `backend/app/routers/module_settings.py:58` |
| GET | `/skills` | `backend/app/routers/ai_core.py:203` |
| GET | `/socio/{user_id}` | `backend/app/routers/extratos.py:75` |
| GET | `/socios` | `backend/app/routers/gestao_societaria.py:71` |
| GET | `/solicitacoes-documentos` | `backend/app/routers/portal_documentos.py:60` |
| GET | `/solicitacoes-resumo` | `backend/app/routers/atendimentos.py:623` |
| GET | `/stats` | `backend/app/routers/atendimentos.py:818` |
| GET | `/stats` | `backend/app/routers/cases.py:130` |
| GET | `/stats` | `backend/app/routers/rag.py:35` |
| GET | `/stats` | `backend/app/routers/raio_x.py:100` |
| GET | `/status-captura` | `backend/app/routers/intimacoes.py:193` |
| GET | `/status` | `backend/app/routers/ai_core.py:215` |
| GET | `/status` | `backend/app/routers/ai_tools.py:58` |
| GET | `/status` | `backend/app/routers/backup_admin.py:89` |
| GET | `/status` | `backend/app/routers/cerebro.py:15` |
| GET | `/status` | `backend/app/routers/google_drive_knowledge.py:31` |
| GET | `/status` | `backend/app/routers/ia_defensiva.py:49` |
| GET | `/status` | `backend/app/routers/infosimples_tjmg.py:66` |
| GET | `/status` | `backend/app/routers/nfse.py:343` |
| GET | `/status` | `backend/app/routers/rag.py:51` |
| GET | `/status` | `backend/app/routers/transparencia.py:46` |
| GET | `/status` | `backend/app/routers/validador_juridico.py:32` |
| GET | `/status` | `backend/app/routers/whatsapp.py:64` |
| GET | `/sumulas/buscar` | `backend/app/routers/sumulas.py:56` |
| GET | `/tabela` | `backend/app/routers/honorarios_oab.py:79` |
| GET | `/taskscore` | `backend/app/routers/analytics.py:43` |
| GET | `/taxa-juros` | `backend/app/routers/indices.py:65` |
| GET | `/taxa-media` | `backend/app/routers/analise_bancaria.py:181` |
| GET | `/templates` | `backend/app/routers/checklists.py:119` |
| GET | `/templates` | `backend/app/routers/workflow.py:112` |
| GET | `/tendencias` | `backend/app/routers/jurimetria.py:232` |
| GET | `/teses` | `backend/app/routers/cerebro.py:65` |
| GET | `/teses` | `backend/app/routers/curadoria_renomada.py:34` |
| GET | `/tipos-rescisao` | `backend/app/routers/calculadoras.py:59` |
| GET | `/tipos` | `backend/app/routers/documents.py:210` |
| GET | `/trabalhista-esp/ferramentas/deposito-recursal` | `backend/app/routers/ramos.py:1252` |
| GET | `/trabalhista-esp/ferramentas/horas-extras` | `backend/app/routers/ramos.py:2588` |
| GET | `/trabalhista-esp/ferramentas/prazos` | `backend/app/routers/ramos.py:1155` |
| GET | `/trabalhista-esp/ferramentas/prescricao-trabalhista` | `backend/app/routers/ramos.py:1199` |
| GET | `/trabalhista-esp/ferramentas/verbas-rescisorias` | `backend/app/routers/ramos.py:3658` |
| GET | `/trabalhista-esp` | `backend/app/routers/ramos.py:1115` |
| GET | `/trabalhista/ferramentas/horas-extras` | `backend/app/routers/ramos.py:2652` |
| GET | `/transito/ferramentas/pontuacao-cnh` | `backend/app/routers/ramos.py:1500` |
| GET | `/transito/ferramentas/prazos-recurso` | `backend/app/routers/ramos.py:1476` |
| GET | `/transito/ferramentas/valor-multa` | `backend/app/routers/ramos.py:3040` |
| GET | `/triagem-jec` | `backend/app/routers/consumidor_monitor.py:203` |
| GET | `/tribunais` | `backend/app/routers/suspensoes.py:60` |
| GET | `/tributario/ferramentas/auto-infracao-prazos` | `backend/app/routers/ramos.py:3803` |
| GET | `/tributario/ferramentas/multa-mora` | `backend/app/routers/ramos.py:2853` |
| GET | `/tributario/ferramentas/parcelamento` | `backend/app/routers/ramos.py:3931` |
| GET | `/tributario/ferramentas/prescricao-decadencia` | `backend/app/routers/ramos.py:3847` |
| GET | `/tributario/ferramentas/reforma-tributaria` | `backend/app/routers/ramos.py:4147` |
| GET | `/tributario/ferramentas/regime-tributario` | `backend/app/routers/ramos.py:4048` |
| GET | `/tributario/ferramentas/simples-nacional` | `backend/app/routers/ramos.py:3994` |
| GET | `/uso-rotas` | `backend/app/routers/architecture.py:21` |
| GET | `/validar-cpf/{cpf}` | `backend/app/routers/utils.py:38` |
| GET | `/victory_vault/modelos` | `backend/app/routers/victory_vault_router.py:22` |
| GET | `/victory_vault/teses` | `backend/app/routers/victory_vault_router.py:14` |
| GET | `/{analise_id}/conversao/preview` | `backend/app/routers/raio_x.py:676` |
| GET | `/{analise_id}/documentos/{documento_id}/download` | `backend/app/routers/raio_x.py:614` |
| GET | `/{analise_id}/exportar` | `backend/app/routers/raio_x.py:641` |
| GET | `/{analise_id}` | `backend/app/routers/raio_x.py:323` |
| GET | `/{analysis_id}/excel` | `backend/app/routers/bank_analysis.py:170` |
| GET | `/{analysis_id}` | `backend/app/routers/bank_analysis.py:147` |
| GET | `/{atendimento_id}/historico` | `backend/app/routers/atendimentos.py:875` |
| GET | `/{atendimento_id}` | `backend/app/routers/atendimentos.py:913` |
| GET | `/{batch_id}` | `backend/app/routers/entrada_universal.py:311` |
| GET | `/{case_id}/andamentos/inteligencia` | `backend/app/routers/datajud_intelligence.py:18` |
| GET | `/{case_id}/andamentos/status` | `backend/app/routers/andamentos.py:36` |
| GET | `/{case_id}/historico` | `backend/app/routers/dossie_estrategico.py:145` |
| GET | `/{case_id}/linha-do-tempo` | `backend/app/routers/cases.py:1186` |
| GET | `/{case_id}/modulos` | `backend/app/routers/dossie_estrategico.py:126` |
| GET | `/{case_id}/movimentos` | `backend/app/routers/cases.py:712` |
| GET | `/{case_id}/resumo` | `backend/app/routers/cases.py:323` |
| GET | `/{case_id}/teses-sugeridas` | `backend/app/routers/cases.py:1247` |
| GET | `/{case_id}/{dossie_id}/pdf` | `backend/app/routers/dossie_estrategico.py:212` |
| GET | `/{case_id}` | `backend/app/routers/cases.py:302` |
| GET | `/{case_id}` | `backend/app/routers/dossie_estrategico.py:88` |
| GET | `/{checklist_id}` | `backend/app/routers/checklists.py:335` |
| GET | `/{client_id}/dados-lgpd.json` | `backend/app/routers/clients.py:833` |
| GET | `/{client_id}/esquecimento/bloqueios` | `backend/app/routers/clients.py:892` |
| GET | `/{client_id}/pending-items` | `backend/app/routers/pending_items.py:35` |
| GET | `/{client_id}/relatorio-lgpd` | `backend/app/routers/clients.py:762` |
| GET | `/{client_id}/resumo` | `backend/app/routers/lgpd_registros.py:250` |
| GET | `/{client_id}` | `backend/app/routers/clients.py:528` |
| GET | `/{com_id}/prazo-sugerido` | `backend/app/routers/intimacoes.py:317` |
| GET | `/{contract_id}` | `backend/app/routers/office_contracts.py:90` |
| GET | `/{contrato_id}` | `backend/app/routers/contratos_societarios.py:244` |
| GET | `/{doc_id}/download` | `backend/app/routers/documents.py:593` |
| GET | `/{doc_id}/exportar-docx` | `backend/app/routers/legal_docs.py:947` |
| GET | `/{doc_id}/jurisprudencia-check` | `backend/app/routers/legal_docs.py:484` |
| GET | `/{doc_id}/pdf` | `backend/app/routers/legal_docs.py:764` |
| GET | `/{doc_id}/validacao` | `backend/app/routers/legal_docs.py:369` |
| GET | `/{doc_id}` | `backend/app/routers/legal_docs.py:348` |
| GET | `/{fee_id}/rateio` | `backend/app/routers/exito_rateio.py:95` |
| GET | `/{indice}` | `backend/app/routers/indices.py:136` |
| GET | `/{juri_id}` | `backend/app/routers/jurisprudencia_interna.py:130` |
| GET | `/{mem_id}` | `backend/app/routers/memoria_institucional.py:124` |
| GET | `/{module_key:path}` | `backend/app/routers/module_help.py:82` |
| GET | `/{nota_id}/pdf` | `backend/app/routers/nfse.py:737` |
| GET | `/{nota_id}/xml` | `backend/app/routers/nfse.py:773` |
| GET | `/{nota_id}` | `backend/app/routers/nfse.py:710` |
| GET | `/{prompt_id}` | `backend/app/routers/prompts_juridicos.py:159` |
| GET | `/{provider_key}/{field_key}/historico` | `backend/app/routers/credential_vault.py:275` |
| GET | `/{room_id}` | `backend/app/routers/data_room.py:308` |
| GET | `/{session_id}/estado` | `backend/app/routers/legal_chat.py:196` |
| GET | `/{session_id}/exportar` | `backend/app/routers/legal_chat.py:382` |
| GET | `/{session_id}` | `backend/app/routers/legal_chat.py:118` |
| GET | `/{snapshot_id}` | `backend/app/routers/case_intelligence.py:77` |
| GET | `/{sociedade_id}` | `backend/app/routers/sociedades_cliente.py:273` |
| GET | `/{tese_id}` | `backend/app/routers/teses.py:275` |
| GET | `/{tpl_id}` | `backend/app/routers/templates.py:90` |
| GET | `/{user_id}/avatar` | `backend/app/routers/users.py:519` |
| PATCH | `/admin-esp/{aid}` | `backend/app/routers/ramos.py:1349` |
| PATCH | `/alertas/{alerta_id}/marcar-lido` | `backend/app/routers/diario_oficial.py:134` |
| PATCH | `/bancario/{bid}` | `backend/app/routers/ramos.py:3236` |
| PATCH | `/cases/{case_id}/kanban` | `backend/app/routers/kanban.py:57` |
| PATCH | `/civel/{cid}` | `backend/app/routers/ramos.py:665` |
| PATCH | `/cofre/documentos/{document_id}/sensibilidade` | `backend/app/routers/novos_modulos.py:393` |
| PATCH | `/docs/{doc_id}` | `backend/app/routers/rag_governance.py:110` |
| PATCH | `/empresarial/{eid}` | `backend/app/routers/ramos.py:432` |
| PATCH | `/historico/{log_id}/status` | `backend/app/routers/ia_defensiva.py:145` |
| PATCH | `/inadimplencia/alertas/{alert_id}/resolver` | `backend/app/routers/novos_modulos.py:123` |
| PATCH | `/logs/{log_id}/hitl` | `backend/app/routers/ai.py:155` |
| PATCH | `/penal/{pid}` | `backend/app/routers/ramos.py:923` |
| PATCH | `/processes/{pid}` | `backend/app/routers/processes.py:78` |
| PATCH | `/rag-curadoria/{doc_id}` | `backend/app/routers/ia_governanca.py:427` |
| PATCH | `/socios/{socio_id}` | `backend/app/routers/gestao_societaria.py:110` |
| PATCH | `/socios/{socio_id}` | `backend/app/routers/sociedades_cliente.py:399` |
| PATCH | `/trabalhista-esp/{tid}` | `backend/app/routers/ramos.py:1136` |
| PATCH | `/{analise_id}` | `backend/app/routers/raio_x.py:335` |
| PATCH | `/{atendimento_id}` | `backend/app/routers/atendimentos.py:928` |
| PATCH | `/{case_id}/{dossie_id}/aprovar` | `backend/app/routers/dossie_estrategico.py:167` |
| PATCH | `/{case_id}` | `backend/app/routers/cases.py:400` |
| PATCH | `/{checklist_id}/itens/{item_id}/marcar` | `backend/app/routers/checklists.py:358` |
| PATCH | `/{client_id}/pending-items/{item_id}` | `backend/app/routers/pending_items.py:83` |
| PATCH | `/{client_id}` | `backend/app/routers/clients.py:604` |
| PATCH | `/{contract_id}` | `backend/app/routers/office_contracts.py:103` |
| PATCH | `/{contrato_id}` | `backend/app/routers/contratos_societarios.py:276` |
| PATCH | `/{deadline_id}/confirmar` | `backend/app/routers/deadlines.py:282` |
| PATCH | `/{deadline_id}` | `backend/app/routers/deadlines.py:232` |
| PATCH | `/{despesa_id}` | `backend/app/routers/despesas.py:207` |
| PATCH | `/{doc_id}/aprovar` | `backend/app/routers/legal_docs.py:534` |
| PATCH | `/{doc_id}/protocolo` | `backend/app/routers/legal_docs.py:590` |
| PATCH | `/{doc_id}` | `backend/app/routers/documents.py:688` |
| PATCH | `/{doc_id}` | `backend/app/routers/legal_docs.py:413` |
| PATCH | `/{env_id}` | `backend/app/routers/environmental.py:143` |
| PATCH | `/{evento_id}` | `backend/app/routers/agenda_eventos.py:176` |
| PATCH | `/{fee_id}` | `backend/app/routers/fees.py:186` |
| PATCH | `/{help_id}` | `backend/app/routers/module_help.py:111` |
| PATCH | `/{juri_id}` | `backend/app/routers/jurisprudencia_interna.py:151` |
| PATCH | `/{lancamento_id}` | `backend/app/routers/centro_custos.py:279` |
| PATCH | `/{mem_id}` | `backend/app/routers/memoria_institucional.py:141` |
| PATCH | `/{prompt_id}` | `backend/app/routers/prompts_juridicos.py:176` |
| PATCH | `/{prova_id}` | `backend/app/routers/provas.py:185` |
| PATCH | `/{registro_id}` | `backend/app/routers/lgpd_registros.py:196` |
| PATCH | `/{session_id}/estado` | `backend/app/routers/legal_chat.py:175` |
| PATCH | `/{session_id}` | `backend/app/routers/legal_chat.py:138` |
| PATCH | `/{sociedade_id}` | `backend/app/routers/sociedades_cliente.py:315` |
| PATCH | `/{task_id}` | `backend/app/routers/tasks.py:120` |
| PATCH | `/{tese_id}` | `backend/app/routers/teses.py:291` |
| PATCH | `/{user_id}` | `backend/app/routers/users.py:319` |
| PATCH | `/{withdrawal_id}/approve` | `backend/app/routers/partner_withdrawals.py:94` |
| PATCH | `/{withdrawal_id}/pay` | `backend/app/routers/partner_withdrawals.py:147` |
| PATCH | `/{withdrawal_id}/reject` | `backend/app/routers/partner_withdrawals.py:123` |
| POST | `/` | `backend/app/routers/agenda_eventos.py:138` |
| POST | `/` | `backend/app/routers/cases.py:186` |
| POST | `/` | `backend/app/routers/clients.py:447` |
| POST | `/` | `backend/app/routers/deadlines.py:189` |
| POST | `/` | `backend/app/routers/environmental.py:100` |
| POST | `/` | `backend/app/routers/fees.py:152` |
| POST | `/` | `backend/app/routers/legal_docs.py:320` |
| POST | `/` | `backend/app/routers/module_help.py:98` |
| POST | `/` | `backend/app/routers/procuracoes.py:78` |
| POST | `/` | `backend/app/routers/prompts.py:41` |
| POST | `/` | `backend/app/routers/raio_x.py:187` |
| POST | `/` | `backend/app/routers/signatures.py:48` |
| POST | `/` | `backend/app/routers/suspensoes.py:89` |
| POST | `/` | `backend/app/routers/tasks.py:86` |
| POST | `/` | `backend/app/routers/templates.py:105` |
| POST | `/` | `backend/app/routers/timesheet.py:75` |
| POST | `/` | `backend/app/routers/users.py:283` |
| POST | `/abusividade` | `backend/app/routers/analise_bancaria.py:254` |
| POST | `/admin-esp` | `backend/app/routers/ramos.py:1328` |
| POST | `/adversarial` | `backend/app/routers/defesas_revisoes_avancado.py:221` |
| POST | `/agente/stream` | `backend/app/routers/ia_agente.py:35` |
| POST | `/alterar-senha` | `backend/app/routers/auth.py:532` |
| POST | `/analisar-caso` | `backend/app/routers/ai.py:54` |
| POST | `/analisar-contrato` | `backend/app/routers/ai.py:905` |
| POST | `/analisar-decisao` | `backend/app/routers/defesas_revisoes_avancado.py:450` |
| POST | `/analisar-magistrado` | `backend/app/routers/diplomacia_v3.py:122` |
| POST | `/analisar-url` | `backend/app/routers/documento_ia.py:207` |
| POST | `/analisar-xml` | `backend/app/routers/tributario_fiscal.py:106` |
| POST | `/analisar` | `backend/app/routers/defesas_revisoes.py:259` |
| POST | `/analisar` | `backend/app/routers/documento_ia.py:106` |
| POST | `/analisar` | `backend/app/routers/ia_defensiva.py:175` |
| POST | `/analise-estrategica` | `backend/app/routers/cerebro.py:19` |
| POST | `/analise-impacto` | `backend/app/routers/intelligence_v3.py:36` |
| POST | `/analyze` | `backend/app/routers/ai_core.py:140` |
| POST | `/aplicar-acoes` | `backend/app/routers/documento_ia.py:284` |
| POST | `/atualizar-valor` | `backend/app/routers/indices.py:103` |
| POST | `/auditar-peca` | `backend/app/routers/ai.py:371` |
| POST | `/bancario` | `backend/app/routers/ramos.py:3218` |
| POST | `/breakeven` | `backend/app/routers/visual_law.py:143` |
| POST | `/buscar` | `backend/app/routers/precedentes_jurisprudencia.py:34` |
| POST | `/calcular-acordo` | `backend/app/routers/diplomacia_v3.py:40` |
| POST | `/calcular-especialidade` | `backend/app/routers/defesas_revisoes_avancado.py:287` |
| POST | `/calcular` | `backend/app/routers/deadlines.py:69` |
| POST | `/calcular` | `backend/app/routers/score_juridico.py:54` |
| POST | `/calcular` | `backend/app/routers/trabalhista_liquidacao.py:139` |
| POST | `/capturar-agora` | `backend/app/routers/intimacoes.py:479` |
| POST | `/cases/{case_id}/etiquetas` | `backend/app/routers/etiquetas.py:71` |
| POST | `/cases/{case_id}/processes` | `backend/app/routers/processes.py:49` |
| POST | `/cases/{case_id}/sync-prazos` | `backend/app/routers/datajud.py:109` |
| POST | `/cases/{case_id}/sync` | `backend/app/routers/datajud.py:67` |
| POST | `/caso/{case_id}/estrategia` | `backend/app/routers/ai.py:796` |
| POST | `/caso/{case_id}/faturar` | `backend/app/routers/timesheet.py:93` |
| POST | `/caso/{case_id}/gerar-ia` | `backend/app/routers/checklists.py:278` |
| POST | `/caso/{case_id}/visual-law` | `backend/app/routers/ai.py:754` |
| POST | `/casos/verificar-conflito` | `backend/app/routers/sumulas.py:99` |
| POST | `/casos/{case_id}/ambiental` | `backend/app/routers/novos_modulos.py:181` |
| POST | `/casos/{case_id}/analise-completa` | `backend/app/routers/intake.py:361` |
| POST | `/casos/{case_id}/aplicar-padrao` | `backend/app/routers/workflow.py:276` |
| POST | `/casos/{case_id}/assistente` | `backend/app/routers/ai.py:514` |
| POST | `/casos/{case_id}/avancar` | `backend/app/routers/workflow.py:367` |
| POST | `/casos/{case_id}/concluir` | `backend/app/routers/workflow.py:468` |
| POST | `/casos/{case_id}/dual` | `backend/app/routers/ai.py:634` |
| POST | `/casos/{case_id}/iniciar` | `backend/app/routers/workflow.py:228` |
| POST | `/casos/{case_id}/mensagens` | `backend/app/routers/portal.py:234` |
| POST | `/casos/{case_id}/proposta/sugerir` | `backend/app/routers/honorarios_oab.py:355` |
| POST | `/casos/{case_id}/proposta` | `backend/app/routers/honorarios_oab.py:373` |
| POST | `/cet` | `backend/app/routers/analise_bancaria.py:219` |
| POST | `/chat` | `backend/app/routers/ai_core.py:108` |
| POST | `/checar-conflito` | `backend/app/routers/clients.py:244` |
| POST | `/citacoes/verificar` | `backend/app/routers/ai.py:31` |
| POST | `/civel` | `backend/app/routers/ramos.py:645` |
| POST | `/cobranca` | `backend/app/routers/pix.py:61` |
| POST | `/cofre/documentos/{document_id}/registrar-acesso` | `backend/app/routers/novos_modulos.py:340` |
| POST | `/comparar-documentos` | `backend/app/routers/defesas_revisoes_avancado.py:190` |
| POST | `/consistencia` | `backend/app/routers/qualidade.py:74` |
| POST | `/contrato` | `backend/app/routers/analise_bancaria.py:117` |
| POST | `/correcao-monetaria` | `backend/app/routers/calculadoras.py:101` |
| POST | `/critica-adversarial` | `backend/app/routers/ia_adversarial.py:42` |
| POST | `/curadoria/apply` | `backend/app/routers/google_drive_knowledge.py:115` |
| POST | `/curadoria/preview` | `backend/app/routers/google_drive_knowledge.py:92` |
| POST | `/deep-research/juridica` | `backend/app/routers/peca_geracao.py:401` |
| POST | `/demonstrativo` | `backend/app/routers/peca_geracao.py:448` |
| POST | `/detectar-prazos` | `backend/app/routers/ai.py:932` |
| POST | `/distribuicao/{dist_id}/aprovar` | `backend/app/routers/gestao_societaria.py:234` |
| POST | `/distribuicao` | `backend/app/routers/gestao_societaria.py:131` |
| POST | `/docs/{doc_id}/revisar` | `backend/app/routers/rag_governance.py:176` |
| POST | `/docs/{doc_id}/testar` | `backend/app/routers/rag_governance.py:225` |
| POST | `/documento-unico` | `backend/app/routers/provas.py:604` |
| POST | `/docx` | `backend/app/routers/export.py:151` |
| POST | `/dossie-pressao` | `backend/app/routers/diplomacia_v3.py:57` |
| POST | `/drive/upload` | `backend/app/routers/documents.py:878` |
| POST | `/due-diligence/template` | `backend/app/routers/sociedades_cliente.py:156` |
| POST | `/due-diligence/templates` | `backend/app/routers/novos_modulos.py:284` |
| POST | `/emitir` | `backend/app/routers/nfse.py:557` |
| POST | `/empresarial` | `backend/app/routers/ramos.py:421` |
| POST | `/entrevista` | `backend/app/routers/triagem_entrevista.py:151` |
| POST | `/estimar` | `backend/app/routers/honorarios_oab.py:88` |
| POST | `/etiquetas` | `backend/app/routers/etiquetas.py:37` |
| POST | `/evolution` | `backend/app/routers/evolution_webhook.py:67` |
| POST | `/executar` | `backend/app/routers/ai_tools.py:73` |
| POST | `/executar` | `backend/app/routers/backup_admin.py:28` |
| POST | `/execute-doc` | `backend/app/routers/ai_skills.py:309` |
| POST | `/execute` | `backend/app/routers/ai_skills.py:269` |
| POST | `/ext/ingerir/datajud` | `backend/app/routers/jurimetria_extra.py:173` |
| POST | `/ext/predicao/treinar` | `backend/app/routers/jurimetria_extra.py:168` |
| POST | `/faq` | `backend/app/routers/conteudo.py:60` |
| POST | `/fontes/tjmg/coletar` | `backend/app/routers/ia_governanca.py:489` |
| POST | `/frontend-error` | `backend/app/routers/observabilidade.py:27` |
| POST | `/gateway/health` | `backend/app/routers/ai.py:431` |
| POST | `/generate` | `backend/app/routers/ai_core.py:157` |
| POST | `/generate` | `backend/app/routers/peca_geracao_router.py:27` |
| POST | `/gerar-minuta` | `backend/app/routers/ia_extra.py:151` |
| POST | `/gerar` | `backend/app/routers/anexos.py:108` |
| POST | `/gerar` | `backend/app/routers/peca_geracao.py:102` |
| POST | `/glossario` | `backend/app/routers/conteudo.py:79` |
| POST | `/importar-env` | `backend/app/routers/credential_vault.py:291` |
| POST | `/importar-lote` | `backend/app/routers/jurisprudencia_externa.py:152` |
| POST | `/importar` | `backend/app/routers/jurisprudencia_externa.py:82` |
| POST | `/inadimplencia/varrer` | `backend/app/routers/novos_modulos.py:108` |
| POST | `/ingerir-ai-log/{log_id}` | `backend/app/routers/rag.py:597` |
| POST | `/ingest-pdf` | `backend/app/routers/rag.py:173` |
| POST | `/ingest-url` | `backend/app/routers/rag.py:220` |
| POST | `/ingest` | `backend/app/routers/rag.py:323` |
| POST | `/instanciar` | `backend/app/routers/checklists.py:199` |
| POST | `/itens/{item_id}/encerrar-vigencia` | `backend/app/routers/honorarios_oab.py:268` |
| POST | `/itens` | `backend/app/routers/honorarios_oab.py:214` |
| POST | `/jurisprudencia-mg/extrair-url` | `backend/app/routers/ia_governanca.py:623` |
| POST | `/jurisprudencia-mg` | `backend/app/routers/ia_governanca.py:560` |
| POST | `/jurisprudencia/pesquisa` | `backend/app/routers/cerebro.py:70` |
| POST | `/keywords` | `backend/app/routers/diario_oficial.py:64` |
| POST | `/ler-todas` | `backend/app/routers/notifications.py:139` |
| POST | `/login` | `backend/app/routers/auth.py:177` |
| POST | `/logout` | `backend/app/routers/auth.py:513` |
| POST | `/logs/{log_id}/feedback` | `backend/app/routers/ai.py:242` |
| POST | `/manual` | `backend/app/routers/nfse.py:390` |
| POST | `/me/avatar` | `backend/app/routers/users.py:470` |
| POST | `/me/sessions/revoke-others` | `backend/app/routers/users.py:152` |
| POST | `/me/sessions/{session_id}/revoke` | `backend/app/routers/users.py:189` |
| POST | `/messages` | `backend/app/routers/whatsapp.py:132` |
| POST | `/motor` | `backend/app/routers/teses.py:488` |
| POST | `/pacote` | `backend/app/routers/defesas_revisoes_pacote_seguro.py:175` |
| POST | `/parecer-pdf` | `backend/app/routers/previdenciario_beneficio.py:204` |
| POST | `/peca-conversao` | `backend/app/routers/ambiental_estrategia.py:213` |
| POST | `/penal` | `backend/app/routers/ramos.py:908` |
| POST | `/persistir` | `backend/app/routers/defesas_revisoes_avancado.py:349` |
| POST | `/pesquisar` | `backend/app/routers/ia_extra.py:197` |
| POST | `/planilha-pdf` | `backend/app/routers/trabalhista_liquidacao.py:311` |
| POST | `/pre-preencher` | `backend/app/routers/ficha_triagem.py:96` |
| POST | `/precificacao/regras` | `backend/app/routers/novos_modulos.py:77` |
| POST | `/predicao-exito` | `backend/app/routers/jurimetria.py:265` |
| POST | `/preencher-minimo` | `backend/app/routers/module_help.py:74` |
| POST | `/preparar-audiencia` | `backend/app/routers/ai.py:413` |
| POST | `/prescricao` | `backend/app/routers/calculadoras.py:141` |
| POST | `/preview` | `backend/app/routers/anexos.py:75` |
| POST | `/processar` | `backend/app/routers/entrada_universal.py:185` |
| POST | `/processes/{pid}/arquivar` | `backend/app/routers/processes.py:134` |
| POST | `/processes/{pid}/desarquivar` | `backend/app/routers/processes.py:168` |
| POST | `/processes/{pid}/principal` | `backend/app/routers/processes.py:108` |
| POST | `/propostas/{proposta_id}/aprovar` | `backend/app/routers/honorarios_oab.py:427` |
| POST | `/propostas/{proposta_id}/rejeitar` | `backend/app/routers/honorarios_oab.py:442` |
| POST | `/push/subscribe` | `backend/app/routers/notifications.py:229` |
| POST | `/razoes` | `backend/app/routers/anexos.py:131` |
| POST | `/recalcular` | `backend/app/routers/indice_risco.py:48` |
| POST | `/recuperar-senha` | `backend/app/routers/auth.py:631` |
| POST | `/redefinir-senha` | `backend/app/routers/auth.py:659` |
| POST | `/refresh` | `backend/app/routers/auth.py:343` |
| POST | `/reindex/{file_id}` | `backend/app/routers/google_drive_knowledge.py:181` |
| POST | `/relatorio-pdf` | `backend/app/routers/tributario_fiscal.py:302` |
| POST | `/report` | `backend/app/routers/ai_core.py:173` |
| POST | `/resolver` | `backend/app/routers/clients.py:126` |
| POST | `/resumir-documento` | `backend/app/routers/ai.py:104` |
| POST | `/resumir-texto` | `backend/app/routers/ia_extra.py:114` |
| POST | `/seed` | `backend/app/routers/rag.py:485` |
| POST | `/send` | `backend/app/routers/whatsapp.py:86` |
| POST | `/simular-adversario` | `backend/app/routers/qualidade.py:90` |
| POST | `/simular` | `backend/app/routers/ambiental_estrategia.py:90` |
| POST | `/simular` | `backend/app/routers/suspensoes.py:141` |
| POST | `/socios` | `backend/app/routers/gestao_societaria.py:90` |
| POST | `/solicitacoes-documentos/itens/{item_id}/upload` | `backend/app/routers/portal_documentos.py:121` |
| POST | `/sugerir-faltantes` | `backend/app/routers/provas.py:380` |
| POST | `/sugerir-ia` | `backend/app/routers/teses.py:364` |
| POST | `/sugerir-tipo` | `backend/app/routers/documents.py:242` |
| POST | `/sugestao-honorarios` | `backend/app/routers/ia_extra.py:255` |
| POST | `/sumulas/ingerir-seed` | `backend/app/routers/sumulas.py:28` |
| POST | `/sync` | `backend/app/routers/google_drive_knowledge.py:156` |
| POST | `/task` | `backend/app/routers/ai_core.py:123` |
| POST | `/templates` | `backend/app/routers/checklists.py:148` |
| POST | `/templates` | `backend/app/routers/workflow.py:140` |
| POST | `/teses-ocultas` | `backend/app/routers/ai.py:345` |
| POST | `/teses/sincronizar` | `backend/app/routers/curadoria_renomada.py:39` |
| POST | `/teses/{tese_id}/aprovar` | `backend/app/routers/matriz_teses.py:109` |
| POST | `/teses/{tese_id}/descartar` | `backend/app/routers/matriz_teses.py:121` |
| POST | `/testes-juridicos` | `backend/app/routers/rag_governance.py:256` |
| POST | `/totp/desativar` | `backend/app/routers/auth.py:802` |
| POST | `/totp/setup` | `backend/app/routers/auth.py:681` |
| POST | `/totp/verificar` | `backend/app/routers/auth.py:727` |
| POST | `/trabalhista-esp` | `backend/app/routers/ramos.py:1122` |
| POST | `/trabalhista/rescisao` | `backend/app/routers/calculadoras.py:65` |
| POST | `/traduzir-andamento` | `backend/app/routers/ia_extra.py:82` |
| POST | `/transcribe-media` | `backend/app/routers/ai_skills.py:460` |
| POST | `/upload` | `backend/app/routers/bank_analysis.py:38` |
| POST | `/upload` | `backend/app/routers/documents.py:305` |
| POST | `/validar-citacoes` | `backend/app/routers/ia_citacoes.py:28` |
| POST | `/validar` | `backend/app/routers/validador_juridico.py:50` |
| POST | `/veredito_ia/analisar` | `backend/app/routers/veredito_ia_router.py:15` |
| POST | `/verificar-citacoes` | `backend/app/routers/qualidade.py:67` |
| POST | `/verificar-conflito` | `backend/app/routers/clients.py:196` |
| POST | `/viabilidade` | `backend/app/routers/defesas_revisoes_avancado.py:256` |
| POST | `/victory_vault/modelos` | `backend/app/routers/victory_vault_router.py:18` |
| POST | `/victory_vault/teses` | `backend/app/routers/victory_vault_router.py:10` |
| POST | `/{analise_id}/arquivar` | `backend/app/routers/raio_x.py:703` |
| POST | `/{analise_id}/converter` | `backend/app/routers/raio_x.py:686` |
| POST | `/{analise_id}/descartar` | `backend/app/routers/raio_x.py:719` |
| POST | `/{analise_id}/reanalisar` | `backend/app/routers/raio_x.py:525` |
| POST | `/{analysis_id}/documento` | `backend/app/routers/bank_analysis.py:187` |
| POST | `/{analysis_id}/gerar-peca` | `backend/app/routers/bank_analysis.py:266` |
| POST | `/{batch_id}/preparar-pacote` | `backend/app/routers/entrada_universal.py:317` |
| POST | `/{batch_id}/vincular-caso` | `backend/app/routers/entrada_universal_vinculo.py:95` |
| POST | `/{case_id}/analisar` | `backend/app/routers/cases.py:1357` |
| POST | `/{case_id}/aplicar-extracao` | `backend/app/routers/cases.py:1026` |
| POST | `/{case_id}/arquivar` | `backend/app/routers/cases.py:498` |
| POST | `/{case_id}/assistente-estrategico` | `backend/app/routers/cases.py:763` |
| POST | `/{case_id}/desarquivar` | `backend/app/routers/cases.py:536` |
| POST | `/{case_id}/encerrar` | `backend/app/routers/cases.py:873` |
| POST | `/{case_id}/gerar-documentos` | `backend/app/routers/cases.py:673` |
| POST | `/{case_id}/gerar` | `backend/app/routers/dossie_estrategico.py:64` |
| POST | `/{case_id}/movimentos/{mov_id}/traduzir` | `backend/app/routers/cases.py:964` |
| POST | `/{case_id}/movimentos` | `backend/app/routers/cases.py:737` |
| POST | `/{case_id}/sincronizar-processo` | `backend/app/routers/cases.py:829` |
| POST | `/{checklist_id}/itens` | `backend/app/routers/checklists.py:422` |
| POST | `/{client_id}/criar-acesso` | `backend/app/routers/clients.py:706` |
| POST | `/{client_id}/esquecimento` | `backend/app/routers/clients.py:914` |
| POST | `/{client_id}/ia-analise` | `backend/app/routers/clients.py:546` |
| POST | `/{client_id}/pending-items` | `backend/app/routers/pending_items.py:53` |
| POST | `/{client_id}/ripd` | `backend/app/routers/lgpd_registros.py:374` |
| POST | `/{com_id}/aceitar-prazo` | `backend/app/routers/intimacoes.py:338` |
| POST | `/{com_id}/processar` | `backend/app/routers/intimacoes.py:279` |
| POST | `/{com_id}/recusar-prazo` | `backend/app/routers/intimacoes.py:457` |
| POST | `/{com_id}/sugerir-prazo` | `backend/app/routers/intimacoes.py:299` |
| POST | `/{contrato_id}/transicao` | `backend/app/routers/contratos_societarios.py:301` |
| POST | `/{deadline_id}/ciencia` | `backend/app/routers/deadlines.py:314` |
| POST | `/{doc_id}/classificar` | `backend/app/routers/documents.py:813` |
| POST | `/{doc_id}/revisar` | `backend/app/routers/legal_docs.py:498` |
| POST | `/{doc_id}/validar` | `backend/app/routers/legal_docs.py:383` |
| POST | `/{entidade}/{registro_id}/restaurar` | `backend/app/routers/trash.py:62` |
| POST | `/{fee_id}/pagamentos` | `backend/app/routers/fees.py:225` |
| POST | `/{fee_id}/rateio` | `backend/app/routers/exito_rateio.py:106` |
| POST | `/{juri_id}/classificar-ia` | `backend/app/routers/jurisprudencia_interna.py:195` |
| POST | `/{key_id}/revogar` | `backend/app/routers/api_keys.py:94` |
| POST | `/{nota_id}/cancelar` | `backend/app/routers/nfse.py:809` |
| POST | `/{notif_id}/ler` | `backend/app/routers/notifications.py:122` |
| POST | `/{perfil}` | `backend/app/routers/ia_especializada.py:55` |
| POST | `/{proc_id}/minuta` | `backend/app/routers/procuracoes.py:103` |
| POST | `/{proc_id}/revogar` | `backend/app/routers/procuracoes.py:160` |
| POST | `/{prompt_id}/executar` | `backend/app/routers/prompts.py:58` |
| POST | `/{prompt_id}/executar` | `backend/app/routers/prompts_juridicos.py:227` |
| POST | `/{provider_key}/testar` | `backend/app/routers/credential_vault.py:314` |
| POST | `/{provider_key}/{field_key}` | `backend/app/routers/credential_vault.py:341` |
| POST | `/{room_id}/arquivos` | `backend/app/routers/data_room.py:378` |
| POST | `/{room_id}/links` | `backend/app/routers/data_room.py:466` |
| POST | `/{session_id}/saida` | `backend/app/routers/legal_chat.py:421` |
| POST | `/{sig_id}/assinar` | `backend/app/routers/signatures.py:191` |
| POST | `/{sociedade_id}/eventos` | `backend/app/routers/sociedades_cliente.py:452` |
| POST | `/{sociedade_id}/socios` | `backend/app/routers/sociedades_cliente.py:356` |
| POST | `/{tese_id}/vincular-caso` | `backend/app/routers/teses.py:328` |
| POST | `/{tpl_id}/gerar` | `backend/app/routers/templates.py:121` |
| PUT | `/preferences` | `backend/app/routers/notifications.py:86` |

## 2. Registro de routers em main.py

```
304:app.include_router(agenda_eventos.router, prefix=API)
305:app.include_router(ai.router, prefix=API)
306:app.include_router(ai_core.router, prefix=API)
307:app.include_router(anexos.router, prefix=API)
308:app.include_router(ai_skills.router, prefix=API)
309:app.include_router(ai_tools.router, prefix=API)
310:app.include_router(analise_bancaria.router, prefix=API)
311:app.include_router(analytics.router, prefix=API)
312:app.include_router(andamentos.router, prefix=API)
313:app.include_router(areas.router, prefix=API)
314:app.include_router(atendimentos.router, prefix=API)
315:app.include_router(atividades.router, prefix=API)
316:app.include_router(audit.router, prefix=API)
317:app.include_router(auth.router, prefix=API)
318:app.include_router(backup_admin.router, prefix=API)
319:app.include_router(bank_analysis.router, prefix=API)
320:app.include_router(calculadoras.router, prefix=API)
321:app.include_router(calendar_feed.router, prefix=API)
322:app.include_router(case_intelligence.router, prefix=API)
323:app.include_router(case_partes.router, prefix=API)
324:app.include_router(cases.router, prefix=API)
325:app.include_router(caso_areas.router, prefix=API)
326:app.include_router(centro_custos.router, prefix=API)
327:app.include_router(cerebro.router, prefix=API)
328:app.include_router(checklists.router, prefix=API)
329:app.include_router(clients.router, prefix=API)
330:app.include_router(compliance.router, prefix=API)
331:app.include_router(consumidor_monitor.router, prefix=API)
332:app.include_router(conteudo.router, prefix=API)
333:app.include_router(contratos_societarios.router, prefix=API)
334:app.include_router(conversao_caso.router, prefix=API)
335:app.include_router(credential_vault.router, prefix=API)  # cofre de credenciais (superadmin)
336:app.include_router(curadoria_renomada.router, prefix=API)
337:app.include_router(dashboard.router, prefix=API)
338:app.include_router(data_room.router, prefix=API)
339:app.include_router(data_room_v4.router, prefix=API)
340:app.include_router(datajud.router, prefix=API)
341:app.include_router(deadlines.router, prefix=API)
342:app.include_router(despesas.router, prefix=API)
343:app.include_router(diario_oficial.router, prefix=API)
344:app.include_router(diplomacia_v3.router, prefix=API)
345:app.include_router(documento_ia.router, prefix=API)
346:app.include_router(raio_x.router, prefix=API)
347:app.include_router(legal_chat.router, prefix=API)
348:app.include_router(documents.router, prefix=API)
349:app.include_router(dossie_cliente.router, prefix=API)
350:app.include_router(dossie_estrategico.router, prefix=API)
351:app.include_router(environmental.router, prefix=API)
352:app.include_router(etiquetas.router, prefix=API)
353:app.include_router(evolution_webhook.router, prefix=API)
354:app.include_router(exito_rateio.router, prefix=API)
355:app.include_router(export.router, prefix=API)
356:app.include_router(extratos.router, prefix=API)
357:app.include_router(fees.router, prefix=API)
358:app.include_router(financeiro_consolidado.router, prefix=API)
359:app.include_router(gestao_societaria.router, prefix=API)
360:app.include_router(google_drive_knowledge.router, prefix=API)  # /api/rag/google-drive/* (curadoria da base, piso admin/socio)
361:app.include_router(honorarios_calc.router, prefix=API)
362:app.include_router(ia_adversarial.router, prefix=API)
363:app.include_router(ia_agente.router, prefix=API)
364:app.include_router(ia_citacoes.router, prefix=API)
365:app.include_router(ia_defensiva.router, prefix=API)
366:app.include_router(ia_especializada.router, prefix=API)
367:app.include_router(ia_extra.router, prefix=API)  # Bloco 1 (Etapa 4): router antes não montado → 8 chamadas frontend em 404
368:app.include_router(ia_governanca.router, prefix=API)
369:app.include_router(ia_saude.router, prefix=API)
370:app.include_router(ia_saude.router_status, prefix=API)  # GET /api/ia/status
371:app.include_router(indice_risco.router, prefix=API)
372:app.include_router(indices.router, prefix=API)  # Índices oficiais BCB (SGS + Olinda) — Bloco 1 das APIs públicas
373:app.include_router(infosimples_receita.router, prefix=API)
374:app.include_router(infosimples_tjmg.router, prefix=API)
375:app.include_router(car.router, prefix=API)  # CAR/SICAR via Infosimples (consulta paga, reuso do conector)
376:app.include_router(transparencia.router, prefix=API)  # CGU sanções CEIS/CNEP/CEPIM — GATED (default off)
378:app.include_router(nfse.router, prefix=API)  # NFS-e (emissão fiscal GATED, homologação) — migração 085
379:app.include_router(intelligence_v3.router, prefix=API)
380:app.include_router(intimacoes.router, prefix=API)
381:app.include_router(jurimetria.router, prefix=API)
382:app.include_router(jurimetria_extra.router, prefix=API)  # A5: router antes órfão (404 silencioso)
383:app.include_router(juris_import.router, prefix=API)
384:app.include_router(jurisprudencia_externa.router, prefix=API)
385:app.include_router(jurisprudencia_interna.router, prefix=API)
386:app.include_router(kanban.router, prefix=API)
387:app.include_router(kit_documental.router, prefix=API)  # POST /api/cases/{id}/kit-documental (P0.3)
388:app.include_router(legal_docs.router, prefix=API)
389:app.include_router(matriz_teses.router, prefix=API)  # FASE 3 Orquestrador — Matriz de Teses (migração 102)
390:app.include_router(orquestrador.router, prefix=API)  # FASE 5 Orquestrador — máquina de estados do caso
391:app.include_router(memoria_institucional.router, prefix=API)
392:app.include_router(honorarios_oab.router, prefix=API)  # frontend: /api/honorarios-oab/estimar (EstimadorHonorarios)
393:app.include_router(intake.router, prefix=API)  # frontend: /api/intake/casos/{id}/analise-completa (IntakeAnalise)
394:app.include_router(triagem_entrevista.router, prefix=API)  # frontend: /api/triagem/entrevista (EntrevistaInteligente — Jornada etapa 2)
395:app.include_router(ficha_triagem.router, prefix=API)  # frontend: /api/triagem/ficha (Ficha de Triagem pré-peça — gate de geração)
396:app.include_router(mensagens.router, prefix=API)
397:app.include_router(module_help.router, prefix=API)  # frontend: /api/module-help/* (HelpButton)
398:app.include_router(motor_peca.router, prefix=API)  # P1: Motor de Peça — /api/cases/{id}/motor-peca/*
399:app.include_router(movimentos.router, prefix=API)
400:app.include_router(noticias.router, prefix=API)
401:app.include_router(notifications.router, prefix=API)
402:app.include_router(novos_modulos.router, prefix=API)
403:app.include_router(observabilidade.router, prefix=API)
404:app.include_router(office_contracts.router, prefix=API)
405:app.include_router(partner_withdrawals.router, prefix=API)
406:app.include_router(peca_geracao.router, prefix=API)
407:app.include_router(peca_geracao_router.router, prefix=API)
408:app.include_router(pending_items.router, prefix=API)
409:app.include_router(pix.router, prefix=API)
410:app.include_router(portal.router, prefix=API)
411:app.include_router(portal_documentos.router, prefix=API)  # Portal: solicitações de documentos + upload (migration 084)
412:app.include_router(solicitacoes_documentos.router, prefix=API)  # advogado: solicitação de documentos ao cliente (migration 084)
413:app.include_router(processes.router, prefix=API)
414:app.include_router(procuracoes.router, prefix=API)
415:app.include_router(produtividade.router, prefix=API)
416:app.include_router(prompts.router, prefix=API)
417:app.include_router(prompts_juridicos.router, prefix=API)
418:app.include_router(qualidade.router, prefix=API)
419:app.include_router(rag.router, prefix=API)
420:app.include_router(rag_public.router, prefix=API)      # API pública (X-API-Key)
429:app.include_router(                       # antes: jurisprudencia_externa.include_router(...)
431:app.include_router(                       # antes: peca_geracao.include_router(...)
433:app.include_router(                       # antes: append em rag.router.routes (prefixo absoluto)
435:app.include_router(                       # antes: andamentos.include_router(...)
437:app.include_router(                       # antes: append em ia_governanca.router.routes
439:app.include_router(api_keys_router.router, prefix=API) # admin de chaves (JWT admin)
440:app.include_router(regulatorio.router, prefix=API)
441:app.include_router(radar_legislativo.router, prefix=API)  # Câmara+Senado+ALMG
442:app.include_router(ramos.router, prefix=API)
443:app.include_router(previdenciario_beneficio.router, prefix=API)  # vertical Previdenciário — regras de transição EC 103/2019 + RMI
444:app.include_router(relatorio.router, prefix=API)
445:app.include_router(relatorio_cliente.router, prefix=API)
446:app.include_router(score_juridico.router, prefix=API)
447:app.include_router(search.router, prefix=API)
448:app.include_router(signatures.router, prefix=API)
449:app.include_router(sociedades_cliente.router, prefix=API)  # gestão societária de CLIENTES (vertical Empresarial)
450:app.include_router(provas.router, prefix=API)  # Gestão de Provas por caso + Documento Único de Anexos (Visual Law)
451:app.include_router(jornada_caso.router, prefix=API)  # Jornada do Caso — estado determinístico das 9 etapas (sem IA)
452:app.include_router(lgpd_registros.router, prefix=API)  # vertical LGPD — ROPA (art. 37) por cliente + RIPD (art. 38)
453:app.include_router(sumulas.router, prefix=API)
454:app.include_router(suspensoes.router, prefix=API)
455:app.include_router(system_modules.router, prefix=API)  # Mapa de Módulos — governança modular
456:app.include_router(diagnostico.router, prefix=API)  # Central Eletrônica de Diagnóstico
457:app.include_router(module_settings.router, prefix=API)  # Lifecycle auditável dos módulos
458:app.include_router(tributario_fiscal.router, prefix=API)  # vertical Tributário — XML fiscal + recuperação de créditos
459:app.include_router(trabalhista_liquidacao.router, prefix=API)  # vertical Trabalhista — liquidação de sentença (ADC 58 / Selic real BCB)
460:app.include_router(ambiental_estrategia.router, prefix=API)  # vertical Ambiental — simulador de estratégia do auto de infração
461:app.include_router(tasks.router, prefix=API)
462:app.include_router(templates.router, prefix=API)
463:app.include_router(teses.router, prefix=API)
464:app.include_router(teses_v4.router, prefix=API)
465:app.include_router(timesheet.router, prefix=API)
466:app.include_router(trash.router, prefix=API)
467:app.include_router(users.router, prefix=API)
468:app.include_router(utils.router, prefix=API)
469:app.include_router(validador_juridico.router, prefix=API)
470:app.include_router(veredito_ia_router.router, prefix=API)
471:app.include_router(victory_vault_router.router, prefix=API)
472:app.include_router(visual_law.router, prefix=API)
473:app.include_router(whatsapp.router, prefix=API)
474:app.include_router(workflow.router, prefix=API)
475:app.include_router(architecture.router, prefix=API)
478:app.include_router(integracoes.datajud_router, prefix=API)
479:app.include_router(integracoes.djen_router, prefix=API)
480:app.include_router(integracoes.brasilapi_router, prefix=API)
```

> Todos os routers do EJC sao registrados manualmente em `backend/app/main.py`
> sob o prefixo `API = "/api"`. Router nao registrado la nao existe em runtime.

## 3. Chamadas de API no frontend

| Caminho chamado | Arquivo |
|---|---|
| `/api/agenda-eventos/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1096` |
| `/api/agenda-eventos/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1263` |
| `/api/agenda-eventos/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1326` |
| `/api/agenda-eventos/` | `frontend/src/components/ContextualAIAssistant.tsx:272` |
| `/api/agenda-eventos/` | `frontend/src/pages/CentralAtividades.tsx:973` |
| `/api/agenda-eventos` | `frontend/src/config/moduleRegistry.tsx:415` |
| `/api/ai/analisar-caso` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:439` |
| `/api/ai/analisar-caso` | `frontend/src/pages/IA.tsx:98` |
| `/api/ai/analisar-contrato` | `frontend/src/pages/CasoDetalhe/TabFerramentas.tsx:231` |
| `/api/ai/analisar-contrato` | `frontend/src/pages/CasoDetalhe/TabFerramentas.tsx:254` |
| `/api/ai/auditar-peca` | `frontend/src/pages/Pecas.tsx:546` |
| `/api/ai/core` | `frontend/src/config/moduleRegistry.tsx:578` |
| `/api/ai/dossie/${caseId}` | `frontend/src/pages/IA.tsx:83` |
| `/api/ai/gerar-minuta` | `frontend/src/pages/AssistenteIA.tsx:85` |
| `/api/ai/gerar-minuta` | `frontend/src/pages/ramos/RamoBase.tsx:791` |
| `/api/ai/logs/${id}/hitl` | `frontend/src/pages/IA.tsx:157` |
| `/api/ai/logs/${result.ai_log_id}/feedback` | `frontend/src/components/ContextualAIAssistant.tsx:290` |
| `/api/ai/logs/${result.ai_log_id}/hitl` | `frontend/src/components/ContextualAIAssistant.tsx:226` |
| `/api/ai/logs` | `frontend/src/pages/IA.tsx:58` |
| `/api/ai/pesquisar` | `frontend/src/pages/AssistenteIA.tsx:75` |
| `/api/ai/resumir-documento` | `frontend/src/pages/IA.tsx:119` |
| `/api/ai/resumir-texto` | `frontend/src/components/NoticiasCard.tsx:115` |
| `/api/ai/resumir-texto` | `frontend/src/pages/AssistenteIA.tsx:77` |
| `/api/ai/skills/execute-doc` | `frontend/src/components/ContextualAIAssistant.tsx:197` |
| `/api/ai/skills/execute-doc` | `frontend/src/pages/FerramentasIA.tsx:261` |
| `/api/ai/skills/execute` | `frontend/src/components/ContextualAIAssistant.tsx:199` |
| `/api/ai/skills/execute` | `frontend/src/pages/FerramentasIA.tsx:264` |
| `/api/ai/skills/execute` | `frontend/src/pages/RaioXProcesso.tsx:671` |
| `/api/ai/skills/transcribe-media` | `frontend/src/pages/FerramentasIA.tsx:259` |
| `/api/ai/skills` | `frontend/src/config/moduleRegistry.tsx:302` |
| `/api/ai/skills` | `frontend/src/config/moduleRegistry.tsx:578` |
| `/api/ai/sugestao-honorarios` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:419` |
| `/api/ai/traduzir-andamento` | `frontend/src/pages/AssistenteIA.tsx:79` |
| `/api/ai` | `frontend/src/config/moduleRegistry.tsx:282` |
| `/api/ai` | `frontend/src/config/moduleRegistry.tsx:578` |
| `/api/ambiental/estrategia/peca-conversao` | `frontend/src/components/AmbientalEstrategia.tsx:255` |
| `/api/analise-bancaria/abusividade` | `frontend/src/components/RevisaoBancariaDeterministica.tsx:69` |
| `/api/analise-bancaria/cet` | `frontend/src/components/RevisaoBancariaDeterministica.tsx:110` |
| `/api/analise-bancaria/contrato` | `frontend/src/pages/ramos/RamoBase.tsx:739` |
| `/api/analise-bancaria/taxa-media` | `frontend/src/pages/ramos/RamoBase.tsx:599` |
| `/api/analytics/case-health` | `frontend/src/pages/DashboardModern.tsx:224` |
| `/api/analytics/funil` | `frontend/src/pages/CentralRelacionamento.tsx:124` |
| `/api/analytics` | `frontend/src/config/moduleRegistry.tsx:416` |
| `/api/atendimentos/${followUp.id}` | `frontend/src/pages/DossieCliente.tsx:537` |
| `/api/atendimentos/${item.id}` | `frontend/src/components/ClientServiceTimeline.tsx:400` |
| `/api/atendimentos/${item.id}` | `frontend/src/components/ClientServiceTimeline.tsx:425` |
| `/api/atendimentos/responsaveis` | `frontend/src/pages/DossieCliente.tsx:980` |
| `/api/atendimentos/solicitacoes-resumo` | `frontend/src/pages/DashboardModern.tsx:220` |
| `/api/atendimentos` | `frontend/src/components/ClientServiceTimeline.tsx:368` |
| `/api/atendimentos` | `frontend/src/pages/DossieCliente.tsx:959` |
| `/api/atividades` | `frontend/src/config/moduleRegistry.tsx:414` |
| `/api/atividades` | `frontend/src/pages/CentralAtividades.tsx:972` |
| `/api/audit` | `frontend/src/config/moduleRegistry.tsx:763` |
| `/api/auth/alterar-senha` | `frontend/src/pages/TrocarSenha.tsx:33` |
| `/api/auth/logout` | `frontend/src/lib/api.ts:424` |
| `/api/auth/recuperar-senha` | `frontend/src/pages/RecuperarSenha.tsx:10` |
| `/api/auth/redefinir-senha` | `frontend/src/pages/RedefinirSenha.tsx:26` |
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
| `/api/cases/${caseId}/areas/${area.area}` | `frontend/src/components/CaseCommandDock.tsx:115` |
| `/api/cases/${caseId}/areas` | `frontend/src/components/CaseCommandDock.tsx:68` |
| `/api/cases/${caseId}/areas` | `frontend/src/components/CaseCommandDock.tsx:93` |
| `/api/cases/${caseId}/converter-judicial` | `frontend/src/components/ConversaoChecklist.tsx:89` |
| `/api/cases/${caseId}/etiquetas/${id}` | `frontend/src/pages/CasoDetalhe.tsx:663` |
| `/api/cases/${caseId}/etiquetas` | `frontend/src/pages/CasoDetalhe.tsx:657` |
| `/api/cases/${caseId}/etiquetas` | `frontend/src/pages/CasoDetalhe.tsx:674` |
| `/api/cases/${caseId}/indice-risco/recalcular` | `frontend/src/pages/CasoDetalhe/TabRisco.tsx:58` |
| `/api/cases/${caseId}/mensagens` | `frontend/src/pages/CasoDetalhe.tsx:565` |
| `/api/cases/${caseId}/motor-peca/analisar` | `frontend/src/components/DefesasRevisoesPanel.tsx:272` |
| `/api/cases/${caseId}/partes/${id}` | `frontend/src/pages/CasoDetalhe/TabPartes.tsx:51` |
| `/api/cases/${caseId}/partes` | `frontend/src/pages/CasoDetalhe/TabPartes.tsx:40` |
| `/api/cases/${caseId}/processes` | `frontend/src/pages/CasoDetalhe/TabProcessos.tsx:59` |
| `/api/cases/${caseId}/score-juridico/calcular` | `frontend/src/pages/CasoDetalhe/TabScore.tsx:29` |
| `/api/cases/${caso.id}/areas/${a}` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:160` |
| `/api/cases/${caso.id}/areas` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:153` |
| `/api/cases/${caso.id}/arquivar` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:329` |
| `/api/cases/${caso.id}/desarquivar` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:231` |
| `/api/cases/${caso.id}/desarquivar` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:341` |
| `/api/cases/${caso.id}/encerrar` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:389` |
| `/api/cases/${caso.id}/gerar-documentos` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:405` |
| `/api/cases/${caso.id}/movimentos` | `frontend/src/components/ContextualAIAssistant.tsx:248` |
| `/api/cases/${caso.id}/movimentos` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:457` |
| `/api/cases/${caso.id}/sincronizar-processo` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:475` |
| `/api/cases/${caso.id}` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:234` |
| `/api/cases/${caso.id}` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:359` |
| `/api/cases/${casoSel}/movimentos` | `frontend/src/pages/ramos/RamoBase.tsx:773` |
| `/api/cases/${delCaso.id}` | `frontend/src/pages/Casos.tsx:478` |
| `/api/cases/${id}/desarquivar` | `frontend/src/pages/Casos.tsx:455` |
| `/api/cases/${id}` | `frontend/src/stores/caseContext.ts:64` |
| `/api/cases/` | `frontend/src/components/DefesasRevisoesPanel.tsx:163` |
| `/api/cases/` | `frontend/src/components/NovoCasoWizard.tsx:266` |
| `/api/cases/` | `frontend/src/components/__tests__/FlowEnhancements.test.ts:38` |
| `/api/cases/` | `frontend/src/pages/CadastroManual.tsx:530` |
| `/api/cases/` | `frontend/src/pages/Casos.tsx:625` |
| `/api/cases/` | `frontend/src/pages/DashboardModern.tsx:213` |
| `/api/cases/` | `frontend/src/pages/Kanban.tsx:74` |
| `/api/cases/` | `frontend/src/pages/Pecas.tsx:417` |
| `/api/cases/stats` | `frontend/src/components/Dashboards.tsx:373` |
| `/api/cases` | `frontend/src/config/moduleRegistry.tsx:194` |
| `/api/cases` | `frontend/src/config/moduleRegistry.tsx:252` |
| `/api/cases` | `frontend/src/config/moduleRegistry.tsx:318` |
| `/api/cases` | `frontend/src/pages/SalaJuridica.tsx:675` |
| `/api/casos/${caseId}/provas/${atual.id}` | `frontend/src/components/ProvasCaso.tsx:417` |
| `/api/casos/${caseId}/provas/${editId}` | `frontend/src/components/ProvasCaso.tsx:370` |
| `/api/casos/${caseId}/provas/${excluirId}` | `frontend/src/components/ProvasCaso.tsx:397` |
| `/api/casos/${caseId}/provas/${outro.id}` | `frontend/src/components/ProvasCaso.tsx:420` |
| `/api/casos/${caseId}/provas/documento-unico` | `frontend/src/components/ProvasCaso.tsx:436` |
| `/api/casos/${caseId}/provas` | `frontend/src/components/ProvasCaso.tsx:376` |
| `/api/checklists/${ckId}/itens/${itemId}/marcar` | `frontend/src/pages/CasoDetalhe.tsx:320` |
| `/api/checklists/caso/${caseId}/gerar-ia` | `frontend/src/pages/CasoDetalhe.tsx:308` |
| `/api/checklists/templates/${id}` | `frontend/src/pages/Checklists.tsx:60` |
| `/api/checklists/templates` | `frontend/src/pages/Checklists.tsx:41` |
| `/api/checklists` | `frontend/src/config/moduleRegistry.tsx:560` |
| `/api/clients/${clientId}/criar-acesso` | `frontend/src/pages/DossieCliente.tsx:1025` |
| `/api/clients/${clientId}/relatorio-financeiro` | `frontend/src/pages/DossieCliente.tsx:676` |
| `/api/clients/${clientId}` | `frontend/src/pages/DossieCliente.tsx:911` |
| `/api/clients/${clientId}` | `frontend/src/pages/DossieCliente.tsx:979` |
| `/api/clients/${leadId}` | `frontend/src/pages/CRMLeads.tsx:154` |
| `/api/clients/` | `frontend/src/components/NovoCasoWizard.tsx:166` |
| `/api/clients/` | `frontend/src/components/NovoCasoWizard.tsx:208` |
| `/api/clients/` | `frontend/src/pages/CRMLeads.tsx:111` |
| `/api/clients/` | `frontend/src/pages/CRMLeads.tsx:128` |
| `/api/clients/` | `frontend/src/pages/CadastroManual.tsx:421` |
| `/api/clients/` | `frontend/src/pages/CadastroManual.tsx:516` |
| `/api/clients/` | `frontend/src/pages/CentralRelacionamento.tsx:125` |
| `/api/clients/` | `frontend/src/pages/CentralRelacionamento.tsx:126` |
| `/api/clients/` | `frontend/src/pages/Clientes.tsx:130` |
| `/api/clients/resolver` | `frontend/src/pages/Casos.tsx:612` |
| `/api/clients/{client_id}/dossie` | `frontend/src/config/moduleRegistry.tsx:228` |
| `/api/clients` | `frontend/src/config/moduleRegistry.tsx:194` |
| `/api/clients` | `frontend/src/config/moduleRegistry.tsx:209` |
| `/api/clients` | `frontend/src/config/moduleRegistry.tsx:228` |
| `/api/clients` | `frontend/src/config/moduleRegistry.tsx:252` |
| `/api/clients` | `frontend/src/config/moduleRegistry.tsx:417` |
| `/api/clients` | `frontend/src/pages/SalaJuridica.tsx:540` |
| `/api/conhecimento/importar-jurisprudencia` | `frontend/src/pages/Conhecimento.tsx:619` |
| `/api/dashboard/` | `frontend/src/components/Dashboards.tsx:373` |
| `/api/dashboard/` | `frontend/src/pages/DashboardModern.tsx:205` |
| `/api/dashboard` | `frontend/src/config/moduleRegistry.tsx:170` |
| `/api/data-rooms/${aberta.id}/arquivos` | `frontend/src/pages/DataRoom.tsx:80` |
| `/api/data-rooms/${aberta.id}/links` | `frontend/src/pages/DataRoom.tsx:89` |
| `/api/data-rooms/${id}` | `frontend/src/pages/DataRoom.tsx:69` |
| `/api/data-rooms` | `frontend/src/config/moduleRegistry.tsx:496` |
| `/api/data-rooms` | `frontend/src/pages/DataRoom.tsx:62` |
| `/api/deadlines/${id}/ciencia` | `frontend/src/pages/Prazos.tsx:113` |
| `/api/deadlines/${id}` | `frontend/src/pages/Prazos.tsx:109` |
| `/api/deadlines/${item.id}/ciencia` | `frontend/src/pages/CentralAtividades.tsx:1118` |
| `/api/deadlines/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1092` |
| `/api/deadlines/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1259` |
| `/api/deadlines/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1289` |
| `/api/deadlines/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1322` |
| `/api/deadlines/` | `frontend/src/pages/CentralAtividades.tsx:1007` |
| `/api/deadlines/` | `frontend/src/pages/CentralAtividades.tsx:974` |
| `/api/deadlines/` | `frontend/src/pages/DashboardModern.tsx:211` |
| `/api/deadlines/` | `frontend/src/pages/Prazos.tsx:97` |
| `/api/deadlines/calcular` | `frontend/src/pages/Prazos.tsx:65` |
| `/api/deadlines/export.csv` | `frontend/src/pages/CentralAtividades.tsx:1214` |
| `/api/deadlines/export.csv` | `frontend/src/pages/Prazos.tsx:72` |
| `/api/deadlines` | `frontend/src/config/moduleRegistry.tsx:434` |
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
| `/api/diagnostico` | `frontend/src/config/moduleRegistry.tsx:747` |
| `/api/diario-oficial/alertas/${id}/marcar-lido` | `frontend/src/pages/DiarioOficial.tsx:108` |
| `/api/diario-oficial/alertas/nao-lidos/count` | `frontend/src/pages/DiarioOficial.tsx:51` |
| `/api/diario-oficial/alertas` | `frontend/src/pages/DiarioOficial.tsx:72` |
| `/api/diario-oficial/keywords/${id}` | `frontend/src/pages/DiarioOficial.tsx:138` |
| `/api/diario-oficial/keywords` | `frontend/src/pages/DiarioOficial.tsx:127` |
| `/api/diario-oficial/keywords` | `frontend/src/pages/DiarioOficial.tsx:86` |
| `/api/diario-oficial` | `frontend/src/config/moduleRegistry.tsx:623` |
| `/api/diplomacia-v3/analisar-magistrado` | `frontend/src/components/visual/CalculadoraAcordo.tsx:157` |
| `/api/diplomacia-v3/dossie-pressao` | `frontend/src/components/visual/CalculadoraAcordo.tsx:670` |
| `/api/documentos-ia` | `frontend/src/config/moduleRegistry.tsx:302` |
| `/api/documentos-ia` | `frontend/src/config/moduleRegistry.tsx:497` |
| `/api/documents/${d.id}/download` | `frontend/src/pages/Documentos.tsx:367` |
| `/api/documents/${d.id}/download` | `frontend/src/pages/Documentos.tsx:396` |
| `/api/documents/${d.id}` | `frontend/src/pages/Documentos.tsx:466` |
| `/api/documents/${d.id}` | `frontend/src/pages/Documentos.tsx:489` |
| `/api/documents/${d.id}` | `frontend/src/pages/Documentos.tsx:589` |
| `/api/documents/${docId}/download` | `frontend/src/pages/CasoDetalhe.tsx:74` |
| `/api/documents/${docId}/download` | `frontend/src/pages/DossieCliente.tsx:934` |
| `/api/documents/${editDoc.id}` | `frontend/src/pages/Documentos.tsx:564` |
| `/api/documents/upload` | `frontend/src/components/CaseCommandDock.tsx:141` |
| `/api/documents/upload` | `frontend/src/pages/Casos.tsx:231` |
| `/api/documents/upload` | `frontend/src/pages/Documentos.tsx:334` |
| `/api/documents` | `frontend/src/config/moduleRegistry.tsx:495` |
| `/api/dossie/${caseId}/${dossie.id}/aprovar` | `frontend/src/components/DossieEstrategicoCaso.tsx:267` |
| `/api/dossie/${caseId}/${dossie.id}/pdf` | `frontend/src/components/DossieEstrategicoCaso.tsx:284` |
| `/api/dossie/${caseId}/gerar` | `frontend/src/components/DossieEstrategicoCaso.tsx:251` |
| `/api/empresarial/sociedades/${detalhe.id}/eventos` | `frontend/src/components/SociedadesCliente.tsx:315` |
| `/api/empresarial/sociedades/${detalhe.id}/socios` | `frontend/src/components/SociedadesCliente.tsx:276` |
| `/api/empresarial/sociedades/socios/${pendenteExcluir}` | `frontend/src/components/SociedadesCliente.tsx:294` |
| `/api/empresarial/sociedades` | `frontend/src/components/SociedadesCliente.tsx:242` |
| `/api/environmental/` | `frontend/src/components/AmbientalAutos.tsx:99` |
| `/api/etiquetas` | `frontend/src/pages/CasoDetalhe.tsx:672` |
| `/api/extratos/detalhado/${caso.id}` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx:60` |
| `/api/fees/${pagModal.id}/pagamentos` | `frontend/src/pages/Honorarios.tsx:133` |
| `/api/fees/` | `frontend/src/pages/Honorarios.tsx:90` |
| `/api/fees` | `frontend/src/config/moduleRegistry.tsx:685` |
| `/api/financeiro` | `frontend/src/config/moduleRegistry.tsx:684` |
| `/api/health` | `frontend/src/config/moduleRegistry.tsx:170` |
| `/api/honorarios-exito/${fee.id}/rateio` | `frontend/src/pages/Honorarios.tsx:105` |
| `/api/honorarios-exito/${rateioModal.fee.id}/rateio` | `frontend/src/pages/Honorarios.tsx:118` |
| `/api/honorarios-oab/estimar` | `frontend/src/components/EstimadorHonorarios.tsx:53` |
| `/api/ia-defensiva/analisar` | `frontend/src/pages/CasoDetalhe/IaDefensivaCaso.tsx:87` |
| `/api/ia-defensiva/historico/${caso.id}` | `frontend/src/pages/CasoDetalhe/IaDefensivaCaso.tsx:46` |
| `/api/ia-defensiva/historico/${logId}/status` | `frontend/src/pages/CasoDetalhe/IaDefensivaCaso.tsx:61` |
| `/api/ia-especializada/${perfil}` | `frontend/src/pages/AssistenteIA.tsx:81` |
| `/api/ia-governanca/dashboard` | `frontend/src/pages/GovernancaIA.tsx:85` |
| `/api/ia-governanca/fontes` | `frontend/src/pages/GovernancaIA.tsx:88` |
| `/api/ia-governanca/guardrails` | `frontend/src/pages/GovernancaIA.tsx:89` |
| `/api/ia-governanca/jurisprudencia-mg/geometria` | `frontend/src/pages/GovernancaIA.tsx:91` |
| `/api/ia-governanca/jurisprudencia-mg` | `frontend/src/pages/GovernancaIA.tsx:167` |
| `/api/ia-governanca/jurisprudencia-mg` | `frontend/src/pages/GovernancaIA.tsx:90` |
| `/api/ia-governanca/prompts` | `frontend/src/pages/GovernancaIA.tsx:87` |
| `/api/ia-governanca/provedores` | `frontend/src/pages/PainelProvedoresIA.tsx:179` |
| `/api/ia-governanca/rag-curadoria/${doc.id}` | `frontend/src/pages/GovernancaIA.tsx:125` |
| `/api/ia-governanca/rag-curadoria` | `frontend/src/pages/GovernancaIA.tsx:86` |
| `/api/ia-governanca` | `frontend/src/config/moduleRegistry.tsx:732` |
| `/api/ia-saude/dashboard` | `frontend/src/pages/DashboardModern.tsx:217` |
| `/api/ia/agente/stream` | `frontend/src/pages/AgenteIA.tsx:147` |
| `/api/intimacoes/${com.id}/aceitar-prazo` | `frontend/src/pages/Intimacoes.tsx:157` |
| `/api/intimacoes/${com.id}/recusar-prazo` | `frontend/src/pages/Intimacoes.tsx:187` |
| `/api/intimacoes/${id}/processar` | `frontend/src/pages/Intimacoes.tsx:122` |
| `/api/intimacoes/${item.id}/prazo-sugerido` | `frontend/src/pages/CentralAtividades.tsx:1147` |
| `/api/intimacoes/${item.id}/processar` | `frontend/src/pages/CentralAtividades.tsx:1098` |
| `/api/intimacoes/${item.id}/processar` | `frontend/src/pages/CentralAtividades.tsx:1331` |
| `/api/intimacoes/capturar-agora` | `frontend/src/pages/CentralAtividades.tsx:1162` |
| `/api/intimacoes/capturar-agora` | `frontend/src/pages/Intimacoes.tsx:108` |
| `/api/intimacoes` | `frontend/src/config/moduleRegistry.tsx:464` |
| `/api/jurimetria/overview` | `frontend/src/pages/DashboardModern.tsx:209` |
| `/api/jurimetria/overview` | `frontend/src/pages/Jurimetria.tsx:116` |
| `/api/jurimetria/por-area` | `frontend/src/pages/Jurimetria.tsx:117` |
| `/api/jurimetria/por-tese` | `frontend/src/pages/Jurimetria.tsx:119` |
| `/api/jurimetria/por-tribunal` | `frontend/src/pages/Jurimetria.tsx:118` |
| `/api/legal-docs/${aprovacao.doc.id}/aprovar` | `frontend/src/pages/Pecas.tsx:311` |
| `/api/legal-docs/${doc.id}/exportar-docx` | `frontend/src/pages/Pecas.tsx:462` |
| `/api/legal-docs/${doc.id}/pdf` | `frontend/src/pages/Pecas.tsx:446` |
| `/api/legal-docs/${doc.id}/validar` | `frontend/src/pages/Pecas.tsx:176` |
| `/api/legal-docs/${doc.id}` | `frontend/src/pages/Pecas.tsx:332` |
| `/api/legal-docs/${doc.id}` | `frontend/src/pages/Pecas.tsx:356` |
| `/api/legal-docs/${doc.id}` | `frontend/src/pages/Pecas.tsx:509` |
| `/api/legal-docs/${id}` | `frontend/src/pages/Pecas.tsx:277` |
| `/api/legal-docs/${protocolo.doc.id}/protocolo` | `frontend/src/pages/Pecas.tsx:383` |
| `/api/legal-docs/${protocolo.doc.id}` | `frontend/src/pages/Pecas.tsx:394` |
| `/api/legal-docs/${revisao.doc.id}/revisar` | `frontend/src/pages/Pecas.tsx:287` |
| `/api/legal-docs/` | `frontend/src/pages/Pecas.tsx:260` |
| `/api/legal-docs` | `frontend/src/config/moduleRegistry.tsx:514` |
| `/api/lgpd/registros/${clientId}/ripd` | `frontend/src/components/LgpdRegistros.tsx:290` |
| `/api/lgpd/registros/${editId}` | `frontend/src/components/LgpdRegistros.tsx:250` |
| `/api/lgpd/registros/${r.id}` | `frontend/src/components/LgpdRegistros.tsx:275` |
| `/api/lgpd/registros` | `frontend/src/components/LgpdRegistros.tsx:253` |
| `/api/memoria-institucional/${id}` | `frontend/src/pages/CasoDetalhe/TabMemoria.tsx:60` |
| `/api/memoria-institucional` | `frontend/src/pages/CasoDetalhe/TabMemoria.tsx:46` |
| `/api/movimentos/recentes` | `frontend/src/pages/DashboardModern.tsx:212` |
| `/api/nfse/${n.id}/${kind}` | `frontend/src/pages/NotasFiscais.tsx:200` |
| `/api/nfse/manual/${cancelNota.id}/cancelar` | `frontend/src/pages/NotasFiscais.tsx:224` |
| `/api/nfse/manual` | `frontend/src/pages/NotasFiscais.tsx:183` |
| `/api/nfse` | `frontend/src/config/moduleRegistry.tsx:687` |
| `/api/noticias` | `frontend/src/pages/Noticias.tsx:15` |
| `/api/notifications/push/subscribe` | `frontend/src/components/NotificationPreferences.tsx:257` |
| `/api/notifications/push/subscribe` | `frontend/src/components/SecurityMenu.tsx:91` |
| `/api/notifications/push/subscriptions/${deviceId}` | `frontend/src/components/NotificationPreferences.tsx:277` |
| `/api/notifications/push/vapid-key` | `frontend/src/components/NotificationPreferences.tsx:234` |
| `/api/notifications/push/vapid-key` | `frontend/src/components/SecurityMenu.tsx:78` |
| `/api/notifications` | `frontend/src/config/moduleRegistry.tsx:418` |
| `/api/observabilidade/frontend-error` | `frontend/src/components/ErrorBoundary.tsx:39` |
| `/api/ok` | `frontend/src/lib/api.test.ts:79` |
| `/api/pecas/demonstrativo` | `frontend/src/pages/ramos/RamoBase.tsx:153` |
| `/api/pecas/gerar` | `frontend/src/components/PecaGeneratorModal.tsx:595` |
| `/api/pix/cobranca` | `frontend/src/pages/Honorarios.tsx:153` |
| `/api/portal/casos/${caseId}/mensagens` | `frontend/src/pages/portal/PortalCasoDetalhe.tsx:25` |
| `/api/portal/casos/${selectedId}/mensagens` | `frontend/src/pages/portal/PortalMensagens.tsx:59` |
| `/api/portal/casos/${selectedId}/mensagens` | `frontend/src/pages/portal/PortalMensagens.tsx:79` |
| `/api/portal/documentos` | `frontend/src/pages/portal/PortalDocumentos.tsx:74` |
| `/api/portal/financeiro` | `frontend/src/pages/portal/PortalDashboard.tsx:53` |
| `/api/portal/mensagens/nao-lidas` | `frontend/src/pages/portal/PortalDashboard.tsx:57` |
| `/api/portal/meus-casos` | `frontend/src/pages/portal/PortalDashboard.tsx:52` |
| `/api/portal/meus-casos` | `frontend/src/pages/portal/PortalMensagens.tsx:48` |
| `/api/portal/solicitacoes-documentos` | `frontend/src/pages/portal/PortalDashboard.tsx:54` |
| `/api/portal/solicitacoes-documentos` | `frontend/src/pages/portal/PortalDocumentos.tsx:73` |
| `/api/previdenciario/ferramentas/parecer-pdf` | `frontend/src/components/PrevidenciarioSimulacao.tsx:260` |
| `/api/processes/${arqPid}/arquivar` | `frontend/src/pages/CasoDetalhe/TabProcessos.tsx:89` |
| `/api/processes/${pid}/desarquivar` | `frontend/src/pages/CasoDetalhe/TabProcessos.tsx:104` |
| `/api/processes/${pid}` | `frontend/src/pages/CasoDetalhe/TabProcessos.tsx:75` |
| `/api/processes` | `frontend/src/config/moduleRegistry.tsx:318` |
| `/api/prompts-juridicos/${id}` | `frontend/src/pages/Prompts.tsx:74` |
| `/api/prompts-juridicos` | `frontend/src/pages/Prompts.tsx:56` |
| `/api/protegido` | `frontend/src/lib/api.test.ts:50` |
| `/api/protegido` | `frontend/src/lib/api.test.ts:62` |
| `/api/qualquer-endpoint` | `frontend/src/lib/api.test.ts:35` |
| `/api/rag/buscar` | `frontend/src/pages/CasoDetalhe.tsx:442` |
| `/api/rag/buscar` | `frontend/src/pages/Conhecimento.tsx:821` |
| `/api/rag/docs/${id}` | `frontend/src/pages/Conhecimento.tsx:837` |
| `/api/rag/docs` | `frontend/src/components/KnowledgeGovernancePanel.tsx:248` |
| `/api/rag/governanca/cobertura` | `frontend/src/components/KnowledgeGovernancePanel.tsx:247` |
| `/api/rag/governanca/saude` | `frontend/src/components/KnowledgeGovernancePanel.tsx:246` |
| `/api/rag/governanca/testes-juridicos` | `frontend/src/components/KnowledgeGovernancePanel.tsx:393` |
| `/api/rag/ingest-pdf` | `frontend/src/pages/Conhecimento.tsx:376` |
| `/api/rag/ingest-url` | `frontend/src/pages/Conhecimento.tsx:391` |
| `/api/rag/ingest` | `frontend/src/components/NoticiasCard.tsx:133` |
| `/api/rag/ingest` | `frontend/src/pages/Conhecimento.tsx:176` |
| `/api/rag/monitor-legislativo` | `frontend/src/pages/Noticias.tsx:16` |
| `/api/raio-x/${selected.id}/${mode}` | `frontend/src/pages/RaioXProcesso.tsx:819` |
| `/api/raio-x/${selected.id}/converter` | `frontend/src/pages/RaioXProcesso.tsx:783` |
| `/api/raio-x/${selected.id}/exportar` | `frontend/src/pages/RaioXProcesso.tsx:569` |
| `/api/raio-x/` | `frontend/src/pages/RaioXProcesso.tsx:362` |
| `/api/raio-x/stats` | `frontend/src/pages/RaioXProcesso.tsx:363` |
| `/api/raio-x` | `frontend/src/config/moduleRegistry.tsx:302` |
| `/api/relatorio/mensal` | `frontend/src/pages/FinanceiroDashboard.tsx:135` |
| `/api/sala-juridica/${ativa.id}/converter` | `frontend/src/pages/SalaJuridica.tsx:555` |
| `/api/sala-juridica/${ativa.id}/exportar` | `frontend/src/pages/SalaJuridica.tsx:627` |
| `/api/sala-juridica/${ativa.id}/mensagens` | `frontend/src/pages/SalaJuridica.tsx:436` |
| `/api/sala-juridica/${ativa.id}/saida` | `frontend/src/pages/SalaJuridica.tsx:480` |
| `/api/sala-juridica/${ativa.id}` | `frontend/src/pages/SalaJuridica.tsx:379` |
| `/api/sala-juridica/${s.id}` | `frontend/src/pages/SalaJuridica.tsx:474` |
| `/api/sala-juridica/${sessao.id}` | `frontend/src/pages/SalaJuridica.tsx:403` |
| `/api/sala-juridica` | `frontend/src/config/moduleRegistry.tsx:282` |
| `/api/signatures/${id}/assinar` | `frontend/src/pages/Assinaturas.tsx:168` |
| `/api/signatures/${s.id}/assinar` | `frontend/src/pages/portal/PortalAssinaturas.tsx:61` |
| `/api/signatures/` | `frontend/src/pages/Assinaturas.tsx:146` |
| `/api/signatures/` | `frontend/src/pages/Assinaturas.tsx:87` |
| `/api/signatures/` | `frontend/src/pages/portal/PortalDashboard.tsx:55` |
| `/api/signatures` | `frontend/src/config/moduleRegistry.tsx:529` |
| `/api/sociedade/distribuicao` | `frontend/src/pages/Sociedade.tsx:123` |
| `/api/sociedade/distribuicao` | `frontend/src/pages/Sociedade.tsx:178` |
| `/api/sociedade/socios` | `frontend/src/pages/Sociedade.tsx:122` |
| `/api/sociedade/socios` | `frontend/src/pages/Sociedade.tsx:156` |
| `/api/suspensoes/${excluirSuspensao.id}` | `frontend/src/pages/CentralAtividades.tsx:1181` |
| `/api/suspensoes/${id}` | `frontend/src/pages/Suspensoes.tsx:74` |
| `/api/suspensoes/` | `frontend/src/pages/CentralAtividades/acoesLegadas.tsx:250` |
| `/api/suspensoes/` | `frontend/src/pages/Suspensoes.tsx:57` |
| `/api/suspensoes/simular` | `frontend/src/pages/CentralAtividades/acoesLegadas.tsx:369` |
| `/api/suspensoes/simular` | `frontend/src/pages/Suspensoes.tsx:82` |
| `/api/suspensoes` | `frontend/src/config/moduleRegistry.tsx:478` |
| `/api/system-modules/settings/${selectedKey}` | `frontend/src/components/ModuleLifecycleSettings.tsx:177` |
| `/api/system-modules` | `frontend/src/config/moduleRegistry.tsx:779` |
| `/api/tasks/${editTask.id}` | `frontend/src/pages/Tarefas.tsx:114` |
| `/api/tasks/${excluir.id}` | `frontend/src/pages/CentralAtividades.tsx:1196` |
| `/api/tasks/${id}` | `frontend/src/pages/Tarefas.tsx:123` |
| `/api/tasks/${id}` | `frontend/src/pages/Tarefas.tsx:130` |
| `/api/tasks/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1094` |
| `/api/tasks/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1261` |
| `/api/tasks/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1293` |
| `/api/tasks/${item.id}` | `frontend/src/pages/CentralAtividades.tsx:1317` |
| `/api/tasks/` | `frontend/src/pages/Tarefas.tsx:116` |
| `/api/tasks/` | `frontend/src/pages/Tarefas.tsx:73` |
| `/api/tasks` | `frontend/src/config/moduleRegistry.tsx:448` |
| `/api/templates/${tplSel}/gerar` | `frontend/src/pages/Pecas.tsx:435` |
| `/api/templates/` | `frontend/src/pages/Pecas.tsx:416` |
| `/api/templates` | `frontend/src/config/moduleRegistry.tsx:514` |
| `/api/teste/stream` | `frontend/src/lib/stream.test.ts:36` |
| `/api/timesheet` | `frontend/src/pages/CasoDetalhe.tsx:192` |
| `/api/trabalhista/liquidacao/planilha-pdf` | `frontend/src/components/LiquidacaoTrabalhista.tsx:320` |
| `/api/trash/${ent}/${id}/restaurar` | `frontend/src/pages/Lixeira.tsx:36` |
| `/api/trash` | `frontend/src/config/moduleRegistry.tsx:810` |
| `/api/triagem/ficha/pre-preencher` | `frontend/src/components/FichaTriagem.tsx:196` |
| `/api/triagem/ficha` | `frontend/src/components/FichaTriagem.tsx:217` |
| `/api/triagem` | `frontend/src/config/moduleRegistry.tsx:365` |
| `/api/tributario/fiscal/relatorio-pdf` | `frontend/src/components/TributarioFiscal.tsx:221` |
| `/api/users/${u.id}` | `frontend/src/pages/Usuarios.tsx:63` |
| `/api/users/${user.id}` | `frontend/src/components/SecurityMenu.tsx:103` |
| `/api/users/` | `frontend/src/pages/Sociedade.tsx:124` |
| `/api/users/` | `frontend/src/pages/Tarefas.tsx:74` |
| `/api/users/` | `frontend/src/pages/Usuarios.tsx:49` |
| `/api/users/me/avatar` | `frontend/src/components/SecurityMenu.tsx:45` |
| `/api/users/me/avatar` | `frontend/src/components/SecurityMenu.tsx:65` |
| `/api/users/me/sessions/${sessionId}/revoke` | `frontend/src/components/AccountSecurity.tsx:146` |
| `/api/users/me/sessions/revoke-others` | `frontend/src/components/AccountSecurity.tsx:161` |
| `/api/users/me/totp-qr` | `frontend/src/components/AccountSecurity.tsx:90` |
| `/api/users` | `frontend/src/config/moduleRegistry.tsx:794` |
| `/api/utils/cep/${cep}` | `frontend/src/pages/Clientes.tsx:440` |
| `/api/v1/` | `frontend/src/lib/api.ts:21` |
| `/api/v1/cases/${caseId}/kanban` | `frontend/src/pages/Kanban.tsx:110` |
| `/api/v1/cases/` | `frontend/src/components/__tests__/FlowEnhancements.test.ts:31` |
| `/api/v1/clients/${clientId}/pending-items/${id}` | `frontend/src/pages/DossieCliente.tsx:262` |
| `/api/v1/clients/${clientId}/pending-items` | `frontend/src/pages/DossieCliente.tsx:220` |
| `/api/v1/clients/${clientId}/pending-items` | `frontend/src/pages/DossieCliente.tsx:246` |
| `/api/v1/datajud/cases/${caseId}/sync` | `frontend/src/pages/DataJudBusca.tsx:71` |
| `/api/v1/datajud` | `frontend/src/config/moduleRegistry.tsx:607` |
| `/api/v1/despesas/${editId}` | `frontend/src/pages/Despesas.tsx:190` |
| `/api/v1/despesas/${id}` | `frontend/src/pages/Despesas.tsx:203` |
| `/api/v1/despesas/${pendenteExcluir}` | `frontend/src/pages/Despesas.tsx:222` |
| `/api/v1/despesas/export/csv` | `frontend/src/pages/Despesas.tsx:118` |
| `/api/v1/despesas/export/csv` | `frontend/src/pages/FinanceiroDashboard.tsx:149` |
| `/api/v1/despesas` | `frontend/src/config/moduleRegistry.tsx:686` |
| `/api/v1/despesas` | `frontend/src/pages/Despesas.tsx:143` |
| `/api/v1/despesas` | `frontend/src/pages/Despesas.tsx:192` |
| `/api/v1/despesas` | `frontend/src/pages/DespesasRecorrentes.tsx:51` |
| `/api/v1/despesas` | `frontend/src/pages/DespesasRecorrentes.tsx:76` |
| `/api/v1/kanban-columns` | `frontend/src/pages/Kanban.tsx:69` |
| `/api/v1/office-contracts/${editing.id}` | `frontend/src/pages/OfficeContracts.tsx:163` |
| `/api/v1/office-contracts/${pendenteExcluir}` | `frontend/src/pages/OfficeContracts.tsx:183` |
| `/api/v1/office-contracts/expiring` | `frontend/src/pages/OfficeContracts.tsx:102` |
| `/api/v1/office-contracts` | `frontend/src/pages/OfficeContracts.tsx:165` |
| `/api/v1/office-contracts` | `frontend/src/pages/OfficeContracts.tsx:99` |
| `/api/v1/partner-withdrawals/${id}/${action}` | `frontend/src/pages/Sociedade.tsx:228` |
| `/api/v1/partner-withdrawals` | `frontend/src/pages/Sociedade.tsx:125` |
| `/api/v1/partner-withdrawals` | `frontend/src/pages/Sociedade.tsx:202` |
| `/api/v1/regulatorio` | `frontend/src/config/moduleRegistry.tsx:638` |
| `/api/v1/tasks/` | `frontend/src/components/__tests__/FlowEnhancements.test.ts:80` |
| `/api/v1` | `frontend/src/lib/api.ts:21` |
| `/api/v1` | `frontend/src/lib/api.ts:9` |
| `/api/validador-juridico/validar` | `frontend/src/pages/IA.tsx:135` |
| `/api/workflow/templates/${id}` | `frontend/src/pages/Workflow.tsx:93` |
| `/api/workflow/templates` | `frontend/src/pages/Workflow.tsx:67` |
| `/api/workflow` | `frontend/src/config/moduleRegistry.tsx:544` |

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
