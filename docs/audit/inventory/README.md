# Inventário Arquitetural EJC — Fase 0

Gerado em: 2026-07-23T15:30:27.613403+00:00
Fingerprint das fontes: `9d17be1cd5fc6dbd6b819c9d5c695d86cf0141ea4e96b6b42e6232e48389e0bf`

> Este inventário é descritivo e conservador. Nenhuma exclusão deve ocorrer apenas por heurística. 
> Itens marcados para exclusão exigem migração, telemetria, busca de consumidores e plano de rollback.

## Cobertura

- Itens totais: **5809**
- Páginas: **96**
- Rotas frontend: **57**
- Endpoints backend: **823**
- Serviços backend: **243**
- Tabelas ORM detectadas: **100**
- Routers não montados: **14**
- Itens que ainda exigem revisão humana: **5209**

## Classificação

| Classificação | Quantidade |
|---|---:|
| manter | 5225 |
| consolidar | 329 |
| renomear | 25 |
| redirecionar | 0 |
| corrigir | 167 |
| desativar | 51 |
| excluir após migração | 12 |

## Tipos inventariados

| Tipo | Quantidade |
|---|---:|
| class | 508 |
| component | 90 |
| endpoint | 823 |
| frontend_function | 1241 |
| frontend_route | 57 |
| function | 2328 |
| model_file | 60 |
| page | 96 |
| python_module | 95 |
| router | 168 |
| service | 243 |
| table | 100 |

## Origem das classificações

| Origem | Quantidade |
|---|---:|
| conservative-default | 5024 |
| duplicate-family | 134 |
| mount-analysis | 51 |
| override | 105 |
| parent-override | 495 |

## Famílias candidatas à consolidação

### `ai`
- `backend/app/routers/ai.py`
- `backend/app/services/ai_service.py`

### `ai_skill`
- `backend/app/models/ai_skill.py`
- `backend/app/services/ai_skill_service.py`

### `anexos`
- `backend/app/routers/anexos.py`
- `backend/app/services/anexos_service.py`

### `bank_analysis`
- `backend/app/models/bank_analysis.py`
- `backend/app/routers/bank_analysis.py`

### `base`
- `backend/app/services/conhecimento_ingest/base.py`
- `backend/app/services/juris_import/base.py`
- `backend/app/services/nfse/base.py`
- `backend/app/services/system_prompts/base.py`

### `case_intelligence`
- `backend/app/models/case_intelligence.py`
- `backend/app/routers/case_intelligence.py`
- `backend/app/services/case_intelligence_service.py`

### `checklists`
- `backend/app/routers/checklists.py`
- `frontend/src/pages/Checklists.tsx`

### `credential_vault`
- `backend/app/routers/credential_vault.py`
- `backend/app/services/credential_vault_service.py`

### `dashboard`
- `backend/app/routers/dashboard.py`
- `backend/app/services/dashboard_service.py`
- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/pages/DashboardModern.tsx`

### `data_room`
- `backend/app/models/data_room.py`
- `backend/app/routers/data_room.py`
- `backend/app/routers/data_room_v4.py`

### `datajud`
- `backend/app/routers/datajud.py`
- `backend/app/services/datajud_service.py`

### `despesas`
- `backend/app/routers/despesas.py`
- `frontend/src/pages/Despesas.tsx`

### `diagnostico`
- `backend/app/routers/diagnostico.py`
- `backend/app/services/diagnostico_service.py`

### `diario_oficial`
- `backend/app/models/diario_oficial.py`
- `backend/app/routers/diario_oficial.py`
- `backend/app/services/diario_oficial_service.py`

### `djen`
- `backend/app/models/djen.py`
- `backend/app/services/djen_service.py`
- `backend/app/services/ingestors/djen.py`

### `document_intake`
- `backend/app/models/document_intake.py`
- `backend/app/services/document_intake_service.py`

### `dossie_estrategico`
- `backend/app/models/dossie_estrategico.py`
- `backend/app/routers/dossie_estrategico.py`

### `entrada_universal`
- `backend/app/routers/entrada_universal.py`
- `backend/app/services/entrada_universal_service.py`

### `environmental`
- `backend/app/models/environmental.py`
- `backend/app/routers/environmental.py`

### `fee_proposal`
- `backend/app/models/fee_proposal.py`
- `backend/app/services/fee_proposal_service.py`

### `ficha_triagem`
- `backend/app/models/ficha_triagem.py`
- `backend/app/routers/ficha_triagem.py`
- `backend/app/services/ficha_triagem_service.py`

### `google_drive`
- `backend/app/services/google_drive.py`
- `backend/app/services/google_drive_service.py`

### `honorarios`
- `backend/app/services/system_prompts/honorarios.py`
- `frontend/src/pages/Honorarios.tsx`

### `honorarios_oab`
- `backend/app/routers/honorarios_oab.py`
- `backend/app/services/honorarios_oab.py`

### `ia_defensiva`
- `backend/app/routers/ia_defensiva.py`
- `backend/app/services/ia_defensiva_service.py`

### `indices`
- `backend/app/routers/indices.py`
- `backend/app/services/indices_service.py`

### `infosimples`
- `backend/app/services/infosimples_service.py`
- `frontend/src/components/Infosimples.tsx`

### `init`
- `backend/app/models/__init__.py`
- `backend/app/routers/__init__.py`
- `backend/app/services/__init__.py`
- `backend/app/services/ai/__init__.py`
- `backend/app/services/ai/agent/__init__.py`
- `backend/app/services/ai/agent/tools/__init__.py`
- `backend/app/services/ai/core/__init__.py`
- `backend/app/services/ambiental/__init__.py`
- `backend/app/services/calc/__init__.py`
- `backend/app/services/conhecimento_ingest/__init__.py`
- `backend/app/services/fiscal/__init__.py`
- `backend/app/services/ingestors/__init__.py`
- `backend/app/services/juris_import/__init__.py`
- `backend/app/services/nfse/__init__.py`
- `backend/app/services/observability/__init__.py`
- `backend/app/services/providers/__init__.py`
- `backend/app/services/system_prompts/__init__.py`

### `intimacoes`
- `backend/app/routers/intimacoes.py`
- `frontend/src/pages/Intimacoes.tsx`

### `jurimetria`
- `backend/app/routers/jurimetria.py`
- `backend/app/services/jurimetria.py`
- `frontend/src/pages/Jurimetria.tsx`

### `jurisprudencia_externa`
- `backend/app/routers/jurisprudencia_externa.py`
- `backend/app/services/jurisprudencia_externa.py`

### `jurisprudencia_interna`
- `backend/app/models/jurisprudencia_interna.py`
- `backend/app/routers/jurisprudencia_interna.py`

### `kanban`
- `backend/app/routers/kanban.py`
- `frontend/src/pages/Kanban.tsx`

### `lexml`
- `backend/app/services/ingestors/lexml.py`
- `backend/app/services/juris_import/lexml.py`

### `matriz_teses`
- `backend/app/models/matriz_teses.py`
- `backend/app/routers/matriz_teses.py`
- `backend/app/services/matriz_teses_service.py`

### `motor_peca`
- `backend/app/routers/motor_peca.py`
- `backend/app/services/motor_peca_service.py`

### `nfse`
- `backend/app/models/nfse.py`
- `backend/app/routers/nfse.py`

### `noticias`
- `backend/app/routers/noticias.py`
- `frontend/src/pages/Noticias.tsx`

### `notification`
- `backend/app/models/notification.py`
- `backend/app/services/notification_service.py`

### `peca_geracao`
- `backend/app/routers/peca_geracao.py`
- `backend/app/routers/peca_geracao_router.py`

### `pncp`
- `backend/app/routers/pncp.py`
- `backend/app/services/pncp_service.py`

### `prazos`
- `backend/app/services/system_prompts/prazos.py`
- `frontend/src/pages/Prazos.tsx`

### `previdenciario_beneficio`
- `backend/app/routers/previdenciario_beneficio.py`
- `backend/app/services/calc/previdenciario_beneficio.py`

### `produtividade`
- `backend/app/routers/produtividade.py`
- `frontend/src/pages/Produtividade.tsx`

### `prompts`
- `backend/app/routers/prompts.py`
- `frontend/src/pages/Prompts.tsx`

### `radar_legislativo`
- `backend/app/routers/radar_legislativo.py`
- `backend/app/services/radar_legislativo.py`

### `rag`
- `backend/app/models/rag.py`
- `backend/app/routers/rag.py`

### `raio_x`
- `backend/app/models/raio_x.py`
- `backend/app/routers/raio_x.py`
- `backend/app/services/raio_x_service.py`

### `sala_de_guerra`
- `backend/app/routers/sala_de_guerra.py`
- `backend/app/routers/sala_de_guerra_v3.py`

### `solicitacao_documento`
- `backend/app/models/solicitacao_documento.py`
- `backend/app/services/solicitacao_documento_service.py`

### `stj`
- `backend/app/services/ingestors/stj.py`
- `backend/app/services/juris_import/stj.py`

### `suspensoes`
- `backend/app/routers/suspensoes.py`
- `frontend/src/pages/Suspensoes.tsx`

### `teses`
- `backend/app/routers/teses.py`
- `backend/app/routers/teses_v4.py`

### `tjmg`
- `backend/app/services/ingestors/tjmg.py`
- `backend/app/services/juris_import/tjmg.py`

### `trabalhista`
- `backend/app/services/calc/trabalhista.py`
- `backend/app/services/system_prompts/trabalhista.py`

### `transparencia`
- `backend/app/routers/transparencia.py`
- `backend/app/services/transparencia_service.py`

### `validador_juridico`
- `backend/app/routers/validador_juridico.py`
- `backend/app/services/validador_juridico_service.py`

### `visual_law`
- `backend/app/routers/visual_law.py`
- `backend/app/services/visual_law.py`

### `wiki`
- `backend/app/models/wiki.py`
- `backend/app/routers/wiki.py`
- `frontend/src/pages/Wiki.tsx`

### `workflow`
- `backend/app/models/workflow.py`
- `backend/app/routers/workflow.py`
- `frontend/src/pages/Workflow.tsx`


## Páginas

| Tipo | Item | Arquivo/rota | Classificação | Fonte | Revisão |
|---|---|---|---|---|---|
| page | `AgenteIA` | `frontend/src/pages/AgenteIA.tsx` | **manter** | conservative-default | sim |
| page | `Ajuda` | `frontend/src/pages/Ajuda.tsx` | **manter** | conservative-default | sim |
| page | `Assinaturas.test` | `frontend/src/pages/Assinaturas.test.tsx` | **manter** | conservative-default | sim |
| page | `Assinaturas` | `frontend/src/pages/Assinaturas.tsx` | **manter** | conservative-default | sim |
| page | `AssistenteIA` | `frontend/src/pages/AssistenteIA.tsx` | **manter** | conservative-default | sim |
| page | `Auditoria` | `frontend/src/pages/Auditoria.tsx` | **manter** | conservative-default | sim |
| page | `Biblioteca` | `frontend/src/pages/Biblioteca.tsx` | **manter** | conservative-default | sim |
| page | `CRMLeads` | `frontend/src/pages/CRMLeads.tsx` | **manter** | conservative-default | sim |
| page | `CadastroManual` | `frontend/src/pages/CadastroManual.tsx` | **manter** | conservative-default | sim |
| page | `CasoDetalhe` | `frontend/src/pages/CasoDetalhe.tsx` | **corrigir** | override | não |
| page | `IaDefensivaCaso` | `frontend/src/pages/CasoDetalhe/IaDefensivaCaso.tsx` | **manter** | conservative-default | sim |
| page | `TabFerramentas` | `frontend/src/pages/CasoDetalhe/TabFerramentas.tsx` | **manter** | conservative-default | sim |
| page | `TabMemoria` | `frontend/src/pages/CasoDetalhe/TabMemoria.tsx` | **manter** | conservative-default | sim |
| page | `TabPartes` | `frontend/src/pages/CasoDetalhe/TabPartes.tsx` | **manter** | conservative-default | sim |
| page | `TabProcessos` | `frontend/src/pages/CasoDetalhe/TabProcessos.tsx` | **manter** | conservative-default | sim |
| page | `TabResumo` | `frontend/src/pages/CasoDetalhe/TabResumo.tsx` | **manter** | conservative-default | sim |
| page | `TabRisco` | `frontend/src/pages/CasoDetalhe/TabRisco.tsx` | **manter** | conservative-default | sim |
| page | `TabScore` | `frontend/src/pages/CasoDetalhe/TabScore.tsx` | **manter** | conservative-default | sim |
| page | `Casos` | `frontend/src/pages/Casos.tsx` | **manter** | conservative-default | sim |
| page | `Central` | `frontend/src/pages/Central.tsx` | **manter** | conservative-default | sim |
| page | `CentralAtividades` | `frontend/src/pages/CentralAtividades.tsx` | **manter** | conservative-default | sim |
| page | `CentralDiagnostico` | `frontend/src/pages/CentralDiagnostico.tsx` | **manter** | conservative-default | sim |
| page | `CentralRelacionamento` | `frontend/src/pages/CentralRelacionamento.tsx` | **manter** | conservative-default | sim |
| page | `Checklists` | `frontend/src/pages/Checklists.tsx` | **consolidar** | duplicate-family | sim |
| page | `Clientes` | `frontend/src/pages/Clientes.tsx` | **manter** | conservative-default | sim |
| page | `Configuracoes` | `frontend/src/pages/Configuracoes.tsx` | **manter** | conservative-default | sim |
| page | `Configurar2FA` | `frontend/src/pages/Configurar2FA.tsx` | **manter** | conservative-default | sim |
| page | `Conhecimento` | `frontend/src/pages/Conhecimento.tsx` | **manter** | conservative-default | sim |
| page | `ConhecimentoGovernado` | `frontend/src/pages/ConhecimentoGovernado.tsx` | **manter** | conservative-default | sim |
| page | `ConteudoJuridico` | `frontend/src/pages/ConteudoJuridico.tsx` | **manter** | conservative-default | sim |
| page | `Dashboard` | `frontend/src/pages/Dashboard.tsx` | **consolidar** | duplicate-family | sim |
| page | `DashboardIA` | `frontend/src/pages/DashboardIA.tsx` | **manter** | conservative-default | sim |
| page | `DashboardModern` | `frontend/src/pages/DashboardModern.tsx` | **consolidar** | duplicate-family | sim |
| page | `DataJudBusca` | `frontend/src/pages/DataJudBusca.tsx` | **manter** | conservative-default | sim |
| page | `DataRoom` | `frontend/src/pages/DataRoom.tsx` | **manter** | conservative-default | sim |
| page | `Despesas` | `frontend/src/pages/Despesas.tsx` | **consolidar** | duplicate-family | sim |
| page | `DespesasRecorrentes` | `frontend/src/pages/DespesasRecorrentes.tsx` | **manter** | conservative-default | sim |
| page | `DiarioOficial` | `frontend/src/pages/DiarioOficial.tsx` | **manter** | conservative-default | sim |
| page | `Documentos` | `frontend/src/pages/Documentos.tsx` | **manter** | conservative-default | sim |
| page | `DossieCliente` | `frontend/src/pages/DossieCliente.tsx` | **manter** | conservative-default | sim |
| page | `EntrevistaInteligente` | `frontend/src/pages/EntrevistaInteligente.tsx` | **manter** | conservative-default | sim |
| page | `Ferramentas` | `frontend/src/pages/Ferramentas.tsx` | **manter** | conservative-default | sim |
| page | `FerramentasIA` | `frontend/src/pages/FerramentasIA.tsx` | **manter** | conservative-default | sim |
| page | `FinanceiroDashboard` | `frontend/src/pages/FinanceiroDashboard.tsx` | **manter** | conservative-default | sim |
| page | `FinanceiroWorkspace` | `frontend/src/pages/FinanceiroWorkspace.tsx` | **manter** | conservative-default | sim |
| page | `GestaoDocumental` | `frontend/src/pages/GestaoDocumental.tsx` | **manter** | conservative-default | sim |
| page | `GovernancaIA` | `frontend/src/pages/GovernancaIA.tsx` | **manter** | conservative-default | sim |
| page | `Honorarios` | `frontend/src/pages/Honorarios.tsx` | **consolidar** | duplicate-family | sim |
| page | `IA` | `frontend/src/pages/IA.tsx` | **manter** | conservative-default | sim |
| page | `InteligenciaWorkspace` | `frontend/src/pages/InteligenciaWorkspace.tsx` | **manter** | conservative-default | sim |
| page | `Intimacoes` | `frontend/src/pages/Intimacoes.tsx` | **consolidar** | duplicate-family | sim |
| page | `JornadaCaso` | `frontend/src/pages/JornadaCaso.tsx` | **manter** | conservative-default | sim |
| page | `Jurimetria` | `frontend/src/pages/Jurimetria.tsx` | **consolidar** | duplicate-family | sim |
| page | `Kanban` | `frontend/src/pages/Kanban.tsx` | **consolidar** | duplicate-family | sim |
| page | `KnowledgeHub` | `frontend/src/pages/KnowledgeHub.tsx` | **excluir após migração** | override | não |
| page | `Lixeira` | `frontend/src/pages/Lixeira.tsx` | **manter** | conservative-default | sim |
| page | `LoginModern` | `frontend/src/pages/LoginModern.tsx` | **manter** | conservative-default | sim |
| page | `MapaModulos` | `frontend/src/pages/MapaModulos.tsx` | **manter** | conservative-default | sim |
| page | `MemoriaInstitucional` | `frontend/src/pages/MemoriaInstitucional.tsx` | **manter** | conservative-default | sim |
| page | `NotFound` | `frontend/src/pages/NotFound.tsx` | **manter** | conservative-default | sim |
| page | `NotasFiscais` | `frontend/src/pages/NotasFiscais.tsx` | **manter** | conservative-default | sim |
| page | `Noticias` | `frontend/src/pages/Noticias.tsx` | **consolidar** | duplicate-family | sim |
| page | `OfficeContracts` | `frontend/src/pages/OfficeContracts.tsx` | **manter** | conservative-default | sim |
| page | `PainelProvedoresIA` | `frontend/src/pages/PainelProvedoresIA.tsx` | **manter** | conservative-default | sim |
| page | `Pecas` | `frontend/src/pages/Pecas.tsx` | **manter** | conservative-default | sim |
| page | `Prazos` | `frontend/src/pages/Prazos.tsx` | **consolidar** | duplicate-family | sim |
| page | `Produtividade` | `frontend/src/pages/Produtividade.tsx` | **consolidar** | duplicate-family | sim |
| page | `Prompts` | `frontend/src/pages/Prompts.tsx` | **consolidar** | duplicate-family | sim |
| page | `RadarCompliance` | `frontend/src/pages/RadarCompliance.tsx` | **manter** | conservative-default | sim |
| page | `RadarRegulatorio` | `frontend/src/pages/RadarRegulatorio.tsx` | **manter** | conservative-default | sim |
| page | `RaioXProcesso` | `frontend/src/pages/RaioXProcesso.tsx` | **manter** | conservative-default | sim |
| page | `RamosHub` | `frontend/src/pages/RamosHub.tsx` | **renomear** | override | não |
| page | `RecuperarSenha` | `frontend/src/pages/RecuperarSenha.tsx` | **manter** | conservative-default | sim |
| page | `RedefinirSenha` | `frontend/src/pages/RedefinirSenha.tsx` | **manter** | conservative-default | sim |
| page | `SalaDeGuerra` | `frontend/src/pages/SalaDeGuerra.tsx` | **manter** | conservative-default | sim |
| page | `Sociedade` | `frontend/src/pages/Sociedade.tsx` | **manter** | conservative-default | sim |
| page | `Suspensoes` | `frontend/src/pages/Suspensoes.tsx` | **consolidar** | duplicate-family | sim |
| page | `Tarefas` | `frontend/src/pages/Tarefas.tsx` | **manter** | conservative-default | sim |
| page | `TrocarSenha` | `frontend/src/pages/TrocarSenha.tsx` | **manter** | conservative-default | sim |
| page | `Usuarios` | `frontend/src/pages/Usuarios.tsx` | **manter** | conservative-default | sim |
| page | `Wiki` | `frontend/src/pages/Wiki.tsx` | **consolidar** | duplicate-family | sim |
| page | `Workflow` | `frontend/src/pages/Workflow.tsx` | **consolidar** | duplicate-family | sim |
| page | `Central.test` | `frontend/src/pages/__tests__/Central.test.tsx` | **manter** | conservative-default | sim |
| page | `Configuracoes.test` | `frontend/src/pages/__tests__/Configuracoes.test.tsx` | **manter** | conservative-default | sim |
| page | `DiarioOficial.test` | `frontend/src/pages/__tests__/DiarioOficial.test.tsx` | **manter** | conservative-default | sim |
| page | `JornadaCaso.test` | `frontend/src/pages/__tests__/JornadaCaso.test.tsx` | **manter** | conservative-default | sim |
| page | `NotFound.test` | `frontend/src/pages/__tests__/NotFound.test.tsx` | **manter** | conservative-default | sim |
| page | `Sociedade.test` | `frontend/src/pages/__tests__/Sociedade.test.tsx` | **manter** | conservative-default | sim |
| page | `PortalAssinaturas` | `frontend/src/pages/portal/PortalAssinaturas.tsx` | **manter** | conservative-default | sim |
| page | `PortalCasoDetalhe` | `frontend/src/pages/portal/PortalCasoDetalhe.tsx` | **manter** | conservative-default | sim |
| page | `PortalCasos` | `frontend/src/pages/portal/PortalCasos.tsx` | **manter** | conservative-default | sim |
| page | `PortalDashboard` | `frontend/src/pages/portal/PortalDashboard.tsx` | **manter** | conservative-default | sim |
| page | `PortalDocumentos` | `frontend/src/pages/portal/PortalDocumentos.tsx` | **manter** | conservative-default | sim |
| page | `PortalFinanceiro` | `frontend/src/pages/portal/PortalFinanceiro.tsx` | **manter** | conservative-default | sim |
| page | `PortalMensagens` | `frontend/src/pages/portal/PortalMensagens.tsx` | **manter** | conservative-default | sim |
| page | `RamoBase` | `frontend/src/pages/ramos/RamoBase.tsx` | **renomear** | override | não |

## Rotas frontend

| Tipo | Item | Arquivo/rota | Classificação | Fonte | Revisão |
|---|---|---|---|---|---|
| frontend_route | `/login` | `/login:79` | **manter** | conservative-default | sim |
| frontend_route | `/recuperar-senha` | `/recuperar-senha:80` | **manter** | conservative-default | sim |
| frontend_route | `/redefinir-senha` | `/redefinir-senha:81` | **manter** | conservative-default | sim |
| frontend_route | `/trocar-senha` | `/trocar-senha:82` | **manter** | conservative-default | sim |
| frontend_route | `/configurar-2fa` | `/configurar-2fa:91` | **manter** | conservative-default | sim |
| frontend_route | `/portal` | `/portal:100` | **manter** | conservative-default | sim |
| frontend_route | `casos` | `casos:111` | **manter** | conservative-default | sim |
| frontend_route | `casos/:id` | `casos/:id:112` | **manter** | conservative-default | sim |
| frontend_route | `financeiro` | `financeiro:113` | **manter** | conservative-default | sim |
| frontend_route | `assinaturas` | `assinaturas:114` | **manter** | conservative-default | sim |
| frontend_route | `mensagens` | `mensagens:115` | **manter** | conservative-default | sim |
| frontend_route | `documentos` | `documentos:116` | **manter** | conservative-default | sim |
| frontend_route | `/ia-governanca/provedores` | `/ia-governanca/provedores:153` | **manter** | conservative-default | sim |
| frontend_route | `/clientes/:clientId/dossie` | `/clientes/:clientId/dossie:170` | **manter** | conservative-default | sim |
| frontend_route | `/ramos/:slug` | `/ramos/:slug:174` | **manter** | conservative-default | sim |
| frontend_route | `*` | `*:180` | **manter** | conservative-default | sim |
| frontend_route | `dashboard` | `/:156` | **manter** | conservative-default | sim |
| frontend_route | `caso-novo` | `/casos/novo:174` | **manter** | conservative-default | sim |
| frontend_route | `crm` | `/crm-leads:198` | **manter** | conservative-default | sim |
| frontend_route | `cadastro-manual` | `/cadastro-manual:230` | **manter** | conservative-default | sim |
| frontend_route | `cliente-detalhe` | `/clientes/:clientId:254` | **manter** | conservative-default | sim |
| frontend_route | `raio-x-processo` | `/raio-x:266` | **manter** | conservative-default | sim |
| frontend_route | `casos` | `/casos:284` | **manter** | conservative-default | sim |
| frontend_route | `caso-detalhe` | `/casos/:id:300` | **manter** | conservative-default | sim |
| frontend_route | `caso-jornada` | `/casos/:id/jornada:314` | **consolidar** | override | não |
| frontend_route | `caso-entrevista` | `/casos/:id/entrevista:329` | **manter** | conservative-default | sim |
| frontend_route | `sala-de-guerra` | `/casos/:caseId/sala-de-guerra:347` | **manter** | conservative-default | sim |
| frontend_route | `ramos` | `/areas-de-atuacao:360` | **manter** | conservative-default | sim |
| frontend_route | `ramo-detalhe` | `/areas-de-atuacao/:slug:377` | **manter** | conservative-default | sim |
| frontend_route | `atividades` | `/atividades:392` | **manter** | conservative-default | sim |
| frontend_route | `prazos` | `/legado/prazos:414` | **manter** | conservative-default | sim |
| frontend_route | `tarefas` | `/legado/tarefas:429` | **manter** | conservative-default | sim |
| frontend_route | `intimacoes` | `/legado/intimacoes:443` | **manter** | conservative-default | sim |
| frontend_route | `suspensoes` | `/legado/suspensoes:459` | **manter** | conservative-default | sim |
| frontend_route | `documentos` | `/documentos:473` | **manter** | conservative-default | sim |
| frontend_route | `pecas` | `/pecas:493` | **manter** | conservative-default | sim |
| frontend_route | `assinaturas` | `/assinaturas:509` | **manter** | conservative-default | sim |
| frontend_route | `workflow` | `/workflow:524` | **manter** | conservative-default | sim |
| frontend_route | `checklists` | `/checklists:539` | **manter** | conservative-default | sim |
| frontend_route | `inteligencia` | `/inteligencia:555` | **manter** | conservative-default | sim |
| frontend_route | `prompts` | `/prompts:573` | **manter** | conservative-default | sim |
| frontend_route | `datajud` | `/datajud:587` | **manter** | conservative-default | sim |
| frontend_route | `diario-oficial` | `/diario-oficial:602` | **manter** | conservative-default | sim |
| frontend_route | `radar-regulatorio` | `/radar-regulatorio:618` | **manter** | conservative-default | sim |
| frontend_route | `radar-compliance` | `/compliance/radar:633` | **manter** | conservative-default | sim |
| frontend_route | `noticias` | `/noticias:648` | **manter** | conservative-default | sim |
| frontend_route | `financeiro` | `/financeiro:662` | **manter** | conservative-default | sim |
| frontend_route | `produtividade` | `/produtividade:683` | **manter** | conservative-default | sim |
| frontend_route | `configuracoes` | `/configuracoes:697` | **manter** | conservative-default | sim |
| frontend_route | `governanca-ia` | `/ia-governanca:710` | **manter** | conservative-default | sim |
| frontend_route | `central-diagnostico` | `/diagnostico:727` | **manter** | conservative-default | sim |
| frontend_route | `auditoria` | `/auditoria:742` | **manter** | conservative-default | sim |
| frontend_route | `mapa-modulos` | `/mapa-modulos:758` | **manter** | conservative-default | sim |
| frontend_route | `usuarios` | `/usuarios:774` | **manter** | conservative-default | sim |
| frontend_route | `lixeira` | `/lixeira:789` | **manter** | conservative-default | sim |
| frontend_route | `ajuda` | `/ajuda:805` | **manter** | conservative-default | sim |
| frontend_route | `ferramentas` | `/ferramentas:819` | **manter** | conservative-default | sim |

## Endpoints backend

| Tipo | Item | Arquivo/rota | Classificação | Fonte | Revisão |
|---|---|---|---|---|---|
| endpoint | `consultar_processo_datajud` | `/api/integracoes/datajud/processos/{tribunal}/{numero_processo}:113` | **manter** | conservative-default | sim |
| endpoint | `consultar_djen_por_oab` | `/api/integracoes/djen/oab/{uf}/{numero_oab}:138` | **manter** | conservative-default | sim |
| endpoint | `consultar_djen_por_processo` | `/api/integracoes/djen/processos/{numero_processo}:163` | **manter** | conservative-default | sim |
| endpoint | `consultar_cnpj` | `/api/integracoes/brasilapi/cnpj/{cnpj}:180` | **manter** | conservative-default | sim |
| endpoint | `consultar_cep` | `/api/integracoes/brasilapi/cep/{cep}:197` | **manter** | conservative-default | sim |
| endpoint | `health` | `/api/api/health:462` | **corrigir** | parent-override | não |
| endpoint | `readiness` | `/api/api/health/ready:477` | **corrigir** | parent-override | não |
| endpoint | `meu_estilo` | `/api/advogado-estilo/me:20` | **desativar** | mount-analysis | sim |
| endpoint | `listar` | `/api/agenda-eventos/:103` | **manter** | conservative-default | sim |
| endpoint | `criar` | `/api/agenda-eventos/:139` | **manter** | conservative-default | sim |
| endpoint | `atualizar` | `/api/agenda-eventos/{evento_id}:177` | **manter** | conservative-default | sim |
| endpoint | `remover` | `/api/agenda-eventos/{evento_id}:242` | **manter** | conservative-default | sim |
| endpoint | `verificar_citacoes_juris` | `/api/ai/citacoes/verificar:33` | **consolidar** | parent-override | não |
| endpoint | `analisar` | `/api/ai/analisar-caso:55` | **consolidar** | parent-override | não |
| endpoint | `dossie_caso` | `/api/ai/dossie/{case_id}:79` | **consolidar** | parent-override | não |
| endpoint | `resumir` | `/api/ai/resumir-documento:107` | **consolidar** | parent-override | não |
| endpoint | `listar_logs` | `/api/ai/logs:121` | **consolidar** | parent-override | não |
| endpoint | `atualizar_hitl` | `/api/ai/logs/{log_id}/hitl:157` | **consolidar** | parent-override | não |
| endpoint | `citacoes_do_log` | `/api/ai/logs/{log_id}/citacoes:193` | **consolidar** | parent-override | não |
| endpoint | `feedback_resposta_ia` | `/api/ai/logs/{log_id}/feedback:244` | **consolidar** | parent-override | não |
| endpoint | `resumo_feedback_ia` | `/api/ai/logs/feedback/resumo:282` | **consolidar** | parent-override | não |
| endpoint | `teses_ocultas` | `/api/ai/teses-ocultas:347` | **consolidar** | parent-override | não |
| endpoint | `auditar` | `/api/ai/auditar-peca:373` | **consolidar** | parent-override | não |
| endpoint | `audiencia` | `/api/ai/preparar-audiencia:415` | **consolidar** | parent-override | não |
| endpoint | `gateway_health` | `/api/ai/gateway/health:433` | **consolidar** | parent-override | não |
| endpoint | `roteamento_preview` | `/api/ai/roteamento/preview:443` | **consolidar** | parent-override | não |
| endpoint | `assistente_estrategico` | `/api/ai/casos/{case_id}/assistente:516` | **consolidar** | parent-override | não |
| endpoint | `dual_ia` | `/api/ai/casos/{case_id}/dual:635` | **consolidar** | parent-override | não |
| endpoint | `visual_law` | `/api/ai/caso/{case_id}/visual-law:754` | **consolidar** | parent-override | não |
| endpoint | `motor_estrategia` | `/api/ai/caso/{case_id}/estrategia:795` | **consolidar** | parent-override | não |
| endpoint | `analisar_contrato_endpoint` | `/api/ai/analisar-contrato:903` | **consolidar** | parent-override | não |
| endpoint | `detectar_prazos` | `/api/ai/detectar-prazos:930` | **consolidar** | parent-override | não |
| endpoint | `core_chat` | `/api/ai/core/chat:109` | **manter** | parent-override | não |
| endpoint | `core_task` | `/api/ai/core/task:124` | **manter** | parent-override | não |
| endpoint | `core_analyze` | `/api/ai/core/analyze:141` | **manter** | parent-override | não |
| endpoint | `core_generate` | `/api/ai/core/generate:158` | **manter** | parent-override | não |
| endpoint | `core_report` | `/api/ai/core/report:174` | **manter** | parent-override | não |
| endpoint | `core_agents` | `/api/ai/core/agents:191` | **manter** | parent-override | não |
| endpoint | `core_skills` | `/api/ai/core/skills:204` | **manter** | parent-override | não |
| endpoint | `core_native_skills_coverage` | `/api/ai/core/native-skills/coverage:210` | **manter** | parent-override | não |
| endpoint | `core_status` | `/api/ai/core/status:216` | **manter** | parent-override | não |
| endpoint | `listar_acoes_contextuais` | `/api/ai/skills/contextual:224` | **consolidar** | parent-override | não |
| endpoint | `listar_skills` | `/api/ai/skills/list:261` | **consolidar** | parent-override | não |
| endpoint | `executar_skill` | `/api/ai/skills/execute:270` | **consolidar** | parent-override | não |
| endpoint | `executar_skill_documento` | `/api/ai/skills/execute-doc:310` | **consolidar** | parent-override | não |
| endpoint | `transcrever_midia` | `/api/ai/skills/transcribe-media:461` | **consolidar** | parent-override | não |
| endpoint | `status_ia` | `/api/ai/status:59` | **consolidar** | parent-override | não |
| endpoint | `executar_ia` | `/api/ai/executar:74` | **consolidar** | parent-override | não |
| endpoint | `simular` | `/api/ambiental/estrategia/simular:92` | **manter** | conservative-default | sim |
| endpoint | `peca_conversao` | `/api/ambiental/estrategia/peca-conversao:215` | **manter** | conservative-default | sim |
| endpoint | `download_peca` | `/api/ambiental/estrategia/peca/{arquivo_id}/download:239` | **manter** | conservative-default | sim |
| endpoint | `analisar_documento` | `/api/analise-bancaria/contrato:109` | **manter** | conservative-default | sim |
| endpoint | `modalidades` | `/api/analise-bancaria/modalidades:136` | **manter** | conservative-default | sim |
| endpoint | `taxa_media` | `/api/analise-bancaria/taxa-media:163` | **manter** | conservative-default | sim |
| endpoint | `calcular_cet_endpoint` | `/api/analise-bancaria/cet:201` | **manter** | conservative-default | sim |
| endpoint | `avaliar_abusividade_endpoint` | `/api/analise-bancaria/abusividade:236` | **manter** | conservative-default | sim |
| endpoint | `jurimetria_endpoint` | `/api/analytics/jurimetria:28` | **manter** | conservative-default | sim |
| endpoint | `taskscore_endpoint` | `/api/analytics/taskscore:44` | **manter** | conservative-default | sim |
| endpoint | `funil_endpoint` | `/api/analytics/funil:53` | **manter** | conservative-default | sim |
| endpoint | `rentabilidade_endpoint` | `/api/analytics/rentabilidade:62` | **manter** | conservative-default | sim |
| endpoint | `onboarding_pendencias` | `/api/analytics/onboarding:72` | **manter** | conservative-default | sim |
| endpoint | `onboarding_cliente` | `/api/analytics/onboarding/{client_id}:82` | **manter** | conservative-default | sim |
| endpoint | `case_health_ranking` | `/api/analytics/case-health:99` | **manter** | conservative-default | sim |
| endpoint | `case_health_detalhe` | `/api/analytics/case-health/{case_id}:110` | **manter** | conservative-default | sim |
| endpoint | `status_andamentos` | `/api/casos/{case_id}/andamentos/status:37` | **manter** | conservative-default | sim |
| endpoint | `sincronizar_andamentos` | `/api/casos/{case_id}/andamentos/sincronizar:58` | **manter** | conservative-default | sim |
| endpoint | `preview` | `/api/anexos/preview:76` | **manter** | conservative-default | sim |
| endpoint | `gerar` | `/api/anexos/gerar:109` | **manter** | conservative-default | sim |
| endpoint | `razoes` | `/api/anexos/razoes:132` | **manter** | conservative-default | sim |
| endpoint | `criar_api_key` | `/api/api-keys:50` | **desativar** | mount-analysis | sim |
| endpoint | `listar_api_keys` | `/api/api-keys:83` | **desativar** | mount-analysis | sim |
| endpoint | `revogar_api_key` | `/api/api-keys/{key_id}/revogar:95` | **desativar** | mount-analysis | sim |
| endpoint | `route_manifest` | `/api/architecture/routes:14` | **manter** | conservative-default | sim |
| endpoint | `domain_contracts` | `/api/architecture/contracts:20` | **manter** | conservative-default | sim |
| endpoint | `listar` | `/api/areas:13` | **manter** | conservative-default | sim |
| endpoint | `listar_atendimentos` | `/api/atendimentos:397` | **manter** | conservative-default | sim |
| endpoint | `criar_atendimento` | `/api/atendimentos:489` | **manter** | conservative-default | sim |
| endpoint | `listar_responsaveis` | `/api/atendimentos/responsaveis:596` | **manter** | conservative-default | sim |
| endpoint | `resumo_solicitacoes` | `/api/atendimentos/solicitacoes-resumo:624` | **manter** | conservative-default | sim |
| endpoint | `meus_atendimentos` | `/api/atendimentos/meus:725` | **manter** | conservative-default | sim |
| endpoint | `por_advogado` | `/api/atendimentos/por-advogado/{advogado_id}:752` | **manter** | conservative-default | sim |
| endpoint | `dashboard_atendimentos` | `/api/atendimentos/dashboard:787` | **manter** | conservative-default | sim |
| endpoint | `stats_mensais` | `/api/atendimentos/stats:819` | **manter** | conservative-default | sim |
| endpoint | `historico_atendimento` | `/api/atendimentos/{atendimento_id}/historico:876` | **manter** | conservative-default | sim |
| endpoint | `obter_atendimento` | `/api/atendimentos/{atendimento_id}:914` | **manter** | conservative-default | sim |
| endpoint | `atualizar_atendimento` | `/api/atendimentos/{atendimento_id}:929` | **manter** | conservative-default | sim |
| endpoint | `remover_atendimento` | `/api/atendimentos/{atendimento_id}:1031` | **manter** | conservative-default | sim |
| endpoint | `listar_atividades` | `/api/atividades:16` | **manter** | conservative-default | sim |
| endpoint | `listar` | `/api/audit/:20` | **manter** | conservative-default | sim |
| endpoint | `login` | `/api/auth/login:179` | **manter** | conservative-default | sim |
| endpoint | `refresh` | `/api/auth/refresh:345` | **manter** | conservative-default | sim |
| endpoint | `logout` | `/api/auth/logout:514` | **manter** | conservative-default | sim |
| endpoint | `alterar_senha` | `/api/auth/alterar-senha:534` | **manter** | conservative-default | sim |
| endpoint | `recuperar_senha` | `/api/auth/recuperar-senha:633` | **manter** | conservative-default | sim |
| endpoint | `redefinir_senha` | `/api/auth/redefinir-senha:661` | **manter** | conservative-default | sim |
| endpoint | `totp_setup` | `/api/auth/totp/setup:683` | **manter** | conservative-default | sim |
| endpoint | `totp_verificar` | `/api/auth/totp/verificar:729` | **manter** | conservative-default | sim |
| endpoint | `totp_desativar` | `/api/auth/totp/desativar:804` | **manter** | conservative-default | sim |
| endpoint | `executar_backup_manual` | `/api/admin/backup/executar:30` | **manter** | conservative-default | sim |
| endpoint | `status_backup` | `/api/admin/backup/status:90` | **manter** | conservative-default | sim |
| endpoint | `upload` | `/api/bank-analysis/upload:39` | **manter** | conservative-default | sim |
| endpoint | `listar` | `/api/bank-analysis/:118` | **manter** | conservative-default | sim |
| endpoint | `detalhe` | `/api/bank-analysis/{analysis_id}:142` | **manter** | conservative-default | sim |
| endpoint | `excel` | `/api/bank-analysis/{analysis_id}/excel:165` | **manter** | conservative-default | sim |
| endpoint | `documento` | `/api/bank-analysis/{analysis_id}/documento:182` | **manter** | conservative-default | sim |
| endpoint | `gerar_peca` | `/api/bank-analysis/{analysis_id}/gerar-peca:262` | **manter** | conservative-default | sim |
| endpoint | `remover` | `/api/bank-analysis/{analysis_id}:346` | **manter** | conservative-default | sim |
| endpoint | `tipos_rescisao` | `/api/calculadoras/tipos-rescisao:60` | **manter** | conservative-default | sim |
| endpoint | `rescisao` | `/api/calculadoras/trabalhista/rescisao:66` | **manter** | conservative-default | sim |
| endpoint | `inss_endpoint` | `/api/calculadoras/inss:81` | **manter** | conservative-default | sim |
| endpoint | `irrf_endpoint` | `/api/calculadoras/irrf:90` | **manter** | conservative-default | sim |
| endpoint | `correcao_monetaria` | `/api/calculadoras/correcao-monetaria:102` | **manter** | conservative-default | sim |
| endpoint | `prescricao_tipos` | `/api/calculadoras/prescricao/tipos:132` | **manter** | conservative-default | sim |
| endpoint | `prescricao` | `/api/calculadoras/prescricao:142` | **manter** | conservative-default | sim |
| endpoint | `custas_tjmg_endpoint` | `/api/calculadoras/custas-tjmg:154` | **manter** | conservative-default | sim |
| endpoint | `minha_url_calendario_revogavel` | `/api/calendar/me/url:103` | **manter** | conservative-default | sim |
| endpoint | `rotacionar_url_calendario` | `/api/calendar/me/rotate:117` | **manter** | conservative-default | sim |
| endpoint | `feed_ics` | `/api/calendar/{user_id}/{token}.ics:166` | **manter** | conservative-default | sim |
| endpoint | `consultar_imovel` | `/api/car/imovel:68` | **manter** | conservative-default | sim |
| endpoint | `consultar_demonstrativo` | `/api/car/demonstrativo:97` | **manter** | conservative-default | sim |
| endpoint | `obter_inteligencia` | `/api/cases/{case_id}/inteligencia:61` | **manter** | conservative-default | sim |
| endpoint | `obter_snapshot` | `/api/cases/{case_id}/inteligencia/{snapshot_id}:78` | **manter** | conservative-default | sim |
| endpoint | `aprovar` | `/api/cases/{case_id}/inteligencia/{snapshot_id}/aprovar:96` | **manter** | conservative-default | sim |
| endpoint | `listar_partes` | `/api/cases/{case_id}/partes:32` | **manter** | conservative-default | sim |
| endpoint | `criar_parte` | `/api/cases/{case_id}/partes:55` | **manter** | conservative-default | sim |
| endpoint | `remover_parte` | `/api/cases/{case_id}/partes/{parte_id}:88` | **manter** | conservative-default | sim |
| endpoint | `listar` | `/api/cases/:83` | **manter** | conservative-default | sim |
| endpoint | `stats_casos` | `/api/cases/stats:133` | **manter** | conservative-default | sim |
| endpoint | `criar` | `/api/cases/:189` | **manter** | conservative-default | sim |
| endpoint | `detalhe` | `/api/cases/{case_id}:302` | **manter** | conservative-default | sim |
| endpoint | `atualizar` | `/api/cases/{case_id}:323` | **manter** | conservative-default | sim |
| endpoint | `arquivar_caso` | `/api/cases/{case_id}/arquivar:411` | **manter** | conservative-default | sim |
| endpoint | `desarquivar_caso` | `/api/cases/{case_id}/desarquivar:449` | **manter** | conservative-default | sim |
| endpoint | `excluir` | `/api/cases/{case_id}:501` | **manter** | conservative-default | sim |
| endpoint | `gerar_documentos` | `/api/cases/{case_id}/gerar-documentos:587` | **manter** | conservative-default | sim |
| endpoint | `listar_movimentos` | `/api/cases/{case_id}/movimentos:625` | **manter** | conservative-default | sim |
| endpoint | `criar_movimento` | `/api/cases/{case_id}/movimentos:650` | **manter** | conservative-default | sim |
| endpoint | `assistente_estrategico_caso` | `/api/cases/{case_id}/assistente-estrategico:676` | **manter** | conservative-default | sim |
| endpoint | `sincronizar_processo` | `/api/cases/{case_id}/sincronizar-processo:742` | **manter** | conservative-default | sim |
| endpoint | `encerrar_caso` | `/api/cases/{case_id}/encerrar:786` | **manter** | conservative-default | sim |
| endpoint | `traduzir_andamento` | `/api/cases/{case_id}/movimentos/{mov_id}/traduzir:877` | **manter** | conservative-default | sim |
| endpoint | `aplicar_extracao` | `/api/cases/{case_id}/aplicar-extracao:939` | **manter** | conservative-default | sim |
| endpoint | `linha_do_tempo` | `/api/cases/{case_id}/linha-do-tempo:1099` | **manter** | conservative-default | sim |
| endpoint | `teses_sugeridas` | `/api/cases/{case_id}/teses-sugeridas:1161` | **manter** | conservative-default | sim |
| endpoint | `analisar_caso_ia` | `/api/cases/{case_id}/analisar:1270` | **manter** | conservative-default | sim |
| endpoint | `listar_areas` | `/api/cases/{case_id}/areas:16` | **manter** | conservative-default | sim |
| endpoint | `adicionar_area` | `/api/cases/{case_id}/areas:25` | **manter** | conservative-default | sim |
| endpoint | `remover_area` | `/api/cases/{case_id}/areas/{area}:46` | **manter** | conservative-default | sim |
| endpoint | `listar_lancamentos` | `/api/centro-custos:96` | **manter** | conservative-default | sim |
| endpoint | `criar_lancamento` | `/api/centro-custos:133` | **manter** | conservative-default | sim |
| endpoint | `resumo_caso` | `/api/centro-custos/caso/{case_id}/resumo:148` | **manter** | conservative-default | sim |
| endpoint | `consolidado_geral` | `/api/centro-custos/consolidado:209` | **manter** | conservative-default | sim |
| endpoint | `atualizar_lancamento` | `/api/centro-custos/{lancamento_id}:280` | **manter** | conservative-default | sim |
| endpoint | `remover_lancamento` | `/api/centro-custos/{lancamento_id}:302` | **manter** | conservative-default | sim |
| endpoint | `status_cerebro` | `/api/cerebro/status:16` | **manter** | conservative-default | sim |
| endpoint | `analise_estrategica` | `/api/cerebro/analise-estrategica:20` | **manter** | conservative-default | sim |
| endpoint | `listar_teses` | `/api/cerebro/teses:66` | **manter** | conservative-default | sim |
| endpoint | `pesquisar_jurisprudencia` | `/api/cerebro/jurisprudencia/pesquisa:71` | **manter** | conservative-default | sim |
| endpoint | `listar_templates` | `/api/checklists/templates:120` | **manter** | conservative-default | sim |
| endpoint | `criar_template` | `/api/checklists/templates:149` | **manter** | conservative-default | sim |
| endpoint | `remover_template` | `/api/checklists/templates/{template_id}:181` | **manter** | conservative-default | sim |
| endpoint | `instanciar_checklist` | `/api/checklists/instanciar:200` | **manter** | conservative-default | sim |
| endpoint | `gerar_checklist_ia_endpoint` | `/api/checklists/caso/{case_id}/gerar-ia:279` | **manter** | conservative-default | sim |
| endpoint | `checklists_do_caso` | `/api/checklists/casos/{case_id}:310` | **manter** | conservative-default | sim |
| endpoint | `obter_checklist` | `/api/checklists/{checklist_id}:336` | **manter** | conservative-default | sim |
| endpoint | `marcar_item` | `/api/checklists/{checklist_id}/itens/{item_id}/marcar:359` | **manter** | conservative-default | sim |
| endpoint | `adicionar_item` | `/api/checklists/{checklist_id}/itens:423` | **manter** | conservative-default | sim |
| endpoint | `cancelar_checklist` | `/api/checklists/{checklist_id}:457` | **manter** | conservative-default | sim |
| endpoint | `resolver_cliente` | `/api/clients/resolver:127` | **manter** | conservative-default | sim |
| endpoint | `verificar_conflito` | `/api/clients/verificar-conflito:197` | **manter** | conservative-default | sim |
| endpoint | `checar_conflito` | `/api/clients/checar-conflito:246` | **manter** | conservative-default | sim |
| endpoint | `listar` | `/api/clients/:396` | **manter** | conservative-default | sim |
| endpoint | `criar` | `/api/clients/:443` | **manter** | conservative-default | sim |
| endpoint | `detalhe` | `/api/clients/{client_id}:524` | **manter** | conservative-default | sim |
| endpoint | `ia_analise_cliente` | `/api/clients/{client_id}/ia-analise:542` | **manter** | conservative-default | sim |
| endpoint | `atualizar` | `/api/clients/{client_id}:600` | **manter** | conservative-default | sim |
| endpoint | `remover` | `/api/clients/{client_id}:672` | **manter** | conservative-default | sim |
| endpoint | `criar_acesso_portal` | `/api/clients/{client_id}/criar-acesso:702` | **manter** | conservative-default | sim |
| endpoint | `relatorio_lgpd` | `/api/clients/{client_id}/relatorio-lgpd:758` | **manter** | conservative-default | sim |
| endpoint | `dados_lgpd_json` | `/api/clients/{client_id}/dados-lgpd.json:829` | **manter** | conservative-default | sim |
| endpoint | `verificar_bloqueios_esquecimento` | `/api/clients/{client_id}/esquecimento/bloqueios:888` | **manter** | conservative-default | sim |
| endpoint | `solicitar_esquecimento` | `/api/clients/{client_id}/esquecimento:910` | **manter** | conservative-default | sim |
| endpoint | `termo_consentimento_ia` | `/api/compliance/cases/{case_id}/termo-consentimento-ia:135` | **manter** | conservative-default | sim |
| endpoint | `radar_compliance` | `/api/compliance/radar:266` | **manter** | conservative-default | sim |
| endpoint | `listar_empresas` | `/api/consumidor-monitor/empresas:151` | **manter** | conservative-default | sim |
| endpoint | `dados_empresa` | `/api/consumidor-monitor/empresa/{nome_empresa}:166` | **manter** | conservative-default | sim |
| endpoint | `triagem_jec` | `/api/consumidor-monitor/triagem-jec:204` | **manter** | conservative-default | sim |
| endpoint | `painel_reclamacoes` | `/api/consumidor-monitor/painel-semanal:277` | **manter** | conservative-default | sim |
| endpoint | `gerar_faq` | `/api/conteudo/faq:61` | **manter** | conservative-default | sim |
| endpoint | `gerar_glossario` | `/api/conteudo/glossario:80` | **manter** | conservative-default | sim |
| endpoint | `listar_contratos` | `/api/contratos:181` | **manter** | conservative-default | sim |
| endpoint | `criar_contrato` | `/api/contratos:216` | **manter** | conservative-default | sim |
| endpoint | `obter_contrato` | `/api/contratos/{contrato_id}:245` | **manter** | conservative-default | sim |
| endpoint | `atualizar_contrato` | `/api/contratos/{contrato_id}:277` | **manter** | conservative-default | sim |
| endpoint | `transicionar_status` | `/api/contratos/{contrato_id}/transicao:302` | **manter** | conservative-default | sim |
| endpoint | `arquivar_contrato` | `/api/contratos/{contrato_id}:342` | **manter** | conservative-default | sim |
| endpoint | `checklist_conversao` | `/api/cases/{case_id}/converter-judicial/checklist:248` | **manter** | conservative-default | sim |
| endpoint | `converter_judicial` | `/api/cases/{case_id}/converter-judicial:260` | **manter** | conservative-default | sim |
| endpoint | `listar_cofre` | `/api/cofre-credenciais:240` | **manter** | parent-override | não |
| endpoint | `historico_campo` | `/api/cofre-credenciais/{provider_key}/{field_key}/historico:278` | **manter** | parent-override | não |
| endpoint | `importar_env` | `/api/cofre-credenciais/importar-env:294` | **manter** | parent-override | não |
| endpoint | `testar_credencial` | `/api/cofre-credenciais/{provider_key}/testar:317` | **manter** | parent-override | não |
| endpoint | `cadastrar_credencial` | `/api/cofre-credenciais/{provider_key}/{field_key}:345` | **manter** | parent-override | não |
| endpoint | `revogar_credencial` | `/api/cofre-credenciais/{provider_key}/{field_key}:385` | **manter** | parent-override | não |
| endpoint | `listar_teses` | `/api/curadoria/teses:35` | **manter** | conservative-default | sim |
| endpoint | `sincronizar_teses_externas` | `/api/curadoria/teses/sincronizar:40` | **manter** | conservative-default | sim |
| endpoint | `analise_vencedora` | `/api/curadoria/analise-vencedora/{caso_id}:48` | **manter** | conservative-default | sim |
| endpoint | `dashboard` | `/api/dashboard/:38` | **manter** | conservative-default | sim |
| endpoint | `relatorio_mensal` | `/api/dashboard/relatorio-mensal:195` | **manter** | conservative-default | sim |
| endpoint | `listar_data_rooms` | `/api/data-rooms:253` | **consolidar** | parent-override | não |
| endpoint | `criar_data_room` | `/api/data-rooms:287` | **consolidar** | parent-override | não |
| endpoint | `obter_data_room` | `/api/data-rooms/{room_id}:309` | **consolidar** | parent-override | não |
| endpoint | `adicionar_arquivo` | `/api/data-rooms/{room_id}/arquivos:379` | **consolidar** | parent-override | não |
| endpoint | `remover_arquivo` | `/api/data-rooms/{room_id}/arquivos/{arquivo_id}:432` | **consolidar** | parent-override | não |
| endpoint | `gerar_link` | `/api/data-rooms/{room_id}/links:467` | **consolidar** | parent-override | não |
| endpoint | `revogar_link` | `/api/data-rooms/{room_id}/links/{link_id}:507` | **consolidar** | parent-override | não |
| endpoint | `acessar_link_publico` | `/api/data-rooms/acesso/{token}:546` | **consolidar** | parent-override | não |
| endpoint | `remover_data_room` | `/api/data-rooms/{room_id}:627` | **consolidar** | parent-override | não |
| endpoint | `criar_sala` | `/api/data-room-v4/:127` | **consolidar** | parent-override | não |
| endpoint | `listar_salas` | `/api/data-room-v4/:167` | **consolidar** | parent-override | não |
| endpoint | `lookup_process` | `/api/v1/datajud/process/{numero_cnj}:27` | **manter** | conservative-default | sim |
| endpoint | `sync_case` | `/api/v1/datajud/cases/{case_id}/sync:68` | **manter** | conservative-default | sim |
| endpoint | `sync_prazos` | `/api/v1/datajud/cases/{case_id}/sync-prazos:110` | **manter** | conservative-default | sim |
| endpoint | `consultar_status_feed` | `/api/{case_id}/andamentos/inteligencia:19` | **desativar** | mount-analysis | sim |
| endpoint | `alimentar_inteligencia_do_caso` | `/api/{case_id}/andamentos/alimentar-ia:32` | **desativar** | mount-analysis | sim |
| endpoint | `reconstruir_feed_lote` | `/api/inteligencia/datajud/reconstruir-lote:62` | **desativar** | mount-analysis | sim |
| endpoint | `calcular` | `/api/deadlines/calcular:70` | **manter** | conservative-default | sim |
| endpoint | `listar` | `/api/deadlines/:90` | **manter** | conservative-default | sim |
| endpoint | `exportar_csv` | `/api/deadlines/export.csv:137` | **manter** | conservative-default | sim |
| endpoint | `criar` | `/api/deadlines/:190` | **manter** | conservative-default | sim |
| endpoint | `atualizar` | `/api/deadlines/{deadline_id}:233` | **manter** | conservative-default | sim |
| endpoint | `confirmar` | `/api/deadlines/{deadline_id}/confirmar:283` | **manter** | conservative-default | sim |
| endpoint | `confirmar_ciencia` | `/api/deadlines/{deadline_id}/ciencia:315` | **manter** | conservative-default | sim |
| endpoint | `cancelar` | `/api/deadlines/{deadline_id}:342` | **manter** | conservative-default | sim |
| endpoint | `meta` | `/api/defesas-revisoes/meta:239` | **desativar** | mount-analysis | sim |
| endpoint | `analisar` | `/api/defesas-revisoes/analisar:256` | **desativar** | mount-analysis | sim |
| endpoint | `comparar_documentos` | `/api/defesas-revisoes/avancado/comparar-documentos:191` | **desativar** | mount-analysis | sim |
| endpoint | `critica_adversarial` | `/api/defesas-revisoes/avancado/adversarial:222` | **desativar** | mount-analysis | sim |
| endpoint | `calcular_viabilidade` | `/api/defesas-revisoes/avancado/viabilidade:257` | **desativar** | mount-analysis | sim |
| endpoint | `calcular_especialidade` | `/api/defesas-revisoes/avancado/calcular-especialidade:288` | **desativar** | mount-analysis | sim |
| endpoint | `persistir_resultado` | `/api/defesas-revisoes/avancado/persistir:350` | **desativar** | mount-analysis | sim |
| endpoint | `analisar_decisao` | `/api/defesas-revisoes/avancado/analisar-decisao:451` | **desativar** | mount-analysis | sim |
| endpoint | `memoria_institucional` | `/api/defesas-revisoes/avancado/memoria/{modalidade}:486` | **desativar** | mount-analysis | sim |
| endpoint | `gerar_pacote_seguro` | `/api/defesas-revisoes/avancado/pacote:176` | **desativar** | mount-analysis | sim |
| endpoint | `get_resumo` | `/api/v1/despesas/resumo:28` | **manter** | conservative-default | sim |
| endpoint | `list_despesas` | `/api/v1/despesas:69` | **manter** | conservative-default | sim |
| endpoint | `export_despesas_csv` | `/api/v1/despesas/export/csv:110` | **manter** | conservative-default | sim |
| endpoint | `create_despesa` | `/api/v1/despesas:169` | **manter** | conservative-default | sim |
| endpoint | `update_despesa` | `/api/v1/despesas/{despesa_id}:208` | **manter** | conservative-default | sim |
| endpoint | `delete_despesa` | `/api/v1/despesas/{despesa_id}:244` | **manter** | conservative-default | sim |
| endpoint | `central_diagnostico` | `/api/diagnostico/central:36` | **manter** | conservative-default | sim |
| endpoint | `listar_keywords` | `/api/diario-oficial/keywords:50` | **manter** | conservative-default | sim |
| endpoint | `criar_keyword` | `/api/diario-oficial/keywords:65` | **manter** | conservative-default | sim |
| endpoint | `remover_keyword` | `/api/diario-oficial/keywords/{keyword_id}:79` | **manter** | conservative-default | sim |
| endpoint | `listar_alertas` | `/api/diario-oficial/alertas:98` | **manter** | conservative-default | sim |
| endpoint | `marcar_lido` | `/api/diario-oficial/alertas/{alerta_id}/marcar-lido:135` | **manter** | conservative-default | sim |
| endpoint | `contar_nao_lidos` | `/api/diario-oficial/alertas/nao-lidos/count:153` | **manter** | conservative-default | sim |
| endpoint | `calcular_acordo` | `/api/diplomacia-v3/calcular-acordo:41` | **manter** | conservative-default | sim |
| endpoint | `dossie_pressao` | `/api/diplomacia-v3/dossie-pressao:59` | **manter** | conservative-default | sim |
| endpoint | `analisar_magistrado` | `/api/diplomacia-v3/analisar-magistrado:123` | **manter** | conservative-default | sim |
| endpoint | `analisar` | `/api/documentos-ia/analisar:107` | **manter** | conservative-default | sim |
| endpoint | `analisar_url` | `/api/documentos-ia/analisar-url:208` | **manter** | conservative-default | sim |
| endpoint | `aplicar_acoes` | `/api/documentos-ia/aplicar-acoes:286` | **manter** | conservative-default | sim |
| endpoint | `listar_tipos` | `/api/documents/tipos:210` | **manter** | conservative-default | sim |
| endpoint | `sugerir_tipo_documento` | `/api/documents/sugerir-tipo:242` | **manter** | conservative-default | sim |
| endpoint | `upload` | `/api/documents/upload:305` | **manter** | conservative-default | sim |
| endpoint | `listar` | `/api/documents/:453` | **manter** | conservative-default | sim |
| endpoint | `download` | `/api/documents/{doc_id}/download:574` | **manter** | conservative-default | sim |
| endpoint | `remover` | `/api/documents/{doc_id}:637` | **manter** | conservative-default | sim |
| endpoint | `atualizar_metadados` | `/api/documents/{doc_id}:669` | **manter** | conservative-default | sim |
| endpoint | `classificar_tipo_documento` | `/api/documents/{doc_id}/classificar:795` | **manter** | conservative-default | sim |
| endpoint | `upload_para_drive` | `/api/documents/drive/upload:859` | **manter** | conservative-default | sim |
| endpoint | `link_documento` | `/api/documents/drive/{file_id}/link:976` | **manter** | conservative-default | sim |
| endpoint | `download_documento` | `/api/documents/drive/{file_id}/download:1005` | **manter** | conservative-default | sim |
| endpoint | `deletar_documento_drive` | `/api/documents/drive/{file_id}:1051` | **manter** | conservative-default | sim |
| endpoint | `dossie_cliente` | `/api/clients/{client_id}/dossie:15` | **manter** | conservative-default | sim |
| endpoint | `gerar` | `/api/dossie/{case_id}/gerar:65` | **manter** | conservative-default | sim |
| endpoint | `obter_atual` | `/api/dossie/{case_id}:89` | **manter** | conservative-default | sim |
| endpoint | `modulos_deterministicos` | `/api/dossie/{case_id}/modulos:127` | **manter** | conservative-default | sim |
| endpoint | `historico` | `/api/dossie/{case_id}/historico:146` | **manter** | conservative-default | sim |
| endpoint | `aprovar` | `/api/dossie/{case_id}/{dossie_id}/aprovar:168` | **manter** | conservative-default | sim |
| endpoint | `exportar_pdf` | `/api/dossie/{case_id}/{dossie_id}/pdf:213` | **manter** | conservative-default | sim |
| endpoint | `meta` | `/api/entrada-universal/meta:174` | **desativar** | mount-analysis | sim |
| endpoint | `processar` | `/api/entrada-universal/processar:186` | **desativar** | mount-analysis | sim |
| endpoint | `obter_lote` | `/api/entrada-universal/{batch_id}:312` | **desativar** | mount-analysis | sim |
| endpoint | `preparar_pacote` | `/api/entrada-universal/{batch_id}/preparar-pacote:318` | **desativar** | mount-analysis | sim |
| endpoint | `vincular_lote_ao_caso` | `/api/entrada-universal/{batch_id}/vincular-caso:96` | **desativar** | mount-analysis | sim |
| endpoint | `listar` | `/api/environmental/:75` | **manter** | conservative-default | sim |
| endpoint | `criar` | `/api/environmental/:101` | **manter** | conservative-default | sim |
| endpoint | `atualizar` | `/api/environmental/{env_id}:144` | **manter** | conservative-default | sim |
| endpoint | `remover` | `/api/environmental/{env_id}:185` | **manter** | conservative-default | sim |
| endpoint | `listar` | `/api/etiquetas:32` | **manter** | conservative-default | sim |
| endpoint | `criar` | `/api/etiquetas:38` | **manter** | conservative-default | sim |
| endpoint | `remover` | `/api/etiquetas/{etiqueta_id}:51` | **manter** | conservative-default | sim |
| endpoint | `do_caso` | `/api/cases/{case_id}/etiquetas:60` | **manter** | conservative-default | sim |
| endpoint | `atribuir` | `/api/cases/{case_id}/etiquetas:72` | **manter** | conservative-default | sim |
| endpoint | `desatribuir` | `/api/cases/{case_id}/etiquetas/{etiqueta_id}:91` | **manter** | conservative-default | sim |
| endpoint | `evolution_webhook` | `/api/webhooks/evolution:58` | **manter** | conservative-default | sim |
| endpoint | `preview_rateio` | `/api/honorarios-exito/{fee_id}/rateio:96` | **manter** | conservative-default | sim |
| endpoint | `gerar_rateio` | `/api/honorarios-exito/{fee_id}/rateio:107` | **manter** | conservative-default | sim |
| endpoint | `export_clientes` | `/api/export/clientes.csv:46` | **manter** | conservative-default | sim |
| endpoint | `export_casos` | `/api/export/casos.csv:64` | **manter** | conservative-default | sim |
| endpoint | `export_caso_pdf` | `/api/export/casos/{case_id}.pdf:82` | **manter** | conservative-default | sim |
| endpoint | `export_docx` | `/api/export/docx:152` | **manter** | conservative-default | sim |
| endpoint | `export_honorarios` | `/api/export/honorarios.csv:184` | **manter** | conservative-default | sim |
| endpoint | `extrato_caso` | `/api/extratos/detalhado/{case_id}:20` | **manter** | conservative-default | sim |
| endpoint | `extrato_advogado` | `/api/extratos/advogado/{user_id}:47` | **manter** | conservative-default | sim |
| endpoint | `extrato_socio` | `/api/extratos/socio/{user_id}:76` | **manter** | conservative-default | sim |
| endpoint | `listar` | `/api/fees/:73` | **manter** | conservative-default | sim |
| endpoint | `resumo` | `/api/fees/resumo:122` | **manter** | conservative-default | sim |
| endpoint | `criar` | `/api/fees/:153` | **manter** | conservative-default | sim |
| endpoint | `atualizar` | `/api/fees/{fee_id}:187` | **manter** | conservative-default | sim |
| endpoint | `registrar_pagamento` | `/api/fees/{fee_id}/pagamentos:226` | **manter** | conservative-default | sim |
| endpoint | `cancelar` | `/api/fees/{fee_id}:284` | **manter** | conservative-default | sim |
| endpoint | `pre_preencher_ficha` | `/api/triagem/ficha/pre-preencher:98` | **manter** | conservative-default | sim |
| endpoint | `obter_ficha` | `/api/triagem/ficha:112` | **manter** | conservative-default | sim |
| endpoint | `salvar_ficha` | `/api/triagem/ficha:125` | **manter** | conservative-default | sim |
| endpoint | `consolidado` | `/api/financeiro/consolidado:45` | **manter** | conservative-default | sim |
| endpoint | `listar_socios` | `/api/sociedade/socios:72` | **manter** | conservative-default | sim |
| endpoint | `cadastrar_socio` | `/api/sociedade/socios:91` | **manter** | conservative-default | sim |
| endpoint | `atualizar_socio` | `/api/sociedade/socios/{socio_id}:111` | **manter** | conservative-default | sim |
| endpoint | `calcular_distribuicao` | `/api/sociedade/distribuicao:132` | **manter** | conservative-default | sim |
| endpoint | `listar_distribuicoes` | `/api/sociedade/distribuicao:207` | **manter** | conservative-default | sim |
| endpoint | `aprovar_distribuicao` | `/api/sociedade/distribuicao/{dist_id}/aprovar:235` | **manter** | conservative-default | sim |
| endpoint | `status_google_drive` | `/api/google-drive/status:33` | **desativar** | mount-analysis | sim |
| endpoint | `listar_arquivos_google_drive` | `/api/google-drive/files:55` | **desativar** | mount-analysis | sim |
| endpoint | `auditar_google_drive` | `/api/google-drive/audit:75` | **desativar** | mount-analysis | sim |
| endpoint | `preview_curadoria_google_drive` | `/api/google-drive/curadoria/preview:94` | **desativar** | mount-analysis | sim |
| endpoint | `aplicar_curadoria_google_drive` | `/api/google-drive/curadoria/apply:117` | **desativar** | mount-analysis | sim |
| endpoint | `sincronizar_google_drive` | `/api/google-drive/sync:158` | **desativar** | mount-analysis | sim |
| endpoint | `reindexar_arquivo_google_drive` | `/api/google-drive/reindex/{file_id}:183` | **desativar** | mount-analysis | sim |
| endpoint | `provisionamento` | `/api/honorarios-calc/cases/{case_id}/provisionamento:44` | **manter** | conservative-default | sim |
| endpoint | `teto_etico` | `/api/honorarios-calc/cases/{case_id}/teto-etico:68` | **manter** | conservative-default | sim |
| endpoint | `itens_tabela` | `/api/honorarios-oab/tabela:80` | **manter** | conservative-default | sim |
| endpoint | `estimar` | `/api/honorarios-oab/estimar:89` | **manter** | conservative-default | sim |
| endpoint | `listar_itens` | `/api/honorarios-oab/itens:195` | **manter** | conservative-default | sim |
| endpoint | `criar_item` | `/api/honorarios-oab/itens:216` | **manter** | conservative-default | sim |
| endpoint | `encerrar_vigencia` | `/api/honorarios-oab/itens/{item_id}/encerrar-vigencia:270` | **manter** | conservative-default | sim |
| endpoint | `sugerir_proposta_honorarios` | `/api/honorarios-oab/casos/{case_id}/proposta/sugerir:357` | **manter** | conservative-default | sim |
| endpoint | `criar_proposta_honorarios` | `/api/honorarios-oab/casos/{case_id}/proposta:375` | **manter** | conservative-default | sim |
| endpoint | `obter_propostas_honorarios` | `/api/honorarios-oab/casos/{case_id}/proposta:407` | **manter** | conservative-default | sim |
| endpoint | `aprovar_proposta_honorarios` | `/api/honorarios-oab/propostas/{proposta_id}/aprovar:429` | **manter** | conservative-default | sim |
| endpoint | `rejeitar_proposta_honorarios` | `/api/honorarios-oab/propostas/{proposta_id}/rejeitar:444` | **manter** | conservative-default | sim |
| endpoint | `critica_adversarial_endpoint` | `/api/ia/critica-adversarial:44` | **consolidar** | parent-override | não |
| endpoint | `agente_stream` | `/api/ia/agente/stream:37` | **consolidar** | parent-override | não |
| endpoint | `validar_citacoes_endpoint` | `/api/ia/validar-citacoes:30` | **consolidar** | parent-override | não |
| endpoint | `status_ia_defensiva` | `/api/ia-defensiva/status:50` | **consolidar** | parent-override | não |
| endpoint | `historico_ia_defensiva` | `/api/ia-defensiva/historico/{case_id}:98` | **consolidar** | parent-override | não |
| endpoint | `atualizar_status_ia_defensiva` | `/api/ia-defensiva/historico/{log_id}/status:146` | **consolidar** | parent-override | não |
| endpoint | `analisar_ia_defensiva` | `/api/ia-defensiva/analisar:176` | **consolidar** | parent-override | não |
| endpoint | `listar_perfis` | `/api/ia-especializada/perfis:51` | **consolidar** | parent-override | não |
| endpoint | `consultar` | `/api/ia-especializada/{perfil}:56` | **consolidar** | parent-override | não |
| endpoint | `traduzir_andamento` | `/api/ai/traduzir-andamento:82` | **consolidar** | parent-override | não |
| endpoint | `resumir_texto` | `/api/ai/resumir-texto:114` | **consolidar** | parent-override | não |
| endpoint | `gerar_minuta` | `/api/ai/gerar-minuta:151` | **consolidar** | parent-override | não |
| endpoint | `pesquisar` | `/api/ai/pesquisar:197` | **consolidar** | parent-override | não |
| endpoint | `sugestao_honorarios` | `/api/ai/sugestao-honorarios:255` | **consolidar** | parent-override | não |
| endpoint | `dashboard_governanca` | `/api/ia-governanca/dashboard:228` | **manter** | parent-override | não |
| endpoint | `listar_curadoria` | `/api/ia-governanca/rag-curadoria:369` | **manter** | parent-override | não |
| endpoint | `atualizar_curadoria` | `/api/ia-governanca/rag-curadoria/{doc_id}:428` | **manter** | parent-override | não |
| endpoint | `governanca_prompts` | `/api/ia-governanca/prompts:452` | **manter** | parent-override | não |
| endpoint | `fontes_ingestao` | `/api/ia-governanca/fontes:469` | **manter** | parent-override | não |
| endpoint | `coletar_tjmg_agora` | `/api/ia-governanca/fontes/tjmg/coletar:486` | **manter** | parent-override | não |
| endpoint | `guardrails` | `/api/ia-governanca/guardrails:515` | **manter** | parent-override | não |
| endpoint | `geometria_jurisprudencia_mg` | `/api/ia-governanca/jurisprudencia-mg/geometria:533` | **manter** | parent-override | não |
| endpoint | `importar_jurisprudencia_mg` | `/api/ia-governanca/jurisprudencia-mg:557` | **manter** | parent-override | não |
| endpoint | `extrair_jurisprudencia_url` | `/api/ia-governanca/jurisprudencia-mg/extrair-url:620` | **manter** | parent-override | não |
| endpoint | `listar_jurisprudencia_mg` | `/api/ia-governanca/jurisprudencia-mg:658` | **manter** | parent-override | não |
| endpoint | `painel_provedores` | `/api/ia-governanca/provedores:52` | **desativar** | mount-analysis | sim |
| endpoint | `ia_status` | `/api/ia/status:29` | **consolidar** | parent-override | não |
| endpoint | `dashboard` | `/api/ia-saude/dashboard:45` | **consolidar** | parent-override | não |
| endpoint | `estado_operacional` | `/api/ia-saude/estado-operacional:86` | **consolidar** | parent-override | não |
| endpoint | `get_indice` | `/api/cases/{case_id}/indice-risco:24` | **manter** | conservative-default | sim |
| endpoint | `recalcular` | `/api/cases/{case_id}/indice-risco/recalcular:49` | **manter** | conservative-default | sim |
| endpoint | `series` | `/api/indices/series:59` | **manter** | conservative-default | sim |
| endpoint | `taxa_juros` | `/api/indices/taxa-juros:66` | **manter** | conservative-default | sim |
| endpoint | `ptax` | `/api/indices/ptax:84` | **manter** | conservative-default | sim |
| endpoint | `atualizar_valor` | `/api/indices/atualizar-valor:104` | **manter** | conservative-default | sim |
| endpoint | `serie_periodo` | `/api/indices/{indice}:137` | **manter** | conservative-default | sim |
| endpoint | `consultar_cpf` | `/api/infosimples/receita/cpf:141` | **manter** | conservative-default | sim |
| endpoint | `consultar_cnpj` | `/api/infosimples/receita/cnpj:174` | **manter** | conservative-default | sim |
| endpoint | `status_infosimples` | `/api/infosimples/status:67` | **manter** | conservative-default | sim |
| endpoint | `consultar_processo_tjmg` | `/api/infosimples/tjmg/processo:79` | **manter** | conservative-default | sim |
| endpoint | `analise_completa` | `/api/intake/casos/{case_id}/analise-completa:362` | **manter** | conservative-default | sim |
| endpoint | `radar_legislativo` | `/api/intelligence-v3/radar/legislativo:19` | **consolidar** | parent-override | não |
| endpoint | `analise_impacto` | `/api/intelligence-v3/analise-impacto:37` | **consolidar** | parent-override | não |
| endpoint | `listar` | `/api/intimacoes/:161` | **manter** | conservative-default | sim |
| endpoint | `status_captura` | `/api/intimacoes/status-captura:194` | **manter** | conservative-default | sim |
| endpoint | `processar` | `/api/intimacoes/{com_id}/processar:280` | **manter** | conservative-default | sim |
| endpoint | `sugerir_prazo` | `/api/intimacoes/{com_id}/sugerir-prazo:300` | **manter** | conservative-default | sim |
| endpoint | `prazo_sugerido` | `/api/intimacoes/{com_id}/prazo-sugerido:318` | **manter** | conservative-default | sim |
| endpoint | `aceitar_prazo` | `/api/intimacoes/{com_id}/aceitar-prazo:339` | **manter** | conservative-default | sim |
| endpoint | `recusar_prazo` | `/api/intimacoes/{com_id}/recusar-prazo:458` | **manter** | conservative-default | sim |
| endpoint | `capturar_agora` | `/api/intimacoes/capturar-agora:480` | **manter** | conservative-default | sim |
| endpoint | `jornada_do_caso` | `/api/casos/{case_id}/jornada:335` | **manter** | conservative-default | sim |
| endpoint | `overview` | `/api/jurimetria/overview:29` | **manter** | conservative-default | sim |
| endpoint | `por_area` | `/api/jurimetria/por-area:80` | **manter** | conservative-default | sim |
| endpoint | `por_magistrado` | `/api/jurimetria/por-magistrado:117` | **manter** | conservative-default | sim |
| endpoint | `por_tribunal` | `/api/jurimetria/por-tribunal:158` | **manter** | conservative-default | sim |
| endpoint | `por_tese` | `/api/jurimetria/por-tese:196` | **manter** | conservative-default | sim |
| endpoint | `tendencias` | `/api/jurimetria/tendencias:233` | **manter** | conservative-default | sim |
| endpoint | `predicao_exito` | `/api/jurimetria/predicao-exito:266` | **manter** | conservative-default | sim |
| endpoint | `desfechos` | `/api/jurimetria/desfechos:61` | **manter** | conservative-default | sim |
| endpoint | `ext_stats` | `/api/jurimetria/ext/stats:76` | **manter** | conservative-default | sim |
| endpoint | `ext_benchmarks` | `/api/jurimetria/ext/benchmarks:87` | **manter** | conservative-default | sim |
| endpoint | `predicao_provimento` | `/api/jurimetria/ext/predicao/provimento:108` | **manter** | conservative-default | sim |
| endpoint | `predicao_treinar` | `/api/jurimetria/ext/predicao/treinar:169` | **manter** | conservative-default | sim |
| endpoint | `ingerir_datajud` | `/api/jurimetria/ext/ingerir/datajud:174` | **manter** | conservative-default | sim |
| endpoint | `importar_jurisprudencia` | `/api/conhecimento/importar-jurisprudencia:53` | **manter** | conservative-default | sim |
| endpoint | `listar_fontes` | `/api/conhecimento/importar-jurisprudencia/fontes:87` | **manter** | conservative-default | sim |
| endpoint | `status_importacao` | `/api/conhecimento/importar-jurisprudencia/status/{job_id}:110` | **manter** | conservative-default | sim |
| endpoint | `buscar` | `/api/jurisprudencia-externa/buscar:34` | **manter** | conservative-default | sim |
| endpoint | `buscar_lexml_endpoint` | `/api/jurisprudencia-externa/buscar/lexml:54` | **manter** | conservative-default | sim |
| endpoint | `buscar_tjmg_endpoint` | `/api/jurisprudencia-externa/buscar/tjmg:69` | **manter** | conservative-default | sim |
| endpoint | `importar_para_base` | `/api/jurisprudencia-externa/importar:83` | **manter** | conservative-default | sim |
| endpoint | `importar_lote` | `/api/jurisprudencia-externa/importar-lote:153` | **manter** | conservative-default | sim |
| endpoint | `status_fontes` | `/api/jurisprudencia-externa/fontes:209` | **manter** | conservative-default | sim |
| endpoint | `listar_jurisprudencias` | `/api/jurisprudencias:80` | **manter** | conservative-default | sim |
| endpoint | `criar_jurisprudencia` | `/api/jurisprudencias:117` | **manter** | conservative-default | sim |
| endpoint | `obter_jurisprudencia` | `/api/jurisprudencias/{juri_id}:131` | **manter** | conservative-default | sim |
| endpoint | `atualizar_jurisprudencia` | `/api/jurisprudencias/{juri_id}:152` | **manter** | conservative-default | sim |
| endpoint | `remover_jurisprudencia` | `/api/jurisprudencias/{juri_id}:176` | **manter** | conservative-default | sim |
| endpoint | `classificar_com_ia` | `/api/jurisprudencias/{juri_id}/classificar-ia:196` | **manter** | conservative-default | sim |
| endpoint | `list_kanban_columns` | `/api/v1/kanban-columns:44` | **manter** | conservative-default | sim |
| endpoint | `update_case_kanban` | `/api/v1/cases/{case_id}/kanban:58` | **manter** | conservative-default | sim |
| endpoint | `gerar_kit_documental` | `/api/cases/{case_id}/kit-documental:58` | **manter** | conservative-default | sim |
| endpoint | `listar` | `/api/legal-docs/:279` | **manter** | parent-override | não |
| endpoint | `criar` | `/api/legal-docs/:321` | **manter** | parent-override | não |
| endpoint | `detalhe` | `/api/legal-docs/{doc_id}:349` | **manter** | parent-override | não |
| endpoint | `status_validacao_juridica` | `/api/legal-docs/{doc_id}/validacao:370` | **manter** | parent-override | não |
| endpoint | `validar_peca_juridica` | `/api/legal-docs/{doc_id}/validar:384` | **manter** | parent-override | não |
| endpoint | `atualizar` | `/api/legal-docs/{doc_id}:414` | **manter** | parent-override | não |
| endpoint | `checar_jurisprudencia_peca` | `/api/legal-docs/{doc_id}/jurisprudencia-check:467` | **manter** | parent-override | não |
| endpoint | `revisar` | `/api/legal-docs/{doc_id}/revisar:481` | **manter** | parent-override | não |
| endpoint | `aprovar` | `/api/legal-docs/{doc_id}/aprovar:517` | **manter** | parent-override | não |
| endpoint | `registrar_protocolo` | `/api/legal-docs/{doc_id}/protocolo:573` | **manter** | parent-override | não |
| endpoint | `remover` | `/api/legal-docs/{doc_id}:677` | **manter** | parent-override | não |
| endpoint | `exportar_pdf` | `/api/legal-docs/{doc_id}/pdf:747` | **manter** | parent-override | não |
| endpoint | `documento_unico_impressao` | `/api/legal-docs/{doc_id}/documento-unico-impressao:798` | **manter** | parent-override | não |
| endpoint | `exportar_docx` | `/api/legal-docs/{doc_id}/exportar-docx:930` | **manter** | parent-override | não |
| endpoint | `listar` | `/api/lgpd/registros:136` | **manter** | conservative-default | sim |
| endpoint | `criar` | `/api/lgpd/registros:160` | **manter** | conservative-default | sim |
| endpoint | `atualizar` | `/api/lgpd/registros/{registro_id}:197` | **manter** | conservative-default | sim |
| endpoint | `remover` | `/api/lgpd/registros/{registro_id}:219` | **manter** | conservative-default | sim |
| endpoint | `resumo` | `/api/lgpd/registros/{client_id}/resumo:251` | **manter** | conservative-default | sim |
| endpoint | `gerar_ripd` | `/api/lgpd/registros/{client_id}/ripd:375` | **manter** | conservative-default | sim |
| endpoint | `download_ripd` | `/api/lgpd/registros/ripd/{arquivo_id}/download:420` | **manter** | conservative-default | sim |
| endpoint | `montar` | `/api/cases/{case_id}/matriz-teses/montar:50` | **manter** | conservative-default | sim |
| endpoint | `obter` | `/api/cases/{case_id}/matriz-teses:90` | **manter** | conservative-default | sim |
| endpoint | `aprovar` | `/api/cases/{case_id}/matriz-teses/teses/{tese_id}/aprovar:111` | **manter** | conservative-default | sim |
| endpoint | `descartar` | `/api/cases/{case_id}/matriz-teses/teses/{tese_id}/descartar:123` | **manter** | conservative-default | sim |
| endpoint | `listar` | `/api/memoria-institucional:60` | **manter** | conservative-default | sim |
| endpoint | `criar` | `/api/memoria-institucional:89` | **manter** | conservative-default | sim |
| endpoint | `obter` | `/api/memoria-institucional/{mem_id}:125` | **manter** | conservative-default | sim |
| endpoint | `atualizar` | `/api/memoria-institucional/{mem_id}:142` | **manter** | conservative-default | sim |
| endpoint | `remover` | `/api/memoria-institucional/{mem_id}:172` | **manter** | conservative-default | sim |
| endpoint | `listar_mensagens` | `/api/cases/{case_id}/mensagens:45` | **manter** | conservative-default | sim |
| endpoint | `enviar_mensagem` | `/api/cases/{case_id}/mensagens:70` | **manter** | conservative-default | sim |
| endpoint | `buscar_ajuda` | `/api/module-help/:51` | **manter** | conservative-default | sim |
| endpoint | `diagnostico_sistema` | `/api/module-help/diagnostico-sistema:66` | **manter** | conservative-default | sim |
| endpoint | `preencher_minimo` | `/api/module-help/preencher-minimo:75` | **manter** | conservative-default | sim |
| endpoint | `ajuda_do_modulo` | `/api/module-help/{module_key:path}:83` | **manter** | conservative-default | sim |
| endpoint | `criar_ajuda` | `/api/module-help/:99` | **manter** | conservative-default | sim |
| endpoint | `atualizar_ajuda` | `/api/module-help/{help_id}:112` | **manter** | conservative-default | sim |
| endpoint | `desativar_ajuda` | `/api/module-help/{help_id}:131` | **manter** | conservative-default | sim |
| endpoint | `listar_module_settings` | `/api/system-modules/settings:59` | **manter** | conservative-default | sim |
| endpoint | `salvar_module_setting` | `/api/system-modules/settings/{module_key}:82` | **manter** | conservative-default | sim |
| endpoint | `remover_module_setting` | `/api/system-modules/settings/{module_key}:140` | **manter** | conservative-default | sim |
| endpoint | `analisar` | `/api/cases/{case_id}/motor-peca/analisar:104` | **manter** | conservative-default | sim |
| endpoint | `gerar` | `/api/cases/{case_id}/motor-peca/gerar:247` | **manter** | conservative-default | sim |
| endpoint | `recentes` | `/api/movimentos/recentes:16` | **manter** | conservative-default | sim |
| endpoint | `status_nfse` | `/api/nfse/status:344` | **manter** | conservative-default | sim |
| endpoint | `listar_nfse` | `/api/nfse:357` | **manter** | conservative-default | sim |
| endpoint | `registrar_nfse_manual` | `/api/nfse/manual:391` | **manter** | conservative-default | sim |
| endpoint | `cancelar_nfse_manual` | `/api/nfse/manual/{nota_id}/cancelar:519` | **manter** | conservative-default | sim |
| endpoint | `emitir_nfse` | `/api/nfse/emitir:558` | **manter** | conservative-default | sim |
| endpoint | `obter_nfse` | `/api/nfse/{nota_id}:711` | **manter** | conservative-default | sim |
| endpoint | `baixar_pdf_nfse` | `/api/nfse/{nota_id}/pdf:738` | **manter** | conservative-default | sim |
| endpoint | `baixar_xml_nfse` | `/api/nfse/{nota_id}/xml:774` | **manter** | conservative-default | sim |
| endpoint | `cancelar_nfse` | `/api/nfse/{nota_id}/cancelar:810` | **manter** | conservative-default | sim |
| endpoint | `listar_noticias` | `/api/noticias:79` | **manter** | conservative-default | sim |
| endpoint | `listar` | `/api/notifications/:39` | **manter** | conservative-default | sim |
| endpoint | `obter_preferencias` | `/api/notifications/preferences:78` | **manter** | conservative-default | sim |
| endpoint | `atualizar_preferencias` | `/api/notifications/preferences:87` | **manter** | conservative-default | sim |
| endpoint | `marcar_lida` | `/api/notifications/{notif_id}/ler:123` | **manter** | conservative-default | sim |
| endpoint | `marcar_todas` | `/api/notifications/ler-todas:140` | **manter** | conservative-default | sim |
| endpoint | `vapid_key` | `/api/notifications/push/vapid-key:171` | **manter** | conservative-default | sim |
| endpoint | `listar_dispositivos_push` | `/api/notifications/push/subscriptions:179` | **manter** | conservative-default | sim |
| endpoint | `revogar_dispositivo_push` | `/api/notifications/push/subscriptions/{subscription_id}:199` | **manter** | conservative-default | sim |
| endpoint | `push_subscribe` | `/api/notifications/push/subscribe:230` | **manter** | conservative-default | sim |
| endpoint | `precificacao_tabela` | `/api/precificacao/tabela:37` | **manter** | conservative-default | sim |
| endpoint | `precificacao_calcular` | `/api/precificacao/calcular/{rule_id}:48` | **manter** | conservative-default | sim |
| endpoint | `criar_regra` | `/api/precificacao/regras:78` | **manter** | conservative-default | sim |
| endpoint | `inadimplencia_alertas` | `/api/inadimplencia/alertas:94` | **manter** | conservative-default | sim |
| endpoint | `inadimplencia_varrer` | `/api/inadimplencia/varrer:109` | **manter** | conservative-default | sim |
| endpoint | `resolver_alerta` | `/api/inadimplencia/alertas/{alert_id}/resolver:124` | **manter** | conservative-default | sim |
| endpoint | `get_ambiental` | `/api/casos/{case_id}/ambiental:165` | **manter** | conservative-default | sim |
| endpoint | `upsert_ambiental` | `/api/casos/{case_id}/ambiental:182` | **manter** | conservative-default | sim |
| endpoint | `listar_templates` | `/api/due-diligence/templates:257` | **manter** | conservative-default | sim |
| endpoint | `criar_template` | `/api/due-diligence/templates:285` | **manter** | conservative-default | sim |
| endpoint | `cofre_logs` | `/api/cofre/documentos/{document_id}/logs:311` | **manter** | conservative-default | sim |
| endpoint | `cofre_registrar_acesso` | `/api/cofre/documentos/{document_id}/registrar-acesso:341` | **manter** | conservative-default | sim |
| endpoint | `cofre_sensibilidade` | `/api/cofre/documentos/{document_id}/sensibilidade:394` | **manter** | conservative-default | sim |
| endpoint | `cofre_relatorio` | `/api/cofre/relatorio:425` | **manter** | conservative-default | sim |
| endpoint | `registrar_erro_frontend` | `/api/observabilidade/frontend-error:28` | **manter** | conservative-default | sim |
| endpoint | `list_contracts` | `/api/v1/office-contracts:24` | **manter** | conservative-default | sim |
| endpoint | `list_expiring` | `/api/v1/office-contracts/expiring:47` | **manter** | conservative-default | sim |
| endpoint | `create_contract` | `/api/v1/office-contracts:60` | **manter** | conservative-default | sim |
| endpoint | `get_contract` | `/api/v1/office-contracts/{contract_id}:91` | **manter** | conservative-default | sim |
| endpoint | `update_contract` | `/api/v1/office-contracts/{contract_id}:104` | **manter** | conservative-default | sim |
| endpoint | `delete_contract` | `/api/v1/office-contracts/{contract_id}:134` | **manter** | conservative-default | sim |
| endpoint | `visao` | `/api/cases/{case_id}/orquestrador:49` | **manter** | conservative-default | sim |
| endpoint | `avancar` | `/api/cases/{case_id}/orquestrador/avancar:64` | **manter** | conservative-default | sim |
| endpoint | `list_withdrawals` | `/api/v1/partner-withdrawals:24` | **manter** | conservative-default | sim |
| endpoint | `create_withdrawal` | `/api/v1/partner-withdrawals:55` | **manter** | conservative-default | sim |
| endpoint | `approve_withdrawal` | `/api/v1/partner-withdrawals/{withdrawal_id}/approve:95` | **manter** | conservative-default | sim |
| endpoint | `reject_withdrawal` | `/api/v1/partner-withdrawals/{withdrawal_id}/reject:124` | **manter** | conservative-default | sim |
| endpoint | `pay_withdrawal` | `/api/v1/partner-withdrawals/{withdrawal_id}/pay:148` | **manter** | conservative-default | sim |
| endpoint | `delete_withdrawal` | `/api/v1/partner-withdrawals/{withdrawal_id}:176` | **manter** | conservative-default | sim |
| endpoint | `meta_pecas` | `/api/pecas/meta:68` | **consolidar** | parent-override | não |
| endpoint | `gerar_peca` | `/api/pecas/gerar:95` | **consolidar** | parent-override | não |
| endpoint | `listar_pecas` | `/api/pecas/:223` | **consolidar** | parent-override | não |
| endpoint | `deep_research_juridica` | `/api/pecas/deep-research/juridica:282` | **consolidar** | parent-override | não |
| endpoint | `gerar_demonstrativo` | `/api/pecas/demonstrativo:324` | **consolidar** | parent-override | não |
| endpoint | `listar_templates` | `/api/document-templates/:22` | **consolidar** | parent-override | não |
| endpoint | `gerar_documento` | `/api/document-templates/generate:28` | **consolidar** | parent-override | não |
| endpoint | `list_pending_items` | `/api/v1/clients/{client_id}/pending-items:36` | **manter** | conservative-default | sim |
| endpoint | `create_pending_item` | `/api/v1/clients/{client_id}/pending-items:54` | **manter** | conservative-default | sim |
| endpoint | `update_pending_item` | `/api/v1/clients/{client_id}/pending-items/{item_id}:84` | **manter** | conservative-default | sim |
| endpoint | `delete_pending_item` | `/api/v1/clients/{client_id}/pending-items/{item_id}:112` | **manter** | conservative-default | sim |
| endpoint | `cobranca` | `/api/pix/cobranca:62` | **manter** | conservative-default | sim |
| endpoint | `status_pncp` | `/api/pncp/status:33` | **manter** | conservative-default | sim |
| endpoint | `listar_contratacoes` | `/api/pncp/contratacoes:42` | **manter** | conservative-default | sim |
| endpoint | `meus_casos` | `/api/portal/meus-casos:34` | **manter** | conservative-default | sim |
| endpoint | `caso_detalhe` | `/api/portal/casos/{case_id}:81` | **manter** | conservative-default | sim |
| endpoint | `documentos` | `/api/portal/documentos:124` | **manter** | conservative-default | sim |
| endpoint | `financeiro` | `/api/portal/financeiro:145` | **manter** | conservative-default | sim |
| endpoint | `mensagens_nao_lidas` | `/api/portal/mensagens/nao-lidas:185` | **manter** | conservative-default | sim |
| endpoint | `listar_mensagens_portal` | `/api/portal/casos/{case_id}/mensagens:209` | **manter** | conservative-default | sim |
| endpoint | `enviar_mensagem_portal` | `/api/portal/casos/{case_id}/mensagens:235` | **manter** | conservative-default | sim |
| endpoint | `listar_solicitacoes_portal` | `/api/portal/solicitacoes-documentos:62` | **manter** | conservative-default | sim |
| endpoint | `upload_item_solicitacao` | `/api/portal/solicitacoes-documentos/itens/{item_id}/upload:123` | **manter** | conservative-default | sim |
| endpoint | `buscar_precedentes_endpoint` | `/api/precedentes/buscar:35` | **desativar** | mount-analysis | sim |
| endpoint | `regras_transicao` | `/api/previdenciario/ferramentas/regras-transicao:82` | **manter** | conservative-default | sim |
| endpoint | `parecer_pdf` | `/api/previdenciario/ferramentas/parecer-pdf:206` | **manter** | conservative-default | sim |
| endpoint | `download_parecer` | `/api/previdenciario/ferramentas/parecer/{arquivo_id}/download:232` | **manter** | conservative-default | sim |
| endpoint | `listar_processos` | `/api/cases/{case_id}/processes:38` | **corrigir** | parent-override | não |
| endpoint | `criar_processo` | `/api/cases/{case_id}/processes:50` | **corrigir** | parent-override | não |
| endpoint | `atualizar_processo` | `/api/processes/{pid}:79` | **corrigir** | parent-override | não |
| endpoint | `definir_principal` | `/api/processes/{pid}/principal:109` | **corrigir** | parent-override | não |
| endpoint | `arquivar_processo` | `/api/processes/{pid}/arquivar:135` | **corrigir** | parent-override | não |
| endpoint | `desarquivar_processo` | `/api/processes/{pid}/desarquivar:169` | **corrigir** | parent-override | não |
| endpoint | `remover_processo` | `/api/processes/{pid}:195` | **corrigir** | parent-override | não |
| endpoint | `listar` | `/api/procuracoes/:40` | **manter** | conservative-default | sim |
| endpoint | `criar` | `/api/procuracoes/:79` | **manter** | conservative-default | sim |
| endpoint | `gerar_minuta` | `/api/procuracoes/{proc_id}/minuta:104` | **manter** | conservative-default | sim |
| endpoint | `revogar` | `/api/procuracoes/{proc_id}/revogar:161` | **manter** | conservative-default | sim |
| endpoint | `produtividade` | `/api/analytics/produtividade:25` | **manter** | conservative-default | sim |
| endpoint | `roi_por_area` | `/api/analytics/roi-por-area:92` | **manter** | conservative-default | sim |
| endpoint | `criar_prompt` | `/api/prompts-biblioteca/:42` | **manter** | conservative-default | sim |
| endpoint | `listar_prompts` | `/api/prompts-biblioteca/:50` | **manter** | conservative-default | sim |
| endpoint | `executar_prompt` | `/api/prompts-biblioteca/{prompt_id}/executar:59` | **manter** | conservative-default | sim |
| endpoint | `listar_prompts` | `/api/prompts-juridicos:106` | **manter** | conservative-default | sim |
| endpoint | `criar_prompt` | `/api/prompts-juridicos:140` | **manter** | conservative-default | sim |
| endpoint | `obter_prompt` | `/api/prompts-juridicos/{prompt_id}:160` | **manter** | conservative-default | sim |
| endpoint | `atualizar_prompt` | `/api/prompts-juridicos/{prompt_id}:177` | **manter** | conservative-default | sim |
| endpoint | `remover_prompt` | `/api/prompts-juridicos/{prompt_id}:208` | **manter** | conservative-default | sim |
| endpoint | `executar_prompt` | `/api/prompts-juridicos/{prompt_id}/executar:228` | **manter** | conservative-default | sim |
| endpoint | `listar_provas` | `/api/casos/{case_id}/provas:129` | **manter** | conservative-default | sim |
| endpoint | `criar_prova` | `/api/casos/{case_id}/provas:153` | **manter** | conservative-default | sim |
| endpoint | `atualizar_prova` | `/api/casos/{case_id}/provas/{prova_id}:187` | **manter** | conservative-default | sim |
| endpoint | `remover_prova` | `/api/casos/{case_id}/provas/{prova_id}:218` | **manter** | conservative-default | sim |
| endpoint | `sugerir_provas_faltantes` | `/api/casos/{case_id}/provas/sugerir-faltantes:382` | **manter** | conservative-default | sim |
| endpoint | `matriz_provas_referencia` | `/api/casos/{case_id}/provas/matriz:465` | **manter** | conservative-default | sim |
| endpoint | `gerar_documento_unico` | `/api/casos/{case_id}/provas/documento-unico:606` | **manter** | conservative-default | sim |
| endpoint | `download_documento_unico` | `/api/casos/{case_id}/provas/documento-unico/{arquivo_id}/download:668` | **manter** | conservative-default | sim |
| endpoint | `verificar` | `/api/qualidade/verificar-citacoes:68` | **manter** | conservative-default | sim |
| endpoint | `consistencia` | `/api/qualidade/consistencia:75` | **manter** | conservative-default | sim |
| endpoint | `simular_adversario` | `/api/qualidade/simular-adversario:91` | **manter** | conservative-default | sim |
| endpoint | `proposicoes` | `/api/radar-legislativo/proposicoes:24` | **manter** | conservative-default | sim |
| endpoint | `stats_conhecimento` | `/api/rag/stats:36` | **manter** | conservative-default | sim |
| endpoint | `status_indexacao_rag` | `/api/rag/status:52` | **manter** | conservative-default | sim |
| endpoint | `ingerir_pdf` | `/api/rag/ingest-pdf:164` | **manter** | conservative-default | sim |
| endpoint | `ingerir_url` | `/api/rag/ingest-url:205` | **manter** | conservative-default | sim |
| endpoint | `ingerir` | `/api/rag/ingest:308` | **manter** | conservative-default | sim |
| endpoint | `buscar` | `/api/rag/buscar:332` | **manter** | conservative-default | sim |
| endpoint | `match_casos` | `/api/rag/match-casos:365` | **manter** | conservative-default | sim |
| endpoint | `listar_docs` | `/api/rag/docs:377` | **manter** | conservative-default | sim |
| endpoint | `remover_doc` | `/api/rag/docs/{doc_id}:409` | **manter** | conservative-default | sim |
| endpoint | `monitor_legislativo` | `/api/rag/monitor-legislativo:427` | **manter** | conservative-default | sim |
| endpoint | `seed_base_conhecimento` | `/api/rag/seed:483` | **manter** | conservative-default | sim |
| endpoint | `ingest_fontes_oficiais` | `/api/rag/ingest-fontes-oficiais:535` | **manter** | conservative-default | sim |
| endpoint | `ingerir_ai_log_aprovado` | `/api/rag/ingerir-ai-log/{log_id}:594` | **manter** | conservative-default | sim |
| endpoint | `saude_base_conhecimento` | `/api/rag/governanca/saude:81` | **desativar** | mount-analysis | sim |
| endpoint | `cobertura_juridica` | `/api/rag/governanca/cobertura:90` | **desativar** | mount-analysis | sim |
| endpoint | `detalhar_governanca_documento` | `/api/rag/governanca/docs/{doc_id}:99` | **desativar** | mount-analysis | sim |
| endpoint | `atualizar_governanca_documento` | `/api/rag/governanca/docs/{doc_id}:111` | **desativar** | mount-analysis | sim |
| endpoint | `testar_conhecimento_documento` | `/api/rag/governanca/docs/{doc_id}/testar:173` | **desativar** | mount-analysis | sim |
| endpoint | `comparar_versoes_documento` | `/api/rag/governanca/docs/{doc_id}/comparar:191` | **desativar** | mount-analysis | sim |
| endpoint | `executar_testes_juridicos` | `/api/rag/governanca/testes-juridicos:204` | **desativar** | mount-analysis | sim |
| endpoint | `ingerir_lote` | `/api/rag/knowledge-base/batch:262` | **manter** | conservative-default | sim |
| endpoint | `status_lote` | `/api/rag/knowledge-base/status:396` | **manter** | conservative-default | sim |
| endpoint | `stats` | `/api/raio-x/stats:101` | **manter** | conservative-default | sim |
| endpoint | `listar` | `/api/raio-x/:138` | **manter** | conservative-default | sim |
| endpoint | `criar` | `/api/raio-x/:188` | **manter** | conservative-default | sim |
| endpoint | `contextual` | `/api/raio-x/contextual/{case_id}:221` | **manter** | conservative-default | sim |
| endpoint | `contextual_analise_advogado` | `/api/raio-x/contextual/{case_id}/analise-advogado:299` | **manter** | conservative-default | sim |
| endpoint | `detalhar` | `/api/raio-x/{analise_id}:324` | **manter** | conservative-default | sim |
| endpoint | `atualizar` | `/api/raio-x/{analise_id}:336` | **manter** | conservative-default | sim |
| endpoint | `analisar_documentos` | `/api/raio-x/{analise_id}/documentos/analisar:394` | **manter** | conservative-default | sim |
| endpoint | `reanalisar` | `/api/raio-x/{analise_id}/reanalisar:526` | **manter** | conservative-default | sim |
| endpoint | `analise_advogado_por_documentos` | `/api/raio-x/{analise_id}/analise-advogado:579` | **manter** | conservative-default | sim |
| endpoint | `download` | `/api/raio-x/{analise_id}/documentos/{documento_id}/download:615` | **manter** | conservative-default | sim |
| endpoint | `exportar` | `/api/raio-x/{analise_id}/exportar:642` | **manter** | conservative-default | sim |
| endpoint | `conversao_preview` | `/api/raio-x/{analise_id}/conversao/preview:677` | **manter** | conservative-default | sim |
| endpoint | `converter` | `/api/raio-x/{analise_id}/converter:687` | **manter** | conservative-default | sim |
| endpoint | `arquivar` | `/api/raio-x/{analise_id}/arquivar:704` | **manter** | conservative-default | sim |
| endpoint | `descartar` | `/api/raio-x/{analise_id}/descartar:720` | **manter** | conservative-default | sim |
| endpoint | `excluir` | `/api/raio-x/{analise_id}:736` | **manter** | conservative-default | sim |
| endpoint | `emp_tipos` | `/api/empresarial/tipos:160` | **corrigir** | parent-override | não |
| endpoint | `emp_listar` | `/api/empresarial:171` | **corrigir** | parent-override | não |
| endpoint | `emp_criar` | `/api/empresarial:179` | **corrigir** | parent-override | não |
| endpoint | `emp_atualizar` | `/api/empresarial/{eid}:190` | **corrigir** | parent-override | não |
| endpoint | `emp_remover` | `/api/empresarial/{eid}:195` | **corrigir** | parent-override | não |
| endpoint | `emp_prazos_rj` | `/api/empresarial/ferramentas/prazos-rj:201` | **corrigir** | parent-override | não |
| endpoint | `emp_cade` | `/api/empresarial/ferramentas/verificar-cade:230` | **corrigir** | parent-override | não |
| endpoint | `civ_listar` | `/api/civel:331` | **corrigir** | parent-override | não |
| endpoint | `civ_criar` | `/api/civel:338` | **corrigir** | parent-override | não |
| endpoint | `civ_atualizar` | `/api/civel/{cid}:358` | **corrigir** | parent-override | não |
| endpoint | `civ_remover` | `/api/civel/{cid}:363` | **corrigir** | parent-override | não |
| endpoint | `civ_prazo_contestacao` | `/api/civel/ferramentas/prazos-contestacao:369` | **corrigir** | parent-override | não |
| endpoint | `civ_alimentos` | `/api/civel/ferramentas/alimentos-calcular:394` | **corrigir** | parent-override | não |
| endpoint | `civ_usucapiao` | `/api/civel/ferramentas/usucapiao-verificar:420` | **corrigir** | parent-override | não |
| endpoint | `pen_listar` | `/api/penal:481` | **corrigir** | parent-override | não |
| endpoint | `pen_criar` | `/api/penal:488` | **corrigir** | parent-override | não |
| endpoint | `pen_atualizar` | `/api/penal/{pid}:503` | **corrigir** | parent-override | não |
| endpoint | `pen_remover` | `/api/penal/{pid}:508` | **corrigir** | parent-override | não |
| endpoint | `pen_prazos` | `/api/penal/ferramentas/prazos-processuais:514` | **corrigir** | parent-override | não |
| endpoint | `pen_anpp` | `/api/penal/ferramentas/verificar-anpp:546` | **corrigir** | parent-override | não |
| endpoint | `pen_prescricao` | `/api/penal/ferramentas/prescricao-punitiva:581` | **corrigir** | parent-override | não |
| endpoint | `trab_listar` | `/api/trabalhista-esp:645` | **corrigir** | parent-override | não |
| endpoint | `trab_criar` | `/api/trabalhista-esp:652` | **corrigir** | parent-override | não |
| endpoint | `trab_atualizar` | `/api/trabalhista-esp/{tid}:666` | **corrigir** | parent-override | não |
| endpoint | `trab_remover` | `/api/trabalhista-esp/{tid}:671` | **corrigir** | parent-override | não |
| endpoint | `trab_prazos` | `/api/trabalhista-esp/ferramentas/prazos:677` | **corrigir** | parent-override | não |
| endpoint | `trab_prescricao` | `/api/trabalhista-esp/ferramentas/prescricao-trabalhista:699` | **corrigir** | parent-override | não |
| endpoint | `trab_deposito` | `/api/trabalhista-esp/ferramentas/deposito-recursal:730` | **corrigir** | parent-override | não |
| endpoint | `adm_listar` | `/api/admin-esp:783` | **corrigir** | parent-override | não |
| endpoint | `adm_criar` | `/api/admin-esp:790` | **corrigir** | parent-override | não |
| endpoint | `adm_atualizar` | `/api/admin-esp/{aid}:811` | **corrigir** | parent-override | não |
| endpoint | `adm_remover` | `/api/admin-esp/{aid}:816` | **corrigir** | parent-override | não |
| endpoint | `adm_multa_transito` | `/api/admin-esp/ferramentas/recurso-multa-transito:822` | **corrigir** | parent-override | não |
| endpoint | `transito_prazos_recurso` | `/api/transito/ferramentas/prazos-recurso:850` | **corrigir** | parent-override | não |
| endpoint | `transito_pontuacao_cnh` | `/api/transito/ferramentas/pontuacao-cnh:884` | **corrigir** | parent-override | não |
| endpoint | `consumidor_devolucao_dobro` | `/api/consumidor/ferramentas/devolucao-dobro:929` | **corrigir** | parent-override | não |
| endpoint | `consumidor_prazos_cdc` | `/api/consumidor/ferramentas/prazos-cdc:948` | **corrigir** | parent-override | não |
| endpoint | `familia_debito_alimentos` | `/api/familia/ferramentas/debito-alimentos:973` | **corrigir** | parent-override | não |
| endpoint | `imobiliario_reajuste_aluguel` | `/api/imobiliario/ferramentas/reajuste-aluguel:993` | **corrigir** | parent-override | não |
| endpoint | `imobiliario_prazos_despejo` | `/api/imobiliario/ferramentas/prazos-despejo:1010` | **corrigir** | parent-override | não |
| endpoint | `previdenciario_prazos` | `/api/previdenciario/ferramentas/prazos:1033` | **corrigir** | parent-override | não |
| endpoint | `lgpd_multa` | `/api/digital_lgpd/ferramentas/multa-lgpd:1056` | **corrigir** | parent-override | não |
| endpoint | `lgpd_prazos` | `/api/digital_lgpd/ferramentas/prazos-lgpd:1073` | **corrigir** | parent-override | não |
| endpoint | `previdenciario_tempo_contribuicao` | `/api/previdenciario/ferramentas/tempo-contribuicao:1095` | **corrigir** | parent-override | não |
| endpoint | `previdenciario_carencia` | `/api/previdenciario/ferramentas/carencia:1123` | **corrigir** | parent-override | não |
| endpoint | `familia_itcmd` | `/api/familia/ferramentas/itcmd-inventario:1149` | **corrigir** | parent-override | não |
| endpoint | `penal_prescricao` | `/api/penal/ferramentas/prescricao-penal:1166` | **corrigir** | parent-override | não |
| endpoint | `penal_dosimetria` | `/api/penal/ferramentas/dosimetria:1186` | **corrigir** | parent-override | não |
| endpoint | `trabalhista_horas_extras` | `/api/trabalhista/ferramentas/horas-extras:1207` | **corrigir** | parent-override | não |
| endpoint | `empresarial_juros_mora` | `/api/empresarial/ferramentas/juros-mora:1235` | **corrigir** | parent-override | não |
| endpoint | `tributario_multa_mora` | `/api/tributario/ferramentas/multa-mora:1256` | **corrigir** | parent-override | não |
| endpoint | `bancario_juros_abusivos` | `/api/bancario/ferramentas/juros-abusivos:1276` | **corrigir** | parent-override | não |
| endpoint | `imobiliario_distrato` | `/api/imobiliario/ferramentas/distrato:1299` | **corrigir** | parent-override | não |
| endpoint | `transito_valor_multa` | `/api/transito/ferramentas/valor-multa:1323` | **corrigir** | parent-override | não |
| endpoint | `consumidor_negativacao` | `/api/consumidor/ferramentas/negativacao-indevida:1349` | **corrigir** | parent-override | não |
| endpoint | `adm_ms` | `/api/admin-esp/ferramentas/mandado-seguranca:1369` | **corrigir** | parent-override | não |
| endpoint | `ban_listar` | `/api/bancario:1425` | **corrigir** | parent-override | não |
| endpoint | `ban_criar` | `/api/bancario:1432` | **corrigir** | parent-override | não |
| endpoint | `ban_atualizar` | `/api/bancario/{bid}:1450` | **corrigir** | parent-override | não |
| endpoint | `ban_remover` | `/api/bancario/{bid}:1455` | **corrigir** | parent-override | não |
| endpoint | `ban_juros` | `/api/bancario/ferramentas/analise-juros:1461` | **corrigir** | parent-override | não |
| endpoint | `ban_superendiv` | `/api/bancario/ferramentas/superendividamento:1501` | **corrigir** | parent-override | não |
| endpoint | `ban_ba` | `/api/bancario/ferramentas/busca-apreensao:1535` | **corrigir** | parent-override | não |
| endpoint | `civ_prescricao_consumidor` | `/api/civel/ferramentas/prescricao-consumidor:1589` | **corrigir** | parent-override | não |
| endpoint | `civ_dano_moral` | `/api/civel/ferramentas/calculo-dano-moral:1660` | **corrigir** | parent-override | não |
| endpoint | `civ_partilha_divorcio` | `/api/civel/ferramentas/partilha-divorcio:1745` | **corrigir** | parent-override | não |
| endpoint | `civ_rescisao_locacao` | `/api/civel/ferramentas/rescisao-locacao:1776` | **corrigir** | parent-override | não |
| endpoint | `trab_verbas_rescisorias` | `/api/trabalhista-esp/ferramentas/verbas-rescisorias:1833` | **corrigir** | parent-override | não |
| endpoint | `adm_reajuste_contrato` | `/api/admin-esp/ferramentas/reajuste-contrato-administrativo:1903` | **corrigir** | parent-override | não |
| endpoint | `bancario_taxas_bacen` | `/api/bancario/ferramentas/taxas-bacen:1937` | **corrigir** | parent-override | não |
| endpoint | `trib_auto_infracao_prazos` | `/api/tributario/ferramentas/auto-infracao-prazos:1952` | **corrigir** | parent-override | não |
| endpoint | `trib_prescricao_decadencia` | `/api/tributario/ferramentas/prescricao-decadencia:1995` | **corrigir** | parent-override | não |
| endpoint | `trib_parcelamento` | `/api/tributario/ferramentas/parcelamento:2078` | **corrigir** | parent-override | não |
| endpoint | `trib_simples_nacional` | `/api/tributario/ferramentas/simples-nacional:2138` | **corrigir** | parent-override | não |
| endpoint | `trib_regime_tributario` | `/api/tributario/ferramentas/regime-tributario:2189` | **corrigir** | parent-override | não |
| endpoint | `trib_reforma_tributaria` | `/api/tributario/ferramentas/reforma-tributaria:2287` | **corrigir** | parent-override | não |
| endpoint | `amb_auto_infracao` | `/api/ambiental/ferramentas/auto-infracao-ambiental:2333` | **corrigir** | parent-override | não |
| endpoint | `amb_crimes_ambientais` | `/api/ambiental/ferramentas/crimes-ambientais:2408` | **corrigir** | parent-override | não |
| endpoint | `amb_tac` | `/api/ambiental/ferramentas/tac-ambiental:2456` | **corrigir** | parent-override | não |
| endpoint | `amb_licenciamento` | `/api/ambiental/ferramentas/licenciamento:2526` | **corrigir** | parent-override | não |
| endpoint | `amb_reserva_legal` | `/api/ambiental/ferramentas/reserva-legal:2576` | **corrigir** | parent-override | não |
| endpoint | `digest_semanal` | `/api/v1/regulatorio/digest-semanal:26` | **manter** | conservative-default | sim |
| endpoint | `relatorio_mensal` | `/api/relatorio/mensal:22` | **manter** | conservative-default | sim |
| endpoint | `relatorio_financeiro_cliente` | `/api/clients/{client_id}/relatorio-financeiro:43` | **manter** | conservative-default | sim |
| endpoint | `sala_de_guerra` | `/api/cases/{case_id}/sala-de-guerra:32` | **consolidar** | parent-override | não |
| endpoint | `atualizar_notas` | `/api/cases/{case_id}/sala-de-guerra/notas:170` | **consolidar** | parent-override | não |
| endpoint | `auditoria_sentinela` | `/api/sala-de-guerra-v3/sentinela/auditoria:30` | **consolidar** | parent-override | não |
| endpoint | `simular_war_room` | `/api/sala-de-guerra-v3/war-room/simular:44` | **consolidar** | parent-override | não |
| endpoint | `gerar_visual_law` | `/api/sala-de-guerra-v3/visual-law/{case_id}:98` | **consolidar** | parent-override | não |
| endpoint | `download_visual_law` | `/api/sala-de-guerra-v3/visual-law/{case_id}/download:126` | **consolidar** | parent-override | não |
| endpoint | `listar_scores` | `/api/cases/{case_id}/score-juridico:36` | **manter** | conservative-default | sim |
| endpoint | `calcular_score` | `/api/cases/{case_id}/score-juridico/calcular:55` | **manter** | conservative-default | sim |
| endpoint | `busca_global` | `/api/search:80` | **manter** | conservative-default | sim |
| endpoint | `busca_global` | `/api/search/:80` | **manter** | conservative-default | sim |
| endpoint | `criar_solicitacao` | `/api/signatures/:47` | **manter** | conservative-default | sim |
| endpoint | `listar` | `/api/signatures/:108` | **manter** | conservative-default | sim |
| endpoint | `assinar` | `/api/signatures/{sig_id}/assinar:164` | **manter** | conservative-default | sim |
| endpoint | `semear_template_due_diligence` | `/api/empresarial/sociedades/due-diligence/template:157` | **manter** | conservative-default | sim |
| endpoint | `listar` | `/api/empresarial/sociedades:196` | **manter** | conservative-default | sim |
| endpoint | `criar` | `/api/empresarial/sociedades:242` | **manter** | conservative-default | sim |
| endpoint | `detalhe` | `/api/empresarial/sociedades/{sociedade_id}:274` | **manter** | conservative-default | sim |
| endpoint | `atualizar` | `/api/empresarial/sociedades/{sociedade_id}:316` | **manter** | conservative-default | sim |
| endpoint | `remover` | `/api/empresarial/sociedades/{sociedade_id}:340` | **manter** | conservative-default | sim |
| endpoint | `adicionar_socio` | `/api/empresarial/sociedades/{sociedade_id}/socios:357` | **manter** | conservative-default | sim |
| endpoint | `atualizar_socio` | `/api/empresarial/sociedades/socios/{socio_id}:400` | **manter** | conservative-default | sim |
| endpoint | `remover_socio` | `/api/empresarial/sociedades/socios/{socio_id}:424` | **manter** | conservative-default | sim |
| endpoint | `registrar_evento` | `/api/empresarial/sociedades/{sociedade_id}/eventos:453` | **manter** | conservative-default | sim |
| endpoint | `criar_solicitacao` | `/api/casos/{case_id}/solicitacoes-documentos:85` | **manter** | conservative-default | sim |
| endpoint | `listar_solicitacoes` | `/api/casos/{case_id}/solicitacoes-documentos:180` | **manter** | conservative-default | sim |
| endpoint | `ingerir_seed` | `/api/sumulas/ingerir-seed:29` | **manter** | conservative-default | sim |
| endpoint | `buscar_sumulas` | `/api/sumulas/buscar:57` | **manter** | conservative-default | sim |
| endpoint | `verificar_conflito` | `/api/casos/verificar-conflito:100` | **manter** | conservative-default | sim |
| endpoint | `tribunais` | `/api/suspensoes/tribunais:61` | **manter** | conservative-default | sim |
| endpoint | `listar` | `/api/suspensoes/:67` | **manter** | conservative-default | sim |
| endpoint | `criar` | `/api/suspensoes/:90` | **manter** | conservative-default | sim |
| endpoint | `remover` | `/api/suspensoes/{suspensao_id}:117` | **manter** | conservative-default | sim |
| endpoint | `simular` | `/api/suspensoes/simular:142` | **manter** | conservative-default | sim |
| endpoint | `mapa_modulos` | `/api/system-modules/mapa:42` | **manter** | conservative-default | sim |
| endpoint | `status_integracoes` | `/api/system-modules/integrations:54` | **manter** | conservative-default | sim |
| endpoint | `listar` | `/api/tasks/:46` | **manter** | conservative-default | sim |
| endpoint | `criar` | `/api/tasks/:87` | **manter** | conservative-default | sim |
| endpoint | `atualizar` | `/api/tasks/{task_id}:121` | **manter** | conservative-default | sim |
| endpoint | `remover` | `/api/tasks/{task_id}:181` | **manter** | conservative-default | sim |
| endpoint | `listar` | `/api/templates/:68` | **manter** | conservative-default | sim |
| endpoint | `detalhe` | `/api/templates/{tpl_id}:91` | **manter** | conservative-default | sim |
| endpoint | `criar` | `/api/templates/:106` | **manter** | conservative-default | sim |
| endpoint | `gerar_peca` | `/api/templates/{tpl_id}/gerar:122` | **manter** | conservative-default | sim |
| endpoint | `remover` | `/api/templates/{tpl_id}:182` | **manter** | conservative-default | sim |
| endpoint | `listar_teses` | `/api/teses:104` | **consolidar** | parent-override | não |
| endpoint | `criar_tese` | `/api/teses:154` | **consolidar** | parent-override | não |
| endpoint | `ranking_teses` | `/api/teses/ranking:171` | **consolidar** | parent-override | não |
| endpoint | `busca_avancada` | `/api/teses/busca-avancada:193` | **consolidar** | parent-override | não |
| endpoint | `teses_do_caso` | `/api/teses/casos/{case_id}:250` | **consolidar** | parent-override | não |
| endpoint | `obter_tese` | `/api/teses/{tese_id}:276` | **consolidar** | parent-override | não |
| endpoint | `atualizar_tese` | `/api/teses/{tese_id}:292` | **consolidar** | parent-override | não |
| endpoint | `arquivar_tese` | `/api/teses/{tese_id}:312` | **consolidar** | parent-override | não |
| endpoint | `vincular_caso` | `/api/teses/{tese_id}/vincular-caso:329` | **consolidar** | parent-override | não |
| endpoint | `sugerir_teses_ia` | `/api/teses/sugerir-ia:365` | **consolidar** | parent-override | não |
| endpoint | `motor_teses` | `/api/teses/motor:489` | **consolidar** | parent-override | não |
| endpoint | `criar_tese` | `/api/teses-v4/:96` | **consolidar** | parent-override | não |
| endpoint | `listar_teses` | `/api/teses-v4/:128` | **consolidar** | parent-override | não |
| endpoint | `sugerir_teses_ia` | `/api/teses-v4/sugestao-ia:164` | **consolidar** | parent-override | não |
| endpoint | `por_caso` | `/api/timesheet/casos/{case_id}:50` | **manter** | conservative-default | sim |
| endpoint | `lancar` | `/api/timesheet/:76` | **manter** | conservative-default | sim |
| endpoint | `faturar` | `/api/timesheet/caso/{case_id}/faturar:94` | **manter** | conservative-default | sim |
| endpoint | `remover` | `/api/timesheet/{entry_id}:143` | **manter** | conservative-default | sim |
| endpoint | `calcular` | `/api/trabalhista/liquidacao/calcular:141` | **manter** | conservative-default | sim |
| endpoint | `planilha_pdf` | `/api/trabalhista/liquidacao/planilha-pdf:313` | **manter** | conservative-default | sim |
| endpoint | `download_planilha` | `/api/trabalhista/liquidacao/planilha/{arquivo_id}/download:337` | **manter** | conservative-default | sim |
| endpoint | `status_transparencia` | `/api/transparencia/status:47` | **manter** | conservative-default | sim |
| endpoint | `consultar_sancoes` | `/api/transparencia/sancoes:59` | **manter** | conservative-default | sim |
| endpoint | `listar` | `/api/trash/:40` | **manter** | conservative-default | sim |
| endpoint | `restaurar` | `/api/trash/{entidade}/{registro_id}/restaurar:63` | **manter** | conservative-default | sim |
| endpoint | `entrevista_inteligente` | `/api/triagem/entrevista:153` | **manter** | conservative-default | sim |
| endpoint | `analisar_xml` | `/api/tributario/fiscal/analisar-xml:108` | **manter** | conservative-default | sim |
| endpoint | `relatorio_pdf` | `/api/tributario/fiscal/relatorio-pdf:304` | **manter** | conservative-default | sim |
| endpoint | `download_relatorio` | `/api/tributario/fiscal/relatorio/{arquivo_id}/download:330` | **manter** | conservative-default | sim |
| endpoint | `meu_perfil` | `/api/users/me:88` | **manter** | conservative-default | sim |
| endpoint | `minha_seguranca` | `/api/users/me/security:94` | **manter** | conservative-default | sim |
| endpoint | `minhas_sessoes` | `/api/users/me/sessions:118` | **manter** | conservative-default | sim |
| endpoint | `revogar_outras_sessoes` | `/api/users/me/sessions/revoke-others:153` | **manter** | conservative-default | sim |
| endpoint | `revogar_sessao` | `/api/users/me/sessions/{session_id}/revoke:190` | **manter** | conservative-default | sim |
| endpoint | `meu_qr_totp` | `/api/users/me/totp-qr:230` | **manter** | conservative-default | sim |
| endpoint | `listar` | `/api/users/:262` | **manter** | conservative-default | sim |
| endpoint | `criar` | `/api/users/:284` | **manter** | conservative-default | sim |
| endpoint | `atualizar` | `/api/users/{user_id}:320` | **manter** | conservative-default | sim |
| endpoint | `desativar` | `/api/users/{user_id}:380` | **manter** | conservative-default | sim |
| endpoint | `minha_url_calendario` | `/api/users/me/calendar-url:417` | **manter** | conservative-default | sim |
| endpoint | `enviar_avatar` | `/api/users/me/avatar:471` | **manter** | conservative-default | sim |
| endpoint | `remover_avatar` | `/api/users/me/avatar:500` | **manter** | conservative-default | sim |
| endpoint | `obter_avatar` | `/api/users/{user_id}/avatar:520` | **manter** | conservative-default | sim |
| endpoint | `cep` | `/api/utils/cep/{cep}:18` | **manter** | conservative-default | sim |
| endpoint | `cnpj` | `/api/utils/cnpj/{cnpj}:29` | **manter** | conservative-default | sim |
| endpoint | `cpf_check` | `/api/utils/validar-cpf/{cpf}:39` | **manter** | conservative-default | sim |
| endpoint | `status_validador` | `/api/validador-juridico/status:33` | **manter** | conservative-default | sim |
| endpoint | `validar` | `/api/validador-juridico/validar:51` | **manter** | conservative-default | sim |
| endpoint | `analisar_tese` | `/api/veredito_ia/analisar:17` | **manter** | conservative-default | sim |
| endpoint | `get_verse` | `/api/verse:46` | **manter** | conservative-default | sim |
| endpoint | `create_tese_vitoriosa` | `/api/victory_vault/teses:11` | **manter** | conservative-default | sim |
| endpoint | `get_teses_vitoriosas` | `/api/victory_vault/teses:15` | **manter** | conservative-default | sim |
| endpoint | `create_modelo_documento` | `/api/victory_vault/modelos:19` | **manter** | conservative-default | sim |
| endpoint | `get_modelos_documentos` | `/api/victory_vault/modelos:23` | **manter** | conservative-default | sim |
| endpoint | `timeline_visual` | `/api/visual-law/casos/{case_id}/timeline:47` | **manter** | conservative-default | sim |
| endpoint | `matriz_risco` | `/api/visual-law/casos/{case_id}/matriz-risco:88` | **manter** | conservative-default | sim |
| endpoint | `alertas` | `/api/visual-law/casos/{case_id}/alertas:118` | **manter** | conservative-default | sim |
| endpoint | `breakeven` | `/api/visual-law/breakeven:145` | **manter** | conservative-default | sim |
| endpoint | `get_status` | `/api/v1/whatsapp/status:65` | **manter** | conservative-default | sim |
| endpoint | `get_qrcode` | `/api/v1/whatsapp/qrcode:76` | **manter** | conservative-default | sim |
| endpoint | `send_message` | `/api/v1/whatsapp/send:87` | **manter** | conservative-default | sim |
| endpoint | `list_chats` | `/api/v1/whatsapp/chats:116` | **manter** | conservative-default | sim |
| endpoint | `get_messages` | `/api/v1/whatsapp/messages:133` | **manter** | conservative-default | sim |
| endpoint | `listar` | `/api/wiki:55` | **manter** | conservative-default | sim |
| endpoint | `obter` | `/api/wiki/{pid}:67` | **manter** | conservative-default | sim |
| endpoint | `criar` | `/api/wiki:79` | **manter** | conservative-default | sim |
| endpoint | `editar` | `/api/wiki/{pid}:90` | **manter** | conservative-default | sim |
| endpoint | `excluir` | `/api/wiki/{pid}:107` | **manter** | conservative-default | sim |
| endpoint | `listar_templates` | `/api/workflow/templates:93` | **manter** | conservative-default | sim |
| endpoint | `criar_template` | `/api/workflow/templates:121` | **manter** | conservative-default | sim |
| endpoint | `arquivar_template` | `/api/workflow/templates/{template_id}:150` | **manter** | conservative-default | sim |
| endpoint | `workflow_do_caso` | `/api/workflow/casos/{case_id}:169` | **manter** | conservative-default | sim |
| endpoint | `iniciar_workflow` | `/api/workflow/casos/{case_id}/iniciar:209` | **manter** | conservative-default | sim |
| endpoint | `aplicar_workflow_padrao` | `/api/workflow/casos/{case_id}/aplicar-padrao:256` | **manter** | conservative-default | sim |
| endpoint | `avancar_etapa` | `/api/workflow/casos/{case_id}/avancar:346` | **manter** | conservative-default | sim |
| endpoint | `concluir_workflow` | `/api/workflow/casos/{case_id}/concluir:403` | **manter** | conservative-default | sim |

## Serviços

| Tipo | Item | Arquivo/rota | Classificação | Fonte | Revisão |
|---|---|---|---|---|---|
| service | `__init__` | `backend/app/services/__init__.py` | **consolidar** | duplicate-family | sim |
| service | `abusividade_service` | `backend/app/services/abusividade_service.py` | **manter** | conservative-default | sim |
| service | `advogado_style_service` | `backend/app/services/advogado_style_service.py` | **manter** | conservative-default | sim |
| service | `__init__` | `backend/app/services/ai/__init__.py` | **consolidar** | duplicate-family | sim |
| service | `adversarial` | `backend/app/services/ai/adversarial.py` | **manter** | conservative-default | sim |
| service | `__init__` | `backend/app/services/ai/agent/__init__.py` | **consolidar** | duplicate-family | sim |
| service | `budget` | `backend/app/services/ai/agent/budget.py` | **manter** | conservative-default | sim |
| service | `hitl_state` | `backend/app/services/ai/agent/hitl_state.py` | **manter** | conservative-default | sim |
| service | `loop` | `backend/app/services/ai/agent/loop.py` | **manter** | conservative-default | sim |
| service | `permissions` | `backend/app/services/ai/agent/permissions.py` | **manter** | conservative-default | sim |
| service | `__init__` | `backend/app/services/ai/agent/tools/__init__.py` | **consolidar** | duplicate-family | sim |
| service | `context` | `backend/app/services/ai/agent/tools/context.py` | **manter** | conservative-default | sim |
| service | `escrita` | `backend/app/services/ai/agent/tools/escrita.py` | **manter** | conservative-default | sim |
| service | `leitura` | `backend/app/services/ai/agent/tools/leitura.py` | **manter** | conservative-default | sim |
| service | `motores` | `backend/app/services/ai/agent/tools/motores.py` | **manter** | conservative-default | sim |
| service | `registry` | `backend/app/services/ai/agent/tools/registry.py` | **manter** | conservative-default | sim |
| service | `__init__` | `backend/app/services/ai/core/__init__.py` | **manter** | override | não |
| service | `agent_registry` | `backend/app/services/ai/core/agent_registry.py` | **manter** | override | não |
| service | `audit_logger` | `backend/app/services/ai/core/audit_logger.py` | **manter** | override | não |
| service | `context_builder` | `backend/app/services/ai/core/context_builder.py` | **manter** | override | não |
| service | `ejc_skill_catalog` | `backend/app/services/ai/core/ejc_skill_catalog.py` | **manter** | override | não |
| service | `hitl_policy` | `backend/app/services/ai/core/hitl_policy.py` | **manter** | override | não |
| service | `intent_classifier` | `backend/app/services/ai/core/intent_classifier.py` | **manter** | override | não |
| service | `orchestrator` | `backend/app/services/ai/core/orchestrator.py` | **manter** | override | não |
| service | `response_validator` | `backend/app/services/ai/core/response_validator.py` | **manter** | override | não |
| service | `skill_registry` | `backend/app/services/ai/core/skill_registry.py` | **manter** | override | não |
| service | `entidades_caso` | `backend/app/services/ai/entidades_caso.py` | **manter** | conservative-default | sim |
| service | `model_router` | `backend/app/services/ai/model_router.py` | **manter** | conservative-default | sim |
| service | `ner_local` | `backend/app/services/ai/ner_local.py` | **manter** | conservative-default | sim |
| service | `provider_metrics_runtime` | `backend/app/services/ai/provider_metrics_runtime.py` | **manter** | conservative-default | sim |
| service | `provider_policy` | `backend/app/services/ai/provider_policy.py` | **manter** | conservative-default | sim |
| service | `provider_registry` | `backend/app/services/ai/provider_registry.py` | **manter** | conservative-default | sim |
| service | `provider_registry_runtime` | `backend/app/services/ai/provider_registry_runtime.py` | **manter** | conservative-default | sim |
| service | `pseudonymizer` | `backend/app/services/ai/pseudonymizer.py` | **manter** | conservative-default | sim |
| service | `reranker` | `backend/app/services/ai/reranker.py` | **manter** | conservative-default | sim |
| service | `sanitization_policy` | `backend/app/services/ai/sanitization_policy.py` | **manter** | conservative-default | sim |
| service | `ai_cache` | `backend/app/services/ai_cache.py` | **manter** | conservative-default | sim |
| service | `ai_contextual` | `backend/app/services/ai_contextual.py` | **manter** | conservative-default | sim |
| service | `ai_core_hardening_patch` | `backend/app/services/ai_core_hardening_patch.py` | **manter** | conservative-default | sim |
| service | `ai_cost` | `backend/app/services/ai_cost.py` | **manter** | conservative-default | sim |
| service | `ai_document_chunking` | `backend/app/services/ai_document_chunking.py` | **manter** | conservative-default | sim |
| service | `ai_gateway` | `backend/app/services/ai_gateway.py` | **manter** | override | não |
| service | `ai_guard` | `backend/app/services/ai_guard.py` | **manter** | conservative-default | sim |
| service | `ai_service` | `backend/app/services/ai_service.py` | **consolidar** | duplicate-family | sim |
| service | `ai_skill_service` | `backend/app/services/ai_skill_service.py` | **consolidar** | duplicate-family | sim |
| service | `__init__` | `backend/app/services/ambiental/__init__.py` | **consolidar** | duplicate-family | sim |
| service | `estrategia_auto` | `backend/app/services/ambiental/estrategia_auto.py` | **manter** | conservative-default | sim |
| service | `analise_estrategica` | `backend/app/services/analise_estrategica.py` | **manter** | conservative-default | sim |
| service | `anexos_service` | `backend/app/services/anexos_service.py` | **consolidar** | duplicate-family | sim |
| service | `autofix_scanner` | `backend/app/services/autofix_scanner.py` | **manter** | conservative-default | sim |
| service | `backup_drive_auth` | `backend/app/services/backup_drive_auth.py` | **manter** | conservative-default | sim |
| service | `backup_service` | `backend/app/services/backup_service.py` | **manter** | conservative-default | sim |
| service | `bank_report` | `backend/app/services/bank_report.py` | **manter** | conservative-default | sim |
| service | `bank_statement` | `backend/app/services/bank_statement.py` | **manter** | conservative-default | sim |
| service | `bcb_service` | `backend/app/services/bcb_service.py` | **manter** | conservative-default | sim |
| service | `__init__` | `backend/app/services/calc/__init__.py` | **consolidar** | duplicate-family | sim |
| service | `cet` | `backend/app/services/calc/cet.py` | **manter** | conservative-default | sim |
| service | `custas_tjmg` | `backend/app/services/calc/custas_tjmg.py` | **manter** | conservative-default | sim |
| service | `liquidacao_trabalhista` | `backend/app/services/calc/liquidacao_trabalhista.py` | **manter** | conservative-default | sim |
| service | `prescricao` | `backend/app/services/calc/prescricao.py` | **manter** | conservative-default | sim |
| service | `previdenciario_beneficio` | `backend/app/services/calc/previdenciario_beneficio.py` | **consolidar** | duplicate-family | sim |
| service | `tax_tables` | `backend/app/services/calc/tax_tables.py` | **manter** | conservative-default | sim |
| service | `trabalhista` | `backend/app/services/calc/trabalhista.py` | **consolidar** | duplicate-family | sim |
| service | `calendario_tribunal` | `backend/app/services/calendario_tribunal.py` | **manter** | conservative-default | sim |
| service | `case_automacao` | `backend/app/services/case_automacao.py` | **manter** | conservative-default | sim |
| service | `case_context` | `backend/app/services/case_context.py` | **manter** | conservative-default | sim |
| service | `case_health` | `backend/app/services/case_health.py` | **manter** | conservative-default | sim |
| service | `case_intel` | `backend/app/services/case_intel.py` | **manter** | conservative-default | sim |
| service | `case_intelligence_service` | `backend/app/services/case_intelligence_service.py` | **consolidar** | duplicate-family | sim |
| service | `checklist_ia` | `backend/app/services/checklist_ia.py` | **manter** | conservative-default | sim |
| service | `citation_check` | `backend/app/services/citation_check.py` | **manter** | conservative-default | sim |
| service | `citation_gate` | `backend/app/services/citation_gate.py` | **manter** | conservative-default | sim |
| service | `client_anonimizacao` | `backend/app/services/client_anonimizacao.py` | **manter** | conservative-default | sim |
| service | `cobranca_cliente_service` | `backend/app/services/cobranca_cliente_service.py` | **manter** | conservative-default | sim |
| service | `conflito_interesses` | `backend/app/services/conflito_interesses.py` | **manter** | conservative-default | sim |
| service | `conflito_service` | `backend/app/services/conflito_service.py` | **manter** | conservative-default | sim |
| service | `__init__` | `backend/app/services/conhecimento_ingest/__init__.py` | **consolidar** | duplicate-family | sim |
| service | `anpd` | `backend/app/services/conhecimento_ingest/anpd.py` | **manter** | conservative-default | sim |
| service | `base` | `backend/app/services/conhecimento_ingest/base.py` | **consolidar** | duplicate-family | sim |
| service | `normas_rfb` | `backend/app/services/conhecimento_ingest/normas_rfb.py` | **manter** | conservative-default | sim |
| service | `crawler_precedentes` | `backend/app/services/crawler_precedentes.py` | **manter** | conservative-default | sim |
| service | `credential_registry` | `backend/app/services/credential_registry.py` | **manter** | conservative-default | sim |
| service | `credential_testers` | `backend/app/services/credential_testers.py` | **manter** | conservative-default | sim |
| service | `credential_vault_service` | `backend/app/services/credential_vault_service.py` | **manter** | override | não |
| service | `dashboard_service` | `backend/app/services/dashboard_service.py` | **consolidar** | duplicate-family | sim |
| service | `datajud_cognitive_feed` | `backend/app/services/datajud_cognitive_feed.py` | **manter** | conservative-default | sim |
| service | `datajud_cognitive_patch` | `backend/app/services/datajud_cognitive_patch.py` | **manter** | conservative-default | sim |
| service | `datajud_service` | `backend/app/services/datajud_service.py` | **consolidar** | duplicate-family | sim |
| service | `datajud_sync_service` | `backend/app/services/datajud_sync_service.py` | **manter** | conservative-default | sim |
| service | `deadline_calculator` | `backend/app/services/deadline_calculator.py` | **manter** | conservative-default | sim |
| service | `deep_research_service` | `backend/app/services/deep_research_service.py` | **manter** | conservative-default | sim |
| service | `diagnostico_service` | `backend/app/services/diagnostico_service.py` | **consolidar** | duplicate-family | sim |
| service | `diario_oficial_service` | `backend/app/services/diario_oficial_service.py` | **consolidar** | duplicate-family | sim |
| service | `diplomacia_digital` | `backend/app/services/diplomacia_digital.py` | **manter** | conservative-default | sim |
| service | `djen_service` | `backend/app/services/djen_service.py` | **consolidar** | duplicate-family | sim |
| service | `document_classifier` | `backend/app/services/document_classifier.py` | **manter** | conservative-default | sim |
| service | `document_format` | `backend/app/services/document_format.py` | **manter** | conservative-default | sim |
| service | `document_intake_service` | `backend/app/services/document_intake_service.py` | **consolidar** | duplicate-family | sim |
| service | `document_url_import_service` | `backend/app/services/document_url_import_service.py` | **manter** | conservative-default | sim |
| service | `documental` | `backend/app/services/documental.py` | **manter** | conservative-default | sim |
| service | `documento_service` | `backend/app/services/documento_service.py` | **manter** | conservative-default | sim |
| service | `docx_service` | `backend/app/services/docx_service.py` | **manter** | conservative-default | sim |
| service | `dossie_modulos` | `backend/app/services/dossie_modulos.py` | **manter** | conservative-default | sim |
| service | `dossie_service` | `backend/app/services/dossie_service.py` | **manter** | conservative-default | sim |
| service | `due_diligence_empresarial` | `backend/app/services/due_diligence_empresarial.py` | **manter** | conservative-default | sim |
| service | `embedding_service` | `backend/app/services/embedding_service.py` | **manter** | conservative-default | sim |
| service | `entrada_universal_service` | `backend/app/services/entrada_universal_service.py` | **consolidar** | duplicate-family | sim |
| service | `event_bus` | `backend/app/services/event_bus.py` | **manter** | conservative-default | sim |
| service | `event_subscribers` | `backend/app/services/event_subscribers.py` | **manter** | conservative-default | sim |
| service | `evento_processual` | `backend/app/services/evento_processual.py` | **manter** | conservative-default | sim |
| service | `extracao_estruturada` | `backend/app/services/extracao_estruturada.py` | **manter** | conservative-default | sim |
| service | `fee_proposal_service` | `backend/app/services/fee_proposal_service.py` | **consolidar** | duplicate-family | sim |
| service | `feriados_service` | `backend/app/services/feriados_service.py` | **manter** | conservative-default | sim |
| service | `ficha_triagem_service` | `backend/app/services/ficha_triagem_service.py` | **consolidar** | duplicate-family | sim |
| service | `__init__` | `backend/app/services/fiscal/__init__.py` | **consolidar** | duplicate-family | sim |
| service | `nfe_parser` | `backend/app/services/fiscal/nfe_parser.py` | **manter** | conservative-default | sim |
| service | `recuperacao_creditos` | `backend/app/services/fiscal/recuperacao_creditos.py` | **manter** | conservative-default | sim |
| service | `funil` | `backend/app/services/funil.py` | **manter** | conservative-default | sim |
| service | `geracao_documental` | `backend/app/services/geracao_documental.py` | **manter** | conservative-default | sim |
| service | `google_drive` | `backend/app/services/google_drive.py` | **consolidar** | duplicate-family | sim |
| service | `google_drive_service` | `backend/app/services/google_drive_service.py` | **consolidar** | duplicate-family | sim |
| service | `google_drive_taxonomy` | `backend/app/services/google_drive_taxonomy.py` | **manter** | conservative-default | sim |
| service | `heartbeat_service` | `backend/app/services/heartbeat_service.py` | **manter** | conservative-default | sim |
| service | `honorarios_oab` | `backend/app/services/honorarios_oab.py` | **consolidar** | duplicate-family | sim |
| service | `ia_defensiva_service` | `backend/app/services/ia_defensiva_service.py` | **consolidar** | duplicate-family | sim |
| service | `ia_parser` | `backend/app/services/ia_parser.py` | **manter** | conservative-default | sim |
| service | `ia_sentinela` | `backend/app/services/ia_sentinela.py` | **manter** | conservative-default | sim |
| service | `inadimplencia_service` | `backend/app/services/inadimplencia_service.py` | **manter** | conservative-default | sim |
| service | `indices_service` | `backend/app/services/indices_service.py` | **consolidar** | duplicate-family | sim |
| service | `infosimples_service` | `backend/app/services/infosimples_service.py` | **consolidar** | duplicate-family | sim |
| service | `ingestion_service` | `backend/app/services/ingestion_service.py` | **manter** | conservative-default | sim |
| service | `__init__` | `backend/app/services/ingestors/__init__.py` | **consolidar** | duplicate-family | sim |
| service | `camara` | `backend/app/services/ingestors/camara.py` | **manter** | conservative-default | sim |
| service | `djen` | `backend/app/services/ingestors/djen.py` | **consolidar** | duplicate-family | sim |
| service | `lexml` | `backend/app/services/ingestors/lexml.py` | **consolidar** | duplicate-family | sim |
| service | `planalto` | `backend/app/services/ingestors/planalto.py` | **manter** | conservative-default | sim |
| service | `senado` | `backend/app/services/ingestors/senado.py` | **manter** | conservative-default | sim |
| service | `stj` | `backend/app/services/ingestors/stj.py` | **consolidar** | duplicate-family | sim |
| service | `tjmg` | `backend/app/services/ingestors/tjmg.py` | **consolidar** | duplicate-family | sim |
| service | `integration_status` | `backend/app/services/integration_status.py` | **manter** | conservative-default | sim |
| service | `jurimetria` | `backend/app/services/jurimetria.py` | **consolidar** | duplicate-family | sim |
| service | `__init__` | `backend/app/services/juris_import/__init__.py` | **consolidar** | duplicate-family | sim |
| service | `base` | `backend/app/services/juris_import/base.py` | **consolidar** | duplicate-family | sim |
| service | `ingest` | `backend/app/services/juris_import/ingest.py` | **manter** | conservative-default | sim |
| service | `lexml` | `backend/app/services/juris_import/lexml.py` | **consolidar** | duplicate-family | sim |
| service | `stj` | `backend/app/services/juris_import/stj.py` | **consolidar** | duplicate-family | sim |
| service | `tjmg` | `backend/app/services/juris_import/tjmg.py` | **consolidar** | duplicate-family | sim |
| service | `jurisprudencia_externa` | `backend/app/services/jurisprudencia_externa.py` | **consolidar** | duplicate-family | sim |
| service | `knowledge_autoapproval` | `backend/app/services/knowledge_autoapproval.py` | **manter** | conservative-default | sim |
| service | `knowledge_governance` | `backend/app/services/knowledge_governance.py` | **manter** | conservative-default | sim |
| service | `legal_base` | `backend/app/services/legal_base.py` | **manter** | conservative-default | sim |
| service | `legal_case_orchestrator` | `backend/app/services/legal_case_orchestrator.py` | **manter** | conservative-default | sim |
| service | `lgpd_service` | `backend/app/services/lgpd_service.py` | **manter** | conservative-default | sim |
| service | `matriz_provas` | `backend/app/services/matriz_provas.py` | **manter** | conservative-default | sim |
| service | `matriz_teses_service` | `backend/app/services/matriz_teses_service.py` | **consolidar** | duplicate-family | sim |
| service | `module_help_seed` | `backend/app/services/module_help_seed.py` | **manter** | conservative-default | sim |
| service | `module_registry` | `backend/app/services/module_registry.py` | **manter** | conservative-default | sim |
| service | `motor_peca_service` | `backend/app/services/motor_peca_service.py` | **consolidar** | duplicate-family | sim |
| service | `movimento_ia` | `backend/app/services/movimento_ia.py` | **manter** | conservative-default | sim |
| service | `__init__` | `backend/app/services/nfse/__init__.py` | **consolidar** | duplicate-family | sim |
| service | `base` | `backend/app/services/nfse/base.py` | **consolidar** | duplicate-family | sim |
| service | `nuvem_fiscal` | `backend/app/services/nfse/nuvem_fiscal.py` | **manter** | conservative-default | sim |
| service | `notification_preferences` | `backend/app/services/notification_preferences.py` | **manter** | conservative-default | sim |
| service | `notification_service` | `backend/app/services/notification_service.py` | **consolidar** | duplicate-family | sim |
| service | `__init__` | `backend/app/services/observability/__init__.py` | **consolidar** | duplicate-family | sim |
| service | `langfuse_client` | `backend/app/services/observability/langfuse_client.py` | **manter** | conservative-default | sim |
| service | `ocr_service` | `backend/app/services/ocr_service.py` | **manter** | conservative-default | sim |
| service | `onboarding` | `backend/app/services/onboarding.py` | **manter** | conservative-default | sim |
| service | `pdf_service` | `backend/app/services/pdf_service.py` | **manter** | conservative-default | sim |
| service | `peca_numeracao` | `backend/app/services/peca_numeracao.py` | **manter** | conservative-default | sim |
| service | `peca_service` | `backend/app/services/peca_service.py` | **manter** | conservative-default | sim |
| service | `pii_crypto` | `backend/app/services/pii_crypto.py` | **manter** | conservative-default | sim |
| service | `pncp_service` | `backend/app/services/pncp_service.py` | **consolidar** | duplicate-family | sim |
| service | `precificacao_service` | `backend/app/services/precificacao_service.py` | **manter** | conservative-default | sim |
| service | `processo_service` | `backend/app/services/processo_service.py` | **corrigir** | override | não |
| service | `__init__` | `backend/app/services/providers/__init__.py` | **consolidar** | duplicate-family | sim |
| service | `anthropic_provider` | `backend/app/services/providers/anthropic_provider.py` | **manter** | conservative-default | sim |
| service | `groq_provider` | `backend/app/services/providers/groq_provider.py` | **manter** | conservative-default | sim |
| service | `maritaca_provider` | `backend/app/services/providers/maritaca_provider.py` | **manter** | conservative-default | sim |
| service | `ollama_provider` | `backend/app/services/providers/ollama_provider.py` | **manter** | conservative-default | sim |
| service | `radar_legislativo` | `backend/app/services/radar_legislativo.py` | **consolidar** | duplicate-family | sim |
| service | `radar_poder` | `backend/app/services/radar_poder.py` | **manter** | conservative-default | sim |
| service | `rag_drive_reclassifier` | `backend/app/services/rag_drive_reclassifier.py` | **manter** | conservative-default | sim |
| service | `rag_juridico` | `backend/app/services/rag_juridico.py` | **manter** | conservative-default | sim |
| service | `raio_x_advogado_service` | `backend/app/services/raio_x_advogado_service.py` | **manter** | conservative-default | sim |
| service | `raio_x_enrichment` | `backend/app/services/raio_x_enrichment.py` | **manter** | conservative-default | sim |
| service | `raio_x_export_service` | `backend/app/services/raio_x_export_service.py` | **manter** | conservative-default | sim |
| service | `raio_x_service` | `backend/app/services/raio_x_service.py` | **consolidar** | duplicate-family | sim |
| service | `relatorio_dono_service` | `backend/app/services/relatorio_dono_service.py` | **manter** | conservative-default | sim |
| service | `rentabilidade` | `backend/app/services/rentabilidade.py` | **manter** | conservative-default | sim |
| service | `rito_engine` | `backend/app/services/rito_engine.py` | **manter** | conservative-default | sim |
| service | `sanitizer` | `backend/app/services/sanitizer.py` | **manter** | conservative-default | sim |
| service | `scheduler` | `backend/app/services/scheduler.py` | **manter** | conservative-default | sim |
| service | `security_service` | `backend/app/services/security_service.py` | **manter** | conservative-default | sim |
| service | `seed_conhecimento` | `backend/app/services/seed_conhecimento.py` | **manter** | conservative-default | sim |
| service | `sentimento_magistrado` | `backend/app/services/sentimento_magistrado.py` | **manter** | conservative-default | sim |
| service | `sociedades_service` | `backend/app/services/sociedades_service.py` | **manter** | conservative-default | sim |
| service | `solicitacao_documento_service` | `backend/app/services/solicitacao_documento_service.py` | **consolidar** | duplicate-family | sim |
| service | `sumulas_ingestion` | `backend/app/services/sumulas_ingestion.py` | **manter** | conservative-default | sim |
| service | `__init__` | `backend/app/services/system_prompts/__init__.py` | **consolidar** | duplicate-family | sim |
| service | `administrativo` | `backend/app/services/system_prompts/administrativo.py` | **manter** | conservative-default | sim |
| service | `agrario` | `backend/app/services/system_prompts/agrario.py` | **manter** | conservative-default | sim |
| service | `agronegocio` | `backend/app/services/system_prompts/agronegocio.py` | **manter** | conservative-default | sim |
| service | `ambiental` | `backend/app/services/system_prompts/ambiental.py` | **manter** | conservative-default | sim |
| service | `analise_caso` | `backend/app/services/system_prompts/analise_caso.py` | **manter** | conservative-default | sim |
| service | `base` | `backend/app/services/system_prompts/base.py` | **consolidar** | duplicate-family | sim |
| service | `blocos_condicionais` | `backend/app/services/system_prompts/blocos_condicionais.py` | **manter** | conservative-default | sim |
| service | `civel` | `backend/app/services/system_prompts/civel.py` | **manter** | conservative-default | sim |
| service | `constitucional` | `backend/app/services/system_prompts/constitucional.py` | **manter** | conservative-default | sim |
| service | `consumidor` | `backend/app/services/system_prompts/consumidor.py` | **manter** | conservative-default | sim |
| service | `contratual` | `backend/app/services/system_prompts/contratual.py` | **manter** | conservative-default | sim |
| service | `criminal` | `backend/app/services/system_prompts/criminal.py` | **manter** | conservative-default | sim |
| service | `eleitoral` | `backend/app/services/system_prompts/eleitoral.py` | **manter** | conservative-default | sim |
| service | `empresarial` | `backend/app/services/system_prompts/empresarial.py` | **manter** | conservative-default | sim |
| service | `familia` | `backend/app/services/system_prompts/familia.py` | **manter** | conservative-default | sim |
| service | `honorarios` | `backend/app/services/system_prompts/honorarios.py` | **consolidar** | duplicate-family | sim |
| service | `imobiliario` | `backend/app/services/system_prompts/imobiliario.py` | **manter** | conservative-default | sim |
| service | `internacional` | `backend/app/services/system_prompts/internacional.py` | **manter** | conservative-default | sim |
| service | `juizados` | `backend/app/services/system_prompts/juizados.py` | **manter** | conservative-default | sim |
| service | `medico` | `backend/app/services/system_prompts/medico.py` | **manter** | conservative-default | sim |
| service | `minutas` | `backend/app/services/system_prompts/minutas.py` | **manter** | conservative-default | sim |
| service | `padrao_ouro` | `backend/app/services/system_prompts/padrao_ouro.py` | **manter** | conservative-default | sim |
| service | `prazos` | `backend/app/services/system_prompts/prazos.py` | **consolidar** | duplicate-family | sim |
| service | `previdenciario` | `backend/app/services/system_prompts/previdenciario.py` | **manter** | conservative-default | sim |
| service | `saude` | `backend/app/services/system_prompts/saude.py` | **manter** | conservative-default | sim |
| service | `sucessoes` | `backend/app/services/system_prompts/sucessoes.py` | **manter** | conservative-default | sim |
| service | `templates_documentos` | `backend/app/services/system_prompts/templates_documentos.py` | **manter** | conservative-default | sim |
| service | `trabalhista` | `backend/app/services/system_prompts/trabalhista.py` | **consolidar** | duplicate-family | sim |
| service | `transito` | `backend/app/services/system_prompts/transito.py` | **manter** | conservative-default | sim |
| service | `triagem` | `backend/app/services/system_prompts/triagem.py` | **manter** | conservative-default | sim |
| service | `tributario` | `backend/app/services/system_prompts/tributario.py` | **manter** | conservative-default | sim |
| service | `taskscore` | `backend/app/services/taskscore.py` | **manter** | conservative-default | sim |
| service | `transparencia_service` | `backend/app/services/transparencia_service.py` | **consolidar** | duplicate-family | sim |
| service | `validador_juridico_service` | `backend/app/services/validador_juridico_service.py` | **consolidar** | duplicate-family | sim |
| service | `validators_service` | `backend/app/services/validators_service.py` | **manter** | conservative-default | sim |
| service | `vault_crypto` | `backend/app/services/vault_crypto.py` | **manter** | conservative-default | sim |
| service | `verificador_jurisprudencia` | `backend/app/services/verificador_jurisprudencia.py` | **manter** | conservative-default | sim |
| service | `visual_law` | `backend/app/services/visual_law.py` | **consolidar** | duplicate-family | sim |
| service | `visual_law_core` | `backend/app/services/visual_law_core.py` | **manter** | conservative-default | sim |
| service | `visual_law_files` | `backend/app/services/visual_law_files.py` | **manter** | conservative-default | sim |
| service | `visual_law_pdf` | `backend/app/services/visual_law_pdf.py` | **manter** | conservative-default | sim |
| service | `visual_law_theme` | `backend/app/services/visual_law_theme.py` | **manter** | conservative-default | sim |
| service | `war_room` | `backend/app/services/war_room.py` | **manter** | conservative-default | sim |

## Tabelas

| Tipo | Item | Arquivo/rota | Classificação | Fonte | Revisão |
|---|---|---|---|---|---|
| table | `ai_logs` | `backend/app/models/ai_log.py:129` | **manter** | conservative-default | sim |
| table | `ai_provider_metrics` | `backend/app/models/ai_provider_metric.py:10` | **manter** | conservative-default | sim |
| table | `ejc_skills` | `backend/app/models/ai_skill.py:6` | **manter** | conservative-default | sim |
| table | `api_keys` | `backend/app/models/api_key.py:17` | **manter** | conservative-default | sim |
| table | `atendimentos` | `backend/app/models/atendimento.py:33` | **manter** | conservative-default | sim |
| table | `audit_logs` | `backend/app/models/audit_log.py:11` | **manter** | conservative-default | sim |
| table | `bank_analyses` | `backend/app/models/bank_analysis.py:10` | **manter** | conservative-default | sim |
| table | `bank_transactions` | `backend/app/models/bank_analysis.py:32` | **manter** | conservative-default | sim |
| table | `bank_abusive_charges` | `backend/app/models/bank_analysis.py:44` | **manter** | conservative-default | sim |
| table | `calendar_feed_credentials` | `backend/app/models/calendar_feed_credential.py:9` | **manter** | conservative-default | sim |
| table | `cases` | `backend/app/models/case.py:66` | **corrigir** | override | não |
| table | `case_movimentos` | `backend/app/models/case.py:160` | **manter** | conservative-default | sim |
| table | `case_intelligence_snapshots` | `backend/app/models/case_intelligence.py:45` | **manter** | conservative-default | sim |
| table | `case_partes` | `backend/app/models/case_parte.py:11` | **manter** | conservative-default | sim |
| table | `caso_areas` | `backend/app/models/caso_area.py:10` | **manter** | conservative-default | sim |
| table | `centro_custos` | `backend/app/models/centro_custo.py:28` | **manter** | conservative-default | sim |
| table | `checklist_templates` | `backend/app/models/checklist.py:22` | **manter** | conservative-default | sim |
| table | `checklist_template_items` | `backend/app/models/checklist.py:45` | **manter** | conservative-default | sim |
| table | `case_checklists` | `backend/app/models/checklist.py:55` | **manter** | conservative-default | sim |
| table | `case_checklist_items` | `backend/app/models/checklist.py:76` | **manter** | conservative-default | sim |
| table | `clients` | `backend/app/models/client.py:30` | **manter** | conservative-default | sim |
| table | `contratos_societarios` | `backend/app/models/contrato_societario.py:35` | **manter** | conservative-default | sim |
| table | `contrato_historico` | `backend/app/models/contrato_societario.py:78` | **manter** | conservative-default | sim |
| table | `data_rooms` | `backend/app/models/data_room.py:12` | **manter** | conservative-default | sim |
| table | `data_room_arquivos` | `backend/app/models/data_room.py:27` | **manter** | conservative-default | sim |
| table | `data_room_links` | `backend/app/models/data_room.py:40` | **manter** | conservative-default | sim |
| table | `data_room_acesso_logs` | `backend/app/models/data_room.py:58` | **manter** | conservative-default | sim |
| table | `deadlines` | `backend/app/models/deadline.py:31` | **manter** | conservative-default | sim |
| table | `diario_oficial_keywords` | `backend/app/models/diario_oficial.py:12` | **manter** | conservative-default | sim |
| table | `diario_oficial_alertas` | `backend/app/models/diario_oficial.py:25` | **manter** | conservative-default | sim |
| table | `djen_comunicacoes` | `backend/app/models/djen.py:8` | **manter** | conservative-default | sim |
| table | `documents` | `backend/app/models/document.py:17` | **manter** | conservative-default | sim |
| table | `document_intake_batches` | `backend/app/models/document_intake.py:10` | **manter** | conservative-default | sim |
| table | `document_intake_items` | `backend/app/models/document_intake.py:34` | **manter** | conservative-default | sim |
| table | `dossies_estrategicos` | `backend/app/models/dossie_estrategico.py:12` | **manter** | conservative-default | sim |
| table | `environmental_cases` | `backend/app/models/environmental.py:34` | **manter** | conservative-default | sim |
| table | `empresarial_cases` | `backend/app/models/especializado.py:47` | **manter** | conservative-default | sim |
| table | `civel_cases` | `backend/app/models/especializado.py:142` | **manter** | conservative-default | sim |
| table | `penal_cases` | `backend/app/models/especializado.py:242` | **manter** | conservative-default | sim |
| table | `trabalhista_cases` | `backend/app/models/especializado.py:342` | **manter** | conservative-default | sim |
| table | `admin_cases` | `backend/app/models/especializado.py:432` | **manter** | conservative-default | sim |
| table | `bancario_cases` | `backend/app/models/especializado.py:516` | **manter** | conservative-default | sim |
| table | `fees` | `backend/app/models/fee.py:30` | **manter** | conservative-default | sim |
| table | `fee_payments` | `backend/app/models/fee.py:56` | **manter** | conservative-default | sim |
| table | `fee_cobranca_envios` | `backend/app/models/fee.py:71` | **manter** | conservative-default | sim |
| table | `fee_proposals` | `backend/app/models/fee_proposal.py:35` | **manter** | conservative-default | sim |
| table | `feriados` | `backend/app/models/feriado.py:9` | **manter** | conservative-default | sim |
| table | `fichas_triagem` | `backend/app/models/ficha_triagem.py:22` | **manter** | conservative-default | sim |
| table | `integration_credentials` | `backend/app/models/integration_credential.py:29` | **manter** | conservative-default | sim |
| table | `jurisprudencias_internas` | `backend/app/models/jurisprudencia_interna.py:20` | **manter** | conservative-default | sim |
| table | `legal_docs` | `backend/app/models/legal_doc.py:33` | **manter** | conservative-default | sim |
| table | `lgpd_registros_tratamento` | `backend/app/models/lgpd_tratamento.py:45` | **manter** | conservative-default | sim |
| table | `legal_issues` | `backend/app/models/matriz_teses.py:38` | **manter** | conservative-default | sim |
| table | `thesis_candidates` | `backend/app/models/matriz_teses.py:53` | **manter** | conservative-default | sim |
| table | `authority_records` | `backend/app/models/matriz_teses.py:86` | **manter** | conservative-default | sim |
| table | `evidence_links` | `backend/app/models/matriz_teses.py:111` | **manter** | conservative-default | sim |
| table | `notas_fiscais_servico` | `backend/app/models/nfse.py:28` | **manter** | conservative-default | sim |
| table | `notifications` | `backend/app/models/notification.py:9` | **manter** | conservative-default | sim |
| table | `notification_preferences` | `backend/app/models/notification.py:38` | **manter** | conservative-default | sim |
| table | `password_reset_tokens` | `backend/app/models/password_reset.py:4` | **manter** | conservative-default | sim |
| table | `user_known_ips` | `backend/app/models/password_reset.py:14` | **manter** | conservative-default | sim |
| table | `processes` | `backend/app/models/process.py:23` | **manter** | conservative-default | sim |
| table | `procuracoes` | `backend/app/models/procuracao.py:8` | **manter** | conservative-default | sim |
| table | `prompts_juridicos` | `backend/app/models/prompt_juridico.py:25` | **manter** | conservative-default | sim |
| table | `provas` | `backend/app/models/prova.py:32` | **manter** | conservative-default | sim |
| table | `push_subscriptions` | `backend/app/models/push.py:6` | **manter** | conservative-default | sim |
| table | `knowledge_docs` | `backend/app/models/rag.py:14` | **manter** | conservative-default | sim |
| table | `knowledge_chunks` | `backend/app/models/rag.py:61` | **manter** | conservative-default | sim |
| table | `fontes_ingestao` | `backend/app/models/rag.py:77` | **manter** | conservative-default | sim |
| table | `raio_x_analises` | `backend/app/models/raio_x.py:11` | **manter** | conservative-default | sim |
| table | `raio_x_documentos` | `backend/app/models/raio_x.py:55` | **manter** | conservative-default | sim |
| table | `module_help` | `backend/app/models/redesign.py:17` | **manter** | conservative-default | sim |
| table | `area_modulos_mapping` | `backend/app/models/redesign.py:37` | **manter** | conservative-default | sim |
| table | `document_types_master` | `backend/app/models/redesign.py:62` | **manter** | conservative-default | sim |
| table | `tabela_oab_honorarios` | `backend/app/models/redesign.py:85` | **manter** | conservative-default | sim |
| table | `scheduler_heartbeat` | `backend/app/models/scheduler_heartbeat.py:17` | **manter** | conservative-default | sim |
| table | `signature_requests` | `backend/app/models/signature.py:15` | **manter** | conservative-default | sim |
| table | `sociedades_cliente` | `backend/app/models/sociedade_cliente.py:41` | **manter** | conservative-default | sim |
| table | `socios_sociedade` | `backend/app/models/sociedade_cliente.py:59` | **manter** | conservative-default | sim |
| table | `eventos_societarios` | `backend/app/models/sociedade_cliente.py:79` | **manter** | conservative-default | sim |
| table | `socios` | `backend/app/models/socio.py:19` | **manter** | conservative-default | sim |
| table | `distribuicoes_lucro` | `backend/app/models/socio.py:40` | **manter** | conservative-default | sim |
| table | `solicitacoes_documentos` | `backend/app/models/solicitacao_documento.py:25` | **manter** | conservative-default | sim |
| table | `solicitacao_documento_itens` | `backend/app/models/solicitacao_documento.py:47` | **manter** | conservative-default | sim |
| table | `suspensoes_tribunal` | `backend/app/models/suspensao.py:10` | **manter** | conservative-default | sim |
| table | `system_module_settings` | `backend/app/models/system_module_setting.py:8` | **manter** | conservative-default | sim |
| table | `tasks` | `backend/app/models/task.py:13` | **manter** | conservative-default | sim |
| table | `doc_templates` | `backend/app/models/template.py:7` | **manter** | conservative-default | sim |
| table | `teses` | `backend/app/models/tese.py:27` | **manter** | conservative-default | sim |
| table | `tese_caso_links` | `backend/app/models/tese.py:62` | **manter** | conservative-default | sim |
| table | `time_entries` | `backend/app/models/time_entry.py:6` | **manter** | conservative-default | sim |
| table | `users` | `backend/app/models/user.py:21` | **manter** | conservative-default | sim |
| table | `refresh_tokens` | `backend/app/models/user.py:83` | **manter** | conservative-default | sim |
| table | `wiki_paginas` | `backend/app/models/wiki.py:8` | **manter** | conservative-default | sim |
| table | `workflow_templates` | `backend/app/models/workflow.py:21` | **manter** | conservative-default | sim |
| table | `workflow_etapas` | `backend/app/models/workflow.py:35` | **manter** | conservative-default | sim |
| table | `case_workflows` | `backend/app/models/workflow.py:50` | **manter** | conservative-default | sim |
| table | `workflow_historico` | `backend/app/models/workflow.py:66` | **manter** | conservative-default | sim |
| table | `dataroom_salas` | `backend/app/routers/data_room_v4.py:28` | **manter** | conservative-default | sim |
| table | `teses_juridicas_v4` | `backend/app/routers/teses_v4.py:26` | **manter** | conservative-default | sim |

## Routers não montados

| Tipo | Item | Arquivo/rota | Classificação | Fonte | Revisão |
|---|---|---|---|---|---|
| router | `__init__` | `backend/app/routers/__init__.py` | **desativar** | mount-analysis | sim |
| router | `advogado_estilo` | `backend/app/routers/advogado_estilo.py` | **desativar** | mount-analysis | sim |
| router | `api_keys` | `backend/app/routers/api_keys.py` | **desativar** | mount-analysis | sim |
| router | `datajud_intelligence` | `backend/app/routers/datajud_intelligence.py` | **desativar** | mount-analysis | sim |
| router | `defesas_revisoes` | `backend/app/routers/defesas_revisoes.py` | **desativar** | mount-analysis | sim |
| router | `defesas_revisoes_avancado` | `backend/app/routers/defesas_revisoes_avancado.py` | **desativar** | mount-analysis | sim |
| router | `defesas_revisoes_pacote_seguro` | `backend/app/routers/defesas_revisoes_pacote_seguro.py` | **desativar** | mount-analysis | sim |
| router | `entrada_universal` | `backend/app/routers/entrada_universal.py` | **desativar** | mount-analysis | sim |
| router | `entrada_universal_vinculo` | `backend/app/routers/entrada_universal_vinculo.py` | **desativar** | mount-analysis | sim |
| router | `google_drive_knowledge` | `backend/app/routers/google_drive_knowledge.py` | **desativar** | mount-analysis | sim |
| router | `ia_provider_metrics` | `backend/app/routers/ia_provider_metrics.py` | **consolidar** | override | não |
| router | `precedentes_jurisprudencia` | `backend/app/routers/precedentes_jurisprudencia.py` | **desativar** | mount-analysis | sim |
| router | `rag_governance` | `backend/app/routers/rag_governance.py` | **desativar** | mount-analysis | sim |
| router | `router` | `backend/app/services/system_prompts/router.py` | **desativar** | mount-analysis | sim |

## Critério de remoção

Um item classificado como `excluir após migração` somente pode ser removido após:

1. comprovação de ausência de consumidores frontend, scripts, jobs, webhooks e integrações;
2. período de telemetria ou logs sem uso;
3. alias/redirecionamento quando houver rota pública ou favorita histórica;
4. migração/backfill de dados quando houver persistência;
5. testes de regressão e rollback documentado;
6. aprovação explícita no PR de remoção.

## Arquivos complementares

- `architecture_inventory.json`: representação integral e estruturada;
- `architecture_inventory.csv`: planilha única para triagem e filtros;
- `classification_review.csv`: somente itens que exigem revisão humana;
- `duplicate_families.json`: famílias candidatas à consolidação;
- `manifest.json`: contagens, fingerprint e resultado do gate.
